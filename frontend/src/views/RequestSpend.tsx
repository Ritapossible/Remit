import { useEffect, useMemo, useState } from "react";
import { useApp, href } from "../state";
import { previewSpend, readSpend, write, type Preview, type SpendView, type TxOutcome } from "../chain/remit";
import { parseGen } from "../lib/money";
import { digestOfUrl, isSha256Hex } from "../lib/digest";
import { describePredicate } from "../lib/mandate";
import { sameAddr } from "../lib/format";
import { Addr, Badge, Empty, Gen, Spinner, TxLine, explainError } from "../components/ui";

export function RequestSpend() {
  const { client, guard, mandate, wallet, network, pollMs, reloadMandate } = useApp();
  const members = useMemo(() => {
    const out: { list: string; addr: string }[] = [];
    for (const [list, addrs] of Object.entries(mandate?.vendor_lists ?? {})) for (const a of addrs) out.push({ list, addr: a });
    return out;
  }, [mandate]);

  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("0.05");
  const [category, setCategory] = useState("media");
  const [uri, setUri] = useState("");
  const [digest, setDigest] = useState("");
  const [claim, setClaim] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [hashing, setHashing] = useState(false);
  const [pending, setPending] = useState(false);
  const [hash, setHash] = useState<string>();
  const [outcome, setOutcome] = useState<TxOutcome | null>(null);
  const [created, setCreated] = useState<SpendView | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!recipient && members[0]) setRecipient(members[0].addr);
  }, [members, recipient]);

  let atto: bigint | null = null;
  let amountErr = "";
  try {
    atto = parseGen(amount);
    if (atto <= 0n) amountErr = "Amount must be positive.";
  } catch (e) {
    amountErr = (e as Error).message;
  }
  const recipientOk = /^0x[0-9a-fA-F]{40}$/.test(recipient.trim());

  // Ask the contract what it WOULD do. Same code path as the real spend.
  useEffect(() => {
    if (!mandate || !recipientOk || !atto || amountErr) {
      setPreview(null);
      return;
    }
    let live = true;
    setPreviewing(true);
    const t = setTimeout(async () => {
      try {
        const p = await previewSpend(client, guard, recipient.trim(), atto!, category);
        if (live) setPreview(p);
      } catch {
        if (live) setPreview(null);
      } finally {
        if (live) setPreviewing(false);
      }
    }, 500);
    return () => {
      live = false;
      clearTimeout(t);
    };
    // atto is derived from amount; depend on the string to avoid bigint identity churn
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, guard, mandate, recipient, amount, category, recipientOk, amountErr]);

  if (!mandate) return <Empty>Load a guard to request a spend against its mandate.</Empty>;

  const me = wallet.kind === "none" ? "" : wallet.address;
  const isAgent = sameAddr(me, mandate.agent);
  const evidenceOk = !uri || isSha256Hex(digest);

  const submit = async () => {
    if (!atto) return;
    setPending(true);
    setHash(undefined);
    setOutcome(null);
    setCreated(null);
    setErr("");
    try {
      const before = mandate.spend_count;
      const o = await write(
        client,
        guard,
        "request_spend",
        [recipient.trim(), atto, category, uri.trim(), uri ? digest : "", claim],
        pollMs,
        setHash,
      );
      setOutcome(o);
      if (o.applied) {
        await reloadMandate();
        setCreated(await readSpend(client, guard, before));
      }
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setPending(false);
    }
  };

  const computeDigest = async () => {
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

  return (
    <>
      <h1 className="page-title">Request a spend</h1>
      <p className="lede">
        The agent declares a payment. Remit decides whether to authorize it — and a preview, run by the contract
        itself, shows which path it will take before anything is signed.
      </p>

      {!isAgent && (
        <div className="notice" style={{ marginBottom: 16 }}>
          Only this guard's agent (<Addr value={mandate.agent} />) can request spends. You can still preview any spend
          below. To try the whole flow yourself, <a href={href({ name: "new" })}>create a guard</a> with your own
          address as the agent.
        </div>
      )}

      <div className="case-grid">
        <div className="card">
          <div style={{ display: "grid", gap: 14 }}>
            <label className="field">
              Recipient
              {members.length > 0 && (
                <select value={members.some((m) => m.addr === recipient) ? recipient : ""} onChange={(e) => setRecipient(e.target.value)}>
                  {members.map((m) => (
                    <option key={m.list + m.addr} value={m.addr}>
                      {m.addr} — on “{m.list}”
                    </option>
                  ))}
                  <option value="">Another address…</option>
                </select>
              )}
              <input className="mono" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="0x…" />
              {!recipientOk && recipient && <span className="hint" style={{ color: "var(--refused)" }}>Not an address.</span>}
            </label>
            <div className="grid-2">
              <label className="field">
                Amount (GEN)
                <input className="mono" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
                {amountErr && <span className="hint" style={{ color: "var(--refused)" }}>{amountErr}</span>}
              </label>
              <label className="field">
                Category
                <input value={category} onChange={(e) => setCategory(e.target.value)} />
              </label>
            </div>
            <label className="field">
              Evidence URL <span className="hint">optional — an invoice or order the jury can retrieve</span>
              <div className="row">
                <input
                  style={{ flex: 1 }}
                  value={uri}
                  onChange={(e) => {
                    setUri(e.target.value);
                    setDigest("");
                  }}
                  placeholder="https://…"
                />
                <button className="btn sm" type="button" disabled={!uri || hashing} onClick={computeDigest}>
                  {hashing ? <Spinner /> : null} Pin digest
                </button>
              </div>
              {digest && <span className="hint mono" style={{ overflowWrap: "anywhere" }}>sha256 {digest}</span>}
            </label>
            <label className="field">
              Note to the jury <span className="hint">shown to validators as untrusted — it cannot override the mandate</span>
              <input value={claim} onChange={(e) => setClaim(e.target.value)} placeholder="e.g. invoice INV-88, part 3 of 3" />
            </label>
            <div>
              <button className="btn primary" disabled={!isAgent || pending || !recipientOk || !!amountErr || !evidenceOk} onClick={submit}>
                {pending ? <Spinner /> : null} Request authorization
              </button>
              {uri && !digest && <span className="hint" style={{ marginLeft: 10 }}>Pin the digest before sending.</span>}
            </div>
          </div>
          <TxLine
            network={network}
            pending={pending}
            hash={hash}
            outcome={outcome}
            successText="The request is recorded and has been classified."
            refusalHint="Only the registered agent may request spends, the amount must be positive, and a committed document needs a digest."
          />
          {err && <div className="notice bad">{err}</div>}
          {created && (
            <div className={`notice ${created.state === "settled" ? "good" : created.state === "refused" ? "bad" : "judgment"}`}>
              <strong>
                Spend #{created.id}: {created.state === "settled" ? "authorized" : created.state === "refused" ? "refused" : "held for the jury"}.
              </strong>{" "}
              <a href={href({ name: "case", id: created.id })}>Open the case →</a>
            </div>
          )}
        </div>

        <div className="card">
          <h3>What Remit would do</h3>
          <p className="sub">Run by the contract as a free view, against its current ledger.</p>
          {previewing && (
            <div className="tx">
              <Spinner /> Asking the contract…
            </div>
          )}
          {!previewing && !preview && <p className="muted small">Enter a recipient and an amount.</p>}
          {!previewing && preview && <PreviewResult preview={preview} amount={atto} />}
        </div>
      </div>
    </>
  );
}

