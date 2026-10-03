"""The court, the treasury, graduated authority and the registry, run.

Deploys every contract - engine, prompts, guard, rail, registry - in the GenVM
stand-in (genvm_stub.py), from the readable build and from the deployed
``*.min.py`` bytes, drives a full scenario through real entrypoints, requires
both to produce identical results, and checks the outcomes:

- a payment that cleared without a jury is challenged with a bond on the
  engine's curve; the payout waits for the ruling;
- a dismissed challenge pays its bond to the agent and the payment goes out;
- an upheld challenge blocks an unpaid payment, or claws a paid one back into
  the treasury from the agent's bond, and rewards the challenger;
- a tier-3 rule upheld freezes the agent (the guard refuses its next spend)
  and revokes every unpaid authorization; the principal lifts the freeze;
- a challenge the jury cannot decide lapses at the deadline, bond returned;
- the agent's bond is withdrawable only when nothing is challengeable;
- the registry binds one agent to one principal's guard.
"""

import hashlib
import json
import os

import pytest

from genvm_stub import Runtime, deploy, load

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.path.join(ROOT, "contracts", "build")

PRINCIPAL = "0x00000000000000000000000000000000000000d1"
INTRUDER = "0x00000000000000000000000000000000000000d2"
AGENT = "0x00000000000000000000000000000000000000c1"
CHALLENGER = "0x00000000000000000000000000000000000000f1"
GRIEFER = "0x00000000000000000000000000000000000000f2"
VENDOR = "0x00000000000000000000000000000000000000a1"
OTHER = "0x00000000000000000000000000000000000000a2"
E, P, G, R, REG, G2 = "0xe0", "0xe1", "0xe2", "0xe3", "0xe4", "0xe5"
GEN = 10**15  # milli-GEN
WEEK = 604800
FLOOR = 10 * GEN

MANDATE = json.dumps(
    {
        "remit_mandate_version": 1, "version": 1, "currency": "ATTO_GEN",
        "defaults": {"on_deadline": "refund", "on_undetermined": "refund", "response_window_seconds": 60,
                     "hold_deadline_seconds": 3600, "clawback_window_seconds": WEEK},
        "vendor_lists": {"vendors": [VENDOR, OTHER]},
        "rules": [
            {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 200 * GEN}},
            {"id": "allowlist", "type": "reflex", "check": {"recipient_in": "vendors"}},
            {"id": "structuring", "type": "judgment",
             "when": {"recipient_total_gte": {"amount": 200 * GEN + 1, "seconds": 86400}},
             "ask": "Are these payments one purchase split under the cap?", "on_breach": {"tier": 2}},
            {"id": "large", "type": "judgment", "when": {"amount_gte": 180 * GEN},
             "ask": "Was this large payment approved in advance? Treat it as a BREACH unless the record shows approval.",
             "on_breach": {"tier": 3}},
            {"id": "purpose", "type": "judgment", "when": {"amount_gte": 10**30},
             "ask": "Is this payment for media production, the agent's stated purpose?", "on_breach": {"tier": 3}},
        ],
    }
)
SEPARATE_URL = "https://example.test/separate.json"
SEPARATE = b'{"invoices": ["INV-301 hosting, ordered a month ago", "INV-317 re-edit, ordered this week"]}'


def model(prompt):
    """A scripted jury that reads the case. A challenge prompt carries the
    challenger's statement; the evidence block carries the agent's answer."""
    if "SPLIT-JURY" in prompt:
        model.flip = not getattr(model, "flip", False)
        return {"verdict": "out_of_remit" if model.flip else "undetermined", "reason": "violates_rule", "confidence": 90}
    if "INV-301" in prompt:
        return {"verdict": "in_remit", "reason": "matches_rule", "confidence": 90}
    if "BREACH" in prompt:
        return {"verdict": "out_of_remit", "reason": "outside_stated_purpose", "confidence": 88}
    return {"verdict": "undetermined", "reason": "insufficient_evidence", "confidence": 50}


