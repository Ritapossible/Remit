import { useState, type ReactNode } from "react";
import { formatGen } from "../lib/money";
import { shortAddr, shortHash } from "../lib/format";
import { NETWORKS, type NetworkId } from "../chain/networks";
import type { TxOutcome } from "../chain/remit";

const LABELS: Record<string, string> = {
  settled: "Settled",
  refused: "Refused",
  held: "Held for jury",
  authorized: "Authorized",
  pending: "Pending",
  in_remit: "In remit",
  out_of_remit: "Out of remit",
  undetermined: "Undetermined",
  verified: "Verified",
  unverified: "Unverified",
  absent: "Absent",
  foreclosed: "Foreclosed",
  reflex: "Reflex",
  judgment: "Judgment",
};

export function Badge({ kind, children, plain }: { kind: string; children?: ReactNode; plain?: boolean }) {
  return <span className={`badge b-${kind}${plain ? " plain" : ""}`}>{children ?? LABELS[kind] ?? kind}</span>;
}

export function Gen({ atto, unit = true }: { atto: string | bigint | number; unit?: boolean }) {
  return (
    <span className="mono">
      {formatGen(atto)}
      {unit ? " GEN" : ""}
    </span>
  );
}

export function Addr({ value, label }: { value?: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="muted">—</span>;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <button type="button" className="btn ghost sm mono" style={{ padding: "0 2px" }} title={`${value} — click to copy`} onClick={copy}>
      {copied ? "copied" : shortAddr(value)}
      {label ? <span className="muted"> · {label}</span> : null}
    </button>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

/**
 * A transaction's fate, in words.
 *
 * Three outcomes, never two. "The contract refused" and "no consensus" both
 * leave state untouched, but they mean different things to the person who
 * clicked: one is an answer, the other is an invitation to try again.
 */
export function TxLine({
  network,
  pending,
  hash,
  outcome,
  refusalHint,
  successText,
}: {
  network: NetworkId;
  pending: boolean;
  hash?: string;
  outcome?: TxOutcome | null;
  refusalHint?: string;
  successText?: string;
}) {
  if (!pending && !hash && !outcome) return null;
  const link = hash ? `${NETWORKS[network].explorer}/tx/${hash}` : undefined;
  return (
    <div style={{ marginTop: 12 }}>
      {hash && (
        <div className="tx">
          {pending && <Spinner />}
          <span>{pending ? "Waiting for consensus…" : "Transaction"}</span>
          <a className="mono" href={link} target="_blank" rel="noreferrer">
            {shortHash(hash)}
          </a>
        </div>
      )}
      {!hash && pending && (
        <div className="tx">
          <Spinner /> <span>Waiting for your wallet…</span>
        </div>
      )}
      {outcome && outcome.applied && (
        <div className="notice good">
          <strong>Done.</strong> {successText ?? "Validators agreed and the change is recorded."}{" "}
          <span className="mono small">{outcome.consensus}</span>
        </div>
      )}
      {outcome && outcome.refused && (
        <div className="notice bad">
          <strong>The contract refused this.</strong> Validators agreed on the refusal, so nothing changed.
          {refusalHint ? ` ${refusalHint}` : ""}
        </div>
      )}
      {outcome && !outcome.agreed && (
        <div className="notice warn">
          <strong>No consensus</strong> (<span className="mono">{outcome.consensus}</span>). The validators did not
          agree, so the change was rolled back and nothing is recorded. It is safe to try again — a different
          validator set may be drawn.
        </div>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function explainError(e: unknown): string {
  const msg = String((e as { shortMessage?: string; message?: string })?.shortMessage ?? (e as Error)?.message ?? e);
  if (/user (rejected|denied)/i.test(msg)) return "You declined the request in your wallet.";
  if (/insufficient funds/i.test(msg)) return "This account has no GEN to pay for the transaction.";
  if (/not valid JSON|DOCTYPE/i.test(msg)) return "The network gateway returned an error page. This is usually momentary — try again.";
  return msg.length > 220 ? `${msg.slice(0, 220)}…` : msg;
}
