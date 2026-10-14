// Milestone 1 on chain: the agent cannot be its own witness.
//
// One invoice, two places. examples/vendor/northlight/ stands for the vendor's
// own invoice host, and the mandate (mandates/demo-<network>.json) pins it for
// the vendor. examples/agent-uploads/ holds the SAME BYTES somewhere the agent
// can publish - the same host, another path. The ledger is the case the jury
// released in every earlier run: two payments to one vendor (0.12 hosting +
// 0.15 media), the second held for crossing the cap.
//
//   forged   the agent commits the agent-uploads copy: refused when committed;
//            the jury may only rule on the ledger; the payment is not made.
//   honest   the agent commits the vendor's copy: committed, fetched and
//            hash-checked by every validator ("verified"), and ruled on.
//
// Each run uses a FRESH guard on this network's Milestone 1 engine, so the
// 24-hour window holds only that run's two payments. What the jury rules is
// RECORDED; the mechanics - the refusal, the artifact state, that a forged
// case never pays - are CHECKED.
//
//   node evidence_scenario.mjs [studio|bradbury]      REPEAT=3 by default
import fs from "node:fs";
import { clientFor, accountFor, retry, outcome, WAIT, compactJson, readBuild, readUntil, settledReceipt } from "./lib.mjs";

const network = process.argv[2] || "studio";
const REPEAT = Number(process.env.REPEAT ?? 3);
const OUT = process.env.OUT ?? `evidence-${network}.json`;
const code = readBuild("guard");
const mandate = compactJson(fs.readFileSync(`../mandates/demo-${network}.json`, "utf8"));
const RESPONSE_WINDOW = JSON.parse(mandate).defaults.response_window_seconds;
const principal = clientFor(network, "principal");
const agent = clientFor(network, "agent");
const agentAddr = accountFor("agent").address;
const vendor = accountFor("vendor").address;
const RAW = "https://raw.githubusercontent.com/Ritapossible/Remit/main/examples/";
const DIGEST = "042ce8f8bffc859860336bc06cba911109489ce059cd8fdbd042d8f9d3427b22";
const GEN = (n) => (BigInt(Math.round(n * 1000)) * 10n ** 15n).toString();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const engine = JSON.parse(fs.readFileSync("deployments.json", "utf8"))[network].engine;

const CASES = {
  forged: { uri: RAW + "agent-uploads/invoices-INV-301-317.json", what: "the vendor's invoice, re-published by the agent outside the vendor's prefix" },
  honest: { uri: RAW + "vendor/northlight/invoices-INV-301-317.json", what: "the same invoice, from the vendor's pinned prefix" },
};
const PAYMENTS = [[0.12, "hosting", "PO-5102 hosting renewal"], [0.15, "media", "PO-5544 ad re-edit"]];

const prior = fs.existsSync(OUT) && !process.env.RESET ? JSON.parse(fs.readFileSync(OUT, "utf8")) : null;
const record = prior ?? { network, engine, mandate_evidence_sources: JSON.parse(mandate).evidence_sources, cases: CASES, payments: PAYMENTS, runs: [] };
const save = () => fs.writeFileSync(OUT, JSON.stringify(record, null, 2) + "\n");

async function send(client, address, fn, args, label) {
  const h = await retry(label, () => client.writeContract({ address, functionName: fn, args, value: 0n }), 4);
  let r = await retry(`${label} receipt`, () => client.waitForTransactionReceipt({ hash: h, status: WAIT, retries: 400, interval: 3000 }), 4);
  r = await settledReceipt(client, h, r);
  return { hash: h, ...outcome(r), receipt: r };
}
/** The contract's own words for a refusal: simulate the same call. */
async function refusalOf(client, address, fn, args) {
  try {
    await client.simulateWriteContract({ address, functionName: fn, args });
    return "";
  } catch (e) {
    return String(e?.details || e?.shortMessage || e?.message || e).slice(0, 300);
  }
}
const spendOf = async (address, id) => {
  const raw = await retry("get_spend", () => principal.readContract({ address, functionName: "get_spend", args: [id] }), 6);
  return typeof raw === "string" ? JSON.parse(raw) : raw;
};
async function deployGuard() {
  const hash = await retry("deploy", () => principal.deployContract({ code, args: [agentAddr, mandate, 3, false, engine], leaderOnly: false }), 5);
  const r = await retry("deploy receipt", () => principal.waitForTransactionReceipt({ hash, status: WAIT, retries: 300, interval: 3000 }), 5);
  return { address: outcome(r).address, hash };
}
const votes = (r) => r?.consensus_data?.validators?.map((v) => v.vote) ?? r?.lastRound?.validatorVotesName ?? [];

