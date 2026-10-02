import { useCallback, useEffect, useRef, useState } from "react";
import {
  useAppKit,
  useAppKitAccount,
  useAppKitNetwork,
  useAppKitProvider,
  useAppKitState,
  useDisconnect,
  useWalletInfo,
} from "@reown/appkit/react";
import { APPKIT_NETWORKS, appKitEnabled, networkIdOfChain } from "./appkit";
import { injected, switchProvider, type Eip1193 } from "./wallet";
import type { NetworkId } from "./networks";

/** A wallet the user brings, whichever way it is connected. */
export interface ExternalWallet {
  /** "appkit" opens Reown's wallet picker; "injected" talks to window.ethereum. */
  via: "appkit" | "injected";
  available: boolean;
  address: string;
  provider?: Eip1193;
  chainId?: number;
  name: string;
  connecting: boolean;
  connect(): Promise<void>;
  /** The account view: address, balance, network and disconnect. */
  manage(): Promise<void>;
  disconnect(): Promise<void>;
  switchTo(n: NetworkId): Promise<void>;
}

function useAppKitWallet(): ExternalWallet {
  const { open, close } = useAppKit();
  const { open: modalOpen } = useAppKitState();
  const { address, isConnected, status } = useAppKitAccount({ namespace: "eip155" });
  const { walletProvider } = useAppKitProvider<Eip1193>("eip155");
  const { chainId, switchNetwork } = useAppKitNetwork();
  const { disconnect } = useDisconnect();
  const { walletInfo } = useWalletInfo("eip155");
  const connected = isConnected && !!address && !!walletProvider;

  // The chain the wallet is really on, asked of the wallet itself. AppKit's own
  // network state keeps the last supported network while a wallet sits on an
  // unsupported chain, and signing there would fail or go to the wrong chain.
  const [walletChain, setWalletChain] = useState<number>();
  useEffect(() => {
    setWalletChain(undefined);
    if (!connected || !walletProvider) return;
    let live = true;
    const p = walletProvider as Eip1193 & { on?: Function; removeListener?: Function };
    const read = () =>
      p
        .request({ method: "eth_chainId" })
        .then((c) => live && setWalletChain(Number(c)))
        .catch(() => live && setWalletChain(chainId === undefined ? undefined : Number(chainId)));
    const onChain = (c: string | number) => live && setWalletChain(Number(c));
    void read();
    p.on?.("chainChanged", onChain);
    return () => {
      live = false;
      p.removeListener?.("chainChanged", onChain);
    };
  }, [connected, walletProvider, chainId]);

  // AppKit opens its "Switch network" sheet when the wallet is on a chain the
  // app does not support, and leaves it open after the wallet has switched by
  // another route (the app's own request, or the wallet's UI). Close it once
  // the wallet reaches a GenLayer network.
  const lastChain = useRef<number | undefined>(undefined);
  useEffect(() => {
    const before = lastChain.current;
    lastChain.current = walletChain;
    if (modalOpen && walletChain !== undefined && before !== walletChain && networkIdOfChain(walletChain) && !networkIdOfChain(before))
      void close();
  }, [walletChain, modalOpen, close]);

  return {
    via: "appkit",
    available: true,
    address: connected ? address! : "",
    provider: connected ? walletProvider : undefined,
    chainId: connected ? walletChain : undefined,
    name: walletInfo?.name ?? "Wallet",
    connecting: status === "connecting" || status === "reconnecting",
    connect: async () => void (await open({ view: "Connect" })),
    manage: async () => void (await open({ view: "Account" })),
    disconnect: () => disconnect({ namespace: "eip155" }),
    switchTo: async (n) => {
      // Ask the wallet itself first. AppKit's switchNetwork compares against
      // its own state, which still reads the last supported network while the
      // wallet sits on another chain, and can then skip the request.
      if (connected && walletProvider) {
        try {
          await switchProvider(walletProvider, n);
          return;
        } catch (e) {
          if (Number((e as { code?: number })?.code) === 4001) throw e;
        }
      }
      await switchNetwork(APPKIT_NETWORKS[n]);
    },
  };
}

function useInjectedWallet(): ExternalWallet {
  const [address, setAddress] = useState("");
  const [chainId, setChainId] = useState<number>();
  const [connecting, setConnecting] = useState(false);
  const eth = injected();

  useEffect(() => {
    if (!eth?.on) return;
    const onAccounts = (a: string[]) => setAddress(a?.[0] ?? "");
    const onChain = (c: string) => setChainId(parseInt(c, 16));
    eth.on("accountsChanged", onAccounts);
    eth.on("chainChanged", onChain);
    return () => {
      eth.removeListener?.("accountsChanged", onAccounts);
      eth.removeListener?.("chainChanged", onChain);
    };
  }, [eth]);

  const connect = useCallback(async () => {
    if (!eth) throw new Error("No wallet found in this browser.");
    setConnecting(true);
    try {
      const [a] = (await eth.request({ method: "eth_requestAccounts" })) as string[];
      if (!a) throw new Error("The wallet shared no account.");
      setChainId(parseInt((await eth.request({ method: "eth_chainId" })) as string, 16));
      setAddress(a);
    } finally {
      setConnecting(false);
    }
  }, [eth]);

  return {
    via: "injected",
    available: !!eth,
    address,
    provider: address ? eth : undefined,
    chainId,
    name: (eth as { isMetaMask?: boolean } | undefined)?.isMetaMask ? "MetaMask" : "Browser wallet",
    connecting,
    connect,
    manage: async () => {},
    disconnect: async () => setAddress(""),
    switchTo: async (n) => {
      if (eth) await switchProvider(eth, n);
    },
  };
}

// Chosen once at load, so the same hooks run on every render.
export const useExternalWallet: () => ExternalWallet = appKitEnabled ? useAppKitWallet : useInjectedWallet;
