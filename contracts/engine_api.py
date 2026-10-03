"""JSON adapters between a Remit guard and the shared Remit engine contract.

Why several contracts: Bradbury caps a transaction at 2^24 gas, and a deploy
costs about 0.96M gas plus 782 per byte of code and arguments (measured with
deploy/probe_gas.mjs), so no contract may exceed about 20 KB. The deterministic
rules live in one shared, stateless engine (this file); the jury's question is
built by a second shared contract (prompts_api.py); each agent's guard keeps
its storage, its entrypoints and the jury. Consensus
closures cannot call another contract, so the jury - the fetch, the model call
and the validator's comparison - stays in the guard, and the guard asks the
engine for everything it needs BEFORE the closures run.

Each function is a thin adapter over the tested engine (remit_core.py) and
prompt layer (remit_prompts.py): parse JSON, call them, return JSON. Pure
Python, tested directly in tests/direct/test_engine_api.py, including that it
decides exactly what the single-contract guard decides.
"""

import json

from remit_core import *


def _rule_view(rule):
    """A mandate rule in the flat shape the guard stores and readers see.

    ``cond`` keeps the original predicate so classification runs the tested
    engine unchanged; ``a``/``b``/``s`` flatten the operands for display.
    """
    kind = str(rule["type"])
    cond = rule["check"] if kind == RULE_REFLEX else rule["when"]
    name, operand = sole_predicate(cond, "rule " + str(rule["id"]))
    a, b, s = 0, 0, ""
    if name in PREDICATES_INT:
        a = int(operand)
    elif name in PREDICATES_WINDOW_AMOUNT:
        a, b = int(operand["amount"]), int(operand["seconds"])
    elif name in PREDICATES_WINDOW_COUNT:
        a, b = int(operand["count"]), int(operand["seconds"])
    elif name in PREDICATES_LIST_NAME:
        s = str(operand)
    else:
        s = ",".join([str(c) for c in operand])
    return {
        "id": str(rule["id"]),
        "type": kind,
        "predicate": name,
        "cond": {name: operand},
        "a": a,
        "b": b,
        "s": s,
        "requires_artifact": bool(rule.get("requires_artifact", False)),
        "tier": int(rule.get("on_breach", {}).get("tier", 0)),
        "ask": str(rule.get("ask", "")),
    }


def api_compile(mandate_json, max_tier):
    """Validate a mandate and flatten it for storage. A non-empty ``errors``
    means the guard must refuse to deploy."""
    try:
        mandate = json.loads(mandate_json)
    except Exception:
        return json.dumps({"errors": ["mandate: not valid JSON"]})
    errors = validate_mandate(mandate, stored_version=0, max_tier=int(max_tier))
    if errors:
        return json.dumps({"errors": errors})
    lists = {}
    for name in mandate.get("vendor_lists", {}):
        lists[str(name)] = [normalize_address(a) for a in mandate["vendor_lists"][name]]
    return json.dumps(
        {
            "errors": [],
            "mandate_version": int(mandate["version"]),
            "mandate_uri": str(mandate.get("mandate_uri", "")),
            "mandate_digest": str(mandate.get("mandate_digest", "")).lower(),
            "defaults": {k: mandate["defaults"][k] for k in REQUIRED_DEFAULTS},
            "vendor_lists": lists,
            "rules": [_rule_view(r) for r in mandate["rules"]],
        }
    )


def _mandate_of(compiled):
    rules = []
    for r in compiled["rules"]:
        rules.append({"id": r["id"], "type": r["type"], ("check" if r["type"] == RULE_REFLEX else "when"): r["cond"]})
    return {"rules": rules, "vendor_lists": compiled["vendor_lists"]}


def _spend_of(row):
    return Spend(amount=int(row[0]), recipient=str(row[1]), category=str(row[2]), at=int(row[3]))


def api_classify(compiled_json, history_json, candidate_json):
    """SETTLED / REFUSED / HELD and the rules that decided it, by the tested
    engine classifier. ``candidate`` and each history row are
    ``[amount, recipient, category, at]``."""
    compiled = json.loads(compiled_json)
    state, fired = classify_spend(
        _mandate_of(compiled),
        _spend_of(json.loads(candidate_json)),
        [_spend_of(h) for h in json.loads(history_json)],
    )
    return json.dumps({"state": state, "rules": [str(r) for r in fired]})


def api_outcomes(compiled_json, requires_artifact):
    """What every possible verdict resolves to, for every artifact state.

    The guard's validator closure needs the leader's verdict mapped to an
    outcome to apply the fail-closed rule, and cannot call this contract from
    inside the closure, so the guard fetches the whole table first. Also
    carries the deadline outcomes (no verdict).
    """
    compiled = json.loads(compiled_json)
    table = {}
    for verdict in VERDICTS:
        table[verdict] = {}
        for artifact in ARTIFACT_STATES:
            table[verdict][artifact] = resolve_hold(
                verdict=verdict,
                artifact=artifact,
                requires_artifact=bool(requires_artifact),
                defaults=compiled["defaults"],
                deadline_reached=False,
            )
    table["deadline"] = {}
    for artifact in ARTIFACT_STATES:
        table["deadline"][artifact] = resolve_hold(
            verdict=None,
            artifact=artifact,
            requires_artifact=bool(requires_artifact),
            defaults=compiled["defaults"],
            deadline_reached=True,
        )
    return json.dumps(table)


def api_uncommitted(held_at, now, window):
    """FORECLOSED inside the response window, ABSENT after it (T9)."""
    return uncommitted_artifact(held_at=int(held_at), now=int(now), response_window_seconds=int(window))
