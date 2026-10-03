// Builds the demo mandate. Amounts are atto-scale GEN (value x 10^18), the
// cross-chain standard the GenLayer docs specify for money.
//
// A 0.2 GEN per-spend cap and a 0.5 GEN daily cap. Two judgment rules: a
// payment that takes one vendor's 24-hour total past the per-spend cap is held
// (structuring, tier 2), and so is a category outside the agent's stated work
// (purpose, tier 3) - which a challenger may also name for a payment that
// cleared.
import fs from "node:fs";
import { accountFor } from "./lib.mjs";

const GEN = (n) => BigInt(Math.round(n * 1000)) * 10n ** 15n;

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
      when: { recipient_total_gte: { amount: GEN(0.2) + 1n, seconds: 86400 } },
      ask: "Are these payments to the same recipient separate purchases, or one purchase split across several payments to stay under the per-payment cap?",
      requires_artifact: false,
      on_breach: { tier: 2 },
    },
    {
      id: "purpose",
      type: "judgment",
      when: { category_not_in: ["media", "hosting"] },
      ask: "Is this payment for the agent's stated work - producing and hosting media for the principal's campaigns - or for something else?",
      requires_artifact: false,
      on_breach: { tier: 3 },
    },
  ],
};

// Atto amounts exceed 2^53, so they are bigints here and written as exact JSON
// integers - never through Number(), which would round them.
const exactJson = (o) =>
  JSON.stringify(o, (k, v) => (typeof v === "bigint" ? `__BIG__${v}` : v), 2).replace(/"__BIG__(\d+)"/g, "$1");

for (const network of ["studio", "bradbury"]) fs.writeFileSync(`../mandates/demo-${network}.json`, exactJson(mandate) + "\n");
console.log("vendorA   ", vendorA);
console.log("vendorB   ", vendorB);
console.log("per-spend ", String(GEN(0.2)), "(0.2 GEN)");
console.log("daily-cap ", String(GEN(0.5)), "(0.5 GEN)");
