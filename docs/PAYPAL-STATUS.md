# Remit for PayPal: status for review

Branch `paypal`. Live at https://remit-paypal.onrender.com. `GET /api/health`
names the commit running (`build`), so a reviewer can tie what they see to
the code.

## What runs today

- **PayPal sandbox, for real.** Each visitor gets three orders created in the
  PayPal sandbox (paid by a sandbox test card and captured, with UPS tracking
  added through PayPal's tracking API), taken from a small pool that is made
  ahead of time. Refunds go to `POST /v2/payments/captures/{id}/refund` with
  the request id as `PayPal-Request-Id`. Live PayPal hosts are refused in code.
- **Real models, through Groq.** The support agent is `openai/gpt-oss-120b`;
  the panel is `qwen/qwen3.8-27b` and `openai/gpt-oss-20b`. Both must say yes
  (quorum 2 of 2); any confident no refuses; an error, a timeout or a doubt
  counts as unsure, and unsure refuses.
- **One way in.** The agent holds no PayPal credentials and no refund tool. It
  reaches PayPal only through Remit's MCP server (`get_order`,
  `get_shipment_tracking`, `list_disputes`, `request_refund`, `get_decision`).
  PayPal's Agent Toolkit is not used; nothing claims it is.
- **The log, anchored on GenLayer.** Every step is in a hash-chained log
  (Postgres on Neon). Its newest hash is published to a `RemitAnchor` contract
  on GenLayer Studio after each decision.

## Evidence

- `paypal/deploy/sandbox-run.json`: the three money cases on the hosted demo,
  with PayPal order ids, the PayPal refund id, each model's vote, and PayPal's
  record afterwards.
- `paypal/web/scripts/e2e.mjs https://remit-paypal.onrender.com`: a real
  browser through the hosted demo. It reads the mode from `/api/health` and
  checks outcomes and PayPal's record, not model wording.
- `paypal/verify_anchor.py https://remit-paypal.onrender.com <contract>`:
  downloads the log page by page, recomputes every hash itself, reads the
  anchor from GenLayer, and compares. The contract is on the Log page.
- `paypal/sandbox_check.py`: the same three cases from a terminal, with your
  own sandbox and model keys.
- Tests: 106 Python tests (SQLite; also run on Postgres with `REMIT_TEST_DB`).
  Failure paths are in `tests/test_hardening.py`.

## Decisions a reviewer should know about

- **Fail closed, including on doubt about money.** A refund call that times
  out or gets a 5xx is recorded as `unknown` and counts against the caps, as
  does a decision a crash cut off. Only a refund PayPal declined (a 4xx)
  counts as nothing moved.
- **The operator is trusted.** Whoever runs the server holds the PayPal and
  model keys and runs the panel. The log makes decisions checkable after the
  fact; the anchor proves what the log said and when, not that every request
  was logged. Remit on GenLayer, where the contract decides, is the version
  no single party controls.
- **The agent follows instructions, not code, in one place.** It is told to
  pass every refund request to Remit and never decide one itself. If a model
  ignores that and refuses on its own, no money moves, but that refusal is not
  in the log. A refund can only ever happen through Remit.
- **Card payments have no PayPal payer id.** The customer is the shop's own
  reference that PayPal recorded on the order (`custom_id`), which the split
  rule groups refunds by.
- **The disputed-order case is offline only.** A merchant cannot open a
  dispute in the sandbox.
- **Free hosting.** Render's free tier sleeps after about 15 idle minutes; the
  first visit after that takes up to a minute. One worker; visitor sessions
  live in memory and end on a restart. Groq's free tier limits tokens per
  minute per model; Remit waits and retries when asked, then refuses.