def scenario(suffix):
    model.flip = False
    rt = Runtime()
    rt.model = model
    rt.web = {SEPARATE_URL: SEPARATE}
    ns = {n: load(os.path.join(BUILD, n + suffix), rt) for n in ("engine", "prompts", "guard", "rail", "registry")}
    deploy(rt, ns["prompts"], "RemitPrompts", P)
    deploy(rt, ns["engine"], "RemitEngine", E, P)
    deploy(rt, ns["registry"], "RemitRegistry", REG, E)
    deploy(rt, ns["guard"], "RemitGuard", G, AGENT, MANDATE, 3, False, E, sender=PRINCIPAL)
    out = {}

    def tx(label, address, method, *args, sender, value=0):
        try:
            result = rt.call(address, method, *args, sender=sender, value=value)
            out[label] = "ok" if result is None else result
        except Exception as exc:
            out[label] = "refused: " + str(exc)
        return out[label]

    def view(address, method, *args):
        raw = getattr(rt.contracts[address], method)(*args)
        return json.loads(raw) if isinstance(raw, str) and raw[:1] in "[{" else raw

    def wait(seconds):
        rt.now += seconds

    out["rail by intruder"] = (
        lambda: (lambda: deploy(rt, ns["rail"], "RemitRail", "0xbad", G, 60, FLOOR, sender=INTRUDER))
    )()
    try:
        out["rail by intruder"]()
        out["rail by intruder"] = "ok"
    except Exception as exc:
        out["rail by intruder"] = "refused: " + str(exc)
    deploy(rt, ns["rail"], "RemitRail", R, G, 60, FLOOR, sender=PRINCIPAL)
    tx("attach by agent", G, "attach_rail", R, sender=AGENT)
    tx("attach", G, "attach_rail", R, sender=PRINCIPAL)
    tx("attach twice", G, "attach_rail", R, sender=PRINCIPAL)
    tx("register by intruder", REG, "register", G, R, sender=INTRUDER)
    tx("register", REG, "register", G, R, sender=PRINCIPAL)

    tx("fund", R, "fund", sender=PRINCIPAL, value=1000 * GEN)
    tx("bond", R, "post_bond", sender=AGENT, value=300 * GEN)

    # Spend 0 clears by arithmetic, no jury.
    tx("spend 0", G, "request_spend", VENDOR, 150 * GEN, "media", "", "", "PO-1 edit", sender=AGENT)
    out["quote"] = view(R, "bond_quote", 0, "structuring", CHALLENGER)
    tx("agent challenges itself", R, "challenge", 0, "structuring", "x", sender=AGENT, value=FLOOR * 10)
    tx("reflex rule", R, "challenge", 0, "per-spend", "x", sender=CHALLENGER, value=FLOOR * 10)
    tx("bond too low", R, "challenge", 0, "structuring", "x", sender=CHALLENGER, value=FLOOR - 1)
    tx("challenge A", R, "challenge", 0, "structuring", "half of one order", sender=CHALLENGER, value=out["quote"]["bond"])
    tx("challenge A twice", R, "challenge", 0, "structuring", "again", sender=GRIEFER, value=10 * FLOOR)
    wait(61)
    tx("pay 0 under challenge", R, "pay", 0, sender=VENDOR)
    tx("respond A", R, "respond", 0, SEPARATE_URL, hashlib.sha256(SEPARATE).hexdigest(), sender=AGENT)
    tx("rule A", R, "rule", 0, sender=VENDOR)
    tx("pay 0 after dismissal", R, "pay", 0, sender=VENDOR)

    # Spend 1 and 2 clear; 1 is challenged under the tier-3 rule and upheld
    # before the rail pays it: blocked, and 2 (unpaid) is revoked.
    tx("spend 1", G, "request_spend", OTHER, 40 * GEN, "travel", "", "", "flight", sender=AGENT)
    tx("spend 2", G, "request_spend", VENDOR, 30 * GEN, "media", "", "", "music", sender=AGENT)
    out["quote B"] = view(R, "bond_quote", 1, "purpose", CHALLENGER)
    tx("challenge B", R, "challenge", 1, "purpose", "BREACH: a flight is not media production", sender=CHALLENGER,
       value=out["quote B"]["bond"])
    tx("rule B early", R, "rule", 1, sender=CHALLENGER)
    wait(61)
    tx("rule B", R, "rule", 1, sender=CHALLENGER)
    tx("pay 1 upheld", R, "pay", 1, sender=OTHER)
    tx("pay 2 revoked", R, "pay", 2, sender=VENDOR)
    tx("spend while frozen", G, "request_spend", VENDOR, 10 * GEN, "media", "", "", "x", sender=AGENT)
    tx("agent lifts", R, "lift_freeze", sender=AGENT)
    tx("principal lifts", R, "lift_freeze", sender=PRINCIPAL)
    tx("spend 3", G, "request_spend", VENDOR, 20 * GEN, "media", "", "", "after lift", sender=AGENT)

    # Spend 0 was paid; a second challenge is upheld and clawed back from the bond.
    tx("challenge C", R, "challenge", 0, "purpose", "BREACH: not media", sender=GRIEFER,
       value=view(R, "bond_quote", 0, "purpose", GRIEFER)["bond"])
    wait(61)
    tx("rule C", R, "rule", 2, sender=GRIEFER)

    # A jury that cannot agree: the challenge lapses at the deadline.
    out["quote D"] = view(R, "bond_quote", 3, "structuring", CHALLENGER)
    tx("challenge D", R, "challenge", 3, "structuring", "SPLIT-JURY", sender=CHALLENGER, value=out["quote D"]["bond"])
    wait(61)
    tx("rule D", R, "rule", 3, sender=CHALLENGER)
    tx("lapse D early", R, "lapse", 3, sender=CHALLENGER)
    tx("withdraw bond while open", R, "withdraw_bond", 1, sender=AGENT)
    wait(3600)
    tx("lapse D", R, "lapse", 3, sender=CHALLENGER)

    tx("withdraw bond in window", R, "withdraw_bond", 1, sender=AGENT)
    tx("withdraw more than treasury", R, "withdraw", int(view(R, "status")["treasury"]) + 1, sender=PRINCIPAL)
    wait(WEEK + 1)
    tx("withdraw bond after window", R, "withdraw_bond", 1, sender=AGENT)

    # The guard's own jury: a tier-3 breach freezes the agent and revokes what
    # the rail has not paid.
    tx("lift court freeze", R, "lift_freeze", sender=PRINCIPAL)
    tx("spend 4", G, "request_spend", VENDOR, 20 * GEN, "media", "", "", "stock footage", sender=AGENT)
    tx("spend 5", G, "request_spend", OTHER, 190 * GEN, "media", "", "", "campaign", sender=AGENT)
    wait(61)
    tx("adjudicate 5", G, "adjudicate", 5, sender=PRINCIPAL)
    out["settlement 4"] = view(G, "settlement_of", 4)
    out["guard after breach"] = {k: v for k, v in view(G, "mandate_info").items() if k.startswith(("frozen", "revoked"))}
    tx("spend after breach", G, "request_spend", VENDOR, 5 * GEN, "media", "", "", "x", sender=AGENT)
    tx("pay 4 revoked by guard", R, "pay", 4, sender=VENDOR)
    tx("guard lift", G, "lift_freeze", sender=PRINCIPAL)
    tx("spend 6", G, "request_spend", VENDOR, 5 * GEN, "media", "", "", "after lift", sender=AGENT)

    # The registry: one agent, one principal's guard.
    deploy(rt, ns["guard"], "RemitGuard", G2, AGENT, MANDATE, 3, False, E, sender=INTRUDER)
    tx("steal agent", REG, "register", G2, "", sender=INTRUDER)

    out["challenges"] = view(R, "challenges")
    out["status"] = view(R, "status")
    out["payments"] = [view(R, "payment_of", i) for i in range(7)]
    out["docket"] = [(s["state"], s["authorization"]) for s in view(G, "docket")]
    out["guard"] = {k: v for k, v in view(G, "mandate_info").items() if k in ("frozen_tier", "rail", "revoked_below")}
    out["registry"] = view(REG, "guards")
    out["guard_of"] = view(REG, "guard_of", AGENT)
    out["transfers"] = list(rt.transfers)
    out["balances"] = dict(rt.balances)
    return out


