// Isolation (T6): a jury running on one guard does not delay another's spends.
//
// Transactions on one Intelligent Contract execute in order, which is why
// Remit deploys a guard per agent. This measures it: guard A gets a held
// payment and its jury is convened; while that round runs, guard B's agent
// (a different key) sends payments to B. B's payments must be accepted while
// A's round is still deciding, at about the latency they have when A is idle.
//
//   node isolation_scenario.mjs [studio|bradbury]
import fs from "node:fs";
import { clientFor, accountFor, compactJson, deployFile, readBuild, sharedContracts, sendTx, readView } from "./lib.mjs";

const network = process.argv[2] || "studio";
const GEN = (n) => (BigInt(Math.round(n * 1000)) * 10n ** 15n).toString();
const mandate = compactJson(fs.readFileSync(`../mandates/demo-${network}.json`, "utf8"));
const WINDOW = JSON.parse(mandate).defaults.response_window_seconds;
const principal = clientFor(network, "principal");
const agentA = clientFor(network, "agent");
const agentB = clientFor(network, "challenger");
const vendor = accountFor("vendor").address;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = () => Date.now() / 1000;
let failures = 0;
const log = [];
function check(label, ok, detail = "") {
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}${detail ? `: ${detail}` : ""}`);
  log.push({ check: label, ok, detail });
}
async function timed(client, address, fn, args, label) {
  const t = now();
  const o = await sendTx(client, address, fn, args, label);
  const r = { label, hash: o.hash, consensus: o.consensus, applied: o.applied, started: t, done: now(), seconds: Math.round(now() - t) };
  log.push(r);
  console.log(`  - ${label}: ${o.applied ? "applied" : o.consensus} in ${r.seconds}s`);
  return r;
}

const { engine } = await sharedContracts(network, principal);
const A = (await deployFile(principal, readBuild("guard"), [accountFor("agent").address, mandate, 3, false, engine], "deploy guard A")).address;
const B = (await deployFile(principal, readBuild("guard"), [accountFor("challenger").address, mandate, 3, false, engine], "deploy guard B")).address;
console.log(`guard A ${A}\nguard B ${B}\n`);

console.log("1. Baseline: B's payments while A is idle");
const base = [];
for (let i = 0; i < 2; i++) base.push(await timed(agentB, B, "request_spend", [vendor, GEN(0.01), "media", "", "", `baseline ${i}`], `B spend ${i} (A idle)`));

console.log("\n2. A's payment is held and its jury convened; B keeps paying meanwhile");
await timed(agentA, A, "request_spend", [vendor, GEN(0.15), "media", "", "", "PO-1 part 1"], "A spend 0");
await timed(agentA, A, "request_spend", [vendor, GEN(0.15), "media", "", "", "PO-1 part 2"], "A spend 1 (held)");
await sleep((WINDOW + 5) * 1000);
const jury = timed(principal, A, "adjudicate", [1], "A adjudicate (jury)");
await sleep(3000);
const during = [];
for (let i = 0; i < 2; i++) during.push(await timed(agentB, B, "request_spend", [vendor, GEN(0.01), "media", "", "", `during ${i}`], `B spend ${i + 2} (A's jury running)`));
const j = await jury;

const avg = (xs) => Math.round(xs.reduce((a, x) => a + x.seconds, 0) / xs.length);
console.log(`\n   A's jury round: ${j.seconds}s. B's payments: ${avg(base)}s idle, ${avg(during)}s during A's round.`);
check("every B payment applied", [...base, ...during].every((x) => x.applied));
check("B's first payment was accepted while A's jury round was still running", during[0].done < j.done,
  during.map((x) => `${Math.round(j.done - x.done)}s before A's round ended`).join(", "));
const docketB = await readView(principal, B, "docket");
check("B recorded all four payments, none held", docketB.length === 4 && docketB.every((s) => s.state === "settled"));

fs.writeFileSync(`isolation-${network}.json`, JSON.stringify({ network, recorded_at: new Date().toISOString(), A, B, jury_seconds: j.seconds, b_idle_avg: avg(base), b_during_avg: avg(during), log }, null, 2));
console.log(`\n${failures} failed checks`);
process.exit(failures ? 1 : 0);
