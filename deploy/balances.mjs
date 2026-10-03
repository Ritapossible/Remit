// Balances of the deployment roles on a network (read-only).
import { accountFor, CHAINS } from "./lib.mjs";

const network = process.argv[2] || "studio";
const rpc = CHAINS[network].rpcUrls.default.http[0];
for (const role of ["principal", "agent", "challenger", "funder", "vendor"]) {
  const address = accountFor(role).address;
  const res = await fetch(rpc, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getBalance", params: [address, "latest"] }),
  });
  console.log(role.padEnd(11), address, Number(BigInt((await res.json()).result ?? "0x0")) / 1e18, "GEN");
}
