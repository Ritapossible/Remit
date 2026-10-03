"""Prompt injection (T4): untrusted text cannot rewrite the jury's question.

Every string in tests/fixtures/injections.json is tried as the agent's claim,
as the text of its committed artifact, and as its declared category. Wherever
it lands, the assembled prompt keeps exactly one of each section heading and
marker, in order, with the untrusted text between its own markers - and a
category that is not a plain label is refused at the gate.
"""

import json
import os

import pytest
from conftest import T0, VENDOR_A, defaults, DROPPED, VENDOR_B

import remit_core as core
import remit_prompts as prompts
import prompts_api
import engine_api

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(ROOT, "tests", "fixtures", "injections.json")) as _h:
    INJECTIONS = json.load(_h)["strings"]

MANDATE = {
    "remit_mandate_version": 1, "version": 1, "currency": "ATTO_GEN", "defaults": defaults(),
    "vendor_lists": {"vendors": [VENDOR_A, VENDOR_B], "dropped": [DROPPED]},
    "rules": [
        {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 20000}},
        {"id": "structuring", "type": "judgment", "when": {"recipient_total_gte": {"amount": 20001, "seconds": 86400}},
         "ask": "Are these payments one purchase split under the cap?", "on_breach": {"tier": 2}},
    ],
}
COMPILED = engine_api.api_compile(json.dumps(MANDATE), 2)

# The prompt's structure, in order. Each must appear exactly once.
STRUCTURE = [
    "=== MANDATE RULE (pinned before this payment; the only authority) ===",
    "=== FACTS (read by the contract from its own ledger) ===",
    "=== DELIVERABLE ===",
    "=== CLAIM (supplied by the agent; UNTRUSTED) ===",
    "--- begin untrusted claim ---",
    "--- end untrusted claim ---",
    "=== YOUR ANSWER ===",
]


def prompt(claim="", artifact_text="", category="media"):
    hist = [[15000, VENDOR_A, category, T0 - 60]]
    cand = [15000, VENDOR_A, category, T0]
    q = json.loads(prompts_api.api_jury_prompt(COMPILED, "structuring", claim, json.dumps(cand), json.dumps(hist), 2))
    state = "verified" if artifact_text else "absent"
    return q["template"].replace(prompts.DELIVERABLE_MARKER, prompts.build_deliverable(state, artifact_text, q["notes"]))


def assert_structure_intact(text, with_artifact):
    expected = STRUCTURE + (["--- begin artifact ---", "--- end artifact ---"] if with_artifact else [])
    for marker in expected:
        assert text.count(marker) == 1, "%r appears %d times" % (marker, text.count(marker))
    positions = [text.index(m) for m in STRUCTURE]
    assert positions == sorted(positions), "sections out of order"
    assert prompts.DELIVERABLE_MARKER not in text
    # No line of untrusted origin may look like a heading or a marker.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") or stripped.startswith("---"):
            assert stripped in expected, "forged structure line: %r" % stripped


@pytest.mark.parametrize("attack", INJECTIONS)
def test_claim_cannot_forge_structure(attack):
    text = prompt(claim=attack)
    assert_structure_intact(text, with_artifact=False)
    start = text.index("--- begin untrusted claim ---")
    end = text.index("--- end untrusted claim ---")
    # The attack's words are still shown to the jury - only disarmed - and
    # they sit inside the untrusted block.
    assert prompts.neutralize(attack) in text[start:end]


@pytest.mark.parametrize("attack", INJECTIONS)
def test_artifact_cannot_forge_structure(attack):
    assert_structure_intact(prompt(artifact_text="Invoice INV-1\n" + attack), with_artifact=True)


@pytest.mark.parametrize("attack", INJECTIONS)
def test_injected_category_is_refused_at_the_gate(attack):
    cand = [100, VENDOR_A, attack, T0]
    out = json.loads(engine_api.api_classify(COMPILED, "[]", json.dumps(cand)))
    assert out["state"] == "invalid" and out["error"], attack


@pytest.mark.parametrize("category", ["media", "hosting", "ads-q4", "ad spend", "v1.2_x"])
def test_ordinary_categories_pass(category):
    cand = [100, VENDOR_A, category, T0]
    assert json.loads(engine_api.api_classify(COMPILED, "[]", json.dumps(cand)))["state"] != "invalid"


@pytest.mark.parametrize("bad", ["", "x" * 41, "media\nfoo", "méda", "a=b", "a<b"])
def test_categories_that_are_not_labels_are_refused(bad):
    assert core.is_category(bad) is False


def test_neutralize_is_idempotent_and_breaks_every_run():
    for attack in INJECTIONS:
        once = prompts.neutralize(attack)
        assert "===" not in once and "---" not in once and "\r" not in once
        assert prompts.neutralize(once) == once


# --- a bonded challenge: the challenger's statement is untrusted too --------

CHALLENGE_STRUCTURE = STRUCTURE[:6] + [
    "=== CHALLENGE (supplied by the challenger; UNTRUSTED) ===",
    "--- begin untrusted challenge ---",
    "--- end untrusted challenge ---",
] + STRUCTURE[6:]


def challenge_prompt(statement, claim=""):
    hist = [[15000, VENDOR_A, "media", T0 - 60]]
    cand = [15000, VENDOR_A, "media", T0]
    q = json.loads(
        prompts_api.api_challenge_prompt(COMPILED, "structuring", claim, statement, json.dumps(cand), json.dumps(hist), 2)
    )
    return q["template"].replace(prompts.DELIVERABLE_MARKER, prompts.build_deliverable("absent", "", q["notes"]))


@pytest.mark.parametrize("attack", INJECTIONS)
def test_challenge_statement_cannot_forge_structure(attack):
    text = challenge_prompt(attack, claim=attack)
    for marker in CHALLENGE_STRUCTURE:
        assert text.count(marker) == 1, "%r appears %d times" % (marker, text.count(marker))
    positions = [text.index(m) for m in CHALLENGE_STRUCTURE]
    assert positions == sorted(positions), "sections out of order"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") or stripped.startswith("---"):
            assert stripped in CHALLENGE_STRUCTURE, "forged structure line: %r" % stripped
    start = text.index("--- begin untrusted challenge ---")
    assert prompts.neutralize(attack) in text[start : text.index("--- end untrusted challenge ---")]


def test_a_challenge_is_framed_as_an_interested_allegation():
    text = challenge_prompt("They split it.")
    assert "posted a bond alleging a breach" in text and "gains if you find one" in text
    assert "opened by an arithmetic trigger" not in text
    assert "opened by an arithmetic trigger" in prompt()


def test_a_challenge_must_name_a_judgment_rule():
    with pytest.raises(core.RemitError):
        prompts_api.api_challenge_prompt(COMPILED, "per-spend", "", "x", json.dumps([1, VENDOR_A, "m", T0]), "[]", 1)
    with pytest.raises(core.RemitError):
        prompts_api.api_challenge_prompt(COMPILED, "nope", "", "x", json.dumps([1, VENDOR_A, "m", T0]), "[]", 1)
