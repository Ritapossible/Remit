import { useEffect, useState } from "react";
import { APP_ROUTES, href, useApp, type Route } from "../state";
import { useTheme } from "../theme";
import { Close, Mark, Menu, Moon, Sun } from "./icons";
import { NETWORKS, type NetworkId } from "../chain/networks";
import { balanceOf, createBurner, forgetBurner, fundOnStudio } from "../chain/wallet";
import { networkIdOfChain } from "../chain/appkit";
import { Addr, Gen, Spinner, explainError } from "./ui";

const APP_TABS: { route: Route; label: string; short?: string }[] = [
  { route: { name: "overview" }, label: "Mandate" },
  { route: { name: "docket" }, label: "Docket" },
  { route: { name: "spend" }, label: "Request a spend", short: "Spend" },
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
              <a key={l.label} href={href(l.route)} aria-current={active ? "page" : undefined} aria-label={l.label}>
                {l.short ? (
                  <>
                    <span className="tab-long">{l.label}</span>
                    <span className="tab-short">{l.short}</span>
                  </>
                ) : (
                  l.label
                )}
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
      <NetworkBanner />
    </div>
  );
}

/** Shown while a connected wallet is on a different chain than the app. Writes
 *  stay disabled until the wallet switches, or the app moves to the wallet's
 *  GenLayer network. */
function NetworkBanner() {
  const { wallet, network, setNetwork, ext, walletOnNetwork } = useApp();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (wallet.kind !== "wallet" || walletOnNetwork) return null;
  const want = NETWORKS[network];
  const other = networkIdOfChain(wallet.chainId);
  const on = other ? NETWORKS[other].label : wallet.chainId ? `chain ${wallet.chainId}` : "another network";
  return (
    <div className="wrap">
      <div className="notice warn net-banner" role="alert">
        <span>
          Your wallet is on <strong>{on}</strong>. Switch it to <strong>{want.label}</strong> to sign here.
        </span>
        <span className="row">
          <button
            className="btn sm primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setErr("");
              try {
                await ext.switchTo(network);
              } catch (e) {
                setErr(explainError(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <Spinner /> : null} Switch to {want.short}
          </button>
          {other && (
            <button className="btn sm" disabled={busy} onClick={() => setNetwork(other)}>
              Use {NETWORKS[other].short} instead
            </button>
          )}
        </span>
        {err && <span className="small" style={{ color: "var(--refused)" }}>{err}</span>}
      </div>
    </div>
  );
}

function WalletControl() {
  const { network, wallet, setWallet, ext, walletOnNetwork } = useApp();
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

  const connectButton = (
    <button
      className="btn primary"
      // Never disabled for the wallet's own state: a stale session can leave
      // AppKit "reconnecting" indefinitely on a phone, and a dead button gives
      // the user no way out. Opening the picker again is the way out.
      disabled={busy}
      onClick={() =>
        run(async () => {
          if (!ext.available)
            throw new Error(
              "No wallet in this browser. Open this page in your wallet app's browser, or use the Studio burner.",
            );
          await ext.connect();
        })
      }
    >
      {ext.connecting || busy ? <Spinner /> : null} Connect wallet
    </button>
  );

  if (wallet.kind === "none") {
    return (
      <div className="row connect-row">
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
        {connectButton}
        {err && <span className="small" style={{ color: "var(--refused)" }}>{err}</span>}
      </div>
    );
  }

  if (wallet.kind === "wallet") {
    return (
      <div className="row wallet-row">
        <button
          className="btn wallet-chip"
          onClick={() => (ext.via === "appkit" ? run(ext.manage) : undefined)}
          title={ext.via === "appkit" ? "Account, network and disconnect" : wallet.name}
        >
          <span className={`dot ${walletOnNetwork ? "ok" : "bad"}`} aria-hidden />
          <span className="small muted wallet-name">{wallet.name}</span>
          <Addr value={address} />
          {walletOnNetwork && <span className="small">{balance === null ? "…" : <Gen atto={balance} />}</span>}
        </button>
        <button className="btn sm ghost" onClick={() => run(ext.disconnect)}>
          Disconnect
        </button>
        {err && <span className="small" style={{ color: "var(--refused)" }}>{err}</span>}
      </div>
    );
  }

  return (
    <div className="row burner-row">
      <span className="small muted">Studio burner</span>
      <Addr value={address} />
      <span className="small">{balance === null ? "…" : <Gen atto={balance} />}</span>
      <button className="btn sm" disabled={busy} onClick={() => run(() => fundOnStudio(address))}>
        {busy ? <Spinner /> : "Top up"}
      </button>
      <button
        className="btn sm ghost"
        onClick={() => {
          forgetBurner();
          setWallet({ kind: "none" });
        }}
      >
        Forget
      </button>
      {connectButton}
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
