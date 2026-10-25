import { useEffect, useState } from "react";
import type { Theme } from "../theme";

const NAV = [
  ["/", "Product"],
  ["/demo", "Try it"],
  ["/how", "How it works"],
  ["/log", "Decision log"],
] as const;

export const REPO = "https://github.com/Ritapossible/Remit/tree/paypal/paypal";
/** Remit on GenLayer, the product this one is built on. */
export const REMIT_SITE = "https://remit-v1.vercel.app";

// The same icons as Remit's own site. Stroke uses currentColor so they follow the theme.
const S = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

const Sun = () => (
  <svg {...S}>
    <circle cx="12" cy="12" r="4.2" fill="currentColor" stroke="none" />
    {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
      <line key={a} x1="12" y1="2.6" x2="12" y2="4.6" transform={`rotate(${a} 12 12)`} />
    ))}
  </svg>
);
const Moon = () => (
  <svg {...S}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" fill="currentColor" stroke="none" />
  </svg>
);
const Menu = () => (
  <svg {...S} width={26}>
    <line x1="3" y1="7" x2="21" y2="7" />
    <line x1="5" y1="12" x2="21" y2="12" />
    <line x1="8" y1="17" x2="21" y2="17" />
  </svg>
);
const Close = () => (
  <svg {...S}>
    <line x1="5" y1="5" x2="19" y2="19" />
    <line x1="19" y1="5" x2="5" y2="19" />
  </svg>
);

const current = (route: string, href: string) => (href === "/" ? route === "/" || route === "" : route.startsWith(href));

export function Header({ route, theme, onTheme }: { route: string; theme: Theme; onTheme: () => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [route]);
  return (
    <header className="site-head">
      <div className="wrap">
        <a className="logo" href="#/" aria-label="Remit for PayPal, home">
          <img src={theme === "dark" ? "/brand/logo-on-dark.svg" : "/brand/logo.svg"} alt="Remit" height={30} />
        </a>
        <nav className="site-nav" aria-label="Main">
          {NAV.map(([href, label]) => (
            <a key={href} href={"#" + href} aria-current={current(route, href) ? "page" : undefined}>
              {label}
            </a>
          ))}
          <a href={REPO} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
        <div className="head-actions">
          <button className="icon-btn" onClick={onTheme} aria-label={theme === "dark" ? "Light theme" : "Dark theme"}>
            {theme === "dark" ? <Moon /> : <Sun />}
          </button>
          <button className="icon-btn menu-btn" aria-expanded={open} aria-label="Menu" onClick={() => setOpen((o) => !o)}>
            {open ? <Close /> : <Menu />}
          </button>
        </div>
      </div>
      {open && (
        <nav className="sheet" aria-label="Mobile">
          {NAV.map(([href, label]) => (
            <a key={href} href={"#" + href} onClick={() => setOpen(false)}>
              {label}
            </a>
          ))}
          <a href={REPO} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-foot">
      <div className="wrap">
        <nav className="foot-links" aria-label="Footer">
          <a href="#/how">How it works</a>
          <a href="#/log">Decision log</a>
          <a href={REPO} target="_blank" rel="noreferrer">Source code</a>
          <a href={REMIT_SITE} target="_blank" rel="noreferrer">Remit on GenLayer</a>
        </nav>
        <p className="copyright">© {new Date().getFullYear()} Remit for PayPal</p>
      </div>
    </footer>
  );
}