@pytest.fixture(scope="module")
def readable():
    return scenario(".py")


@pytest.fixture(scope="module")
def deployed():
    return scenario(".min.py")


def test_deployed_bytes_behave_exactly_like_the_tested_build(readable, deployed):
    assert readable.keys() == deployed.keys()
    for key in readable:
        assert readable[key] == deployed[key], key


def test_binding(readable):
    r = readable
    assert "only the guard's principal may deploy its rail" in r["rail by intruder"]
    assert "only the principal may attach" in r["attach by agent"]
    assert r["attach"] == "ok" and "already attached" in r["attach twice"]
    assert r["guard"]["rail"] == R


def test_who_may_challenge_and_for_what_bond(readable):
    r = readable
    assert r["quote"] == {"error": "", "bond": 15 * GEN}  # 10% of 150, above the floor
    assert "cannot challenge its own" in r["agent challenges itself"]
    assert "judgment rules" in r["reflex rule"]
    assert "the bond for this challenge is" in r["bond too low"]
    assert r["challenge A"] == "ok"
    assert "already under challenge" in r["challenge A twice"]


def test_a_payout_waits_for_the_ruling_and_a_dismissal_releases_it(readable):
    r = readable
    assert "under challenge" in r["pay 0 under challenge"]
    a = r["challenges"][0]
    assert (a["state"], a["verdict"], a["artifact"]) == ("dismissed", "in_remit", "verified")
    assert r["pay 0 after dismissal"] == "ok"
    assert r["payments"][0]["paid"] and r["payments"][0]["amount"] == 150 * GEN
    # T1: the griefed agent is paid the forfeited bond.
    assert (R, AGENT, 15 * GEN) in r["transfers"]


