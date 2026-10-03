import { CasePayment } from "../components/Rail";
import { useCallback, useEffect, useState } from "react";
import { useApp, href } from "../state";
import { useNow } from "../hooks";
import { readSpend, write, type SpendView, type TxOutcome } from "../chain/remit";
import { digestOfUrl, isSha256Hex } from "../lib/digest";
import { duration, sameAddr } from "../lib/format";
import { pathOf, PATH_TEXT } from "../lib/path";
import { formatGen } from "../lib/money";
import { Addr, Badge, Empty, Spinner, TxLine, explainError } from "../components/ui";
import { describePredicate } from "../lib/mandate";

export function CaseView({ id }: { id: number }) {
  const { client, guard, mandate } = useApp();
  const [spend, setSpend] = useState<SpendView | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!mandate) return;
    try {
      setSpend(await readSpend(client, guard, id));
      setError("");
    } catch {
      setError(`There is no spend #${id} on this guard.`);
    }
  }, [client, guard, id, mandate]);

  useEffect(() => {
    setSpend(null);
    void reload();
  }, [reload]);

  if (!mandate) return <Empty>Load a guard first.</Empty>;
  if (error) return <div className="notice bad">{error}</div>;
  if (!spend) return <Empty>Reading case #{id}…</Empty>;

  const { path } = pathOf(spend, mandate);
  const rule = mandate.rules.find((r) => r.id === spend.rules[0]);

  return (
    <>
      <p className="small">
        <a href={href({ name: "docket" })}>← Docket</a>
      </p>
      <div className="case-head">
        <div>
          <div className="small muted">Case #{spend.id} · {spend.category || "uncategorised"}</div>
          <div className="amt">
            {formatGen(spend.amount)} <span className="muted" style={{ fontSize: "0.5em" }}>GEN</span>
          </div>
          <div className="small">
            to <Addr value={spend.recipient} />
          </div>
        </div>
        <div className="row">
          {/* One badge: authorization is what a rail acts on. The state is in the timeline. */}
          <Badge kind={spend.authorization} />
          {spend.shadow && <Badge kind="neutral">shadow</Badge>}
        </div>
      </div>

      <div className="case-grid">
        <div>
          <div className="card">
            <h3>What happened</h3>
            <p className="sub">{PATH_TEXT[path]}</p>
            <Timeline spend={spend} />
          </div>

          {spend.verdict && <VerdictCard spend={spend} />}

          {rule && (
            <div className="card">
              <h3>
                The rule{" "}
                <Badge kind={rule.type} plain>
                  {rule.type}
                </Badge>
              </h3>
              <p className="sub mono">{rule.id}</p>
              {rule.type === "judgment" ? (
                <>
                  <div className="small muted">Triggered because {describePredicate(rule, true)}. The jury was asked:</div>
                  <div className="serif" style={{ fontSize: 20, lineHeight: 1.35, marginTop: 6 }}>
                    “{rule.ask}”
                  </div>
                </>
              ) : (
                <div>{describePredicate(rule)}</div>
              )}
            </div>
          )}

          <div className="card">
            <div className="untrusted">
              <div className="tag">The agent's claim · untrusted</div>
              <div style={{ marginTop: 6 }}>{spend.claim || <span className="muted">(none)</span>}</div>
            </div>
            <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
              Shown here exactly as the jury saw it: as what the agent asserts, never as fact. The amounts, recipient
              and history above were read by the contract from its own ledger.
            </p>
          </div>
        </div>

        <div>
          <Actions spend={spend} onChange={reload} />
          <ArtifactCard spend={spend} />
        </div>
      </div>
    </>
  );
}

