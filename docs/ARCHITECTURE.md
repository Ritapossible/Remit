# Remit - Architecture

Read [THREAT-MODEL.md](THREAT-MODEL.md) first. Everything here is a consequence
of something there.

---

## 1. The central decision: how judgment is triggered

A gate must decide, deterministically, whether a given spend needs a jury.
Getting this wrong sinks the product, so the rejected options are recorded.

**Rejected - jury on every spend.** Conceptually clean, unusable in practice.
Every purchase would wait on a consensus round. The gate would be slower than
the human approval it replaces.

**Rejected - jury decides whether a jury is needed.** Circular. The contract
cannot know a judgment rule is implicated without already applying judgment.

**Chosen - principal-authored deterministic triggers.** Each judgment rule
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

This is non-circular, cheap, and - the part that matters commercially - it is a
**dial the principal controls**. Tighten triggers for more safety and more
latency; loosen them for speed. Remit does not choose the trade-off. It exposes
it.

## 2. Spend lifecycle

Remit holds no funds. The agent **declares** a spend; Remit decides whether it
is authorized; a settlement rail - a treasury contract, a payment processor, an
agent framework's wallet - reads that decision and moves the money. See §6 for
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
`authorized`, `refused`, or - while held - `pending`; and `revoked` once a
tier-3 breach withdraws an authorization the rail had not yet paid (§6b). That
single view is the whole integration surface for a rail.

`preview_spend(recipient, amount, category)` runs the same classifier as a free
view, so a client can say *"this will be held for a jury"* before anything is
signed. It is the contract's own code path, so the prediction cannot drift from
the decision the way a reimplementation in a frontend would.

## 3. Why withholding makes optimistic action safe

Remit binds on **round acceptance**, not on finality. An alarm-shaped design
cannot safely do this - acting provisionally means having paused a live protocol
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
is rolled back - only `result_name` says whether anything happened. Outcomes
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
deterministic: `recipient_total_gte` holds a payment when the total paid to
**that same recipient** in the last 24 hours, including this payment, exceeds
the per-payment cap. A split purchase is one order from one vendor paid in
pieces, so the payment that crosses the cap is held - at most one cap's worth
reaches a vendor in a day without a jury, and waiting an hour does not reset
it. An agent-wide count (`spend_count_gte`) is still in the vocabulary but is
the wrong trigger for this: it fires on unrelated purchases from different
vendors and lets the first payments of a split clear.

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

**How validators agree.** Each validator fetches and hash-checks the artifact
itself; the artifact state is compared **exactly**, so a leader cannot lie about
the evidence. Then each validator **re-answers the same question** and compares
verdicts with a rule that **fails closed** (`validator_agrees` in
`remit_core.py`):

| Leader | Validator | Accepts? |
| --- | --- | --- |
| same verdict | same verdict | yes |
| `out_of_remit` | `undetermined` | yes - a refusal stands over doubt |
| `undetermined` (mandate default: refund) | `out_of_remit` | yes - both refuse |
| `in_remit` | anything else | **no** - an authorization needs agreement |
| anything else | `in_remit` | **no** - a validator sure it is in remit vetoes |

A verdict of `in_remit` below confidence 60 is counted as `undetermined`
(`harden_verdict`), for the leader and every validator alike. Reason codes are
recorded but not compared. Prose is never compared.

**The rule is per validator; the round is decided by majority.** Each
validator votes with this rule, and GenLayer accepts the leader's answer when a
majority of validators vote to agree. Fail-closed therefore shapes every vote,
but one dissenting validator is not a veto. Measured on Studio: invoices forged
to make a split look like two orders got it released once in three runs, two
validators agreeing and one dissenting (`deploy/jury-v3-studio.json`). A round
where a majority disagrees fails, and the hold is convened again or runs to its
deadline default. What stands between a released payment and the vendor after
that is time: anyone can appeal the round until it is final, and the rail does
not pay until `finality_seconds` have passed.

An `UNDETERMINED` verdict resolves to the **registered default**
(`on_undetermined`), which the principal chose when writing the mandate, and the
case is recorded as undetermined so the docket does not count it as a win for
either side. With the shipped templates the default is `refund`: money does not
move on doubt.

**What a verified artifact means.** "Verified" means the bytes every validator
fetched match the digest the agent committed. It proves which document the jury
read, not that the document is true: the agent chose it. The prompt says so,
and tells the jury the ledger wins where the two conflict. The adversarial case
in `deploy/jury-scenarios-studio.json` measures what a self-serving document
does to the verdict.

**Every rule that fired is asked.** If two judgment triggers fire on one spend,
the jury gets both questions and any breach is `out_of_remit`.

## 6. The gate holds no money; the rail does

Remit splits deciding from paying.

- **`RemitGuard`** (`contracts/contract_shell.py`, built to
  `contracts/build/guard.py`) decides. It has no payable method and no
  transfer. It exposes `settlement_of(spend_id)`: the authorization, recipient,
  amount and decision time, ignoring shadow mode.
