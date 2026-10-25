"""The demo shop in the PayPal sandbox: real orders, paid by a sandbox test
card and captured, with real shipment tracking. Each visitor gets their own
set, so one visitor's refunds never change another's demo.

The offline shop (``offline.py``) has a fourth case, an open dispute; the
sandbox cannot open a dispute from the merchant's side, so it is offline only.
"""

import secrets

# A sandbox test card. PayPal's sandbox accepts its published test numbers;
# REMIT_SANDBOX_CARD=number,YYYY-MM overrides it.
TEST_CARD = {"number": "4111111111111111", "expiry": "2030-12", "security_code": "123"}

CASES = [  # (customer, items, shipment status): one per demo case
    ("Ada Obi", [("Ceramic mug set", 1, 4500)], "DELIVERED"),   # arrived broken: refundable
    ("Ben Cole", [("Wireless earbuds", 1, 4500)], "DELIVERED"),  # "never arrived", but delivered
    ("Chi Eze", [("Desk lamp", 1, 12000)], "DELIVERED"),         # split refunds; the $900 injection
]


def card_from(env_value):
    if not env_value:
        return dict(TEST_CARD)
    number, _, expiry = env_value.partition(",")
    return {"number": number.strip(), "expiry": expiry.strip() or TEST_CARD["expiry"],
            "security_code": TEST_CARD["security_code"]}


def demo_orders(paypal, card=None, currency="USD"):
    """Create one visitor's orders in the sandbox and return their ids."""
    card = card or dict(TEST_CARD)
    token = secrets.token_hex(4)
    ids = []
    for i, (name, items, status) in enumerate(CASES):
        customer = "%s-%s" % (name.split()[0].upper(), token)
        order_id, capture_id = paypal.create_paid_order(
            customer_id=customer, items=items, currency=currency, card=dict(card, name=name),
            request_id="remit-demo-%s-%d" % (token, i))
        paypal.add_tracker(capture_id, status=status, carrier="UPS",
                           tracking_number="1Z%s%02d" % (token.upper(), i))
        ids.append(order_id)
    return ids
