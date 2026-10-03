import {
  DAY_SECONDS,
  PREDICATES,
  PREDICATES_INT,
  PREDICATES_LIST_NAME,
  PREDICATES_STR_SET,
  PREDICATES_WINDOW_AMOUNT,
  PREDICATES_WINDOW_COUNT,
  REQUIRED_DEFAULTS,
  RULE_TYPES,
} from "./constants";
import { formatGen } from "./money";
import { duration } from "./format";

// ---------------------------------------------------------------- chain shapes

export interface RuleInfo {
  id: string;
  type: "reflex" | "judgment";
  predicate: string;
  a: string | number;
  b: string | number;
  s: string;
  requires_artifact: boolean;
  tier: number;
  ask: string;
}

export interface MandateInfo {
  principal: string;
  agent: string;
  max_tier: number;
  shadow: boolean;
  mandate_uri: string;
  mandate_digest: string;
  mandate_version: number;
  defaults: {
    on_deadline: string;
    on_undetermined: string;
    response_window_seconds: number;
    hold_deadline_seconds: number;
    clawback_window_seconds: number;
  };
  rules: RuleInfo[];
  vendor_lists?: Record<string, string[]>;
  spend_count: number;
  /** Graduated authority; absent on guards built before tiers 2 and 3. */
  release?: string;
  rail?: string;
  frozen_tier?: number;
  frozen_by?: number;
  revoked_below?: number;
}

// ----------------------------------------------------------- plain English

const gen = (v: string | number | bigint) => `${formatGen(BigInt(v))} GEN`;
const within = (seconds: string | number) => {
  const s = Number(seconds);
  return s === DAY_SECONDS ? "24 hours" : duration(s);
};

/** "more than X" when the threshold is one smallest unit above a round
 *  amount (how a "more than the cap" trigger is written), else "X or more". */
function moreThan(a: number | string | bigint): string {
  const v = BigInt(a);
  return v % 1000n === 1n ? `more than ${gen(v - 1n)}` : `${gen(v)} or more`;
}

/** A rule as a sentence. Reflex rules read as limits; triggers as conditions. */
export function describePredicate(r: Pick<RuleInfo, "predicate" | "a" | "b" | "s">, asTrigger = false): string {
  const { predicate: p, a, b, s } = r;
  switch (p) {
    case "amount_lte":
      return asTrigger ? `a payment of ${gen(a)} or less` : `No single payment above ${gen(a)}`;
    case "amount_gte":
      return asTrigger ? `a payment of ${gen(a)} or more` : `Every payment at least ${gen(a)}`;
    case "daily_total_lte":
      return asTrigger ? `24-hour total at or under ${gen(a)}` : `At most ${gen(a)} in any rolling 24 hours`;
    case "daily_total_gte":
      return asTrigger ? `24-hour total reaching ${gen(a)}` : `At least ${gen(a)} in the last 24 hours`;
    case "window_total_lte":
      return asTrigger ? `total within ${within(b)} at or under ${gen(a)}` : `At most ${gen(a)} in any ${within(b)}`;
    case "window_total_gte":
      return asTrigger ? `${gen(a)} or more paid within ${within(b)}` : `At least ${gen(a)} within ${within(b)}`;
    case "spend_count_lte":
      return asTrigger ? `${a} or fewer payments within ${within(b)}` : `At most ${a} payments in any ${within(b)}`;
    case "spend_count_gte":
      return asTrigger ? `${a} or more payments within ${within(b)}` : `At least ${a} payments within ${within(b)}`;
    case "recipient_total_lte":
      return asTrigger ? `${moreThan(a)} total to one recipient within ${within(b)}`.replace("more than", "at most") : `At most ${gen(a)} to any one recipient in ${within(b)}`;
    case "recipient_total_gte":
      return asTrigger ? `${moreThan(a)} paid to the same recipient within ${within(b)}` : `At least ${gen(a)} to one recipient within ${within(b)}`;
    case "recipient_count_lte":
      return asTrigger ? `${a} or fewer payments to the same recipient within ${within(b)}` : `At most ${a} payments to any one recipient in ${within(b)}`;
    case "recipient_count_gte":
      return asTrigger ? `${a} or more payments to the same recipient within ${within(b)}` : `At least ${a} payments to one recipient within ${within(b)}`;
    case "recipient_in":
      return asTrigger ? `the recipient is on “${s}”` : `Recipient must be on the “${s}” list`;
    case "recipient_not_in":
      return asTrigger ? `the recipient is not on “${s}”` : `Recipient must not be on the “${s}” list`;
    case "category_in":
      return asTrigger ? `the category is one of ${s.split(",").join(", ")}` : `Category must be one of ${s.split(",").join(", ")}`;
    case "category_not_in":
      return asTrigger ? `the category is not ${s.split(",").join(", ")}` : `Category must not be ${s.split(",").join(", ")}`;
    default:
      return p;
  }
}

