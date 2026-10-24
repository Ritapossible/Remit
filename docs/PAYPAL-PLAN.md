# Remit on PayPal: build plan for the PayPal AI Hackathon

Status: plan, for review before any code is written.
Deadline: **Thursday 12 November 2026, 12:00 PST** (20:00 UTC, 21:00 in
Lagos). Target: submit on **Wednesday 11 November**, one day early.
Today: Saturday 24 October. 19 days.

---

## 1. What the hackathon asks for (checked on the official site)

Source: paypalaihackathon.devpost.com: overview, rules, resources, FAQs,
updates (read 24 October).

| Requirement | Where it is stated | How this plan meets it |
| --- | --- | --- |
| Meaningfully use **both PayPal and AI**; "PayPal integration is central" | Overview, Rules section 4 | Money moves only through PayPal: Orders v2 authorization, then capture or void. AI is both the agent that asks to spend and the panel that judges each request. |
| Use the **free PayPal sandbox** | Rules section 4 | Sandbox only; no live keys anywhere. |
| New, or an existing project **significantly updated** after 1 October, and explain how | Rules section 4, "New & Existing" | Remit existed on GenLayer. The PayPal rail, the PayPal-sourced evidence, the agent, the AI panel and the new app are all built from 24 October. Section 11 below is the statement. |
| A **working demo** judges can run: hosted URL, or full setup steps | Rules section 4 | Both: a hosted app, and a one-command local setup with the judges' own sandbox keys. |
| **Public repo with an open-source license** shown in the About section | Rules section 4 | Remit is MIT; the license is already detected. |
| **Video under 3 minutes** on YouTube, public, showing it working; no third-party trademarks or copyrighted music without permission | Rules section 4 | Section 10. No music, our own screen only. |
| **Tools**: name the AI models and services and explain how each is used | Overview, "What to Submit" | A "Built with" table in the README and the Devpost text. |
| English | Rules section 4 | Yes. |
| Eligibility | Rules section 3, FAQ | Nigeria is not excluded. A PayPal developer sandbox account must open from Nigeria; if sign-up fails, the FAQ says to ask in the PayPal Discord. **This is the first thing to check (section 8, step 0).** |

