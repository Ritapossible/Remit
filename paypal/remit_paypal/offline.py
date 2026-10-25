"""Offline mode: a fake PayPal holding the demo shop's orders, and stand-in
models that apply the demo policy plainly. For trying Remit without keys,
and for tests. Never used when PayPal credentials are configured."""

import json
import secrets
import time

from .fake_paypal import FakePayPal

DAY = 86400


def answer(verdict, confidence=90, reason="matches_rule"):
    return json.dumps({"verdict": verdict, "reason": reason, "confidence": confidence})


def reader(prompt):
    """Reads only the PayPal records and the request, never the untrusted
    block, and applies the demo policy plainly."""
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


def offline_models():
    return {"stand-in-a": reader, "stand-in-b": reader, "stand-in-c": reader}


def demo_orders(p, now=None):
    """Add one fresh set of the demo shop's orders, one per case in the plan,
    and return their ids. Each visitor gets their own set, so one visitor's
    refund never changes another's demo."""
    now = int(now if now is not None else time.time())
    # Each set's customers are its own, so one visitor's refunds never count
    # against another's. The log outlives the server (a restart empties this
    # fake PayPal but not the database), so the ids are random, never a count.
    n = secrets.token_hex(4)
    who = lambda name: "DEMO-%s-%s" % (name, n)  # noqa: E731
    return [
        p.add_order(payer_id=who("ADA"), name="Ada Obi", items=[("Ceramic mug set", 1, 4500)],
                    paid_at=now - 5 * DAY, delivered_at=now - 2 * DAY)[0],          # damaged, refundable
        p.add_order(payer_id=who("BEN"), name="Ben Cole", items=[("Wireless earbuds", 1, 4500)],
                    paid_at=now - 12 * DAY, delivered_at=now - 9 * DAY)[0],         # "never arrived", delivered
        p.add_order(payer_id=who("CHI"), name="Chi Eze", items=[("Desk lamp", 1, 12000)],
                    paid_at=now - 3 * DAY, delivered_at=now - DAY)[0],              # split refunds
        p.add_order(payer_id=who("DAN"), name="Dan Roe", items=[("Wool scarf", 1, 4500)],
                    paid_at=now - 6 * DAY, delivered_at=now - 3 * DAY, disputed=True)[0],  # open dispute
    ]


def offline_paypal(now=None):
    """A fake PayPal holding one set of the demo orders (ORDER-0001 to 0004)."""
    p = FakePayPal()
    demo_orders(p, now)
    return p
