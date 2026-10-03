import { useCallback, useEffect, useState } from "react";
import { useApp } from "../state";
import { NETWORKS } from "../chain/networks";
import {
  CONTRACT_CODE,
  readBondQuote,
  readChallenges,
  readRegistry,
  verifyGuardCode,
  write,
  type Challenge,
  type Registration,
  type SpendView,
} from "../chain/remit";
import { parseGen } from "../lib/money";
import { duration, sameAddr } from "../lib/format";
import { useNow } from "../hooks";
import { Addr, Badge, Gen, Spinner, TxLine } from "./ui";
import { isAddr, useRailStatus, useTx } from "./Rail";

// The court lives in the rail. A payment that cleared without a jury can be
// challenged for the mandate's clawback window, with a bond on the engine's
// rising curve; the agent may answer with pinned evidence; anyone convenes the
// jury. Upheld: the payment is blocked (unpaid) or clawed back from the agent's
// bond (paid), and a tier-2/3 rule freezes the agent. Dismissed: the bond goes
// to the agent.

const TIER_TEXT: Record<number, string> = {
  2: "frozen: no new spend is authorized until the principal lifts it",
  3: "frozen, and every payment requested before the breach that the rail had not paid is revoked",
};

/** Court figures and controls inside the Treasury card. */
export function CourtSummary() {
  const { client, rail, mandate, wallet, network, pollMs, canSign } = useApp();
  const { status, reload } = useRailStatus();
  const tx = useTx();
  const [amount, setAmount] = useState("0.1");
  if (!status || status.standing === undefined || !mandate) return null;
  const me = wallet.kind === "none" ? "" : wallet.address;
  const isPrincipal = sameAddr(me, mandate.principal);
  let value = 0n;
  try {
    value = parseGen(amount);
  } catch {
    value = 0n;
  }
  const frozen = Number(status.frozen_tier ?? 0);
  return (
    <div style={{ marginTop: 18 }}>
      <h4 style={{ margin: "0 0 6px" }}>Court</h4>
      <p className="small muted" style={{ marginTop: 0 }}>
        Payments that cleared without a jury can be challenged for {duration(mandate.defaults.clawback_window_seconds)}.
        The agent's bond is what makes a payment that already left recoverable.
      </p>
      <dl className="kv">
        <dt>Treasury</dt>
        <dd>
          <Gen atto={status.treasury ?? "0"} />
        </dd>
        <dt>Agent's bond</dt>
        <dd>
          <Gen atto={status.standing} />
        </dd>
        <dt>Challenges</dt>
        <dd>
          {status.challenge_count ?? 0} raised, {status.open_challenges ?? 0} open, <Gen atto={status.escrowed ?? "0"} /> in bonds
        </dd>
        <dt>Bond floor</dt>
        <dd>
          <Gen atto={status.bond_floor ?? "0"} />
        </dd>
        <dt>Court freeze</dt>
        <dd>{frozen >= 2 ? <Badge kind="refused">Tier {frozen}</Badge> : <span className="muted">none</span>}</dd>
      </dl>
      <div className="row" style={{ marginTop: 12 }}>
        <input value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="GEN to bond" style={{ width: 110 }} />
        <button
          className="btn"
          disabled={!canSign || tx.pending || value <= 0n}
          onClick={() => tx.run((onHash) => write(client, rail, "post_bond", [], pollMs, onHash, value), reload)}
        >
          {tx.pending ? <Spinner /> : null} Add to the agent's bond
        </button>
        {frozen >= 2 && isPrincipal && (
          <button
            className="btn"
            disabled={!canSign || tx.pending}
            onClick={() => tx.run((onHash) => write(client, rail, "lift_freeze", [], pollMs, onHash), reload)}
          >
            Lift the court's freeze
          </button>
        )}
      </div>
      <TxLine network={network} pending={tx.pending} hash={tx.hash} outcome={tx.outcome} refusalHint="The rail refused." />
      {tx.err && <div className="notice bad">{tx.err}</div>}
    </div>
  );
}

