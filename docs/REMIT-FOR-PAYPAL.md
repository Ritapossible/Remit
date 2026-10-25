# Remit for PayPal

Remit for PayPal brings Remit's spending policy to PayPal. Merchants put AI
agents on customer support, and those agents can issue refunds. A customer can
talk one into a refund it should not give: by prompt injection, by a story
PayPal's own records contradict, or by asking for one large refund in small
pieces. Remit for PayPal is the step between the agent and PayPal's refund.

**[Open Remit for PayPal](https://remit-paypal.onrender.com)** to try it: chat
with a demo shop's support agent, try to talk it into a refund, and watch every
decision in a live console. It runs on the PayPal sandbox; no real money moves.

## How a refund is decided

The agent never refunds. It asks Remit, and Remit:

1. Reads the facts from PayPal: the order, the capture, earlier refunds,
   shipment tracking and open disputes. Nothing the customer or the agent
   writes is treated as a fact.
2. Runs the checks code can decide: per-refund and daily caps, what is still
   refundable, open disputes, blocked customers.
3. Asks a panel of AI models only when a rule needs judgment, such as whether
   the refund fits the merchant's policy. The panel fails closed: a model that
   errors, hesitates or disagrees is a no.
4. Only then asks PayPal to refund, once, with the request's id as PayPal's
   idempotency key.
5. Writes every step to a hash-chained log.

## What it shares with Remit on GenLayer

Remit for PayPal is built on this project, not beside it.

- **The same engine.** The limit checks are Remit's own engine
  (`contracts/remit_core.py`), imported unchanged.
- **The same mandate.** Caps and rules are written in the
  [mandate format](MANDATE-FORMAT.md), with a PayPal section for the refund
  policy in plain language.
- **The log is anchored on GenLayer.** After each decision, the log's newest
  hash is published to an Intelligent Contract on GenLayer. Once a hash is on
  chain, rewriting any earlier entry no longer matches it, and anyone can check
  a server's log against GenLayer without trusting the server.

The difference is where the decision lives. In Remit on GenLayer, the contract
itself decides, and no single party controls it. In Remit for PayPal, the
merchant's Remit server decides and PayPal moves the money; GenLayer makes the
record independently checkable.

## Connect your own agent

Remit for PayPal is an MCP server. Claude Desktop, Cursor or your own agent
connects to it and gets PayPal's tools: `get_order`, `get_shipment_tracking`,
`list_disputes`, `request_refund` and `get_decision`. There is no tool that
refunds without the guard.

The code, setup and tests are in the
[`paypal` folder on the `paypal` branch](https://github.com/Ritapossible/Remit/tree/paypal/paypal).
