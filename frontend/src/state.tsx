import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NETWORKS, type NetworkId } from "./chain/networks";
import { loadBurner, makeClient, type Client, type Wallet } from "./chain/wallet";
import { useExternalWallet, type ExternalWallet } from "./chain/useExternalWallet";
import { networkIdOfChain } from "./chain/appkit";
import { readMandate } from "./chain/remit";
import type { MandateInfo } from "./lib/mandate";
import { sameAddr } from "./lib/format";

export type Route =
  | { name: "home" }
  | { name: "overview" }
  | { name: "docket" }
  | { name: "case"; id: number }
  | { name: "spend" }
  | { name: "new" }
  | { name: "docs"; slug: string }
  | { name: "roadmap" };

export const APP_ROUTES = new Set(["overview", "docket", "case", "spend", "new"]);

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "").split("?")[0] || "/";
  const m = path.match(/^\/app\/case\/(\d+)$/);
  if (m) return { name: "case", id: Number(m[1]) };
  if (path === "/app" || path === "/app/") return { name: "overview" };
  if (path === "/app/docket") return { name: "docket" };
  if (path === "/app/spend") return { name: "spend" };
  if (path === "/app/new") return { name: "new" };
  const d = path.match(/^\/docs(?:\/([a-z0-9-]+))?\/?$/);
  if (d) return { name: "docs", slug: d[1] ?? "" };
  if (path === "/roadmap") return { name: "roadmap" };
  return { name: "home" };
}

export function href(r: Route): string {
  switch (r.name) {
    case "home":
      return "#/";
    case "overview":
      return "#/app";
    case "case":
      return `#/app/case/${r.id}`;
    case "docs":
      return r.slug ? `#/docs/${r.slug}` : "#/docs";
    case "roadmap":
      return "#/roadmap";
    default:
      return `#/app/${r.name}`;
  }
}

export type Role = "principal" | "agent" | "both" | "observer";

interface AppState {
  route: Route;
  network: NetworkId;
  setNetwork(n: NetworkId): void;
  /** The wallet that signs: a connected wallet if there is one, else the
   *  Studio burner, else none. */
  wallet: Wallet;
  /** Sets the Studio burner (or clears it with kind "none"). */
  setWallet(w: Wallet): void;
  /** The connected wallet, through Reown AppKit or the browser. */
  ext: ExternalWallet;
  /** False while a connected wallet is on a different chain than the app. */
  walletOnNetwork: boolean;
  /** A signer is present and on the app's network. Every write checks this. */
  canSign: boolean;
  guard: string;
  setGuard(g: string): void;
  /** The RemitRail that pays this guard's authorized spends, if one is known. */
  rail: string;
  setRail(r: string): void;
  client: Client;
  mandate: MandateInfo | null;
  mandateError: string;
  reloadMandate(): Promise<void>;
  role: Role;
  pollMs: number;
}

const Ctx = createContext<AppState | null>(null);

function readQuery(): { net?: NetworkId; guard?: string; rail?: string } {
  const q = new URLSearchParams(window.location.search);
  const net = q.get("net");
  return {
    net: net === "studio" || net === "bradbury" ? net : undefined,
    guard: q.get("guard") ?? undefined,
    rail: q.get("rail") ?? undefined,
  };
}

/** The reference rail belongs to the reference guard only. */
function defaultRailFor(net: NetworkId, guard: string): string {
  const n = NETWORKS[net];
  return n.defaultRail && sameAddr(guard, n.defaultGuard) ? n.defaultRail : "";
}

function writeQuery(net: NetworkId, guard: string, rail: string) {
  const q = new URLSearchParams(window.location.search);
  q.set("net", net);
  if (guard) q.set("guard", guard);
  else q.delete("guard");
  if (rail && rail !== defaultRailFor(net, guard)) q.set("rail", rail);
  else q.delete("rail");
  window.history.replaceState(null, "", `${window.location.pathname}?${q}${window.location.hash}`);
}

