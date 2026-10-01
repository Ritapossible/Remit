# Mandate Format

A mandate is the versioned ruleset governing one agent. The principal authors
it, publishes it at a URI, and pins its digest on chain at registration.

Design rule: **the mandate is the only authority.** Nothing a claimant supplies
at spend time can widen it.

---

## Document

```json
{
  "remit_mandate_version": 1,
  "agent": "0x...",
  "principal": "0x...",
  "version": 3,
  "currency": "USD_CENTS",
  "defaults": {
    "on_deadline": "refund",
    "on_undetermined": "refund",
    "response_window_seconds": 900,
    "hold_deadline_seconds": 86400,
    "clawback_window_seconds": 604800
  },
  "vendor_lists": {
    "vendors": ["0xa...", "0xb..."],
    "dropped": ["0xc..."]
  },
  "rules": []
}
```

`rules` holds the reflex and judgment rules described below.

`version` is an integer that must strictly increase. A case pins the version it
was raised under and is unaffected by later publications (T5).

`currency` is a unit label only. All amounts on chain are integers in the
smallest unit. **No floats anywhere.**

## Defaults

| Field | Meaning |
| --- | --- |
| `on_deadline` | `refund` \| `release`. Resolution when a HELD spend hits its deadline with no verdict. (T2) |
| `on_undetermined` | `refund` \| `release`. Resolution on an `UNDETERMINED` verdict. Unproven is not guilty. |
| `response_window_seconds` | Minimum time the agent has to commit an artifact before a case may resolve against it for silence. (T9) |
| `hold_deadline_seconds` | Hard ceiling on any hold. |
| `clawback_window_seconds` | How long a SETTLED spend remains challengeable. (T7) |

Every default is mandatory. There is no implicit fallback, because an unstated
default is a decision nobody made.

## Reflex rules

Deterministic. Evaluated in the spend transaction. No jury, no latency.

```json
{"id": "daily-cap",   "type": "reflex", "check": {"daily_total_lte": 50000}}
{"id": "per-spend",   "type": "reflex", "check": {"amount_lte": 20000}}
{"id": "allowlist",   "type": "reflex", "check": {"recipient_in": "vendors"}}
{"id": "not-dropped", "type": "reflex", "check": {"recipient_not_in": "dropped"}}
```

Supported predicates in v1 - deliberately small, because every predicate is
surface area and an unevaluable one is worse than a missing one:

| Predicate | Operand |
| --- | --- |
| `amount_lte` / `amount_gte` | integer |
| `daily_total_lte` / `daily_total_gte` | integer |
| `window_total_lte` / `window_total_gte` | `{"amount": int, "seconds": int}` |
| `spend_count_lte` / `spend_count_gte` | `{"count": int, "seconds": int}` |
| `recipient_in` / `recipient_not_in` | vendor list name |
| `category_in` / `category_not_in` | list of category strings |

Every predicate is a plain boolean function over facts the contract already
holds. The two call sites differ only in what a `True` means:

- in a reflex `check`, `True` is required for the spend to pass;
- in a judgment `when`, `True` convenes the jury.

A `check` or `when` object holds **exactly one** predicate in v1. Multiple
predicates would need stated conjunction semantics, and an ambiguous rule is
worse than a missing one.

`daily_total_*` is a **rolling 86400-second window**, not a calendar day. This
avoids a timezone, which a mandate has no way to carry unambiguously. All
windows are half-open - `(now - seconds, now]` - and include the spend being
evaluated.

## Judgment rules

Natural-language. One boolean question. Convened only when `when` fires.

```json
{
  "id": "brief-alignment",
  "type": "judgment",
  "when": {"amount_gte": 20000},
  "ask": "Does this purchase serve the campaign brief?",
  "context_uri": "https://example.org/briefs/q4.md",
  "context_digest": "sha256:...",
  "requires_artifact": true,
  "on_breach": {"tier": 1}
}
```

