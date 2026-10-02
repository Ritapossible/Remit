import { useEffect, useState } from "react";
import { appKit, themeVariablesFor } from "./chain/appkit";

export type Theme = "light" | "dark";
const KEY = "remit.theme";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** A per-viewer convenience only: storage can fail, and the page must render
 *  correctly without it. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === "light" || saved === "dark") return saved;
    } catch {
      /* storage unavailable */
    }
    return systemTheme();
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    // The wallet modal follows the site's theme.
    appKit?.setThemeMode(theme);
    appKit?.setThemeVariables(themeVariablesFor(theme));
  }, [theme]);
  const toggle = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* storage unavailable */
      }
      return next;
    });
  return [theme, toggle];
}
