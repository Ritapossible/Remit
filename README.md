# Remit

**Spending authority for AI agents.**

Arithmetic clears in the same transaction. Judgment goes to a jury.
The agent spends nothing outside its remit.

Built on [GenLayer](https://genlayer.com) Intelligent Contracts.

---

## The problem

You can give an agent a wallet. You cannot give it judgment.

Code can enforce a budget. Code cannot enforce a brief:

| Rule | Who can check it |
| --- | --- |
| "No more than $500 per day" | Arithmetic. Any smart contract. |
| "Only vendors on the allowlist" | Arithmetic. Any smart contract. |
| "No single payment over $200" | Arithmetic. Any smart contract. |
| **"This purchase serves the campaign brief"** | **Nothing on-chain today.** |
| **"This invoice matches a deliverable we received"** | **Nothing on-chain today.** |
| **"This is not the vendor we dropped for quality"** | **Nothing on-chain today.** |
| **"These three payments are one purchase split to stay under the cap"** | **Nothing on-chain today.** |

The bottom four are why people cap agent budgets at amounts too small to be
useful. No amount of Solidity reaches them. They are not thresholds — they are
readings of intent against a written mandate, which is exactly what GenLayer's
Optimistic Democracy adjudicates.

Remit is the gate that sits in front of an agent's money and applies both kinds
of rule, each with the machinery it actually needs.

## The design in one screen

A principal registers an agent under a **mandate** — a versioned, digest-pinned
ruleset. Every rule is typed.

```
reflex    deterministic Python, evaluated in the spend transaction
          refuses immediately, costs nothing, adds no latency

judgment  natural-language rule, evaluated by a validator jury
          consulted ONLY when its deterministic `when` trigger fires
```

A spend arrives. The contract evaluates every reflex rule and every judgment
trigger, deterministically, in that transaction.

```
no reflex breach, no trigger fires   ->  SETTLED     same transaction, no jury
reflex breach                        ->  REFUSED     same transaction, no jury
a judgment trigger fires             ->  HELD        value escrowed, jury convened
                                              |
                                     jury reads the pinned rule, the facts the
                                     contract read itself, and the digest-verified
                                     artifact the agent committed at spend time
                                              |
                                  ALLOWED  ->  vendor credited
                                  REFUSED  ->  principal credited back
```

The common path never touches a jury. That is the whole reason this is usable:
if every purchase waited on consensus, nobody would ship it. The jury is spent
only on the residue that code cannot express.

**If you cannot name a rule that code cannot evaluate, you do not need
GenLayer.** Remit exists because that list is non-empty and expensive.

## Why a gate and not an alarm

The obvious shape for this is a monitor: watch the agent, catch violations,
file a challenge afterwards. That is forensics. The money already left.

Remit refuses before value moves, and that one inversion buys a property the
monitor shape cannot have:

> **Escrow makes optimistic action safe.**

A halt-style module that acts on a provisional verdict has wrongly paused a live
protocol if the appeal reverses it. Remit holding money in escrow on a
provisional verdict costs nothing if the appeal reverses it — the value never
moved in either direction. So Remit binds on **round acceptance**, not on
finality, without taking on the risk that forces alarm-shaped designs to wait.

## Graduated authority

A principal grants a maximum tier at registration. Remit can never exceed it.

| Tier | On an out-of-remit verdict |
| --- | --- |
| 0 | Record the case. Nothing is refused. (**shadow mode**) |
| 1 | Refuse this spend. |
| 2 | Refuse this spend, freeze the agent pending principal review. |
| 3 | Refuse, freeze, and slash the agent's bond. |

Tier 0 is the adoption ramp: Remit runs with zero authority and publishes what
it *would* have refused. A principal grants real authority once the public case
record shows a false-positive rate they can live with.

Three rules hold at every tier:

- **The principal's own key always outranks Remit.** Additive authority, never
  exclusive. A module that can permanently brick you gets adopted by nobody.
- **Freezes expire.** Every restriction carries a TTL and lifts itself. A stuck
  court must not become a permanent outage.
- **Remit never pushes value.** All outcomes credit an owed balance that the
  recipient withdraws. See `docs/ARCHITECTURE.md` for the measured reason.

## Repository layout

```
contracts/          Intelligent Contract sources (built, not hand-edited)
  remit_core.py     deterministic engine — pure Python, no chain, no LLM
  remit_prompts.py  prompt construction, isolated and separately testable
  contract_shell.py the chain layer: storage, entrypoints, consensus blocks
tests/direct/       in-memory tests, no server (genlayer-test direct mode)
tests/integration/  end-to-end against Studio / testnet
deploy/             deployment and on-chain walkthrough scripts
docs/
  THREAT-MODEL.md   written first — the interface falls out of it
  ARCHITECTURE.md   the full design and its measured constraints
  MANDATE-FORMAT.md the rule schema principals author
PLAN.md             phased build plan and current status
CLAUDE.md           project memory: hard constraints, conventions, commands
```

## Status

**Phases 1 and 2 complete. Running on GenLayer Studio.**

| | |
| --- | --- |
| Engine | 149 tests, 100% statement / 99% branch coverage |
| Mutation | 20 mutants, 20 killed, 0 survived |
| Studio guard | [`0x2805897041eC33Bd04fFc0E7Ea5A879463bfE5bF`](https://genlayer-explorer.vercel.app) |
| On-chain scenarios | all pass, **0 failed checks** |

Every scenario below ran as a real transaction and every assertion is on
resulting state, never on a transaction being accepted:

- a small allowlisted payment **settles in the same transaction**, no jury;
- a payment to a dropped vendor is **refused by arithmetic**, no jury;
- a 0.45 GEN purchase split into 3 x 0.15 under a 0.2 GEN per-payment cap
  clears every threshold and is **held** by the windowed trigger — and a
  refused payment correctly does not count toward that window;
- adjudicating inside the response window is **refused**, so an agent cannot
  lose for not using a window it never had;
- with the invoice committed, validators fetch it, hash-check it against the
  pinned digest, and reach `MAJORITY_AGREE` on
  `out_of_remit / structured_to_evade`;
- the principal **lifts a live hold in one transaction**.

Testnet Asimov/Bradbury is prepared but not yet deployed: the accounts hold no
GEN and the network exposes no programmatic faucet. See [PLAN.md](PLAN.md).

```bash
python3 -m pytest tests/direct        # 149 tests, no chain needed
python3 tests/mutation_check.py       # every guard must be killable
node deploy/testnet_status.mjs        # testnet readiness
```

## Built with

- [GenLayer docs](https://docs.genlayer.com) — protocol and SDK reference
- [GenLayer Skills](https://skills.genlayer.com) — `genlayer-dev` (contract
  authoring, `genvm-lint`, direct and integration tests) and `genlayer-docs`
- [GenLayer Studio](https://studio.genlayer.com) — hosted development network

## License

MIT. See [LICENSE](LICENSE).

Remit shares a problem domain with prior GenLayer emergency-halt work
(notably [Halt](https://github.com/JspIIV/halt), AGPL-3.0) but contains no code
derived from it and inverts its posture: Remit gates spends before value moves
rather than halting protocols after a breach.
