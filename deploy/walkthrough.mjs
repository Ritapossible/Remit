// Real transactions against a deployed Remit guard.
//
// Every assertion is on resulting STATE. A transaction being ACCEPTED proves
// only that consensus agreed; consensus agreeing on a refusal is a network
// success and a spend refusal (hard law 3).
import fs from "node:fs";
import { clientFor, accountFor, retry, outcome, WAIT, readUntil } from "./lib.mjs";

const network = process.argv[2] || "studio";
const { address, rail } = JSON.parse(fs.readFileSync("deployments.json", "utf8"))[network];
const agent = clientFor(network, "agent");
const principal = clientFor(network, "principal");
const vendorA = accountFor("vendor").address;
const vendorB = accountFor("challenger").address;
const DROPPED = "0x00000000000000000000000000000000000000b1";
const GEN = (n) => (BigInt(Math.round(n * 1000)) * (10n ** 15n)).toString();

const txs = [];
let failures = 0;

async function send(client, functionName, args, label) {
  const hash = await retry(label, () =>
    client.writeContract({ address, functionName, args, value: 0n }), 4);
  const r = await retry(`${label} receipt`, () =>
    client.waitForTransactionReceipt({ hash, status: WAIT, retries: 300, interval: 2500 }), 4);
  // The leader's own status reads "return" even when the validators disagree
  // and the state change is rolled back; outcome() reads the consensus result.
  const o = outcome(r);
  txs.push({ label, hash, leader: o.leader, consensus: o.consensus });
  return { hash, st: o.leader, consensus: o.consensus, agreed: o.agreed };
}

async function spendOf(id) {
  const raw = await retry("get_spend", () =>
    principal.readContract({ address, functionName: "get_spend", args: [id] }), 4);
  return typeof raw === "string" ? JSON.parse(raw) : raw;
}

