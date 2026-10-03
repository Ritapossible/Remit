import { RailPanel } from "../components/Rail";
import { FreezeBanner } from "../components/Court";
import { useApp, href } from "../state";
import { useDocket } from "../hooks";
import { describePredicate, type RuleInfo } from "../lib/mandate";
import { duration } from "../lib/format";
import { pathOf } from "../lib/path";
import { Addr, Badge, Empty } from "../components/ui";
import { NETWORKS } from "../chain/networks";

export function Overview() {
  const { mandate, mandateError, guard, network, setGuard } = useApp();
  const { docket } = useDocket();

  if (!mandate) {
    const def = NETWORKS[network].defaultGuard;
    return (
      <>
        <h1 className="page-title">Your agent can have a wallet. Remit gives it a remit.</h1>
        <p className="lede">
          Code can enforce a budget. It cannot enforce a brief. Remit applies both kinds of rule, each with the
          machinery it needs: arithmetic clears in the same transaction, and only the questions code cannot answer
          go to a jury of GenLayer validators.
        </p>
        {mandateError && <div className="notice bad">{mandateError}</div>}
        {!guard && !def && (
          <div className="notice warn" style={{ marginTop: 16 }}>
            No reference guard is recorded for {NETWORKS[network].label} in this build. Load a guard by address, deploy
            one on the New guard page, or see the <a href={href({ name: "roadmap" })}>roadmap</a>.
          </div>
        )}
        {!guard && (
          <div className="row" style={{ marginTop: 16 }}>
            {def && (
              <button className="btn primary" onClick={() => setGuard(def)}>
                Open the reference guard on {NETWORKS[network].short}
              </button>
            )}
            <a className="btn" href={href({ name: "new" })}>
              Create a guard
            </a>
          </div>
        )}
        {guard && !mandateError && <Empty>Reading the mandate…</Empty>}
      </>
    );
  }

  const reflex = mandate.rules.filter((r) => r.type === "reflex");
  const judgment = mandate.rules.filter((r) => r.type === "judgment");
  const total = docket?.length ?? 0;
  const paths = (docket ?? []).map((s) => pathOf(s, mandate).path);
  const noJury = paths.filter((p) => p === "none" || p === "reflex").length;
  const jury = paths.filter((p) => p === "jury" || p === "pending").length;
  const refused = (docket ?? []).filter((s) => s.authorization === "refused").length;
  const d = mandate.defaults;

  return (
    <>
      <FreezeBanner />
      <h1 className="page-title">This agent spends under a written mandate.</h1>
      <p className="lede">
        Every payment is checked against the rules below before it is authorized. Arithmetic decides in the same
        transaction. A jury is convened only when a judgment rule's trigger fires - and it answers one question.
      </p>

      <div className="stats">
        <div className="stat feature-stat">
          <div className="v">{docket ? (total ? `${Math.round((noJury / total) * 100)}%` : "-") : "…"}</div>
          <div className="k">decided without a jury</div>
        </div>
        <div className="stat">
          <div className="v">{docket ? total : "…"}</div>
          <div className="k">spends requested</div>
        </div>
        <div className="stat">
          <div className="v">{docket ? jury : "…"}</div>
          <div className="k">sent to the jury</div>
        </div>
        <div className="stat">
          <div className="v">{docket ? refused : "…"}</div>
          <div className="k">refused</div>
        </div>
      </div>

      <div className="lanes">
        <section className="lane reflex" aria-labelledby="lane-reflex">
          <header>
            <h4 id="lane-reflex">Reflex · arithmetic</h4>
            <Badge kind="reflex" plain>
              {reflex.length} {reflex.length === 1 ? "rule" : "rules"}
            </Badge>
          </header>
          <p className="blurb">Plain Python in the spend transaction. No LLM, no committee, no added latency.</p>
          {reflex.map((r) => (
            <RuleRow key={r.id} r={r} />
          ))}
          {!reflex.length && <p className="muted small">No arithmetic limits.</p>}
        </section>

        <section className="lane judgment" aria-labelledby="lane-judgment">
          <header>
            <h4 id="lane-judgment">Judgment · the jury</h4>
            <Badge kind="judgment" plain>
              {judgment.length} {judgment.length === 1 ? "rule" : "rules"}
            </Badge>
          </header>
          <p className="blurb">
            Convened only when the trigger fires. Validators read the rule, the facts the contract recorded, and any
            evidence the agent committed - then answer one question.
          </p>
          {judgment.map((r) => (
            <RuleRow key={r.id} r={r} />
          ))}
          {!judgment.length && (
            <div className="notice warn">
              No judgment rules. Everything here is arithmetic a plain smart contract could evaluate faster.
            </div>
          )}
        </section>
      </div>

      <h2 className="app-h2">Where the money is</h2>
      <RailPanel />

      <h2 className="app-h2">Authority</h2>
      <div className="grid-2">
        <div className="card">
          <dl className="kv">
            <dt>Principal</dt>
            <dd>
              <Addr value={mandate.principal} /> <span className="muted small">owns the money; always outranks Remit</span>
            </dd>
            <dt>Agent</dt>
            <dd>
              <Addr value={mandate.agent} /> <span className="muted small">the only key that can request spends</span>
            </dd>
            <dt>Mode</dt>
            <dd>
              {mandate.shadow ? (
                <>
                  <Badge kind="held">Shadow</Badge>{" "}
                  <span className="small">refusals are recorded on the docket but never withheld</span>
                </>
              ) : (
                <>
                  <Badge kind="settled">Enforcing</Badge>{" "}
                  <span className="small">refusals withhold authorization</span>
                </>
              )}
            </dd>
            <dt>Max tier</dt>
            <dd>
              {mandate.max_tier}{" "}
              <span className="muted small">
                - the most authority granted. A breach at tier 1 refuses the payment; tier 2 also freezes the agent
                until the principal lifts it; tier 3 also revokes every unpaid payment requested before the breach.
              </span>
            </dd>
            <dt>Mandate</dt>
            <dd>
              version {mandate.mandate_version}
              {mandate.mandate_digest ? (
                <>
                  {" "}
                  · <span className="mono small">{mandate.mandate_digest.slice(0, 16)}…</span>
                </>
              ) : null}
            </dd>
          </dl>
        </div>
        <div className="card">
          <dl className="kv">
            <dt>Response window</dt>
            <dd>
              {duration(d.response_window_seconds)}{" "}
              <span className="muted small">an agent cannot lose a case for silence before this passes</span>
            </dd>
            <dt>Hold deadline</dt>
            <dd>
              {duration(d.hold_deadline_seconds)} <span className="muted small">no hold is indefinite</span>
            </dd>
            <dt>If undetermined</dt>
            <dd>
              {d.on_undetermined === "refund" ? "refuse" : "release"}{" "}
              <span className="muted small">unproven is not guilty - the principal chose this default</span>
            </dd>
            <dt>At the deadline</dt>
            <dd>{d.on_deadline === "refund" ? "refuse" : "release"}</dd>
          </dl>
        </div>
      </div>

      {mandate.vendor_lists && Object.keys(mandate.vendor_lists).length > 0 && (
        <>
          <h2 className="app-h2">Who this agent may pay</h2>
          <div className="grid-2">
            {Object.entries(mandate.vendor_lists).map(([name, addrs]) => (
              <div className="card" key={name}>
                <h3>“{name}”</h3>
                <p className="sub">
                  {addrs.length} {addrs.length === 1 ? "address" : "addresses"}
                </p>
                <div className="row">
                  {addrs.map((a) => (
                    <Addr key={a} value={a} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function RuleRow({ r }: { r: RuleInfo }) {
  if (r.type === "reflex") {
    return (
      <div className="rule">
        <div className="id">{r.id}</div>
        <div className="text">{describePredicate(r)}</div>
      </div>
    );
  }
  return (
    <div className="rule">
      <div className="id">
        {r.id} · tier {r.tier}
        {r.requires_artifact ? " · evidence required" : ""}
      </div>
      <div className="when">When {describePredicate(r, true)}, ask:</div>
      <div className="ask">“{r.ask}”</div>
    </div>
  );
}
