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

```
                       spend(amount, to, category, memo_uri, memo_digest)
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
   no jury         no jury                       value escrowed
   principal       vendor credited                      |
   retains         (owed balance)          +------------+------------+
                        |                  |  NON-DETERMINISTIC      |
                challengeable within       |  gl.vm.run_nondet       |
                the claw-back window       |  leader + validator     |
                (T7 forensic tail)         +------------+------------+
                                                        |
                                           IN_REMIT / OUT_OF_REMIT / UNDETERMINED
                                                        |
                                    +-------------------+-------------------+
                                    |                   |                   |
                                 ALLOWED            REFUSED            deadline
                              vendor credited   principal credited   registered default
```

Note what the terminal states have in common: **every one of them credits an
owed balance.** Nothing is pushed. See §6.

## 3. Why escrow makes optimistic action safe

Remit binds on **round acceptance**, not on finality. An alarm-shaped design
cannot safely do this — acting provisionally means having paused a live protocol
that an appeal may say should never have been paused, and the outage is real
whichever way the appeal goes.

Remit's provisional action is *holding value in escrow*. If the appeal reverses
the verdict, the value never moved in either direction and the reversal costs
nothing but time. The escrow absorbs the provisionality.

This is the strongest structural argument for the gate framing over the alarm
framing, and it is the reason Remit can act at consensus speed rather than
finality speed.

Consequence for implementation: **`ACCEPTED` is not success.** A round that
accepts a refusal has succeeded as consensus and failed as a spend. Outcomes are
judged on resulting **state**, never on the absence of an exception.

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

## 6. Payouts are pull-based. Always.

Measured on a live network in prior work in this codebase's lineage:

> `emit_transfer` credits a **contract**. It does not credit an externally
> owned account. A transfer to a wallet debits the sender and credits the wallet
> nothing. The value is destroyed and the transaction is ACCEPTED.

Therefore every terminal state credits `owed[address]`, and recipients call
`withdraw()`. Vendor payouts, principal refunds, bond returns, slash proceeds —
all of them.

A second, harder lesson from the same lineage governs the withdrawal maths:

> Resolve entitlement on **equality**, never on an inequality.
> `held >= committed` restored an already-delivered payout when a residue was
> present, and a claimant ended up holding 1.8 for a 0.925 entitlement.
> `held == committed` is correct.

Both are hard laws in `CLAUDE.md`, and both have structural tests, because
neither is visible in a code review and neither fails an integration test.

## 7. Deployment topology

```
RemitFactory
  |
  +-- deploy(agent, mandate_uri, mandate_digest, max_tier, defaults)
        |
        +-- RemitGuard  (one instance per agent)
              storage:  mandate pin + version, reflex state, spend log,
                        open cases, owed balances, agent standing, bonds
```

One instance per agent is the T6 mitigation and it is structural. There is no
shared-instance deployment path, because a shared instance would let one noisy
agent stall every other principal through serial execution and appeal-driven
recomputation.

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
carrying them.

1. **Bond denomination.** Fixed native amount, or a fraction of the spend? A
   fraction scales with what is at risk but makes small spends uneconomic to
   challenge. Leaning fraction with a floor; needs the numbers from Phase 1.
2. **Standing decay.** How fast does a losing challenger's escalated bond decay
   back to the floor? Too fast is exploitable, too slow bans honest challengers
   who had one bad week.
3. **Mandate hosting.** IPFS, or any HTTPS URI with a digest? The digest makes
   the host untrusted, so HTTPS is defensible — but availability becomes a
   liveness dependency. Leaning: any URI, digest-pinned, with the registered
   default resolving the case if it is unreachable.
4. **Multi-rule cases.** If two judgment triggers fire on one spend, is that one
   case with two questions or two cases? One case is cheaper; two is cleaner for
   the docket. Undecided.
