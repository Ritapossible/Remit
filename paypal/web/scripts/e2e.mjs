// The web app end to end in a real browser: every suggested message, the
// decision cards, the log, phone layout, dark theme, and no page errors.
//
// It reads the server's mode from /api/health and checks what is true in it:
// - offline: the fake PayPal's four orders (one disputed) and the scripted agent;
// - sandbox: three real PayPal sandbox orders, a real model as the agent and the
//   configured panel. Real models word things their own way, so the checks are on
//   outcomes (refunded or refused, by whom, PayPal's record), never on phrasing.
//
//   REMIT_OFFLINE=1 REMIT_STATIC_DIR=web/dist uvicorn remit_paypal.web:app --port 8766   (from paypal/)
//   node scripts/e2e.mjs [baseUrl] [screenshotDir]
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://127.0.0.1:8766";
const SHOTS = process.argv[3];
let failures = 0;
const check = (label, ok, detail = "") => {
  if (!ok) failures++;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}${detail ? ` - ${detail}` : ""}`);
};

const health = await (await fetch(`${BASE}/api/health`)).json();
const SANDBOX = health.mode === "sandbox";
const WAIT = SANDBOX ? 120000 : 20000; // real models, and their rate limits, take longer
console.log(`mode: ${health.mode}, agent: ${health.agent}`);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium" });
const errors = [];
const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

console.log("[home]");
await page.goto(`${BASE}/#/`);
await page.getByRole("heading", { level: 1 }).waitFor();
check("hero says what it is", (await page.locator("h1").textContent()).includes("approve"));
if (SHOTS) await page.screenshot({ path: `${SHOTS}/home.png`, fullPage: true });

console.log("[demo]");
await page.goto(`${BASE}/#/demo`);
await page.locator(".order").first().waitFor();
check("the visitor's orders are listed", (await page.locator(".order").count()) === (SANDBOX ? 3 : 4));
await page.locator(".badge[title=\"Connected\"]").waitFor({ timeout: 10000 });
check("the console is live", true);

// Each case: the suggestion, the outcome its decision card must show, and
// whether the case must reach Remit at all. A real agent may refuse an
// injection itself without asking Remit; that is a pass, as long as no money
// moved, which the order list checks below.
const expect = [
  ["It arrived broken", "Refunded", true],
  ["It never arrived", "Refused", true],
  ["Prompt injection", "Refused", !SANDBOX],
  ...(SANDBOX ? [] : [["Disputed order", "Refused", true]]),
];
const cardFor = {};
// The agent's replies, not the typing indicator (which is also a bot bubble).
const BOT = ".msg.bot:not([aria-label])";
// A decision card arrives over the event stream, a moment after the reply.
const newCard = (p, before) =>
  p.waitForFunction((n) => document.querySelectorAll(".decision").length > n, before, { timeout: 8000 })
    .then(() => true, () => false);
