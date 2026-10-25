// Every call the web app makes to the Remit server. Shapes mirror
// remit_paypal/web.py and remit_paypal/mcp_server.py.

import { useEffect, useRef, useState } from "react";

export interface Session {
  session_id: string;
  orders: string[];
  shop: string;
}

export interface Order {
  order_id: string;
  items: { name: string; quantity: number }[];
  paid: string;
  refunded: string;
  refundable: string;
  paid_at: number;
  shipping: { status: string; carrier: string; updated_at: number } | null;
  open_disputes: number;
}

/** What request_refund returns through MCP. */
export interface RefundResult {
  request_id: string;
  outcome: "refunded" | "refused";
  reason: string;
  decided_by: string;
  rules: string[];
  panel: { model: string; verdict: string; confidence: number }[];
  paypal_refund_id: string | null;
}

export type ConsoleEvent = { id: number; at: number } & (
  | { type: "customer"; text: string }
  | { type: "agent"; text: string }
  | { type: "error"; text: string }
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; result: Record<string, unknown> }
);

export interface LogEntry {
  seq: number;
  at: number;
  kind: "requested" | "facts" | "engine" | "panel" | "refunded" | "refused" | "failed";
  body: Record<string, unknown>;
  prev: string;
  hash: string;
}

export interface Anchor {
  seq: number;
  hash: string;
  tx: string;
  at: number;
}

export interface Decision {
  request_id: string;
  state: string;
  paypal_refund_id: string | null;
  log: LogEntry[];
  anchor?: Anchor | null;
}

export type AnchorStatus =
  | { configured: false }
  | {
      configured: true;
      contract: string;
      explorer: string;
      head_seq: number;
      anchor: Anchor | null;
      pending: boolean;
      last_error: string;
      check: { matches: boolean | null; seq?: number; hash?: string; reason?: string };
    };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () =>
    call<{ ok: boolean; mode: "offline" | "sandbox"; agent: string; log_verifies: boolean; log_broken_at: number | null }>(
      "/api/health",
    ),
  session: () => call<Session>("/api/session", { method: "POST" }),
  orders: (sid: string) => call<Order[]>(`/api/orders?session_id=${encodeURIComponent(sid)}`),
  chat: (sid: string, message: string) =>
    call<{ reply: string }>("/api/chat", { method: "POST", body: JSON.stringify({ session_id: sid, message }) }),
  log: (since = 0) => call<{ verifies: boolean; broken_at: number | null; entries: LogEntry[] }>(`/api/log?since=${since}`),
  decision: (id: string) => call<Decision>(`/api/decisions/${encodeURIComponent(id)}`),
  anchor: () => call<AnchorStatus>("/api/anchor"),
};

/** The session's live console: server-sent events, reconnecting with backoff.
 *  Events are de-duplicated by id, so a reconnect's replay is harmless. */
export function useConsole(sid: string | null) {
  const [events, setEvents] = useState<ConsoleEvent[]>([]);
  const [live, setLive] = useState(false);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    if (!sid) return;
    let source: EventSource | null = null;
    let retry = 0;
    let timer: number | undefined;
    let closed = false;

    const open = () => {
      source = new EventSource(`/api/events?session_id=${encodeURIComponent(sid)}`);
      source.onopen = () => {
        retry = 0;
        setLive(true);
      };
      source.onmessage = (m) => {
        const e = JSON.parse(m.data) as ConsoleEvent;
        if (seen.current.has(e.id)) return;
        seen.current.add(e.id);
        setEvents((list) => [...list, e]);
      };
      source.onerror = () => {
        setLive(false);
        source?.close();
        if (!closed) timer = window.setTimeout(open, Math.min(15000, 1000 * 2 ** retry++));
      };
    };
    open();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      source?.close();
    };
  }, [sid]);

  return { events, live };
}
