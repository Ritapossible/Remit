// Funds deployment accounts on the testnet from a funding key. Plain native
// transfers between wallets, confirmed by reading balances back afterwards.
import { createWalletClient, createPublicClient, http, defineChain, parseEther } from "viem";
import { accountFor } from "./lib.mjs";

const chain = defineChain({
  id: 4221,
  name: "GenLayer Testnet Asimov",
  nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc-asimov.genlayer.com"] } },
});
const transport = http("https://rpc-asimov.genlayer.com");
const pub = createPublicClient({ chain, transport });
const funder = accountFor("funder");
const wallet = createWalletClient({ chain, transport, account: funder });

const plan = process.argv.slice(2).map((a) => a.split("=")); // role=amount
for (const [role, amount] of plan) {
  const to = accountFor(role).address;
  const before = await pub.getBalance({ address: to });
  const hash = await wallet.sendTransaction({ to, value: parseEther(amount) });
  const r = await pub.waitForTransactionReceipt({ hash, timeout: 180000 });
  const after = await pub.getBalance({ address: to });
  console.log(`${role.padEnd(10)} +${amount} GEN  status=${r.status}  ${Number(before) / 1e18} -> ${Number(after) / 1e18}  tx ${hash}`);
}
console.log(`funder left: ${Number(await pub.getBalance({ address: funder.address })) / 1e18} GEN`);
