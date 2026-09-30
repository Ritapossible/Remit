// Fails if the frontend drifts from the engine.
//
// 1. Every enum the UI renders must match contracts/remit_core.py exactly. A
//    state the UI does not know is a state it silently mislabels.
// 2. The TypeScript mandate validator must ACCEPT and REJECT exactly what the
//    Python validate_mandate does, across the shipped fixtures, the UI's own
//    templates, and a corpus of deliberate breakages. Messages may differ;
//    verdicts may not. A form that accepts what the contract rejects wastes a
//    deployment; one that rejects what the contract accepts blocks a user.
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import * as C from "../src/lib/constants";
import { campaignTemplate, contractorTemplate, parseMandateText, validateMandate } from "../src/lib/mandate";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CORE = join(ROOT, "contracts");
let failures = 0;
const fail = (msg: string) => {
  failures++;
  console.log("  FAIL " + msg);
};

// ------------------------------------------------------------- 1. constants
const py = JSON.parse(
  execFileSync("python3", [
    "-c",
    `import sys, json; sys.path.insert(0, ${JSON.stringify(CORE)}); import remit_core as c
print(json.dumps({"SPEND_STATES": c.SPEND_STATES, "ARTIFACT_STATES": c.ARTIFACT_STATES, "VERDICTS": c.VERDICTS,
 "OUTCOMES": c.OUTCOMES, "RULE_TYPES": c.RULE_TYPES, "PREDICATES": c.PREDICATES, "REQUIRED_DEFAULTS": c.REQUIRED_DEFAULTS,
 "DAY_SECONDS": c.DAY_SECONDS}))`,
  ]).toString(),
);
console.log("constants");
for (const key of Object.keys(py)) {
  const mine = JSON.stringify((C as Record<string, unknown>)[key]);
  const theirs = JSON.stringify(py[key]);
  if (mine !== theirs) fail(`${key}: ui=${mine} engine=${theirs}`);
  else console.log(`  ok   ${key}`);
}

// ----------------------------------------------------------- 2. validator
const cases: { name: string; text: string; storedVersion: number; maxTier: number }[] = [];
const add = (name: string, text: string, storedVersion = 0, maxTier = 3) => cases.push({ name, text, storedVersion, maxTier });

for (const f of readdirSync(join(ROOT, "mandates")).filter((n) => n.endsWith(".json") && n !== "standard.json"))
  add(`fixture ${f}`, readFileSync(join(ROOT, "mandates", f), "utf8"));
const vendors = ["0x3F55971f7fd2594A90871Db489fBb82f1DB4d747"];
add("template campaign", campaignTemplate(vendors));
add("template contractor", contractorTemplate(vendors));
add("campaign under max tier 1", campaignTemplate(vendors), 0, 1);
add("campaign republished at same version", campaignTemplate(vendors), 1, 3);

