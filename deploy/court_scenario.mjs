// The court on chain: bonded challenges, clawback and tier 2/3 enforcement.
//
// A fresh guard and rail (attached, registered, funded; the agent posts a
// standing bond). Payments that clear by arithmetic are then challenged:
//
//   A  a single stock-footage payment challenged as "part of a split": the
//      payout waits for the ruling; recorded whatever the jury decides
//   B  a payment labelled media whose own claim says flight tickets, challenged
//      under the tier-3 purpose rule before the rail pays it
//   C  the same kind of payment, challenged after the rail paid it
//
// Verdicts are RECORDED, as in jury_scenarios.mjs. What is checked is the
// mechanics each verdict must produce: who was paid, what the rail refuses,
// what the guard refuses, what the principal can lift.
//
//   node court_scenario.mjs [studio|bradbury]
import fs from "node:fs";
import { clientFor, accountFor, compactJson, deployAgentSetup, sendTx, readView, readUntil } from "./lib.mjs";

const network = process.argv[2] || "studio";
// The court is what is under test here, not the payout delay, so this rail
// waits only a minute (the reference rail on Bradbury waits 40).
const FINALITY = Number(process.env.RAIL_FINALITY ?? 60);
const GEN = (n) => BigInt(Math.round(n * 1000)) * 10n ** 15n;
const mandate = compactJson(fs.readFileSync(`../mandates/demo-${network}.json`, "utf8"));
const WINDOW = JSON.parse(mandate).defaults.response_window_seconds;
const principal = clientFor(network, "principal");
const agent = clientFor(network, "agent");
const challenger = clientFor(network, "challenger");
const second = clientFor(network, "funder");
const vendor = accountFor("vendor").address;
const rpc = principal.chain.rpcUrls.default.http[0];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fmt = (v) => `${Number(v) / 1e18} GEN`;
const log = [];
const cases = {};
let failures = 0;

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

async function tx(client, address, fn, args, label, value = 0n) {
  const o = await sendTx(client, address, fn, args, label, value);
  log.push({ tx: label, hash: o.hash, consensus: o.consensus, leader: o.leader });
  console.log(`  - ${label}: ${o.applied ? "applied" : o.refused ? "refused" : o.consensus}`);
  return o;
}

console.log(`network ${network}, court rail finality ${FINALITY}s\n`);
const setup = await deployAgentSetup(network, principal, {
  agent: accountFor("agent").address, mandate, maxTier: 3, finality: FINALITY, bondFloor: GEN(0.01), fund: GEN(0.3),
});
const { guard, rail, registry } = setup;
log.push({ setup });
console.log(`guard ${guard}\nrail  ${rail}\nregistry ${registry}\n`);
await tx(agent, rail, "post_bond", [], "agent posts a 0.1 GEN bond", GEN(0.1));

const status = async () => readView(principal, rail, "status");
const challengeOf = async (id) => (await readView(principal, rail, "challenges"))[id];
const settledSpend = async (id) =>
  (await readUntil(() => readView(principal, guard, "get_spend", [id]), (x) => x.state !== "held", { seconds: 120 })).value;

// Open a challenge for the quoted bond, let the response window pass, rule.
async function challengeAndRule(client, spendId, rule, statement, cid, label) {
  const quote = await readView(principal, rail, "bond_quote", [spendId, rule, client.account.address]);
  check(`${label}: eligible`, quote.error, "");
  const opened = await tx(client, rail, "challenge", [spendId, rule, statement], `${label}: challenge (bond ${fmt(quote.bond)})`, BigInt(quote.bond));
  check(`${label}: challenge opened`, opened.applied, true);
  await readUntil(() => challengeOf(cid), (c) => !!c, { seconds: 120 });
  return BigInt(quote.bond);
}

async function rule(cid, label) {
  await sleep((WINDOW + 5) * 1000);
  const r = await tx(principal, rail, "rule", [cid], `${label}: rule`);
  const c = (await readUntil(() => challengeOf(cid), (x) => x.state !== "open", { seconds: r.agreed ? 300 : 30 })).value;
  console.log(`    verdict ${c.verdict} / ${c.reason} @${c.confidence} -> ${c.state}`);
  return { r, c };
}

// --- A: a single payment challenged as part of a split ---------------------
console.log("A. a cleared payment is challenged; its payout waits for the ruling");
await tx(agent, guard, "request_spend", [vendor, GEN(0.05).toString(), "media", "", "", "PO-7001 stock footage for the spring campaign"], "spend 0");
check("spend 0 cleared by arithmetic", (await settledSpend(0)).authorization, "authorized");
const bondA = await challengeAndRule(challenger, 0, "structuring", "This is one part of a larger order split into small payments.", 0, "A");
await sleep((FINALITY + 5) * 1000);
check("A: paying while challenged is refused", (await tx(agent, rail, "pay", [0], "A: pay 0 while challenged")).refused, true);
const agentBefore = await balance(accountFor("agent").address);
const A = await rule(0, "A");
cases.A = A.c;
check("A: ruled", ["dismissed", "upheld"].includes(A.c.state), true);
if (A.c.state === "dismissed") {
  check("A: the bond went to the agent", A.c.settlement.to_agent, String(bondA));
  check("A: dismissed payment now pays", (await tx(agent, rail, "pay", [0], "A: pay 0 after dismissal")).applied, true);
  const quoteAfter = await readView(principal, rail, "bond_quote", [0, "purpose", challenger.account.address]);
  check("A: the losing challenger's next bond doubled", BigInt(quoteAfter.bond), 2n * bondA);
} else {
  check("A: upheld, the unpaid payment is blocked", A.c.settlement.blocked, true);
}

