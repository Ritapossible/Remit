// The web app end to end in a real browser, against the server in offline
// mode (fake PayPal, stand-in models): every suggested message, the decision
// cards, the log, phone layout, dark theme, and no page errors.
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
check("the visitor's orders are listed", (await page.locator(".order").count()) === 4);
await page.locator(".badge[title=\"Connected\"]").waitFor({ timeout: 10000 });
check("the console is live", true);

const expect = [
  ["It arrived broken", "Refunded"],
  ["It never arrived", "Refused"],
  ["Prompt injection", "Refused"],
  ["Disputed order", "Refused"],
];
for (const [label, outcome] of expect) {
  const before = await page.locator(".decision").count();
  await page.getByRole("button", { name: label }).click();
  await page.locator(".decision").nth(before).waitFor({ timeout: 20000 });
  const card = page.locator(".decision").nth(before);
  await card.locator(".steps li").first().locator(".facts").waitFor({ timeout: 10000 }).catch(() => {});
  const text = await card.textContent();
  check(`${label}: ${outcome}`, text.includes(outcome), text.slice(0, 90));
}
const cards = page.locator(".decision");
check("the refund card names PayPal's refund", (await cards.nth(0).textContent()).includes("PayPal refund REFUND-"));
check("the 'never arrived' card shows three panel votes", (await cards.nth(1).locator(".vote").count()) === 3);
check("the injection was stopped by code, no model", (await cards.nth(2).textContent()).includes("No model was asked"));
check("the refunded order now shows its refund", (await page.locator(".order").first().textContent()).includes("refunded USD 45.00"));
await page.getByRole("button", { name: "Where is my order?" }).click();
await page.locator(".msg.bot").last().filter({ hasText: "Shipping" }).waitFor({ timeout: 10000 });
check("an ordinary question gets an ordinary answer", true);
if (SHOTS) await page.screenshot({ path: `${SHOTS}/demo.png` });

console.log("[log]");
await page.goto(`${BASE}/#/log`);
await page.locator(".verify").waitFor();
check("the log verifies", (await page.locator(".verify").textContent()).includes("Verified"));
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
}
await phone.goto(`${BASE}/#/demo`);
await phone.locator(".order").first().waitFor();
await phone.getByRole("button", { name: "It never arrived" }).click();
await phone.locator(".msg.bot").nth(1).waitFor({ timeout: 20000 });
await phone.getByRole("tab", { name: /Console/ }).click();
await phone.locator(".decision").first().waitFor({ timeout: 10000 });
check("on a phone, the console tab shows the decision", await phone.locator(".decision").first().isVisible());
if (SHOTS) await phone.screenshot({ path: `${SHOTS}/phone-console.png` });

check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
await browser.close();
console.log(failures ? `${failures} failed` : "all passed");
process.exit(failures ? 1 : 0);