// Breakages, each applied to a clean campaign mandate.
const base = () => JSON.parse(campaignTemplate(vendors));
type M = ReturnType<typeof base>;
const mutations: [string, (m: M) => unknown][] = [
  ["not an object", () => []],
  ["version as string", (m) => ((m.version = "1"), m)],
  ["version zero", (m) => ((m.version = 0), m)],
  ["version float", (m) => ((m.version = 1.5), m)],
  ["defaults missing", (m) => (delete m.defaults, m)],
  ...(C.REQUIRED_DEFAULTS.map((k) => [`default ${k} missing`, (m: M) => (delete m.defaults[k], m)]) as [string, (m: M) => unknown][]),
  ["unknown default token", (m) => ((m.defaults.on_deadline = "hold_forever"), m)],
  ["window >= deadline", (m) => ((m.defaults.response_window_seconds = 3600), m)],
  ["negative window", (m) => ((m.defaults.response_window_seconds = -1), m)],
  ["bool window", (m) => ((m.defaults.response_window_seconds = true), m)],
  ["vendor_lists not object", (m) => ((m.vendor_lists = ["0xabc"]), m)],
  ["vendor list not a list", (m) => ((m.vendor_lists.vendors = "0xabc"), m)],
  ["vendor not hex", (m) => ((m.vendor_lists.vendors = ["0xzz"]), m)],
  ["vendor uppercase hex ok", (m) => ((m.vendor_lists.vendors = ["0XABCDEF"]), m)],
  ["vendor empty string", (m) => ((m.vendor_lists.vendors = [""]), m)],
  ["rules not a list", (m) => ((m.rules = {}), m)],
  ["rule not object", (m) => (m.rules.push("x"), m)],
  ["duplicate id", (m) => ((m.rules[1].id = m.rules[0].id), m)],
  ["empty id", (m) => ((m.rules[0].id = ""), m)],
  ["unknown type", (m) => ((m.rules[0].type = "advisory"), m)],
  ["unknown predicate", (m) => ((m.rules[0].check = { amount_roughly: 1 }), m)],
  ["two predicates", (m) => ((m.rules[0].check = { amount_lte: 1, amount_gte: 0 }), m)],
  ["no predicate", (m) => ((m.rules[0].check = {}), m)],
  ["check not object", (m) => ((m.rules[0].check = 5), m)],
  ["negative amount", (m) => ((m.rules[0].check = { amount_lte: -1 }), m)],
  ["float amount", (m) => ((m.rules[0].check = { amount_lte: 0.2 }), m)],
  ["bool amount", (m) => ((m.rules[0].check = { amount_lte: true }), m)],
  ["string amount", (m) => ((m.rules[0].check = { amount_lte: "200" }), m)],
  ["window operand scalar", (m) => ((m.rules[0].check = { window_total_lte: 5 }), m)],
  ["window missing seconds", (m) => ((m.rules[0].check = { window_total_lte: { amount: 5 } }), m)],
  ["count window ok", (m) => ((m.rules[0].check = { spend_count_lte: { count: 5, seconds: 60 } }), m)],
  ["undefined list", (m) => ((m.rules[2].check = { recipient_in: "contractors" }), m)],
  ["list name not string", (m) => ((m.rules[2].check = { recipient_in: 7 }), m)],
  ["empty category list", (m) => ((m.rules[0].check = { category_in: [] }), m)],
  ["category list ok", (m) => ((m.rules[0].check = { category_in: ["media"] }), m)],
  ["judgment no ask", (m) => (delete m.rules[4].ask, m)],
  ["judgment empty ask", (m) => ((m.rules[4].ask = ""), m)],
  ["judgment no on_breach", (m) => (delete m.rules[4].on_breach, m)],
  ["judgment tier string", (m) => ((m.rules[4].on_breach = { tier: "high" }), m)],
  ["judgment tier too high", (m) => ((m.rules[4].on_breach = { tier: 9 }), m)],
  ["requires_artifact not bool", (m) => ((m.rules[4].requires_artifact = "yes"), m)],
  ["context uri without digest", (m) => ((m.rules[4].context_uri = "https://x.y/z"), m)],
  ["context uri with digest", (m) => ((m.rules[4].context_uri = "https://x.y/z"), (m.rules[4].context_digest = "sha256:00"), m)],
  ["reflex-only mandate", (m) => ((m.rules = m.rules.filter((r: { type: string }) => r.type === "reflex")), m)],
  ["empty rules", (m) => ((m.rules = []), m)],
];
for (const [name, mutate] of mutations) add(name, JSON.stringify(mutate(base())));

const dir = mkdtempSync(join(tmpdir(), "remit-parity-"));
const corpus = join(dir, "corpus.json");
writeFileSync(corpus, JSON.stringify(cases));
const verdicts: boolean[] = JSON.parse(
  execFileSync("python3", [
    "-c",
    `import sys, json; sys.path.insert(0, ${JSON.stringify(CORE)}); import remit_core as c
out = []
for k in json.load(open(${JSON.stringify(corpus)})):
    try:
        m = json.loads(k["text"])
    except Exception:
        out.append(False); continue
    out.append(len(c.validate_mandate(m, stored_version=k["storedVersion"], max_tier=k["maxTier"])) == 0)
print(json.dumps(out))`,
  ]).toString(),
);

console.log(`\nvalidator (${cases.length} cases)`);
cases.forEach((k, i) => {
  let ui: boolean;
  try {
    ui = validateMandate(parseMandateText(k.text), { storedVersion: k.storedVersion, maxTier: k.maxTier }).length === 0;
  } catch {
    ui = false;
  }
  const engine = verdicts[i];
  if (ui !== engine) fail(`${k.name}: ui ${ui ? "accepts" : "rejects"}, engine ${engine ? "accepts" : "rejects"}`);
});
const accepted = verdicts.filter(Boolean).length;
console.log(`  ${cases.length - failures} agree · engine accepts ${accepted}, rejects ${cases.length - accepted}`);
console.log(failures ? `\n${failures} parity failure(s)` : "\nparity ok");
process.exit(failures ? 1 : 0);
