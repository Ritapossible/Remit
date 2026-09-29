"""Bond economics (T1, T2).

These tests fix the numbers that ARCHITECTURE.md open questions 1 and 2 left
open. Changing a constant in BondPolicy without changing these tests is a
silent change to the product's incentive structure.
"""

import pytest
from conftest import AGENT, CHALLENGER, T0

import remit_core as core

WEEK = 604800


def bond(amount, losses=0, last_loss_at=0, now=T0, policy=None):
    return core.challenge_bond(
        amount=amount,
        losses=losses,
        last_loss_at=last_loss_at,
        now=now,
        policy=policy or core.BondPolicy(),
    )


# --- denomination: fraction with a floor (open question 1) ----------------


def test_small_spends_pay_the_floor():
    """A pure fraction would make a small spend uneconomic to challenge."""
    assert bond(1000) == 500  # 10% of $10 is $1, floor is $5
    assert bond(0) == 500


def test_large_spends_pay_the_fraction():
    """A flat bond would make a large spend cheap to grief."""
    assert bond(100000) == 10000  # 10% of $1000
    assert bond(1000000) == 100000


def test_the_crossover_is_where_the_fraction_overtakes_the_floor():
    assert bond(5000) == 500  # exactly at the crossover
    assert bond(5001) == 500  # integer division, still the floor
    assert bond(6000) == 600


# --- escalation (T1) ------------------------------------------------------


def test_repeat_false_challenger_bond_escalates():
    """T1. Five consecutive losses, each bond strictly above the last.

    A flat-bond implementation fails this test, which is the point of it.
    """
    amounts = [bond(100000, losses=n, last_loss_at=T0, now=T0) for n in range(5)]
    assert amounts == [10000, 20000, 40000, 80000, 160000]
    for earlier, later in zip(amounts, amounts[1:]):
        assert later > earlier
    assert amounts[4] == amounts[0] * 16


def test_escalation_is_capped_so_the_number_stays_a_number():
    capped = bond(100000, losses=99, last_loss_at=T0, now=T0)
    assert capped == 10000 * core.BondPolicy().max_multiplier


def test_an_honest_challenger_always_pays_the_base():
    assert bond(100000, losses=0) == 10000


# --- decay (open question 2) ----------------------------------------------


def test_one_loss_is_forgiven_per_week():
    args = {"losses": 4, "last_loss_at": T0, "policy": core.BondPolicy()}
    assert core.effective_losses(now=T0, **args) == 4
    assert core.effective_losses(now=T0 + WEEK - 1, **args) == 4
    assert core.effective_losses(now=T0 + WEEK, **args) == 3
    assert core.effective_losses(now=T0 + 2 * WEEK, **args) == 2
    assert core.effective_losses(now=T0 + 4 * WEEK, **args) == 0


def test_decay_never_goes_negative():
    assert (
        core.effective_losses(
            losses=1, last_loss_at=T0, now=T0 + 100 * WEEK, policy=core.BondPolicy()
        )
        == 0
    )


def test_a_griefer_pays_to_keep_grinding():
    """Waiting out one escalation step costs a week of inactivity. Grinding
    through it costs double each time. Both are priced; neither is free."""
    immediate = bond(100000, losses=3, last_loss_at=T0, now=T0)
    after_a_week = bond(100000, losses=3, last_loss_at=T0, now=T0 + WEEK)
    assert immediate == 80000
    assert after_a_week == 40000


def test_clock_running_backwards_raises():
    with pytest.raises(core.RemitError, match="precedes"):
        core.effective_losses(losses=1, last_loss_at=T0, now=T0 - 1, policy=core.BondPolicy())


# --- appeals (T2) ---------------------------------------------------------


def test_appeal_bond_exceeds_challenge_bond():
    """T2. An appeal must cost strictly more than the challenge it contests."""
    policy = core.BondPolicy()
    for challenge in (500, 10000, 160000):
        assert core.appeal_bond(challenge_bond_amount=challenge, policy=policy) > challenge


def test_an_appeal_multiplier_below_two_is_refused():
    with pytest.raises(core.RemitError, match="appeal_multiplier"):
        core.appeal_bond(
            challenge_bond_amount=1000, policy=core.BondPolicy(appeal_multiplier=1)
        )


def test_an_escalation_factor_below_two_is_refused():
    with pytest.raises(core.RemitError, match="escalation_factor"):
        bond(100000, losses=1, last_loss_at=T0, policy=core.BondPolicy(escalation_factor=1))


# --- rewards and settlement (T1) ------------------------------------------


def test_reward_is_a_fraction_of_the_refused_spend():
    policy = core.BondPolicy()
    assert core.challenge_reward(refused_amount=100000, agent_standing=999999, policy=policy) == 5000


def test_reward_is_capped_by_the_agents_standing_bond():
    """Paying more than the agent posted would make the reward a claim on
    somebody who never agreed to it."""
    policy = core.BondPolicy()
    assert core.challenge_reward(refused_amount=100000, agent_standing=1200, policy=policy) == 1200
    assert core.challenge_reward(refused_amount=100000, agent_standing=0, policy=policy) == 0


def test_a_dismissed_challenge_compensates_the_agent_not_the_protocol():
    """T1. The griefed party is the party paid."""
    credits, debit = core.settle_challenge(
        bond=20000, refused_amount=0, upheld=False,
        agent=AGENT, challenger=CHALLENGER, agent_standing=50000, policy=core.BondPolicy(),
    )
    assert credits == {AGENT: 20000}
    assert debit == 0


def test_an_upheld_challenge_returns_the_bond_and_pays_a_reward():
    credits, debit = core.settle_challenge(
        bond=10000, refused_amount=100000, upheld=True,
        agent=AGENT, challenger=CHALLENGER, agent_standing=50000, policy=core.BondPolicy(),
    )
    assert credits == {CHALLENGER: 15000}
    assert debit == 5000
    assert sum(credits.values()) == 10000 + debit  # conservation


def test_challenge_settlement_refuses_a_self_challenge():
    with pytest.raises(core.RemitError, match="must differ"):
        core.settle_challenge(
            bond=1000, refused_amount=0, upheld=False,
            agent=AGENT, challenger=AGENT, agent_standing=0, policy=core.BondPolicy(),
        )
