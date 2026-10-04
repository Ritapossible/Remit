// The first slice of a split, on chain: the rail does not pay it while the
// slice that tripped the structuring trigger is held, and refuses it with the
// split. A control pair to the other vendor, released, pays both slices.
//
// A fresh guard and rail (not registered), so the 24-hour window and the
// daily cap hold only this run's payments. The mandate is the network's demo
// mandate: per-payment cap 0.20 GEN, structuring at more than 0.20 GEN to one
// vendor in 24 hours.
//
// JURY=1: the second slice of A is decided by the jury (adjudicate, no
// artifact, the ledger alone) instead of the principal. The verdict is
// recorded, not asserted; the rail is checked against whatever was decided.
//
//   node split_scenario.mjs [studio|bradbury]        JURY=1 for the jury path
import fs from "node:fs";
import { clientFor, accountFor, compactJson, readBuild, sharedContracts, deployFile, sendTx, readView, readUntil } from "./lib.mjs";

const network = process.argv[2] || "studio";
const FINALITY = Number(process.env.RAIL_FINALITY ?? (network === "studio" ? 60 : 2400));
const mandateText = fs.readFileSync(`../mandates/demo-${network}.json`, "utf8");
const mandate = compactJson(mandateText);
const [VENDOR, OTHER] = JSON.parse(mandateText).vendor_lists.vendors;
const principal = clientFor(network, "principal");
const agent = clientFor(network, "agent");
const agentAddr = accountFor("agent").address;
const GEN = (n) => BigInt(Math.round(n * 1000)) * 10n ** 15n;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const JURY = process.env.JURY === "1";
const OUT = `split-${JURY ? "jury-" : ""}${network}.json`;
const record = { network, decided_by: JURY ? "jury (adjudicate)" : "principal (override)", finality_seconds: FINALITY, started: new Date().toISOString(), txs: [], checks: [] };
const save = () => fs.writeFileSync(OUT, JSON.stringify(record, null, 2) + "\n");
let failures = 0;

