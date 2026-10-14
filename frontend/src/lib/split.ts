import type { RuleInfo } from "./mandate";

/** Mirrors `split_windows` / `split_hold` in contracts/remit_core.py. The rail
 *  runs the Python; this lets the app say why before anyone signs, on networks
 *  whose simulations return no refusal reason. */
const SPLIT_PREDICATES = ["recipient_total_lte", "recipient_total_gte", "recipient_count_lte", "recipient_count_gte"];

export function splitWindows(rules: RuleInfo[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rules) if (r.type === "judgment" && SPLIT_PREDICATES.includes(r.predicate)) out[r.id] = Number(r.b);
  return out;
}

interface Summary {
  id: number;
  recipient: string;
  at: number;
  state: string;
  rules: string[];
  outcome: string;
}

/** "pending" (a later linked payment is held), "refused" (one was refused on
 *  split rules alone), or "" (pays). */
export function splitHold(spend: Summary, later: Summary[], rules: RuleInfo[]): "" | "pending" | "refused" {
  const windows = splitWindows(rules);
  const mine = spend.recipient.toLowerCase();
  let result: "" | "pending" = "";
  for (const o of later) {
    if (o.id <= spend.id || o.recipient.toLowerCase() !== mine) continue;
    const reach = Math.max(0, ...o.rules.map((r) => windows[r] ?? 0));
    if (reach <= 0 || o.at - spend.at >= reach) continue;
    if (o.state === "held") result = "pending";
    else if (o.outcome === "refused" && o.rules.every((r) => r in windows)) return "refused";
  }
  return result;
}

export const SPLIT_REASON = {
  pending: "waits: a later payment to this vendor is held as a split of it",
  refused: "refused with the split it belongs to",
} as const;
