// Drives the built UI in a real browser against the real Studio network.
//
// A typecheck proves the app compiles and a unit test proves a function works.
// Neither proves a person can use it. This clicks through the product the way
// a reviewer would: read a mandate, open a jury-decided case, verify its
// evidence, then create a guard with a Studio burner and walk a split purchase
// all the way to a verdict - with the T9 window guard observed on the way.
//
// Usage: node scripts/e2e.mjs <reference-guard> [baseUrl]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const REF = process.argv[2];
const BASE = process.argv[3] ?? "http://localhost:4173";
const SHOTS = new URL("../../docs/screenshots/", import.meta.url).pathname;
mkdirSync(SHOTS, { recursive: true });
// An ordinary invoice: one order of 0.30 GEN, two payments received. It states
// no motive - the jury must read the split from the ledger and the document.
const INVOICE = "https://raw.githubusercontent.com/Ritapossible/Remit/main/examples/invoice-INV-91.json";

let failures = 0;
const check = (label, ok, detail = "") => {
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}${detail ? ` - ${detail}` : ""}`);
};

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium",
  // Route through the environment proxy when one is configured; local preview bypasses it.
  ...(process.env.HTTPS_PROXY ? { proxy: { server: process.env.HTTPS_PROXY, bypass: "localhost,127.0.0.1" } } : {}),
});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(String(e)));
const shot = (name) => page.screenshot({ path: `${SHOTS}${name}.png`, fullPage: true });
const text = () => page.locator("main").innerText();
const waitText = (t, timeout = 60000) => page.getByText(t, { exact: false }).first().waitFor({ timeout });

// ------------------------------------------------------------- the site
console.log("[site] landing, docs, roadmap");
await page.goto(`${BASE}/?net=studio#/`);
await waitText("only what you");
await waitText("Live · GenLayer Studio", 60000);
check("landing shows a live case from the reference guard", true);
await page.getByText("Does Remit hold my agent’s money?").click();
check("FAQ expands", (await page.locator("main").innerText()).includes("no way to withdraw"));
await shot("00-home");
await page.getByRole("button", { name: /Switch to dark theme/ }).click();
check("theme toggles to dark", (await page.evaluate(() => document.documentElement.dataset.theme)) === "dark");
await shot("00-home-dark");
await page.getByRole("button", { name: /Switch to light theme/ }).click();

await page.goto(`${BASE}/#/docs/getting-started`);
await page.locator(".prose h1").waitFor();
check("docs render from the repository", (await page.locator(".prose h1").innerText()).includes("Getting started"));
await page.locator('.prose a[href="#/docs/integration"]').first().click();
await page.locator(".prose h1", { hasText: "Integration" }).waitFor();
check("doc-to-doc links route inside the site", true);
await shot("09-docs");
await page.goto(`${BASE}/#/roadmap`);
await waitText("phases complete");
check("roadmap is generated from PLAN.md", (await text()).includes("Beyond"));
await shot("10-roadmap");

// --------------------------------------------------- reading the reference guard
console.log("\n[read] reference guard");
await page.goto(`${BASE}/?net=studio&guard=${REF}#/app`);
await waitText("This agent spends under a written mandate.");
await waitText("decided without a jury");
let t = await text();
check("reflex lane renders in plain English", t.includes("No single payment above 0.2 GEN"));
check("judgment lane shows the question", t.includes("one purchase split"));
check("vendor lists are public", t.includes("Who this agent may pay"));
await shot("01-mandate");

await page.goto(`${BASE}/?net=studio&guard=${REF}#/app/docket`);
await page.locator("table tbody tr").first().waitFor({ timeout: 60000 });
const rows = await page.locator("table tbody tr").count();
check("docket lists spends", rows > 0, `${rows} rows`);
await shot("02-docket");

await page.getByRole("button", { name: "Jury decided" }).click();
const juryRow = page.locator("table tbody tr").first();
if (await juryRow.count()) {
  await juryRow.click();
  await waitText("The jury's answer");
  t = await text();
  check("case shows the jury's verdict", /Outside the remit|Within the remit|Undetermined/.test(t));
  // innerText reflects CSS text-transform, so the uppercase label must be matched case-insensitively.
  check("claim is labelled untrusted", /untrusted/i.test(t));
  await shot("03-case-decided");
} else check("a jury-decided case exists on the reference guard", false);

// ------------------------------------------------------ the full flow, as a user
console.log("\n[flow] create a guard with a Studio burner");
await page.goto(`${BASE}/?net=studio#/app/new`);
await page.getByRole("button", { name: "Studio burner" }).click();
await page.getByRole("button", { name: "Forget" }).waitFor({ timeout: 60000 });
check("burner created and funded", true);
await page.getByRole("button", { name: "Use my address" }).click();
await waitText("The mandate is valid.");
await shot("04-new-guard");
await page.getByRole("button", { name: /Deploy guard/ }).click();
await page.getByRole("button", { name: "Open this guard →" }).waitFor({ timeout: 300000 });
check("guard deployed through the UI", true);
await page.getByRole("button", { name: "Open this guard →" }).click();
await waitText("You are the principal and the agent.");
check("role detected: principal and agent", true);

