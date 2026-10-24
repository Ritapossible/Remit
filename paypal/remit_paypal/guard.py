"""The guard between an AI agent and PayPal's refund API.

The agent never refunds. It asks the guard, which:

1. reads the facts from PayPal itself (order, capture, refunds, tracking,
   disputes);
2. applies checks code can decide, then Remit's engine (caps, windows,
   blocked customers, the split rule), unchanged from the GenLayer contracts;
3. asks the panel of AI models only when a judgment rule fires;
4. refunds through PayPal only when the outcome is ALLOWED, with the request
   ID as PayPal's idempotency key;
5. logs every step in the hash-chained ledger.

Every failure ends without a refund. Decisions are made one at a time, so
two requests cannot both fit under one cap.
"""

import json
import threading
import time
from dataclasses import asdict, dataclass, field

from . import facts as factsmod
from .engine import core, prompts
from .ledger import FAILED, REFUNDED, REFUSED

ALLOWED, DENIED = core.OUTCOME_ALLOWED, core.OUTCOME_REFUSED


@dataclass
class Decision:
    request_id: str
    outcome: str  # "allowed" or "refused"
    stage: str  # facts, checks, engine, panel, paypal
    rules: list = field(default_factory=list)
    reason: str = ""
    verdict: str = ""
    votes: list = field(default_factory=list)
    refund_id: str = ""
    facts: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def load_mandate(text_or_dict):
    """A Remit mandate with a ``paypal`` section. Payer IDs listed there are
    turned into the engine's recipient form, and the whole mandate is checked
    by Remit's own validator."""
    m = json.loads(text_or_dict) if isinstance(text_or_dict, str) else json.loads(json.dumps(text_or_dict))
    pp = m.get("paypal", {})
    lists = m.setdefault("vendor_lists", {})
    for name, payers in pp.get("payer_lists", {}).items():
        lists[name] = [factsmod.payer_address(p) for p in payers]
    core.require_valid_mandate(m, stored_version=0, max_tier=m.get("max_tier", 3))
    if not isinstance(pp.get("currency"), str):
        raise core.RemitError("paypal.currency: expected a currency code")
    return m


