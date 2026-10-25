import { useState } from "react";
import type { Theme } from "../theme";

const NAV = [
  ["/demo", "Try it"],
  ["/how", "How it works"],
  ["/log", "Decision log"],
] as const;

export const REPO = "https://github.com/Ritapossible/Remit/tree/paypal/paypal";

function Sun() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
    </svg>
  );
}
function Moon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
    </svg>
  );
}
function Menu() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

export function Header({ route, theme, onTheme }: { route: string; theme: Theme; onTheme: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-head">
      <div className="wrap">
        <a className="logo" href="#/" aria-label="Remit for PayPal, home" onClick={() => setOpen(false)}>
          <img src={theme === "dark" ? "/brand/logo-on-dark.svg" : "/brand/logo.svg"} alt="Remit" height={30} />
          <span className="badge" style={{ marginLeft: 4 }}>for PayPal</span>
        </a>
        <nav className="site-nav" aria-label="Main">
          {NAV.map(([href, label]) => (
            <a key={href} href={"#" + href} aria-current={route.startsWith(href) ? "page" : undefined}>
              {label}
            </a>
          ))}
        </nav>
        <div className="head-actions">
          <button className="icon-btn" onClick={onTheme} aria-label={theme === "dark" ? "Light theme" : "Dark theme"}>
            {theme === "dark" ? <Sun /> : <Moon />}
          </button>
          <button className="icon-btn menu-btn" aria-expanded={open} aria-label="Menu" onClick={() => setOpen((o) => !o)}>
            <Menu />
          </button>
        </div>
      </div>
      {open && (
        <nav className="sheet" aria-label="Main">
          {NAV.map(([href, label]) => (
            <a key={href} href={"#" + href} onClick={() => setOpen(false)}>
              {label}
            </a>
          ))}
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-foot">
      <div className="wrap">
        <span>Remit for PayPal. A PayPal AI Hackathon entry. PayPal sandbox only: no real money moves.</span>
        <a href={REPO}>Source code (MIT)</a>
        <a href="#/how">How it works</a>
      </div>
    </footer>
  );
}