| Field | Meaning |
| --- | --- |
| `when` | Deterministic trigger. Same predicate vocabulary as `check`. |
| `ask` | The single question. Must be answerable yes/no against the evidence. |
| `context_uri` / `context_digest` | Supporting material the jury fetches and hash-verifies. Optional; absent means the `ask` stands alone. |
| `requires_artifact` | If true, a spend that trips this trigger must carry `memo_uri` + `memo_digest`. |
| `on_breach.tier` | Response tier, capped by the registered `max_tier`. |

### The standard three

Shipped in `mandates/standard.json` because they recur and because each is
provably outside what code can evaluate.

**`brief-alignment`** - does this serve the stated purpose? Needs a
`context_uri` pointing at the brief.

**`invoice-match`** - does this payment correspond to something delivered?
`requires_artifact: true`; the artifact is the invoice or receipt.

**`structuring`** - are these separate purchases, or one purchase split to stay
under the cap? Its trigger is windowed and deterministic, so shrinking
individual amounts does not evade it:

```json
{
  "id": "structuring",
  "type": "judgment",
  "when": {"spend_count_gte": {"count": 3, "seconds": 3600}},
  "ask": "Are these separate purchases, or one purchase split across payments to stay under the per-spend cap?",
  "on_breach": {"tier": 2}
}
```

This is the T7 mitigation and the reason the product exists. A pure-code system
cannot answer it at any threshold.

## Validation at registration

A mandate is rejected - loudly, never with a falsy default - if:

1. `version` does not strictly exceed the stored version.
2. Any rule `id` is duplicated.
3. Any `when` or `check` uses a predicate outside the v1 vocabulary.
4. A vendor list name is referenced but not defined.
5. Any `defaults` field is missing.
6. `on_breach.tier` exceeds the registered `max_tier` on any rule.
7. Any amount is not a non-negative integer.

And one advisory that is not a rejection:

> **A mandate containing no judgment rules does not need GenLayer.**
> Registration succeeds and returns this notice. A plain smart contract would
> serve that configuration faster and cheaper, and saying so is more useful than
> taking the deployment.

## Worked example

```json
{
  "remit_mandate_version": 1,
  "version": 1,
  "currency": "USD_CENTS",
  "defaults": {
    "on_deadline": "refund",
    "on_undetermined": "refund",
    "response_window_seconds": 900,
    "hold_deadline_seconds": 86400,
    "clawback_window_seconds": 604800
  },
  "vendor_lists": {
    "vendors": ["0xSTOCKPHOTO", "0xCOPYWRITER", "0xADNETWORK"],
    "dropped": ["0xBADAGENCY"]
  },
  "rules": [
    {"id": "daily-cap",   "type": "reflex", "check": {"daily_total_lte": 50000}},
    {"id": "per-spend",   "type": "reflex", "check": {"amount_lte": 20000}},
    {"id": "not-dropped", "type": "reflex", "check": {"recipient_not_in": "dropped"}},
    {
      "id": "brief-alignment",
      "type": "judgment",
      "when": {"amount_gte": 10000},
      "ask": "Does this purchase serve the Q4 campaign brief?",
      "context_uri": "https://example.org/briefs/q4.md",
      "context_digest": "sha256:0000...",
      "requires_artifact": true,
      "on_breach": {"tier": 1}
    },
    {
      "id": "structuring",
      "type": "judgment",
      "when": {"spend_count_gte": {"count": 3, "seconds": 3600}},
      "ask": "Are these separate purchases, or one purchase split across payments to stay under the per-spend cap?",
      "on_breach": {"tier": 2}
    }
  ]
}
```

Against this mandate:

| Spend | Outcome |
| --- | --- |
| $40 to `0xSTOCKPHOTO` | **SETTLED** in-transaction. Under every cap, no trigger fires, no jury. |
| $250 to `0xBADAGENCY` | **REFUSED** in-transaction by `not-dropped`. No jury. |
| $150 to `0xADNETWORK` with an off-brief invoice | **HELD** by `brief-alignment`, jury convened, likely REFUSED. |
| 3 × $190 to related recipients in one hour | **HELD** by `structuring`. Every individual spend is legal. Only a jury can answer it. |