- **`RemitRail`** (`contracts/rail_shell.py`, built to `contracts/build/rail.py`)
  holds GEN, pays, and hosts the court (§6b). Its one payout,
  `pay(spend_id)`, reads `settlement_of` from the guard and reverts unless the
  spend is authorized, unpaid, and decided at least `finality_seconds` ago. It
  pays exactly the authorized amount to exactly the authorized recipient, and
  never while a challenge holds the spend. The principal's `withdraw` reaches
  only the treasury, never a bond; every other value path belongs to the court.
  Accounting is internal (`treasury`, `standing`, `escrowed`), because value
  sent by `emit_transfer` leaves at finality and the balance lags. A rail
  refuses to bind to a guard it was not deployed by the principal of, or to a
  shadow-mode guard.

Once a principal funds the rail instead of the agent's wallet, the agent's key
has no path to the money except through the guard. That is the property a gate
needs, and `deploy/rail-studio.json` records it on chain: paid on
authorization, reverted when early, held, refused, or already paid, with
balances read after each call.

**Why the delay.** A rail that paid the moment a verdict was accepted could pay
out before an appeal reversed it. GenLayer sends value from `emit_transfer` when
the paying transaction **finalises**, and the rail additionally waits
`finality_seconds` after the guard's decision. Set it to at least the network's
appeal window.

**Sending to a wallet.** Value goes to an externally owned account through an
EVM contract interface (`@gl.evm.contract_interface`, then
`.emit_transfer(value=...)`), as GenLayer's value-transfer docs describe.
Measured on Studio: a payable deposit credits the contract and an
`emit_transfer` through the interface credits the wallet once the transaction
finalises. The older note that value sent to a wallet "is destroyed" applied to
calling `gl.get_contract_at(wallet).emit_transfer`, which treats the wallet as
an Intelligent Contract; that path is not used.

The engine resolves amounts on **equality**, never on an inequality, and
returns credit ledgers whose sums are checked exactly - including the court's
settlement below.

## 6b. The court: challenges, clawback and graduated authority

A trigger catches what it was written for. A payment that slipped under every
trigger - a mislabelled category, a split shaped to avoid the window - would
otherwise be final. So a payment that **cleared without a jury** stays open to
a bonded challenge for the mandate's `clawback_window_seconds`.

```
challenge(spend_id, rule_id, statement)  payable: the bond
   engine.challenge_terms  -> eligible? which bond?   (challenge_error, challenge_bond)
        |
   rail.pay(spend_id) now reverts: "under challenge"
        |
respond(challenge_id, uri, digest)       the agent, inside the response window
        |
rule(challenge_id)                       anyone, once answered or the window passed
   prompts.challenge_prompt  -> the rule's own question about this payment,
                                with the challenger's statement as untrusted text
   gl.vm.run_nondet          -> fail closed in the challenge's direction
   engine.challenge_result   -> transfers, loss streak, freeze
        |
   UPHELD                         DISMISSED (in_remit or undetermined)
   unpaid: payment blocked        bond -> the agent (the griefed party, T1)
   paid:   amount -> treasury     payment payable again
           from the agent's bond
   challenger: bond + reward      LAPSED (no decision by the hold deadline)
   tier 2: agent frozen           bond returned, nobody marked as losing
   tier 3: frozen + revoke unpaid
```

- **Who may challenge.** Anyone but the agent, naming one of the mandate's
  judgment rules. A payment decided by a jury, or by the principal's override,
  is not challengeable: a jury's verdict is reviewed by GenLayer's own appeal.
- **The bond** is the engine's curve (`challenge_bond`): 10% of the payment,
  never below the rail's floor, doubling with each loss in the challenger's
  streak, one step forgiven per week, cleared by a win.
- **The jury** answers the challenged rule's own question, with the same
  evidence handling as a hold. Upholding is the dangerous direction - it takes
  the agent's bond and can freeze it - so `challenge_agrees` mirrors
  `validator_agrees`: an upheld ruling stands only on agreement, a validator
  sure of the breach vetoes a dismissal, and a hesitant breach (confidence under
  60) counts as undetermined (`harden_challenge`).
- **The settlement** (`resolve_challenge`) makes the principal whole before the
  challenger is rewarded, and never takes more than the agent's bond. Its sums
  are checked exactly.
- **The agent's bond** is what makes a payment that already left recoverable.
  The agent can withdraw it only when no challenge is open and every payment
  that cleared without a jury is past the clawback window.

**Graduated authority.** A breach carries its rule's tier, capped by the
guard's `max_tier`, from the guard's own jury or from an upheld challenge:

| Tier | Effect |
| --- | --- |
| 1 | The payment is refused (or blocked / clawed back). |
| 2 | Also: the agent is **frozen**. The guard refuses every new spend until the principal lifts it. |
| 3 | Also: every payment requested before the breach that the rail has not paid is **revoked** (`authorization: revoked`; by spend index, so a payment decided in the same second is on one side or the other). |

The guard holds its own freeze and reads the rail's court freeze
(`court_freeze`) on every spend, once the principal has called
`attach_rail`. The principal lifts either with `lift_freeze`; a revocation
stands. Shadow mode freezes nothing.

## 7. Deployment topology

```
RemitPrompts (one per network, shared)   builds the jury's question
  constructor()                          stateless, view-only

RemitEngine  (one per network, shared)   validates mandates, classifies
  constructor(prompts)                   spends, maps verdicts to outcomes;
                                         stateless, view-only

RemitGuard  (one instance per agent)
  constructor(agent, mandate_json, max_tier, shadow, engine)
  storage:    the mandate as the engine compiled it, spend ledger, cases,
              verdicts, decision times
  runs:       the jury (consensus closures cannot call another contract, so
              the guard fetches the question and the outcome table first)

RemitRail   (one per guard, deployed by the guard's principal)
  constructor(guard, finality_seconds, bond_floor)
  storage:    treasury, paid ledger, the agent's bond, challenges (one JSON
              record each), challenger loss streaks, the court's freeze
  holds:      the GEN the agent may spend, and every bond
  runs:       the court's jury

RemitRegistry (one per network, shared)
  constructor(engine)
  storage:    guard, rail, principal and agent of every registration
```

**Why separate contracts.** Bradbury caps a transaction at 2^24 gas and a deploy
costs about 0.96M plus 782 gas per byte of code and arguments, so nothing over
about 20 KB deploys. The shared contracts are stateless and ownerless: nobody
can change their behaviour after deployment, and each guard fixes its engine
address at its own deployment. Studio runs the same contracts, so there is one
design to review. Deployed sizes: engine 18.1 KB, prompts 10.6 KB, guard
17.4 KB (plus its mandate), rail 16.8 KB, registry 3.0 KB.

One instance per agent is the T6 mitigation and it is structural: transactions
on one Intelligent Contract execute serially, so a shared instance would let
one noisy agent stall every other principal. The deployer is the principal.

**The registry** (`contracts/registry_shell.py`) is where guards are found. A
principal registers the guard they deployed, with its rail. The registry reads
the guard rather than trusting the caller - the guard must name the caller as
its principal and be bound to this network's engine, and a rail must name the
guard - and binds each agent to one principal's guard at a time; only that
principal can move it. The app lists every registration and checks the code at
each address against the published `guard.min.py`, byte for byte
(`getContractCode`), before showing it as verified. A factory contract that
deployed guards itself was the other design: it would have to carry the guard's
17 KB of code in its own storage and pay for it again in each deploy, under the
same 2^24 gas cap, so the registry verifies instead of deploying.

## 8. Build pipeline

Splitting the source and building the deployable artifacts is not ceremony -
the deterministic engine must be testable without a chain, and every deployed
contract must fit Bradbury's gas cap.

```
contracts/remit_core.py      pure Python. No gl.*, no network, no LLM.
contracts/remit_prompts.py   prompt construction. Isolated, separately testable.
contracts/engine_api.py      JSON adapters the engine exposes   (+ engine_shell.py)
contracts/prompts_api.py     JSON adapter for the jury question (+ prompts_shell.py)
contracts/jury_common.py     reading a jury's answer (guard and court).
contracts/contract_shell.py  the guard: storage, entrypoints, consensus blocks.
contracts/rail_shell.py      the treasury and the court.
contracts/registry_shell.py  the registry.
        |
        +-- deploy/build_contract.py --> contracts/build/<name>.py
                                         (readable, tested)
                                    --> contracts/build/<name>.min.py
                                         (deployed: docstrings, comments and
                                          unreachable definitions stripped,
                                          local and module-level names shortened)
```

`tests/direct/test_built_behaviour.py` and `test_built_court.py` run the
readable and the minified builds of every contract in a small stand-in for
GenVM (`tests/direct/genvm_stub.py`) and require identical results, so the
renaming is proven by execution, not by reading. `tests/direct/test_split.py`
holds the split to three promises: the adapters
decide exactly what the engine decides and the guard's assembled prompt is
byte-identical to the one measured before the split; each `.min.py` is a fresh
minify of its tested build and uses no undefined name; and each fits the gas
budget.

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
   with a floor: `max(floor, amount * 1000 / 10000)` - 10% of what is at risk,
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
   the host untrusted, so HTTPS is defensible - but availability becomes a
   liveness dependency. Leaning: any URI, digest-pinned, with the registered
   default resolving the case if it is unreachable.
4. **Multi-rule cases.** If two judgment triggers fire on one spend, is that one
   case with two questions or two cases? One case is cheaper; two is cleaner for
   the docket. Undecided.