class Guard:
    def __init__(self, paypal, ledger, mandate, panel, clock=time.time):
        self.paypal = paypal
        self.ledger = ledger
        self.mandate = mandate
        self.panel = panel
        self.clock = clock
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ api
    def request_refund(self, *, request_id, order_id, amount_cents, category, customer_text="", agent_note=""):
        with self.lock:
            return self._decide(str(request_id), str(order_id), amount_cents, str(category),
                                str(customer_text), str(agent_note))

    # ------------------------------------------------------------ internals
    def _log(self, kind, **body):
        self.ledger.append(int(self.clock()), kind, body)

    def _refuse(self, d, stage, reason, rules=()):
        d.outcome, d.stage, d.reason, d.rules = DENIED, stage, reason, list(rules)
        self.ledger.finish(d.request_id, REFUSED)
        self._log("refused", request_id=d.request_id, stage=stage, reason=reason, rules=list(rules))
        return d

    def _decide(self, request_id, order_id, amount, category, customer_text, agent_note):
        now = int(self.clock())
        d = Decision(request_id=request_id, outcome=DENIED, stage="request")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise core.RemitError("amount_cents: expected a positive integer")
        self._log("requested", request_id=request_id, order_id=order_id, amount_cents=amount, category=category,
                  customer_text=customer_text, agent_note=agent_note)

        # 1. Facts, from PayPal only.
        try:
            f = self.paypal.facts(order_id)
        except Exception as exc:
            self.ledger.start(request_id, "", "", "", amount, category, now)
            return self._refuse(d, "facts", "could not read the order from PayPal: %s" % exc)
        d.facts = f.lines(now)
        self.ledger.start(request_id, f.recipient, f.payer_id, f.capture_id, amount, category, now)
        self._log("facts", request_id=request_id, capture_id=f.capture_id, payer_id=f.payer_id,
                  recipient=f.recipient, lines=d.facts)

        # 2. Checks code decides that the engine does not know about.
        pp = self.mandate["paypal"]
        if f.currency != pp["currency"]:
            return self._refuse(d, "checks", "the order is in %s; this mandate refunds %s" % (f.currency, pp["currency"]),
                                ["currency"])
        if amount > f.refundable_cents:
            return self._refuse(d, "checks", "%s requested, but only %s of this payment is still refundable" % (
                factsmod.money(amount, f.currency), factsmod.money(f.refundable_cents, f.currency)), ["refundable"])
        if pp.get("refuse_when_disputed", True) and f.open_disputes:
            return self._refuse(d, "checks", "this payment has an open PayPal dispute; it is resolved there",
                                ["no-open-dispute"])

        # 3. Remit's engine, unchanged.
        spend = core.Spend(amount=amount, recipient=f.recipient, category=category, at=now)
        history = self.ledger.history(exclude=request_id)
        state, rule_ids = core.classify_spend(self.mandate, spend, history)
        self._log("engine", request_id=request_id, state=state, rules=rule_ids)
        if state == core.SPEND_REFUSED:
            return self._refuse(d, "engine", self._rule_text(rule_ids[0]), rule_ids)

        # 4. The panel, only when a judgment rule fired.
        if state == core.SPEND_HELD:
            d.rules = rule_ids
            prompt = self._prompt(rule_ids, f, spend, history, customer_text, agent_note, now)
            verdict, votes = self.panel.decide(prompt)
            d.verdict, d.votes = verdict, [asdict(v) for v in votes]
            outcome = core.resolve_hold(
                verdict=verdict, artifact=core.ARTIFACT_ABSENT, requires_artifact=False,
                defaults=self.mandate["defaults"], deadline_reached=False)
            self._log("panel", request_id=request_id, rules=rule_ids, verdict=verdict, outcome=outcome,
                      prompt=prompt, votes=d.votes)
            if outcome != ALLOWED:
                why = {"out_of_remit": "the panel found it outside the policy",
                       "undetermined": "the panel could not agree it fits the policy"}[verdict]
                return self._refuse(d, "panel", why, rule_ids)

        # 5. PayPal, only now.
        try:
            refund = self.paypal.refund(f.capture_id, amount, f.currency, request_id,
                                        note="Refund authorized by Remit (%s)" % request_id)
        except Exception as exc:
            d.outcome, d.stage, d.reason = DENIED, "paypal", "PayPal did not complete the refund: %s" % exc
            self.ledger.finish(request_id, FAILED)
            self._log("failed", request_id=request_id, reason=d.reason)
            return d
        d.outcome, d.stage, d.refund_id = ALLOWED, "paypal", refund["id"]
        d.reason = "refunded by PayPal (%s)" % refund.get("status", "")
        self.ledger.finish(request_id, REFUNDED, refund["id"])
        self._log("refunded", request_id=request_id, paypal_refund_id=refund["id"], status=refund.get("status"),
                  capture_id=f.capture_id, amount_cents=amount)
        return d

    def _rule(self, rule_id):
        for r in self.mandate["rules"]:
            if r["id"] == rule_id:
                return r
        raise core.RemitError("unknown rule %r" % rule_id)

    def _rule_text(self, rule_id):
        return self._rule(rule_id).get("explain", "the mandate's rule %r" % rule_id)

    def _prompt(self, rule_ids, f, spend, history, customer_text, agent_note, now):
        asks = [self._rule(r)["ask"] for r in rule_ids]
        same = [h for h in history if h.recipient == spend.recipient and now - h.at < core.DAY_SECONDS]
        lines = [
            "Refund requested: %s to the customer who paid this order." % factsmod.money(spend.amount, f.currency),
            "Reason category chosen by the agent: %s" % prompts.neutralize(spend.category),
            "Refunds this guard already made to this customer in the last 24 hours: %d, totalling %s." % (
                len(same), factsmod.money(sum(h.amount for h in same), f.currency)),
        ]
        for h in same:
            lines.append("    %s, %d minutes before this request, reason %s" % (
                factsmod.money(h.amount, f.currency), (now - h.at) // 60, prompts.neutralize(h.category)))
        policy = self.mandate["paypal"].get("policy", [])
        template = prompts.build_verdict_template(
            ask=asks, facts_lines=lines, rule_context=policy,
            claim_text="Customer's messages:\n%s\n\nSupport agent's note:\n%s" % (customer_text or "(none)", agent_note or "(none)"),
        )
        record = ["These records were read from PayPal by the guard itself, not supplied by the customer or the agent:"]
        record += ["- " + line for line in f.lines(now)]
        return template.replace(prompts.DELIVERABLE_MARKER, "\n".join(record))