/** A freeze in force, from the guard's own jury or from the rail's court. */
export function FreezeBanner() {
  const { client, guard, rail, mandate, wallet, network, pollMs, canSign, reloadMandate } = useApp();
  const { status, reload } = useRailStatus();
  const tx = useTx();
  if (!mandate) return null;
  const own = Number(mandate.frozen_tier ?? 0);
  const court = Number(status?.frozen_tier ?? 0);
  const tier = Math.max(own, court);
  if (tier < 2) return null;
  const isPrincipal = sameAddr(wallet.kind === "none" ? "" : wallet.address, mandate.principal);
  return (
    <div className="notice bad" role="status" style={{ marginBottom: 18 }}>
      <strong>The agent is frozen at tier {tier}.</strong> {TIER_TEXT[tier >= 3 ? 3 : 2]}.{" "}
      {own >= 2 && <>The guard's jury found a breach on spend #{mandate.frozen_by}. </>}
      {court >= 2 && <>The rail's court upheld challenge #{status?.frozen_by}. </>}
      {isPrincipal && (
        <span className="row" style={{ marginTop: 8 }}>
          {own >= 2 && (
            <button
              className="btn sm"
              disabled={!canSign || tx.pending}
              onClick={() => tx.run((onHash) => write(client, guard, "lift_freeze", [], pollMs, onHash), reloadMandate)}
            >
              Lift the guard's freeze
            </button>
          )}
          {court >= 2 && status && (
            <button
              className="btn sm"
              disabled={!canSign || tx.pending}
              onClick={() => tx.run((onHash) => write(client, rail, "lift_freeze", [], pollMs, onHash), reload)}
            >
              Lift the court's freeze
            </button>
          )}
        </span>
      )}
      <TxLine network={network} pending={tx.pending} hash={tx.hash} outcome={tx.outcome} />
    </div>
  );
}

/** The court for one payment: its challenges, and the actions open to the viewer. */
export function CaseCourt({ spend }: { spend: SpendView }) {
  const { client, rail, mandate, wallet, network, pollMs, canSign } = useApp();
  const { status } = useRailStatus();
  const [challenges, setChallenges] = useState<Challenge[]>([]);
  const now = useNow(5000);
  const load = useCallback(async () => {
    if (!isAddr(rail)) return;
    setChallenges((await readChallenges(client, rail)).filter((c) => c.spend === spend.id));
  }, [client, rail, spend.id]);
  useEffect(() => {
    void load();
  }, [load]);
  if (!mandate || !status || status.standing === undefined) return null;

  const me = wallet.kind === "none" ? "" : wallet.address;
  const isAgent = sameAddr(me, mandate.agent);
  const open = challenges.find((c) => c.state === "open");
  const upheld = challenges.find((c) => c.state === "upheld");
  const window = mandate.defaults.clawback_window_seconds;
  const challengeable =
    spend.authorization === "authorized" &&
    spend.verdict === "" &&
    spend.reason === "" &&
    (spend.decided_at ?? 0) > 0 &&
    now - (spend.decided_at ?? 0) <= window &&
    !open &&
    !upheld;

  return (
    <div className="card">
      <h3>Court</h3>
      <p className="sub">
        This payment cleared {spend.verdict ? "through the jury" : "by arithmetic"}.{" "}
        {spend.verdict || spend.reason
          ? "A jury's or the principal's decision is reviewed by GenLayer's appeal, not by a challenge."
          : `Anyone but the agent may challenge it under a judgment rule until ${duration(Math.max(0, (spend.decided_at ?? 0) + window - now))} from now, with a bond.`}
      </p>
      {challenges.map((c) => (
        <ChallengeRow key={c.id} c={c} spend={spend} isAgent={isAgent} reload={load} />
      ))}
      {challengeable && !isAgent && <ChallengeForm spend={spend} reload={load} />}
      {!canSign && challengeable && <p className="small muted">Connect a wallet to challenge.</p>}
      <span className="small muted">
        Court of rail <Addr value={rail} /> on {NETWORKS[network].short} · polls every {pollMs / 1000}s
      </span>
    </div>
  );
}

function ChallengeRow({ c, spend, isAgent, reload }: { c: Challenge; spend: SpendView; isAgent: boolean; reload: () => Promise<void> }) {
  const { client, rail, mandate, network, pollMs, canSign } = useApp();
  const tx = useTx();
  const now = useNow(5000);
  const [uri, setUri] = useState("");
  const [digest, setDigest] = useState("");
  if (!mandate) return null;
  const windowEnds = c.opened_at + mandate.defaults.response_window_seconds;
  const deadline = c.opened_at + mandate.defaults.hold_deadline_seconds;
  const s = c.settlement;
  return (
    <div className="notice" style={{ marginBottom: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>
          Challenge #{c.id} · <span className="mono">{c.rule}</span>
        </strong>
        <Badge kind={c.state} />
      </div>
      <div className="small" style={{ margin: "6px 0" }}>
        By <Addr value={c.challenger} />, bond <Gen atto={c.bond} />. <span className="muted">Untrusted statement:</span> “{c.statement}”
      </div>
      {c.state !== "open" && c.verdict && (
        <div className="small">
          Jury: <b>{c.verdict.replace(/_/g, " ")}</b> ({c.reason}, {c.confidence}%), evidence {c.artifact}.{" "}
          {s && c.state === "upheld" && (
            <>
              {s.blocked ? "The rail had not paid it: blocked." : <>Clawed back <Gen atto={s.to_treasury} /> to the treasury from the agent's bond.</>}{" "}
              Challenger received <Gen atto={s.to_challenger} />.{c.tier && c.tier >= 2 ? ` Tier ${c.tier}: the agent was ${TIER_TEXT[c.tier >= 3 ? 3 : 2]}.` : ""}
            </>
          )}
          {s && c.state === "dismissed" && (
            <>
              The bond, <Gen atto={s.to_agent} />, went to the agent.
            </>
          )}
        </div>
      )}
      {c.state === "lapsed" && <div className="small">No decision by the deadline: the bond went back and nobody lost.</div>}
      {c.state === "open" && (
        <>
          <p className="small" style={{ margin: "6px 0" }}>
            The rail will not pay #{spend.id} while this is open.{" "}
            {c.memo_uri ? (
              <>
                The agent answered with <span className="mono">{c.memo_uri}</span>.
              </>
            ) : now < windowEnds ? (
              <>The agent may answer for {duration(windowEnds - now)} more.</>
            ) : (
              <>The response window has passed.</>
            )}
          </p>
          {isAgent && !c.memo_uri && (
            <div className="row">
              <input placeholder="https://… evidence" value={uri} onChange={(e) => setUri(e.target.value)} style={{ flex: "1 1 220px" }} />
              <input className="mono" placeholder="sha256 hex" value={digest} onChange={(e) => setDigest(e.target.value)} style={{ flex: "1 1 220px" }} />
              <button
                className="btn sm"
                disabled={!canSign || tx.pending || !uri || !/^[0-9a-fA-F]{64}$/.test(digest)}
                onClick={() => tx.run((onHash) => write(client, rail, "respond", [c.id, uri, digest], pollMs, onHash), reload)}
              >
                Answer
              </button>
            </div>
          )}
          <div className="row" style={{ marginTop: 8 }}>
            <button
              className="btn sm primary"
              disabled={!canSign || tx.pending || (!c.memo_uri && now < windowEnds)}
              onClick={() => tx.run((onHash) => write(client, rail, "rule", [c.id], pollMs, onHash), reload)}
            >
              {tx.pending ? <Spinner /> : null} Convene the jury
            </button>
            {now >= deadline && (
              <button
                className="btn sm"
                disabled={!canSign || tx.pending}
                onClick={() => tx.run((onHash) => write(client, rail, "lapse", [c.id], pollMs, onHash), reload)}
              >
                Lapse it (deadline passed)
              </button>
            )}
          </div>
        </>
      )}
      <TxLine network={network} pending={tx.pending} hash={tx.hash} outcome={tx.outcome} refusalHint="The court refused." />
      {tx.err && <div className="notice bad">{tx.err}</div>}
    </div>
  );
}

function ChallengeForm({ spend, reload }: { spend: SpendView; reload: () => Promise<void> }) {
  const { client, rail, mandate, wallet, network, pollMs, canSign } = useApp();
  const rules = (mandate?.rules ?? []).filter((r) => r.type === "judgment");
  const [rule, setRule] = useState(rules[0]?.id ?? "");
  const [statement, setStatement] = useState("");
  const [quote, setQuote] = useState<{ error: string; bond: string } | null>(null);
  const tx = useTx();
  const me = wallet.kind === "none" ? "" : wallet.address;
  useEffect(() => {
    if (!rule || !me) return;
    readBondQuote(client, rail, spend.id, rule, me)
      .then(setQuote)
      .catch(() => setQuote(null));
  }, [client, rail, spend.id, rule, me]);
  if (!rules.length) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <h4 style={{ margin: "0 0 6px" }}>Challenge this payment</h4>
      <div className="row">
        <select value={rule} onChange={(e) => setRule(e.target.value)} aria-label="Rule">
          {rules.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} (tier {r.tier ?? 0})
            </option>
          ))}
        </select>
      </div>
      <textarea
        rows={3}
        placeholder="Why this payment breaches the rule. The jury reads it as an untrusted allegation."
        value={statement}
        onChange={(e) => setStatement(e.target.value)}
        style={{ width: "100%", marginTop: 8 }}
      />
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="btn primary"
          disabled={!canSign || tx.pending || !quote || !!quote.error || !statement.trim()}
          onClick={() =>
            tx.run((onHash) => write(client, rail, "challenge", [spend.id, rule, statement.trim()], pollMs, onHash, BigInt(quote!.bond)), reload)
          }
        >
          {tx.pending ? <Spinner /> : null} Challenge with a bond of {quote && !quote.error ? <Gen atto={quote.bond} /> : "…"}
        </button>
        <span className="hint">
          {quote?.error
            ? quote.error
            : "Returned with a reward if upheld; paid to the agent if dismissed. Each loss doubles your next bond."}
        </span>
      </div>
      <TxLine network={network} pending={tx.pending} hash={tx.hash} outcome={tx.outcome} refusalHint="The court refused the challenge." />
      {tx.err && <div className="notice bad">{tx.err}</div>}
    </div>
  );
}

/** Guards registered on this network, each checked against the published build. */
export function RegistryList() {
  const { client, network, setGuard, setRail } = useApp();
  const registry = NETWORKS[network].registry;
  const [rows, setRows] = useState<Registration[] | null>(null);
  const [verified, setVerified] = useState<Record<string, boolean | undefined>>({});
  const [err, setErr] = useState("");
  useEffect(() => {
    setRows(null);
    setVerified({});
    if (!registry) return;
    readRegistry(client, registry)
      .then((r) => {
        setRows(r.slice().reverse());
        r.slice(-12).forEach((g) =>
          verifyGuardCode(client, g.guard)
            .then((ok) => setVerified((v) => ({ ...v, [g.guard]: ok })))
            .catch(() => setVerified((v) => ({ ...v, [g.guard]: false }))),
        );
      })
      .catch((e) => setErr(String(e?.message ?? e)));
  }, [client, registry]);
  if (!registry) return null;
  return (
    <div className="card">
      <h3>Registered guards</h3>
      <p className="sub">
        The registry at <Addr value={registry} /> binds each agent to one principal's guard. A guard shows as{" "}
        <b>verified</b> when the code deployed at its address is byte-for-byte the published build ({CONTRACT_CODE.length.toLocaleString()} bytes).
      </p>
      {err && <div className="notice bad">{err}</div>}
      {rows === null && !err && <Spinner />}
      {rows?.length === 0 && <p className="small muted">Nothing registered yet.</p>}
      {rows && rows.length > 0 && (
        <div className="table-wrap stack-wrap">
          <table className="table stack">
            <thead>
              <tr>
                <th>Guard</th>
                <th>Agent</th>
                <th>Principal</th>
                <th>Rail</th>
                <th>Code</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((g) => (
                <tr key={g.guard + g.registered_at}>
                  <td data-label="Guard">
                    <Addr value={g.guard} />
                  </td>
                  <td data-label="Agent">
                    <Addr value={g.agent} />
                  </td>
                  <td data-label="Principal">
                    <Addr value={g.principal} />
                  </td>
                  <td data-label="Rail">{g.rail ? <Addr value={g.rail} /> : <span className="muted">none</span>}</td>
                  <td data-label="Code">
                    {!g.active ? (
                      <Badge kind="pending">Replaced</Badge>
                    ) : verified[g.guard] === undefined ? (
                      <span className="muted small">checking…</span>
                    ) : verified[g.guard] ? (
                      <Badge kind="authorized">Verified</Badge>
                    ) : (
                      <Badge kind="refused">Different code</Badge>
                    )}
                  </td>
                  <td data-label="">
                    <button
                      className="btn sm"
                      onClick={() => {
                        setGuard(g.guard);
                        if (g.rail) setRail(g.rail);
                        window.location.hash = "#/app";
                      }}
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
