# Remit — Architecture

Read [THREAT-MODEL.md](THREAT-MODEL.md) first. Everything here is a consequence
of something there.

---

## 1. The central decision: how judgment is triggered

A gate must decide, deterministically, whether a given spend needs a jury.
Getting this wrong sinks the product, so the rejected options are recorded.

**Rejected — jury on every spend.** Conceptually clean, unusable in practice.
Every purchase would wait on a consensus round. The gate would be slower than
the human approval it replaces.

**Rejected — jury decides whether a jury is needed.** Circular. The contract
cannot know a judgment rule is implicated without already applying judgment.

**Chosen — principal-authored deterministic triggers.** Each judgment rule
carries a `when` trigger: a deterministic predicate over facts the contract
already holds. The trigger decides; the jury answers.

```python
{
  "id": "brief-alignment",
  "type": "judgment",
  "when": {"amount_gte": 20000},          # deterministic. cents.
  "ask": "Does this purchase serve the campaign brief?",
  "on_breach": {"tier": 1}
}
```

This is non-circular, cheap, and — the part that matters commercially — it is a
**dial the principal controls**. Tighten triggers for more safety and more
latency; loosen them for speed. Remit does not choose the trade-off. It exposes
it.

## 2. Spend lifecycle

Remit holds no funds. The agent **declares** a spend; Remit decides whether it
is authorized; a settlement rail — a treasury contract, a payment processor, an
agent framework's wallet — reads that decision and moves the money. See §6 for
why, which was established by introspecting the live runtime rather than chosen.

```
            request_spend(recipient, amount, category, memo_uri, memo_digest, claim)
                                        |
                        +---------------+---------------+
                        |   DETERMINISTIC, in this tx   |
                        |   - evaluate all reflex rules |
                        |   - evaluate all triggers     |
                        +---------------+---------------+
                                        |
        +---------------+---------------+---------------+
        |               |                               |
   reflex breach   no trigger fires              a trigger fires
        |               |                               |
     REFUSED         SETTLED                          HELD
     no jury         no jury                 authorization withheld
                                                        |
                                           +------------+------------+
                                           |  NON-DETERMINISTIC      |
                                           |  gl.vm.run_nondet       |
                                           |  leader + validators    |
                                           +------------+------------+
                                                        |
                                      IN_REMIT / OUT_OF_REMIT / UNDETERMINED
                                                        |
                                    +-------------------+-------------------+
                                    |                   |                   |
                                AUTHORIZED           REFUSED          at the deadline:
                                                                     registered default
```

Every terminal state is a value of `authorization_of(spend_id)`:
`authorized`, `refused`, or — while held — `pending`. That single view is the
whole integration surface for a rail.

`preview_spend(recipient, amount, category)` runs the same classifier as a free
view, so a client can say *"this will be held for a jury"* before anything is
signed. It is the contract's own code path, so the prediction cannot drift from
the decision the way a reimplementation in a frontend would.

## 3. Why withholding makes optimistic action safe

Remit binds on **round acceptance**, not on finality. An alarm-shaped design
cannot safely do this — acting provisionally means having paused a live protocol
that an appeal may say should never have been paused, and the outage is real
whichever way the appeal goes.

Remit's provisional action is *withholding an authorization*. If an appeal
reverses the verdict, no value moved in either direction and the reversal costs
nothing but time.

This is the strongest structural argument for the gate framing over the alarm
framing, and it is the reason Remit can act at consensus speed rather than
finality speed.

Consequence for implementation: **`ACCEPTED` is not success.** A round that
accepts a refusal has succeeded as consensus and failed as a spend. And the
leader's own status reads `return` even when validators disagree and the change
is rolled back — only `result_name` says whether anything happened. Outcomes
are judged on resulting **state**, never on the absence of an exception.

## 4. Rule types

### Reflex

Deterministic, evaluated in the spend transaction, no LLM, no committee, no
added latency. Refuses or passes immediately.

```python
{"id": "daily-cap",  "type": "reflex", "check": {"daily_total_lte": 50000}}
{"id": "per-spend",  "type": "reflex", "check": {"amount_lte": 20000}}
{"id": "allowlist",  "type": "reflex", "check": {"recipient_in": "vendors"}}
```

If a mandate contains only reflex rules, **it does not need GenLayer.** The
registration path says so explicitly rather than silently accepting a
configuration that a plain smart contract would serve better and faster.

### Judgment

Natural-language rule, one boolean question, convened only on its trigger.

The standard library ships three, because they are the ones that recur and the
ones code provably cannot express:

| Rule | The question code cannot answer |
| --- | --- |
| `brief-alignment` | Does this serve the stated purpose? |
| `invoice-match` | Does this payment correspond to something delivered? |
| `structuring` | Are these separate purchases, or one purchase split under the cap? |

`structuring` is the T7 mitigation and the demo's centrepiece. Its trigger is
windowed and deterministic — *N spends to related recipients within T* — so it
cannot be evaded by shrinking amounts.

## 5. What the jury sees

Three provenance-labelled blocks, never merged:

```
MANDATE RULE          contract-read, digest-verified against the pinned version
FACTS                 contract-read from its own storage in this transaction
DELIVERABLE           fetched by URI, hash-checked against the commitment digest
                      states: verified | unverified | absent | foreclosed
CLAIM (untrusted)     delimited, labelled, authority explicitly denied
```

It returns:

