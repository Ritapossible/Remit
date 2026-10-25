"""The web server: chat with the shop's support agent, watch every step in a
live console, and read the decision log.

    POST /api/session            a visitor session: its id and its orders
    POST /api/chat               {session_id, message} -> the agent's reply
    GET  /api/orders?session_id  the visitor's orders, as PayPal records them
    GET  /api/events?session_id  server-sent events: tool calls, results, decisions
    GET  /api/log?since=N        the hash-chained log, and whether it verifies
    GET  /api/decisions/{id}     one decision, its log entries, and the GenLayer anchor covering it
    GET  /api/anchor             the log's anchor on GenLayer, checked against GenLayer itself
    GET  /api/health

The agent talks to PayPal only through the Remit MCP server, connected
in-process. Run: ``uvicorn remit_paypal.web:app`` (configured from the
environment, see ``config.py``).
"""

import asyncio
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from mcp import Client
from pydantic import BaseModel, Field

from .agent import ScriptedAgent, Session, ToolAgent
from .facts import money
from .mcp_server import create_server

MAX_MESSAGE = 1000


class Bus:
    """Per-session event fan-out to any number of server-sent-event streams,
    with a short replay buffer for a stream that connects late."""

    def __init__(self, keep=200):
        self.keep = keep
        self.history = defaultdict(lambda: deque(maxlen=keep))
        self.queues = defaultdict(set)
        self.lock = threading.Lock()
        self.seq = 0

    def emit(self, sid, event):
        with self.lock:
            self.seq += 1
            event = {"id": self.seq, "at": int(time.time()), **event}
            self.history[sid].append(event)
            queues = list(self.queues[sid])
        for q, loop in queues:
            loop.call_soon_threadsafe(q.put_nowait, event)

    def subscribe(self, sid):
        q, loop = asyncio.Queue(), asyncio.get_running_loop()
        with self.lock:
            self.queues[sid].add((q, loop))
            backlog = list(self.history[sid])
        return q, loop, backlog

    def unsubscribe(self, sid, q, loop):
        with self.lock:
            self.queues[sid].discard((q, loop))


class Limiter:
    """A sliding window per key: at most ``n`` calls in ``seconds``."""

    def __init__(self, n, seconds):
        self.n, self.seconds, self.calls = n, seconds, defaultdict(deque)

    def allow(self, key, now=None):
        now = now if now is not None else time.time()
        q = self.calls[key]
        while q and now - q[0] > self.seconds:
            q.popleft()
        if len(q) >= self.n:
            return False
        q.append(now)
        return True


class ChatIn(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)


