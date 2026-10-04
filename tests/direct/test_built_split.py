"""The first slice of a split, run through the built guard and rail.

Deploys engine, prompts, guard and rail in the GenVM stand-in, from the
readable build and the deployed ``*.min.py`` bytes, requires identical
results, and checks that the rail - the only contract that moves value - pays
the slice under the cap only when the slice that tripped the structuring
trigger is cleared:

A. second slice held: the first waits; refused as a split: the first is
   refused with it;
B. second slice allowed: both pay;
C. the first slice paid before the second arrived: nothing to hold (the gap
   that remains is the court's, and the finality delay's length);
D. second slice refused under another rule as well: not a ruling on the split,
   so the first pays once the second is decided.
"""

import json
import os

import pytest

from genvm_stub import Runtime, deploy, load

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.path.join(ROOT, "contracts", "build")
PRINCIPAL = "0x00000000000000000000000000000000000000d1"
AGENT = "0x00000000000000000000000000000000000000c1"
VENDOR = "0x00000000000000000000000000000000000000a1"
OTHER = "0x00000000000000000000000000000000000000a2"
E, P, G, R = "0xe0", "0xe1", "0xe2", "0xe3"
GEN = 10**15
DAY = 86400
FINALITY = 60

MANDATE = json.dumps(
    {
        "remit_mandate_version": 1, "version": 1, "currency": "ATTO_GEN",
        "defaults": {"on_deadline": "refund", "on_undetermined": "refund", "response_window_seconds": 60,
                     "hold_deadline_seconds": 3600, "clawback_window_seconds": 7 * DAY},
        "vendor_lists": {"vendors": [VENDOR, OTHER]},
        "rules": [
            {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 200 * GEN}},
            {"id": "allowlist", "type": "reflex", "check": {"recipient_in": "vendors"}},
            {"id": "structuring", "type": "judgment",
             "when": {"recipient_total_gte": {"amount": 200 * GEN + 1, "seconds": DAY}},
             "ask": "Are these payments one purchase split under the cap?", "on_breach": {"tier": 2}},
            {"id": "large", "type": "judgment", "when": {"amount_gte": 180 * GEN},
             "ask": "Was this large payment approved in advance?", "on_breach": {"tier": 2}},
        ],
    }
)


