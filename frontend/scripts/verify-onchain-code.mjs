// Verifies that the contracts deployed at the addresses in a deployments file
// are byte-for-byte the build committed at a given git commit.
//
// For each contract it fetches the deployed source with gen_getContractCode,
// hashes it, and compares the hash with `git show <commit>:contracts/build/<name>.min.py`.
// Nothing is trusted from the repository except the commit you name.
//
//   cd frontend && npm ci
//   node scripts/verify-onchain-code.mjs <commit> <deployments.json> [studio|bradbury ...]
//
//   # Release 1 (the build reviewed for the reward)
//   node scripts/verify-onchain-code.mjs c11fa828f0f8b8efff80830c36074ad7acdebf69 ../deploy/deployments-v1.json
//   # Milestone 1
//   node scripts/verify-onchain-code.mjs ae29fc34a44744fbf44e63ddae1204e46fcdf053 ../deploy/deployments.json
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createClient } from "genlayer-js";
import { studionet, testnetBradbury } from "genlayer-js/chains";

const [commit, file, ...nets] = process.argv.slice(2);
if (!commit || !file) {
  console.error("usage: node scripts/verify-onchain-code.mjs <commit> <deployments.json> [studio|bradbury ...]");
  process.exit(2);
}
const CHAINS = { studio: studionet, bradbury: testnetBradbury };
const ROLES = [["engine", "engine"], ["prompts", "prompts"], ["registry", "registry"], ["address", "guard"], ["rail", "rail"]];
const sha = (s) => createHash("sha256").update(s).digest("hex");
const built = (name) => execFileSync("git", ["show", `${commit}:contracts/build/${name}.min.py`], { encoding: "utf8" });

const deployments = JSON.parse(readFileSync(file, "utf8"));
let failed = 0;
for (const net of nets.length ? nets : Object.keys(CHAINS)) {
  if (!deployments[net]) continue;
  const client = createClient({ chain: CHAINS[net] });
  for (const [key, name] of ROLES) {
    const address = deployments[net][key];
    if (!address) continue;
    const want = sha(built(name));
    let got;
    try {
      got = sha(await client.getContractCode(address));
    } catch (e) {
      got = "unreadable: " + String(e?.message ?? e).slice(0, 60);
    }
    const ok = got === want;
    if (!ok) failed++;
    console.log(`${ok ? "match   " : "MISMATCH"} ${net.padEnd(9)} ${name.padEnd(9)} ${address}  ${got.slice(0, 64)}`);
  }
}
console.log(failed ? `${failed} contract(s) do not match ${commit}` : `every deployed contract is the build at ${commit}`);
process.exit(failed ? 1 : 0);
