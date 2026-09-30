// Builds the demo mandate. Amounts are atto-scale GEN (value x 10^18), the
// cross-chain standard the GenLayer docs specify for money.
//
// The scenario mirrors docs: a 0.2 GEN per-spend cap and a 0.5 GEN daily cap,
// against a 0.45 GEN purchase split into 3 x 0.15. Every threshold is
// satisfied; only judgment resolves it.
import fs from "node:fs";
import { accountFor } from "./lib.mjs";

const GEN = (n) => (BigInt(Math.round(n * 1000)) * (10n ** 15n)).toString();

const vendorA = accountFor("vendor").address;
const vendorB = accountFor("challenger").address; // a second allowlisted vendor
const dropped = "0x00000000000000000000000000000000000000b1";

const mandate = {
  remit_mandate_version: 1,
  version: 1,
  currency: "ATTO_GEN",
  defaults: {
    on_deadline: "refund",
    on_undetermined: "refund",
    response_window_seconds: 60,
    hold_deadline_seconds: 3600,
    clawback_window_seconds: 604800,
  },
  vendor_lists: { vendors: [vendorA, vendorB], dropped: [dropped] },
  rules: [
    { id: "per-spend",   type: "reflex", check: { amount_lte: GEN(0.2) } },
    { id: "daily-cap",   type: "reflex", check: { daily_total_lte: GEN(0.5) } },
    { id: "allowlist",   type: "reflex", check: { recipient_in: "vendors" } },
    { id: "not-dropped", type: "reflex", check: { recipient_not_in: "dropped" } },
    {
      id: "structuring",
      type: "judgment",
      when: { spend_count_gte: { count: 3, seconds: 3600 } },
      ask: "Are these separate purchases, or one purchase split across several payments to stay under the per-payment cap?",
      requires_artifact: false,
      on_breach: { tier: 2 },
    },
  ],
};

// The engine takes non-negative ints; JSON cannot carry a bigint, so atto
// amounts travel as decimal strings and are coerced on the contract side.
const asInt = (o) => JSON.parse(JSON.stringify(o), (k, v) =>
  (k === "amount_lte" || k === "daily_total_lte") ? Number(v) : v);

fs.writeFileSync("../mandates/demo-studio.json", JSON.stringify(asInt(mandate), null, 2));
console.log("vendorA   ", vendorA);
console.log("vendorB   ", vendorB);
console.log("per-spend ", GEN(0.2), "(0.2 GEN)");
console.log("daily-cap ", GEN(0.5), "(0.5 GEN)");
console.log("spend     ", GEN(0.15), "(0.15 GEN) x 3 = 0.45 GEN");
