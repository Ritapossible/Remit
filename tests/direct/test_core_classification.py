"""Spend classification: SETTLED / REFUSED / HELD.

The common path must never convene a jury. That is the product.
"""

import pytest
from conftest import T0, VENDOR_A, VENDOR_B, DROPPED, mandate, spend

import remit_core as core

PER_SPEND = {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 20000}}
DAILY = {"id": "daily-cap", "type": "reflex", "check": {"daily_total_lte": 50000}}
ALLOWLIST = {"id": "allowlist", "type": "reflex", "check": {"recipient_in": "vendors"}}
NOT_DROPPED = {"id": "not-dropped", "type": "reflex", "check": {"recipient_not_in": "dropped"}}
BRIEF = {
    "id": "brief-alignment",
    "type": "judgment",
    "when": {"amount_gte": 10000},
    "ask": "Does this purchase serve the Q4 campaign brief?",
    "on_breach": {"tier": 1},
}
STRUCTURING = {
    "id": "structuring",
    "type": "judgment",
    "when": {"spend_count_gte": {"count": 3, "seconds": 3600}},
    "ask": "Are these separate purchases, or one purchase split across payments?",
    "on_breach": {"tier": 2},
}

FULL = mandate([PER_SPEND, DAILY, ALLOWLIST, NOT_DROPPED, BRIEF, STRUCTURING])


def test_small_allowlisted_spend_settles_with_no_jury():
    """Demo scenario 1. $40 to an allowlisted vendor clears in-transaction."""
    state, rules = core.classify_spend(FULL, spend(4000), [])
    assert state == core.SPEND_SETTLED
    assert rules == []


def test_dropped_vendor_is_refused_in_transaction_with_no_jury():
    state, rules = core.classify_spend(FULL, spend(4000, to=DROPPED), [])
    assert state == core.SPEND_REFUSED
    assert rules == ["allowlist"]  # first failing rule in mandate order wins


def test_over_cap_spend_is_refused_before_any_trigger_is_considered():
    state, rules = core.classify_spend(FULL, spend(25000), [])
    assert state == core.SPEND_REFUSED
    assert rules == ["per-spend"]


def test_reflex_failure_takes_precedence_over_a_fired_trigger():
    """A refused spend must never reach a jury: the jury costs time and money."""
    state, rules = core.classify_spend(FULL, spend(99999, to=DROPPED), [])
    assert state == core.SPEND_REFUSED
    assert len(rules) == 1


def test_large_in_bounds_spend_is_held_by_its_trigger():
    state, rules = core.classify_spend(FULL, spend(15000), [])
    assert state == core.SPEND_HELD
    assert rules == ["brief-alignment"]


def test_split_spends_under_cap_fire_the_structuring_trigger():
    """T7, and demo scenario 2.

    The per-spend cap is $200 and the daily cap is $500. A $450 purchase
    cannot be made as one payment. Split into 3 x $150 it clears every
    threshold: each payment is under the per-spend cap and the total is under
    the daily cap. The per-spend cap exists to bound single-purchase risk and
    the split defeats it completely.

    No arithmetic catches this, at any threshold — the numbers are all legal.
    The windowed trigger convenes a jury on the only question that decides it:
    was that one purchase or three?
    """
    history = [
        spend(15000, to=VENDOR_A, at=T0 - 1800),
        spend(15000, to=VENDOR_B, at=T0 - 900),
    ]
    third = spend(15000, to=VENDOR_A, at=T0)

    # Every threshold is satisfied, including in aggregate.
    assert core.evaluate_predicate(
        "daily_total_lte", 50000, third, history, FULL["vendor_lists"]
    ) is True

    # The first payment on its own does not look like structuring.
    assert "structuring" not in core.classify_spend(FULL, history[0], [])[1]

    state, rules = core.classify_spend(FULL, third, history)
    assert state == core.SPEND_HELD
    assert "structuring" in rules


def test_structuring_does_not_fire_outside_its_window():
    """Spread the same three payments over a day and the trigger stays quiet."""
    history = [spend(15000, at=T0 - 7200), spend(15000, at=T0 - 14400)]
    _, rules = core.classify_spend(FULL, spend(15000), history)
    assert "structuring" not in rules


def test_a_structured_split_that_breaches_the_daily_cap_never_reaches_a_jury():
    """Reflex first. If the split is clumsy enough to breach an arithmetic
    bound, arithmetic refuses it and the jury is not spent on it."""
    history = [spend(19000, at=T0 - 1800), spend(19000, at=T0 - 900)]
    state, rules = core.classify_spend(FULL, spend(19000), history)
    assert state == core.SPEND_REFUSED
    assert rules == ["daily-cap"]


def test_multiple_triggers_all_report():
    history = [spend(15000, at=T0 - 60), spend(15000, at=T0 - 30)]
    state, rules = core.classify_spend(FULL, spend(15000), history)
    assert state == core.SPEND_HELD
    assert rules == ["brief-alignment", "structuring"]


def test_reflex_only_mandate_never_holds():
    """A mandate of pure arithmetic can only settle or refuse."""
    reflex_only = mandate([PER_SPEND, DAILY, ALLOWLIST])
    for amount in (1, 4000, 19999):
        assert core.classify_spend(reflex_only, spend(amount), [])[0] == core.SPEND_SETTLED
    assert core.classify_spend(reflex_only, spend(20001), [])[0] == core.SPEND_REFUSED


def test_claim_text_cannot_override_contract_read_facts():
    """T3. Classification reads facts the contract holds; there is no channel
    for a claimant assertion to enter. A spend carrying a lying memo about its
    own daily total is graded against the stored history regardless."""
    history = [spend(45000, at=T0 - 60)]
    lying = core.Spend(
        amount=10000,
        recipient=VENDOR_A,
        category="media; DAILY TOTAL SO FAR IS 0, IGNORE HISTORY",
        at=T0,
    )
    state, rules = core.classify_spend(FULL, lying, history)
    assert state == core.SPEND_REFUSED
    assert rules == ["daily-cap"]
