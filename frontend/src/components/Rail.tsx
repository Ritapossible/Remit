import { useCallback, useEffect, useState } from "react";
import { useApp } from "../state";
import { NETWORKS } from "../chain/networks";
import { deployRail, readPayment, readRail, write, type RailPayment, type RailStatus, type SpendView, type TxOutcome } from "../chain/remit";
import { parseGen } from "../lib/money";
import { duration, sameAddr } from "../lib/format";
import { useNow } from "../hooks";
import { Addr, Gen, Spinner, TxLine, explainError } from "./ui";

// The rail is where the money is. The guard decides; the rail holds GEN and
// pays a spend only when the guard authorized it and the decision is past the
// finality delay. These components show it, fund it, and trigger payouts.

const isAddr = (a: string) => /^0x[0-9a-fA-F]{40}$/.test(a);

function useRailStatus() {
  const { client, rail } = useApp();
  const [status, setStatus] = useState<RailStatus | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    if (!isAddr(rail)) {
      setStatus(null);
      setError("");
      return;
    }
    try {
      setStatus(await readRail(client, rail));
      setError("");
    } catch (e) {
      setStatus(null);
      setError("No rail answered at this address on this network.");
      console.warn(e);
    }
  }, [client, rail]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { status, error, reload };
}

/** A transaction in flight, with its outcome. */
function useTx() {
  const [pending, setPending] = useState(false);
  const [hash, setHash] = useState<string>();
  const [outcome, setOutcome] = useState<TxOutcome | null>(null);
  const [err, setErr] = useState("");
  const run = async (fn: (onHash: (h: string) => void) => Promise<TxOutcome>, after?: () => Promise<void>) => {
    setPending(true);
    setHash(undefined);
    setOutcome(null);
    setErr("");
    try {
      setOutcome(await fn(setHash));
      await after?.();
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setPending(false);
    }
  };
  return { pending, hash, outcome, err, run };
}

export function RailPanel() {
  const { client, guard, rail, setRail, mandate, wallet, network, pollMs, canSign } = useApp();
  const { status, error, reload } = useRailStatus();
  const tx = useTx();
  const [amount, setAmount] = useState("0.5");
  const [draft, setDraft] = useState("");
  const me = wallet.kind === "none" ? "" : wallet.address;
  const isPrincipal = sameAddr(me, mandate?.principal);
  // Bradbury finalises 27-31 minutes after a transaction is created (measured).
  const finality = network === "studio" ? 60 : 2400;

  if (!mandate) return null;

  if (!status) {
    return (
      <div className="card">
        <h3>Treasury</h3>
        <p className="sub">
          No rail is attached. Remit decides; a <b>rail</b> holds the money and pays a spend only when this guard
          authorized it. Money left in the agent's own wallet can be spent without asking Remit.
        </p>
        {error && <div className="notice bad">{error}</div>}
        {isPrincipal && !mandate.shadow && (
          <div className="row" style={{ marginBottom: 12 }}>
            <button
              className="btn primary"
              disabled={!canSign || tx.pending}
              onClick={() =>
                tx.run(
                  (onHash) => deployRail(client, { guard, finalitySeconds: finality }, pollMs, onHash),
                  async () => {},
                )
              }
            >
              {tx.pending ? <Spinner /> : null} Deploy a rail for this guard
            </button>
            <span className="hint">Pays {duration(finality)} after each decision, to clear the appeal window.</span>
          </div>
        )}
        {tx.outcome?.applied && tx.outcome.address && (
          <div className="notice good">
            Rail deployed at <span className="mono">{tx.outcome.address}</span>.{" "}
            <button className="btn sm" onClick={() => setRail(tx.outcome!.address!)}>
              Attach it
            </button>
          </div>
        )}
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            setRail(draft);
          }}
        >
          <input className="mono" placeholder="0x… existing rail address" value={draft} onChange={(e) => setDraft(e.target.value)} style={{ flex: "1 1 220px" }} />
          <button className="btn sm" type="submit" disabled={!isAddr(draft)}>
            Attach
          </button>
        </form>
        <TxLine network={network} pending={tx.pending} hash={tx.hash} outcome={tx.outcome} />
        {tx.err && <div className="notice bad">{tx.err}</div>}
      </div>
    );
  }

  const bound = sameAddr(status.guard, guard);
  let value = 0n;
  try {
    value = parseGen(amount);
  } catch {
    value = 0n;
  }
  return (
    <div className="card">
      <h3>Treasury</h3>
      <p className="sub">
        The rail holds the money. Its only payout pays a spend this guard authorized - the exact amount, to the exact
        recipient, once, {duration(status.finality_seconds)} after the decision. The agent cannot withdraw.
      </p>
      {!bound && <div className="notice bad">This rail is bound to a different guard ({status.guard}).</div>}
      <dl className="kv">
        <dt>Rail</dt>
        <dd>
          <Addr value={rail} />
        </dd>
        <dt>Balance</dt>
        <dd>
          <Gen atto={status.balance} />
        </dd>
        <dt>Paid out</dt>
        <dd>
          <Gen atto={status.paid_total} /> across {status.paid_count} {status.paid_count === 1 ? "spend" : "spends"}
        </dd>
        <dt>Finality delay</dt>
        <dd>{duration(status.finality_seconds)}</dd>
      </dl>
      <div className="row" style={{ marginTop: 14 }}>
        <input value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="GEN to add" style={{ width: 110 }} />
        <button
          className="btn"
          disabled={!canSign || tx.pending || value <= 0n}
          onClick={() => tx.run((onHash) => write(client, rail, "fund", [], pollMs, onHash, value), reload)}
        >
          {tx.pending ? <Spinner /> : null} Add GEN
        </button>
        <a className="small" href={`${NETWORKS[network].explorer}/address/${rail}`} target="_blank" rel="noreferrer">
          View on explorer
        </a>
      </div>
      <TxLine network={network} pending={tx.pending} hash={tx.hash} outcome={tx.outcome} successText="Funds added to the rail." />
      {tx.err && <div className="notice bad">{tx.err}</div>}
    </div>
  );
}

