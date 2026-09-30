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

## Phase 2 — Contract layer `[x]`

- [x] `contracts/remit_prompts.py` — provenance-labelled blocks, untrusted
      delimitation, foreclosure stated neutrally, explicit enum mapping
- [x] `contracts/contract_shell.py` — storage, entrypoints, consensus block
- [x] `deploy/build_contract.py`
- [x] Structural tests reading the **built** source: no transfer primitive, no
      payable entrypoint, fetch and digest check inline in both closures,
      runner pinned, no float literals in executable code, closure captures
      coerced, payloads decoded until they are dicts
- [ ] `genvm-lint` in CI — the linter is not pip-installable and ships with the
      GenVM runner; the structural tests cover its rules that matter here
- [ ] Direct-mode tests with `mock_llm` / `mock_web` / `warp` — `gltest` needs
      Python 3.12+ and this container runs 3.11 by default; a 3.12 venv is
      prepared

**Exit criterion — met.** 149 tests green, 20 of 20 mutants killed, contract
builds reproducibly.

## Phase 3 — On chain `[~]`

Deploy is not the milestone. **Transactions are the milestone.**

### Studio `[x]`

- [x] Guard deployed and mandate registered
- [x] All demo scenarios executed as real transactions, **0 failed checks**
- [x] Every assertion made on resulting state, and on `result_name` rather
      than the leader's own status — the leader reads `return` even when the
      validators disagree and the state change is rolled back

| | |
| --- | --- |
| Guard (walkthrough) | `0x2805897041eC33Bd04fFc0E7Ea5A879463bfE5bF` |
| Guard (structuring) | `0xfc04A6FD61878C1707fcb120723c3Af424976676` |
| Transactions | 8 + 5 |
| Failed checks | 0 |

### Testnet Asimov / Bradbury `[ ]` — blocked on funding

Both hostnames resolve to the same chain (id 4221) and the RPC is reachable.
The contract, the mandate (`mandates/demo-asimov.json`, wider windows for
slower finality) and the deploy path are ready; the accounts hold 0 GEN and the
network exposes no programmatic faucet, so this needs testnet GEN from the
portal. `node deploy/testnet_status.mjs` reports readiness.

## Phase 4 — Docket and shadow mode
`[ ]`

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
