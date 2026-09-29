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

## Phase 1 — Deterministic engine `[x]`

Pure Python. No `gl.*`, no network, no LLM, no wall clock. Runs in
milliseconds, testable without a chain. This is where most of the product's
logic lives.

- [x] `contracts/remit_core.py`
  - [x] Mandate parsing and the seven registration validations
  - [x] Reflex predicate evaluation (the v1 vocabulary, and nothing beyond it)
  - [x] Trigger evaluation — same vocabulary, different call site
  - [x] Spend classification: `SETTLED` / `REFUSED` / `HELD`
  - [x] Artifact state: `verified` / `unverified` / `absent` / `foreclosed`
  - [x] Response-window arithmetic distinguishing absent from foreclosed (T9)
  - [x] Hold-deadline resolution to the registered default (T2)
  - [x] Bond curve: floor, escalation on repeat loss, decay (T1)
  - [x] Withdrawal resolution on **equality**, never an inequality
- [x] `tests/direct/test_core_*.py` — **134 tests, 100% statement and 99%
      branch coverage** on the engine, against a 95% target
- [x] Mutation pass — `tests/mutation_check.py`, **20 mutants, 20 killed, 0
      survived**. Every guard has a test that fails when the guard is removed.

**Exit criterion — met.** Open questions 1 (bond denomination) and 2 (standing
decay) are answered with numbers and fixed by tests. See
`docs/ARCHITECTURE.md` §10.

### What Phase 1 found

Two things the design documents had wrong, both caught by running the code:

- **Demo scenario 2 did not demonstrate anything.** 3 × $190 breaches the $500
  daily cap, so arithmetic refused it before a jury was ever convened. The
  scenario is now 3 × $150 against a $450 purchase — under every threshold,
  and only judgment can resolve it.
- **The predicate vocabulary was asymmetric.** `MANDATE-FORMAT.md` listed
  `spend_count_lte` while the shipped `structuring` rule used
  `spend_count_gte`. The vocabulary is now symmetric pairs, and window
  semantics (rolling, half-open, inclusive of the spend under evaluation) are
  stated rather than implied.

One guard also survived the first mutation run: `_require_conserved` could be
weakened without any test failing, because in `settle_hold` the credits equal
the escrow by construction. An invariant no test can break is indistinguishable
from one that is not there, so it now has a direct test.

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

2. **Structuring.** A $450 purchase under a $200 per-spend cap and a $500 daily
   cap. It cannot be made as one payment. Split into 3 x $150 it clears every
   threshold — each payment under the per-spend cap, the total under the daily
   cap — and the per-spend cap, which exists to bound single-purchase risk, is
   defeated completely. The windowed trigger fires and the jury answers the only
   question that decides it: one purchase, or three?
   *Proves the jury is load-bearing. This is the scenario that matters.*

   The first draft of this scenario used 3 x $190, which the engine refused on
   the daily cap before any jury was convened. Arithmetic caught it, so it
   proved nothing. Writing the engine before the demo script is what surfaced
   that.

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
