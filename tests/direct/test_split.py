"""The split deployment: engine, prompts and guard.

Remit deploys as three contracts because Bradbury caps a transaction at 2^24
gas. These tests hold the split to three promises:

1. **Same decisions.** The engine and prompts adapters decide exactly what the
   tested engine functions decide, and the guard's assembled jury prompt is
   byte-for-byte the prompt measured on Studio before the split.
2. **Deployable bytes are the tested bytes.** Each ``*.min.py`` equals a fresh
   minify of its readable build, and every name a minified contract uses is
   defined - a tree-shaker mistake fails here, not on a chain.
3. **It fits.** Each contract stays inside the measured gas budget.
"""

import ast
import builtins
import itertools
import json
import os
import sys

import pytest
from conftest import T0, VENDOR_A, VENDOR_B, DROPPED, defaults, mandate

import remit_core as core
import remit_prompts as prompts

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD = os.path.join(ROOT, "contracts", "build")
sys.path.insert(0, os.path.join(ROOT, "contracts"))
sys.path.insert(0, os.path.join(ROOT, "deploy"))

import engine_api  # noqa: E402
import prompts_api  # noqa: E402
from minify_contract import minify, _names_used  # noqa: E402

CAP = 16_777_216
# Measured on Bradbury with deploy/probe_gas.mjs: gas = 0.96M + 782 per byte
# of code and constructor arguments.
FIXED_GAS, GAS_PER_BYTE = 960_000, 782


def deploy_gas(nbytes):
    return FIXED_GAS + GAS_PER_BYTE * nbytes


DEMO = {
    "remit_mandate_version": 1,
    "version": 1,
    "currency": "ATTO_GEN",
    "defaults": defaults(on_undetermined=core.DEFAULT_REFUND, response_window_seconds=60, hold_deadline_seconds=3600),
    "vendor_lists": {"vendors": [VENDOR_A, VENDOR_B], "dropped": [DROPPED]},
    "rules": [
        {"id": "per-spend", "type": "reflex", "check": {"amount_lte": 20000}},
        {"id": "daily-cap", "type": "reflex", "check": {"daily_total_lte": 50000}},
        {"id": "allowlist", "type": "reflex", "check": {"recipient_in": "vendors"}},
        {"id": "not-dropped", "type": "reflex", "check": {"recipient_not_in": "dropped"}},
        {
            "id": "structuring",
            "type": "judgment",
            "when": {"recipient_total_gte": {"amount": 20001, "seconds": 86400}},
            "ask": "Are these payments one purchase split under the cap?",
            "on_breach": {"tier": 2},
        },
        {
            "id": "big",
            "type": "judgment",
            "when": {"amount_gte": 15000},
            "ask": "Does this payment match a delivered item?",
            "requires_artifact": True,
            "on_breach": {"tier": 1},
        },
    ],
}


def compiled():
    out = json.loads(engine_api.api_compile(json.dumps(DEMO), 2))
    assert out["errors"] == []
    return out


def row(s):
    return [s.amount, s.recipient, s.category, s.at]


# --- 1. same decisions ------------------------------------------------------


def test_compile_rejects_what_validate_rejects():
    bad = dict(DEMO, rules=[{"id": "x", "type": "reflex", "check": {"nope": 1}}])
    assert json.loads(engine_api.api_compile(json.dumps(bad), 2))["errors"]
    assert json.loads(engine_api.api_compile("not json", 2))["errors"] == ["mandate: not valid JSON"]


@pytest.mark.parametrize(
    "history,amount,to",
    [
        ([], 5000, VENDOR_A),
        ([], 25000, VENDOR_A),
        ([], 5000, DROPPED),
        ([(15000, VENDOR_A, -60)], 15000, VENDOR_A),
        ([(15000, VENDOR_A, -60)], 15000, VENDOR_B),
        ([(15000, VENDOR_A, -90000)], 15000, VENDOR_A),
        ([(15000, VENDOR_A, -60), (15000, VENDOR_B, -30)], 10000, VENDOR_B),
        ([(20000, VENDOR_A, -60), (20000, VENDOR_B, -30)], 15000, VENDOR_A),
    ],
)
def test_classify_matches_the_engine(history, amount, to):
    hist = [core.Spend(amount=a, recipient=r, category="media", at=T0 + d) for a, r, d in history]
    cand = core.Spend(amount=amount, recipient=to, category="media", at=T0)
    expected = core.classify_spend(DEMO, cand, hist)
    got = json.loads(engine_api.api_classify(json.dumps(compiled()), json.dumps([row(h) for h in hist]), json.dumps(row(cand))))
    assert (got["state"], got["rules"]) == (expected[0], list(expected[1]))


@pytest.mark.parametrize("requires", [False, True])
@pytest.mark.parametrize("on_undetermined", [core.DEFAULT_REFUND, core.DEFAULT_RELEASE])
def test_outcome_table_is_resolve_hold(requires, on_undetermined):
    m = dict(DEMO, defaults=defaults(on_undetermined=on_undetermined))
    c = json.loads(engine_api.api_compile(json.dumps(m), 2))
    table = json.loads(engine_api.api_outcomes(json.dumps(c), requires))
    for verdict, artifact in itertools.product(core.VERDICTS, core.ARTIFACT_STATES):
        assert table[verdict][artifact] == core.resolve_hold(
            verdict=verdict, artifact=artifact, requires_artifact=requires, defaults=m["defaults"], deadline_reached=False
        )
    for artifact in core.ARTIFACT_STATES:
        assert table["deadline"][artifact] == core.resolve_hold(
            verdict=None, artifact=artifact, requires_artifact=requires, defaults=m["defaults"], deadline_reached=True
        )


