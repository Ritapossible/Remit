import fs from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { studionet, testnetAsimov, testnetBradbury } from "genlayer-js/chains";

export const KEYDIR = process.env.REMIT_KEYS;

// genlayer-js 1.1.8 ships HTTPS endpoints and the current consensus contracts.
// 0.15 pointed the testnet at a plain-HTTP raw IP and a retired consensus
// contract, and hardcoded 21000 gas: every testnet write failed. Asimov and
// Bradbury share chain id 4221 but route through DIFFERENT consensus
// contracts, so the network is always named explicitly.
export const CHAINS = { studio: studionet, asimov: testnetAsimov, bradbury: testnetBradbury };

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
    try {
      return await fn();
    } catch (e) {
      last = e;
      const msg = String(e?.message || e);
      if (i === tries - 1) break;
      const wait = 2000 * Math.pow(2, i);
      console.log(`  ${label}: ${msg.slice(0, 120)} - retry in ${wait}ms`);
      await new Promise((r) => setTimeout(r, wait));
    }
  }
  throw last;
}

// Remit binds on acceptance, not finality, so that is what the scripts wait for.
export const WAIT = "ACCEPTED";

/**
 * The same facts, spelled two ways:
 *   Studio            result_name: MAJORITY_AGREE, leader_receipt[0].result.status: return
 *   Bradbury (1.1.8)  resultName: AGREE, txExecutionResultName: FINISHED_WITH_RETURN
 * Read both here so no script has to. Success is agreement AND a normal return;
 * agreement on an error is a refusal; anything else changed nothing.
 */
export function outcome(r) {
  const consensus = r?.result_name ?? r?.resultName ?? "UNKNOWN";
  const exec = r?.txExecutionResultName ?? "";
  const leader =
    r?.consensus_data?.leader_receipt?.[0]?.result?.status ??
    (/RETURN/.test(exec) ? "return" : /ERROR|ROLLBACK/.test(exec) ? "contract_error" : exec || "unknown");
  const agreed = /AGREE/.test(consensus) && !/DISAGREE/.test(consensus);
  return {
    consensus,
    leader,
    agreed,
    applied: agreed && leader === "return",
    refused: agreed && leader === "contract_error",
    address: r?.data?.contract_address ?? r?.txDataDecoded?.contractAddress ?? r?.contract_address,
  };
}
