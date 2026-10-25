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
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q          # 72 tests, offline: simulated PayPal, stand-in models, a fake GenLayer
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

### The web app

`web/` is the site judges and visitors use: the pitch, the live demo (chat
with the shop's agent beside the Remit console, where each refund request
appears as a decision card with PayPal's records, the code checks, each
model's vote, and PayPal's refund id or the reason), the decision log with
its verification, and how to connect your own agent. Remit's design system,
light and dark, phone and desktop.

```bash
cd web && npm install && npm run build && cd ..
REMIT_OFFLINE=1 REMIT_STATIC_DIR=web/dist .venv/bin/uvicorn remit_paypal.web:app --port 8000
# open http://127.0.0.1:8000

cd web && node scripts/e2e.mjs http://127.0.0.1:8000   # a real browser through every demo case, phone layout, dark theme
```

In offline mode each visitor gets their own fresh set of the demo shop's
orders. For a public demo, use a mandate whose daily cap fits the expected
traffic: the cap is the shop's, shared by every customer.

### The log, anchored on GenLayer

Remit on PayPal builds on Remit on GenLayer: PayPal moves the money; GenLayer
makes the record independently checkable. After each decision the log's
newest hash is published to `RemitAnchor` (`contracts/remit_anchor.py`), a
deterministic Intelligent Contract on GenLayer Studio: only the operator
anchors, entry numbers strictly increase, and anyone can read it. Once a hash
is on chain, rewriting any earlier entry no longer matches it, even if every
later hash is rebuilt. Anchoring runs in the background and never holds up a
refund; if GenLayer is unavailable it queues and catches up.

| | |
| --- | --- |
| Contract | [`0xdA7921d968AA726a037a1464D1DfbF7c8D0A7B73`](https://explorer-studio.genlayer.com/address/0xdA7921d968AA726a037a1464D1DfbF7c8D0A7B73) on GenLayer Studio (`deploy/anchor-studio.json`) |
| A run | The browser test's 21 log entries, anchored in two transactions (entries 5 and 21); `verify_anchor.py` says they match. The same log with one early entry rewritten and every later hash rebuilt passes its own chain check, and `verify_anchor.py` says it does not match (`deploy/anchor-run-studio.json`) |

Check a server yourself, without trusting it or its page:

```bash
.venv/bin/python verify_anchor.py https://<remit server>
```

It downloads the log, recomputes every hash itself, reads the newest anchor
straight from GenLayer, and compares. Anchoring is on when the server has
`REMIT_ANCHOR_CONTRACT` and `REMIT_ANCHOR_KEY` (the operator's key, kept out
of the repository; `deploy/deploy_anchor.py` makes and funds one and deploys
the contract).

The anchor proves what the log said and when. It does not prove that every
decision was logged: an operator could leave one out before anchoring.
Remit on GenLayer, where the contract itself decides, is the version no
single party controls.
