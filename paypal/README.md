# Remit on PayPal

A spending policy for AI agents' PayPal tools. The plan is
[docs/PAYPAL-PLAN.md](../docs/PAYPAL-PLAN.md).

The agent never refunds. It asks the guard (`remit_paypal/guard.py`):

1. Facts are read from PayPal (order, capture, refunds, tracking, disputes).
2. Checks code can decide run next, then Remit's engine
   (`contracts/remit_core.py`, imported unchanged).
3. The panel of AI models is asked only when a judgment rule fires, and
   fails closed.
4. Only then does PayPal refund, with the request ID as its idempotency key.
5. Every step is written to a hash-chained log.

```bash
cd paypal
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q          # 49 tests, offline: simulated PayPal and stand-in models
```

### The MCP server

Any MCP client (Claude Desktop, Cursor, an agent framework) can use Remit's
tools: `get_order`, `get_shipment_tracking`, `list_disputes`,
`request_refund` (guarded) and `get_decision`. There is no tool that refunds
without the guard.

```bash
REMIT_OFFLINE=1 .venv/bin/python -m remit_paypal.mcp_server     # try it without keys: the demo shop's orders
```

With a PayPal sandbox app and a model key (see `remit_paypal/config.py`):

```bash
PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=... REMIT_MODEL_API_KEY=... \
  .venv/bin/python -m remit_paypal.mcp_server
```

### The web server

Chat with the shop's support agent, watch every step in a live console, and
read the decision log. The agent reaches PayPal only through the Remit MCP
server, like any other agent.

```bash
REMIT_OFFLINE=1 .venv/bin/uvicorn remit_paypal.web:app --port 8000   # the demo shop, no keys
```

| Endpoint | What it does |
| --- | --- |
| `POST /api/session` | A visitor session: its id and its orders |
| `POST /api/chat` | `{session_id, message}`, returns the agent's reply |
| `GET /api/events?session_id=` | Server-sent events: the customer's messages, each tool call and result, the agent's replies |
| `GET /api/log?since=` | The hash-chained log, and whether it verifies |
| `GET /api/decisions/{request_id}` | One decision and its log entries |

`REMIT_AGENT_MODEL` set (with `REMIT_MODEL_API_KEY`) runs a model with tool
calling as the agent; unset, a scripted agent with no model drives the same
tools. The server, never the model, chooses each refund's request id, passes
the customer's own words to Remit, and refuses any order that is not the
visitor's. Chat is rate-limited per visitor and per day.
