import { useEffect, useState } from "react";
import { api, type Decision, type LogEntry, type RefundResult } from "../api";

const RULE_NAMES: Record<string, string> = {
  refundable: "Within what was paid",
  currency: "Currency",
  "no-open-dispute": "No open dispute",
  "per-refund-cap": "Per-refund cap",
  "daily-cap": "Daily cap",
  "not-blocked": "Customer not blocked",
  "refund-policy": "Refund policy",
  "split-refunds": "Split refunds",
};

const VERDICT: Record<string, string> = {
  in_remit: "allows it",
  out_of_remit: "refuses it",
  undetermined: "unsure",
};

function entry(log: LogEntry[], kind: LogEntry["kind"]) {
  return log.find((e) => e.kind === kind)?.body as Record<string, any> | undefined;
}

/** One refund request, as Remit decided it: a stage per row, each with who
 *  decided it. The summary comes from the tool result; the detail from the
 *  decision's own log entries. */
export function DecisionCard({ result, amount }: { result: RefundResult; amount?: string }) {
  const [d, setD] = useState<Decision | null>(null);
  useEffect(() => {
    let live = true;
    api.decision(result.request_id).then((x) => live && setD(x)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [result.request_id]);

  const log = d?.log ?? [];
  const facts = entry(log, "facts");
  const engine = entry(log, "engine");
  const panel = entry(log, "panel");
  const refused = entry(log, "refused");
  const refunded = entry(log, "refunded");
  const failed = entry(log, "failed");
  const stoppedAt = refused?.stage as string | undefined;
  const ok = result.outcome === "refunded";

  return (
    <article className={"decision " + result.outcome} aria-label={`Refund ${result.outcome}`}>
      <header>
        <span className={"badge " + (ok ? "ok" : "no")}>{ok ? "Refunded" : "Refused"}</span>
        {amount && <span className="amount">USD {amount}</span>}
        <span className="muted small">
          decided by <b>{result.decided_by}</b>
        </span>
        <code className="mono small muted" style={{ marginLeft: "auto" }}>{result.request_id}</code>
      </header>
      <div className="why">{ok ? `PayPal refund ${result.paypal_refund_id}` : capital(result.reason)}</div>
      <ol className="steps">
        <li>
          <span className="stage">
            PayPal records<small className="badge code">read by Remit</small>
          </span>
          {facts ? (
            <ul className="facts">
              {(facts.lines as string[]).map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          ) : (
            <span className="muted">{stoppedAt === "facts" ? "Could not be read: nothing was refunded." : "Loading…"}</span>
          )}
        </li>
        <li className={!engine && stoppedAt !== "checks" ? "skip" : ""}>
          <span className="stage">
            Code checks<small className="badge code">no model</small>
          </span>
          <span>
            {stoppedAt === "checks" || stoppedAt === "engine" ? (
              <>
                <span className="badge no">Stopped</span> {RULE_NAMES[(refused?.rules as string[])?.[0]] ?? "Rule"}:{" "}
                {String(refused?.reason ?? "")}. No model was asked.
              </>
            ) : engine ? (
              <>
                <span className="badge ok">Passed</span> limits, refundable amount, disputes.
                {engine.state === "held" && (
                  <> Judgment needed: {(engine.rules as string[]).map((r) => RULE_NAMES[r] ?? r).join(", ")}.</>
                )}
              </>
            ) : (
              "Not reached."
            )}
          </span>
        </li>
        <li className={panel ? "" : "skip"}>
          <span className="stage">
            AI panel<small className="badge ai">fails closed</small>
          </span>
          {panel ? (
            <div className="votes">
              {(panel.votes as any[]).map((v) => (
                <div className="vote" key={v.model}>
                  <span className="model" title={v.model}>{v.model}</span>
                  <span className="small">
                    {VERDICT[v.verdict] ?? v.verdict} · {v.confidence}
                    {v.error ? " · error" : ""}
                  </span>
                  <span className="bar">
                    <i className={v.verdict} style={{ width: `${Math.max(4, v.confidence)}%` }} />
                  </span>
                </div>
              ))}
              <span className="small">
                Panel: <b>{VERDICT[panel.verdict as string] ?? panel.verdict}</b>
              </span>
              <details className="prompt">
                <summary>The exact question the models were asked</summary>
                <pre>{String(panel.prompt ?? "")}</pre>
              </details>
            </div>
          ) : (
            <span className="muted">{stoppedAt === "checks" || stoppedAt === "engine" ? "Not needed: code already refused." : engine ? "Not needed." : "Not reached."}</span>
          )}
        </li>
        <li className={refunded || failed ? "" : "skip"}>
          <span className="stage">
            PayPal refund<small className="badge code">only if allowed</small>
          </span>
          <span>
            {refunded ? (
              <>
                <span className="badge ok">{String(refunded.status ?? "COMPLETED")}</span> <code>{String(refunded.paypal_refund_id)}</code>
              </>
            ) : failed ? (
              <>
                <span className="badge warn">Not completed</span> {String(failed.reason)}. Nothing was refunded.
              </>
            ) : (
              <span className="muted">Never sent to PayPal.</span>
            )}
          </span>
        </li>
      </ol>
    </article>
  );
}

function capital(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) + "." : "";
}
