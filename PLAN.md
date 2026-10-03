# Remit - Build Plan

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done and verified

Verified means measured, not assumed. A phase is not done because the code
exists; it is done because a test or an on-chain transaction proves it.

---

## Phase 0 - Foundation `[x]`

- [x] Threat model written first, before any interface
- [x] Architecture, with rejected options recorded
- [x] Mandate format specified
- [x] Project memory (`CLAUDE.md`) with the hard constraints
- [x] Repository scaffold, licence, ignore rules

## Phase 1 - Deterministic engine `[x]`

Pure Python. No `gl.*`, no network, no LLM, no wall clock. Runs in
milliseconds, testable without a chain. This is where most of the product's
logic lives.

- [x] `contracts/remit_core.py`
  - [x] Mandate parsing and the seven registration validations
  - [x] Reflex predicate evaluation (the v1 vocabulary, and nothing beyond it)
  - [x] Trigger evaluation - same vocabulary, different call site
  - [x] Spend classification: `SETTLED` / `REFUSED` / `HELD`
  - [x] Artifact state: `verified` / `unverified` / `absent` / `foreclosed`
  - [x] Response-window arithmetic distinguishing absent from foreclosed (T9)
  - [x] Hold-deadline resolution to the registered default (T2)
  - [x] Bond curve: floor, escalation on repeat loss, decay (T1)
  - [x] Withdrawal resolution on **equality**, never an inequality
- [x] `tests/direct/test_core_*.py` - 134 tests at the end of this phase, 100%
      statement and 99% branch coverage on the engine, against a 95% target
      (the suite has grown since; the README carries the current count)
- [x] Mutation pass - `tests/mutation_check.py`, **20 mutants, 20 killed, 0
      survived**. Every guard has a test that fails when the guard is removed.

**Exit criterion - met.** Open questions 1 (bond denomination) and 2 (standing
decay) are answered with numbers and fixed by tests. See
`docs/ARCHITECTURE.md` §10.

### What Phase 1 found

Two things the design documents had wrong, both caught by running the code:

- **Demo scenario 2 did not demonstrate anything.** 3 × $190 breaches the $500
  daily cap, so arithmetic refused it before a jury was ever convened. The
  scenario is now 3 × $150 against a $450 purchase - under every threshold,
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

## Phase 2 - Contract layer `[x]`

- [x] `contracts/remit_prompts.py` - provenance-labelled blocks, untrusted
      delimitation, foreclosure stated neutrally, explicit enum mapping
- [x] `contracts/contract_shell.py` - storage, entrypoints, consensus block
- [x] `deploy/build_contract.py`
- [x] Structural tests reading the **built** source: no transfer primitive, no
      payable entrypoint, fetch and digest check inline in both closures,
      runner pinned, no float literals in executable code, closure captures
      coerced, payloads decoded until they are dicts
- [ ] `genvm-lint` in CI - the linter is not pip-installable and ships with the
      GenVM runner; the structural tests cover its rules that matter here
- [ ] Direct-mode tests with `mock_llm` / `mock_web` / `warp` - `gltest` needs
      Python 3.12+ and this container runs 3.11 by default; a 3.12 venv is
      prepared

**Exit criterion - met.** 149 tests green, 20 of 20 mutants killed, contract
builds reproducibly.

## Phase 3 - On chain: Studio `[x]`

Deploy is not the milestone. **Transactions are the milestone.**

- [x] Guard deployed and mandate registered
- [x] All demo scenarios executed as real transactions, **0 failed checks**
- [x] Every assertion made on resulting state, and on `result_name` rather
      than the leader's own status - the leader reads `return` even when the
      validators disagree and the state change is rolled back

| | |
| --- | --- |
| Reference guard | `0xA7299Ccb90Ce06C1047cb28253b205037E7e1364` |
| Walkthrough transactions | 8 |
| Failed checks | 0 |

## Phase 4 - Product: web app, docs, roadmap `[~]`

- [x] Web app on Studio: mandate, docket, case view, request a spend, new guard
- [x] `preview_spend` view, so the app predicts the path a spend will take by
      running the contract's own classifier rather than a copy of it
- [x] Studio burner for wallet-free trials; MetaMask on both networks
- [x] Wallet connection through Reown AppKit (browser and mobile wallets);
      the wallet is asked to switch to Studio or Bradbury, and nothing signs on
      the wrong chain
- [x] Parity check: UI enums and mandate validator against the Python engine
- [x] Adjudication stability: 8 of 8 consecutive trials reached consensus - on
      **one case**, with an invoice that stated the split. That measured
      consensus mechanics, not judgment; Phase 4b measures judgment.
- [x] Docs: getting started, concepts, mandate format, integration, threat model,
      GenVM field notes
- [ ] Browser end-to-end run of the full flow on Studio, in CI
- [ ] Hosted build published from `main`

