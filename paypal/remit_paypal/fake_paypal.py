"""An in-memory PayPal with the response shapes the guard reads, for tests and
offline demos. Refunds honour ``PayPal-Request-Id``: the same request ID
returns the same refund and moves no more money."""

import itertools
from datetime import datetime, timezone

from .facts import from_paypal


def stamp(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def amount(value_cents, currency="USD"):
    return {"currency_code": currency, "value": "%d.%02d" % (value_cents // 100, value_cents % 100)}


class FakePayPal:
    def __init__(self):
        self.orders = {}
        self.trackers = {}  # capture id -> list
        self.disputes = {}  # capture id -> list
        self.refunds_by_request = {}
        self.refund_calls = 0
        self.fail_refund = None  # an exception to raise on the next refund
        self._ids = itertools.count(1)

    def add_order(self, *, payer_id, name, items, paid_at, currency="USD", delivered_at=None, shipped_at=None,
                  disputed=False):
        n = next(self._ids)
        order_id, capture_id = "ORDER-%04d" % n, "CAPTURE-%04d" % n
        total = sum(q * c for _, q, c in items)
        given, _, surname = name.partition(" ")
        self.orders[order_id] = {
            "id": order_id,
            "status": "COMPLETED",
            "payer": {"payer_id": payer_id, "name": {"given_name": given, "surname": surname}},
            "purchase_units": [{
                "amount": amount(total, currency),
                "items": [{"name": i, "quantity": str(q), "unit_amount": amount(c, currency)} for i, q, c in items],
                "payments": {
                    "captures": [{"id": capture_id, "status": "COMPLETED", "amount": amount(total, currency),
                                  "create_time": stamp(paid_at)}],
                    "refunds": [],
                },
            }],
        }
        trackers = []
        if shipped_at is not None:
            trackers.append({"transaction_id": capture_id, "status": "SHIPPED", "carrier": "UPS",
                             "last_updated_time": stamp(shipped_at)})
        if delivered_at is not None:
            trackers = [{"transaction_id": capture_id, "status": "DELIVERED", "carrier": "UPS",
                         "last_updated_time": stamp(delivered_at)}]
        self.trackers[capture_id] = trackers
        self.disputes[capture_id] = [{"dispute_id": "PP-D-%d" % n, "status": "OPEN"}] if disputed else []
        return order_id, capture_id

    def facts(self, order_id):
        if order_id not in self.orders:
            raise LookupError("RESOURCE_NOT_FOUND: order %s" % order_id)
        order = self.orders[order_id]
        capture_id = order["purchase_units"][0]["payments"]["captures"][0]["id"]
        return from_paypal(order, self.trackers[capture_id], self.disputes[capture_id])

    def refund(self, capture_id, amount_cents, currency, request_id, note=""):
        if request_id in self.refunds_by_request:
            return self.refunds_by_request[request_id]
        self.refund_calls += 1
        if self.fail_refund is not None:
            exc, self.fail_refund = self.fail_refund, None
            raise exc
        for order in self.orders.values():
            payments = order["purchase_units"][0]["payments"]
            if payments["captures"][0]["id"] == capture_id:
                refund = {"id": "REFUND-%04d" % next(self._ids), "status": "COMPLETED",
                          "amount": amount(amount_cents, currency), "note_to_payer": note,
                          "create_time": stamp(0)}
                payments["refunds"].append(refund)
                self.refunds_by_request[request_id] = refund
                return refund
        raise LookupError("RESOURCE_NOT_FOUND: capture %s" % capture_id)
