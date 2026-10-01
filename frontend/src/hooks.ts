import { useCallback, useEffect, useState } from "react";
import { useApp } from "./state";
import { readDocket, type SpendView } from "./chain/remit";

export function useDocket(autoMs = 0) {
  const { client, guard, mandate } = useApp();
  const [docket, setDocket] = useState<SpendView[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (!mandate) return;
    setLoading(true);
    try {
      setDocket(await readDocket(client, guard));
      setError("");
    } catch (e) {
      setError("Could not read the docket. The gateway may be busy - try refreshing.");
      console.warn(e);
    } finally {
      setLoading(false);
    }
  }, [client, guard, mandate]);

  useEffect(() => {
    setDocket(null);
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!autoMs) return;
    const t = setInterval(() => void reload(), autoMs);
    return () => clearInterval(t);
  }, [autoMs, reload]);

  return { docket, error, loading, reload };
}

/** Seconds since the epoch, ticking. For countdowns only - the contract's own
 *  clock is authoritative, and the UI says "about" where it matters. */
export function useNow(tickMs = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), tickMs);
    return () => clearInterval(t);
  }, [tickMs]);
  return now;
}
