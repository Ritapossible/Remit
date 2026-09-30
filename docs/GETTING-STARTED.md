# Getting started

Remit is a spending gate for AI agents. You write a **mandate**; Remit checks
every payment your agent requests against it and returns one answer per spend —
**authorized**, **refused**, or **pending** while a jury decides.

This guide walks the whole flow in the app on GenLayer Studio. It takes about
five minutes and needs no wallet.

## 1. Get a key

Open the app and choose **Use a Studio burner**. The app generates a key in your
browser and funds it from Studio's faucet.

A burner is for Studio only. Its GEN has no value, and the key is kept in your
browser's local storage in plain text — never use it for anything else. On the
testnet, connect MetaMask instead.

## 2. Create a guard

Go to **New guard**.

- **Agent address** — the only key that will be able to request spends. For a
  first run, choose **Use my address**: you will be both the principal (you
  deployed it) and the agent, so you can try every action.
- **Template** — *Campaign spend* catches purchases split to dodge a per-payment
  cap. *Contractor payouts* requires an invoice before a larger payout clears.
- **Max tier** — the most authority you grant. Tier 0 records refusals without
  withholding anything.
- **Shadow mode** — run with no authority at all and read the docket first.

The checks panel validates the mandate in your browser with the same rules the
contract applies at deployment. Deploy when it says the mandate is valid.

## 3. Request spends

Go to **Request a spend**. As you type, the panel on the right asks the contract
what it *would* do — a free view that runs the contract's own classifier.

With the campaign template, try:

| Spend | What happens |
| --- | --- |
| 0.15 GEN to a listed vendor | **Authorized** in the same transaction. No jury. |
| 0.25 GEN | **Refused** by the per-payment cap. No jury. |
| A second 0.15 GEN | **Authorized.** Every threshold still passes. |
| A third 0.15 GEN within the hour | **Held for the jury.** Every arithmetic limit passes — the only question left is whether three payments are one purchase split to stay under the cap. |

## 4. Commit evidence

Open the held case. As the agent, paste a URL to the invoice or order, choose
**Compute digest**, then **Commit**. The digest pins the exact bytes: validators
fetch the same URL and hash it themselves, and a document that has changed lands
as *unverified*.

Try the reference invoice:

```
https://raw.githubusercontent.com/Ritapossible/Remit/main/examples/invoice-INV-88.json
```

**Verify it yourself** re-hashes the document in your browser.

## 5. Convene the jury

Choose **Adjudicate**. Validators read the mandate rule, the payment history the
contract recorded, and the evidence — then each answers the same question
independently.

If no evidence was committed, the button stays disabled until the agent's
response window has passed: an agent can never lose a case for not using a
window it never had.

Three outcomes are possible, and the app tells them apart:

- **Done** — validators agreed; the verdict is recorded.
- **The contract refused this** — validators agreed on a refusal; nothing
  changed.
- **No consensus** — validators disagreed; the change was rolled back. It is
  safe to try again.

## 6. Read the docket

**Docket** lists every spend and how it was decided — cleared, refused by
arithmetic, decided by the jury, or overridden by the principal. The share
decided without a jury is the number to watch: the gate only earns its latency
on the cases code cannot decide.

## Next

- [Concepts](#/docs/concepts) — the design and why it is shaped this way
- [Mandate format](#/docs/mandate-format) — writing your own rules
- [Integration](#/docs/integration) — connecting a settlement rail