function Timeline({ spend }: { spend: SpendView }) {
  const { mandate } = useApp();
  const now = useNow();
  const win = mandate?.defaults.response_window_seconds ?? 0;
  const dl = mandate?.defaults.hold_deadline_seconds ?? 0;
  const held = spend.held_at > 0;
  const items: { cls: string; t: string; d?: string }[] = [
    { cls: "done", t: "Requested by the agent", d: new Date(spend.at * 1000).toLocaleString() },
  ];
  if (spend.state === "settled" && !held && !spend.verdict) {
    items.push({ cls: "good", t: "Authorized in the same transaction", d: "No rule fired. No jury convened." });
  } else if (spend.state === "refused" && !held && !spend.verdict && spend.reason !== "principal_override") {
    items.push({ cls: "bad", t: "Refused in the same transaction", d: `Arithmetic rule “${spend.rules[0]}”. No jury convened.` });
  } else {
    items.push({ cls: "done", t: "Held for the jury", d: `Trigger “${spend.rules.join(", ")}” fired. Authorization withheld.` });
    items.push(
      spend.memo_uri
        ? { cls: "done", t: "Evidence committed", d: "The agent pinned a document by its sha256 digest." }
        : spend.state === "held"
          ? {
              cls: "now",
              t: "Response window",
              d:
                now < spend.held_at + win
                  ? `About ${duration(spend.held_at + win - now)} left for the agent to commit evidence.`
                  : "Elapsed. The case can now be decided without evidence.",
            }
          : { cls: "done", t: "No evidence committed" },
    );
    if (spend.state === "held") {
      items.push({
        cls: "now",
        t: "Awaiting a decision",
        d: `Anyone may convene the jury. At the deadline (about ${duration(Math.max(0, spend.held_at + dl - now))} from now) it resolves to the registered default.`,
      });
    } else {
      const how =
        spend.reason === "principal_override"
          ? "The principal overrode the hold."
          : spend.reason === "deadline_default"
            ? "The deadline passed with no verdict; the registered default applied."
            : `The jury answered “${spend.verdict.replace(/_/g, " ")}”.`;
      items.push({ cls: spend.outcome === "allowed" ? "good" : "bad", t: spend.outcome === "allowed" ? "Authorized" : "Refused", d: how });
    }
  }
  return (
    <ol className="timeline">
      {items.map((i, n) => (
        <li key={n} className={i.cls}>
          <div className="t">{i.t}</div>
          {i.d && <div className="d">{i.d}</div>}
        </li>
      ))}
    </ol>
  );
}

function VerdictCard({ spend }: { spend: SpendView }) {
  const tone = spend.verdict === "in_remit" ? "settled" : spend.verdict === "out_of_remit" ? "refused" : "neutral";
  return (
    <div className="card">
      <div className="verdict" style={{ background: `var(--${tone === "neutral" ? "surface-2" : tone + "-bg"})`, borderColor: "transparent" }}>
        <div className="small muted">The jury's answer</div>
        <div className="big" style={{ color: tone === "neutral" ? "var(--ink)" : `var(--${tone})` }}>
          {spend.verdict === "in_remit" ? "Within the remit" : spend.verdict === "out_of_remit" ? "Outside the remit" : "Undetermined"}
        </div>
        <dl className="kv small">
          <dt>Reason</dt>
          <dd className="mono">{spend.reason || "-"}</dd>
          <dt>Evidence</dt>
          <dd>
            <Badge kind={spend.artifact || "absent"} />
          </dd>
          <dt>Leader confidence</dt>
          <dd>
            {spend.confidence}%
            <div className="meter">
              <i style={{ width: `${Math.min(100, spend.confidence)}%` }} />
            </div>
          </dd>
        </dl>
      </div>
      <p className="small muted" style={{ marginBottom: 0 }}>
        {spend.artifact === "verified" || spend.artifact === "unverified"
          ? "Every validator fetched the evidence and checked its digest itself, then answered the same question independently."
          : "No evidence was committed, so validators answered from the rule and the payment history the contract recorded - each independently."}{" "}
        Confidence is the leader's and never entered the comparison.
      </p>
    </div>
  );
}

function ArtifactCard({ spend }: { spend: SpendView }) {
  const [check, setCheck] = useState<{ busy: boolean; result?: string; ok?: boolean }>({ busy: false });
  if (!spend.memo_uri) return null;
  const verify = async () => {
    setCheck({ busy: true });
    try {
      const { digest, bytes } = await digestOfUrl(spend.memo_uri);
      const ok = digest === spend.memo_digest.toLowerCase();
      setCheck({ busy: false, ok, result: ok ? `Matches - ${bytes} bytes hash to the pinned digest.` : `Does not match. Served bytes hash to ${digest.slice(0, 16)}….` });
    } catch (e) {
      setCheck({ busy: false, ok: false, result: explainError(e) });
    }
  };
  return (
    <div className="card">
      <h3>Evidence</h3>
      <p className="sub">Pinned by digest. Validators retrieve it and hash-check it themselves.</p>
      <dl className="kv small">
        <dt>Document</dt>
        <dd>
          <a href={spend.memo_uri} target="_blank" rel="noreferrer" style={{ overflowWrap: "anywhere" }}>
            {spend.memo_uri.length > 70 ? spend.memo_uri.slice(0, 70) + "…" : spend.memo_uri}
          </a>
        </dd>
        <dt>sha256</dt>
        <dd className="mono">{spend.memo_digest}</dd>
      </dl>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn sm" onClick={verify} disabled={check.busy}>
          {check.busy ? <Spinner /> : null} Verify it yourself
        </button>
      </div>
      {check.result && <div className={`notice ${check.ok ? "good" : "bad"}`}>{check.result}</div>}
    </div>
  );
}

