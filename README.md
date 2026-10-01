<p>
  <img src="frontend/public/brand/logo.svg" alt="Remit" height="56" />
</p>

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
useful. No amount of Solidity reaches them. They are not thresholds - they are
readings of intent against a written mandate, which is exactly what GenLayer's
Optimistic Democracy adjudicates.

Remit is the gate that sits in front of an agent's money and applies both kinds
of rule, each with the machinery it actually needs.

## The design in one screen

A principal registers an agent under a **mandate** - a versioned, digest-pinned
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
a judgment trigger fires             ->  HELD        authorization withheld, jury convened
                                              |
                                     jury reads the pinned rule, the facts the
                                     contract read itself, and the digest-verified
                                     artifact the agent committed at spend time
                                              |
                                  IN_REMIT      ->  authorized
                                  OUT_OF_REMIT  ->  refused
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

> **Withholding makes optimistic action safe.**

A halt-style module that acts on a provisional verdict has wrongly paused a live
protocol if the appeal reverses it. Remit withholding an authorization on a
provisional verdict costs nothing if the appeal reverses it - no value moved in
either direction. So Remit binds on **round acceptance**, not on finality,
without taking on the risk that forces alarm-shaped designs to wait.

Remit holds no funds at all. It decides; a rail - a treasury contract, a card
program, an agent framework's wallet - reads `authorization_of(spend_id)` and
settles. See `docs/ARCHITECTURE.md` §6 for why that was measured, not chosen.

## Graduated authority

A principal grants a maximum tier at registration. Remit can never exceed it.

| Tier | On an out-of-remit verdict |
| --- | --- |
| 0 | Record the case. Nothing is refused. (**shadow mode**) |
| 1 | Refuse this spend. |
| 2 | Refuse, recorded at severity 2. |
| 3 | Refuse, recorded at severity 3. |

Tier 0 is the adoption ramp: Remit runs with zero authority and publishes what
it *would* have refused. A principal grants real authority once the public case
record shows a false-positive rate they can live with.

Three rules hold at every tier:

- **The principal's own key always outranks Remit.** Additive authority, never
  exclusive. A module that can permanently brick you gets adopted by nobody.
- **Freezes expire.** Every restriction carries a TTL and lifts itself. A stuck
  court must not become a permanent outage.
- **Remit never takes custody.** It authorises; a rail settles. See
  `docs/ARCHITECTURE.md` §6 for the measured reason.

In this version tiers 2 and 3 are recorded as severity on the docket; agent
freezing and bond slashing are on the [roadmap](PLAN.md).

## Status

**Running on GenLayer Studio. Testnet is next.**

| | |
| --- | --- |
| Reference guard (Studio) | `0xA7299Ccb90Ce06C1047cb28253b205037E7e1364` |
| On-chain walkthrough | 8 transactions, **0 failed checks** |
| Jury consensus with pinned evidence | **8 of 8** consecutive trials |
| Engine | 151 tests, 100% statement / 99% branch coverage |
| Mutation | 20 mutants, 20 killed |

Every scenario ran as a real transaction, and every assertion is on resulting
state and on the consensus outcome (`result_name`) - never on a transaction
merely being accepted:

- a small allowlisted payment **settles in the same transaction**, no jury;
- a payment to a dropped vendor is **refused by arithmetic**, no jury;
- a 0.45 GEN purchase split into 3 × 0.15 under a 0.2 GEN per-payment cap
  clears every threshold and is **held** by the windowed trigger;
- adjudicating inside the response window is **refused**, so an agent cannot
  lose for not using a window it never had;
- validators reach `MAJORITY_AGREE` on `out_of_remit / structured_to_evade`,
  and with a digest-pinned invoice they each fetch and verify it themselves;
- the principal **lifts a live hold in one transaction**.

See [PLAN.md](PLAN.md) for what is done and what isn't.

```bash
python3 -m pytest tests/direct        # no chain needed
python3 tests/mutation_check.py       # every guard must be killable
node deploy/testnet_status.mjs        # testnet readiness
```

## Web app

A full product site ships with the contract, in `frontend/`:

| Page | What it's for |
| --- | --- |
| **Product** | What Remit is, with a live case read from the reference guard |
| **App** | Read a guard's mandate and docket, open cases, request spends, create guards |
| **Docs** | Getting started, concepts, integration, mandate format, threat model, GenVM field notes - rendered from `docs/` |
| **Roadmap** | Generated from `PLAN.md`, so it can't claim progress the plan doesn't record |

On Studio you can try everything without a wallet: **Studio burner** creates a
key in your browser and funds it from Studio's faucet. On the testnet, connect
MetaMask.

### Hosting on Vercel

Import the repository in Vercel and deploy. Either Root Directory works:

- **Repository root** uses `vercel.json`.
- **`frontend`** (Vercel's suggestion) uses `frontend/vercel.json`.

No environment variables are needed. The app reads files outside `frontend/`
(the deployed contract, `docs/`, `PLAN.md`). With `frontend` as the root, keep
Vercel's "Include files outside the root directory in the Build Step" setting
on. It is on by default.

### Local development

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run parity       # UI enums and mandate validator vs. the Python engine
npm run build
```

## Repository layout

```
contracts/          Intelligent Contract sources (built, not hand-edited)
  remit_core.py     deterministic engine - pure Python, no chain, no LLM
  remit_prompts.py  prompt construction, isolated and separately testable
  contract_shell.py the chain layer: storage, entrypoints, consensus block
  build/remit.py    the exact artifact deployed (committed, so it can be checked)
frontend/           the web app, docs site and roadmap (Vite + React + genlayer-js)
tests/direct/       engine tests and structural tests on the built contract
tests/mutation_check.py   every guard must have a test that fails without it
deploy/             deployment, on-chain walkthroughs, testnet readiness
docs/               the documentation the site renders
mandates/           standard rules and example mandates
PLAN.md             phased plan - the roadmap page is generated from it
CLAUDE.md           project memory: hard constraints, conventions, commands
.github/workflows/  CI on every push; site published from main
```

## Built with

- [GenLayer docs](https://docs.genlayer.com) - protocol and SDK reference
- [GenLayer Skills](https://skills.genlayer.com) - `genlayer-dev` (contract
  authoring, `genvm-lint`, direct and integration tests) and `genlayer-docs`
- [GenLayer Studio](https://studio.genlayer.com) - hosted development network

## License

MIT. See [LICENSE](LICENSE).

Remit shares a problem domain with prior GenLayer emergency-halt work
(notably [Halt](https://github.com/JspIIV/halt), AGPL-3.0) but contains no code
derived from it and inverts its posture: Remit gates spends before value moves
rather than halting protocols after a breach.