async function spend(amount, claim, expect) {
  await page.goto(page.url().replace(/#.*$/, "#/app/spend"));
  await page.getByLabel("Amount (GEN)").fill(amount);
  await page.getByPlaceholder("e.g. invoice INV-88, part 3 of 3").fill(claim);
  await waitText(expect.preview, 60000);
  await page.getByRole("button", { name: "Request authorization" }).click();
  await waitText(expect.result, 300000);
}

console.log("\n[flow] two payments of 0.15 GEN to one vendor - one 0.30 order, split");
await spend("0.15", "PO-5521 product video", { preview: "Authorized instantly", result: "authorized." });
check("payment 1 authorized in the same transaction", true);

await page.goto(page.url().replace(/#.*$/, "#/app/spend"));
await page.getByLabel("Amount (GEN)").fill("0.15");
await page.getByPlaceholder("e.g. invoice INV-88, part 3 of 3").fill("PO-5521 product video");
await waitText("Held for the jury", 60000);
check("preview predicts the hold before signing", (await text()).includes("one purchase split"));
await shot("05-preview-held");
await page.getByRole("button", { name: "Request authorization" }).click();
await waitText("held for the jury.", 300000);
check("payment 2 held - it takes the vendor past the per-payment cap", true);
await page.getByText("Open the case →").click();
await waitText("Act on this case");

// T9: with no evidence and the window open, the UI must not let you adjudicate.
const adjudicate = page.getByRole("button", { name: "Adjudicate" });
check("adjudicate disabled inside the response window", await adjudicate.isDisabled());
check("the window is explained", (await text()).includes("never had"));
await shot("06-case-window");

console.log("\n[flow] commit the invoice, then convene the jury");
await page.getByPlaceholder("https://… invoice, order or receipt").fill(INVOICE);
await page.getByRole("button", { name: "Compute digest" }).click();
await page.getByRole("button", { name: "Commit" }).waitFor({ state: "visible" });
await page.waitForFunction(() => /[0-9a-f]{64}/.test(document.body.innerText), null, { timeout: 30000 });
await page.getByRole("button", { name: "Commit", exact: true }).click();
await waitText("Evidence committed", 300000);
check("evidence committed", true);
await page.getByRole("button", { name: "Verify it yourself" }).click();
await waitText("Matches", 30000);
check("evidence verifies in the browser", true);

await page.getByRole("button", { name: "Adjudicate" }).click();
const verdictOrRetry = await Promise.race([
  waitText("The jury's answer", 600000).then(() => "verdict"),
  waitText("No consensus", 600000).then(() => "no-consensus"),
]);
if (verdictOrRetry === "no-consensus") {
  console.log("  note: no consensus on the first round; retrying once, as the UI invites");
  await page.getByRole("button", { name: "Adjudicate" }).click();
  await waitText("The jury's answer", 600000);
}
t = await text();
check("jury verdict recorded", /Outside the remit|Within the remit|Undetermined/.test(t));
check("verdict is out of remit", t.includes("Outside the remit"));
check("the rail would not pay it", t.includes("The rail will not pay") || t.includes("No rail is attached"));
await shot("07-case-verdict");
const caseUrl = page.url();

console.log("\n[flow] a rail: deploy, fund, pay what was authorized");
await page.goto(caseUrl.replace(/#.*$/, "#/app"));
await page.getByRole("button", { name: "Deploy a rail for this guard" }).click();
await page.getByRole("button", { name: "Attach it" }).waitFor({ timeout: 300000 });
check("rail deployed through the UI", true);
await page.getByRole("button", { name: "Attach it" }).click();
await waitText("The agent cannot withdraw.", 60000);
await page.getByLabel("GEN to add").fill("0.3");
await page.getByRole("button", { name: "Add GEN" }).click();
await waitText("Funds added to the rail.", 300000);
check("rail funded", true);
await page.goto(page.url().replace(/#.*$/, "#/app/case/0"));
await page.getByRole("button", { name: /Pay .* from the rail/ }).waitFor({ timeout: 60000 });
await page.waitForFunction(() => ![...document.querySelectorAll("button")].find((b) => /from the rail/.test(b.textContent))?.disabled, null, { timeout: 120000 });
await page.getByRole("button", { name: /Pay .* from the rail/ }).click();
await waitText("Paid. The recipient", 300000);
check("authorized spend paid from the rail", true);
await page.reload();
await waitText("The rail sent", 60000);
check("payment recorded on the rail", true);
await page.goto(page.url().replace(/#.*$/, "#/app/case/1"));
await waitText("The rail will not pay this spend", 60000);
check("refused spend shown as unpayable", true);
await shot("11-rail");

// ----------------------------------------------------------------- mobile
console.log("\n[layout] phone width");
// Every page, not just the landing page: docs carry code and tables that can
// widen a column past the screen.
const base = BASE + "/";
const g = `?guard=${REF}`;
const phonePages = [
  "#/", "#/roadmap",
  "#/docs/getting-started", "#/docs/integration", "#/docs/architecture",
  "#/docs/mandate-format", "#/docs/threat-model", "#/docs/genvm-notes",
  `#/app${g}`, `#/app/docket${g}`, `#/app/case/1${g}`, `#/app/spend${g}`, `#/app/new${g}`,
];
for (const width of [390, 360]) {
  await page.setViewportSize({ width, height: 844 });
  const wide = [];
  for (const route of phonePages) {
    await page.goto(base + route);
    await page.waitForTimeout(700);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 1) wide.push(`${route} +${overflow}px`);
  }
  check(`no horizontal page scroll at ${width}px on ${phonePages.length} pages`, wide.length === 0, wide.join(", "));
}
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(base + "#/");
await waitText("only what you");
await shot("08-mobile");

check("no uncaught page errors", consoleErrors.length === 0, consoleErrors.slice(0, 2).join(" | "));
await browser.close();
console.log(`\n${failures} failed checks`);
process.exit(failures ? 1 : 0);