def create_app(guard, *, orders_for, agent_kind="scripted", model=None, api_key="", base_url="",
               transport=None, chat_per_minute=12, chats_per_day=2000, sessions_per_hour=30, static_dir=None,
               anchorer=None):
    """``orders_for(session_id)`` gives a new visitor their orders."""
    bus, sessions = Bus(), {}
    per_ip, daily = Limiter(chat_per_minute, 60), Limiter(chats_per_day, 86400)
    new_per_ip = Limiter(sessions_per_hour, 3600)  # in the sandbox, each new session creates real orders
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        if anchorer is not None:
            anchorer.start()
        try:
            async with Client(create_server(guard, anchorer=anchorer)) as mcp:
                if agent_kind == "model":
                    state["agent"] = ToolAgent(mcp, bus.emit, model, api_key, base_url, transport=transport)
                else:
                    state["agent"] = ScriptedAgent(mcp, bus.emit)
                yield
        finally:
            if anchorer is not None:
                anchorer.stop()

    app = FastAPI(title="Remit on PayPal", lifespan=lifespan)

    def session(sid):
        s = sessions.get(sid)
        if s is None:
            raise HTTPException(404, "unknown session")
        return s

    @app.get("/api/health")
    def health():
        ok, broken = guard.ledger.verify()
        from .fake_paypal import FakePayPal

        mode = "offline" if isinstance(guard.paypal, FakePayPal) else "sandbox"
        return {"ok": True, "mode": mode, "agent": state["agent"].name, "log_verifies": ok, "log_broken_at": broken}

    @app.post("/api/session")
    def new_session(request: Request):
        if not new_per_ip.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(429, "Too many new sessions; wait a while and try again.")
        sid = secrets.token_hex(6)
        try:
            orders = orders_for(sid)
        except Exception as exc:
            raise HTTPException(503, "The demo shop could not set up your orders: %s" % type(exc).__name__)
        sessions[sid] = Session(sid, orders)
        return {"session_id": sid, "orders": sessions[sid].orders, "shop": "Kiln & Co."}

    @app.get("/api/orders")
    def orders(session_id: str):
        """The visitor's orders as PayPal records them, for the order list."""
        out = []
        for oid in session(session_id).orders:
            try:
                f = guard.paypal.facts(oid)
            except Exception:
                continue
            ship = f.shipments[-1] if f.shipments else None
            out.append({
                "order_id": f.order_id,
                "items": [{"name": n, "quantity": q} for n, q, _ in f.items],
                "paid": money(f.captured_cents, f.currency),
                "refunded": money(f.refunded_cents, f.currency),
                "refundable": money(f.refundable_cents, f.currency),
                "paid_at": f.captured_at,
                "shipping": {"status": ship.status, "carrier": ship.carrier, "updated_at": ship.updated_at} if ship else None,
                "open_disputes": f.open_disputes,
            })
        return out

    @app.post("/api/chat")
    async def chat(body: ChatIn, request: Request):
        s = session(body.session_id)
        ip = request.client.host if request.client else "unknown"
        if not per_ip.allow(ip) or not daily.allow("all"):
            raise HTTPException(429, "Too many messages; wait a minute and try again.")
        bus.emit(s.id, {"type": "customer", "text": body.message})
        try:
            text = await state["agent"].reply(s, body.message)
        except Exception as exc:  # the agent failed: say so, move no money
            bus.emit(s.id, {"type": "error", "text": "the agent failed: %s" % type(exc).__name__})
            text = "Sorry, something went wrong on our side. No refund was made; please try again."
        bus.emit(s.id, {"type": "agent", "text": text})
        if anchorer is not None:
            anchorer.notify()  # never waited on: anchoring is off the refund path
        return {"reply": text}

    @app.get("/api/events")
    async def events(session_id: str, request: Request):
        session(session_id)
        q, loop, backlog = bus.subscribe(session_id)

        async def stream():
            try:
                for e in backlog:
                    yield "data: %s\n\n" % json.dumps(e)
                while not await request.is_disconnected():
                    try:
                        e = await asyncio.wait_for(q.get(), timeout=15)
                        yield "data: %s\n\n" % json.dumps(e)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                bus.unsubscribe(session_id, q, loop)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/events/recent")
    def recent(session_id: str):
        session(session_id)
        return list(bus.history[session_id])

    @app.get("/api/log")
    def log(since: int = 0):
        ok, broken = guard.ledger.verify()
        return {"verifies": ok, "broken_at": broken, "entries": guard.ledger.entries(since)}

    @app.get("/api/decisions/{request_id}")
    def decision(request_id: str):
        row = guard.ledger.get(request_id)
        if row is None:
            raise HTTPException(404, "unknown request")
        log = [e for e in guard.ledger.entries() if e["body"].get("request_id") == request_id]
        covering = anchorer.anchor_covering(log[-1]["seq"]) if anchorer is not None and log else None
        return {**row, "log": log, "anchor": covering}

    @app.get("/api/anchor")
    def anchor():
        if anchorer is None:
            return {"configured": False}
        return {"configured": True, **anchorer.status()}

    if static_dir and os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


def app_from_env(env=os.environ):
    from .config import build_guard

    guard = build_guard(env)
    if env.get("REMIT_OFFLINE") == "1":
        from .offline import demo_orders

        orders_for = lambda sid: demo_orders(guard.paypal)  # noqa: E731  each visitor gets fresh orders
    else:
        from .sandbox_shop import card_from, demo_orders

        card = card_from(env.get("REMIT_SANDBOX_CARD", ""))
        orders_for = lambda sid: demo_orders(guard.paypal, card)  # noqa: E731  each visitor: fresh sandbox orders
    kind = "model" if env.get("REMIT_AGENT_MODEL") else "scripted"
    from .config import build_anchorer

    anchorer = build_anchorer(guard.ledger, env)
    return create_app(guard, orders_for=orders_for, agent_kind=kind, model=env.get("REMIT_AGENT_MODEL"),
                      api_key=env.get("REMIT_MODEL_API_KEY", ""),
                      base_url=env.get("REMIT_MODEL_BASE_URL", "https://openrouter.ai/api/v1"),
                      static_dir=env.get("REMIT_STATIC_DIR"), anchorer=anchorer)


def __getattr__(name):  # ``uvicorn remit_paypal.web:app`` builds the app on first use
    if name == "app":
        globals()["app"] = app_from_env()
        return globals()["app"]
    raise AttributeError(name)