function PreviewResult({ preview, amount }: { preview: Preview; amount: bigint | null }) {
  const { mandate } = useApp();
  const rules = preview.rules.map((id) => mandate?.rules.find((r) => r.id === id)).filter(Boolean);
  if (preview.state === "invalid") return <div className="notice bad">{preview.reason}</div>;
  if (preview.state === "settled")
    return (
      <>
        <Badge kind="settled">Authorized instantly</Badge>
        <p>
          {amount !== null && <Gen atto={amount} />} clears every arithmetic limit and no judgment trigger fires. It
          would be authorized in the same transaction — no jury, no wait.
        </p>
      </>
    );
  if (preview.state === "refused")
    return (
      <>
        <Badge kind="refused">Refused by arithmetic</Badge>
        {rules.map((r) => (
          <p key={r!.id}>
            <span className="mono small">{r!.id}</span>: {describePredicate(r!)}. Refused in the same transaction; no
            jury is spent on it.
          </p>
        ))}
      </>
    );
  return (
    <>
      <Badge kind="held">Held for the jury</Badge>
      <p>
        Every arithmetic limit passes, but a judgment trigger fires. Authorization would be withheld and validators
        convened to answer:
      </p>
      {rules.map((r) => (
        <div key={r!.id} style={{ marginBottom: 10 }}>
          <div className="small muted">
            {r!.id} — because {describePredicate(r!, true)}
          </div>
          <div className="serif" style={{ fontSize: 18, lineHeight: 1.35 }}>
            “{r!.ask}”
          </div>
          {r!.requires_artifact && <div className="small" style={{ color: "var(--held)" }}>This rule requires evidence.</div>}
        </div>
      ))}
    </>
  );
}
