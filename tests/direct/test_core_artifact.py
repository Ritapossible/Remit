"""Artifact provenance, and the foreclosure distinction (T9).

ABSENT and FORECLOSED resolve in opposite directions. Collapsing them
reintroduces a grief that was confirmed on chain in prior work: one party acts
fast enough that the other cannot respond, and the forfeit lands on a record
that looks empty.
"""

import pytest
from conftest import T0

import remit_core as core

DIGEST = "a" * 64
OTHER = "b" * 64


def test_matching_digest_verifies():
    assert core.verify_artifact(DIGEST, DIGEST) == core.ARTIFACT_VERIFIED


def test_digest_comparison_ignores_case_and_surrounding_space():
    assert core.verify_artifact("  " + DIGEST.upper() + " ", DIGEST) == core.ARTIFACT_VERIFIED


def test_digest_mismatch_is_not_evidence():
    """T4. A fetched body that does not hash to the commitment is UNVERIFIED.

    It is never silently accepted as the artifact the agent promised.
    """
    assert core.verify_artifact(DIGEST, OTHER) == core.ARTIFACT_UNVERIFIED


def test_unfetchable_artifact_is_unverified_not_verified():
    assert core.verify_artifact(DIGEST, None) == core.ARTIFACT_UNVERIFIED


def test_inside_the_response_window_an_uncommitted_artifact_is_foreclosed():
    state = core.uncommitted_artifact(held_at=T0, now=T0 + 899, response_window_seconds=900)
    assert state == core.ARTIFACT_FORECLOSED


def test_at_the_window_boundary_it_becomes_absent():
    """The window is a minimum guarantee: at exactly ``window`` it has elapsed."""
    assert (
        core.uncommitted_artifact(held_at=T0, now=T0 + 900, response_window_seconds=900)
        == core.ARTIFACT_ABSENT
    )


def test_absent_and_foreclosed_are_distinct_states():
    assert core.ARTIFACT_ABSENT != core.ARTIFACT_FORECLOSED
    assert core.ARTIFACT_ABSENT in core.ARTIFACT_STATES
    assert core.ARTIFACT_FORECLOSED in core.ARTIFACT_STATES


def test_time_running_backwards_raises_rather_than_defaulting():
    with pytest.raises(core.RemitError, match="precedes"):
        core.uncommitted_artifact(held_at=T0, now=T0 - 1, response_window_seconds=900)


@pytest.mark.parametrize("empty", [None, ""])
def test_artifact_state_routes_an_uncommitted_artifact_to_the_window(empty):
    assert (
        core.artifact_state(
            committed_digest=empty,
            fetched_digest=None,
            held_at=T0,
            now=T0 + 10,
            response_window_seconds=900,
        )
        == core.ARTIFACT_FORECLOSED
    )


def test_artifact_state_routes_a_committed_artifact_to_the_digest_check():
    assert (
        core.artifact_state(
            committed_digest=DIGEST,
            fetched_digest=DIGEST,
            held_at=T0,
            now=T0 + 100000,
            response_window_seconds=900,
        )
        == core.ARTIFACT_VERIFIED
    )