def scenario(suffix):
    rt = Runtime()
    rt.model = lambda prompt: {"verdict": "undetermined", "reason": "insufficient_evidence", "confidence": 50}
    ns = {n: load(os.path.join(BUILD, n + suffix), rt) for n in ("engine", "prompts", "guard", "rail")}
    deploy(rt, ns["prompts"], "RemitPrompts", P)
    deploy(rt, ns["engine"], "RemitEngine", E, P)
    deploy(rt, ns["guard"], "RemitGuard", G, AGENT, MANDATE, 3, False, E, sender=PRINCIPAL)
    deploy(rt, ns["rail"], "RemitRail", R, G, FINALITY, 10 * GEN, sender=PRINCIPAL)
    out = {}

    def tx(label, address, method, *args, sender, value=0):
        try:
            result = rt.call(address, method, *args, sender=sender, value=value)
            out[label] = "ok" if result is None else result
        except Exception as exc:
            out[label] = "refused: " + str(exc)
        return out[label]

    def state(i):
        return json.loads(rt.contracts[G].get_spend(i))["state"]

    tx("attach", G, "attach_rail", R, sender=PRINCIPAL)
    tx("fund", R, "fund", sender=PRINCIPAL, value=2000 * GEN)

    # A. 150 then 100 to one vendor: the second trips the trigger.
    tx("A spend 0", G, "request_spend", VENDOR, 150 * GEN, "media", "", "", "part one", sender=AGENT)
    rt.now += FINALITY + 1
    tx("A spend 1", G, "request_spend", VENDOR, 100 * GEN, "media", "", "", "part two", sender=AGENT)
    out["A states"] = [state(0), state(1)]
    tx("A pay 0 while 1 is held", R, "pay", 0, sender=VENDOR)
    tx("A refuse 1", G, "override_refuse", 1, sender=PRINCIPAL)
    tx("A pay 0 after the split is refused", R, "pay", 0, sender=VENDOR)

    # B. The same shape to another vendor, ruled separate purchases.
    tx("B spend 2", G, "request_spend", OTHER, 150 * GEN, "media", "", "", "hosting", sender=AGENT)
    rt.now += FINALITY + 1
    tx("B spend 3", G, "request_spend", OTHER, 100 * GEN, "media", "", "", "re-edit", sender=AGENT)
    tx("B pay 2 while 3 is held", R, "pay", 2, sender=OTHER)
    tx("B release 3", G, "override_release", 3, sender=PRINCIPAL)
    rt.now += FINALITY + 1
    tx("B pay 2", R, "pay", 2, sender=OTHER)
    tx("B pay 3", R, "pay", 3, sender=OTHER)

    # C. Past every window: the first slice is paid before the second exists.
    rt.now += DAY + 1
    tx("C spend 4", G, "request_spend", VENDOR, 150 * GEN, "media", "", "", "part one", sender=AGENT)
    rt.now += FINALITY + 1
    tx("C pay 4 before any second slice", R, "pay", 4, sender=VENDOR)
    tx("C spend 5", G, "request_spend", VENDOR, 100 * GEN, "media", "", "", "part two", sender=AGENT)
    out["C state 5"] = state(5)
    tx("C pay 4 again", R, "pay", 4, sender=VENDOR)

    # D. The second slice also trips another rule; refused under both.
    rt.now += DAY + 1
    tx("D spend 6", G, "request_spend", OTHER, 100 * GEN, "media", "", "", "part one", sender=AGENT)
    rt.now += FINALITY + 1
    tx("D spend 7", G, "request_spend", OTHER, 190 * GEN, "media", "", "", "part two", sender=AGENT)
    out["D rules 7"] = json.loads(rt.contracts[G].get_spend(7))["rules"]
    tx("D pay 6 while 7 is held", R, "pay", 6, sender=OTHER)
    tx("D refuse 7", G, "override_refuse", 7, sender=PRINCIPAL)
    tx("D pay 6 after a mixed refusal", R, "pay", 6, sender=OTHER)

    out["status"] = json.loads(rt.contracts[R].status())
    out["transfers"] = list(rt.transfers)
    return out


@pytest.fixture(scope="module")
def readable():
    return scenario(".py")


@pytest.fixture(scope="module")
def deployed():
    return scenario(".min.py")


def test_deployed_bytes_behave_exactly_like_the_tested_build(readable, deployed):
    assert readable == deployed


def test_A_the_first_slice_waits_then_falls_with_the_split(readable):
    r = readable
    assert r["A states"] == ["settled", "held"]
    assert r["A pay 0 while 1 is held"] == "refused: [EXPECTED] waits: a later payment to this vendor is held as a split of it"
    assert r["A refuse 1"] == "ok"
    assert r["A pay 0 after the split is refused"] == "refused: [EXPECTED] refused with the split it belongs to"


def test_B_separate_purchases_both_pay(readable):
    r = readable
    assert r["B pay 2 while 3 is held"].startswith("refused: [EXPECTED] waits")
    assert (r["B release 3"], r["B pay 2"], r["B pay 3"]) == ("ok", "ok", "ok")
    assert (R, OTHER, 150 * GEN) in r["transfers"] and (R, OTHER, 100 * GEN) in r["transfers"]


def test_C_a_slice_paid_before_the_second_arrives_is_not_held_after_the_fact(readable):
    r = readable
    assert r["C pay 4 before any second slice"] == "ok"
    assert r["C state 5"] == "held"
    assert r["C pay 4 again"] == "refused: [EXPECTED] spend already paid"


def test_D_a_refusal_under_another_rule_too_is_not_a_ruling_on_the_split(readable):
    r = readable
    assert r["D rules 7"] == ["structuring", "large"]
    assert r["D pay 6 while 7 is held"].startswith("refused: [EXPECTED] waits")
    assert r["D pay 6 after a mixed refusal"] == "ok"


def test_the_first_slice_of_a_refused_split_never_leaves_the_rail(readable):
    paid_to_vendor = [a for (_, to, a) in readable["transfers"] if to == VENDOR]
    assert paid_to_vendor == [150 * GEN]  # only C's slice, paid before any split existed