**Exit criterion.** A newcomer can go from the landing page to a jury verdict on
their own guard without reading source code.

## Phase 4b - Answering the review: the check on the money's path `[x]`

An outside review found that the demo proved a narrower thing than the README
claimed. Every point checked out against the code. What changed:

- [x] **The jury fails closed.** A validator used to accept any leader verdict
      whenever it was itself unsure, so one confident `in_remit` over a doubtful
      committee released money. Now an authorization needs agreement, a refusal
      may stand over doubt, and a validator sure of `in_remit` vetoes anything
      else (`validator_agrees`). An `in_remit` below confidence 60 counts as
      undetermined. Every combination is tested; two mutants pin it.
- [x] **Every fired rule goes to the jury**, not just the first.
- [x] **The structuring trigger is per recipient.** It was "3 payments to anyone
      in an hour": it fired on unrelated vendors, let the first two payments of
      a split clear, and could be waited out. `recipient_total_gte` holds the
      payment that takes one vendor past the per-payment cap within 24 hours.
- [x] **The prompt is neutral.** It no longer tells the model that undetermined
      is "not for a judgement call", says a trigger firing is not evidence, and
      says a verified artifact proves which document was read - the agent's own
      - not that it is true; the ledger wins.
- [x] **Dead designs removed.** The defensibility prompt and its parser are gone;
      ARCHITECTURE, THREAT-MODEL and CLAUDE.md describe the rule that runs.
- [x] **The rail** (`contracts/rail.py`): holds GEN, pays only what the guard
      authorized, once, after a finality delay; the agent cannot withdraw.
      `deploy/rail-studio.json`: paid and reverted cases, balances read after.
- [x] **Payable and wallet transfers measured.** The old note "no payable; value
      sent to a wallet is destroyed" was wrong about the documented path:
      `gl.public.write.payable` and an EVM-interface `emit_transfer` work on
      Studio and Bradbury (credited at finality).
- [x] **Jury measured on evidence that cuts both ways** (fresh guard per case):
      a plain invoice for one split order, invoices forged to claim two orders,
      genuinely separate purchases, and no evidence.
- [ ] Injection corpus (one adversarial artifact is not a corpus) - Phase 6
- [ ] Appeal reversing a verdict while a payout waits - Phase 6

## Phase 5 - Testnet: Bradbury `[x]`

- [x] Deploy gas measured before sending (`deploy/probe_gas.mjs`): about 0.96M
      plus 782 per byte of code and arguments, against a 2^24 cap
- [x] Split into a shared engine, a shared prompts contract and a per-agent
      guard; each fits, and tests hold the split to the same decisions and the
      same jury prompt
- [x] Reference guard and rail deployed; walkthrough 13 transactions, 0 failed
- [x] Jury cases run on Bradbury; text-mode answers misread one case, so the
      guard asks for JSON; undecided rounds (no majority, validator timeout)
      convened again and decided correctly
- [x] Timings recorded: finality 27-31 minutes, so Bradbury rails wait 40;
      a receipt can arrive before its round is decided, so scripts poll
- [x] The app waits for a decided round too: a receipt still IDLE is polled,
      not reported as "no consensus"

## Phase 6 - Hardening `[ ]`

- [ ] Injection corpus fixture and the T4 suite against the live prompt
- [ ] Appeal path: bind on accept, reverse on appeal, confirm the reversal is free
- [ ] Isolation test: a held case on guard A does not delay guard B
- [ ] Direct-mode contract tests with `mock_llm`, `mock_web`, `warp` (Python 3.12)

## Beyond v1

Not scheduled. Listed so the direction is visible and nobody mistakes it for
something already built.

- **Bonded challenges.** Let anyone contest a settled spend within the clawback
  window. The bond curve, decay and settlement are already implemented and
  tested in the engine; the contract entrypoint is not.
- **Tier 2 and 3 enforcement.** Freeze the agent pending principal review; slash
  a standing bond. Today these tiers are recorded as severity only.
- **Guard factory and index.** Deploy and discover guards per principal.
- **Mandate republishing.** New versions for new spends, with open cases pinned
  to the version they were raised under.
- **Agent SDKs.** TypeScript and Python clients so agent frameworks call
  `request_spend` directly.
- **Notifications.** Tell a principal when a spend is held.

## Sequencing rationale

The engine comes before the contract because the chain layer is slow to iterate
and most of the logic does not need it. The threat model came before the
interface because bonds and tiers are consequences of attacks - writing them
first would have been guessing.

Phase 3 is deliberately separated from Phase 2. A deployed contract that has
never transacted proves nothing, and the distinction has cost real time in this
codebase's lineage.

## Non-goals

Stated so they do not creep in:

- Cross-chain enforcement
- Intercepting transactions Remit is not called on
- Detection or monitoring - Remit adjudicates and gates; anyone may feed it
- Governing agent behaviour beyond value leaving the contract
