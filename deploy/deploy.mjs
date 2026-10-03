import fs from "node:fs";
import { clientFor, accountFor, retry, outcome, WAIT } from "./lib.mjs";

const network = process.argv[2] || "studio";
const shadow = process.argv.includes("--shadow");
// --rail also deploys a RemitRail bound to the new guard and funds it.
const withRail = process.argv.includes("--rail");
const RAIL_FINALITY = Number(process.env.RAIL_FINALITY ?? (network === "studio" ? 60 : 1800));
const RAIL_FUND = BigInt(process.env.RAIL_FUND_MILLI ?? 500) * 10n ** 15n;
const MAX_TIER = 2;

const code = fs.readFileSync("../contracts/build/remit.py");
const mandate = fs.readFileSync(`../mandates/demo-${network}.json`, "utf8");
const agent = accountFor("agent").address;
const client = clientFor(network, "principal");

console.log(`network   ${network}`);
console.log(`principal ${accountFor("principal").address}`);
console.log(`agent     ${agent}`);
console.log(`max_tier  ${MAX_TIER}   shadow ${shadow}`);
console.log(`contract  ${code.length} bytes`);

const hash = await retry("deploy", () =>
  client.deployContract({ code, args: [agent, mandate, MAX_TIER, shadow], leaderOnly: false }), 5);
console.log("\ndeploy tx:", hash);

const receipt = await retry("receipt", () =>
  client.waitForTransactionReceipt({ hash, status: WAIT, retries: 300, interval: 3000 }), 5);
const address = outcome(receipt).address;
console.log("status:", receipt?.status, "address:", address);

if (!address) {
  console.log("DEPLOY FAILED - receipt follows:");
  console.log(JSON.stringify(receipt, null, 2).slice(0, 3000));
  process.exit(1);
}

const info = await retry("mandate_info", () =>
  client.readContract({ address, functionName: "mandate_info", args: [] }), 5);
const parsed = typeof info === "string" ? JSON.parse(info) : info;
console.log("\n=== registered mandate ===");
console.log("principal ", parsed.principal);
console.log("agent     ", parsed.agent);
console.log("max_tier  ", parsed.max_tier, " shadow", parsed.shadow);
console.log("rules     ", parsed.rules.map(r => `${r.id}(${r.type})`).join(" "));
console.log("defaults  ", JSON.stringify(parsed.defaults));

let rail;
if (withRail) {
  const railHash = await retry("deploy rail", () =>
    client.deployContract({ code: fs.readFileSync("../contracts/rail.py"), args: [address, RAIL_FINALITY], leaderOnly: false }), 5);
  const rr = outcome(await retry("rail receipt", () => client.waitForTransactionReceipt({ hash: railHash, status: WAIT, retries: 300, interval: 3000 }), 5));
  if (!rr.applied) throw new Error(`rail deploy failed: ${rr.consensus} ${rr.leader}`);
  rail = rr.address;
  const fundHash = await retry("fund rail", () => client.writeContract({ address: rail, functionName: "fund", args: [], value: RAIL_FUND }), 5);
  const fr = outcome(await retry("fund receipt", () => client.waitForTransactionReceipt({ hash: fundHash, status: WAIT, retries: 300, interval: 3000 }), 5));
  if (!fr.applied) throw new Error(`rail funding failed: ${fr.consensus} ${fr.leader}`);
  console.log(`\nrail      ${rail}  finality ${RAIL_FINALITY}s  funded ${Number(RAIL_FUND) / 1e18} GEN`);
}

const path = "deployments.json";
const all = fs.existsSync(path) ? JSON.parse(fs.readFileSync(path, "utf8")) : {};
all[network] = { address, deploy_tx: hash, agent, max_tier: MAX_TIER, shadow, at: new Date().toISOString(), ...(rail ? { rail, rail_finality_seconds: RAIL_FINALITY } : {}) };
fs.writeFileSync(path, JSON.stringify(all, null, 2));
console.log("\nrecorded in deploy/deployments.json");