function Actions({ spend, onChange }: { spend: SpendView; onChange: () => Promise<void> }) {
  const { client, guard, mandate, wallet, network, pollMs, canSign } = useApp();
  const now = useNow();
  const [pending, setPending] = useState(false);
  const [hash, setHash] = useState<string>();
  const [outcome, setOutcome] = useState<TxOutcome | null>(null);
  const [err, setErr] = useState("");
  const [hint, setHint] = useState<string>();
  const [uri, setUri] = useState("");
  const [digest, setDigest] = useState("");
  const [hashing, setHashing] = useState(false);

  if (!mandate) return null;
  const me = wallet.kind === "none" ? "" : wallet.address;
  const isAgent = sameAddr(me, mandate.agent);
  const isPrincipal = sameAddr(me, mandate.principal);
  const held = spend.state === "held";
  const winEnds = spend.held_at + mandate.defaults.response_window_seconds;
  const deadline = spend.held_at + mandate.defaults.hold_deadline_seconds;
  const windowOpen = held && !spend.memo_uri && now < winEnds;
  const pastDeadline = held && now >= deadline;

  const run = async (fn: string, args: unknown[], refusal: string) => {
    setPending(true);
    setHash(undefined);
    setOutcome(null);
    setErr("");
    setHint(refusal);
    try {
      const o = await write(client, guard, fn, args, pollMs, setHash);
      setOutcome(o);
      await onChange();
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setPending(false);
    }
  };

  const compute = async () => {
    setHashing(true);
    setErr("");
    try {
      setDigest((await digestOfUrl(uri.trim())).digest);
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setHashing(false);
    }
  };

  if (!held) {
    return (
      <div className="card">
        <h3>Decided</h3>
        <p className="sub" style={{ marginBottom: 0 }}>
          This case is closed. The guard's answer for this spend is <b>{spend.authorization}</b>.
        </p>
        <CasePayment spend={spend} />
        <TxLine network={network} pending={pending} hash={hash} outcome={outcome} refusalHint={hint} />
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Act on this case</h3>
      <p className="sub">Authorization is withheld until one of these happens.</p>

      {wallet.kind === "none" && <div className="notice">Connect a wallet to act. Anyone may convene the jury.</div>}

      {isAgent && (
        <div style={{ marginBottom: 18 }}>
          <div className="small" style={{ fontWeight: 500, marginBottom: 6 }}>
            Commit evidence <span className="muted">· agent</span>
          </div>
          <input
            placeholder="https://… invoice, order or receipt"
            value={uri}
            onChange={(e) => {
              setUri(e.target.value);
              setDigest("");
            }}
            style={{ width: "100%" }}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn sm" disabled={!uri || hashing} onClick={compute}>
              {hashing ? <Spinner /> : null} Compute digest
            </button>
            <button
              className="btn sm primary"
              disabled={pending || !canSign || !isSha256Hex(digest)}
              onClick={() => run("commit_artifact", [spend.id, uri.trim(), digest], "Evidence can only be committed while the spend is held.")}
            >
              Commit
            </button>
          </div>
          {digest && <div className="small mono muted" style={{ marginTop: 6, overflowWrap: "anywhere" }}>{digest}</div>}
          <div className="hint" style={{ marginTop: 6 }}>
            The digest is computed from the bytes this browser receives. Validators fetch the same URL; if the bytes
            differ, the evidence lands as unverified.
          </div>
        </div>
      )}

      <div style={{ marginBottom: 18 }}>
        <div className="small" style={{ fontWeight: 500, marginBottom: 6 }}>
          Convene the jury <span className="muted">· anyone</span>
        </div>
        <button
          className="btn primary"
          disabled={pending || !canSign || windowOpen}
          onClick={() => run("adjudicate", [spend.id], "")}
        >
          {pending ? <Spinner /> : null} Adjudicate
        </button>
        {windowOpen && (
          <div className="notice warn">
            The agent has about <b>{duration(winEnds - now)}</b> left to commit evidence. The contract refuses to
            decide before then, so a party can never lose for not using a window it never had.
          </div>
        )}
      </div>

      {(isPrincipal || pastDeadline) && (
        <div className="row" style={{ marginBottom: 6 }}>
          {isPrincipal && (
            <>
              <button className="btn" disabled={pending || !canSign} onClick={() => run("override_release", [spend.id], "")}>
                Release
              </button>
              <button className="btn danger" disabled={pending || !canSign} onClick={() => run("override_refuse", [spend.id], "")}>
                Refuse
              </button>
              <span className="small muted">principal override · your key always outranks Remit</span>
            </>
          )}
          {pastDeadline && (
            <button className="btn" disabled={pending || !canSign} onClick={() => run("resolve_deadline", [spend.id], "")}>
              Resolve at deadline
            </button>
          )}
        </div>
      )}

      <TxLine network={network} pending={pending} hash={hash} outcome={outcome} refusalHint={hint} />
      {err && <div className="notice bad">{err}</div>}
    </div>
  );
}