// ------------------------------------------------ validation (engine parity)
//
// A port of validate_mandate in contracts/remit_core.py, used only where no
// contract exists yet to ask: the "new guard" form. scripts/parity.ts runs this
// and the Python original over the same corpus and fails on any difference in
// what is accepted. Messages may differ; verdicts may not.

type Json = null | boolean | number | bigint | string | Json[] | { [k: string]: Json };

/** JSON.parse that keeps integers past 2^53 exact, as bigint. */
export function parseMandateText(text: string): Json {
  const marked = text.replace(/([:\[,]\s*)(-?\d{16,})(?=\s*[,}\]])/g, '$1"__bigint__$2"');
  return JSON.parse(marked, (_k, v) =>
    typeof v === "string" && v.startsWith("__bigint__") ? BigInt(v.slice(10)) : v,
  ) as Json;
}

const isObj = (v: unknown): v is Record<string, Json> =>
  typeof v === "object" && v !== null && !Array.isArray(v) && typeof v !== "bigint";
const isInt = (v: unknown) => typeof v === "bigint" || (typeof v === "number" && Number.isInteger(v));
const nonNegInt = (v: unknown) => isInt(v) && BigInt(v as number | bigint) >= 0n;
const isAddress = (v: unknown) =>
  typeof v === "string" && v.trim() !== "" && /^0x[0-9a-f]+$/.test(v.trim().toLowerCase());

export function validateMandate(m: Json, opts: { storedVersion: number; maxTier: number }): string[] {
  const errors: string[] = [];
  const bad = (msg: string) => errors.push(msg);
  if (!isObj(m)) return ["mandate: expected an object"];

  const version = m.version;
  if (!isInt(version)) bad("version: expected an integer");
  else if (BigInt(version as number) <= BigInt(opts.storedVersion)) bad(`version: must exceed ${opts.storedVersion}`);

  let defaults = m.defaults;
  if (!isObj(defaults)) {
    bad("defaults: expected an object");
    defaults = {};
  }
  const d = defaults as Record<string, Json>;
  for (const key of REQUIRED_DEFAULTS) if (!(key in d)) bad(`defaults: missing ${key}`);
  for (const key of ["on_deadline", "on_undetermined"])
    if (key in d && d[key] !== "refund" && d[key] !== "release") bad(`defaults.${key}: expected "refund" or "release"`);
  for (const key of ["response_window_seconds", "hold_deadline_seconds", "clawback_window_seconds"])
    if (key in d && !nonNegInt(d[key])) bad(`defaults.${key}: expected a non-negative integer`);
  if (nonNegInt(d.response_window_seconds) && nonNegInt(d.hold_deadline_seconds))
    if (BigInt(d.response_window_seconds as number) >= BigInt(d.hold_deadline_seconds as number))
      bad("defaults: response_window_seconds must be less than hold_deadline_seconds");

  let lists = m.vendor_lists ?? {};
  if (!isObj(lists)) {
    bad("vendor_lists: expected an object");
    lists = {};
  }
  const vl = lists as Record<string, Json>;
  for (const name of Object.keys(vl)) {
    const members = vl[name];
    if (!Array.isArray(members)) {
      bad(`vendor_lists.${name}: expected a list`);
      continue;
    }
    for (const a of members) if (!isAddress(a)) bad(`vendor_lists.${name}: not an address: ${String(a)}`);
  }

  const rules = m.rules;
  if (!Array.isArray(rules)) return [...errors, "rules: expected a list"];

  const seen = new Set<string>();
  rules.forEach((rule, i) => {
    const where = `rules[${i}]`;
    if (!isObj(rule)) return bad(`${where}: expected an object`);
    const id = rule.id;
    if (typeof id !== "string" || id === "") bad(`${where}.id: expected a non-empty string`);
    else if (seen.has(id)) bad(`${where}.id: duplicate rule id "${id}"`);
    else seen.add(id);

    const type = rule.type;
    if (!RULE_TYPES.includes(type as never)) return bad(`${where}.type: expected reflex or judgment`);

    const key = type === "reflex" ? "check" : "when";
    const obj = rule[key];
    if (!isObj(obj)) bad(`${where}.${key}: expected an object`);
    else if (Object.keys(obj).length !== 1) bad(`${where}.${key}: expected exactly 1 predicate`);
    else {
      const [name] = Object.keys(obj);
      const op = obj[name];
      if (!PREDICATES.includes(name as never)) bad(`${where}.${key}: "${name}" is outside the v1 vocabulary`);
      else if (PREDICATES_INT.includes(name as never)) {
        if (!nonNegInt(op)) bad(`${where}.${key}.${name}: expected a non-negative integer`);
      } else if (PREDICATES_WINDOW_AMOUNT.includes(name as never) || PREDICATES_WINDOW_COUNT.includes(name as never)) {
        const k = PREDICATES_WINDOW_AMOUNT.includes(name as never) ? "amount" : "count";
        if (!isObj(op)) bad(`${where}.${key}: expected an object operand`);
        else if (!(k in op) || !("seconds" in op)) bad(`${where}.${key}: operand needs "${k}" and "seconds"`);
        else if (!nonNegInt(op[k]) || !nonNegInt(op.seconds)) bad(`${where}.${key}.${name}: expected non-negative integers`);
      } else if (PREDICATES_LIST_NAME.includes(name as never)) {
        if (typeof op !== "string" || op === "") bad(`${where}.${key}: expected a list name`);
        else if (!(op in vl)) bad(`${where}.${key}: vendor list "${op}" is not defined`);
      } else if (PREDICATES_STR_SET.includes(name as never)) {
        if (!Array.isArray(op) || op.length === 0) bad(`${where}.${key}.${name}: expected a non-empty list`);
      }
    }

    if (type === "judgment") {
      if (typeof rule.ask !== "string" || rule.ask === "") bad(`${where}.ask: expected a non-empty string`);
      const ob = rule.on_breach;
      if (!isObj(ob) || !("tier" in ob)) bad(`${where}.on_breach: expected an object with "tier"`);
      else if (!nonNegInt(ob.tier)) bad(`${where}.on_breach.tier: expected a non-negative integer`);
      else if (BigInt(ob.tier as number) > BigInt(opts.maxTier))
        bad(`${where}.on_breach.tier: ${String(ob.tier)} exceeds the granted max tier ${opts.maxTier}`);
      if (rule.requires_artifact && typeof rule.requires_artifact !== "boolean")
        bad(`${where}.requires_artifact: expected true or false`);
      if (!!rule.context_uri !== !!rule.context_digest)
        bad(`${where}: context_uri and context_digest must be given together`);
    }
  });
  return errors;
}

