import { APP_ROUTES, href, useApp } from "./state";
import { AppBar, GuardBar, SiteHeader } from "./components/Header";
import { Mark } from "./components/icons";
import { Home } from "./views/Home";
import { Overview } from "./views/Overview";
import { Docket } from "./views/Docket";
import { CaseView } from "./views/CaseView";
import { RequestSpend } from "./views/RequestSpend";
import { NewGuard } from "./views/NewGuard";
import { Docs } from "./views/Docs";
import { Roadmap } from "./views/Roadmap";
import { REPO_URL } from "./lib/docs";

export function App() {
  const { route } = useApp();
  const inApp = APP_ROUTES.has(route.name);
  return (
    <>
      <a className="sr-only" href="#main">
        Skip to content
      </a>
      <SiteHeader />
      {inApp && <AppBar />}
      <main id="main">
        {route.name === "home" && <Home />}
        {inApp && (
          <div className="wrap app-main">
            {route.name !== "new" && <GuardBar />}
            {route.name === "overview" && <Overview />}
            {route.name === "docket" && <Docket />}
            {route.name === "case" && <CaseView id={route.id} />}
            {route.name === "spend" && <RequestSpend />}
            {route.name === "new" && (
              <div style={{ paddingTop: 28 }}>
                <NewGuard />
              </div>
            )}
          </div>
        )}
        {route.name === "docs" && <Docs slug={route.slug} />}
        {route.name === "roadmap" && <Roadmap />}
      </main>
      <Footer />
    </>
  );
}

function Footer() {
  return (
    <footer className="site-foot">
      <div className="wrap">
        <div>
          <a className="logo" href="#/" style={{ marginBottom: 12 }}>
            <Mark size={28} />
            <b style={{ fontSize: 22 }}>Remit</b>
          </a>
          <p style={{ margin: "12px 0 0", maxWidth: 34 + "ch" }}>
            Spending authority for AI agents. Built on GenLayer Intelligent Contracts. MIT licensed.
          </p>
        </div>
        <div>
          <h4>Product</h4>
          <ul>
            <li><a href={href({ name: "overview" })}>App</a></li>
            <li><a href={href({ name: "new" })}>Create a guard</a></li>
            <li><a href={href({ name: "roadmap" })}>Roadmap</a></li>
          </ul>
        </div>
        <div>
          <h4>Docs</h4>
          <ul>
            <li><a href={href({ name: "docs", slug: "getting-started" })}>Getting started</a></li>
            <li><a href={href({ name: "docs", slug: "integration" })}>Integration</a></li>
            <li><a href={href({ name: "docs", slug: "genvm-notes" })}>Building on GenVM</a></li>
          </ul>
        </div>
        <div>
          <h4>Ecosystem</h4>
          <ul>
            <li><a href="https://genlayer.com" target="_blank" rel="noreferrer">genlayer.com</a></li>
            <li><a href="https://skills.genlayer.com" target="_blank" rel="noreferrer">skills.genlayer.com</a></li>
            <li><a href={REPO_URL} target="_blank" rel="noreferrer">Source on GitHub</a></li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
