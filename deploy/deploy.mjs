// Deploy the reference guard for a network: the shared contracts (prompts,
// engine, registry) if not recorded yet, then a guard and its rail - the rail
// attached to the guard, both registered, the rail funded, the agent's
// standing bond posted.
//
//   node deploy.mjs [studio|bradbury] [--fresh-shared] [--no-rail] [--shadow]
import fs from "node:fs";
import { clientFor, accountFor, compactJson, readBuild, sharedContracts, deployFile, deployAgentSetup, sendTx, readView } from "./lib.mjs";

const network = process.argv[2] || "studio";
const shadow = process.argv.includes("--shadow");
const withRail = !shadow && !process.argv.includes("--no-rail");
// Bradbury finalises a transaction 27-31 minutes after creation (measured: still
// ACCEPTED at 1609 s, FINALIZED by 1852 s), so its rail waits 40 minutes.
const RAIL_FINALITY = Number(process.env.RAIL_FINALITY ?? (network === "studio" ? 60 : 2400));
const RAIL_FUND = BigInt(process.env.RAIL_FUND_MILLI ?? 500) * 10n ** 15n;
const AGENT_BOND = BigInt(process.env.AGENT_BOND_MILLI ?? 200) * 10n ** 15n;
const BOND_FLOOR = BigInt(process.env.BOND_FLOOR_MILLI ?? 10) * 10n ** 15n;
const MAX_TIER = 3;

const mandate = compactJson(fs.readFileSync(`../mandates/demo-${network}.json`, "utf8"));
const agent = accountFor("agent").address;
const client = clientFor(network, "principal");

console.log(`network   ${network}`);
console.log(`principal ${accountFor("principal").address}`);
console.log(`agent     ${agent}`);
console.log(`max_tier  ${MAX_TIER}   shadow ${shadow}`);
console.log(`guard     ${readBuild("guard").length} bytes + mandate ${mandate.length} bytes`);

const shared = await sharedContracts(network, client, { fresh: process.argv.includes("--fresh-shared") });
console.log(`engine    ${shared.engine}\nprompts   ${shared.prompts}\nregistry  ${shared.registry}`);

let rec;
if (withRail) {
  rec = await deployAgentSetup(network, client, {
    agent, mandate, maxTier: MAX_TIER, finality: RAIL_FINALITY, bondFloor: BOND_FLOOR, fund: RAIL_FUND,
  });
  const bond = await sendTx(clientFor(network, "agent"), rec.rail, "post_bond", [], "agent bond", AGENT_BOND);
  if (!bond.applied) throw new Error(`agent bond failed: ${bond.consensus} ${bond.leader}`);
  rec.agent_bond_tx = bond.hash;
  console.log(`\nguard     ${rec.guard}\nrail      ${rec.rail}  finality ${RAIL_FINALITY}s  funded ${Number(RAIL_FUND) / 1e18} GEN`);
  console.log(`          bond floor ${Number(BOND_FLOOR) / 1e18} GEN, agent bond ${Number(AGENT_BOND) / 1e18} GEN`);
} else {
  const g = await deployFile(client, readBuild("guard"), [agent, mandate, MAX_TIER, shadow, shared.engine], "deploy guard");
  rec = { guard: g.address, guard_tx: g.hash };
  const reg = await sendTx(client, shared.registry, "register", [g.address, ""], "register");
  if (!reg.applied) throw new Error(`register failed: ${reg.consensus} ${reg.leader}`);
  console.log(`\nguard     ${rec.guard}`);
}

const info = await readView(client, rec.guard, "mandate_info");
console.log("\n=== registered mandate ===");
console.log("principal ", info.principal);
console.log("agent     ", info.agent);
console.log("max_tier  ", info.max_tier, " shadow", info.shadow, " rail", info.rail || "(none)");
console.log("rules     ", info.rules.map((r) => `${r.id}(${r.type}${r.tier ? ` t${r.tier}` : ""})`).join(" "));

const path = "deployments.json";
const all = JSON.parse(fs.readFileSync(path, "utf8"));
const { prompts, prompts_tx, engine, engine_tx, registry, registry_tx } = all[network];
all[network] = {
  prompts, prompts_tx, engine, engine_tx, registry, registry_tx,
  address: rec.guard,
  deploy_tx: rec.guard_tx,
  agent,
  max_tier: MAX_TIER,
  shadow,
  at: new Date().toISOString(),
  ...(withRail
    ? { rail: rec.rail, rail_tx: rec.rail_tx, rail_finality_seconds: RAIL_FINALITY, bond_floor: String(BOND_FLOOR), agent_bond: String(AGENT_BOND) }
    : {}),
};
fs.writeFileSync(path, JSON.stringify(all, null, 2));
console.log("\nrecorded in deploy/deployments.json");
