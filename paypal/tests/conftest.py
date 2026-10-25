import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from remit_paypal.fake_paypal import FakePayPal  # noqa: E402
from remit_paypal.guard import Guard, load_mandate  # noqa: E402
from remit_paypal.ledger import Ledger  # noqa: E402
from remit_paypal.panel import Panel  # noqa: E402
from remit_paypal.offline import answer, reader  # noqa: E402,F401

NOW = 1_793_000_000
DAY = 86400
MANDATE = os.path.join(os.path.dirname(HERE), "mandates", "demo-shop.json")


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


@pytest.fixture(autouse=True)
def _ledger_store(monkeypatch):
    """REMIT_TEST_DB=postgresql://... runs every test's ledger on Postgres,
    from empty tables, instead of SQLite in memory."""
    url = os.environ.get("REMIT_TEST_DB")
    if not url:
        yield
        return
    import psycopg

    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS log, refunds, anchors")
    monkeypatch.setattr(Ledger.__init__, "__defaults__", (url,))
    yield
