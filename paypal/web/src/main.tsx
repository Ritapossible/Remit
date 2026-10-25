import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader";
import "@fontsource/jetbrains-mono";
import "./tokens.css";
import "./app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Footer, Header } from "./components/chrome";
import { useRoute, useTheme } from "./theme";
import { Demo } from "./views/Demo";
import { Home } from "./views/Home";
import { How } from "./views/How";
import { Log } from "./views/Log";

function App() {
  const route = useRoute();
  const [theme, toggle] = useTheme();
  const view = route.startsWith("/demo") ? <Demo /> : route.startsWith("/log") ? <Log /> : route.startsWith("/how") ? <How /> : <Home />;
  return (
    <>
      <Header route={route} theme={theme} onTheme={toggle} />
      <main id="main">{view}</main>
      {!route.startsWith("/demo") && <Footer />}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
