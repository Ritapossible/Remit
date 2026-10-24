import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from remit_paypal.fake_paypal import FakePayPal  # noqa: E402
from remit_paypal.guard import Guard, load_mandate  # noqa: E402
from remit_paypal.ledger import Ledger  # noqa: E402
from remit_paypal.panel import Panel  # noqa: E402

NOW = 1_793_000_000
DAY = 86400
MANDATE = os.path.join(os.path.dirname(HERE), "mandates", "demo-shop.json")


def answer(verdict, confidence=90, reason="matches_rule"):
    return json.dumps({"verdict": verdict, "reason": reason, "confidence": confidence})


def reader(prompt):
    """A stand-in model that reads only the PayPal records and the request,
    never the untrusted block, and applies the demo policy plainly."""
    trusted = prompt.split("=== CLAIM", 1)[0]
    claim = prompt.split("--- begin untrusted claim ---", 1)[1].split("--- end untrusted claim ---", 1)[0].lower()
    if "split into parts" in trusted:
        n = trusted.split("Refunds this guard already made to this customer in the last 24 hours: ", 1)[1]
        if int(n.split(",", 1)[0]) >= 2:
            return answer("out_of_remit", 85, "structured_to_evade")
    if "never arrived" in claim and "DELIVERED" in trusted:
        return answer("out_of_remit", 90, "violates_rule")
    if "damaged" in claim or "broken" in claim:
        return answer("in_remit", 88)
    return answer("undetermined", 50, "insufficient_evidence")


class World:
    def __init__(self, models=None, quorum=2):
        self.now = NOW
        self.paypal = FakePayPal()
        self.ledger = Ledger()
        with open(MANDATE) as f:
            self.mandate = load_mandate(f.read())
        models = models or {"model-a": reader, "model-b": reader, "model-c": reader}
        self.prompts = []

        def recording(fn):
            def call(prompt):
                self.prompts.append(prompt)
                return fn(prompt)
            return call

        self.panel = Panel({n: recording(m) for n, m in models.items()}, quorum=quorum)
        self.guard = Guard(self.paypal, self.ledger, self.mandate, self.panel, clock=lambda: self.now)
        self._req = 0

    def order(self, cents=4500, items=None, **kw):
        kw.setdefault("payer_id", "PAYER1")
        kw.setdefault("name", "Ada Obi")
        kw.setdefault("paid_at", self.now - 5 * DAY)
        return self.paypal.add_order(items=items or [("Ceramic mug set", 1, cents)], **kw)

    def ask(self, order_id, cents, category="damaged", customer="", note="", request_id=None):
        self._req += 1
        return self.guard.request_refund(request_id=request_id or "req-%d" % self._req, order_id=order_id,
                                         amount_cents=cents, category=category, customer_text=customer,
                                         agent_note=note)


@pytest.fixture
def world():
    return World()