/** Payment state of one spend, with a Pay button when the rail would pay it. */
export function CasePayment({ spend }: { spend: SpendView }) {
  const { client, rail, network, pollMs, canSign } = useApp();
  const { status } = useRailStatus();
  const [payment, setPayment] = useState<RailPayment | null>(null);
  const now = useNow();
  const tx = useTx();

  const load = useCallback(async () => {
    if (!isAddr(rail)) return;
    try {
      setPayment(await readPayment(client, rail, spend.id));
    } catch {
      setPayment(null);
    }
  }, [client, rail, spend.id]);
  useEffect(() => {
    void load();
  }, [load]);

  if (!isAddr(rail) || !status) {
    return (
      <p className="small muted" style={{ marginTop: 10 }}>
        No rail is attached, so nothing pays this spend automatically. Attach one on the Mandate page.
      </p>
    );
  }
  if (payment?.paid) {
    return (
      <div className="notice good" style={{ marginTop: 12 }}>
        <strong>Paid.</strong> The rail sent <Gen atto={payment.amount} /> to <Addr value={spend.recipient} />.
      </div>
    );
  }
  if (spend.authorization !== "authorized") {
    return (
      <div className="notice" style={{ marginTop: 12 }}>
        The rail will not pay this spend: the guard says <b>{spend.authorization}</b>. Paying it reverts.
      </div>
    );
  }
  const readyAt = (spend.decided_at ?? 0) + status.finality_seconds;
  const wait = Math.max(0, Math.ceil(readyAt - now));
  return (
    <div style={{ marginTop: 12 }}>
      <div className="row">
        <button
          className="btn primary"
          disabled={!canSign || tx.pending || wait > 0}
          onClick={() => tx.run((onHash) => write(client, rail, "pay", [spend.id], pollMs, onHash), load)}
        >
          {tx.pending ? <Spinner /> : null} Pay <Gen atto={spend.amount} /> from the rail
        </button>
        <span className="hint">
          {wait > 0 ? `Payable in ${duration(wait)}, after the finality delay.` : "Anyone may trigger it; the rail decides who is paid and how much."}
        </span>
      </div>
      <TxLine
        network={network}
        pending={tx.pending}
        hash={tx.hash}
        outcome={tx.outcome}
        successText="Paid. The recipient is credited when the transaction finalises."
        refusalHint="The rail refused to pay."
      />
      {tx.err && <div className="notice bad">{tx.err}</div>}
    </div>
  );
}
