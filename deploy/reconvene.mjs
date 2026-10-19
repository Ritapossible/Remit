// Convene the jury again on a case whose round ended without a decision
// (no majority, or a validator timeout). Such a round changes nothing - the
// spend stays held - and a fresh round draws a new validator set. Records every
// round in the run's `rounds`; the run's top-level fields are the latest round.
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
// Keep every round, and make the top level the latest round as the chain
// records it, so the record never contradicts itself.
if (!run.rounds) run.rounds = [{ round: 1, adjudicate_tx: run.adjudicate_tx, consensus: run.consensus, validator_votes: run.validator_votes,
  verdict: run.verdict, outcome: run.outcome, authorization: run.authorization, state: run.state }];
const round = { round: run.rounds.length + 1, adjudicate_tx: h, consensus: o.consensus, verdict: s.verdict, reason: s.reason,
  confidence: s.confidence, artifact: s.artifact, outcome: s.outcome, authorization: s.authorization, state: s.state };
run.rounds.push(round);
Object.assign(run, { adjudicate_tx: h, consensus: o.consensus, validator_votes: null, verdict: s.verdict, reason: s.reason,
  confidence: s.confidence, artifact: s.artifact, outcome: s.outcome, authorization: s.authorization, state: s.state });
run.rounds_to_decide = run.rounds.length;
fs.writeFileSync(file, JSON.stringify(d, null, 2));
console.log(`${name} #${runNo} reconvened: ${o.consensus} -> ${s.verdict || "-"} / ${s.reason} @${s.confidence} -> ${s.outcome || "still held"}`);
