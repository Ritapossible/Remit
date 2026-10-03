"""The jury's agreement rule fails closed, and a hesitant yes is not a yes."""

import itertools

import pytest
from conftest import defaults

import remit_core as core

IN, OUT, UND = core.VERDICT_IN_REMIT, core.VERDICT_OUT_OF_REMIT, core.VERDICT_UNDETERMINED


def outcome_of(verdict, on_undetermined=core.DEFAULT_REFUND):
    return core.resolve_hold(
        verdict=verdict,
        artifact=core.ARTIFACT_ABSENT,
        requires_artifact=False,
        defaults=defaults(on_undetermined=on_undetermined),
        deadline_reached=False,
    )


def agrees(leader, own, on_undetermined=core.DEFAULT_REFUND):
    return core.validator_agrees(
        leader_verdict=leader, own_verdict=own, leader_outcome=outcome_of(leader, on_undetermined)
    )


# The full table under a refund default, written out so a reviewer can read it.
@pytest.mark.parametrize(
    "leader,own,expected",
    [
        (IN, IN, True),
        (IN, UND, False),  # the old rule said True: one confident yes over doubt
        (IN, OUT, False),
        (OUT, OUT, True),
        (OUT, UND, True),  # a refusal stands over doubt
        (OUT, IN, False),  # opposite definite answers disagree
        (UND, UND, True),
        (UND, OUT, True),  # undetermined resolves to refund here: still a refusal
        (UND, IN, False),  # a validator sure it is in remit vetoes
    ],
)
def test_agreement_table_under_a_refund_default(leader, own, expected):
    assert agrees(leader, own) is expected


def test_undetermined_that_releases_is_permissive_not_doubt():
    """If the mandate maps undetermined to release, an undetermined leader is
    authorizing money, so it needs agreement like an in_remit leader does."""
    assert agrees(UND, OUT, on_undetermined=core.DEFAULT_RELEASE) is False
    assert agrees(UND, UND, on_undetermined=core.DEFAULT_RELEASE) is True


@pytest.mark.parametrize("on_undetermined", [core.DEFAULT_REFUND, core.DEFAULT_RELEASE])
def test_no_validator_ever_accepts_a_leader_that_allows_without_agreeing(on_undetermined):
    """The property, over every combination: whenever the leader's verdict
    would release the spend, a validator accepts it only if it reached the
    same verdict."""
    for leader, own in itertools.product(core.VERDICTS, repeat=2):
        if outcome_of(leader, on_undetermined) == core.OUTCOME_ALLOWED and leader != own:
            assert agrees(leader, own, on_undetermined) is False, (leader, own)


def test_a_validator_sure_of_in_remit_accepts_only_in_remit():
    for leader in core.VERDICTS:
        assert agrees(leader, IN) is (leader == IN)


@pytest.mark.parametrize(
    "verdict,confidence,expected",
    [
        (IN, 59, UND),
        (IN, 60, IN),
        (IN, 0, UND),
        (OUT, 10, OUT),  # a hesitant no is still a no: refusing costs a resubmission
        (UND, 99, UND),
    ],
)
def test_a_hesitant_in_remit_is_undetermined(verdict, confidence, expected):
    assert core.harden_verdict(verdict, confidence) == expected


def test_agreement_rejects_unknown_tokens():
    with pytest.raises(core.RemitError):
        core.validator_agrees(leader_verdict="maybe", own_verdict=IN, leader_outcome=core.OUTCOME_ALLOWED)
    with pytest.raises(core.RemitError):
        core.validator_agrees(leader_verdict=IN, own_verdict=IN, leader_outcome="paid")
