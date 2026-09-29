"""Mandate validation at registration.

The seven rejections in docs/MANDATE-FORMAT.md, each with a test that fails if
its check is removed, plus the one advisory that is not a rejection.
"""

import json
import os

import pytest
from conftest import VENDOR_A, DROPPED, mandate

import remit_core as core

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


def test_a_well_formed_mandate_validates():
    assert errors(mandate([REFLEX, JUDGMENT])) == []


# --- 1: version -----------------------------------------------------------


def test_version_must_strictly_increase():
    """T5. A republished mandate cannot reuse or lower its version number."""
    assert any("does not exceed" in e for e in errors(mandate([REFLEX], version=3), stored_version=3))
    assert any("does not exceed" in e for e in errors(mandate([REFLEX], version=2), stored_version=3))
    assert errors(mandate([REFLEX], version=4), stored_version=3) == []


def test_a_non_integer_version_is_refused():
    m = mandate([REFLEX])
    m["version"] = "3"
    assert any("version" in e for e in errors(m))


# --- 2: duplicate ids -----------------------------------------------------


def test_duplicate_rule_ids_are_refused():
    duplicate = dict(JUDGMENT)
    duplicate["id"] = REFLEX["id"]
    assert any("duplicate rule id" in e for e in errors(mandate([REFLEX, duplicate])))


# --- 3: vocabulary --------------------------------------------------------


def test_a_predicate_outside_the_vocabulary_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"amount_roughly": 100}}
    assert any("vocabulary" in e for e in errors(mandate([rule])))


def test_an_ambiguous_check_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"amount_lte": 1, "amount_gte": 2}}
    assert any("exactly 1 predicate" in e for e in errors(mandate([rule])))


# --- 4: vendor lists ------------------------------------------------------


def test_an_undefined_vendor_list_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"recipient_in": "contractors"}}
    assert any("not defined" in e for e in errors(mandate([rule])))


def test_a_malformed_vendor_address_is_refused():
    assert any("not hex" in e for e in errors(mandate([REFLEX], lists={"vendors": ["0xzz"]})))


# --- 5: defaults ----------------------------------------------------------


@pytest.mark.parametrize("missing", core.REQUIRED_DEFAULTS)
def test_every_default_is_mandatory(missing):
    """An unstated default is a decision nobody made."""
    m = mandate([REFLEX])
    del m["defaults"][missing]
    assert any(missing in e for e in errors(m))


def test_an_unknown_default_token_is_refused():
    m = mandate([REFLEX], on_deadline="hold_forever")
    assert any("on_deadline" in e for e in errors(m))


def test_a_response_window_longer_than_the_deadline_is_refused():
    """Otherwise every hold expires while still foreclosed and no case could
    ever resolve against a silent agent."""
    m = mandate([REFLEX], response_window_seconds=90000, hold_deadline_seconds=86400)
    assert any("less than hold_deadline" in e for e in errors(m))


# --- 6: tier cap ----------------------------------------------------------


def test_a_rule_may_not_request_more_authority_than_was_granted():
    """A rule asking for tier 3 under a tier 1 registration never reaches a
    jury, because it is refused at registration."""
    assert any("exceeds registered max_tier" in e for e in errors(mandate([JUDGMENT]), max_tier=0))
    assert errors(mandate([JUDGMENT]), max_tier=1) == []


# --- 7: amounts -----------------------------------------------------------


def test_a_negative_amount_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"amount_lte": -1}}
    assert any("non-negative" in e for e in errors(mandate([rule])))


def test_a_float_amount_is_refused():
    rule = {"id": "x", "type": "reflex", "check": {"amount_lte": 200.0}}
    assert any("expected int" in e for e in errors(mandate([rule])))


# --- judgment-specific ----------------------------------------------------


def test_a_judgment_rule_without_a_question_is_refused():
    rule = dict(JUDGMENT)
    del rule["ask"]
    assert any("ask" in e for e in errors(mandate([rule])))


def test_a_context_uri_without_a_digest_is_refused():
    """T5/T10. An unpinned context is not evidence, and validators fetching an
    unpinned URI see different bytes."""
    rule = dict(JUDGMENT, context_uri="https://example.org/brief.md")
    assert any("together" in e for e in errors(mandate([rule])))
    paired = dict(rule, context_digest="sha256:" + "0" * 64)
    assert errors(mandate([paired])) == []


def test_an_unknown_rule_type_is_refused():
    rule = {"id": "x", "type": "advisory", "check": {"amount_lte": 1}}
    assert any("type" in e for e in errors(mandate([rule])))


# --- errors accumulate ----------------------------------------------------


def test_every_problem_is_reported_at_once():
    broken = mandate([{"id": "x", "type": "reflex", "check": {"nope": 1}}], version=1)
    del broken["defaults"]["on_deadline"]
    found = errors(broken, stored_version=5)
    assert len(found) >= 3


# --- the advisory ---------------------------------------------------------


def test_a_reflex_only_mandate_registers_with_a_notice():
    """It is more useful to say a mandate does not need GenLayer than to take
    the deployment."""
    m = mandate([REFLEX])
    assert errors(m) == []
    notices = core.mandate_notices(m)
    assert len(notices) == 1
    assert "no judgment rules" in notices[0]


def test_a_mandate_with_judgment_rules_has_no_notice():
    assert core.mandate_notices(mandate([REFLEX, JUDGMENT])) == []


def test_require_valid_mandate_raises_and_returns_notices():
    with pytest.raises(core.RemitError, match="mandate rejected"):
        core.require_valid_mandate(mandate([REFLEX]), stored_version=9, max_tier=3)
    assert core.require_valid_mandate(mandate([REFLEX, JUDGMENT]), stored_version=0, max_tier=3) == []


# --- the shipped fixtures -------------------------------------------------

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "mandates")


def test_the_example_mandate_validates():
    with open(os.path.join(FIXTURES, "example-campaign.json")) as handle:
        assert errors(json.load(handle)) == []


def test_the_standard_rules_are_well_formed():
    """The three shipped judgment rules must survive validation when dropped
    into a mandate, or the library ships broken."""
    with open(os.path.join(FIXTURES, "standard.json")) as handle:
        standard = json.load(handle)
    m = mandate(standard["rules"] + [REFLEX])
    assert errors(m) == []
