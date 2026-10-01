import { createAccount, createClient, generatePrivateKey } from "genlayer-js";
import { NETWORKS, type NetworkId } from "./networks";

// Two ways to sign:
//
//  - MetaMask, on either network. This is how real testnet GEN is spent.
//  - A Studio burner: a key generated in this browser and funded from Studio's
//    faucet. It exists so anyone can try the full flow in under a minute
//    without a wallet. It is never offered on the testnet, and it is stored in
//    localStorage in plain text - which is acceptable only because Studio GEN
//    has no value.

export type Wallet =
  | { kind: "none" }
  | { kind: "metamask"; address: string }
  | { kind: "burner"; address: string; key: `0x${string}` };

const BURNER_KEY = "remit.studio-burner.v1";

type Eth = { request(args: { method: string; params?: unknown[] }): Promise<unknown> };
const eth = (): Eth | undefined => (window as unknown as { ethereum?: Eth }).ethereum;
export const hasMetaMask = () => !!eth();

export function makeClient(network: NetworkId, wallet: Wallet) {
  const net = NETWORKS[network];
  const account =
    wallet.kind === "burner"
      ? createAccount(wallet.key)
      : wallet.kind === "metamask"
        ? (wallet.address as `0x${string}`)
        : // Read-only: a throwaway account that never signs, so gen_call has a sender.
          createAccount(generatePrivateKey());
  return createClient({ chain: net.chain, endpoint: net.rpc, account } as Parameters<typeof createClient>[0]);
}

export type Client = ReturnType<typeof makeClient>;

export async function connectMetaMask(network: NetworkId): Promise<Wallet> {
  const provider = eth();
  if (!provider) throw new Error("MetaMask is not installed in this browser.");
  const net = NETWORKS[network];
  const chainId = `0x${net.chain.id.toString(16)}`;
  const current = (await provider.request({ method: "eth_chainId" })) as string;
  if (current !== chainId) {
    try {
      await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId }] });
    } catch {
      // Unknown chain: add it with the HTTPS RPC, never the SDK's plain-HTTP default.
      await provider.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId,
            chainName: net.label,
            rpcUrls: [net.rpc],
            nativeCurrency: net.chain.nativeCurrency,
            blockExplorerUrls: [net.explorer],
          },
        ],
      });
    }
  }
  const [address] = (await provider.request({ method: "eth_requestAccounts" })) as string[];
  if (!address) throw new Error("No account was shared by MetaMask.");
  return { kind: "metamask", address };
}

export function loadBurner(): Wallet {
  try {
    const key = localStorage.getItem(BURNER_KEY) as `0x${string}` | null;
    if (key && /^0x[0-9a-fA-F]{64}$/.test(key)) return { kind: "burner", key, address: createAccount(key).address };
  } catch {
    /* storage unavailable: fall through to a fresh, unsaved burner */
  }
  return { kind: "none" };
}

export function createBurner(): Wallet {
  const key = generatePrivateKey();
  try {
    localStorage.setItem(BURNER_KEY, key);
  } catch {
    /* private mode: the burner lives for this tab only */
  }
  return { kind: "burner", key, address: createAccount(key).address };
}

export function forgetBurner() {
  try {
    localStorage.removeItem(BURNER_KEY);
  } catch {
    /* nothing to forget */
  }
}

async function rpc(url: string, method: string, params: unknown[]) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params }),
  });
  const body = await res.json();
  if (body.error) throw new Error(body.error.message ?? "RPC error");
  return body.result;
}

export async function balanceOf(network: NetworkId, address: string): Promise<bigint> {
  return BigInt((await rpc(NETWORKS[network].rpc, "eth_getBalance", [address, "latest"])) ?? "0x0");
}

/** Studio only. The amount travels as a raw JSON integer - a hex or string
 *  amount is rejected by sim_fundAccount. */
export async function fundOnStudio(address: string, gen = 5): Promise<void> {
  const body = `{"jsonrpc":"2.0","id":${Date.now()},"method":"sim_fundAccount","params":["${address}",${BigInt(gen) * 10n ** 18n}]}`;
  const res = await fetch(NETWORKS.studio.rpc, { method: "POST", headers: { "Content-Type": "application/json" }, body });
  const json = await res.json();
  if (json.error) throw new Error(json.error.message ?? "Faucet refused");
}