// --- B: tier 3 upheld before the payout ------------------------------------
console.log("\nB. a payment whose own claim is not media, challenged under the tier-3 purpose rule before the rail pays");
await tx(agent, guard, "request_spend", [vendor, GEN(0.04).toString(), "media", "", "", "Flight tickets for the team offsite in Lisbon"], "spend 1");
check("spend 1 cleared by arithmetic (labelled media)", (await settledSpend(1)).authorization, "authorized");
await challengeAndRule(challenger, 1, "purpose", "The agent's own description says this paid for flight tickets, not media work.", 1, "B");
await tx(agent, guard, "request_spend", [vendor, GEN(0.01).toString(), "media", "", "", "PO-7002 b-roll clip"], "spend 2 (unpaid when B is ruled)");
const B = await rule(1, "B");
cases.B = B.c;
check("B: ruled", ["dismissed", "upheld"].includes(B.c.state), true);
if (B.c.state === "upheld") {
  check("B: tier", B.c.tier, 3);
  check("B: the payment was blocked, not paid", B.c.settlement.blocked, true);
  const st = (await readUntil(status, (s) => Number(s.frozen_tier) === 3, { seconds: 120 })).value;
  check("B: court froze the agent at tier 3", st.frozen_tier, 3);
  check("B: tier 3 revoked the payments requested before it", st.revoked_below, 3);
  await sleep((FINALITY + 5) * 1000);
  check("B: the rail refuses the clawed-back payment", (await tx(agent, rail, "pay", [1], "B: pay 1")).refused, true);
  check("B: the rail refuses the revoked payment", (await tx(agent, rail, "pay", [2], "B: pay 2")).refused, true);
  check("B: payment_of says revoked", (await readView(principal, rail, "payment_of", [2])).revoked, true);
  check("B: the guard refuses a new spend (frozen)", (await tx(agent, guard, "request_spend", [vendor, GEN(0.01).toString(), "media", "", "", "x"], "B: spend while frozen")).refused, true);
  check("B: the agent cannot lift it", (await tx(agent, rail, "lift_freeze", [], "B: agent lifts")).refused, true);
  check("B: the principal lifts it", (await tx(principal, rail, "lift_freeze", [], "B: principal lifts")).applied, true);
}

// --- C: upheld after the payout - clawed back from the agent's bond -------
console.log("\nC. the same kind of payment, challenged after the rail paid it");
const n = Number((await readView(principal, guard, "mandate_info")).spend_count);
await tx(agent, guard, "request_spend", [vendor, GEN(0.03).toString(), "media", "", "", "Gym membership for the operator, March"], `spend ${n}`);
check(`spend ${n} cleared`, (await settledSpend(n)).authorization, "authorized");
await sleep((FINALITY + 5) * 1000);
check(`C: rail pays spend ${n}`, (await tx(agent, rail, "pay", [n], `C: pay ${n}`)).applied, true);
const before = await status();
const cid = Number(before.challenge_count);
await challengeAndRule(second, n, "purpose", "The agent's own description is a personal gym membership - not producing or hosting media.", cid, "C");
const C = await rule(cid, "C");
cases.C = C.c;
check("C: ruled", ["dismissed", "upheld"].includes(C.c.state), true);
if (C.c.state === "upheld") {
  const after = await status();
  check("C: not blocked - it was already paid", C.c.settlement.blocked, false);
  check("C: clawed back into the treasury", BigInt(after.treasury) - BigInt(before.treasury), GEN(0.03));
  check("C: taken from the agent's bond", BigInt(before.standing) - BigInt(after.standing), BigInt(C.c.settlement.from_standing));
  await tx(principal, rail, "lift_freeze", [], "C: principal lifts");
}

// --- the bond and the registry ---------------------------------------------
console.log("\nD. the agent's bond stays while payments are challengeable; the registry binds the agent");
check("D: bond withdrawal inside the clawback window is refused", (await tx(agent, rail, "withdraw_bond", [1], "D: withdraw bond")).refused, true);
check("D: the agent cannot register the principal's guard", (await tx(agent, registry, "register", [guard, rail], "D: register by agent")).refused, true);
const listed = (await readView(principal, registry, "guards")).filter((g) => g.guard.toLowerCase() === guard.toLowerCase());
check("D: the registry lists the guard with its rail", listed.length === 1 && listed[0].rail.toLowerCase() === rail.toLowerCase(), true);

const final = await status();
console.log("\nrail status:", JSON.stringify(final));
fs.writeFileSync(`court-${network}.json`, JSON.stringify({ network, recorded_at: new Date().toISOString(), guard, rail, registry, finality_seconds: FINALITY, cases, status: final, log }, null, 2));
console.log(`\n${failures} failed checks`);
process.exit(failures === 0 ? 0 : 1);
