"""What PayPal says about one capture, read from PayPal's own APIs.

Every field here comes from a PayPal response the guard fetched itself.
Nothing the customer or the agent wrote reaches this module.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


def payer_address(payer_id):
    """The engine names recipients by ``0x`` hex strings. A PayPal payer ID
    maps to one by a fixed hash, so the same customer is the same recipient
    in every window. The log keeps both."""
    return "0x" + hashlib.sha256(str(payer_id).encode("utf-8")).hexdigest()[:40]


def cents(value):
    """PayPal amounts are decimal strings ("45.00"). Parsed exactly into
    integer cents; anything else is refused rather than rounded."""
    text = str(value).strip()
    if text.startswith("-") or not text:
        raise ValueError("not an amount: %r" % value)
    whole, _, frac = text.partition(".")
    if not whole.isdigit() or (frac and not frac.isdigit()) or len(frac) > 2:
        raise ValueError("not an amount: %r" % value)
    return int(whole) * 100 + int((frac + "00")[:2])


def epoch(stamp):
    """An RFC 3339 time from PayPal, as Unix seconds. A time that cannot be
    read is an error that names it, never a guess."""
    text = str(stamp).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("unreadable time from PayPal: %r" % (stamp,)) from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


@dataclass(frozen=True)
class Shipment:
    status: str  # SHIPPED, DELIVERED, ON_HOLD, CANCELLED, LOCAL_PICKUP
    carrier: str
    updated_at: int


@dataclass(frozen=True)
class Facts:
    order_id: str
    capture_id: str
    payer_id: str
    payer_name: str
    currency: str
    items: tuple  # (name, quantity, unit cents)
    captured_cents: int
    refunded_cents: int
    captured_at: int
    shipments: tuple = field(default_factory=tuple)
    open_disputes: int = 0

    @property
    def recipient(self):
        return payer_address(self.payer_id)

    @property
    def refundable_cents(self):
        return self.captured_cents - self.refunded_cents

    @property
    def delivered(self):
        return any(s.status == "DELIVERED" for s in self.shipments)

    def lines(self, now):
        """The facts as the panel reads them: plain statements, PayPal as
        their source."""
        out = [
            "Order %s, paid by customer %s (PayPal payer %s)." % (self.order_id, self.payer_name, self.payer_id),
            "Items: " + "; ".join("%s x%d at %s" % (n, q, money(c, self.currency)) for n, q, c in self.items) + ".",
            "Captured %s on %s (%d days ago)." % (
                money(self.captured_cents, self.currency), day(self.captured_at), (now - self.captured_at) // 86400),
            "Already refunded: %s. Still refundable: %s." % (
                money(self.refunded_cents, self.currency), money(self.refundable_cents, self.currency)),
        ]
        if not self.shipments:
            out.append("Shipment tracking: none recorded.")
        for s in self.shipments:
            out.append("Shipment tracking: %s by %s, last updated %s (%d days ago)." % (
                s.status, s.carrier or "an unnamed carrier", day(s.updated_at), (now - s.updated_at) // 86400))
        out.append("Open disputes on this payment: %d." % self.open_disputes)
        return out


def money(value_cents, currency):
    return "%s %d.%02d" % (currency, value_cents // 100, value_cents % 100)


def day(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %B %Y")


def from_paypal(order, trackers, disputes):
    """Build the facts from PayPal's responses: the order (``GET
    /v2/checkout/orders/{id}``), its trackers (``GET /v1/shipping/trackers``)
    and disputes on its capture (``GET /v1/customer/disputes``). An order
    with anything but exactly one completed capture is refused: a refund
    must name the one payment it reverses."""
    unit = order["purchase_units"][0]
    payments = unit.get("payments", {})
    captures = [c for c in payments.get("captures", []) if c.get("status") in ("COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED")]
    if len(captures) != 1:
        raise ValueError("order %s has %d settled captures; expected exactly one" % (order.get("id"), len(captures)))
    capture = captures[0]
    currency = capture["amount"]["currency_code"]
    refunded = sum(cents(r["amount"]["value"]) for r in payments.get("refunds", [])
                   if r.get("status") in ("COMPLETED", "PENDING"))
    payer = order.get("payer", {})
    name = payer.get("name", {})
    card = order.get("payment_source", {}).get("card", {})
    # A PayPal account payment names its payer. A card payment has no payer
    # id; the customer is the shop's own reference PayPal recorded on the
    # order at payment time (custom_id), never anything said at refund time.
    payer_id = payer.get("payer_id") or ("customer:" + unit["custom_id"] if unit.get("custom_id") else "")
    items = tuple((i["name"], int(i.get("quantity", 1)), cents(i["unit_amount"]["value"])) for i in unit.get("items", []))
    shipments = tuple(
        Shipment(status=str(t.get("status", "")).upper(), carrier=str(t.get("carrier", "")),
                 updated_at=epoch(t.get("last_updated_time") or t.get("create_time") or capture["create_time"]))
        for t in trackers
    )
    open_states = ("OPEN", "WAITING_FOR_BUYER_RESPONSE", "WAITING_FOR_SELLER_RESPONSE", "UNDER_REVIEW")
    return Facts(
        order_id=order["id"],
        capture_id=capture["id"],
        payer_id=payer_id,
        payer_name=(" ".join(p for p in (name.get("given_name"), name.get("surname")) if p)) or card.get("name") or "unknown",
        currency=currency,
        items=items,
        captured_cents=cents(capture["amount"]["value"]),
        refunded_cents=refunded,
        captured_at=epoch(capture["create_time"]),
        shipments=shipments,
        open_disputes=sum(1 for d in disputes if d.get("status") in open_states),
    )
