import { StrictMode, type ReactNode } from "react";
import { WagmiProvider } from "wagmi";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
// Creates the Reown AppKit modal when a project ID is configured.
import { wagmiAdapter } from "./chain/appkit";

const queryClient = new QueryClient();
function WalletRoot({ children }: { children: ReactNode }) {
  if (!wagmiAdapter) return <>{children}</>;
  return (
    <WagmiProvider config={wagmiAdapter.wagmiConfig}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </WagmiProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WalletRoot>
      <AppProvider>
        <App />
      </AppProvider>
    </WalletRoot>
  </StrictMode>,
);
