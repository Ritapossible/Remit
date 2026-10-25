"""The anchorer against an in-memory RemitAnchor: only the newest head is
sent, outages queue and catch up, refunds never wait, and a rewritten log no
longer matches what was anchored."""

import threading
import time

from conftest import DAY, MANDATE, World
from fastapi.testclient import TestClient

from remit_paypal.anchor import Anchorer, FakeAnchor, recompute, verify
from remit_paypal.guard import Guard, load_mandate
from remit_paypal.ledger import Ledger
from remit_paypal.offline import offline_models, offline_paypal
from remit_paypal.panel import Panel
from remit_paypal.web import create_app


def decided(world, n=2):
    o, _ = world.order(cents=9000, delivered_at=world.now - DAY)
    for i in range(n):
        world.ask(o, 1000, customer="It arrived broken.")
    return world


def test_only_the_newest_head_is_anchored_and_it_matches():
    w = decided(World())
    chain = FakeAnchor()
    a = Anchorer(w.ledger, chain, contract="0xc")
    first = a.anchor_once()
    head = w.ledger.head()
    assert first["seq"] == head["seq"] and first["hash"] == head["hash"] and chain.calls == 1
    assert a.anchor_once() is None and chain.calls == 1  # nothing new, nothing sent
    assert verify(w.ledger, chain) == {"matches": True, "seq": head["seq"], "hash": head["hash"]}
    decided(w, 1)
    second = a.anchor_once()
    assert second["seq"] == w.ledger.head()["seq"] > first["seq"] and chain.calls == 2
    assert a.anchor_covering(1)["seq"] == first["seq"] and a.anchor_covering(first["seq"] + 1)["seq"] == second["seq"]


def test_an_outage_queues_and_catches_up():
    w = decided(World())
    chain = FakeAnchor()
    chain.fail = 2
    a = Anchorer(w.ledger, chain)
    assert a.anchor_once() is None and "unavailable" in a.last_error and a.status(check_chain=False)["pending"]
    assert a.anchor_once() is None
    assert a.anchor_once()["seq"] == w.ledger.head()["seq"] and a.last_error == ""
    assert not a.status(check_chain=False)["pending"]


def test_a_rewritten_log_no_longer_matches_its_anchor():
    w = decided(World())
    chain = FakeAnchor()
    Anchorer(w.ledger, chain).anchor_once()
    # The operator edits an early entry and rebuilds every hash after it, so the
    # local chain verifies again; GenLayer still holds the original.
    w.ledger.db.execute("UPDATE log SET body = replace(body, 'broken', 'fine') WHERE seq = 1")
    from remit_paypal.ledger import GENESIS, entry_hash
    prev = GENESIS
    for seq, at, kind, body in w.ledger.db.execute("SELECT seq, at, kind, body FROM log ORDER BY seq").fetchall():
        h = entry_hash(prev, seq, at, kind, body)
        w.ledger.db.execute("UPDATE log SET prev = ?, hash = ? WHERE seq = ?", (prev, h, seq))
        prev = h
    assert w.ledger.verify() == (True, None)
    result = verify(w.ledger, chain)
    assert result["matches"] is False and "differs from what was anchored" in result["reason"]


def test_a_broken_local_chain_is_reported_and_nothing_anchored_yet_is_said():
    w = decided(World())
    chain = FakeAnchor()
    assert verify(w.ledger, chain) == {"matches": None, "reason": "nothing anchored yet"}
    Anchorer(w.ledger, chain).anchor_once()
    w.ledger.db.execute("UPDATE log SET body = replace(body, 'broken', 'fine') WHERE seq = 1")
    assert verify(w.ledger, chain)["matches"] is False


def test_recompute_matches_the_servers_hashes_without_trusting_them():
    w = decided(World())
    entries = w.ledger.entries()
    assert recompute(entries) == {e["seq"]: e["hash"] for e in entries}
    entries[0]["body"]["customer_text"] = "rewritten"
    assert recompute(entries)[entries[-1]["seq"]] != entries[-1]["hash"]


def app_with(chain):
    with open(MANDATE) as f:
        guard = Guard(offline_paypal(time.time()), Ledger(), load_mandate(f.read()), Panel(offline_models(), quorum=2))
    anchorer = Anchorer(guard.ledger, chain, contract="0xabc", retry_seconds=0.2)
    return create_app(guard, orders_for=lambda sid: sorted(guard.paypal.orders), anchorer=anchorer), anchorer


def test_a_refund_never_waits_for_genlayer_and_the_web_shows_the_anchor():
    chain = FakeAnchor()
    chain.gate = threading.Event()  # GenLayer is stuck: every anchor send waits
    app, anchorer = app_with(chain)
    with TestClient(app) as c:
        sid = c.post("/api/session").json()["session_id"]
        t0 = time.time()
        r = c.post("/api/chat", json={"session_id": sid, "message": "ORDER-0001 arrived broken, refund please"})
        assert r.status_code == 200 and "Done" in r.json()["reply"] and time.time() - t0 < 3
        assert c.get("/api/anchor").json()["pending"] is True
        chain.gate.set()  # GenLayer is back
        for _ in range(50):
            status = c.get("/api/anchor").json()
            if not status["pending"] and status["check"]["matches"]:
                break
            time.sleep(0.1)
        assert status["configured"] and status["check"]["matches"] is True
        assert status["explorer"].endswith("/address/0xabc")
        d = c.get("/api/decisions/%s-r1" % sid).json()
        assert d["anchor"] and d["anchor"]["seq"] >= d["log"][-1]["seq"]
    assert anchorer.thread is not None and not anchorer.thread.is_alive()


def test_without_anchoring_configured_the_app_says_so():
    with open(MANDATE) as f:
        guard = Guard(offline_paypal(time.time()), Ledger(), load_mandate(f.read()), Panel(offline_models(), quorum=2))
    with TestClient(create_app(guard, orders_for=lambda sid: [])) as c:
        assert c.get("/api/anchor").json() == {"configured": False}
