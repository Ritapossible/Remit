import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { NETWORKS, type NetworkId } from "./chain/networks";
import { loadBurner, makeClient, type Client, type Wallet } from "./chain/wallet";
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
  wallet: Wallet;
  setWallet(w: Wallet): void;
  guard: string;
  setGuard(g: string): void;
  client: Client;
  mandate: MandateInfo | null;
  mandateError: string;
  reloadMandate(): Promise<void>;
  role: Role;
  pollMs: number;
}

const Ctx = createContext<AppState | null>(null);

function readQuery(): { net?: NetworkId; guard?: string } {
  const q = new URLSearchParams(window.location.search);
  const net = q.get("net");
  return { net: net === "studio" || net === "bradbury" ? net : undefined, guard: q.get("guard") ?? undefined };
}

function writeQuery(net: NetworkId, guard: string) {
  const q = new URLSearchParams(window.location.search);
  q.set("net", net);
  if (guard) q.set("guard", guard);
  else q.delete("guard");
  window.history.replaceState(null, "", `${window.location.pathname}?${q}${window.location.hash}`);
}

export function AppProvider({ children }: { children: ReactNode }) {
  const initial = readQuery();
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  const [network, setNetworkRaw] = useState<NetworkId>(initial.net ?? "studio");
  const [wallet, setWallet] = useState<Wallet>(() => (network === "studio" ? loadBurner() : { kind: "none" }));
  const [guard, setGuardRaw] = useState<string>(initial.guard ?? NETWORKS[initial.net ?? "studio"].defaultGuard ?? "");
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

  useEffect(() => writeQuery(network, guard), [network, guard]);

  const setNetwork = useCallback((n: NetworkId) => {
    setNetworkRaw(n);
    // A burner exists only on Studio. Never carry one onto the testnet.
    setWallet((w) => (n === "studio" ? (w.kind === "none" ? loadBurner() : w) : w.kind === "burner" ? { kind: "none" } : w));
    setGuardRaw(NETWORKS[n].defaultGuard ?? "");
  }, []);

  const setGuard = useCallback((g: string) => setGuardRaw(g.trim()), []);

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
    guard,
    setGuard,
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