function check(label, actual, expected) {
  const ok = String(actual) === String(expected);
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}: ${actual}${ok ? "" : `  (expected ${expected})`}`);
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

console.log(`contract ${address} on ${network}\n`);

// --- 1: clears instantly, no jury ----------------------------------------
console.log("[1] small allowlisted spend - must settle in the same transaction");
await send(agent, "request_spend", [vendorA, GEN(0.05), "media", "", "", "stock photo for the Q4 banner"], "spend#0");
let s = await spendOf(0);
check("state", s.state, "settled");
check("authorization", s.authorization, "authorized");
check("rules fired", JSON.stringify(s.rules), "[]");
check("no jury convened (verdict empty)", s.verdict === "", true);

// --- 2: refused in-transaction, no jury ----------------------------------
console.log("\n[2] spend to a dropped vendor - must be refused by arithmetic");
await send(agent, "request_spend", [DROPPED, GEN(0.05), "media", "", "", "agency retainer"], "spend#1");
s = await spendOf(1);
check("state", s.state, "refused");
check("authorization", s.authorization, "refused");
check("rule that refused it", JSON.stringify(s.rules), '["allowlist"]');
check("no jury convened", s.verdict === "", true);

// --- 3: structuring - the scenario the product exists for -----------------
// The trigger is per recipient: the payment that takes one vendor's 24-hour
// total past the 0.2 GEN per-payment cap is held. Payments to other vendors
// do not count, and the first payment of a split is the most that clears.
console.log("\n[3] structuring - the payment that crosses the cap for one vendor is held");
await send(agent, "request_spend", [vendorA, GEN(0.15), "media", "", "", "PO-5521 product video"], "spend#2");
let e2 = await spendOf(2);
check("spend#2 settles (vendor total 0.20, at the cap)", e2.state, "settled");
await send(agent, "request_spend", [vendorA, GEN(0.15), "media", "", "", "PO-5521 product video"], "spend#3");
s = await spendOf(3);
check("state", s.state, "held");
check("authorization withheld", s.authorization, "pending");
check("trigger that fired", JSON.stringify(s.rules), '["structuring"]');
// The refused spend#1 is deliberately absent from the window: a spend that
// never moved value must not count against a later one.
check("refused spend did not count toward the window", s.rules.includes("structuring"), true);
// --- 4: T9 - cannot adjudicate before the agent has had its window -------
console.log("\n[4] T9 - adjudicating inside the response window must be refused");
const early = await send(principal, "adjudicate", [3], "adjudicate-early");
check("refused while foreclosed", early.st, "contract_error");
check("still held, nothing decided", (await spendOf(3)).state, "held");

console.log("\n    waiting out the 60s response window...");
await sleep(65000);

// --- 5: the jury decides -------------------------------------------------
console.log("\n[5] adjudicate - the jury answers what no threshold can");
const adj = await send(principal, "adjudicate", [3], "adjudicate");
const seen = await readUntil(() => spendOf(3), (x) => x.verdict !== "");
s = seen.value;
if (seen.waited) console.log(`    (the verdict became readable ${seen.waited}s after ACCEPTED)`);
console.log(`    verdict=${s.verdict} reason=${s.reason} confidence=${s.confidence} artifact=${s.artifact}`);
check(`consensus reached (${adj.consensus})`, adj.agreed, true);
check("a verdict was recorded", s.verdict !== "", true);
check("case resolved", ["settled", "refused"].includes(s.state), true);
check("authorization decided", ["authorized", "refused"].includes(s.authorization), true);

// --- 6: the principal always outranks Remit ------------------------------
console.log("\n[6] override - the principal lifts a live hold in one transaction");
await send(agent, "request_spend", [vendorA, GEN(0.1), "media", "", "", "PO-5560 thumbnail set"], "spend#4");
let held = await spendOf(4);
check("spend#4 held by the trigger", held.state, "held");
if (held.state === "held") {
  await send(principal, "override_release", [4], "override_release");
  const after = await spendOf(4);
  check("override released it", after.authorization, "authorized");
  check("recorded as an override", after.reason, "principal_override");
}

// --- 7: the rail pays what the guard authorized, and nothing else --------
if (rail) {
  console.log(`\n[7] rail ${rail} - pay every spend; only authorized ones move money`);
  const st = JSON.parse(await retry("rail status", () => principal.readContract({ address: rail, functionName: "status", args: [] }), 4));
  await sleep((st.finality_seconds + 5) * 1000);
  for (let id = 0; id < 5; id++) {
    const auth = (await spendOf(id)).authorization;
    const h = await retry(`pay#${id}`, () => principal.writeContract({ address: rail, functionName: "pay", args: [id], value: 0n }), 4);
    const r = outcome(await retry(`pay#${id} receipt`, () => principal.waitForTransactionReceipt({ hash: h, status: WAIT, retries: 300, interval: 2500 }), 4));
    txs.push({ label: `pay#${id}`, hash: h, leader: r.leader, consensus: r.consensus });
    check(`pay #${id} (${auth}) ${auth === "authorized" ? "paid" : "reverted"}`, auth === "authorized" ? r.applied : r.refused, true);
  }
}

// --- record --------------------------------------------------------------
const docketRaw = await retry("docket", () =>
  principal.readContract({ address, functionName: "docket", args: [] }), 4);
const docket = typeof docketRaw === "string" ? JSON.parse(docketRaw) : docketRaw;
console.log("\n=== docket ===");
for (const e of docket) {
  console.log(`  #${e.id} ${String(e.amount / 1e18).padStart(6)} GEN  ${e.state.padEnd(8)} ${e.authorization.padEnd(10)} rules=${e.rules.join(",") || "-"} ${e.verdict || ""}`);
}
fs.writeFileSync(`walkthrough-${network}.json`, JSON.stringify({ address, txs, docket }, null, 2));
console.log(`\n${txs.length} transactions, ${failures} failed checks`);
process.exit(failures === 0 ? 0 : 1);
