import fs from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { studionet, testnetAsimov } from "genlayer-js/chains";

export const KEYDIR = process.env.REMIT_KEYS;
export const CHAINS = { studio: studionet, asimov: testnetAsimov };

export function accountFor(role) {
  const key = fs.readFileSync(`${KEYDIR}/${role}.key`, "utf8").trim();
  return createAccount(key);
}

export function clientFor(network, role) {
  const chain = CHAINS[network];
  if (!chain) throw new Error(`unknown network ${network}`);
  return createClient({ chain, account: accountFor(role) });
}

// Transient RPC failures are common on both networks; a retry loop keeps a
// walkthrough from dying on one bad gateway response.
export async function retry(label, fn, tries = 4) {
  let last;
  for (let i = 0; i < tries; i++) {
    try { return await fn(); }
    catch (e) {
      last = e;
      const msg = String(e?.message || e);
      if (i === tries - 1) break;
      const wait = 2000 * Math.pow(2, i);
      console.log(`  ${label}: ${msg.slice(0, 120)} — retry in ${wait}ms`);
      await new Promise(r => setTimeout(r, wait));
    }
  }
  throw last;
}
