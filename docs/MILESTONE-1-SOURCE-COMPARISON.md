# Milestone 1: source comparison

An exact, immutable comparison between the Remit release that was reviewed
for reward (Release 1, `remit-engine/3`) and the release that implements
pinned evidence sources and URL validation (Milestone 1, `remit-engine/5`),
including the application integration. Every claim here can be checked from
the commit hashes and the chain alone.

## The two commits

| | Commit (full SHA) | Engine | Guard |
| --- | --- | --- | --- |
| **Base**: Release 1, reviewed for reward | [`c11fa828f0f8b8efff80830c36074ad7acdebf69`](https://github.com/Ritapossible/Remit/tree/c11fa828f0f8b8efff80830c36074ad7acdebf69) | `remit-engine/3` | `remit-guard/3` |
| **Head**: Milestone 1 | [`ae29fc34a44744fbf44e63ddae1204e46fcdf053`](https://github.com/Ritapossible/Remit/tree/ae29fc34a44744fbf44e63ddae1204e46fcdf053) | `remit-engine/5` | `remit-guard/4` |

Commit hashes are immutable: the same hash always names the same tree, so
these two links cannot be changed after review.

**Full comparison:**
<https://github.com/Ritapossible/Remit/compare/c11fa828f0f8b8efff80830c36074ad7acdebf69...ae29fc34a44744fbf44e63ddae1204e46fcdf053>

The base is the last commit before Milestone 1 work began. It is also exactly
the code deployed as Release 1: all ten deployed Release 1 contracts (five on
Studio, five on Bradbury) hash identically to the build committed at this
commit (see below). The submission was dated 3 Oct; the commits of 4 Oct
(the split hold) are part of this base and were deployed with it.

Later commits on `main` after the head add only the intro video (README,
home page, media files, one style rule), this document and
`frontend/scripts/verify-onchain-code.mjs`. They touch no contract, no test
and no part of the evidence feature:
`git diff --name-only ae29fc34a44744fbf44e63ddae1204e46fcdf053 main -- contracts tests frontend/src/lib`
prints nothing.

## On-chain proof that each release is that source

Each contract's deployed code was fetched with `gen_getContractCode` and
hashed. It equals the SHA-256 of `contracts/build/<name>.min.py` at the
commit, byte for byte. Rebuilding from source at both commits
(`python3 deploy/build_contract.py`) reproduces the committed builds exactly.

**Release 1** = build at `c11fa828…`:

| Contract | SHA-256 of the deployed code | Studio | Bradbury |
| --- | --- | --- | --- |
| engine (`remit-engine/3`) | `b19fe7d20f349ee3be1ce40d0733e2bda90a39998ba38901a9c0dae19b87c484` | `0xC54324E0127BC5ce3E314467a1c2Eec9F9bEC515` | `0x6Bbf7978ba6f7A61E29b33D0f13ecc01B9F50CE3` |
| guard (`remit-guard/3`) | `3f42ba1cc4590a1a4e23df7c3bf42fd8b9954d2ea4721990765d8fc0a5eeb16e` | `0xB025487E70C98B33062ea40AD059a3d3855013E1` | `0xb9E354eeB1B1c43E3416e39472aA4B30eB94DcC8` |
| rail | `b4329eb75b9bb017057578998194d9e7b6f3e810747f5b10ab51e487ca0913ed` | `0x3a79D5dD360a7112061281E8041FAd2E2eccb610` | `0x0350eBBbf6752d44BB37E5318F093c1e4DB18225` |
| prompts | `e7f447ef4b3f8d96be81e55dcd5fb09fa0bfccd4e6ce5991f948bb540216f0db` | `0xba3Aa01E33bE3e464B2D9b6630a1851e411b51A5` | `0x18D3D692481C78f57E488E352155076cf2E091cd` |
| registry | `8ace43caec23078deabc3143709a62a83202135277a48022422435db0184bf2d` | `0xC55Dcbf923da53Fd5746De792b6991c9b9144dE0` | `0x3Bc28fF37db197A1c57ED262b8FAC405ee02bAeE` |

**Milestone 1** = build at `ae29fc34…`:

| Contract | SHA-256 of the deployed code | Studio | Bradbury |
| --- | --- | --- | --- |
| engine (`remit-engine/5`) | `e1327cd15b6398883363ecc7e98f2fca8e30f3e2ff663f5ce3c7dd481bcf44aa` | `0x361Dc1B1EdDb2Dbe5E7CcbcA157D1b979201d9C7` | `0xfeA8Ec15868526e921502820C5c1Fe8fCEA6E685` |
| guard (`remit-guard/4`) | `206349447a47e0be05e7d27331199e06495eb430aad5d97d7deebc93c6d4272b` | `0xF7EE795EF77519b5dF9d367cd3588dC902603E0F` | `0x8EB28e009B6BC8b2853C549F87A917D1b371EAe9` |
| rail (unchanged) | `b4329eb75b9bb017057578998194d9e7b6f3e810747f5b10ab51e487ca0913ed` | `0x85016A51f34a1A633862749f1ab5c7F436948846` | `0xCE6EBe9e8B6C2AD94839Db40a5D2f0d2D6cD8EdE` |
| prompts (unchanged) | `e7f447ef4b3f8d96be81e55dcd5fb09fa0bfccd4e6ce5991f948bb540216f0db` | `0x06c9570A7F57a54eb0f07c4Cc3c6ee0f312c48D9` | `0xF34a07Ce68B59158f325bcb40314258fA22dA70a` |
| registry (unchanged) | `8ace43caec23078deabc3143709a62a83202135277a48022422435db0184bf2d` | `0x95E415844BEA23DEa63B16A6f82FA2168ead19cf` | `0x74ba5878B0714275dbB97Ec4D9b7Ea823b3c3707` |

Only the engine and the guard changed. Rail, prompts and registry are
identical bytes; they were redeployed only because a guard binds to one
engine and the registry to one engine.

A first Milestone 1 deployment (`remit-engine/4`, commit
[`c155cbc`](https://github.com/Ritapossible/Remit/commit/c155cbc), engine hash
`a1af3800ac062978c467722d01710d8c33cf041d5406098557a5dac7de4b2c20`) refused
`%2e` but not a double-encoded `%252e`. It was replaced by `remit-engine/5`
(commit [`4a2dd31`](https://github.com/Ritapossible/Remit/commit/4a2dd31e6e633c8728351703ebdb54a8db2f0666)),
which refuses any `%`. Its addresses and records are kept in `deploy/archive/`.

## What changed in the contracts

`git diff c11fa828f0f8b8efff80830c36074ad7acdebf69 ae29fc34a44744fbf44e63ddae1204e46fcdf053 -- contracts/*.py`:
4 files, 49 lines added, 2 removed. Permalinks are at the head commit.

| Change | Where |
| --- | --- |
| URL validation: `_unsafe_url` refuses `..`, any `%` (so `%2e` and `%252e`), `\`, `@`, `#`, `?` and spaces | [`remit_core.py` L810-L812](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/remit_core.py#L810-L812) |
| A pinned prefix must be `https://host.tld/…/`, ending in `/` | [`remit_core.py` L815-L819](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/remit_core.py#L815-L819) |
| The check: a pinned recipient's evidence must start with one of its prefixes; unpinned recipients unrestricted | [`remit_core.py` L822-L832](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/remit_core.py#L822-L832) |
| Mandate validation of `evidence_sources` (1-4 valid prefixes per address) | [`remit_core.py` L899-L905](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/remit_core.py#L899-L905) |
| Compiled mandate carries `evidence_sources` | [`engine_api.py` L79](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/engine_api.py#L79) |
| Engine view `evidence_error`; release `remit-engine/5` | [`engine_shell.py` L16, L31-L33](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/engine_shell.py#L16-L33) |
| Guard `_pinned`: refuses with `[EXPECTED] evidence must come from the vendor, under …` | [`contract_shell.py` L136-L140](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/contract_shell.py#L136-L140) |
| Enforced on `request_spend` (memo evidence), before any fetch or model | [`contract_shell.py` L223](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/contract_shell.py#L223) |
| Enforced on `commit_artifact`, before any fetch or model | [`contract_shell.py` L269](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/contracts/contract_shell.py#L269) |

**On "URL canonicalization".** The contract does not decode or normalize a
URL and then compare it; a decoder in the contract could disagree with the
decoder on the vendor's server. It refuses every URL whose meaning could
change under decoding or normalization (any `%`, `..`, `\`, `@`, `?`, `#`,
whitespace), and compares what is left as plain text against the pinned
prefix. Prefixes must end in `/`, so `https://vendor.example/` cannot match
`https://vendor.example.attacker.io/`. This fails closed: an unusual but
honest URL is refused and has to be republished under a plain path.

## What changed in the application

`git diff c11fa828… ae29fc34… -- frontend/src`:

| Change | Where |
| --- | --- |
| The same rules in TypeScript: `unsafeUrl`, `evidencePrefixOk`, `evidenceError` | [`mandate.ts` L140-L153](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/lib/mandate.ts#L140-L153) |
| Mandate validator accepts and checks `evidence_sources` | [`mandate.ts` L195-L203](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/lib/mandate.ts#L195-L203) |
| Request a spend: warns "The guard will refuse this" before signing | [`RequestSpend.tsx` L77-L78, L183](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/views/RequestSpend.tsx#L77-L78) |
| Commit evidence: same warning, and the Commit button is disabled | [`CaseView.tsx` L262, L340, L347](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/views/CaseView.tsx#L262) |
| Mandate page lists each vendor's pinned evidence prefixes | [`Overview.tsx` L215-L240](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/views/Overview.tsx#L215-L240) |
| Pay button knows the rail's split hold (browser copy of `split_hold`, plus a simulation of `pay`) | [`split.ts`](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/lib/split.ts), [`Rail.tsx` L224-L247](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/frontend/src/components/Rail.tsx#L224-L247) |

The app does not decide anything: it only warns before a transaction the
contract would refuse. `frontend/scripts/parity.ts` fails the build if the
app and the contract disagree; it runs the Python `pinned_source_error` and
the TypeScript `evidenceError` on 39 recipient/URL pairs (including `%2e`,
`%252e`, `%2f`, traversal, userinfo, queries and fragments), and both
validators on 74 mandates.

## Tests

| What | Where |
| --- | --- |
| 34 tests: prefixes, URLs (incl. double-encoding), unpinned vendors, mandate validation, and the built guard (readable and deployed bytes) refusing a forged commit while releasing the vendor's own invoice | [`tests/direct/test_pinned_evidence.py`](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/tests/direct/test_pinned_evidence.py) |
| 7 new mutants, each weakening one rule (`pinned-evidence-unchecked`, `traversal-escapes-prefix`, `double-encoding-escapes-prefix`, `prefix-without-slash`, `sources-not-validated`, `request-skips-pinning`, `commit-skips-pinning`); all killed | [`tests/mutation_check.py` L31-L75](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/tests/mutation_check.py#L31-L75) |
| Totals at the head: 403 tests pass, 59/59 mutants killed, parity agrees | `python3 -m pytest`, `python3 tests/mutation_check.py`, `cd frontend && npm run parity` |

## On-chain runs of the fix

The same invoice bytes are published in two places in this repository: the
vendor's pinned prefix (`examples/vendor/northlight/`) and the agent's own
path (`examples/agent-uploads/`). Each run deploys a fresh guard on the
Milestone 1 engine, makes two payments to the vendor (the second is held),
then commits evidence.

| | Agent's copy | Double-encoded path under the vendor's prefix | Vendor's copy |
| --- | --- | --- | --- |
| Studio ([`deploy/evidence-studio.json`](https://github.com/Ritapossible/Remit/blob/ae29fc34a44744fbf44e63ddae1204e46fcdf053/deploy/evidence-studio.json)) | refused at commit 3/3, paid 0 | refused 3/3 | verified and released 3/3 |
| Bradbury ([`deploy/evidence-bradbury.json`](https://github.com/Ritapossible/Remit/blob/main/deploy/evidence-bradbury.json)) | refused at commit 3/3, paid 0 | refused 3/3 | verified and released 3/3 |

**Two Bradbury jury rounds needed a second round.** In forged run 3 and
honest run 2 the first jury round ended with every validator `NOT_VOTED`.
That round decided nothing: the spend stayed held and nothing was
authorized or paid. Each was convened again with `deploy/reconvene.mjs` (a
fresh round, a new validator set), and both then decided: forged run 3
refused (`out_of_remit` 80), honest run 2 released (`in_remit` 100,
evidence verified). The other four Bradbury runs, and all six on Studio,
decided in their first round. In the record, the top-level fields of each
run are its deciding round, re-read from the chain with `get_spend(1)` on
19 Oct 2026, and both rounds are listed under `rounds` with their
transaction hashes. (Until 19 Oct the deciding round sat in a nested
`reconvened` field and the top level still showed the first, undecided
round; the file was restructured, with no new transactions.)

Every transaction hash is in those records. Every refusal reads, from the
chain, `evidence must come from the vendor, under
https://raw.githubusercontent.com/Ritapossible/Remit/main/examples/vendor/northlight/`.

## Reproduce

```sh
git clone https://github.com/Ritapossible/Remit && cd Remit

# 1. The exact source difference
git diff c11fa828f0f8b8efff80830c36074ad7acdebf69 ae29fc34a44744fbf44e63ddae1204e46fcdf053 -- contracts/*.py
git diff c11fa828f0f8b8efff80830c36074ad7acdebf69 ae29fc34a44744fbf44e63ddae1204e46fcdf053 -- frontend/src tests

# 2. The builds are reproducible from source
git checkout ae29fc34a44744fbf44e63ddae1204e46fcdf053
python3 deploy/build_contract.py && git status --porcelain contracts/build   # prints nothing
sha256sum contracts/build/engine.min.py contracts/build/guard.min.py

# 3. The deployed contracts are those builds (reads the chain)
git checkout main && cd frontend && npm ci
node scripts/verify-onchain-code.mjs c11fa828f0f8b8efff80830c36074ad7acdebf69 ../deploy/deployments-v1.json
node scripts/verify-onchain-code.mjs ae29fc34a44744fbf44e63ddae1204e46fcdf053 ../deploy/deployments.json

# 4. The tests, at the head
git checkout ae29fc34a44744fbf44e63ddae1204e46fcdf053
python3 -m pytest && python3 tests/mutation_check.py
cd frontend && npm ci && npm run parity
```

Both verifications print `every deployed contract is the build at <commit>`
(run on 19 Oct 2026 against the public Studio and Bradbury RPC endpoints:
10 of 10 contracts for each release).
