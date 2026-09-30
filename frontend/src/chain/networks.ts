import { studionet, testnetAsimov } from "genlayer-js/chains";
import deployments from "../../../deploy/deployments.json";

export type NetworkId = "studio" | "asimov";

export interface NetworkConfig {
  id: NetworkId;
  label: string;
  short: string;
  chain: typeof studionet;
  /** HTTPS RPC. The SDK's testnet default is plain HTTP to a raw IP, which a
   *  page served over HTTPS cannot call. */
  rpc: string;
  explorer: string;
  /** Studio has a faucet method on its RPC; the testnet has none. */
  faucet: boolean;
  /** Seconds to wait between receipt polls. Testnet finality is slower. */
  pollMs: number;
  defaultGuard?: string;
}

const d = deployments as Record<string, { address?: string }>;

export const NETWORKS: Record<NetworkId, NetworkConfig> = {
  studio: {
    id: "studio",
    label: "GenLayer Studio",
    short: "Studio",
    chain: studionet,
    rpc: "https://studio.genlayer.com/api",
    explorer: "https://genlayer-explorer.vercel.app",
    faucet: true,
    pollMs: 2500,
    defaultGuard: d.studio?.address,
  },
  asimov: {
    id: "asimov",
    label: "Testnet Asimov · Bradbury",
    short: "Testnet",
    chain: testnetAsimov as typeof studionet,
    rpc: "https://rpc-asimov.genlayer.com",
    explorer: "https://explorer-asimov.genlayer.com",
    faucet: false,
    pollMs: 5000,
    defaultGuard: d.asimov?.address,
  },
};