function check(label, actual, expected) {
  const ok = String(actual) === String(expected);
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}: ${actual}${ok ? "" : `  (expected ${expected})`}`);
  record.checks.push({ check: label, actual: String(actual), expected: String(expected), ok });
  save();
}

// The revert's message, from the leader's stderr ("" where a node does not return it).
async function reason(client, hash) {
  const tx = await client.getTransaction({ hash }).catch(() => null);
  const text = JSON.stringify(tx ?? {}, (k, v) => (typeof v === "bigint" ? v.toString() : v));
  return (text.match(/Exception: (\[EXPECTED\][^"\\]*)/) || [, ""])[1];
}

async function send(client, address, fn, args, label, value = 0n) {
  const o = await sendTx(client, address, fn, args, label, value);
  const error = o.refused ? await reason(client, o.hash) : "";
  record.txs.push({ tx: label, hash: o.hash, consensus: o.consensus, leader: o.leader, ...(o.refused ? { error } : {}) });
  save();
  console.log(`    ${label}: ${o.consensus} ${o.leader} ${o.hash}`);
  return { ...o, error };
}
const because = (o, text) => (o.refused ? (o.error ? o.error.includes(text) : "no message on this node") : "not refused");

const spend = (i) => readView(principal, guard, "get_spend", [i]);
const settled = (i, want) => readUntil(() => readView(principal, guard, "settlement_of", [i]), (x) => x.authorization === want, { seconds: 300 });

console.log(`network ${network}, rail finality ${FINALITY}s`);
const { engine } = await sharedContracts(network, principal);
const g = await deployFile(principal, readBuild("guard"), [agentAddr, mandate, 3, false, engine], "deploy guard");
const r = await deployFile(principal, readBuild("rail"), [g.address, FINALITY, GEN(0.01)], "deploy rail");
const guard = g.address;
const rail = r.address;
Object.assign(record, { guard, guard_tx: g.hash, rail, rail_tx: r.hash, vendor: VENDOR, other: OTHER });
console.log(`guard ${guard}\nrail  ${rail}`);
check("attach rail", (await send(principal, guard, "attach_rail", [rail], "attach rail")).applied, true);
check("fund rail 0.5 GEN", (await send(principal, rail, "fund", [], "fund rail", GEN(0.5))).applied, true);

console.log("\nA. 0.15 then 0.08 GEN to one vendor: the second slice trips structuring");
await send(agent, guard, "request_spend", [VENDOR, GEN(0.15).toString(), "media", "", "", "PO-7101 launch video, part 1"], "spend 0");
check("spend 0 authorized", (await settled(0, "authorized")).value.authorization, "authorized");
await send(agent, guard, "request_spend", [VENDOR, GEN(0.08).toString(), "media", "", "", "PO-7101 launch video, part 2"], "spend 1");
const s1 = (await readUntil(() => spend(1), (x) => x.state === "held", { seconds: 300 })).value;
check("spend 1 held", s1.state, "held");
check("spend 1 rules", JSON.stringify(s1.rules), JSON.stringify(["structuring"]));

console.log(`\n   waiting out the ${FINALITY}s finality delay on spend 0`);
await sleep(FINALITY * 1000 + 10000);
let o = await send(agent, rail, "pay", [0], "pay 0 while 1 held");
check("pay 0 while the split is held: refused", o.refused, true);
check("  because the split is held", because(o, "held as a split"), true);
if (!JURY) {
  check("refuse spend 1 (principal)", (await send(principal, guard, "override_refuse", [1], "override_refuse 1")).applied, true);
  await readUntil(() => spend(1), (x) => x.state === "refused", { seconds: 300 });
  o = await send(agent, rail, "pay", [0], "pay 0 after refusal");
  check("pay 0 after the split is refused: refused", o.refused, true);
  check("  because the split was refused", because(o, "refused with the split"), true);
  check("spend 0 unpaid on the rail", (await readView(principal, rail, "payment_of", [0])).paid ?? false, false);
} else {
  // The response window (60 s in the demo mandate) has passed with the delay.
  const adj = await send(principal, guard, "adjudicate", [1], "adjudicate 1");
  check("jury round agreed", adj.agreed, true);
  const s1j = (await readUntil(() => spend(1), (x) => x.state !== "held", { seconds: 600 })).value;
  const votes = adj.receipt?.consensus_data?.validators?.map((v) => v.vote) ?? adj.receipt?.lastRound?.validatorVotesName ?? [];
  record.jury = { adjudicate_tx: adj.hash, consensus: adj.consensus, votes, state: s1j.state, verdict: s1j.verdict,
    reason: s1j.reason, confidence: s1j.confidence, outcome: s1j.outcome, rules: s1j.rules };
  save();
  console.log(`   jury: ${s1j.verdict} (${s1j.reason}, ${s1j.confidence}) -> spend 1 ${s1j.state}, outcome ${s1j.outcome}`);
  check("spend 1 decided", ["settled", "refused"].includes(s1j.state), true);
  check("spend 1 rules unchanged", JSON.stringify(s1j.rules), JSON.stringify(["structuring"]));
  o = await send(agent, rail, "pay", [0], "pay 0 after the jury");
  if (s1j.state === "refused") {
    check("pay 0 after a jury refusal: refused", o.refused, true);
    check("  because the split was refused", because(o, "refused with the split"), true);
    check("spend 0 unpaid on the rail", (await readView(principal, rail, "payment_of", [0])).paid ?? false, false);
  } else {
    check("pay 0 after a jury release: paid", o.applied, true);
  }
}

console.log("\nB. Control: 0.15 then 0.08 GEN to the other vendor, the second released");
await send(agent, guard, "request_spend", [OTHER, GEN(0.15).toString(), "hosting", "", "", "PO-5102 hosting renewal"], "spend 2");
check("spend 2 authorized", (await settled(2, "authorized")).value.authorization, "authorized");
await send(agent, guard, "request_spend", [OTHER, GEN(0.08).toString(), "media", "", "", "PO-5544 ad re-edit"], "spend 3");
check("spend 3 held", (await readUntil(() => spend(3), (x) => x.state === "held", { seconds: 300 })).value.state, "held");
console.log(`   waiting out the ${FINALITY}s finality delay on spend 2`);
await sleep(FINALITY * 1000 + 10000);
o = await send(agent, rail, "pay", [2], "pay 2 while 3 held");
check("pay 2 while spend 3 held: refused", o.refused, true);
check("  because the split is held", because(o, "held as a split"), true);
check("release spend 3 (principal)", (await send(principal, guard, "override_release", [3], "override_release 3")).applied, true);
await settled(3, "authorized");
console.log(`   waiting out the ${FINALITY}s finality delay`);
await sleep(FINALITY * 1000 + 10000);
check("pay 2 after release", (await send(agent, rail, "pay", [2], "pay 2")).applied, true);
check("pay 3 after release", (await send(agent, rail, "pay", [3], "pay 3")).applied, true);

record.rail_status = await readView(principal, rail, "status");
record.finished = new Date().toISOString();
record.failures = failures;
save();
console.log(`\n${failures ? `${failures} FAILED` : "all checks passed"} -> deploy/${OUT}`);
process.exit(failures ? 1 : 0);