export function mandateNotices(m: Json): string[] {
  const rules = isObj(m) && Array.isArray(m.rules) ? m.rules : [];
  const judgments = rules.filter((r) => isObj(r) && r.type === "judgment");
  return judgments.length
    ? []
    : ["This mandate has no judgment rules. Every rule in it is arithmetic a plain smart contract would evaluate faster and cheaper - Remit will register it, but it isn't buying you anything."];
}

// -------------------------------------------------------------- templates

const G = (n: string) => (BigInt(n.replace(".", "").padEnd(n.split(".")[0].length + 18, "0").slice(0, n.split(".")[0].length + 18))).toString();

export function campaignTemplate(vendors: string[]): string {
  const v = vendors.length ? vendors : ["0x0000000000000000000000000000000000000001"];
  return `{
  "remit_mandate_version": 1,
  "version": 1,
  "currency": "ATTO_GEN",
  "defaults": {
    "on_deadline": "refund",
    "on_undetermined": "refund",
    "response_window_seconds": 60,
    "hold_deadline_seconds": 3600,
    "clawback_window_seconds": 604800
  },
  "vendor_lists": {
    "vendors": [${v.map((a) => `"${a}"`).join(", ")}],
    "dropped": ["0x00000000000000000000000000000000000000b1"]
  },
  "rules": [
    { "id": "per-spend",   "type": "reflex", "check": { "amount_lte": ${G("0.2")} } },
    { "id": "daily-cap",   "type": "reflex", "check": { "daily_total_lte": ${G("0.5")} } },
    { "id": "allowlist",   "type": "reflex", "check": { "recipient_in": "vendors" } },
    { "id": "not-dropped", "type": "reflex", "check": { "recipient_not_in": "dropped" } },
    {
      "id": "structuring",
      "type": "judgment",
      "when": { "recipient_total_gte": { "amount": ${(BigInt(G("0.2")) + 1n).toString()}, "seconds": 86400 } },
      "ask": "Are these payments to the same recipient separate purchases, or one purchase split across several payments to stay under the per-payment cap?",
      "requires_artifact": false,
      "on_breach": { "tier": 2 }
    }
  ]
}`;
}

export function contractorTemplate(vendors: string[]): string {
  const v = vendors.length ? vendors : ["0x0000000000000000000000000000000000000001"];
  return `{
  "remit_mandate_version": 1,
  "version": 1,
  "currency": "ATTO_GEN",
  "defaults": {
    "on_deadline": "refund",
    "on_undetermined": "refund",
    "response_window_seconds": 120,
    "hold_deadline_seconds": 7200,
    "clawback_window_seconds": 604800
  },
  "vendor_lists": { "contractors": [${v.map((a) => `"${a}"`).join(", ")}] },
  "rules": [
    { "id": "per-payout",  "type": "reflex", "check": { "amount_lte": ${G("1")} } },
    { "id": "contractors", "type": "reflex", "check": { "recipient_in": "contractors" } },
    {
      "id": "invoice-match",
      "type": "judgment",
      "when": { "amount_gte": ${G("0.1")} },
      "ask": "Does this payment correspond to a deliverable that was actually received?",
      "requires_artifact": true,
      "on_breach": { "tier": 1 }
    }
  ]
}`;
}
