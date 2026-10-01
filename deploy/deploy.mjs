import fs from "node:fs";
import { clientFor, accountFor, retry, outcome, WAIT } from "./lib.mjs";

const network = process.argv[2] || "studio";
const shadow = process.argv.includes("--shadow");
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

const path = "deployments.json";
const all = fs.existsSync(path) ? JSON.parse(fs.readFileSync(path, "utf8")) : {};
all[network] = { address, deploy_tx: hash, agent, max_tier: MAX_TIER, shadow, at: new Date().toISOString() };
fs.writeFileSync(path, JSON.stringify(all, null, 2));
console.log("\nrecorded in deploy/deployments.json");
