import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts are self-hosted: no third-party request on page load, and the site
// renders identically offline or behind a strict network policy.
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/newsreader/opsz-italic.css";
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./styles.css";
import { App } from "./App";
import { AppProvider } from "./state";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
);
