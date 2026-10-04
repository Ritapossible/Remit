"""A split is one purchase: the first slice waits for, and falls with, the
ruling on the slice that tripped the structuring trigger (``split_hold``)."""

import pytest

import remit_core as core

V = "0x00000000000000000000000000000000000000a1"
W = "0x00000000000000000000000000000000000000a2"
DAY = 86400
RULES = [
    {"id": "per-spend", "type": "reflex", "predicate": "amount_lte", "a": 200, "b": 0},
    {"id": "structuring", "type": "judgment", "predicate": "recipient_total_gte", "a": 201, "b": DAY},
    {"id": "large", "type": "judgment", "predicate": "amount_gte", "a": 180, "b": 0},
]


def spend(i, at, *, to=V, state="settled", rules=(), outcome="allowed"):
    return {"id": i, "recipient": to, "at": at, "state": state, "rules": list(rules), "outcome": outcome}


FIRST = spend(0, 1000)


def test_only_judgment_rules_on_one_vendor_are_split_rules():
    assert core.split_windows(RULES) == {"structuring": DAY}


def test_a_first_slice_waits_while_the_later_slice_is_held():
    held = spend(1, 1500, state="held", rules=["structuring"], outcome="")
    assert core.split_hold(FIRST, [held], RULES) == core.SPLIT_PENDING


def test_a_first_slice_falls_with_a_split_ruled_one_purchase():
    refused = spend(1, 1500, state="refused", rules=["structuring"], outcome="refused")
    assert core.split_hold(FIRST, [refused], RULES) == core.SPLIT_REFUSED


def test_a_first_slice_pays_when_the_later_slice_was_allowed():
    allowed = spend(1, 1500, state="settled", rules=["structuring"], outcome="allowed")
    assert core.split_hold(FIRST, [allowed], RULES) == ""


def test_a_refusal_that_involved_another_rule_is_not_a_ruling_on_the_split():
    mixed = spend(1, 1500, state="refused", rules=["structuring", "large"], outcome="refused")
    assert core.split_hold(FIRST, [mixed], RULES) == ""
    # ...but while it is held, the first slice still waits.
    held = spend(1, 1500, state="held", rules=["structuring", "large"], outcome="")
    assert core.split_hold(FIRST, [held], RULES) == core.SPLIT_PENDING


@pytest.mark.parametrize(
    "other",
    [
        spend(1, 1500, to=W, state="held", rules=["structuring"], outcome=""),  # another vendor
        spend(1, 1000 + DAY, state="held", rules=["structuring"], outcome=""),  # outside the window
        spend(1, 1500, state="held", rules=["large"], outcome=""),  # not a split rule
        spend(0, 1500, state="held", rules=["structuring"], outcome=""),  # not later
    ],
)
def test_unrelated_payments_do_not_hold_a_slice(other):
    assert core.split_hold(FIRST, [other], RULES) == ""


def test_the_window_is_half_open_like_classification():
    inside = spend(1, 1000 + DAY - 1, state="held", rules=["structuring"], outcome="")
    assert core.split_hold(FIRST, [inside], RULES) == core.SPLIT_PENDING


def test_a_refused_split_outranks_one_still_held_and_case_does_not_split_a_vendor():
    held = spend(1, 1200, to=V.upper().replace("0X", "0x"), state="held", rules=["structuring"], outcome="")
    refused = spend(2, 1300, state="refused", rules=["structuring"], outcome="refused")
    assert core.split_hold(FIRST, [held, refused], RULES) == core.SPLIT_REFUSED
    assert core.split_hold(FIRST, [held], RULES) == core.SPLIT_PENDING
