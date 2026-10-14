// Closes a held spend whose jury never voted: after held_at + response window,
// resolve_deadline applies the mandate's default (refuse). Usage:
//   node deploy/close_deadline.mjs <network> <guard> <spend_id>
import { clientFor, sendTx, readView } from "./lib.mjs";
const [network, guard, id] = process.argv.slice(2);
const principal = clientFor(network, "principal");
const r = await sendTx(principal, guard, "resolve_deadline", [Number(id)], "resolve_deadline");
const s = await readView(principal, guard, "get_spend", [Number(id)]);
console.log(JSON.stringify({ tx: r.hash, applied: r.applied, state: s.state, outcome: s.outcome, authorization: s.authorization, verdict: s.verdict, reason: s.reason }));
