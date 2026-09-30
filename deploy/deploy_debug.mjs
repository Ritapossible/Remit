import fs from "node:fs";
import { clientFor, accountFor, retry } from "./lib.mjs";
const code = fs.readFileSync("../contracts/build/remit.py");
const mandate = fs.readFileSync("../mandates/demo-studio.json", "utf8");
const agent = accountFor("agent").address;
const client = clientFor("studio", "principal");
const hash = await retry("deploy", () =>
  client.deployContract({ code, args: [agent, mandate, 2, false], leaderOnly: false }), 5);
console.log("TXHASH", hash);
const r = await retry("receipt", () =>
  client.waitForTransactionReceipt({ hash, status: "FINALIZED", retries: 300, interval: 3000 }), 5);
const dump = JSON.stringify(r, (k, v) => typeof v === "bigint" ? v.toString() : v, 2);
// Surface any error text wherever it hides in the receipt shape.
const errs = [...dump.matchAll(/"(err|error|message|stderr|exception|reason)"\s*:\s*("(?:[^"\\]|\\.)*")/gi)];
console.log("\n=== error-ish fields ===");
for (const m of errs.slice(0, 25)) console.log(m[1], "=", m[2].slice(0, 400));
console.log("\n=== status ===", r?.status, r?.data?.contract_address ?? "(no address)");
fs.writeFileSync("last_receipt.json", dump);
console.log("full receipt in deploy/last_receipt.json,", dump.length, "bytes");
