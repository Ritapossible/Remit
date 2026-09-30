"""Structural tests on the BUILT contract.

These read ``contracts/build/remit.py`` as text because every property here is
invisible to a code review and survives an integration test. Each one
corresponds to a hard law in CLAUDE.md that has already cost real money or real
days somewhere in this codebase's lineage.
"""

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BUILT = os.path.join(ROOT, "contracts", "build", "remit.py")
RUNNER = "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"


@pytest.fixture(scope="module")
def built():
    """Rebuild before reading, so these never pass against a stale artifact."""
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "deploy", "build_contract.py")],
        check=True, capture_output=True,
    )
    with open(BUILT) as handle:
        return handle.read()


# --- T8 / hard law 1 ------------------------------------------------------


def test_no_emit_transfer_in_contract_source(built):
    """Remit takes no custody, so it can never destroy value.

    ``emit_transfer`` is a method on ``ContractProxy`` — a contract-to-contract
    primitive — which is exactly why value sent through it to an externally
    owned account is destroyed. A reviewer cannot see this and a passing
    integration test will not reveal it.
    """
    assert "emit_transfer" not in built
    assert "emit_raw_transfer" not in built


def test_no_payable_entrypoint(built):
    """No entrypoint takes custody. ``gl.public`` exposes only ``view`` and
    ``write`` in the pinned runner, and Remit relies on neither changing."""
    assert "payable" not in built
    assert "gl.message.value" not in built


# --- T10 / hard law 4 -----------------------------------------------------


def test_fetch_is_inline_in_both_closures(built):
    """``genvm-lint`` cannot trace a web call through a helper, and a helper
    that lints clean at authoring time fails on the network. The duplication is
    deliberate; this test is what stops someone 'tidying' it away."""
    fetches = re.findall(r"gl\.nondet\.web\.\w+\(", built)
    assert len(fetches) >= 2, "expected the fetch written out in both closures"

    leader = built.index("def leader()")
    validator = built.index("def validator(")
    after = built.index("gl.vm.run_nondet")
    assert leader < validator < after
    assert "gl.nondet.web." in built[leader:validator], "leader closure has no inline fetch"
    assert "gl.nondet.web." in built[validator:after], "validator closure has no inline fetch"


def test_digest_is_checked_in_both_closures(built):
    """Fetching is not enough: each side must hash-check independently, or the
    validator is trusting the leader's word about the artifact (T4)."""
    leader = built.index("def leader()")
    validator = built.index("def validator(")
    after = built.index("gl.vm.run_nondet")
    assert "hashlib.sha256" in built[leader:validator]
    assert "hashlib.sha256" in built[validator:after]


# --- hard law 5 -----------------------------------------------------------


def test_consensus_uses_run_nondet_not_strict_eq(built):
    """``strict_eq`` routes through ``run_nondet_unsafe``, which does not
    sandbox the validator and offers no ``compare_user_errors``."""
    assert "gl.vm.run_nondet(" in built
    assert "strict_eq" not in built
    assert "run_nondet_unsafe" not in built
    assert "compare_user_errors=True" in built


def test_validator_checks_evidence_exactly_and_judgement_for_defensibility(built):
    """Split comparison, and both halves matter.

    The artifact state is compared exactly: the validator hash-checked it
    itself, so a leader cannot lie about the evidence. The judgement is checked
    for defensibility, because five validators run five different models and
    demanding an identical judgement makes consensus fail on exactly the
    questions this product exists to answer — measured on Studio, where a
    leader's verdict drew three disagreements and the state change was rolled
    back.

    Neither half may be dropped: exact-only cannot reach consensus, and
    defensibility-only would let a leader assert any evidence it liked.
    """
    validator = built.index("def validator(")
    after = built.index("gl.vm.run_nondet")
    body = built[validator:after]
    assert 'str(_theirs.get("artifact", "")) != _state' in body, "evidence not compared exactly"
    assert "build_defensibility_prompt" in body, "judgement not independently reviewed"
    assert "_is_defensible(" in body
    assert "confidence" not in body, "confidence must not enter the comparison"


def test_an_unreadable_validator_review_is_a_disagreement(built):
    """Failing closed: an unparseable review must not wave a verdict through."""
    fn = built[built.index("def _is_defensible("):]
    fn = fn[: fn.index("\ndef _parse_verdict")]
    assert fn.count("return False") >= 3


# --- the runner pin -------------------------------------------------------


def test_runner_is_pinned_to_the_documented_hash(built):
    """All GenLayer networks reject :test, :latest and unversioned aliases."""
    assert built.startswith('# { "Depends": "%s" }' % RUNNER)
    for alias in ("py-genlayer:test", "py-genlayer:latest", '"py-genlayer"'):
        assert alias not in built


# --- no floats, anywhere --------------------------------------------------


def test_no_float_literals_in_executable_code(built):
    """Amounts are integers in the smallest unit. A float in a settlement path
    is a defect, not a rounding question.

    Tokenised rather than grepped: a regex over the source also matches prose
    in comments and docstrings, which would make this test noisy enough that
    someone eventually deletes it.
    """
    import io
    import tokenize

    floats = []
    for token in tokenize.generate_tokens(io.StringIO(built).readline):
        if token.type == tokenize.NUMBER and ("." in token.string or "e" in token.string.lower()):
            floats.append((token.start[0], token.string))
    assert floats == [], "float literals in executable code: %r" % floats
    assert not re.search(r"\bfloat\(\s*amount", built)


# --- the build is honest --------------------------------------------------


def test_built_file_is_reproducible(built):
    """Building twice must produce identical bytes, or the deployed artifact
    cannot be verified against source."""
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "deploy", "build_contract.py")],
        check=True, capture_output=True,
    )
    with open(BUILT) as handle:
        assert handle.read() == built


def test_every_engine_state_reaches_the_summary_view(built):
    """A state the docket cannot show is a state nobody can audit. This exists
    because a field once landed in the wrong view and the deployed list had no
    key while the contract matched its source."""
    summary = built[built.index("def _summarise("):]
    for key in ("verdict", "reason", "confidence", "artifact", "outcome", "tier", "authorization"):
        assert '"%s"' % key in summary, "summary view is missing %r" % key
