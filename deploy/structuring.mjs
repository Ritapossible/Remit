// Scenario 2 on a FRESH guard, so the window contains only the split payments.
//
// Mixing an unrelated purchase into the window makes the record genuinely
// ambiguous, and a jury is right to be unsure. A clean window is not stagecraft
// — it is the scenario the rule describes.
import fs from "node:fs";
import { clientFor, accountFor, retry } from "./lib.mjs";

const network = process.argv[2] || "studio";
const code = fs.readFileSync("../contracts/build/remit.py");
const mandate = fs.readFileSync(`../mandates/demo-${network}.json`, "utf8");
const agentAddr = accountFor("agent").address;
const principal = clientFor(network, "principal");
const agent = clientFor(network, "agent");
const vendorA = accountFor("vendor").address;
const GEN = (n) => (BigInt(Math.round(n * 1000)) * (10n ** 15n)).toString();
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
let failures = 0;
const txs = [];

function check(label, actual, expected) {
  const ok = String(actual) === String(expected);
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}: ${actual}${ok ? "" : `  (expected ${expected})`}`);
}

const hash = await retry("deploy", () =>
  principal.deployContract({ code, args: [agentAddr, mandate, 2, false], leaderOnly: false }), 5);
const dr = await retry("receipt", () =>
  principal.waitForTransactionReceipt({ hash, status: "FINALIZED", retries: 300, interval: 3000 }), 5);
const address = dr?.data?.contract_address ?? dr?.contract_address;
console.log(`fresh guard ${address}\n  deploy ${hash}\n`);

async function send(client, fn, args, label) {
  const h = await retry(label, () => client.writeContract({ address, functionName: fn, args, value: 0n }), 4);
  const r = await retry(`${label} receipt`, () =>
    client.waitForTransactionReceipt({ hash: h, status: "FINALIZED", retries: 300, interval: 2500 }), 4);
  txs.push({ label, hash: h, result: r?.result_name, leader: r?.consensus_data?.leader_receipt?.[0]?.result?.status });
  return { hash: h, result: r?.result_name, leaderStatus: r?.consensus_data?.leader_receipt?.[0]?.result?.status, receipt: r };
}
const spendOf = async (id) => {
  const raw = await retry("get_spend", () => principal.readContract({ address, functionName: "get_spend", args: [id] }), 4);
  return typeof raw === "string" ? JSON.parse(raw) : raw;
};

console.log("A 0.45 GEN purchase under a 0.2 GEN per-payment cap, split 3 x 0.15:");
for (let i = 0; i < 3; i++) {
  await send(agent, "request_spend",
    [vendorA, GEN(0.15), "media", "", "", `invoice INV-88 part ${i + 1} of 3`], `split#${i}`);
  const s = await spendOf(i);
  console.log(`  payment ${i + 1}: ${s.state}  rules=${s.rules.join(",") || "-"}`);
}
let s = await spendOf(2);
check("third payment held", s.state, "held");
check("trigger", JSON.stringify(s.rules), '["structuring"]');
check("authorization withheld", s.authorization, "pending");

console.log("\n  waiting out the 60s response window (T9)...");
await sleep(65000);

console.log("\nadjudicating:");
const adj = await send(principal, "adjudicate", [2], "adjudicate");
console.log(`  consensus: ${adj.result}`);
const eq = adj.receipt?.consensus_data?.leader_receipt?.[0]?.eq_outputs;
if (eq) console.log("  leader said:", JSON.stringify(eq).slice(0, 260));
console.log("  votes:", (adj.receipt?.consensus_data?.validators ?? []).map(v => v.vote).join(", "));

s = await spendOf(2);
console.log(`  verdict=${s.verdict} reason=${s.reason} confidence=${s.confidence} artifact=${s.artifact}`);
check("consensus reached", adj.result, "MAJORITY_AGREE");
check("verdict recorded", s.verdict !== "", true);
check("case resolved", ["settled", "refused"].includes(s.state), true);

fs.writeFileSync(`structuring-${network}.json`, JSON.stringify({ address, deploy: hash, txs, final: s }, null, 2));
console.log(`\n${failures} failed checks`);
process.exit(failures === 0 ? 0 : 1);
