import { studionet, testnetBradbury } from "genlayer-js/chains";
import deployments from "../../../deploy/deployments.json";

export type NetworkId = "studio" | "bradbury";

export interface NetworkConfig {
  id: NetworkId;
  label: string;
  short: string;
  chain: typeof studionet;
  rpc: string;
  explorer: string;
  /** Studio has a faucet method on its RPC; the testnet has none. */
  faucet: boolean;
  pollMs: number;
  defaultGuard?: string;
  /** Whether the app can deploy a guard here today. Bradbury caps a
   *  transaction at 2^24 gas; the single-contract build exceeds it, so
   *  deployment there waits on the engine/guard split (see the roadmap). */
  deployable: boolean;
}

const d = deployments as Record<string, { address?: string }>;
const explorerOf = (c: typeof studionet) => (c.blockExplorers?.default.url ?? "").replace(/\/$/, "");

// Chain config comes from genlayer-js 1.1.8. Older releases pointed the testnet
// at a plain-HTTP raw IP and a retired consensus contract. Bradbury shares
// chain id 4221 with Asimov but routes through a different consensus contract,
// so it is named explicitly and never inferred from the chain id.
export const NETWORKS: Record<NetworkId, NetworkConfig> = {
  studio: {
    id: "studio",
    label: "GenLayer Studio",
    short: "Studio",
    chain: studionet,
    rpc: studionet.rpcUrls.default.http[0],
    explorer: explorerOf(studionet),
    faucet: true,
    pollMs: 2500,
    defaultGuard: d.studio?.address,
    deployable: true,
  },
  bradbury: {
    id: "bradbury",
    label: "GenLayer Bradbury testnet",
    short: "Bradbury",
    chain: testnetBradbury as typeof studionet,
    rpc: testnetBradbury.rpcUrls.default.http[0],
    explorer: explorerOf(testnetBradbury as typeof studionet),
    faucet: false,
    pollMs: 4000,
    defaultGuard: d.bradbury?.address,
    deployable: false,
  },
};
