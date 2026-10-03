"""Challenges, clawback and graduated authority (T1, T7).

A payment that cleared without a jury stays open to a bonded challenge for the
mandate's clawback window. These tests fix who may challenge what, how the
jury's agreement rule runs in the challenge direction, who is paid what when a
challenge is decided, and what a breach at tier 2 and 3 does to the agent.
"""

import itertools

import pytest
from conftest import AGENT, CHALLENGER, T0

import remit_core as core

IN, OUT, UND = core.VERDICT_IN_REMIT, core.VERDICT_OUT_OF_REMIT, core.VERDICT_UNDETERMINED
WEEK = 604800
JUDGMENT = {"id": "structuring", "type": core.RULE_JUDGMENT}
REFLEX = {"id": "per-spend", "type": core.RULE_REFLEX}


def cleared(**over):
    s = {"authorization": "authorized", "verdict": "", "reason": "", "decided_at": T0, "amount": 1000}
    s.update(over)
    return s


def error(spend=None, rule=JUDGMENT, challenger=CHALLENGER, now=T0 + 60):
    return core.challenge_error(
        spend=spend or cleared(), rule=rule, challenger=challenger, agent=AGENT, now=now,
        clawback_window_seconds=WEEK,
    )


# --- who may challenge what -------------------------------------------------


def test_a_payment_that_cleared_without_a_jury_is_challengeable():
    assert error() == ""


def test_only_authorized_payments_are_challengeable():
    assert "only an authorized" in error(cleared(authorization="refused"))
    assert "only an authorized" in error(cleared(authorization="pending"))
    assert "only an authorized" in error(cleared(authorization="revoked"))


def test_a_jury_or_principal_decision_is_not_rechallenged():
    """A jury's verdict is reviewed by GenLayer's appeal; an override is the
    principal's own call."""
    assert "appeal" in error(cleared(verdict=IN, reason="matches_rule"))
    assert "appeal" in error(cleared(reason="principal_override"))


def test_a_challenge_names_a_judgment_rule():
    """Reflex rules are arithmetic and already decided exactly."""
    assert "judgment rules" in error(rule=REFLEX)
    assert "judgment rules" in error(rule=None)


def test_the_agent_cannot_challenge_itself():
    assert "cannot challenge its own" in error(challenger=AGENT)


def test_the_clawback_window_closes():
    assert error(now=T0 + WEEK) == ""
    assert "window" in error(now=T0 + WEEK + 1)
    assert "window" in error(cleared(decided_at=0))


# --- the jury, in the challenge direction ------------------------------------


def test_a_hesitant_breach_is_not_a_breach():
    assert core.harden_challenge(OUT, 59) == UND
    assert core.harden_challenge(OUT, 60) == OUT
    assert core.harden_challenge(IN, 10) == IN
    with pytest.raises(core.RemitError):
        core.harden_challenge("maybe", 90)


@pytest.mark.parametrize("leader,own", list(itertools.product((IN, OUT, UND), repeat=2)))
def test_challenge_agreement_table(leader, own):
    """Upholding needs agreement; a validator sure of the breach vetoes a
    dismissal; two dismissing readings agree."""
    expected = {
        (IN, IN): True, (IN, OUT): False, (IN, UND): True,
        (OUT, IN): False, (OUT, OUT): True, (OUT, UND): False,
        (UND, IN): True, (UND, OUT): False, (UND, UND): True,
    }[(leader, own)]
    assert core.challenge_agrees(leader_verdict=leader, own_verdict=own) is expected


def test_one_confident_uphold_over_unsure_validators_does_not_stand():
    assert not core.challenge_agrees(leader_verdict=OUT, own_verdict=UND)


# --- who is paid what --------------------------------------------------------


def resolve(verdict, *, paid, standing, bond=200, amount=1000):
    return core.resolve_challenge(
        verdict=verdict, bond=bond, amount=amount, paid=paid, standing=standing, policy=core.BondPolicy()
    )


@pytest.mark.parametrize("verdict", [IN, UND])
def test_a_dismissed_challenge_pays_its_bond_to_the_agent(verdict):
    r = resolve(verdict, paid=True, standing=5000)
    assert r["state"] == core.CHALLENGE_DISMISSED
    assert r["to_agent"] == 200 and r["to_challenger"] == 0
    assert r["to_treasury"] == 0 and r["from_standing"] == 0 and not r["blocked"]


def test_an_upheld_challenge_on_an_unpaid_payment_blocks_it():
    """Caught before the rail paid: the money never leaves the treasury, so
    nothing is taken from the bond except the reward."""
    r = resolve(OUT, paid=False, standing=5000)
    assert r["state"] == core.CHALLENGE_UPHELD and r["blocked"]
    assert r["to_treasury"] == 0
    assert r["to_challenger"] == 200 + 50  # bond back + 5% of 1000
    assert r["from_standing"] == 50


def test_an_upheld_challenge_on_a_paid_payment_claws_back_from_the_bond():
    r = resolve(OUT, paid=True, standing=5000)
    assert not r["blocked"]
    assert r["to_treasury"] == 1000
    assert r["to_challenger"] == 250
    assert r["from_standing"] == 1050


def test_the_principal_is_made_whole_before_the_challenger_is_rewarded():
    r = resolve(OUT, paid=True, standing=1020)
    assert r["to_treasury"] == 1000
    assert r["to_challenger"] == 200 + 20  # only what is left of the bond
    r = resolve(OUT, paid=True, standing=600)
    assert r["to_treasury"] == 600 and r["to_challenger"] == 200 and r["from_standing"] == 600


def test_resolution_never_pays_more_than_bond_plus_standing():
    for verdict, paid, standing in itertools.product((IN, OUT, UND), (True, False), (0, 30, 600, 5000)):
        r = resolve(verdict, paid=paid, standing=standing)
        assert r["from_standing"] <= standing
        assert r["to_challenger"] + r["to_agent"] + r["to_treasury"] == 200 + r["from_standing"]


def test_a_win_clears_the_streak_and_a_loss_extends_it():
    assert core.record_challenge_result(losses=3, upheld=True, now=T0) == (0, 0)
    assert core.record_challenge_result(losses=3, upheld=False, now=T0) == (4, T0)
    first = core.challenge_bond(amount=1000, losses=0, last_loss_at=0, now=T0, policy=core.BondPolicy())
    losses, last = core.record_challenge_result(losses=0, upheld=False, now=T0)
    second = core.challenge_bond(amount=1000, losses=losses, last_loss_at=last, now=T0 + 1, policy=core.BondPolicy())
    assert second == 2 * first


# --- graduated authority ------------------------------------------------------


def test_tiers_one_and_below_freeze_nothing():
    assert core.freeze_tier(tier=0, shadow=False) == 0
    assert core.freeze_tier(tier=1, shadow=False) == 0


def test_tier_two_freezes_and_tier_three_revokes():
    assert core.freeze_tier(tier=2, shadow=False) == core.TIER_FREEZE
    assert core.freeze_tier(tier=3, shadow=False) == core.TIER_REVOKE


def test_shadow_mode_freezes_nothing():
    assert core.freeze_tier(tier=3, shadow=True) == 0


def test_revocation_reaches_back_but_not_forward():
    assert not core.is_revoked(spend_id=0, revoked_below=0)
    assert core.is_revoked(spend_id=0, revoked_below=5)
    assert core.is_revoked(spend_id=4, revoked_below=5)
    assert not core.is_revoked(spend_id=5, revoked_below=5)