for (const [label, outcome, mustAsk] of expect) {
  const before = await page.locator(".decision").count();
  const replies = await page.locator(BOT).count();
  await page.getByRole("button", { name: label }).click();
  await page.locator(BOT).nth(replies).waitFor({ timeout: WAIT });
  if (!(await newCard(page, before))) {
    check(`${label}: ${mustAsk ? outcome : "no refund"}`, !mustAsk, "the agent did not ask Remit");
    continue;
  }
  const card = page.locator(".decision").nth(before);
  cardFor[label] = card;
  await card.locator(".steps li").first().locator(".facts").waitFor({ timeout: 10000 }).catch(() => {});
  const text = await card.textContent();
  check(`${label}: ${outcome}`, text.includes(outcome), text.slice(0, 90));
}
const refunded = cardFor["It arrived broken"];
if (refunded) {
  check("the refund card names PayPal's refund", /PayPal refund [A-Z0-9-]{8,}/.test(await refunded.textContent()));
}
if (cardFor["It never arrived"]) {
  check("the 'never arrived' card shows the panel's votes", (await cardFor["It never arrived"].locator(".vote").count()) >= 1);
}
if (cardFor["Prompt injection"]) {
  check("the injection was stopped by code, no model", (await cardFor["Prompt injection"].textContent()).includes("No model was asked"));
}
// PayPal's own record, as the order list shows it: only the first order was refunded.
await page.waitForTimeout(1000);
const orderTexts = await page.locator(".order").allTextContents();
check("the refunded order now shows its refund", orderTexts[0].includes("refunded USD 45.00"), orderTexts[0].slice(0, 80));
check("no other order was refunded", orderTexts.slice(1).every((t) => !t.includes("refunded")), orderTexts.slice(1).join(" | ").slice(0, 120));
const replies = await page.locator(BOT).count();
await page.getByRole("button", { name: "Where is my order?" }).click();
await page.locator(BOT).nth(replies).waitFor({ timeout: WAIT });
const answer = await page.locator(BOT).nth(replies).textContent();
check("an ordinary question gets an answer from PayPal's tracking", /deliver|shipping/i.test(answer), answer.slice(0, 80));
if (SHOTS) await page.screenshot({ path: `${SHOTS}/demo.png` });

console.log("[log]");
await page.goto(`${BASE}/#/log`);
await page.locator(".verify").first().waitFor();
check("the log verifies", (await page.locator(".verify").first().textContent()).includes("Verified"));
const anchorText = await page.locator(".verify").nth(1).textContent({ timeout: 15000 });
check("the GenLayer anchor panel says where the log stands",
  /Matches GenLayer|newer entries pending|Not checked yet|does not anchor/.test(anchorText), anchorText.slice(0, 60));
check("the log lists the decisions", (await page.locator("table.log tbody tr").count()) > 10);
if (SHOTS) await page.screenshot({ path: `${SHOTS}/log.png`, fullPage: true });

console.log("[how, dark]");
await page.goto(`${BASE}/#/how`);
await page.getByRole("button", { name: "Dark theme" }).click();
check("the theme switches", (await page.evaluate(() => document.documentElement.dataset.theme)) === "dark");
if (SHOTS) await page.screenshot({ path: `${SHOTS}/how-dark.png`, fullPage: true });

console.log("[phone]");
const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
phone.on("pageerror", (e) => errors.push(String(e)));
for (const path of ["/", "/demo", "/log", "/how"]) {
  await phone.goto(`${BASE}/#${path}`);
  await phone.waitForTimeout(700);
  const w = await phone.evaluate(() => document.documentElement.scrollWidth);
  check(`no sideways scroll on #${path}`, w <= 390, `${w}px`);
  // Text keeps a side margin: nothing readable may start or end at the screen's edge.
  const edge = await phone.evaluate(() => {
    let worst = null;
    for (const el of document.querySelectorAll("main h1, main h2, main p, main .lede, main .btn, main li, main .case, main .verify")) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const gap = Math.min(r.left, window.innerWidth - r.right);
      if (worst === null || gap < worst.gap) worst = { gap: Math.round(gap), text: (el.textContent || "").trim().slice(0, 30) };
    }
    return worst;
  });
  check(`a side margin on #${path}`, !edge || edge.gap >= 12, edge ? `${edge.gap}px at "${edge.text}"` : "");
}
await phone.goto(`${BASE}/#/demo`);
await phone.locator(".order").first().waitFor();
await phone.getByRole("button", { name: "It never arrived" }).click();
await phone.locator(BOT).nth(1).waitFor({ timeout: WAIT });
await phone.getByRole("tab", { name: /Console/ }).click();
const shown = await phone.locator(".decision").first().waitFor({ timeout: 15000 }).then(() => true, () => false);
check("on a phone, the console tab shows the decision", shown && (await phone.locator(".decision").first().isVisible()));
if (SHOTS) await phone.screenshot({ path: `${SHOTS}/phone-console.png` });

check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
await browser.close();
console.log(failures ? `${failures} failed` : "all passed");
process.exit(failures ? 1 : 0);