def test_an_upheld_challenge_blocks_an_unpaid_payment_and_tier_three_revokes(readable):
    r = readable
    assert "response window has not elapsed" in r["rule B early"]
    b = r["challenges"][1]
    assert (b["state"], b["verdict"], b["tier"]) == ("upheld", "out_of_remit", 3)
    assert b["settlement"]["blocked"] and b["settlement"]["to_treasury"] == 0
    # The challenger lost A, so B's bond doubled (BondPolicy); a win resets it.
    assert r["quote B"]["bond"] == 2 * FLOOR and r["quote D"]["bond"] == FLOOR
    assert (R, CHALLENGER, 2 * FLOOR + 2 * GEN) in r["transfers"]  # bond + 5% of 40
    assert "clawed this spend back" in r["pay 1 upheld"]
    assert "revoked by a tier-3 ruling" in r["pay 2 revoked"]
    assert r["payments"][2]["revoked"] and not r["payments"][2]["paid"]
    # Spend 3 was authorized after the lift, still unpaid when challenge C (also
    # tier 3) was upheld - so C revoked it in turn.
    assert r["payments"][3]["revoked"]
    assert "frozen at tier 3" in r["spend while frozen"]
    assert "only the principal" in r["agent lifts"]
    assert r["principal lifts"] == "ok" and r["spend 3"] == "ok"


def test_an_upheld_challenge_on_a_paid_payment_claws_back_from_the_bond(readable):
    r = readable
    c = r["challenges"][2]
    assert c["state"] == "upheld" and not c["settlement"]["blocked"]
    # 300 bond - 2 reward (B) = 298 standing: 150 back to the treasury, then
    # 5% of 150 to the challenger from what is left.
    assert c["settlement"]["to_treasury"] == 150 * GEN
    assert c["settlement"]["to_challenger"] == 15 * GEN + int(7.5 * GEN)
    assert (R, GRIEFER, 15 * GEN + int(7.5 * GEN)) in r["transfers"]


def test_an_undecidable_challenge_lapses_with_its_bond_returned(readable):
    r = readable
    assert "validators disagreed" in r["rule D"]
    assert "deadline not reached" in r["lapse D early"]
    d = r["challenges"][3]
    assert d["state"] == "lapsed"
    assert (R, CHALLENGER, FLOOR) in r["transfers"]


def test_bonds_and_treasury_are_separate(readable):
    r = readable
    s = r["status"]
    assert "a challenge is open" in r["withdraw bond while open"]
    assert "clawback window" in r["withdraw bond in window"]
    assert "invalid withdrawal amount" in r["withdraw more than treasury"]
    assert r["withdraw bond after window"] == "ok"
    assert s["escrowed"] == 0 and s["open_challenges"] == 0
    # treasury: 1000 funded - 150 paid + 150 clawed back
    assert s["treasury"] == 1000 * GEN
    # standing: 300 - 2 (B reward) - 157.5 (C clawback + reward) - 1 withdrawn
    assert s["standing"] == 300 * GEN - 2 * GEN - 150 * GEN - int(7.5 * GEN) - 1
    # Everything the rail holds is accounted for by its ledgers.
    assert r["balances"][R] == s["treasury"] + s["standing"] + s["escrowed"]


def test_the_registry_binds_an_agent_to_one_principals_guard(readable):
    r = readable
    assert "only the guard's principal may register it" in r["register by intruder"]
    assert r["register"] == "ok"
    assert "bound to another principal's guard" in r["steal agent"]
    assert r["guard_of"] == G
    assert [(g["guard"], g["rail"], g["active"]) for g in r["registry"]] == [(G, R, True)]


def test_the_guards_own_tier_three_breach_freezes_and_revokes(readable):
    r = readable
    assert r["adjudicate 5"] == "ok"
    assert r["docket"][5] == ("refused", "refused")
    assert r["guard after breach"]["frozen_tier"] == 3 and r["guard after breach"]["frozen_by"] == 5
    assert r["settlement 4"]["authorization"] == "revoked"
    assert r["docket"][4] == ("settled", "revoked")
    assert "frozen at tier 3" in r["spend after breach"]
    assert "spend is revoked" in r["pay 4 revoked by guard"]
    # Lifting restores spending; the revocation stands.
    assert r["guard lift"] == "ok" and r["spend 6"] == "ok"
    assert r["docket"][6] == ("settled", "authorized")
