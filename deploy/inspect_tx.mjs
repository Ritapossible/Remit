import fs from "node:fs";
import { clientFor, retry } from "./lib.mjs";
const client = clientFor(process.argv[2], "principal");
const r = await retry("receipt", () =>
  client.waitForTransactionReceipt({ hash: process.argv[3], status: "FINALIZED", retries: 200, interval: 2000 }), 4);
fs.writeFileSync("/tmp/tx.json", JSON.stringify(r, (k, v) => typeof v === "bigint" ? v.toString() : v, 2));
console.log("written /tmp/tx.json");
