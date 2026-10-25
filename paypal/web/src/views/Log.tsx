import { useEffect, useState } from "react";
import { api, type AnchorStatus, type LogEntry } from "../api";

const REPO_VERIFY = "python verify_anchor.py " + window.location.origin;

function AnchorPanel({ a }: { a: AnchorStatus | null }) {
  if (!a) return null;
  if (!a.configured)
    return (
      <div className="verify">
        <span className="badge">GenLayer</span>
        <span>This server does not anchor its log. The hosted demo does.</span>
      </div>
    );
  const m = a.check.matches;
  return (
    <div className="anchor-panel">
      <div className="verify">
        <span className={"badge " + (m === true ? "ok" : m === false ? "no" : "")}>
          {m === true ? "Matches GenLayer" : m === false ? "Does not match" : "Not checked yet"}
        </span>
        <b>
          {m === true
            ? `Entries 1 to ${a.check.seq} are exactly what was anchored`
            : m === false
              ? a.check.reason
              : a.check.reason ?? "Nothing anchored yet"}
        </b>
        {a.pending && <span className="badge warn">newer entries pending</span>}
      </div>
      <dl className="anchor-facts">
        <div>
          <dt>Contract</dt>
          <dd>
            <a href={a.explorer} target="_blank" rel="noreferrer"><code>{a.contract}</code></a> · RemitAnchor on GenLayer Studio
          </dd>
        </div>
        {a.anchor && (
          <>
            <div>
              <dt>Latest anchor</dt>
              <dd>entry {a.anchor.seq} · <code>{a.anchor.hash.slice(0, 16)}…</code></dd>
            </div>
            <div>
              <dt>Transaction</dt>
              <dd><code>{a.anchor.tx}</code></dd>
            </div>
          </>
        )}
        <div>
          <dt>Check it yourself</dt>
          <dd>
            <code>{REPO_VERIFY}</code>
            <span className="muted small"> recomputes the log and reads GenLayer directly; it trusts neither this page nor this server.</span>
          </dd>
        </div>
      </dl>
    </div>
  );
}

const KIND: Record<LogEntry["kind"], [string, string]> = {
  requested: ["Requested", ""],
  facts: ["PayPal records read", "code"],
  engine: ["Code checks", "code"],
  panel: ["AI panel", "ai"],
  refunded: ["Refunded", "ok"],
  refused: ["Refused", "no"],
  failed: ["PayPal failed", "warn"],
};

function summary(e: LogEntry) {
  const b = e.body as Record<string, any>;
  switch (e.kind) {
    case "requested":
      return `USD ${(b.amount_cents / 100).toFixed(2)} on ${b.order_id}, reason "${b.category}"`;
    case "facts":
      return `capture ${b.capture_id}`;
    case "engine":
      return b.state === "held" ? `judgment needed: ${(b.rules as string[]).join(", ")}` : b.state === "refused" ? `refused by ${b.rules[0]}` : "passed";
    case "panel":
      return `${b.verdict}: ${(b.votes as any[]).map((v) => `${v.model} ${v.verdict} ${v.confidence}`).join("; ")}`;
    case "refunded":
      return `PayPal refund ${b.paypal_refund_id} (${b.status})`;
    case "refused":
      return `${b.stage}: ${b.reason}`;
    case "failed":
      return b.reason;
  }
}

export function Log() {
  const [data, setData] = useState<{ verifies: boolean; broken_at: number | null; entries: LogEntry[] } | null>(null);
  const [error, setError] = useState("");
  const [anchor, setAnchor] = useState<AnchorStatus | null>(null);
  const load = () => {
    api.log().then(setData).catch(() => setError("The log could not be loaded."));
    api.anchor().then(setAnchor).catch(() => setAnchor(null));
  };
  useEffect(() => {
    load();
  }, []);

  const rows = data ? [...data.entries].reverse() : [];
  return (
    <div className="wrap page">
      <span className="eyebrow">Every decision, every step</span>
      <h1 className="h2" style={{ marginTop: 12 }}>The decision log</h1>
      <p className="lede">
        Each entry stores the hash of the entry before it. Editing or deleting any past entry breaks every hash after it, and the
        check below fails. The newest hash is also published on GenLayer, so even a rewrite that rebuilds every hash no
        longer matches what is on chain. This makes history impossible to rewrite unnoticed; it does not prove every
        decision was logged, and it does not make the operator trustless.
      </p>
      <div style={{ height: 24 }} />
      {error && <p className="notice">{error}</p>}
      {data && (
        <div className="verify">
          <span className={"badge " + (data.verifies ? "ok" : "no")}>{data.verifies ? "Verified" : "Broken"}</span>
          <b>{data.verifies ? `${data.entries.length} entries, unbroken chain` : `The chain breaks at entry ${data.broken_at}`}</b>
          <button className="btn sm" style={{ marginLeft: "auto" }} onClick={load}>Check again</button>
        </div>
      )}
      <div style={{ height: 14 }} />
      <AnchorPanel a={anchor} />
      <div style={{ height: 20 }} />
      {data && (
        <div className="table-wrap">
          <table className="log">
            <thead>
              <tr>
                <th>#</th>
                <th>Step</th>
                <th>Request</th>
                <th>What happened</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.seq}>
                  <td className="mono">{e.seq}</td>
                  <td><span className={"badge " + KIND[e.kind][1]}>{KIND[e.kind][0]}</span></td>
                  <td className="mono small">{String((e.body as any).request_id ?? "")}</td>
                  <td>{summary(e)}</td>
                  <td className="hash" title={`prev ${e.prev}\nhash ${e.hash}`}>{e.hash.slice(0, 12)}…</td>
                </tr>
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={5} className="muted">No decisions yet. Try the demo.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
