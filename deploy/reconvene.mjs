// Convene the jury again on a case whose round ended without a decision
// (no majority, or a validator timeout). Such a round changes nothing - the
// spend stays held - and a fresh round draws a new validator set. Records the
// second attempt next to the first in the scenario file.
//   node reconvene.mjs <network> <file.json> <case> <run>
import fs from "node:fs";
import { clientFor, retry, outcome, WAIT, settledReceipt, readUntil } from "./lib.mjs";
const [network, file, name, runNo] = process.argv.slice(2);
const c = clientFor(network, "principal");
const d = JSON.parse(fs.readFileSync(file, "utf8"));
const run = d.runs.find((r) => r.case === name && String(r.run) === String(runNo));
const h = await retry("adjudicate", () => c.writeContract({ address: run.guard, functionName: "adjudicate", args: [1], value: 0n }), 4);
let r = await retry("receipt", () => c.waitForTransactionReceipt({ hash: h, status: WAIT, retries: 400, interval: 3000 }), 4);
r = await settledReceipt(c, h, r);
const o = outcome(r);
const read = async () => JSON.parse(await c.readContract({ address: run.guard, functionName: "get_spend", args: [1] }));
const s = (await readUntil(read, (x) => x.state !== "held", { seconds: o.agreed ? 300 : 30 })).value;
run.reconvened = { adjudicate_tx: h, consensus: o.consensus, verdict: s.verdict, reason: s.reason, confidence: s.confidence, artifact: s.artifact, outcome: s.outcome, authorization: s.authorization };
fs.writeFileSync(file, JSON.stringify(d, null, 2));
console.log(`${name} #${runNo} reconvened: ${o.consensus} -> ${s.verdict || "-"} / ${s.reason} @${s.confidence} -> ${s.outcome || "still held"}`);
