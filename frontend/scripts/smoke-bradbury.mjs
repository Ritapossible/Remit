// Read-only smoke test of the app on Bradbury: the reference guard, its docket,
// its cases and its rail, as a reviewer sees them. No wallet, no transactions.
//   node scripts/smoke-bradbury.mjs [baseUrl]
import { chromium } from "playwright";
const base = process.argv[2] || "http://localhost:4174";
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium" });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
let failed = 0;
const check = (name, ok) => { console.log(`  ${ok ? "ok  " : "FAIL"} ${name}`); if (!ok) failed++; };
const seen = async (text, ms = 120000) => page.getByText(text).first().waitFor({ timeout: ms }).then(() => true, () => false);

await page.goto(base + "/#/app");
await page.getByLabel("Network").selectOption("bradbury");
check("Bradbury mandate loads", await seen("Who this agent may pay"));
check("pinned evidence sources are shown", await seen("Where each vendor's evidence must come from"));
check("the vendor's pinned prefix is listed", await seen("examples/vendor/northlight/"));
await page.goto(base + "/#/app/docket");
check("docket lists the 5 reference spends", await page.locator("table tbody tr").nth(4).waitFor({ timeout: 120000 }).then(() => true, () => false));
await page.goto(base + "/#/app/case/3");
check("case 3: the jury's verdict is shown", await seen("Outside the remit"));
await page.goto(base + "/#/app/case/0");
check("case 0: the rail's split refusal is shown before signing", await seen("refused with the split it belongs to", 180000));
await page.goto(base + "/#/app/case/4");
check("case 4: paid by the rail", await seen("Paid.", 120000));
check("no uncaught page errors", errors.length === 0);
if (errors.length) console.log(errors.join("\n"));
await browser.close();
console.log(failed ? `${failed} failed` : "bradbury smoke ok");
process.exit(failed ? 1 : 0);
