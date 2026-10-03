"""The jury's question, built from a guard's ledger: the shared prompts contract.

Split from the engine only for size (see engine_api.py). Pure Python over the
tested engine and prompt layer, tested directly in tests/direct.
"""

import json

from remit_core import *
from remit_prompts import *


def _spend_of(row):
    return Spend(amount=int(row[0]), recipient=str(row[1]), category=str(row[2]), at=int(row[3]))


def api_jury_prompt(compiled_json, rule_ids, claim, candidate_json, history_json, spend_index):
    """The adjudication prompt with the evidence left as DELIVERABLE_MARKER,
    and the evidence notes the guard fills it in with, as JSON
    ``{"template": str, "notes": {artifact_state: str}}``.

    Built only from facts the guard read from its own ledger - the payment,
    the history, the mandate. Every fired judgment rule is asked. Mirrors the
    single-contract guard's adjudicate exactly; tests hold the two to it.
    """
    compiled = json.loads(compiled_json)
    by_id = {r["id"]: r for r in compiled["rules"]}
    fired = [r for r in str(rule_ids).split(",") if r != ""]
    for r in fired:
        if r not in by_id:
            raise RemitError("unknown rule %r" % r)
    if not fired:
        raise RemitError("no fired rule to ask")
    candidate = _spend_of(json.loads(candidate_json))
    history = [_spend_of(h) for h in json.loads(history_json)]
    prior = [h for h in history if h.at < candidate.at]
    to_same = same_recipient(candidate, prior)

    window_seconds = 0
    for r in fired:
        if int(by_id[r]["b"]) > window_seconds:
            window_seconds = int(by_id[r]["b"])
    if window_seconds == 0:
        window_seconds = 3600

    recent = []
    for h in sorted(prior, key=lambda x: -x.at)[:8]:
        if candidate.at - h.at <= window_seconds:
            recent.append((h.amount, h.recipient, candidate.at - h.at, h.category))
    facts = build_facts_lines(
        recent=recent,
        amount=candidate.amount,
        recipient=candidate.recipient,
        category=candidate.category,
        spend_index=int(spend_index),
        window_count=window_count(candidate, prior, window_seconds, candidate.at),
        window_seconds=window_seconds,
        window_total=window_total(candidate, prior, window_seconds, candidate.at),
        daily_total=window_total(candidate, prior, DAY_SECONDS, candidate.at),
        rule_id=",".join(fired),
        recipient_count=window_count(candidate, to_same, window_seconds, candidate.at),
        recipient_total=window_total(candidate, to_same, window_seconds, candidate.at),
    )
    context = []
    for r in compiled["rules"]:
        if r["type"] == RULE_REFLEX and r["predicate"] == "amount_lte":
            context.append("per-payment cap: %d (smallest unit)" % int(r["a"]))
        elif r["type"] == RULE_REFLEX and r["predicate"] == "daily_total_lte":
            context.append("cap on the rolling 86400-second total: %d (smallest unit)" % int(r["a"]))
    template = build_verdict_template(
        ask=[str(by_id[r]["ask"]) for r in fired],
        facts_lines=[str(f) for f in facts],
        claim_text=str(claim),
        rule_context=context,
    )
    return json.dumps({"template": template, "notes": dict(ARTIFACT_NOTES)})
