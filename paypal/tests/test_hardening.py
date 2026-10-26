"""Failure paths found in the backend review: each test is a way money could
be miscounted, a decision left half-made, or the public server worn down."""

import json
import threading
import time

import httpx
from fastapi.testclient import TestClient

from conftest import DAY, World, answer
from remit_paypal.agent import Session, ToolAgent
from remit_paypal.ledger import Ledger
from remit_paypal.panel import Panel
from remit_paypal.paypal_api import PayPalError


def kinds(w, request_id):
    return [e["kind"] for e in w.ledger.entries() if e["body"].get("request_id") == request_id]


# ------------------------------------------------------------- the guard

def test_a_reused_request_id_leaves_the_log_untouched():
    w = World()
    o, _ = w.order(cents=4500, delivered_at=w.now - 2 * DAY)
    w.ask(o, 1000, customer="broken", request_id="same")
    before = len(w.ledger.entries())
    try:
        w.ask(o, 1000, customer="broken", request_id="same")
        raise AssertionError("a reused request id must be refused")
    except Exception as exc:
        assert "already submitted" in str(exc)
    assert len(w.ledger.entries()) == before  # no stray "requested" entry for the duplicate


def test_an_unexpected_error_mid_decision_ends_the_request_refused():
    w = World(models={"a": lambda p: answer("in_remit"), "b": lambda p: answer("in_remit"),
                      "c": lambda p: answer("in_remit")})
    o, _ = w.order(cents=4500, delivered_at=w.now - 2 * DAY)

    def boom(*a, **k):
        raise KeyError("panel exploded")

    w.guard.panel.decide = boom
    d = w.ask(o, 4500, customer="broken", request_id="r1")
    assert d.outcome == "refused" and d.stage == "error" and w.paypal.refund_calls == 0
    assert w.ledger.get("r1")["state"] == "refused" and kinds(w, "r1")[-1] == "refused"


def test_a_refund_paypal_may_have_made_counts_against_the_caps():
    """A timeout after PayPal received the refund leaves it unknown whether
    money moved. The caps must assume it did: fail closed."""
    w = World()
    first = [w.order(cents=9000, payer_id="P%d" % i, delivered_at=w.now - DAY)[0] for i in range(4)]
    w.paypal.fail_refund = httpx.ReadTimeout("timed out")
    d = w.ask(first[0], 9000, customer="broken")
    assert d.outcome == "refused" and d.stage == "paypal" and w.ledger.get(d.request_id)["state"] == "unknown"
    outcomes = [w.ask(o, 9000, customer="broken").outcome for o in first[1:]]
    assert outcomes == ["allowed", "allowed", "refused"]  # 90 unknown + 180 = 270; another 90 passes the 300 cap


def test_a_refund_paypal_declined_does_not_count_against_the_caps():
    w = World()
    ids = [w.order(cents=9000, payer_id="P%d" % i, delivered_at=w.now - DAY)[0] for i in range(4)]
    w.paypal.fail_refund = PayPalError(422, "UNPROCESSABLE_ENTITY", "capture cannot be refunded")
    d = w.ask(ids[0], 9000, customer="broken")
    assert d.outcome == "refused" and w.ledger.get(d.request_id)["state"] == "failed"
    assert [w.ask(o, 9000, customer="broken").outcome for o in ids[1:]] == ["allowed", "allowed", "allowed"]


def test_a_decision_cut_off_by_a_crash_counts_against_the_caps(tmp_path):
    path = str(tmp_path / "log.sqlite3")
    Ledger(path).start("crashed", "0xabc", "P0", "C0", 9000, "damaged", World().now)  # never finished
    w = World()
    w.ledger = w.guard.ledger = Ledger(path)
    ids = [w.order(cents=9000, payer_id="P%d" % i, delivered_at=w.now - DAY)[0] for i in range(1, 4)]
    assert [w.ask(o, 9000, customer="broken").outcome for o in ids] == ["allowed", "allowed", "refused"]


# ------------------------------------------------------------- the panel

def test_a_hung_model_does_not_hold_the_decision_past_the_timeout():
    release = threading.Event()

    def hung(prompt):
        release.wait(10)
        return answer("in_remit")

    panel = Panel({"a": lambda p: answer("in_remit"), "b": hung}, quorum=1, timeout=0.5)
    started = time.time()
    verdict, votes = panel.decide("q")
    release.set()
    assert time.time() - started < 3
    assert {v.model: v.verdict for v in votes}["b"] == "undetermined"


# ------------------------------------------------------------- the agent

class FakeMCP:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))

        class R:
            is_error = False
            content = [type("T", (), {"text": json.dumps({"ok": True})})()]
        return R()


def test_the_agent_sends_a_numeric_amount_as_the_decimal_string_the_tool_takes():
    import asyncio

    mcp = FakeMCP()
    agent = ToolAgent(mcp, lambda *a: None, "m", "k", "http://x")
    s = Session("s1", ["ORDER-0001"])
    s.customer_lines.append("broken")
    call = {"id": "c1", "function": {"name": "request_refund",
                                     "arguments": json.dumps({"order_id": "ORDER-0001", "amount": 45, "reason": "damaged"})}}
    asyncio.run(agent._run(s, call))
    assert mcp.calls[0][1]["amount"] == "45.00"


