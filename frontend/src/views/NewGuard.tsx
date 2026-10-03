import { useMemo, useState } from "react";
import { useApp, href } from "../state";
import { CONTRACT_CODE, GAS_CAP, compactJson, deployGuard, estimateDeployGas, write, type TxOutcome } from "../chain/remit";
import { RegistryList } from "../components/Court";
import { useTx } from "../components/Rail";
import { campaignTemplate, contractorTemplate, mandateNotices, parseMandateText, validateMandate } from "../lib/mandate";
import { Spinner, TxLine, explainError } from "../components/ui";
import { NETWORKS } from "../chain/networks";

// Two stand-in vendor addresses so a fresh guard has someone to pay. Replace
// them with real recipients in the editor.
const DEMO_VENDORS = ["0x3F55971f7fd2594A90871Db489fBb82f1DB4d747", "0xeF359811497c724Ef1942c6C079c64C07d87952D"];

const TEMPLATES = {
  campaign: { label: "Campaign spend - catches split purchases", make: campaignTemplate },
  contractor: { label: "Contractor payouts - invoice must match delivery", make: contractorTemplate },
} as const;

export function NewGuard() {
  const { client, wallet, network, pollMs, setGuard, canSign } = useApp();
  const me = wallet.kind === "none" ? "" : wallet.address;
  const [agent, setAgent] = useState("");
  const [tpl, setTpl] = useState<keyof typeof TEMPLATES>("campaign");
  const [text, setText] = useState(() => campaignTemplate(DEMO_VENDORS));
  const [maxTier, setMaxTier] = useState(2);
  const [shadow, setShadow] = useState(false);
  const [pending, setPending] = useState(false);
  const [hash, setHash] = useState<string>();
  const [outcome, setOutcome] = useState<TxOutcome | null>(null);
  const [err, setErr] = useState("");
  const reg = useTx();
  const registry = NETWORKS[network].registry;

  const check = useMemo(() => {
    try {
      const m = parseMandateText(text);
      return { errors: validateMandate(m, { storedVersion: 0, maxTier }), notices: mandateNotices(m), parseError: "" };
    } catch (e) {
      return { errors: [], notices: [], parseError: `Not valid JSON: ${(e as Error).message}` };
    }
  }, [text, maxTier]);

  const agentOk = /^0x[0-9a-fA-F]{40}$/.test(agent.trim());
  // Bradbury's per-transaction gas cap covers the guard's code and its
  // constructor arguments, so a long mandate can make a deploy impossible.
  const argBytes = new TextEncoder().encode(compactJson(text)).length + 160;
  const gas = estimateDeployGas(new TextEncoder().encode(CONTRACT_CODE).length, argBytes);
  const tooBig = gas > GAS_CAP * 0.98;
  const valid = !check.parseError && check.errors.length === 0 && agentOk && !tooBig;

  const deploy = async () => {
    setPending(true);
    setHash(undefined);
    setOutcome(null);
    setErr("");
    try {
      setOutcome(
        await deployGuard(
          client,
          { agent: agent.trim(), mandateText: text, maxTier, shadow, engine: NETWORKS[network].engine ?? "" },
          pollMs,
          setHash,
        ),
      );
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <h1 className="page-title">Create a guard</h1>
      <p className="lede">
        One guard per agent. You deploy it, so you are its principal and your key always outranks it. The mandate is
        pinned at deployment and cannot be edited under an open case.
      </p>

      {!NETWORKS[network].deployable && (
        <div className="notice warn" style={{ marginBottom: 16 }}>
          Guards can't be deployed on {NETWORKS[network].label} yet: the shared engine every guard is bound to has
          not been deployed there. See the <a href={href({ name: "roadmap" })}>roadmap</a>, or switch networks.
        </div>
      )}
      <div className="case-grid">
        <div className="card">
          <div style={{ display: "grid", gap: 14 }}>
            <label className="field">
              Agent address <span className="hint">the only key that will be able to request spends</span>
              <div className="row">
                <input className="mono" style={{ flex: 1 }} value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="0x…" />
                <button className="btn sm" type="button" disabled={!me} onClick={() => setAgent(me)}>
                  Use my address
                </button>
              </div>
              <span className="hint">For a demo, use your own address: you will be both principal and agent and can try every action.</span>
            </label>

            <div className="grid-2">
              <label className="field">
                Template
                <select
                  value={tpl}
                  onChange={(e) => {
                    const k = e.target.value as keyof typeof TEMPLATES;
                    setTpl(k);
                    setText(TEMPLATES[k].make(DEMO_VENDORS));
                  }}
                >
                  {Object.entries(TEMPLATES).map(([k, t]) => (
                    <option key={k} value={k}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Max authority tier
                <select value={maxTier} onChange={(e) => setMaxTier(Number(e.target.value))}>
                  <option value={0}>0 - record only</option>
                  <option value={1}>1 - refuse the spend</option>
                  <option value={2}>2 - refuse, severity 2</option>
                  <option value={3}>3 - refuse, severity 3</option>
                </select>
              </label>
            </div>

            <label className="row small" style={{ gap: 8 }}>
              <input type="checkbox" checked={shadow} onChange={(e) => setShadow(e.target.checked)} />
              Shadow mode - record every case on the docket, but never withhold authorization
            </label>

            <label className="field">
              Mandate
              <textarea rows={22} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} />
              <span className="hint">
                Amounts are atto-GEN (GEN × 10¹⁸) and stay exact: the text is sent as written and parsed by the contract.
                Deploy cost ≈ {(gas / 1e6).toFixed(1)}M gas of the {(GAS_CAP / 1e6).toFixed(1)}M a transaction may use.
              </span>
              {tooBig && (
                <div className="notice bad" style={{ marginTop: 8 }}>
                  This mandate is too long to deploy in one transaction. Shorten it: fewer vendors, or shorter questions.
                </div>
              )}
            </label>

            <div>
              <button className="btn primary" disabled={!valid || pending || !canSign || !NETWORKS[network].deployable} onClick={deploy}>
                {pending ? <Spinner /> : null} Deploy guard on {NETWORKS[network].short}
              </button>
              {wallet.kind === "none" && <span className="hint" style={{ marginLeft: 10 }}>Connect a wallet first.</span>}
              {wallet.kind !== "none" && !canSign && (
                <span className="hint" style={{ marginLeft: 10 }}>Switch your wallet to {NETWORKS[network].short} first.</span>
              )}
            </div>
          </div>
          <TxLine
            network={network}
            pending={pending}
            hash={hash}
            outcome={outcome}
            successText={outcome?.address ? `Guard deployed at ${outcome.address}.` : "Guard deployed."}
            refusalHint="The contract rejected the mandate or its arguments."
          />
          {outcome?.applied && outcome.address && (
            <div className="row" style={{ marginTop: 10 }}>
              <button
                className="btn primary"
                onClick={() => {
                  setGuard(outcome.address!);
                  window.location.hash = href({ name: "overview" });
                }}
              >
                Open this guard →
              </button>
              {registry && (
                <button
                  className="btn"
                  disabled={!canSign || reg.pending || !!reg.outcome?.applied}
                  onClick={() => reg.run((onHash) => write(client, registry, "register", [outcome.address!, ""], pollMs, onHash))}
                >
                  {reg.pending ? <Spinner /> : null} {reg.outcome?.applied ? "Registered" : "Register it"}
                </button>
              )}
            </div>
          )}
          {outcome?.applied && (
            <TxLine
              network={network}
              pending={reg.pending}
              hash={reg.hash}
              outcome={reg.outcome}
              successText="Registered: the agent is bound to this guard on this network."
              refusalHint="The registry refused: the agent may already be bound to another principal's guard."
            />
          )}
          {err && <div className="notice bad">{err}</div>}
        </div>

        <div className="card">
          <h3>Checks</h3>
          <p className="sub">Run in your browser with the same rules the contract applies at deployment.</p>
          {check.parseError && <div className="notice bad">{check.parseError}</div>}
          {!check.parseError && check.errors.length === 0 && <div className="notice good">The mandate is valid.</div>}
          {check.errors.map((e) => (
            <div key={e} className="notice bad small">
              {e}
            </div>
          ))}
          {check.notices.map((n) => (
            <div key={n} className="notice warn small">
              {n}
            </div>
          ))}
          {!agentOk && agent && <div className="notice bad small">The agent address is not valid.</div>}
        </div>
      </div>
      <RegistryList />
    </>
  );
}
