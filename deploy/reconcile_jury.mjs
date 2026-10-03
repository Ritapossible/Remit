// Re-read every recorded jury run from the chain: the guard's decision for the
// held spend, and the adjudication's consensus result. A receipt can be
// returned before its round is decided (seen on Bradbury), so the record is
// corrected from the chain itself, never from what the script saw first.
//   node reconcile_jury.mjs <network> <file.json> [...]
import fs from "node:fs";
import { clientFor, retry, outcome } from "./lib.mjs";
const [network, ...files] = process.argv.slice(2);
const c = clientFor(network, "principal");
for (const file of files) {
  const d = JSON.parse(fs.readFileSync(file, "utf8"));
  for (const run of d.runs) {
    const s = JSON.parse(await retry("get_spend", () => c.readContract({ address: run.guard, functionName: "get_spend", args: [1] }), 4));
    const t = await retry("tx", () => c.getTransaction({ hash: run.adjudicate_tx }), 4);
    const o = outcome(t);
    const before = `${run.verdict || "-"}/${run.outcome || "-"}/${run.consensus}`;
    Object.assign(run, {
      consensus: o.consensus,
      validator_votes: t?.lastRound?.validatorVotesName ?? run.validator_votes,
      verdict: s.verdict, reason: s.reason, confidence: s.confidence, artifact: s.artifact,
      outcome: s.outcome, authorization: s.authorization, reconciled_from_chain: true,
    });
    console.log(`${file} ${run.case} #${run.run}: ${before} -> ${s.verdict}/${s.outcome}/${o.consensus} (${s.reason} @${s.confidence})`);
  }
  fs.writeFileSync(file, JSON.stringify(d, null, 2));
}