export function AppProvider({ children }: { children: ReactNode }) {
  const initial = readQuery();
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  const [network, setNetworkRaw] = useState<NetworkId>(initial.net ?? "studio");
  const [burner, setWallet] = useState<Wallet>(() => (network === "studio" ? loadBurner() : { kind: "none" }));
  const ext = useExternalWallet();
  const extRef = useRef(ext);
  extRef.current = ext;
  const [guard, setGuardRaw] = useState<string>(initial.guard ?? NETWORKS[initial.net ?? "studio"].defaultGuard ?? "");
  const [rail, setRailRaw] = useState<string>(
    () => initial.rail ?? defaultRailFor(initial.net ?? "studio", initial.guard ?? NETWORKS[initial.net ?? "studio"].defaultGuard ?? ""),
  );
  const [mandate, setMandate] = useState<MandateInfo | null>(null);
  const [mandateError, setMandateError] = useState("");

  useEffect(() => {
    const onHash = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => writeQuery(network, guard, rail), [network, guard, rail]);

  const setNetwork = useCallback((n: NetworkId) => {
    setNetworkRaw(n);
    // A connected wallet follows the app. If the user declines, the network
    // banner keeps asking and writes stay disabled.
    const e = extRef.current;
    if (e.address && e.chainId !== NETWORKS[n].chain.id) e.switchTo(n).catch((err) => console.warn(err));
    // A burner exists only on Studio. Never carry one onto the testnet.
    setWallet((w) => (n === "studio" ? (w.kind === "none" ? loadBurner() : w) : w.kind === "burner" ? { kind: "none" } : w));
    setGuardRaw(NETWORKS[n].defaultGuard ?? "");
    setRailRaw(defaultRailFor(n, NETWORKS[n].defaultGuard ?? ""));
  }, []);

  // A rail belongs to one guard: changing the guard drops it unless the new
  // guard is the reference one with its reference rail.
  const setGuard = useCallback(
    (g: string) => {
      setGuardRaw(g.trim());
      setRailRaw(defaultRailFor(network, g.trim()));
    },
    [network],
  );
  const setRail = useCallback((r: string) => setRailRaw(r.trim()), []);

  const wallet: Wallet = useMemo(
    () =>
      ext.address && ext.provider
        ? { kind: "wallet", address: ext.address, provider: ext.provider, chainId: ext.chainId ?? 0, name: ext.name }
        : burner,
    [ext.address, ext.provider, ext.chainId, ext.name, burner],
  );
  const walletOnNetwork = wallet.kind !== "wallet" || wallet.chainId === NETWORKS[network].chain.id;
  const canSign = wallet.kind !== "none" && walletOnNetwork;

  // Keep the wallet and the app on the same network.
  //  - On connect, the app's network wins: the wallet is asked to switch.
  //  - Later, if the user moves the wallet to the other GenLayer network
  //    (in the wallet or in the Reown modal), the app follows it.
  const seenChain = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!ext.address || ext.chainId === undefined) {
      seenChain.current = undefined;
      return;
    }
    const first = seenChain.current === undefined;
    const changed = seenChain.current !== ext.chainId;
    seenChain.current = ext.chainId;
    if (ext.chainId === NETWORKS[network].chain.id) return;
    const other = networkIdOfChain(ext.chainId);
    if (!first && changed && other) setNetwork(other);
    else if (first) ext.switchTo(network).catch((err) => console.warn(err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ext.address, ext.chainId]);

  const client = useMemo(() => makeClient(network, wallet), [network, wallet]);

  const reloadMandate = useCallback(async () => {
    if (!/^0x[0-9a-fA-F]{40}$/.test(guard)) {
      setMandate(null);
      setMandateError(guard ? "That is not a contract address." : "");
      return;
    }
    try {
      setMandateError("");
      setMandate(await readMandate(client, guard));
    } catch (e) {
      setMandate(null);
      setMandateError(
        `No Remit guard answered at this address on ${NETWORKS[network].short}. ` +
          `It may be on the other network, or not a Remit contract.`,
      );
      console.warn(e);
    }
  }, [client, guard, network]);

  useEffect(() => {
    void reloadMandate();
  }, [reloadMandate]);

  const address = wallet.kind === "none" ? "" : wallet.address;
  const isP = sameAddr(address, mandate?.principal);
  const isA = sameAddr(address, mandate?.agent);
  const role: Role = isP && isA ? "both" : isP ? "principal" : isA ? "agent" : "observer";

  const value: AppState = {
    route,
    network,
    setNetwork,
    wallet,
    setWallet,
    ext,
    walletOnNetwork,
    canSign,
    guard,
    setGuard,
    rail,
    setRail,
    client,
    mandate,
    mandateError,
    reloadMandate,
    role,
    pollMs: NETWORKS[network].pollMs,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
