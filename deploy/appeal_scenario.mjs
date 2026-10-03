// An appeal while a payout waits.
//
// The guard decides when a jury round is ACCEPTED; GenLayer lets anyone appeal
// that round until it is FINALIZED. The rail exists to make that safe: it pays
// only once a decision is `finality_seconds` old. This script measures it:
//
//   1. a held spend is released by the jury (separate purchases, the case the
//      jury has released in every decided round so far);
//   2. the principal appeals the adjudication transaction at once, posting
//      the network's minimum appeal bond;
//   3. while the appeal runs, the rail is asked to pay - it must refuse;
//   4. the transaction's status is polled to FINALIZED, and the verdict read
//      again - upheld or overturned, recorded either way;
//   5. after the finality delay, the rail pays exactly what the final state
//      says: the spend if it stayed authorized, nothing if it was overturned.
//
//   node appeal_scenario.mjs [studio|bradbury]
import fs from "node:fs";
import { clientFor, accountFor, compactJson, deployAgentSetup, sendTx, readView, readUntil, retry } from "./lib.mjs";

const network = process.argv[2] || "studio";
const FINALITY = Number(process.env.RAIL_FINALITY ?? (network === "studio" ? 300 : 2400));
const MAX_BOND = BigInt(process.env.MAX_APPEAL_BOND_MILLI ?? 3000) * 10n ** 15n;
const GEN = (n) => BigInt(Math.round(n * 1000)) * 10n ** 15n;
const RAW = "https://raw.githubusercontent.com/Ritapossible/Remit/main/examples/";
const mandate = compactJson(fs.readFileSync(`../mandates/demo-${network}.json`, "utf8"));
const principal = clientFor(network, "principal");
const agent = clientFor(network, "agent");
const vendor = accountFor("vendor").address;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();
const at = () => Math.round((Date.now() - t0) / 1000);
const log = [];
const timeline = [];
let failures = 0;

