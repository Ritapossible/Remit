# Remit — Build Plan

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done and verified

Verified means measured, not assumed. A phase is not done because the code
exists; it is done because a test or an on-chain transaction proves it.

---

## Phase 0 — Foundation `[x]`

- [x] Threat model written first, before any interface
- [x] Architecture, with rejected options recorded
- [x] Mandate format specified
- [x] Project memory (`CLAUDE.md`) with the hard constraints
- [x] Repository scaffold, licence, ignore rules

## Phase 1 — Deterministic engine `[ ]`

Pure Python. No `gl.*`, no network, no LLM. Runs in milliseconds, testable
without a chain. This is where most of the product's logic lives.

- [ ] `contracts/remit_core.py`
  - [ ] Mandate parsing and the seven registration validations
  - [ ] Reflex predicate evaluation (the v1 vocabulary, and nothing beyond it)
  - [ ] Trigger evaluation — same vocabulary, different call site
  - [ ] Spend classification: `SETTLED` / `REFUSED` / `HELD`
  - [ ] Artifact state: `verified` / `unverified` / `absent` / `foreclosed`
  - [ ] Response-window arithmetic distinguishing absent from foreclosed (T9)
  - [ ] Hold-deadline resolution to the registered default (T2)
  - [ ] Bond curve: floor, escalation on repeat loss, decay (T1)
  - [ ] Withdrawal resolution on **equality**, never an inequality
- [ ] `tests/direct/test_core_*.py` — target ≥ 95% branch coverage on the engine
- [ ] Mutation pass: every guard must have a test that fails when the guard is
      removed. A check that cannot fail is not evidence.

**Exit criterion.** Open question 1 (bond denomination) and 2 (standing decay)
in `ARCHITECTURE.md` are answered with numbers, not adjectives.

## Phase 2 — Contract layer `[ ]`

- [ ] `contracts/remit_prompts.py`
  - [ ] Provenance-labelled blocks: MANDATE RULE / FACTS / DELIVERABLE / CLAIM
  - [ ] Untrusted delimitation of all claimant text
  - [ ] Foreclosed stated as a fact about the record, never as grounds for doubt
- [ ] `contracts/contract_shell.py`
  - [ ] Pinned runner header (exact hash in `CLAUDE.md`)
  - [ ] Storage: mandate pin + version, spend log, cases, owed balances, standing
  - [ ] `register` / `spend` / `commit_artifact` / `challenge` / `resolve` /
        `withdraw` / `override` / views
  - [ ] `gl.vm.run_nondet(leader, validator, compare_user_errors=True)`
  - [ ] Fetch written **inline in both closures** — duplicated on purpose
  - [ ] Cheap classified guards ordered first, before any unknown-address call
- [ ] `deploy/build_contract.py` and `deploy/minify_contract.py`
- [ ] `genvm-lint` clean in CI
- [ ] Direct-mode tests with `mock_llm`, `mock_web`, `warp` cheatcodes
- [ ] Structural tests that read the **built** source:
  - [ ] no `emit_transfer` anywhere (T8)
  - [ ] fetch inline in both closures (T10)
  - [ ] every state constant appears in the summary view it belongs to

**Exit criterion.** Direct-mode suite green, lint clean, structural tests green.

## Phase 3 — On chain `[ ]`

Deploy is not the milestone. **Transactions are the milestone.**

- [ ] Factory deployed to Studio; one guard instance per agent (T6)
- [ ] `deploy/walkthrough.mjs` executing all three demo scenarios live
- [ ] Deployed bytecode verified byte-for-byte against the built source
- [ ] Every claimed transaction hash resolved against the network by a checker
      script, not by hand
- [ ] Owed balances asserted **after** withdrawal, in the recipient's account —
      never inferred from a transaction being ACCEPTED

**Exit criterion.** The three scenarios below have transaction hashes, and a
script resolves every one of them.

### Demo scenarios

1. **Clears instantly.** $40 to an allowlisted vendor. Under every cap, no
   trigger fires. Settles in the same transaction. No jury, no latency.
   *Proves the common path is fast.*

2. **Structuring.** Three payments of $190 to related recipients within an hour,
   against a $200 per-spend cap. Every individual spend is legal. The windowed
   trigger fires, the jury answers the question code cannot, the third payment
   is held and refused.
   *Proves the jury is load-bearing. This is the scenario that matters.*

3. **No false positive.** A $400 spend that looks wrong but is genuinely in
   mandate. Held, adjudicated, **allowed**, vendor withdraws.
   *Proves the gate is not merely a stricter cap.*

4. **Override.** The principal lifts a live hold in one transaction.
   *Proves Remit is additive authority, not a hostage.*

## Phase 4 — Docket and shadow mode `[ ]`

- [ ] `max_tier = 0` path: every case recorded, nothing refused
- [ ] Public case view: rule, verdict, reason, tier, whether authority was used
- [ ] Undetermined cases counted as undetermined, never as a win for either side
- [ ] Frontend: mandate authoring, spend feed, case detail, docket

**Exit criterion.** A principal can run Remit for a week at tier 0 and read a
false-positive rate off the docket.

## Phase 5 — Hardening `[ ]`

- [ ] Injection corpus fixture and the T4 suite
- [ ] Appeal-path integration tests (bind on accept, reverse on appeal, verify
      escrow made the reversal free)
- [ ] Isolation test: a held case on instance A does not delay instance B
- [ ] README transaction links verified end to end by script

---

## Sequencing rationale

The engine comes before the contract because the chain layer is slow to iterate
and most of the logic does not need it. The threat model came before the
interface because bonds and tiers are consequences of attacks — writing them
first would have been guessing.

Phase 3 is deliberately separated from Phase 2. A deployed contract that has
never transacted proves nothing, and the distinction has cost real time in this
codebase's lineage.

## Non-goals

Stated so they do not creep in:

- Cross-chain enforcement
- Intercepting transactions Remit is not called on
- Detection or monitoring — Remit adjudicates and gates; anyone may feed it
- Governing agent behaviour beyond value leaving the contract
