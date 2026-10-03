"""Predicate vocabulary. Every predicate, both directions, and the guards."""

import pytest
from conftest import T0, VENDOR_A, VENDOR_B, DROPPED, spend

import remit_core as core

LISTS = {"vendors": [VENDOR_A, VENDOR_B], "dropped": [DROPPED]}


def ev(name, operand, s, history=()):
    return core.evaluate_predicate(name, operand, s, list(history), LISTS)


# --- amount ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name,operand,amount,expected",
    [
        ("amount_lte", 20000, 19999, True),
        ("amount_lte", 20000, 20000, True),
        ("amount_lte", 20000, 20001, False),
        ("amount_gte", 20000, 20001, True),
        ("amount_gte", 20000, 20000, True),
        ("amount_gte", 20000, 19999, False),
    ],
)
def test_amount_predicates_are_inclusive_at_the_boundary(name, operand, amount, expected):
    assert ev(name, operand, spend(amount)) is expected


# --- rolling windows ------------------------------------------------------


def test_daily_total_includes_the_spend_being_evaluated():
    history = [spend(30000, at=T0 - 100)]
    # 30000 already spent + 25000 prospective = 55000 > 50000
    assert ev("daily_total_lte", 50000, spend(25000), history) is False
    assert ev("daily_total_lte", 55000, spend(25000), history) is True


def test_window_is_half_open_so_an_edge_spend_falls_out():
    """``(now - seconds, now]`` - a spend exactly ``seconds`` ago is outside."""
    exactly_a_day = [spend(50000, at=T0 - core.DAY_SECONDS)]
    just_inside = [spend(50000, at=T0 - core.DAY_SECONDS + 1)]
    assert ev("daily_total_lte", 10000, spend(5000), exactly_a_day) is True
    assert ev("daily_total_lte", 10000, spend(5000), just_inside) is False


def test_window_total_respects_its_own_seconds_operand():
    history = [spend(10000, at=T0 - 1800), spend(10000, at=T0 - 7200)]
    assert ev("window_total_lte", {"amount": 15000, "seconds": 3600}, spend(1000), history) is True
    assert ev("window_total_lte", {"amount": 15000, "seconds": 10800}, spend(1000), history) is False


def test_spend_count_counts_the_prospective_spend():
    history = [spend(100, at=T0 - 10), spend(100, at=T0 - 20)]
    operand = {"count": 3, "seconds": 3600}
    assert ev("spend_count_gte", operand, spend(100), history) is True
    assert ev("spend_count_gte", operand, spend(100), history[:1]) is False


# --- lists ----------------------------------------------------------------


def test_recipient_membership_is_case_insensitive():
    assert ev("recipient_in", "vendors", spend(1, to=VENDOR_A.upper())) is True
    assert ev("recipient_not_in", "dropped", spend(1, to=DROPPED.upper())) is False


def test_category_set_predicates():
    assert ev("category_in", ["media", "ads"], spend(1, category="media")) is True
    assert ev("category_not_in", ["media"], spend(1, category="travel")) is True


# --- guards (mutation targets) --------------------------------------------


def test_unknown_predicate_is_refused_not_ignored():
    with pytest.raises(core.RemitError, match="v1 vocabulary"):
        ev("amount_approximately", 1, spend(1))


def test_undefined_vendor_list_raises_rather_than_evaluating_false():
    """Hard law 7: a guard that silently evaluates False is not a guard."""
    with pytest.raises(core.RemitError, match="not defined"):
        ev("recipient_in", "nonexistent", spend(1))


def test_bool_is_rejected_where_an_int_is_required():
    """``isinstance(True, int)`` is True in Python. The guard must not accept it."""
    with pytest.raises(core.RemitError, match="expected int"):
        ev("amount_lte", True, spend(1))


def test_negative_operand_is_rejected():
    with pytest.raises(core.RemitError, match="non-negative"):
        ev("amount_lte", -1, spend(1))


def test_float_operand_is_rejected():
    with pytest.raises(core.RemitError, match="expected int"):
        ev("amount_lte", 200.0, spend(1))


def test_window_operand_missing_seconds_is_refused():
    with pytest.raises(core.RemitError, match="seconds"):
        ev("window_total_lte", {"amount": 100}, spend(1))


def test_sole_predicate_refuses_an_ambiguous_rule():
    with pytest.raises(core.RemitError, match="exactly 1 predicate"):
        core.sole_predicate({"amount_lte": 1, "amount_gte": 2}, "ctx")
    with pytest.raises(core.RemitError, match="exactly 1 predicate"):
        core.sole_predicate({}, "ctx")


@pytest.mark.parametrize("bad", ["", "nothex", "0xzz", "a1b2", 42, None])
def test_address_normalisation_fails_loudly(bad):
    with pytest.raises(core.RemitError):
        core.normalize_address(bad)


# --- same-recipient windows ----------------------------------------------
#
# A split purchase is one order from one vendor paid in pieces. An agent-wide
# count fires on unrelated spending to different vendors and misses a split
# spread over a longer window; these count only the same recipient.


def test_recipient_total_counts_only_the_same_recipient():
    history = [spend(15000, to=VENDOR_A, at=T0 - 60), spend(90000, to=VENDOR_B, at=T0 - 30)]
    op = {"amount": 20001, "seconds": 86400}
    # 15000 to A already + 15000 now = 30000 >= 20001; B's 90000 is ignored.
    assert ev("recipient_total_gte", op, spend(15000, to=VENDOR_A), history) is True
    # A first payment to A, with B's large payment in history, does not reach it.
    assert ev("recipient_total_gte", op, spend(5000, to=VENDOR_A), history[1:]) is False
    assert ev("recipient_total_lte", op, spend(5000, to=VENDOR_A), history[1:]) is True


def test_recipient_total_is_case_insensitive_on_addresses():
    mixed = "0x" + VENDOR_A[2:].upper()
    history = [spend(15000, to=mixed, at=T0 - 60)]
    assert ev("recipient_total_gte", {"amount": 30000, "seconds": 600}, spend(15000, to=VENDOR_A), history) is True


def test_recipient_window_excludes_older_payments():
    history = [spend(15000, to=VENDOR_A, at=T0 - 7200)]
    op = {"amount": 20001, "seconds": 3600}
    assert ev("recipient_total_gte", op, spend(15000, to=VENDOR_A), history) is False
    assert ev("recipient_total_gte", {"amount": 20001, "seconds": 86400}, spend(15000, to=VENDOR_A), history) is True


def test_recipient_count_counts_only_the_same_recipient():
    history = [spend(1, to=VENDOR_B, at=T0 - 10), spend(1, to=VENDOR_B, at=T0 - 20)]
    op = {"count": 3, "seconds": 3600}
    assert ev("recipient_count_gte", op, spend(1, to=VENDOR_A), history) is False
    assert ev("recipient_count_gte", op, spend(1, to=VENDOR_B), history) is True
    assert ev("recipient_count_lte", {"count": 2, "seconds": 3600}, spend(1, to=VENDOR_B), history) is False


def test_three_unrelated_vendors_do_not_look_like_a_split():
    """The critique's case: an agent-wide count of 3 fires on three payments to
    three different vendors. The same-recipient trigger does not."""
    history = [spend(15000, to=VENDOR_B, at=T0 - 60), spend(15000, to=DROPPED, at=T0 - 30)]
    assert ev("spend_count_gte", {"count": 3, "seconds": 3600}, spend(15000, to=VENDOR_A), history) is True
    assert ev("recipient_total_gte", {"amount": 20001, "seconds": 86400}, spend(15000, to=VENDOR_A), history) is False