```python
{"verdict": "IN_REMIT" | "OUT_OF_REMIT" | "UNDETERMINED",
 "reason": "<enum code>",
 "confidence": <int 0-100>}
```

Compared under the equivalence principle on the **enum and reason code**. Never
on prose. This is both the injection ceiling (T4) and what makes validator
agreement achievable at all (T10).

An `UNDETERMINED` verdict is not a breach. **Unproven is not guilty** — it
resolves to the registered default, and the case is recorded as undetermined so
the docket does not silently count it as a win for either side.

## 6. Remit takes no custody

This was forced by measurement, and it is the better design for it.

Introspecting the pinned runner on Studio showed that `gl.advanced` exposes only
`emit_raw_event`, `gl_call` and `user_error_immediate`; `gl.public` exposes only
`view` and `write`, with **no `payable`**; and the only way to move value is
`ContractProxy.emit_transfer`, reached through `gl.get_contract_at(address)`.
That is a **contract-to-contract** call — which explains a failure measured in
earlier work in this lineage, where value sent to an externally owned account
through it was debited from the sender, credited to nobody, and the transaction
still reported ACCEPTED.

A gate that holds nothing cannot destroy anything. So Remit decides and a rail
settles:

- a GenLayer-native treasury reads `authorization_of` synchronously through
  `gl.get_contract_at(remit).view()` before it moves funds, or
- an off-chain rail (a card program, a payment API, an agent framework's
  wallet) reads the same view over RPC.

The engine still resolves amounts on **equality**, never on an inequality —
`held >= committed` once restored an already-delivered payout when a residue was
present — and returns credit ledgers whose sums are checked exactly. Those
functions are the basis for the bonded challenge path on the roadmap.

## 7. Deployment topology

```
RemitGuard  (one instance per agent)
  constructor(agent, mandate_json, max_tier, shadow)
  storage:    mandate pin + version, defaults, typed rules, vendor lists,
              spend ledger, cases, verdicts
```

One instance per agent is the T6 mitigation and it is structural: transactions
on one Intelligent Contract execute serially, so a shared instance would let
one noisy agent stall every other principal. The deployer is the principal.
Today each guard is deployed directly (the app's *New guard* page does this); a
factory that deploys and indexes guards is on the roadmap.

## 8. Build pipeline

Splitting the source and building the deployable artifact is not ceremony — the
deterministic engine must be testable without a chain, and the deployed contract
must be minified to fit pubdata limits on testnet.

```
contracts/remit_core.py      pure Python. No gl.*, no network, no LLM.
contracts/remit_prompts.py   prompt construction. Isolated, separately testable.
contracts/contract_shell.py  storage, entrypoints, consensus blocks.
        |
        +-- deploy/build_contract.py  -->  contracts/build/remit.py
        +-- deploy/minify_contract.py -->  contracts/build/remit.min.py
```

`remit_core.py` holds every decision that can be made without a jury, which is
most of them. It is imported directly by the direct-mode tests and runs in
milliseconds.

## 9. Constraints that shape the code

Measured, not assumed. Full detail and rationale in `CLAUDE.md`.

| Constraint | Consequence |
| --- | --- |
| `gl.nondet.web.request` is untraceable through a helper by `genvm-lint` | The fetch is written **inline in both closures**, duplicated on purpose. |
| `gl.eq_principle.strict_eq` uses `run_nondet_unsafe` | Use `gl.vm.run_nondet(leader, validator, compare_user_errors=True)`. The validator must be sandboxed. |
| A view call into a codeless address is uncatchable and hangs to the leader timeout | Cheap classified guards are ordered **first**, before any call that could reach an unknown address. |
| Testnet enforces a per-transaction gas ceiling and pubdata limits | Deploy the minified build; cap the gas proxy well under the block limit. |
| `ACCEPTED` is not success | Assert on resulting state. Never on the absence of an exception. |

## 10. Open questions

Recorded rather than resolved, because guessing them would be worse than
carrying them. Two were answered in Phase 1 and are struck through; the
numbers now live in tests, so changing a constant without changing a test is
not possible.

~~1. **Bond denomination.**~~ **Answered in Phase 1.** A fraction of the spend
   with a floor: `max(floor, amount * 1000 / 10000)` — 10% of what is at risk,
   never less than the floor. A flat bond makes a large spend cheap to grief; a
   pure fraction makes a small spend uneconomic to challenge at all. The floor
   prices attention, the fraction scales with exposure. Fixed by
   `tests/direct/test_core_bonds.py`.

~~2. **Standing decay.**~~ **Answered in Phase 1.** Escalation is geometric in
   the challenger's effective loss count (×2, capped at 64×), and one loss is
   forgiven per **7 days** since the last. A single win resets the streak
   outright. Grinding through an escalation costs double each attempt; waiting
   one out costs a week of inactivity per step. Both are priced, neither is
   free, and an honest challenger who had one bad week is back to the floor in
   days rather than banned. Fixed by `tests/direct/test_core_bonds.py`.

3. **Mandate hosting.** IPFS, or any HTTPS URI with a digest? The digest makes
   the host untrusted, so HTTPS is defensible — but availability becomes a
   liveness dependency. Leaning: any URI, digest-pinned, with the registered
   default resolving the case if it is unreachable.
4. **Multi-rule cases.** If two judgment triggers fire on one spend, is that one
   case with two questions or two cases? One case is cheaper; two is cleaner for
   the docket. Undecided.
