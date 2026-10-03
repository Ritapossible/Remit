// The rail end to end: money moves only when the guard authorized it.
//
// A fresh guard and its rail. The principal funds the rail; the agent's spends
// go through the guard; anyone may ask the rail to pay. Every payout and every
// refusal is checked against balances read from the chain after the call.
//
//   node rail_scenario.mjs [studio]
import fs from "node:fs";
import { clientFor, accountFor, retry, outcome, WAIT, compactJson, readBuild, sharedContracts, readUntil, settledReceipt } from "./lib.mjs";

const network = process.argv[2] || "studio";
const FINALITY = Number(process.env.RAIL_FINALITY ?? 45);
const guardCode = readBuild("guard");
const railCode = fs.readFileSync("../contracts/rail.py");
const mandate = compactJson(fs.readFileSync(`../mandates/demo-${network}.json`, "utf8"));
const principal = clientFor(network, "principal");
const agent = clientFor(network, "agent");
const agentAddr = accountFor("agent").address;
const vendor = accountFor("vendor").address;
const OUTSIDER = "0x00000000000000000000000000000000000000e7"; // not on the allowlist
const rpc = principal.chain.rpcUrls.default.http[0];
const GEN = (n) => BigInt(Math.round(n * 1000)) * 10n ** 15n;
const fmt = (v) => `${Number(v) / 1e18} GEN`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
const log = [];

function check(label, actual, expected) {
  const ok = String(actual) === String(expected);
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}: ${actual}${ok ? "" : `  (expected ${expected})`}`);
  log.push({ check: label, actual: String(actual), expected: String(expected), ok });
}

async function balance(addr) {
  const res = await fetch(rpc, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getBalance", params: [addr, "latest"] }),
  });
  return BigInt((await res.json()).result ?? "0x0");
}

async function deploy(code, args, label) {
  const hash = await retry(label, () => principal.deployContract({ code, args, leaderOnly: false }), 5);
  const r = await retry(`${label} receipt`, () => principal.waitForTransactionReceipt({ hash, status: WAIT, retries: 300, interval: 3000 }), 5);
  const o = outcome(r);
  if (!o.applied) throw new Error(`${label} failed: ${o.consensus} ${o.leader}`);
  log.push({ tx: label, hash, address: o.address });
  return o.address;
}

async function send(client, address, fn, args, label, value = 0n) {
  const h = await retry(label, () => client.writeContract({ address, functionName: fn, args, value }), 4);
  let r = await retry(`${label} receipt`, () => client.waitForTransactionReceipt({ hash: h, status: WAIT, retries: 300, interval: 2500 }), 4);
  r = await settledReceipt(client, h, r);
  const o = outcome(r);
  log.push({ tx: label, hash: h, consensus: o.consensus, leader: o.leader });
  return o;
}

const read = async (address, fn, args = []) => {
  const raw = await retry(fn, () => principal.readContract({ address, functionName: fn, args }), 4);
  return typeof raw === "string" ? JSON.parse(raw) : raw;
};

// Wait until a balance changes (value sent by emit_transfer lands when the
// paying transaction finalises), or give up.
async function settledBalance(addr, before, seconds = 240) {
  for (let t = 0; t < seconds; t += 10) {
    const b = await balance(addr);
    if (b !== before) return b;
    await sleep(10000);
  }
  return balance(addr);
}

console.log(`network ${network}, rail finality delay ${FINALITY}s\n`);
const { engine } = await sharedContracts(network, principal);
const guard = await deploy(guardCode, [agentAddr, mandate, 2, false, engine], "deploy guard");
const rail = await deploy(railCode, [guard, FINALITY], "deploy rail");
console.log(`guard ${guard}\nrail  ${rail}\n`);

console.log("1. The principal funds the rail with 0.5 GEN");
let o = await send(principal, rail, "fund", [], "fund", GEN(0.5));
check("fund applied", o.applied, true);
check("rail balance", fmt(await balance(rail)), fmt(GEN(0.5)));

console.log("\n2. Spend 0: 0.15 GEN to an allowlisted vendor - authorized in the same transaction");
o = await send(agent, guard, "request_spend", [vendor, GEN(0.15).toString(), "media", "", "", "storyboard"], "spend 0");
let s = (await readUntil(() => read(guard, "settlement_of", [0]), (x) => x.authorization === "authorized", { seconds: 120 })).value;
check("guard says", s.authorization, "authorized");

console.log("\n3. Paying before the finality delay reverts");
o = await send(agent, rail, "pay", [0], "pay 0 early");
check("early pay refused by consensus (agreed on the revert)", o.refused, true);

console.log(`\n4. After ${FINALITY}s, anyone may trigger the payout; the vendor receives exactly 0.15 GEN`);
await sleep(FINALITY * 1000 + 5000);
const vendorBefore = await balance(vendor);
const railBefore = await balance(rail);
o = await send(agent, rail, "pay", [0], "pay 0");
check("pay applied", o.applied, true);
const vendorAfter = await settledBalance(vendor, vendorBefore);
check("vendor received", fmt(vendorAfter - vendorBefore), fmt(GEN(0.15)));
check("rail paid out", fmt(railBefore - (await balance(rail))), fmt(GEN(0.15)));

console.log("\n5. Paying the same spend twice reverts");
o = await send(agent, rail, "pay", [0], "pay 0 again");
check("double pay refused", o.refused, true);

console.log("\n6. Spend 1: a second 0.15 GEN to the same vendor - held for the jury (same-recipient trigger)");
o = await send(agent, guard, "request_spend", [vendor, GEN(0.15).toString(), "media", "", "", "edit"], "spend 1");
s = (await readUntil(() => read(guard, "settlement_of", [1]), (x) => x.authorization === "pending", { seconds: 120 })).value;
check("guard says", s.authorization, "pending");
const railMid = await balance(rail);
o = await send(agent, rail, "pay", [1], "pay 1 while held");
check("paying a held spend refused", o.refused, true);
check("rail balance unchanged", fmt(await balance(rail)), fmt(railMid));

console.log("\n7. Spend 2: 0.05 GEN to an address not on the allowlist - refused by arithmetic");
o = await send(agent, guard, "request_spend", [OUTSIDER, GEN(0.05).toString(), "media", "", "", "misc"], "spend 2");
s = (await readUntil(() => read(guard, "settlement_of", [2]), (x) => x.authorization === "refused", { seconds: 120 })).value;
check("guard says", s.authorization, "refused");
await sleep(FINALITY * 1000 + 5000);
o = await send(agent, rail, "pay", [2], "pay 2 refused");
check("paying a refused spend refused", o.refused, true);
check("outsider received nothing", fmt(await balance(OUTSIDER)), fmt(0n));

console.log("\n8. The agent cannot withdraw the treasury");
o = await send(agent, rail, "withdraw", [GEN(0.1).toString()], "agent withdraw");
check("agent withdraw refused", o.refused, true);

const status = await read(rail, "status");
console.log("\nrail status:", JSON.stringify(status));
check("paid exactly one spend", status.paid_count, 1);
check("rail holds the rest", fmt(BigInt(status.balance)), fmt(GEN(0.35)));

fs.writeFileSync(`rail-${network}.json`, JSON.stringify({ network, guard, rail, finality_seconds: FINALITY, log, status }, null, 2));
console.log(`\n${failures} failed checks`);
process.exit(failures === 0 ? 0 : 1);
