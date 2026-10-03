# Building on GenVM: field notes

Everything here was **measured** while building Remit on GenLayer Studio, most
of it by bisecting failures that produced no error message. It is written for
anyone building an Intelligent Contract, not only for Remit.

## Deployment

**The runner header must be followed immediately by code.** Any comment line
between `# { "Depends": "py-genlayer:…" }` and the first statement fails the
deploy with `contract_error` on every validator - empty stderr, no error code,
no description. Put banners after the imports.

**Pin the runner.** Networks reject `py-genlayer:test`, `:latest` and
unversioned aliases. Remit pins the hash published by the `genlayer-dev` skill
at [skills.genlayer.com](https://skills.genlayer.com).

**Size is not a problem on Studio, and is the whole problem on Bradbury.**
Studio deployed 70 KB contracts without complaint. Bradbury caps a single
transaction at **2^24 gas** (16M accepted, 17M refused, measured). Deploy gas is
**about 0.96M plus 782 per byte of code and constructor arguments** - fitted to
dry-run estimates of three contract sizes with `deploy/probe_gas.mjs`, which asks
genlayer-js for the gas of a deploy and stops before signing. So about 20 KB of
code and arguments is the ceiling. Stripping docstrings, comments, unreachable
definitions and indentation took Remit from 70 KB to 36 KB; past that, the only
sound move was to split it into three contracts - a shared engine (16.4 KB),
a shared prompts contract (9.9 KB) and a per-agent guard (17.7 KB, plus the
mandate, sent without whitespace).

**Use genlayer-js 1.1.8 or later for the testnet.** 0.15 hardcoded `gas: 21000`
on every GenLayer transaction (Studio ignores gas, so it never showed there),
pointed the testnet at a plain-HTTP raw IP, and used a retired consensus
contract. Every testnet write failed: first "intrinsic gas too low", then, with
gas fixed, "Transaction not processed by consensus".

## What the runtime actually exposes

Introspected on the pinned runner:

| Namespace | Members |
| --- | --- |
| `gl.public` | `view`, `write` (and `gl.public.write.payable`) |
| `gl.advanced` | `emit_raw_event`, `gl_call`, `user_error_immediate` |
| `gl.wasi` | `get_balance`, `get_self_balance`, `gl_call`, `storage_read`, `storage_write` |
| `gl.ContractProxy` | `address`, `balance`, `emit`, `emit_transfer`, `view` |

**Correction.** An earlier version of this table said "no `payable`" because
introspection looked for it on `gl.public`. It lives on `gl.public.write`, as
GenLayer's value-transfer docs show, and it works on this runner. Measured with
a probe contract on Studio and Bradbury:

| Step | Studio | Bradbury |
| --- | --- | --- |
| `@gl.public.write.payable` deposit of 0.01 GEN | contract balance 0.01 | contract balance 0.01 |
| `emit_transfer` of 0.004 GEN to a fresh wallet through `@gl.evm.contract_interface` | wallet credited ~30 s later, at finality | message emitted with `onAcceptance: false`; credited at finality (after the appeal window) |

What destroys value is calling `gl.get_contract_at(wallet).emit_transfer`,
which treats a wallet as an Intelligent Contract. Wallets are paid through an
EVM contract interface; `contracts/rail.py` does exactly that. The clock is
`datetime.datetime.now()`; GenVM makes it deterministic.

## Consensus

**A leader's return value reaches the validator as a wrapper object** - not a
`str`, not a `dict`. `isinstance(x, str)` is false while `"verified" in str(x)`
is true, and the payload is JSON-encoded twice. A decoder that returns `{}` for
anything unrecognised makes every validator reject a correct answer. Coerce with
`str()` and decode until you have a dict.

*How this was found:* a probe contract with one method per predicate, each
validator returning a single boolean about what it received. Agree or disagree
became a one-bit readout of the validator's view.

**`result_name` is the outcome.** The leader's status reads `return` even when
validators disagree and the state change is rolled back.

**Coerce storage reads before capturing them in a closure.** The leader runs
in-process; the validator is sandboxed and its closure is pickled. Cast captured
values to plain Python types.

**Write web fetches inline in both closures.** `genvm-lint` cannot trace
`gl.nondet.web` calls through a helper function.

**Use `gl.vm.run_nondet`, not `gl.eq_principle.strict_eq`,** for anything
involving an LLM. `strict_eq` routes through `run_nondet_unsafe`, which does not
sandbox the validator.

## Getting validators to agree

**Don't ask a validator to grade the leader.** "Is this answer defensible?"
split models roughly evenly. Receipts showed five different models per
transaction.

**Do ask it the same question.** Have each validator answer the leader's exact
question from evidence it fetched itself. Compare deterministic evidence (a
hash check) exactly; compare the judgement as an enum, and let a validator that
is itself unsure abstain rather than veto.

**State the enum mapping in every prompt.** A rule phrased as a question does
not tell a model which reading means *breach*. Omitting the mapping from one of
two prompts cost three disagreements.

**Give facts shape, not just totals.** A jury given only aggregates returned an
incoherent answer. Include the sequence - each prior payment, its amount,
recipient and age.

**Evidence makes judgement determinate.** On inference alone, reviewers
correctly answered that a breach was not proven. With a digest-pinned invoice
the same question reached agreement in 8 of 8 consecutive trials.

## Networks

| | Studio | Testnet Bradbury |
| --- | --- | --- |
| Chain id | 61999 | 4221 (shared with Asimov; different consensus contract) |
| SDK chain | `studionet` | `testnetBradbury` |
| RPC | `https://studio.genlayer.com/api` | `https://rpc-bradbury.genlayer.com` |
| Faucet | `sim_fundAccount(address, wei)` - wei as a raw JSON integer | none programmatic |
| Per-transaction gas cap | not enforced | 2^24 |
| Deploy cost | - | ~0.96M + 782 gas per byte of code and arguments |
| Acceptance to finality | about 30 s | 27-31 min (a deploy was still ACCEPTED at 1609 s and FINALIZED by 1852 s) |
| Value sent by `emit_transfer` arrives | at finality | at finality |
| Refusal detail | `exit_code 1` only | `txExecutionResultName` |
| Consensus result field | `result_name: MAJORITY_AGREE` | `resultName: AGREE` |

A minimal contract reached acceptance on Bradbury in 14 seconds.
