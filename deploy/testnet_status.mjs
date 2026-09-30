// Reports whether the testnet deploy can proceed, and why not if it cannot.
import { accountFor, CHAINS } from "./lib.mjs";
const rpc = CHAINS.testnetAsimov?.rpcUrls?.default?.http?.[0] ?? "https://rpc-asimov.genlayer.com";
for (const role of ["principal", "agent"]) {
  const a = accountFor(role).address;
  const r = await fetch(rpc, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", method: "eth_getBalance", params: [a, "latest"], id: 1 }) });
  const j = await r.json();
  const bal = BigInt(j.result ?? "0x0");
  console.log(`${role.padEnd(10)} ${a}  ${Number(bal) / 1e18} GEN  ${bal > 0n ? "READY" : "NEEDS FUNDING"}`);
}
