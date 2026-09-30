import { useEffect, useState } from "react";
import { APP_ROUTES, href, useApp, type Route } from "../state";
import { useTheme } from "../theme";
import { Close, Mark, Menu, Moon, Sun } from "./icons";
import { NETWORKS, type NetworkId } from "../chain/networks";
import {
  balanceOf,
  connectMetaMask,
  createBurner,
  forgetBurner,
  fundOnStudio,
  hasMetaMask,
} from "../chain/wallet";
import { Addr, Gen, Spinner, explainError } from "./ui";

const APP_TABS: { route: Route; label: string }[] = [
  { route: { name: "overview" }, label: "Mandate" },
  { route: { name: "docket" }, label: "Docket" },
  { route: { name: "spend" }, label: "Request a spend" },
  { route: { name: "new" }, label: "New guard" },
];

const SITE_LINKS: { route: Route; label: string; match: (r: Route) => boolean }[] = [
  { route: { name: "home" }, label: "Product", match: (r) => r.name === "home" },
  { route: { name: "overview" }, label: "App", match: (r) => APP_ROUTES.has(r.name) },
  { route: { name: "docs", slug: "" }, label: "Docs", match: (r) => r.name === "docs" },
  { route: { name: "roadmap" }, label: "Roadmap", match: (r) => r.name === "roadmap" },
];

export function SiteHeader() {
  const { route } = useApp();
  const [theme, toggleTheme] = useTheme();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [route]);
  return (
    <header className="site-head">
      <div className="wrap">
        <a className="logo" href="#/" aria-label="Remit home">
          <Mark />
          <b>Remit</b>
        </a>
        <nav className="site-nav" aria-label="Main">
          {SITE_LINKS.map((l) => (
            <a key={l.label} href={href(l.route)} aria-current={l.match(route) ? "page" : undefined}>
              {l.label}
            </a>
          ))}
          <a href="https://github.com/Ritapossible/Remit" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
        <div className="head-actions">
          <button className="icon-btn" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            {theme === "dark" ? <Moon /> : <Sun />}
          </button>
          <button className="icon-btn menu-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Menu">
            {open ? <Close /> : <Menu />}
          </button>
        </div>
      </div>
      {open && (
        <nav className="sheet" aria-label="Mobile">
          {SITE_LINKS.map((l) => (
            <a key={l.label} href={href(l.route)}>
              {l.label}
            </a>
          ))}
          <a href="https://github.com/Ritapossible/Remit" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
      )}
    </header>
  );
}

export function AppBar() {
  const { route, network, setNetwork } = useApp();
  return (
    <div className="app-bar">
      <div className="wrap">
        <nav className="tabs" aria-label="App">
          {APP_TABS.map((l) => {
            const active = l.route.name === route.name || (l.route.name === "docket" && route.name === "case");
            return (
              <a key={l.label} href={href(l.route)} aria-current={active ? "page" : undefined}>
                {l.label}
              </a>
            );
          })}
        </nav>
        <div className="right">
          <select aria-label="Network" value={network} onChange={(e) => setNetwork(e.target.value as NetworkId)}>
            {Object.values(NETWORKS).map((n) => (
              <option key={n.id} value={n.id}>
                {n.label}
              </option>
            ))}
          </select>
          <WalletControl />
        </div>
      </div>
    </div>
  );
}

function WalletControl() {
  const { network, wallet, setWallet } = useApp();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [balance, setBalance] = useState<bigint | null>(null);

  const address = wallet.kind === "none" ? "" : wallet.address;

  useEffect(() => {
    let live = true;
    setBalance(null);
    if (!address) return;
    balanceOf(network, address)
      .then((b) => live && setBalance(b))
      .catch(() => live && setBalance(null));
    return () => {
      live = false;
    };
  }, [address, network, busy]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErr("");
    try {
      await fn();
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setBusy(false);
    }
  };

  if (wallet.kind === "none") {
    return (
      <div className="row">
        {network === "studio" && (
          <button
            className="btn"
            disabled={busy}
            title="A key generated in this browser and funded from Studio's faucet. Studio only; its GEN has no value."
            onClick={() =>
              run(async () => {
                const w = createBurner();
                if (w.kind === "burner") await fundOnStudio(w.address);
                setWallet(w);
              })
            }
          >
            {busy ? <Spinner /> : null} Studio burner
          </button>
        )}
        <button
          className="btn primary"
          disabled={busy || !hasMetaMask()}
          title={hasMetaMask() ? "" : "MetaMask is not installed in this browser"}
          onClick={() => run(async () => setWallet(await connectMetaMask(network)))}
        >
          Connect MetaMask
        </button>
        {err && <span className="small" style={{ color: "var(--refused)" }}>{err}</span>}
      </div>
    );
  }

  return (
    <div className="row">
      <span className="small muted">{wallet.kind === "burner" ? "Studio burner" : "MetaMask"}</span>
      <Addr value={address} />
      <span className="small">{balance === null ? "…" : <Gen atto={balance} />}</span>
      {wallet.kind === "burner" && (
        <button className="btn sm" disabled={busy} onClick={() => run(() => fundOnStudio(address))}>
          {busy ? <Spinner /> : "Top up"}
        </button>
      )}
      <button
        className="btn sm ghost"
        onClick={() => {
          if (wallet.kind === "burner") forgetBurner();
          setWallet({ kind: "none" });
        }}
      >
        {wallet.kind === "burner" ? "Forget" : "Disconnect"}
      </button>
      {err && <span className="small" style={{ color: "var(--refused)" }}>{err}</span>}
    </div>
  );
}

export function GuardBar() {
  const { guard, setGuard, network, role, mandate, mandateError, wallet } = useApp();
  const [draft, setDraft] = useState(guard);
  useEffect(() => setDraft(guard), [guard]);
  const def = NETWORKS[network].defaultGuard;
  const roleText =
    wallet.kind === "none"
      ? "Connect a wallet to act. Anyone can read."
      : role === "observer"
        ? "You are an observer of this guard."
        : role === "both"
          ? "You are the principal and the agent."
          : `You are the ${role}.`;
  return (
    <div className="guardbar">
      <span>Guard</span>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          setGuard(draft);
        }}
      >
        <input
          className="mono"
          aria-label="Guard contract address"
          placeholder="0x… Remit guard address"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button className="btn sm" type="submit">
          Load
        </button>
        {def && def.toLowerCase() !== guard.toLowerCase() && (
          <button className="btn sm ghost" type="button" onClick={() => setGuard(def)}>
            Use the reference guard
          </button>
        )}
      </form>
      {mandate && <span>· {roleText}</span>}
      {mandateError && <span style={{ color: "var(--refused)" }}>· {mandateError}</span>}
    </div>
  );
}
