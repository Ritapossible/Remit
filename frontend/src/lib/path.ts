import type { SpendView } from "../chain/remit";
import type { MandateInfo } from "./mandate";

export type Path = "none" | "reflex" | "jury" | "override" | "deadline" | "pending";

/** How a spend was decided — the product's thesis in one word per row. */
export function pathOf(s: SpendView, m: MandateInfo | null): { path: Path; rule?: string } {
  const rule = s.rules[0];
  const kind = m?.rules.find((r) => r.id === rule)?.type;
  if (s.state === "held") return { path: "pending", rule };
  if (s.reason === "principal_override") return { path: "override", rule };
  if (s.reason === "deadline_default") return { path: "deadline", rule };
  if (s.verdict) return { path: "jury", rule };
  if (s.state === "refused" && kind === "reflex") return { path: "reflex", rule };
  if (!rule) return { path: "none" };
  return { path: kind === "judgment" ? "jury" : "reflex", rule };
}

export const PATH_TEXT: Record<Path, string> = {
  none: "Cleared — no rule fired",
  reflex: "Refused by arithmetic",
  jury: "Decided by the jury",
  override: "Principal override",
  deadline: "Deadline default",
  pending: "Awaiting the jury",
};