def test_a_long_conversation_is_trimmed_without_splitting_a_tool_call():
    from remit_paypal.agent import trim

    msgs = [{"role": "system", "content": "s"}]
    for i in range(40):
        msgs += [{"role": "user", "content": "u%d" % i},
                 {"role": "assistant", "content": None, "tool_calls": [{"id": "c%d" % i}]},
                 {"role": "tool", "tool_call_id": "c%d" % i, "content": "{}"},
                 {"role": "assistant", "content": "a%d" % i}]
    out = trim(msgs, keep=30)
    assert out[0]["role"] == "system" and out[1]["role"] == "user" and len(out) <= 31
    assert out[-1] == msgs[-1]


# ------------------------------------------------------------- the server

def make_app(**kw):
    from remit_paypal.web import create_app
    w = World()
    o, _ = w.order(cents=4500, delivered_at=w.now - 2 * DAY)
    return create_app(w.guard, orders_for=lambda sid: [o], **kw), w


def test_old_sessions_are_dropped_so_memory_stays_bounded():
    app, _ = make_app(max_sessions=3)
    with TestClient(app) as c:
        sids = [c.post("/api/session").json()["session_id"] for _ in range(5)]
        assert c.get("/api/orders", params={"session_id": sids[0]}).status_code == 404
        assert c.get("/api/orders", params={"session_id": sids[-1]}).status_code == 200


def test_new_sessions_are_capped_for_everyone_not_only_per_address():
    """A client can claim any address in X-Forwarded-For, so the per-address
    limit alone does not bound how many sandbox orders get created."""
    app, _ = make_app(sessions_per_hour=100, all_sessions_per_hour=3)
    with TestClient(app) as c:
        codes = [c.post("/api/session", headers={"X-Forwarded-For": "10.0.0.%d" % i}).status_code for i in range(5)]
        assert codes == [200, 200, 200, 429, 429]


def test_health_answers_without_reading_the_whole_log():
    app, w = make_app()
    w.ledger.verify = lambda: (_ for _ in ()).throw(AssertionError("health must not verify the whole log"))
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["ok"] and h["mode"] == "offline" and "log_head" in h


# ------------------------------------------------------------- the log

def test_the_log_is_served_in_pages_and_verified_whole():
    app, w = make_app()
    for i in range(5):
        w.ledger.append(w.now, "note", {"i": i})
    import remit_paypal.web as web
    old, web.LOG_PAGE = web.LOG_PAGE, 2
    try:
        with TestClient(app) as c:
            got, since = [], 0
            while since is not None:
                page = c.get("/api/log", params={"since": since}).json()
                assert page["verifies"] and page["head"] == 5 and len(page["entries"]) <= 2
                got += [e["seq"] for e in page["entries"]]
                since = page["next"]
            assert got == [1, 2, 3, 4, 5]
            assert [e["seq"] for e in c.get("/api/log", params={"tail": 2}).json()["entries"]] == [4, 5]
    finally:
        web.LOG_PAGE = old


def test_a_retried_write_that_already_landed_is_not_an_error():
    led = Ledger()
    seq, h = led.append(1, "note", {"a": 1})
    real = led.db.execute

    def replayed(sql, params=()):  # the reconnect retry: the row is already there
        if sql.startswith("INSERT INTO log"):
            real(sql, params)
            return real(sql, params)
        return real(sql, params)

    led.db.execute = replayed
    assert led.append(2, "note", {"b": 2})[0] == seq + 1 and led.verify() == (True, None)


def test_the_anchor_check_is_cached_while_the_log_is_unchanged():
    from remit_paypal.anchor import Anchorer, FakeAnchor

    led, chain = Ledger(), FakeAnchor()
    led.append(1, "note", {})
    a = Anchorer(led, chain)
    a.anchor_once()
    reads = []
    real = chain.latest
    chain.latest = lambda: reads.append(1) or real()
    assert a.status()["check"]["matches"] and a.status()["check"]["matches"]
    assert len(reads) == 1  # the second status reused the first check
    led.append(2, "note", {})
    a.status()
    assert len(reads) == 2  # a longer log is checked again


def test_a_refund_paypal_made_is_reported_even_if_recording_it_fails():
    w = World()
    o, _ = w.order(cents=4500, delivered_at=w.now - 2 * DAY)
    real = w.ledger.finish

    def finish(request_id, state, refund_id=None):
        if state == "refunded":
            raise ConnectionError("database went away")
        return real(request_id, state, refund_id)

    w.ledger.finish = finish
    d = w.ask(o, 4500, customer="broken", request_id="r1")
    assert d.outcome == "allowed" and d.refund_id and "could not finish" in d.reason
    assert w.ledger.get("r1")["state"] == "unknown"  # counted against the caps
