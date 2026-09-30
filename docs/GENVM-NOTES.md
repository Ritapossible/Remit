# Building on GenVM: field notes

Everything here was **measured** while building Remit on GenLayer Studio, most
of it by bisecting failures that produced no error message. It is written for
anyone building an Intelligent Contract, not only for Remit.

## Deployment

**The runner header must be followed immediately by code.** Any comment line
between `# { "Depends": "py-genlayer:…" }` and the first statement fails the
deploy with `contract_error` on every validator — empty stderr, no error code,
no description. Put banners after the imports.

**Pin the runner.** Networks reject `py-genlayer:test`, `:latest` and
unversioned aliases. Remit pins the hash published by the `genlayer-dev` skill
at [skills.genlayer.com](https://skills.genlayer.com).

**Size was not the problem.** Contracts up to 56 KB of executable code
deployed cleanly on Studio.

## What the runtime actually exposes

Introspected on the pinned runner:

| Namespace | Members |
| --- | --- |
| `gl.public` | `view`, `write` — no `payable` |
| `gl.advanced` | `emit_raw_event`, `gl_call`, `user_error_immediate` |
| `gl.wasi` | `get_balance`, `get_self_balance`, `gl_call`, `storage_read`, `storage_write` |
| `gl.ContractProxy` | `address`, `balance`, `emit`, `emit_transfer`, `view` |

The only way to move value is `ContractProxy.emit_transfer`, a
contract-to-contract call — which is why value sent through it to a wallet is
destroyed. The clock is `datetime.datetime.now()`; GenVM makes it
deterministic.

## Consensus

**A leader's return value reaches the validator as a wrapper object** — not a
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
incoherent answer. Include the sequence — each prior payment, its amount,
recipient and age.

**Evidence makes judgement determinate.** On inference alone, reviewers
correctly answered that a breach was not proven. With a digest-pinned invoice
the same question reached agreement in 8 of 8 consecutive trials.

## Networks

| | Studio | Testnet Asimov / Bradbury |
| --- | --- | --- |
| Chain id | 61999 | 4221 — both hostnames, one chain |
| RPC | `https://studio.genlayer.com/api` | `https://rpc-asimov.genlayer.com` |
| Faucet | `sim_fundAccount(address, wei)` — wei as a raw JSON integer | none programmatic |
| Refusal detail | `exit_code 1` only | — |

The SDK's built-in testnet endpoint is plain HTTP to a raw IP. Browsers served
over HTTPS refuse it; override the endpoint.