function check(label, actual, expected) {
  const ok = String(actual) === String(expected);
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}: ${actual}${ok ? "" : `  (expected ${expected})`}`);
  log.push({ check: label, actual: String(actual), expected: String(expected), ok });
}
async function tx(client, address, fn, args, label, value = 0n) {
  const o = await sendTx(client, address, fn, args, label, value);
  log.push({ tx: label, hash: o.hash, consensus: o.consensus, leader: o.leader, at: at() });
  console.log(`  - [${at()}s] ${label}: ${o.applied ? "applied" : o.refused ? "refused" : o.consensus}`);
  return o;
}
// The finalised state, read explicitly. After an appeal, Studio has been
// measured to serve a broken non-final copy of the appealed contract.
const readFinal = async (fn, args) => {
  const raw = await principal.readContract({ address: guard, functionName: fn, args, transactionHashVariant: "latest-final" });
  return typeof raw === "string" ? JSON.parse(raw) : raw;
};
let guard;
const statusOf = async (hash) => {
  const t = await retry("getTransaction", () => principal.getTransaction({ hash }), 4);
  return { status: String(t.statusName ?? t.status), result: String(t.resultName ?? t.result_name ?? ""), round: t };
};

console.log(`network ${network}, rail finality ${FINALITY}s\n`);
const setup = await deployAgentSetup(network, principal, {
  agent: accountFor("agent").address, mandate, maxTier: 3, finality: FINALITY, bondFloor: GEN(0.01), fund: GEN(0.4),
});
guard = setup.guard;
const { rail } = setup;
console.log(`guard ${guard}\nrail  ${rail}`);

console.log("\n1. A held spend, released by the jury");
await tx(agent, guard, "request_spend", [vendor, GEN(0.12).toString(), "hosting", "", "", "PO-5102 hosting renewal"], "spend 0");
await tx(agent, guard, "request_spend", [vendor, GEN(0.15).toString(), "media", "", "", "PO-5544 ad re-edit"], "spend 1");
await tx(agent, guard, "commit_artifact", [1, RAW + "invoices-INV-301-317-separate.json", "042ce8f8bffc859860336bc06cba911109489ce059cd8fdbd042d8f9d3427b22"], "commit");
const adj = await tx(principal, guard, "adjudicate", [1], "adjudicate");
const first = (await readUntil(() => readView(principal, guard, "get_spend", [1]), (x) => x.state !== "held", { seconds: 300 })).value;
console.log(`    verdict ${first.verdict} @${first.confidence} -> ${first.authorization}`);
timeline.push({ at: at(), event: "accepted", ...(await statusOf(adj.hash)), verdict: first.verdict, authorization: first.authorization });

console.log("\n2. The principal appeals the adjudication while it is not final");
let appeal = { attempted: false };
try {
  const bond = await principal.getMinAppealBond({ txId: adj.hash }).catch((e) => {
    appeal.bond_error = String(e?.message ?? e).slice(0, 200);
    return 0n;
  });
  appeal.min_bond = String(bond);
  if (bond > MAX_BOND) throw new Error(`minimum appeal bond ${bond} exceeds the ${MAX_BOND} this script may spend`);
  const hash = await principal.appealTransaction({ txId: adj.hash, value: bond });
  appeal = { ...appeal, attempted: true, hash: String(hash ?? ""), at: at() };
  console.log(`  - [${at()}s] appeal submitted, bond ${Number(bond) / 1e18} GEN`);
} catch (e) {
  appeal.error = String(e?.message ?? e).slice(0, 300);
  console.log(`  - appeal could not be submitted: ${appeal.error}`);
}
check("appeal submitted", appeal.attempted, true);

console.log("\n3. While the decision is not yet past the finality delay, the rail refuses to pay");
check("pay before the delay is refused", (await tx(agent, rail, "pay", [1], "pay 1 during appeal")).refused, true);

console.log("\n4. Follow the adjudication to FINALIZED");
let last = "";
for (;;) {
  const s = await statusOf(adj.hash).catch((e) => ({ status: last, result: "", error: String(e?.message ?? e).slice(0, 120) }));
  if (s.status !== last) {
    // While an appeal round re-executes, a read of the guard can fail; record it.
    const spend = await readView(principal, guard, "get_spend", [1]).catch((e) => ({ verdict: "?", authorization: `read failed: ${String(e?.shortMessage ?? e?.message ?? e).slice(0, 60)}` }));
    timeline.push({ at: at(), event: "status", status: s.status, result: s.result, verdict: spend.verdict, authorization: spend.authorization });
    console.log(`  - [${at()}s] ${s.status} ${s.result}  verdict ${spend.verdict} -> ${spend.authorization}`);
    last = s.status;
  }
  if (/FINALIZED/.test(s.status) || at() > 3 * 3600) break;
  await sleep(30000);
}
const final = await readFinal("get_spend", [1]);
// Is the guard still healthy at its current (non-final) state?
const health = {};
health.nonfinal_read = await readView(principal, guard, "get_spend", [1]).then(() => "ok").catch((e) => String(e?.details ?? e?.shortMessage ?? e).slice(0, 120));
health.code = await principal.getContractCode(guard).then((c) => `${c.length} bytes`).catch((e) => String(e?.details ?? e?.shortMessage ?? e).slice(0, 120));
console.log(`    guard after the appeal: non-final read ${health.nonfinal_read}; code ${health.code}`);
check("adjudication finalized", /FINALIZED/.test(last), true);
const outcome = final.authorization === first.authorization ? "upheld" : "overturned";
console.log(`    the appeal ${outcome} the verdict: ${first.verdict} -> ${final.verdict} (${final.authorization})`);

console.log("\n5. After the finality delay the rail pays what the final state says");
const decided = Number(final.decided_at);
const wait = decided + FINALITY + 10 - Math.floor(Date.now() / 1000);
if (wait > 0) await sleep(wait * 1000);
const paid = await tx(agent, rail, "pay", [1], "pay 1 after finality");
const payload = paid.receipt?.consensus_data?.leader_receipt?.[0]?.result?.payload ?? paid.receipt?.txExecutionResultName ?? "";
health.pay_result = String(payload).slice(0, 200);
console.log(`    rail answer: ${health.pay_result}`);
check(`rail ${final.authorization === "authorized" ? "pays" : "refuses"} the ${final.authorization} spend`, final.authorization === "authorized" ? paid.applied : paid.refused, true);

fs.writeFileSync(
  `appeal-${network}.json`,
  JSON.stringify({ network, recorded_at: new Date().toISOString(), guard, rail, finality_seconds: FINALITY, adjudicate_tx: adj.hash, appeal, first, final, outcome, health, timeline, log }, null, 2),
);
console.log(`\n${failures} failed checks`);
process.exit(failures === 0 ? 0 : 1);
