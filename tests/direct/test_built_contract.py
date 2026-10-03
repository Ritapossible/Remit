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

    ``emit_transfer`` is a method on ``ContractProxy`` - a contract-to-contract
    primitive - which is exactly why value sent through it to an externally
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


def test_validator_checks_evidence_exactly_and_fails_closed_on_judgement(built):
    """Split comparison, and both halves matter.

    The artifact state is compared exactly: the validator hash-checked it
    itself, so a leader cannot lie about the evidence. The judgement is
    re-answered by the validator and compared through ``validator_agrees``,
    which fails closed: a leader's refusal may stand over an unsure validator,
    but a leader's authorization stands only on agreement. The earlier rule let
    an unsure validator accept anything, so one confident in_remit over an
    unsure committee released the spend.
    """
    validator = built.index("def validator(")
    after = built.index("gl.vm.run_nondet")
    body = built[validator:after]
    assert 'str(_theirs.get("artifact", "")) != _state' in body, "evidence not compared exactly"
    assert "build_verdict_prompt" in body, "validator does not re-answer the question"
    assert "validator_agrees(" in body, "judgement not compared through the fail-closed rule"
    assert "resolve_hold(" in body, "the leader's verdict must be judged by what it would do"
    assert "== VERDICT_UNDETERMINED" not in body, "an unsure validator must not accept everything"
    assert '_mine["confidence"]' not in body, "confidence must not enter the comparison"


def test_a_hesitant_in_remit_is_undetermined(built):
    fn = built[built.index("def _parse_verdict(raw) -> dict:"):]
    assert "harden_verdict(verdict, confidence)" in fn


def test_every_fired_rule_reaches_the_jury(built):
    start = built.index("    def adjudicate(self, spend_id: int) -> None:")
    body = built[start : built.index("def leader()", start)]
    assert "fired[0]" not in body, "only the first fired rule would be judged"
    assert "ask = [str(self.rule_ask[r]) for r in fired]" in body


def test_no_dead_defensibility_design_ships(built):
    assert "build_defensibility_prompt" not in built
    assert "_is_defensible" not in built


def test_settlement_view_ignores_shadow(built):
    """A rail pays on settlement_of. It must report the real outcome, never the
    shadow-mode 'authorized' that authorization_of returns for observers."""
    fn = built[built.index("    def settlement_of(self, spend_id: int) -> str:"):]
    fn = fn[: fn.index("@gl.public.view", 10)]
    assert "self.shadow" not in fn.split("return json.dumps")[0]
    for key in ('"authorization"', '"recipient"', '"amount"', '"decided_at"', '"shadow"'):
        assert key in fn


def test_an_unreadable_llm_response_is_undetermined_not_a_guess(built):
    """Anything unparseable resolves to UNDETERMINED, which falls to the
    registered default. It is never coerced into a verdict."""
    fn = built[built.index("def _parse_verdict(raw) -> dict:"):]
    assert "verdict = VERDICT_UNDETERMINED" in fn


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


def test_closure_captures_are_plain_python(built):
    """Values captured by the consensus closures must be coerced.

    The leader runs in-process and tolerates a storage-backed value. The
    validator is sandboxed and its closure is pickled, where a storage proxy
    does not survive - measured on Studio, where the leader returned a correct
    verdict and every validator disagreed, deterministically, with no error
    anywhere in the receipt. Nothing about that failure points at the cause,
    which is why it is a test rather than a comment.
    """
    start = built.index("    def adjudicate(self, spend_id: int) -> None:")
    body = built[start : built.index("def leader()", start)]
    for name in ("memo_uri", "memo_digest", "claim"):
        assert "%s = str(" % name in body, "%s is captured without coercion" % name
    assert "ask = [str(" in body, "ask is captured without coercion"
    assert '"on_undetermined": str(self.d_on_undetermined)' in body, "defaults captured without coercion"
    assert "facts = [str(f) for f in facts]" in body
    assert "rule_context = [str(c) for c in" in body


def test_consensus_payloads_are_decoded_until_they_are_dicts(built):
    """A leader's return value reaches the validator JSON-encoded, so one
    ``json.loads`` yields a string. Calling ``.get`` on it raises inside the
    closure, and that error counts as a disagreement - which is how a correct
    verdict came to be rejected by every validator, deterministically, with
    nothing in the receipt pointing at the cause.
    """
    assert "def _as_dict(value) -> dict:" in built
    validator = built.index("def validator(")
    after = built.index("gl.vm.run_nondet")
    body = built[validator:after]
    assert "_as_dict(leader_result)" in body
    assert "json.loads(leader_result)" not in body, "single decode is not enough"


def test_as_dict_coerces_a_wrapper_object(built):
    """A leader's value reaches the validator as a wrapper object, not a str.

    Established on Studio with a per-predicate consensus readout: each probe
    method returned one boolean and agree/disagree was the bit.
    ``isinstance(x, str)`` came back false while ``"verified" in str(x)`` came
    back true. A decoder that gives up on anything not already dict/bytes/str
    therefore sees nothing, and every validator disagrees with a correct
    verdict and no error anywhere in the receipt.
    """
    fn = built[built.index("def _as_dict(value) -> dict:"):]
    fn = fn[: fn.index("\ndef _parse_verdict")]
    assert "not isinstance(data, (dict, str))" in fn
    assert "data = str(data)" in fn


def _method(built, name):
    start = built.index("    def %s(" % name)
    nxt = built.find("\n    @gl.public", start + 1)
    nxt2 = built.find("\n    def ", start + 1)
    ends = [e for e in (nxt, nxt2) if e != -1]
    return built[start : min(ends)] if ends else built[start:]


def test_preview_spend_is_a_view_on_the_real_classifier(built):
    """The preview exists so a UI can say "this will be held for a jury" before
    anyone signs. It is only trustworthy if it is the contract's own decision
    path - a reimplementation elsewhere would drift - and only safe if it is a
    view that cannot write."""
    decorator = built[: built.index("    def preview_spend(")].rstrip().splitlines()[-1].strip()
    assert decorator == "@gl.public.view"
    body = _method(built, "preview_spend")
    assert "self._classify(" in body and "self._history()" in body
    assert "self.s_" not in body.replace("self.s_", "", 0) or "] =" not in body, "preview must not write"
    assert "spend_count =" not in body


def test_new_storage_fields_are_appended(built):
    """Storage layout is position-sensitive; new fields are appended, never
    inserted."""
    cls = built[built.index("class RemitGuard(gl.Contract):") : built.index("    def __init__(self, agent: str")]
    fields = [l.split(":")[0].strip() for l in cls.splitlines() if re.match(r"^    [a-z_]+: ", l)]
    assert fields[-2:] == ["vendor_entries", "s_decided_at"]


def test_claim_reaches_the_summary_view(built):
    summary = built[built.index("def _summarise("):]
    assert '"claim": self.s_claim[key]' in summary
