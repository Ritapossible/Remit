# CLAUDE.md - Remit project memory

Read this before writing contract code. Most entries here were **measured on a
live network**, not inferred from documentation, and several describe failures
that are invisible in code review and that a passing integration test will not
reveal.

Canonical references, in this order:
1. [docs.genlayer.com](https://docs.genlayer.com) - protocol and SDK
2. [skills.genlayer.com](https://skills.genlayer.com) → `genlayerlabs/skills`,
   plugin `genlayer-dev` (`write-contract`, `genvm-lint`, `direct-tests`,
   `integration-tests`, `genlayer-cli`) and `genlayer-docs`
3. [genlayer.com](https://genlayer.com) - positioning and ecosystem

---

## Hard laws

Breaking any of these has already cost real money or real days. Each has a
structural test; if the test is missing, write it before the code.

### 1. Never push value. Ever.

`emit_transfer` credits a **contract**. It does **not** credit an externally
owned account. Measured on Studio: the sender is debited, the wallet is credited
nothing, the value is destroyed, and the transaction reports ACCEPTED.

Every payout is `owed[address] += amount` plus a `withdraw()` the recipient
calls. Vendor payouts, refunds, bond returns, slash proceeds - no exceptions.

> Test: `test_no_emit_transfer_in_contract_source` greps the **built** source.

### 2. Resolve entitlement on equality, never an inequality

`held >= committed` restored an already-delivered payout when a residue was
present; a claimant ended up holding 1.8 for a 0.925 entitlement. The condition
is `held == committed`.

Generally: never infer a state from an inequality when the exact value is
available. If two different states can satisfy your comparison, it is wrong.

### 3. `ACCEPTED` is not success

Consensus agreeing on a refusal is a **network success** and a **spend failure**.
Assert on resulting state. Never on the absence of an exception.

### 4. The fetch goes inline in both closures

`genvm-lint` cannot trace `gl.nondet.web.request` through a helper function. A
helper that lints clean at authoring time fails on the network.

Write the fetch, the digest check and the canonicalisation **inline in the leader
closure and again in the validator closure.** The duplication is deliberate.
Do not refactor it away.

> Test: `test_fetch_is_inline_in_both_closures`, structural, on the built source.

### 5. `gl.vm.run_nondet`, not `gl.eq_principle.strict_eq`

`strict_eq` routes through `run_nondet_unsafe`, which does not sandbox the
validator and offers no `compare_user_errors`.

```python
gl.vm.run_nondet(leader_fn, validator_fn, compare_user_errors=True)
```

### 6. Order cheap classified guards first

A view call into a codeless address is **uncatchable**. On Studio it hangs for
the full leader timeout (600s); on testnet it refuses in 7–14s. Reordering the
guards so cheap deterministic checks run before any call that could reach an
unknown address took a path from 600s to under 9s.

### 7. Accept both `str` and `Address` in views, and fail loudly otherwise

A `CalldataAddress` passed where a `str` key was expected returned **0** with no
error - a check that could not fail, mistaken for evidence. The same lookup
returned `0.875` as a string and `0.000` as a `CalldataAddress`.

`_lookup_key()` accepts `str | Address` and raises on anything else. Never
return a falsy default from a lookup.

### 8. The runner header must be followed immediately by code

Any comment line between `# { "Depends": ... }` and the first statement makes
the deploy fail with `contract_error` on **every** validator, empty stderr, no
error code, no description. Nothing in the receipt points at it.

The generated-file banner therefore sits *after* the imports. This cost a full
binary search over the module to find.

> Test: `test_runner_is_pinned_to_the_documented_hash` plus the build's own
> preamble ordering.

### 9. There is no transfer primitive on `gl.advanced`

Introspected on the live runner: `gl.advanced` has only `emit_raw_event`,
`gl_call`, `user_error_immediate`. `gl.public` has only `view` and `write` -
**no `payable`**. `gl.wasi` has only `get_balance` / `get_self_balance`, both
read-only.

The one way to move value is `ContractProxy.emit_transfer(*, value, on=...)`,
reached through `gl.get_contract_at(addr)`. It is a **contract-to-contract**
call, which is exactly why value routed through it to an externally owned
account is destroyed.

Remit therefore takes no custody at all. A gate that holds nothing cannot
destroy anything.

> Test: `test_no_emit_transfer_in_contract_source`, `test_no_payable_entrypoint`

### 10. A leader's value reaches the validator as a wrapper object

Not a `str`, not a `dict`. Established with a per-predicate consensus readout -
each probe method returned one boolean and agree/disagree was the bit:

| probe | result |
| --- | --- |
| `isinstance(x, str)` | disagree - it is **not** a string |
| `len(str(x)) > 0` | agree |
| `"verified" in str(x)` | agree - the payload **is** in `str(x)` |

A decoder that gives up on anything not already `dict`/`bytes`/`str` sees
nothing, returns `{}`, and the validator rejects a correct verdict. Every
validator disagrees, deterministically, with no error anywhere in the receipt.

Decode with `_as_dict`: coerce via `str()`, then `json.loads` repeatedly until
it is a dict (the payload is double-encoded).

> Test: `test_as_dict_coerces_a_wrapper_object`

### 11. `result_name` is the consensus outcome, not `leader_receipt[0].result.status`

The leader's own status reads `return` even when the validators disagree and
the state change is rolled back. Only `result_name` (`MAJORITY_AGREE` vs
`MAJORITY_DISAGREE`) says whether anything actually happened. A walkthrough that
checks the leader's status will report success on a transaction that changed
nothing - this is hard law 3 wearing a disguise.

### 12. The validator re-answers the question; it does not grade the answer

Asking a validator "is the leader's verdict defensible?" was measured on Studio
and is **not stable**: models split roughly evenly, so consensus fails on
exactly the questions the product exists to answer. The receipts show five
different models per transaction.

Re-answering a narrow, well-specified question is far more determinate. The
split is:

- **deterministic evidence** (the artifact's hash-checked state) - compared
  **exactly**; the validator fetched it itself, so a leader cannot lie about it;
- **the judgement** - the validator answers the same question from its own
  evidence, and agrees if the verdicts match, or if its own answer is
  `undetermined` (a validator that is itself unsure does not veto a colleague
  who reached a definite answer; two opposite *definite* answers is a real
  disagreement, which is what appeals are for).

Neither half may be dropped: exact-only cannot reach consensus,
defensibility-only lets a leader assert any evidence it likes.

### 13. Coerce storage reads before capturing them in a closure

The leader runs in-process and tolerates a storage-backed value. The validator
is sandboxed and its closure is pickled. Cast every captured value with `str()`
/ `int()` / a list comprehension first.

> Test: `test_closure_captures_are_plain_python`

### 14. Aggregates hide shape

A jury given only totals returned an incoherent verdict and the other
validators correctly refused it. Facts must carry the **sequence** - each prior
payment, its amount, recipient and age - not just the sums.

### 15. State the enum mapping in every prompt

A rule phrased as a question ("are these separate purchases, or one purchase
split?") does not tell a model which reading means `out_of_remit`. Both the
answering prompt and any review prompt must say so explicitly. Omitting it from
one of the two was worth three validator disagreements.

### 16. Mutation-test every guard

For each guard, there must be a test that **fails when the guard is removed**.
A guard with no such test is decoration. This is how #7 was caught.

---

## Prompt rules

- Provenance-label every block: `MANDATE RULE` / `FACTS` / `DELIVERABLE` /
  `CLAIM (untrusted)`. Never merge them.
- All claimant text is delimited and explicitly labelled untrusted, with the
  mandate rule stated as the only authority.
- The returned value is a **small enum plus a reason code**. Never free text.
  The equivalence comparison is over that enum.
- **A missing commitment is a fact about the record, not grounds for doubt.**
  Wording that invites the model to lower confidence because evidence is absent
  produced confidence 24 and blocked legitimate outcomes. State absence
  neutrally and let the rule decide what absence means.
- `foreclosed` (the window had not elapsed) and `absent` (it had) are different
  states with opposite resolutions. Never collapse them.

---

## Network constraints

| | Studio | Testnet |
| --- | --- | --- |
| Faucet | `sim_fundAccount` - address + **wei as a raw JSON integer** | n/a |
| Reason strings | yes | no - plan for opaque refusals |
| Gas | generous | per-transaction ceiling well under the block limit; cap the proxy |
| Pubdata | generous | limited - deploy the **minified** build |
| Codeless view call | hangs to the 600s leader timeout | refuses in 7–14s |
| Rate limiting | occasional HTML gateway pages surfacing as JSON parse errors | `-32005` |

A Studio "Leader Timeout" is usually contract shape (see hard law #6), not a
network defect. Check guard ordering before blaming the network.

---

## Conventions

- **Integers only.** All amounts in the smallest unit. No floats anywhere -
  not in the engine, not in tests, not in fixtures.
- **Build, do not hand-edit.** `contracts/build/` is generated. Edit
  `remit_core.py`, `remit_prompts.py` or `contract_shell.py` and rebuild.
- **The engine is chain-free.** `remit_core.py` imports no `gl.*`, touches no
  network, calls no LLM. If a decision can be made deterministically, it lives
  there and is tested in milliseconds.
- **One guard instance per agent.** Factory-deployed. There is no shared-instance
  path - a shared instance reintroduces head-of-line blocking (T6).
- **Keys never enter the repository.** Deployment keys live outside the working
  tree, `chmod 600`. `*.key` and `keys/` are in `.gitignore`.
- **The clock is `datetime.datetime.now()`.** GenVM makes it deterministic;
  `gltest`'s `warp` cheatcode patches it. There is no `gl.block.timestamp`.
- **Update the README when an address changes.** A README naming a stale
  contract is a defect, and a script verifies every transaction hash in it.

## Runner header

Pin the GenVM runner. Do not float it.

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

This hash is carried from prior working contracts in this codebase's lineage.
**Re-verify it against the current `genlayer-dev` skill before the first
deployment** - pins move, and a stale pin fails at deploy time rather than at
lint time.

## Commands

```bash
genvm-lint contracts/build/remit.py     # must be clean before any deploy
pytest tests/direct -q                  # in-memory, no server, seconds
pytest tests/integration -q             # against Studio / testnet
python deploy/build_contract.py         # -> contracts/build/remit.py
python deploy/minify_contract.py        # -> contracts/build/remit.min.py
```

`genlayer-test` direct mode needs Python 3.12+ and provides `direct_vm`,
`direct_deploy`, `direct_alice`, plus the `mock_llm`, `mock_web` and `warp`
cheatcodes.

## Definition of done

A change is done when:

1. `genvm-lint` is clean on the built source.
2. Direct-mode tests pass, including the structural ones.
3. Every new guard has a test that fails when the guard is removed.
4. If behaviour changed on chain, a **transaction hash** demonstrates it - a
   deployment alone proves nothing.
5. The README and `PLAN.md` reflect reality, including what is still broken.

Report outcomes faithfully. If a step was skipped, say so. If a test fails, show
the output.
