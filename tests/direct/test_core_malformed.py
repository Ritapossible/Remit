"""Malformed input.

A validator that only handles well-formed mandates is a validator that fails
open. Every one of these arrives from outside and must be refused by name, not
by exception trace and not by a falsy default.
"""

import pytest
from conftest import T0, VENDOR_A, mandate, spend

import remit_core as core

LISTS = {"vendors": [VENDOR_A]}
REFLEX = {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 20000}}
JUDGMENT = {
    "id": "brief",
    "type": "judgment",
    "when": {"amount_gte": 10000},
    "ask": "Does this serve the brief?",
    "on_breach": {"tier": 1},
}


def errors(m, *, stored_version=0, max_tier=3):
    return core.validate_mandate(m, stored_version=stored_version, max_tier=max_tier)


# --- predicate operands ---------------------------------------------------


def test_daily_total_gte_is_evaluated():
    history = [spend(30000, at=T0 - 100)]
    assert core.evaluate_predicate("daily_total_gte", 40000, spend(15000), history, LISTS) is True
    assert core.evaluate_predicate("daily_total_gte", 50000, spend(15000), history, LISTS) is False


def test_a_scalar_where_a_window_object_belongs_is_refused():
    with pytest.raises(core.RemitError, match="object operand"):
        core.evaluate_predicate("window_total_lte", 100, spend(1), [], LISTS)


def test_a_scalar_where_a_category_list_belongs_is_refused():
    with pytest.raises(core.RemitError, match="list operand"):
        core.evaluate_predicate("category_in", "media", spend(1), [], LISTS)


def test_a_non_object_check_is_refused():
    with pytest.raises(core.RemitError, match="expected an object"):
        core.sole_predicate("amount_lte", "ctx")


# --- appeal bond edge -----------------------------------------------------


def test_a_zero_challenge_bond_cannot_produce_a_greater_appeal_bond():
    """The guard is not decoration: at zero the multiplier cannot separate
    them, and the function refuses rather than returning an equal bond."""
    with pytest.raises(core.RemitError, match="does not exceed"):
        core.appeal_bond(challenge_bond_amount=0, policy=core.BondPolicy())


# --- mandate shape --------------------------------------------------------


@pytest.mark.parametrize("not_an_object", [None, [], "mandate", 7])
def test_a_mandate_that_is_not_an_object_is_refused(not_an_object):
    assert errors(not_an_object) == ["mandate: expected an object"]


def test_defaults_that_are_not_an_object_are_refused():
    m = mandate([REFLEX])
    m["defaults"] = "none"
    found = errors(m)
    assert any("defaults: expected an object" in e for e in found)
    assert any("missing" in e for e in found)


def test_a_non_integer_window_default_is_refused():
    m = mandate([REFLEX])
    m["defaults"]["response_window_seconds"] = "900"
    assert any("response_window_seconds" in e for e in errors(m))


def test_a_non_integer_deadline_does_not_crash_the_ordering_check():
    m = mandate([REFLEX])
    m["defaults"]["hold_deadline_seconds"] = None
    found = errors(m)
    assert any("hold_deadline_seconds" in e for e in found)


def test_vendor_lists_that_are_not_an_object_are_refused():
    m = mandate([REFLEX])
    m["vendor_lists"] = ["0xabc"]
    assert any("vendor_lists: expected an object" in e for e in errors(m))


def test_a_vendor_list_that_is_not_a_list_is_refused():
    m = mandate([REFLEX], lists={"vendors": "0xabc"})
    assert any("expected a list" in e for e in errors(m))


def test_rules_that_are_not_a_list_are_refused():
    m = mandate([REFLEX])
    m["rules"] = {"per-spend": REFLEX}
    assert any("rules: expected a list" in e for e in errors(m))


def test_a_rule_that_is_not_an_object_is_refused():
    assert any("expected an object" in e for e in errors(mandate(["per-spend"])))


@pytest.mark.parametrize("bad_id", [None, "", 7])
def test_a_rule_without_a_usable_id_is_refused(bad_id):
    rule = dict(REFLEX, id=bad_id)
    assert any("non-empty string" in e for e in errors(mandate([rule])))


def test_a_malformed_window_operand_in_a_mandate_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"window_total_lte": {"seconds": 60}}}
    assert any("amount" in e for e in errors(mandate([rule])))


def test_an_empty_category_list_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"category_in": []}}
    assert any("non-empty list" in e for e in errors(mandate([rule])))


def test_a_judgment_rule_without_on_breach_is_refused():
    rule = dict(JUDGMENT)
    del rule["on_breach"]
    assert any("on_breach" in e for e in errors(mandate([rule])))


def test_a_non_integer_tier_is_refused():
    rule = dict(JUDGMENT, on_breach={"tier": "high"})
    assert any("tier" in e for e in errors(mandate([rule])))


def test_a_non_bool_requires_artifact_is_refused():
    rule = dict(JUDGMENT, requires_artifact="yes")
    assert any("requires_artifact" in e for e in errors(mandate([rule])))


def test_the_vocabulary_tuple_and_the_dispatch_stay_in_sync():
    """``evaluate_predicate`` ends in an 'unhandled predicate' raise that is
    unreachable while ``PREDICATES`` and the dispatch chain agree.

    An unreachable guard is indistinguishable from a missing one, so this test
    forces the divergence: a name added to the vocabulary but not to the
    dispatch must raise rather than fall off the end returning None. It also
    fails if a future predicate is added to ``PREDICATES`` and left unhandled.
    """
    original = core.PREDICATES
    core.PREDICATES = original + ("amount_vibes",)
    try:
        with pytest.raises(core.RemitError, match="unhandled predicate"):
            core.evaluate_predicate("amount_vibes", 1, spend(1), [], LISTS)
    finally:
        core.PREDICATES = original

    for name in core.PREDICATES:
        assert (
            name in core.PREDICATES_INT
            or name in core.PREDICATES_WINDOW_AMOUNT
            or name in core.PREDICATES_WINDOW_COUNT
            or name in core.PREDICATES_LIST_NAME
            or name in core.PREDICATES_STR_SET
        ), "%s is in PREDICATES but in no dispatch group" % name
