"""The Remit MCP server: PayPal's tools for any agent, the money behind the
guard.

Read tools return what PayPal says about an order. The one tool that moves
money, ``request_refund``, runs the guard. There is no tool that refunds
without it, and the PayPal credentials stay in this process.

    python -m remit_paypal.mcp_server          # stdio, for Claude Desktop, Cursor, any MCP client
"""

import json

from mcp.server.mcpserver import MCPServer

from .engine import core
from .facts import cents, money

INSTRUCTIONS = (
    "You are connected to a shop's PayPal account through Remit. You can read orders, shipment tracking and "
    "disputes. You cannot refund directly: request_refund asks Remit, which reads PayPal's own records, applies "
    "the shop's limits and refund policy, and refunds only if they allow it. Report Remit's decision and reason "
    "to the customer as they are; do not promise a refund Remit has not made."
)


def _facts_view(f):
    return {
        "order_id": f.order_id,
        "customer": f.payer_name,
        "items": [{"name": n, "quantity": q, "unit_price": money(c, f.currency)} for n, q, c in f.items],
        "paid": money(f.captured_cents, f.currency),
        "already_refunded": money(f.refunded_cents, f.currency),
        "still_refundable": money(f.refundable_cents, f.currency),
    }


def create_server(guard, name="Remit", anchorer=None):
    server = MCPServer(name, instructions=INSTRUCTIONS)
    paypal = guard.paypal

    @server.tool(description="The order as PayPal records it: items, what was paid, what was already refunded.")
    def get_order(order_id: str) -> str:
        return json.dumps(_facts_view(paypal.facts(order_id)))

    @server.tool(description="Shipment tracking for the order, from PayPal: status (SHIPPED, DELIVERED, ...), carrier, last update.")
    def get_shipment_tracking(order_id: str) -> str:
        f = paypal.facts(order_id)
        return json.dumps({"order_id": f.order_id, "shipments": [
            {"status": s.status, "carrier": s.carrier, "updated_at": s.updated_at} for s in f.shipments]})

    @server.tool(description="How many PayPal disputes are open on the order's payment.")
    def list_disputes(order_id: str) -> str:
        f = paypal.facts(order_id)
        return json.dumps({"order_id": f.order_id, "open_disputes": f.open_disputes})

    @server.tool(description=(
        "Ask Remit to refund a customer. Remit reads the order from PayPal, applies the shop's limits and refund "
        "policy, and refunds through PayPal only if allowed. amount is a decimal string such as \"45.00\". "
        "request_id must be unique per request; reuse it only to look up the same request."))
    def request_refund(request_id: str, order_id: str, amount: str, reason: str, customer_message: str = "",
                       agent_note: str = "") -> str:
        try:
            amount_cents = cents(amount)
            if amount_cents <= 0:
                raise ValueError("the amount must be more than zero")
            d = guard.request_refund(request_id=request_id, order_id=order_id, amount_cents=amount_cents,
                                     category=reason, customer_text=customer_message, agent_note=agent_note)
        except (ValueError, core.RemitError) as exc:
            # A request the guard cannot take is refused, never raised: the agent
            # gets a decision it can read, and no money moves.
            return json.dumps({"request_id": request_id, "outcome": "refused", "reason": str(exc),
                               "decided_by": "code", "rules": ["request"], "panel": [], "paypal_refund_id": None})
        return json.dumps({
            "request_id": d.request_id,
            "outcome": "refunded" if d.outcome == "allowed" else "refused",
            "reason": d.reason,
            # Who decided: for an allowed refund, the panel if it was asked, else
            # code; PayPal only carries it out. For a refusal, the stage that stopped it.
            "decided_by": ("AI panel" if d.votes else "code") if d.outcome == "allowed" else
                          {"facts": "PayPal", "checks": "code", "engine": "code", "panel": "AI panel",
                           "paypal": "PayPal", "error": "code"}.get(d.stage, d.stage),
            "rules": d.rules,
            "panel": [{"model": v["model"], "verdict": v["verdict"], "confidence": v["confidence"]} for v in d.votes],
            "paypal_refund_id": d.refund_id or None,
        })

    @server.tool(description="A past refund decision and its log entries, by request_id.")
    def get_decision(request_id: str) -> str:
        row = guard.ledger.get(request_id)
        if row is None:
            return json.dumps({"request_id": request_id, "found": False})
        entries = guard.ledger.entries_for(request_id)
        for e in entries:
            e["body"].pop("prompt", None)
        covering = anchorer.anchor_covering(entries[-1]["seq"]) if anchorer is not None and entries else None
        return json.dumps({"found": True, **row, "log": entries, "genlayer_anchor": covering})

    return server


def main():
    from .config import build_guard  # noqa: I001

    from .config import build_anchorer

    guard = build_guard()
    anchorer = build_anchorer(guard.ledger)
    if anchorer is not None:
        anchorer.start()
    create_server(guard, anchorer=anchorer).run()


if __name__ == "__main__":
    main()