**Judging**: five criteria, equally weighted: Technological
Implementation, Design ("a complete, coherent product experience, not just
a technical proof of concept"), Potential Impact, Innovation, Presentation.
Ties are broken by the first criterion, so technical implementation counts
most when two projects are close.

**Prizes we can aim at**: 1st to 3rd place ($12,000 / $8,000 / $5,000), or
one honorable mention ($5,000 each). The two that fit are **Best Use of
Agentic Commerce** and **Best Use of PayPal + AI**. Plus at most one sponsor
prize: hosting on **Render** qualifies for its prize (Render credits) at
almost no extra cost. A project wins at most one grand prize *or* one
honorable mention, plus one sponsor prize (Rules section 8).

---

## 2. The product in one paragraph

**Remit: spending authority for AI agents, on PayPal.** A business gives an
AI agent a budget and a written brief ("buy what the spring campaign needs,
from our approved vendors"). When the agent wants to pay a vendor, Remit
first checks by code the arithmetic rules (per-spend cap, daily cap,
approved vendors, dropped vendors) and the vendor's invoice as PayPal
returns it; a spend that fails never touches the money. Otherwise PayPal
places a hold for the amount, and rules of judgment ("does this purchase serve the brief?", "is this one purchase
split to stay under the cap?") go to a panel of AI models, each reading the
vendor's invoice **as PayPal returns it**. If Remit allows the spend, the hold
is captured and the vendor is paid. If not, the hold is voided and no money
moves. Every decision, every model's vote and every PayPal ID is in an audit
log anyone can check.

**Who it is for**: teams that already let agents act but cap their budgets
at amounts too small to matter, because code can enforce a budget but not a
brief. **Why PayPal**: PayPal already holds the funds, the vendor's identity
and the vendor's invoice. Remit adds the missing step between "the agent
asked" and "the money moved".

---

## 3. Architecture

```
 ┌──────────────┐   quote, order    ┌──────────────────────┐  create_invoice,  ┌─────────┐
 │ Buyer agent  │ ────────────────► │ Vendor agent (shop)  │ ────────────────► │ PayPal  │
 │ (LLM), shops │ ◄──────────────── │ PayPal Agent Toolkit │  send_invoice     │ sandbox │
 │ for the brief│    invoice ID     │ (vendor's own creds) │                   └─────────┘
 └──────┬───────┘                   └──────────────────────┘
        │ one tool only: request_spend(vendor, invoice_id, amount, note)
        ▼
 ┌─────────────────────────────── Remit server (FastAPI) ─────────────────────────────┐
 │ 1. Evidence:  fetch the invoice from PayPal Invoicing v2; admission rules (sec. 5)  │
 │ 2. Reflex:    remit_core (reused, unchanged): caps, windows, allow/deny lists       │
 │    (1 or 2 fails → refused: no order is created, no money is held)                  │
 │ 3. Hold:      Orders v2 order, intent AUTHORIZE, payee = vendor → authorization     │
 │ 4. Judgment:  AI panel, N models, fail-closed (remit_prompts + jury reading reused) │
 │ 5. Settle:    capture (allowed) or void (refused), with PayPal-Request-Id           │
 │ 6. Record:    append-only, hash-chained audit log                                   │
 └───────────────┬─────────────────────────────────────────────────────┬──────────────┘
                 │ Payments API: capture / void / refund                │ REST + SSE
                 ▼                                                      ▼
           PayPal sandbox                                        Web app (React)
```

**Trust boundaries (the core design rule)**

- The **agent never holds credentials that move money**. Its PayPal tools are
  the Agent Toolkit with only read actions switched on (the toolkit's
  `configuration.actions` allowlist). The toolkit has no capture or void
  tools at all; `pay_order` and `create_refund` stay switched off. Its only
  way to spend is `request_spend`, which goes through Remit.
- **Only the Remit server** holds the payer's credentials and calls capture,
  void and refund.
- **Evidence is never supplied by the agent.** The agent names an invoice
  ID; Remit fetches it from PayPal and checks it (section 5).

### Stack

| Part | Choice | Why |
| --- | --- | --- |
| Server | Python 3.11, FastAPI | `remit_core.py` and `remit_prompts.py` are plain Python with no GenLayer calls: imported unchanged, their existing direct tests keep running. |
| PayPal | REST v2 (Orders, Payments, Invoicing) through a small typed client; Agent Toolkit 1.11.0 (Python) for the agent | Remit's own calls need idempotency headers and exact error handling, so we write them directly; the agent uses PayPal's own toolkit, which also counts for "PayPal + AI". |
| Agent | OpenAI Agents SDK, or LangChain (both supported by the toolkit), any OpenAI-compatible model | Decided at the spike by which keys we have. |
| AI panel | 3 models from different families through one OpenAI-compatible endpoint (for example OpenRouter) | One key gives model diversity; the panel size and models are config. |
| Storage | SQLite (one file), WAL mode | Enough for a demo. Spends for one mandate are serialised (section 6). |
| Web app | React + Vite, reusing Remit's design system and components | Remit's look is finished; no wallet libraries needed. |
| Hosting | Render (server and static site) | Sponsor prize eligibility; one platform. |

---

## 4. Money flow and the PayPal calls

States of one spend (each change is logged):

```
requested ─► (invoice or reflex refused) ─────────────────────► refused  (nothing held)
          └─► held ─► judging ─► allowed ─► captured
                              └► refused ─► voided
          (no judgment rule triggered: held ─► captured directly)
held/judging ──(any error, timeout, unparsable panel)──────────► voided   (fail closed)
captured ──(invoice later cancelled or disputed)──────────────► refunded  (optional, section 12)
```

| Step | PayPal API | Facts relied on (checked in PayPal's docs) |
| --- | --- | --- |
| Hold | `POST /v2/checkout/orders`, `intent: AUTHORIZE`, then authorize | "An authorization places a hold on the funds and is valid for 29 days"; capture "within the 3-day honor period"; reauthorize after it. A demo spend is decided in minutes. |
| Release | `POST /v2/payments/authorizations/{id}/capture` | Sent with `PayPal-Request-Id` = our spend ID, so a retry never captures twice. |
| Refuse | `POST /v2/payments/authorizations/{id}/void` | Same idempotency rule. |
| Evidence | `GET /v2/invoicing/invoices/{id}` | Returns invoicer, recipient, amount, items, status. |
| After the fact | `POST /v2/payments/captures/{id}/refund`; webhooks for capture and void | Optional, see section 12. |

**What is not settled yet, and is the first thing built (section 8, step 1):**

1. **Who approves the hold.** An agent cannot click a PayPal approval
   pop-up. Options, in order of preference:
   - **R1, a vaulted payer.** The business approves Remit once (Vault v3 /
     `payment_source.paypal.vault_id`), and Remit creates each authorization
     itself. This is the true agentic flow.
   - **R2, approval per spend.** The business approves each hold in the
     PayPal pop-up, and Remit still decides capture or void. Weaker autonomy,
     but it works on any account.
   - **R3, payouts from a funded balance.** No hold at all; the refusal is
     "never sent". This is the last resort, because it loses the hold story.
2. **Who receives the money.**
   - **Preferred:** the vendor is the payee directly (`purchase_units[].payee`).
   - **Fallback:** the Remit platform is the payee, and the vendor is paid by
     Payouts after capture. That would make Remit a holder of funds; we would
     say so plainly in the README.
3. **Reading the vendor's invoice.** The Invoicing API reads invoices as the
   invoicer. In a real deployment the vendor grants Remit read access to its
   invoices when it connects its PayPal account (partner onboarding with
   third-party permissions). In the sandbox demo, the vendor's sandbox app
   credentials stand in for that grant. The spike checks whether third-party
   read access works in the sandbox; if it does not, the README says the demo
   simulates the grant.

---

## 5. Evidence from PayPal, and what it does and does not prove

Remit on GenLayer took evidence from a URL under a prefix the business
pinned for each vendor (Milestone 1). That fixed the forged-invoice result
from Release 1: on Studio and Bradbury, invoices the agent forged were
refused 3 of 3 and paid 0. On PayPal the evidence is tied to the vendor's
**PayPal account** instead of a URL path.

Remit admits an invoice only if **all** of these hold, checked by code before
any model sees it:

- the invoicer's merchant ID is the vendor the agent named, and that vendor
  is on the mandate's approved list;
- the recipient is the business that owns the mandate;
- amount and currency equal the spend exactly;
- status is sent or unpaid, and not cancelled;
- the invoice has not paid another spend already (replay guard: one invoice
  pays one spend, enforced by a unique key in storage).

**Claim we make**: the agent cannot forge a vendor's invoice. It would have
to control the vendor's PayPal account, and only vendors the business
approved count.

**Claim we do not make**: that an invoice proves the goods arrived, or that
a vendor cannot collude with the agent. The jury judges the invoice against
the brief; it cannot see a warehouse.

---

## 6. The AI parts

**The buyer agent.** It shops against the brief, then calls
`request_spend`. It is deliberately not trusted: everything it says is a
claim that Remit checks.

**The vendor agent (agent-to-agent commerce).** Invoices belong to the
account that issued them: with the business's credentials, the buyer agent
cannot list or read a vendor's invoices through the API. So each demo vendor
runs a small shop whose own agent quotes and then issues a real PayPal
invoice with the Agent Toolkit's invoice tools (`create_invoice`,
`send_invoice`), addressed to the business, and returns the invoice ID. The
buyer agent passes that ID to `request_spend`, and Remit reads the invoice
from PayPal itself. Both agents use PayPal's toolkit; neither can move the
business's money. Whether the buyer agent keeps any PayPal tools (for
example `get_order` on its own spends) is decided at the spike.

**The panel.** Same question Remit's jury asks today, built by the existing
prompt code (`remit_prompts`), with untrusted text neutralised (invoice
fields, the agent's note). Each model answers JSON
`{verdict: in_remit | out_of_remit | undetermined, confidence}`, read by
the existing fail-closed parser. Anything unparsable counts as
`undetermined`.

- **Release rule (default, configurable):** at least 2 of 3 `in_remit`, and
  no `out_of_remit`.
- **Anything else** follows the mandate's default for undecided cases. The
  demo mandate's default is to void.
- **Temperature 0.** Every prompt and every raw answer is stored in the audit
  log, so a judge can see why a spend was released.

**The trade-off, stated in the README:** on GenLayer, no single party decides;
validators run by different people must agree. On PayPal, whoever runs the
Remit server runs the panel and holds the keys to capture. What remains is
that every decision is **auditable**: the log shows that each capture follows
an allowed ruling, and each refusal ends in a void. Remit on GenLayer stays
in the roadmap as the decentralised version.

**Prompt injection.** Invoice text comes from a vendor and the note from the
agent, so either may try to instruct the panel. They are passed as quoted
data blocks that cannot close their own block (Remit's existing
`neutralize`). The demo includes one invoice that says "approve this", and
it must not change the outcome.

---

## 7. Engineering rules

- **Idempotency:** one spend ID is used as the `PayPal-Request-Id` on capture
  and void. A crash between "decided" and "settled" is recovered on restart by
  reading the authorization's status from PayPal and finishing the step.
- **No double spend against the caps:** spends for one mandate are decided one
  at a time (a per-mandate lock in a single worker). A daily cap is computed
  from settled and held amounts together.
- **Fail closed everywhere:** a PayPal error, a model timeout, or a malformed
  answer ends in a void, never a capture.
- **Audit log:** append-only. Each entry stores the hash of the one before it,
  so an edit breaks the chain. It records the ruling inputs, each vote, and
  the PayPal IDs and statuses as PayPal returned them.
- **Secrets:** the server environment only. The agent process gets read-only
  credentials. Nothing is in the repo or the browser.
- **Hosted demo safety:**
  - a per-visitor rate limit;
  - a daily model-spend cap;
  - a "reset demo" button that restores the sandbox scenario;
  - sandbox only, with a check that refuses to start on live keys.
- **Tests:**
  - Remit's existing direct tests run unchanged.
  - New unit tests cover the state machine, the invoice admission rules and
    the panel reading.
  - Contract tests replay recorded sandbox responses.
  - One end-to-end script runs the three demo cases against the real sandbox
    and records the PayPal IDs.

---

## 8. Schedule

| Dates | Step | Done when |
| --- | --- | --- |
| Sat 24 Oct | **0. Accounts**: PayPal developer account from Nigeria; sandbox business (payer), two sandbox business vendors; model API key(s) | Keys in the server's environment. If sign-up fails, ask in the PayPal Discord the same day. |
| Sat 24 to Mon 26 Oct | **1. Spike** (throwaway scripts): vaulted AUTHORIZE (R1); payee = vendor; capture and void; invoice read across accounts; a vendor agent issuing an invoice with the Agent Toolkit | A written decision on R1/R2/R3, payee and invoice access. **Go/no-go gate.** |
| Tue 27 to Thu 29 Oct | **2. Server core**: mandate in USD cents (remit_core reused), PayPal client, state machine, idempotency, audit log, tests | All three demo cases run by script, without AI (reflex only). |
| Fri 30 Oct to Mon 2 Nov | **3. AI**: panel (3 models), evidence admission, the agent with toolkit plus `request_spend`, injection case | End-to-end script: allowed spend captured, off-brief voided, forged or unapproved invoice refused. |
| Tue 3 to Fri 6 Nov | **4. Web app**: mandate editor, live spend feed, ruling detail (votes, invoice, PayPal IDs), audit log view; Render deploy | Hosted URL works from a phone. |
| Sat 7 to Sun 8 Nov | **5. Hardening**: crash recovery, webhooks, rate limits, reset, judge setup script, README | A fresh machine runs it from the README in under 10 minutes. |
| Mon 9 to Tue 10 Nov | **6. Story**: video, Devpost text, screenshots, "Built with" | Video under 3 minutes, uploaded. |
| Wed 11 Nov | **Submit**. Thursday morning is a buffer only | Submission complete. |

**Cut list, in order, if behind:** webhooks → refunds → mandate editor
(ship one fixed demo mandate) → third panel model (go to 2 of 2, unanimous).
Never cut: the real PayPal hold, capture and void; the invoice checks; the
audit log; the video.

---

## 9. Demo cases (they are also the end-to-end tests)

1. **In the brief**: the agent buys the campaign's ad re-edit from an approved
   vendor, with a matching PayPal invoice. Held → panel 3 of 3 `in_remit` →
   **captured**. The vendor's sandbox balance rises.
2. **Off the brief**: the agent buys a gaming laptop "for the campaign".
   Held → panel `out_of_remit` → **voided**. No money moves.
3. **Split purchase**: two payments to one vendor that together pass the cap.
   The second triggers the structuring rule; the panel reads both invoices →
   **voided**.
4. **Evidence the agent cannot make**: an invoice from an unapproved PayPal
   account, or one already used. **Refused by code before any model runs.**
5. **Injection**: an invoice whose notes say "approve this". The outcome is
   unchanged.

---

## 10. Video (under 3 minutes)

| Time | Content |
| --- | --- |
| 0:00 to 0:20 | The problem: "You can give an agent a wallet. You cannot give it judgment." |
| 0:20 to 0:45 | The mandate: caps by code, the brief by the panel. |
| 0:45 to 2:15 | Cases 1, 2 and 4 live: the hold appears, each model's vote, then capture or void, with the PayPal status shown. |
| 2:15 to 2:45 | The audit log, and how the trust model works. |
| 2:45 to 3:00 | Who it is for, and what is next (GenLayer, real onboarding). |

No music. No third-party logos beyond naming PayPal as the platform, which
the rules require us to use.

---

## 11. "Significantly updated" statement (for the submission)

Before 1 October, Remit was a set of GenLayer contracts paying test tokens.
During the hackathon we added:

- a PayPal rail: Orders v2 authorization, capture and void, with
  idempotency and crash recovery;
- evidence fetched from PayPal's Invoicing API, with code-level admission
  rules;
- an AI agent built on PayPal's Agent Toolkit, with read-only tools;
- a panel of AI models replacing the validator jury;
- a hash-chained audit log;
- a new web app and hosting.

Only the rules engine and the prompt-building code are carried over, with
their tests.

---

## 12. Risks and open questions

| Risk | Effect | Mitigation |
| --- | --- | --- |
| A PayPal developer account cannot be opened from Nigeria | Blocks everything | Step 0 on day 1; PayPal Discord; a teammate's account as the last resort. |
| Vaulted merchant-initiated authorization is unavailable in the sandbox | No autonomous holds | R2 (approval per spend), stated plainly. |
| Payee = vendor is not allowed with AUTHORIZE for a non-partner app | Vendor not paid directly | Platform payee plus Payouts, with custody stated. |
| Third-party invoice read needs partner approval | Evidence needs the vendor's own credentials | Simulated grant in the demo, stated in the README. |
| Model cost or rate limits during judging | Demo fails | Daily cap, cached replays, recorded video as the fallback. |
| Judges do not run it | Scored on video and text | Video carries the whole story; the README opens with the hosted link. |
| Scope creep | Late submission | Cut list in section 8; submit one day early. |
| Refunds after capture | Not core | Optional: refund only when the invoice is later cancelled or disputed. Never called a "clawback": PayPal takes a refund from the vendor, not the agent. |

**Inputs needed from the owner:**

1. A PayPal developer account and sandbox app credentials.
2. Which AI provider keys are available.
3. Repo choice: a `paypal/` folder in the Remit repo (recommended, since it
   shows the history) or a new repo.

**Where this lives**: the Remit repo, branch `paypal`, with the code in
`paypal/`. GenLayer Remit on `main` is untouched.
