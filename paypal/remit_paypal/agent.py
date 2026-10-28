"""The shop's support agent. It reaches PayPal only through the Remit MCP
server, like any other agent, so the demo exercises the product's one path.

Two agents share one interface, ``await agent.reply(session, message)``:

- ``ToolAgent``: a model with tool calling over any OpenAI-compatible API.
- ``ScriptedAgent``: no model; reads the order and the reason from the
  message and asks Remit. For offline demos and tests.

Both report every tool call to ``emit`` so the console can show it, and both
let the server, not the model, choose each refund's ``request_id``.
"""

import asyncio
import json
import re

import httpx

from .models import retry_after, without_thinking

SHOP = "Kiln & Co."

SYSTEM = (
    "You are the customer support agent for %s, a small online shop that takes payment with PayPal. "
    "Help the customer with their order. You can look up orders, shipment tracking and disputes. "
    "Whenever a customer asks for money back, call request_refund with the order, the amount they ask for, "
    "a short reason (damaged, not_received, not_as_described, changed_mind, other) and their own words. "
    "Always call it, even when you expect a refusal: you never decide a refund yourself, in either "
    "direction. Remit decides, from PayPal's records and the shop's policy, and records every decision. "
    "You cannot refund any other way, and you must not promise a refund. Tell the customer Remit's decision "
    "and its reason plainly. Never claim someone approved anything. Keep replies short and kind." % SHOP
)

ORDER_RE = re.compile(r"\b(ORDER-\d{4,}|[A-Z0-9]{17})\b")
AMOUNT_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)|\b(\d+\.\d{2})\b")
REASONS = (
    ("not_received", ("never arrived", "never came", "didn't arrive", "did not arrive", "not received", "lost")),
    ("damaged", ("broken", "damaged", "smashed", "cracked", "defective", "shattered")),
    ("not_as_described", ("not as described", "wrong item", "different from")),
    ("changed_mind", ("changed my mind", "don't want", "do not want")),
)
WANTS_MONEY = ("refund", "money back", "reimburse", "return", "compensat") + tuple(w for _, ws in REASONS for w in ws)


KEEP_MESSAGES = 30  # the conversation sent to the model: the system prompt and the newest turns


def trim(messages, keep=KEEP_MESSAGES):
    """The system prompt and at most ``keep`` newest messages, starting at a
    customer's message, so a tool result is never sent without the call that
    asked for it."""
    if len(messages) <= keep + 1:
        return messages
    head, tail = messages[:1], messages[-keep:]
    while tail and tail[0].get("role") != "user":
        tail = tail[1:]
    return head + tail


class ToolFailed(Exception):
    """An MCP tool answered with an error instead of a result."""


class Session:
    def __init__(self, sid, orders):
        self.id, self.orders = sid, list(orders)
        self.messages = []  # the conversation, as chat messages
        self.customer_lines = []
        self.refunds = 0

    def next_request_id(self):
        self.refunds += 1
        return "%s-r%d" % (self.id, self.refunds)


def _reason(text):
    low = text.lower()
    for name, words in REASONS:
        if any(w in low for w in words):
            return name
    return "other"


