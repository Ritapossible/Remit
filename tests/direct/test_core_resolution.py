"""Hold resolution and value conservation."""

import pytest
from conftest import AGENT, PRINCIPAL, VENDOR_A, defaults

import remit_core as core


def resolve(**kwargs):
    base = {
        "verdict": core.VERDICT_IN_REMIT,
        "artifact": core.ARTIFACT_VERIFIED,
        "requires_artifact": False,
        "defaults": defaults(),
        "deadline_reached": False,
    }
    base.update(kwargs)
    return core.resolve_hold(**base)


# --- verdicts -------------------------------------------------------------


def test_in_remit_allows():
    assert resolve(verdict=core.VERDICT_IN_REMIT) == core.OUTCOME_ALLOWED


def test_out_of_remit_refuses():
    assert resolve(verdict=core.VERDICT_OUT_OF_REMIT) == core.OUTCOME_REFUSED


def test_undetermined_falls_to_the_registered_default():
    """Unproven is not guilty. The principal chose which way this falls."""
    assert resolve(verdict=core.VERDICT_UNDETERMINED) == core.OUTCOME_REFUSED
    assert (
        resolve(
            verdict=core.VERDICT_UNDETERMINED,
            defaults=defaults(on_undetermined=core.DEFAULT_RELEASE),
        )
        == core.OUTCOME_ALLOWED
    )


# --- T9: foreclosure ------------------------------------------------------


def test_foreclosed_artifact_resolves_in_agents_favour():
    """T9. A party never given its window cannot lose for not using it."""
    assert (
        resolve(
            verdict=core.VERDICT_OUT_OF_REMIT,
            artifact=core.ARTIFACT_FORECLOSED,
            requires_artifact=True,
        )
        == core.OUTCOME_ALLOWED
    )


def test_absent_artifact_after_window_does_not():
    """The same missing artifact, once the window has elapsed, is the agent's
    own silence and refuses."""
    assert (
        resolve(
            verdict=core.VERDICT_IN_REMIT,
            artifact=core.ARTIFACT_ABSENT,
            requires_artifact=True,
        )
        == core.OUTCOME_REFUSED
    )


def test_foreclosure_outranks_a_reached_deadline():
    assert (
        resolve(verdict=None, artifact=core.ARTIFACT_FORECLOSED, deadline_reached=True)
        == core.OUTCOME_ALLOWED
    )


def test_a_missing_artifact_is_ignored_when_the_rule_did_not_require_one():
    assert (
        resolve(
            verdict=core.VERDICT_IN_REMIT,
            artifact=core.ARTIFACT_ABSENT,
            requires_artifact=False,
        )
        == core.OUTCOME_ALLOWED
    )


def test_unverified_artifact_refuses_when_required():
    """T4. A digest mismatch is not the evidence the rule asked for."""
    assert (
        resolve(
            verdict=core.VERDICT_IN_REMIT,
            artifact=core.ARTIFACT_UNVERIFIED,
            requires_artifact=True,
        )
        == core.OUTCOME_REFUSED
    )


# --- T2: deadlines --------------------------------------------------------


def test_held_spend_resolves_at_deadline_to_registered_default():
    """T2. No hold is indefinite."""
    assert (
        resolve(verdict=None, artifact=core.ARTIFACT_ABSENT, deadline_reached=True)
        == core.OUTCOME_REFUSED
    )
    assert (
        resolve(
            verdict=None,
            artifact=core.ARTIFACT_ABSENT,
            deadline_reached=True,
            defaults=defaults(on_deadline=core.DEFAULT_RELEASE),
        )
        == core.OUTCOME_ALLOWED
    )


def test_no_verdict_before_the_deadline_is_not_resolvable():
    with pytest.raises(core.RemitError, match="not resolvable"):
        resolve(verdict=None, artifact=core.ARTIFACT_ABSENT, deadline_reached=False)


# --- guards ---------------------------------------------------------------


def test_unknown_verdict_raises():
    with pytest.raises(core.RemitError, match="verdict"):
        resolve(verdict="probably_fine")


def test_unknown_artifact_state_raises():
    with pytest.raises(core.RemitError, match="artifact state"):
        resolve(artifact="maybe")


def test_missing_default_raises_rather_than_assuming_one():
    incomplete = defaults()
    del incomplete["on_deadline"]
    with pytest.raises(core.RemitError, match="missing"):
        resolve(defaults=incomplete)


# --- settlement -----------------------------------------------------------


def test_allowed_credits_the_vendor_and_refused_credits_the_principal():
    allowed = core.settle_hold(
        escrow=15000, committed=15000, outcome=core.OUTCOME_ALLOWED,
        vendor=VENDOR_A, principal=PRINCIPAL,
    )
    assert allowed == {VENDOR_A: 15000}
    refused = core.settle_hold(
        escrow=15000, committed=15000, outcome=core.OUTCOME_REFUSED,
        vendor=VENDOR_A, principal=PRINCIPAL,
    )
    assert refused == {PRINCIPAL: 15000}


def test_settlement_conserves_value_exactly():
    for outcome in core.OUTCOMES:
        credits = core.settle_hold(
            escrow=12345, committed=12345, outcome=outcome,
            vendor=VENDOR_A, principal=PRINCIPAL,
        )
        assert sum(credits.values()) == 12345


def test_escrow_must_equal_the_committed_amount_exactly():
    """Hard law 2. A surplus once restored an already-delivered payout; the
    claimant ended up holding 1.8 for a 0.925 entitlement. An inequality here
    is satisfied by two different states, so it is the wrong comparison."""
    with pytest.raises(core.RemitError, match="!="):
        core.settle_hold(
            escrow=15001, committed=15000, outcome=core.OUTCOME_ALLOWED,
            vendor=VENDOR_A, principal=PRINCIPAL,
        )
    with pytest.raises(core.RemitError, match="!="):
        core.settle_hold(
            escrow=14999, committed=15000, outcome=core.OUTCOME_ALLOWED,
            vendor=VENDOR_A, principal=PRINCIPAL,
        )


def test_the_conservation_invariant_itself_rejects_a_mismatch():
    """``_require_conserved`` is an internal invariant: in ``settle_hold`` the
    credits equal the escrow by construction, so no public call can violate it.

    That is exactly why it needs a direct test. An invariant no test can break
    is indistinguishable from one that is not there, and the mutation harness
    reports it as an untested guard.
    """
    assert core._require_conserved(500, 500, "ctx") == 500
    with pytest.raises(core.RemitError, match="not conserved"):
        core._require_conserved(499, 500, "ctx")
    with pytest.raises(core.RemitError, match="not conserved"):
        core._require_conserved(501, 500, "ctx")