def _expected_prompt(c, fired, claim, cand, hist, index, state, text):
    """The prompt as the single-contract guard built it on Studio, written out
    from the engine and prompt functions directly."""
    by_id = {r["id"]: r for r in c["rules"]}
    prior = [h for h in hist if h.at < cand.at]
    window = max([int(by_id[r]["b"]) for r in fired] + [0]) or 3600
    to_same = core.same_recipient(cand, prior)
    recent = [
        (h.amount, h.recipient, cand.at - h.at, h.category)
        for h in sorted(prior, key=lambda x: -x.at)[:8]
        if cand.at - h.at <= window
    ]
    facts = prompts.build_facts_lines(
        recent=recent, amount=cand.amount, recipient=cand.recipient, category=cand.category, spend_index=index,
        window_count=core.window_count(cand, prior, window, cand.at), window_seconds=window,
        window_total=core.window_total(cand, prior, window, cand.at),
        daily_total=core.window_total(cand, prior, core.DAY_SECONDS, cand.at), rule_id=",".join(fired),
        recipient_count=core.window_count(cand, to_same, window, cand.at),
        recipient_total=core.window_total(cand, to_same, window, cand.at),
    )
    context = ["per-payment cap: 20000 (smallest unit)", "cap on the rolling 86400-second total: 50000 (smallest unit)"]
    return prompts.build_verdict_prompt(
        ask=[by_id[r]["ask"] for r in fired], facts_lines=facts, artifact_state=state,
        artifact_text=text, claim_text=claim, rule_context=context,
    )


@pytest.mark.parametrize("fired", [["structuring"], ["structuring", "big"]])
@pytest.mark.parametrize("state,text", [("verified", "INVOICE"), ("absent", ""), ("unverified", "")])
def test_the_guards_prompt_is_the_measured_prompt(fired, state, text):
    c = compiled()
    hist = [core.Spend(amount=15000, recipient=VENDOR_A, category="media", at=T0 - 60)]
    cand = core.Spend(amount=15000, recipient=VENDOR_A, category="media", at=T0)
    q = json.loads(
        prompts_api.api_jury_prompt(
            json.dumps(c), ",".join(fired), "my claim", json.dumps(row(cand)), json.dumps([row(h) for h in hist]), 2
        )
    )
    # Exactly what the guard's closures do with the answer:
    assembled = q["template"].replace(
        prompts.DELIVERABLE_MARKER, prompts.build_deliverable(state, text, {str(k): str(v) for k, v in q["notes"].items()})
    )
    assert assembled == _expected_prompt(c, fired, "my claim", cand, hist, 2, state, text)


def test_jury_prompt_refuses_unknown_or_missing_rules():
    c = json.dumps(compiled())
    with pytest.raises(core.RemitError):
        prompts_api.api_jury_prompt(c, "nope", "", json.dumps([1, VENDOR_A, "m", T0]), "[]", 1)
    with pytest.raises(core.RemitError):
        prompts_api.api_jury_prompt(c, "", "", json.dumps([1, VENDOR_A, "m", T0]), "[]", 1)


# --- 2. deployable bytes are the tested bytes ------------------------------

CONTRACTS = {
    "engine": "RemitEngine",
    "prompts": "RemitPrompts",
    "guard": "RemitGuard",
    "rail": "RemitRail",
    "registry": "RemitRegistry",
}
# Names the GenVM runtime provides through `from genlayer import *`.
GENLAYER = {"gl", "Address", "u256", "TreeMap", "DynArray"}


@pytest.mark.parametrize("name,root", CONTRACTS.items())
def test_deployed_file_is_a_fresh_minify_of_the_tested_build(name, root):
    with open(os.path.join(BUILD, name + ".py")) as h:
        readable = h.read()
    with open(os.path.join(BUILD, name + ".min.py")) as h:
        deployed = h.read()
    assert minify(readable, root=root)[0] == deployed
    lines = deployed.splitlines()
    assert lines[0].startswith('# { "Depends": "py-genlayer:')
    assert lines[1] == "from genlayer import *", "the header must be followed immediately by code"


@pytest.mark.parametrize("name", CONTRACTS)
def test_every_name_a_deployed_contract_uses_is_defined(name):
    with open(os.path.join(BUILD, name + ".min.py")) as h:
        tree = ast.parse(h.read())
    defined = set(GENLAYER) | set(dir(builtins))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            defined |= {(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"}
    missing = set()
    for node in tree.body:
        missing |= _names_used(node) - defined
    assert not missing, "%s.min.py uses undefined names: %s" % (name, sorted(missing))


# --- 3. it fits -------------------------------------------------------------

# Room left for the guard's constructor arguments. The demo mandate, sent
# compact, is about 1.2 KB.
MANDATE_ROOM = 1_800


@pytest.mark.parametrize("name", ["engine", "prompts", "registry"])
def test_shared_contracts_fit_the_gas_cap(name):
    size = os.path.getsize(os.path.join(BUILD, name + ".min.py"))
    assert deploy_gas(size) < CAP * 0.95, "%s.min.py is %d bytes" % (name, size)


def test_the_guard_leaves_room_for_a_mandate():
    size = os.path.getsize(os.path.join(BUILD, "guard.min.py"))
    assert deploy_gas(size + MANDATE_ROOM) < CAP * 0.97, "guard.min.py is %d bytes" % size


def test_the_rail_fits_with_its_arguments():
    """Constructor arguments are an address and two integers."""
    size = os.path.getsize(os.path.join(BUILD, "rail.min.py"))
    assert deploy_gas(size + 200) < CAP * 0.95, "rail.min.py is %d bytes" % size