class ScriptedAgent:
    """No model. Good enough to drive every demo case, and honest about it."""

    name = "scripted"

    def __init__(self, mcp, emit):
        self.mcp, self.emit = mcp, emit

    async def _tool(self, session, name, args):
        self.emit(session.id, {"type": "tool_call", "tool": name, "args": args})
        result = await self.mcp.call_tool(name, args)
        text = result.content[0].text if result.content else ""
        if result.is_error:
            self.emit(session.id, {"type": "error", "text": "%s failed: %s" % (name, text[:200])})
            raise ToolFailed(text)
        data = json.loads(text)
        self.emit(session.id, {"type": "tool_result", "tool": name, "result": data})
        return data

    async def reply(self, session, message):
        session.customer_lines.append(message)
        found = ORDER_RE.search(message.upper())
        order_id = found.group(1) if found else (session.orders[0] if len(session.orders) == 1 else None)
        if order_id is None:
            return "Which order is this about? Your orders: %s." % ", ".join(session.orders)
        if order_id not in session.orders:
            return "I can only help with your own orders: %s." % ", ".join(session.orders)
        if not any(w in message.lower() for w in WANTS_MONEY):
            o = await self._tool(session, "get_order", {"order_id": order_id})
            t = await self._tool(session, "get_shipment_tracking", {"order_id": order_id})
            ship = t["shipments"][0]["status"].lower() if t["shipments"] else "not shipped yet"
            return "Order %s: %s, paid %s. Shipping: %s." % (
                order_id, ", ".join(i["name"] for i in o["items"]), o["paid"], ship)
        o = await self._tool(session, "get_order", {"order_id": order_id})
        if o["still_refundable"].endswith(" 0.00"):
            return "Order %s has already been refunded in full (%s)." % (order_id, o["already_refunded"])
        m = AMOUNT_RE.search(message)
        amount = (m.group(1) or m.group(2)) if m else o["still_refundable"].split()[-1]
        d = await self._tool(session, "request_refund", {
            "request_id": session.next_request_id(), "order_id": order_id, "amount": "%.2f" % float(amount),
            "reason": _reason(message), "customer_message": "\n".join(session.customer_lines[-5:]),
            "agent_note": "Customer asked for %s back on %s." % (amount, order_id)})
        if d["outcome"] == "refunded":
            return "Done: Remit approved it and PayPal refunded %s to you (refund %s)." % (
                "%.2f" % float(amount), d["paypal_refund_id"])
        return "I'm sorry, I can't refund this: %s. A person on our team can review it." % d["reason"]


class ToolAgent:
    """A model that calls the Remit MCP server's tools."""

    name = "model"

    def __init__(self, mcp, emit, model, api_key, base_url, transport=None, max_steps=6):
        self.mcp, self.emit, self.model, self.max_steps = mcp, emit, model, max_steps
        self.http = httpx.AsyncClient(base_url=base_url, timeout=60, transport=transport,
                                      headers={"Authorization": "Bearer " + api_key})
        self._tools = None

    async def tools(self):
        if self._tools is None:
            listed = (await self.mcp.list_tools()).tools
            self._tools = [{"type": "function", "function": {
                "name": t.name, "description": t.description or "", "parameters": t.input_schema}} for t in listed]
        return self._tools

    async def reply(self, session, message):
        session.customer_lines.append(message)
        if not session.messages:
            session.messages.append({"role": "system", "content": SYSTEM + " The customer's orders: %s." % (
                ", ".join(session.orders))})
        session.messages.append({"role": "user", "content": message})
        session.messages = trim(session.messages)
        for _ in range(self.max_steps):
            body = {"model": self.model, "temperature": 0, "messages": session.messages, "tools": await self.tools()}
            r = await self.http.post("/chat/completions", json=body)
            for _ in range(2):  # rate limited: wait as asked, twice at most
                wait = retry_after(r)
                if wait is None:
                    break
                await asyncio.sleep(wait)
                r = await self.http.post("/chat/completions", json=body)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            if isinstance(msg.get("content"), str):
                msg["content"] = without_thinking(msg["content"])  # the customer sees the answer, not the reasoning
            calls = msg.get("tool_calls") or []
            session.messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
            if not calls:
                return msg.get("content") or ""
            for call in calls:
                session.messages.append({"role": "tool", "tool_call_id": call["id"],
                                         "content": await self._run(session, call)})
        return "I'm sorry, I couldn't finish that. A person on our team will follow up."

    async def _run(self, session, call):
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
        except ValueError:
            return json.dumps({"error": "arguments were not valid JSON"})
        if args.get("order_id") and args["order_id"] not in session.orders:
            return json.dumps({"error": "that order does not belong to this customer"})
        if name == "request_refund":
            if isinstance(args.get("amount"), (int, float)) and not isinstance(args["amount"], bool):
                args["amount"] = "%.2f" % args["amount"]  # the tool takes a decimal string; models often send a number
            args["request_id"] = session.next_request_id()  # the server chooses, never the model
            args["customer_message"] = "\n".join(session.customer_lines[-5:])  # the customer's own words
        self.emit(session.id, {"type": "tool_call", "tool": name, "args": args})
        try:
            result = await self.mcp.call_tool(name, args)
            text = result.content[0].text if result.content else ""
            if result.is_error:
                text = json.dumps({"error": text[:500]})
        except Exception as exc:
            text = json.dumps({"error": str(exc)})
        try:
            self.emit(session.id, {"type": "tool_result", "tool": name, "result": json.loads(text)})
        except ValueError:
            self.emit(session.id, {"type": "tool_result", "tool": name, "result": {"text": text}})
        return text
