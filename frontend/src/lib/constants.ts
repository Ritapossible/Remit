// Mirrors contracts/remit_core.py. scripts/parity.ts fails the build if these
// drift from the engine, because a state the UI does not know is a state it
// silently mislabels.

export const SPEND_STATES = ["settled", "refused", "held"] as const;
export type SpendState = (typeof SPEND_STATES)[number];

export const ARTIFACT_STATES = ["verified", "unverified", "absent", "foreclosed"] as const;
export type ArtifactState = (typeof ARTIFACT_STATES)[number];

export const VERDICTS = ["in_remit", "out_of_remit", "undetermined"] as const;
export type Verdict = (typeof VERDICTS)[number];

export const OUTCOMES = ["allowed", "refused"] as const;

export const AUTHORIZATIONS = ["authorized", "refused", "pending"] as const;
export type Authorization = (typeof AUTHORIZATIONS)[number];

export const RULE_TYPES = ["reflex", "judgment"] as const;
export type RuleType = (typeof RULE_TYPES)[number];

export const PREDICATES_INT = ["amount_lte", "amount_gte", "daily_total_lte", "daily_total_gte"] as const;
export const PREDICATES_WINDOW_AMOUNT = ["window_total_lte", "window_total_gte", "recipient_total_lte", "recipient_total_gte"] as const;
export const PREDICATES_WINDOW_COUNT = ["spend_count_lte", "spend_count_gte", "recipient_count_lte", "recipient_count_gte"] as const;
export const PREDICATES_LIST_NAME = ["recipient_in", "recipient_not_in"] as const;
export const PREDICATES_STR_SET = ["category_in", "category_not_in"] as const;
export const PREDICATES = [
  ...PREDICATES_INT,
  ...PREDICATES_WINDOW_AMOUNT,
  ...PREDICATES_WINDOW_COUNT,
  ...PREDICATES_LIST_NAME,
  ...PREDICATES_STR_SET,
] as const;
export type Predicate = (typeof PREDICATES)[number];

export const REQUIRED_DEFAULTS = [
  "on_deadline",
  "on_undetermined",
  "response_window_seconds",
  "hold_deadline_seconds",
  "clawback_window_seconds",
] as const;

export const DAY_SECONDS = 86400;