let failures = 0;
const check = (run, label, ok) => {
  run.checks[label] = !!ok;
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
};

console.log(`engine ${engine} on ${network}; ${REPEAT} runs per case`);
for (const [name, c] of Object.entries(CASES)) {
  for (let n = record.runs.filter((r) => r.case === name && r.done).length; n < REPEAT; n++) {
    console.log(`\n=== ${name} (run ${n + 1}/${REPEAT}): ${c.what}`);
    const run = { case: name, run: n + 1, uri: c.uri, checks: {} };
    record.runs = record.runs.filter((r) => !(r.case === name && r.run === n + 1));
    record.runs.push(run);
    const g = await deployGuard();
    run.guard = g.address;
    run.deploy_tx = g.hash;
    save();
    console.log(`  guard ${g.address}`);
    for (let i = 0; i < PAYMENTS.length; i++) {
      const [amt, cat, claim] = PAYMENTS[i];
      const o = await send(agent, g.address, "request_spend", [vendor, GEN(amt), cat, "", "", claim], `spend ${i}`);
      run[`spend_${i}_tx`] = o.hash;
    }
    const held = await readUntil(() => spendOf(g.address, 1), (x) => x.state === "held", { seconds: 120 });
    check(run, "the second payment is held", held.value.state === "held");

    const commit = await send(agent, g.address, "commit_artifact", [1, c.uri, DIGEST], "commit evidence");
    run.commit_tx = commit.hash;
    run.commit = commit.applied ? "committed" : commit.refused ? "refused" : commit.consensus;
    if (!commit.applied) run.commit_reason = await refusalOf(agent, g.address, "commit_artifact", [1, c.uri, DIGEST]);
    console.log(`  commit: ${run.commit}${run.commit_reason ? " - " + run.commit_reason.slice(0, 140) : ""}`);
    if (name === "forged") {
      check(run, "the forged evidence is refused when committed", commit.refused);
      check(run, "the refusal names the vendor's prefix", /must come from the vendor/.test(run.commit_reason ?? ""));
      // The agent's response window passes with no admissible evidence.
      await sleep((RESPONSE_WINDOW + 15) * 1000);
    } else {
      check(run, "the vendor's evidence is committed", commit.applied);
    }

    const adj = await send(principal, g.address, "adjudicate", [1], "adjudicate");
    const done = await readUntil(() => spendOf(g.address, 1), (x) => x.state !== "held", { seconds: adj.agreed ? 300 : 60 });
    const s = done.value;
    Object.assign(run, {
      adjudicate_tx: adj.hash, consensus: adj.consensus, validator_votes: votes(adj.receipt),
      verdict: s.verdict, reason: s.reason, confidence: s.confidence, artifact: s.artifact, outcome: s.outcome,
      authorization: s.authorization, state: s.state,
    });
    console.log(`  consensus ${adj.consensus} votes [${run.validator_votes.join(",")}]`);
    console.log(`  verdict ${s.verdict} / ${s.reason} @${s.confidence}  artifact ${s.artifact}  ->  ${s.outcome} (${s.authorization})`);
    if (name === "forged") {
      check(run, "the jury saw no evidence (artifact absent)", s.artifact === "absent" || !adj.agreed);
      check(run, "the forged case is not paid", s.authorization !== "authorized");
    } else {
      check(run, "every validator fetched and hash-checked it (artifact verified)", s.artifact === "verified" || !adj.agreed);
      check(run, "the case resolved", ["settled", "refused"].includes(s.state) || !adj.agreed);
    }
    run.done = true;
    save();
  }
}

const by = (name) => record.runs.filter((r) => r.case === name);
record.summary = {
  forged: { runs: by("forged").length, refused_at_commit: by("forged").filter((r) => r.commit === "refused").length,
            paid: by("forged").filter((r) => r.authorization === "authorized").length },
  honest: { runs: by("honest").length, verified: by("honest").filter((r) => r.artifact === "verified").length,
            released: by("honest").filter((r) => r.authorization === "authorized").length,
            verdicts: by("honest").map((r) => `${r.verdict} ${r.confidence}`) },
};
record.failures = record.runs.reduce((n, r) => n + Object.values(r.checks).filter((v) => !v).length, 0);
record.finished = new Date().toISOString();
save();
console.log("\n" + JSON.stringify(record.summary, null, 2));
console.log(`${record.failures} failed checks -> deploy/${OUT}`);
process.exit(record.failures ? 1 : 0);
