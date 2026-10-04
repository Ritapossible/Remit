import { useEffect, useMemo, useState } from "react";
import { href } from "../state";
import { NETWORKS } from "../chain/networks";
import { makeClient } from "../chain/wallet";
import { readDocket, readMandate, type SpendView } from "../chain/remit";
import type { MandateInfo } from "../lib/mandate";
import { formatGen } from "../lib/money";
import { pathOf } from "../lib/path";
import { Copy, Eye, Key, Pin, Vault } from "../components/icons";

const REPO = "github.com/Ritapossible/Remit";

/** Reads the reference guard directly, independent of the app's selected
 *  network, so the landing page always shows the same live record. */
function useReference() {
  const [data, setData] = useState<{ mandate: MandateInfo; docket: SpendView[] } | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const guard = NETWORKS.studio.defaultGuard;
    if (!guard) return setFailed(true);
    const c = makeClient("studio", { kind: "none" });
    let live = true;
    Promise.all([readMandate(c, guard), readDocket(c, guard)])
      .then(([mandate, docket]) => live && setData({ mandate, docket }))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);
  return { data, failed };
}

export function Home() {
  const { data, failed } = useReference();
  return (
    <>
      <section className="hero wrap">
        <div className="hero-grid">
          <div>
            <span className="ribbon">Built on GenLayer</span>
            <h1 className="display">
              Your agent <span className="hl">spends</span>
              <br />
              only what you <em>meant</em>
            </h1>
            <p className="lede">
              Code can enforce a budget. It can’t enforce a brief. Remit checks every payment an AI agent asks to
              make - arithmetic in the same transaction, and a jury of GenLayer validators only for the questions code
              can’t answer.
            </p>
            <div className="btn-stack" style={{ marginTop: 32 }}>
              <a className="btn primary lg" href={href({ name: "overview" })}>
                Open the app
              </a>
              <a className="btn soft lg" href={href({ name: "docs", slug: "getting-started" })}>
                Read the docs
              </a>
            </div>
          </div>
          <LiveCase data={data} failed={failed} />
        </div>
      </section>

      <section className="section wrap">
        <span className="eyebrow">The gap</span>
        <h2 className="h2" style={{ marginTop: 14 }}>
          A cap stops a big purchase. It doesn’t stop <em>three small ones.</em>
        </h2>
        <p className="lede" style={{ marginBottom: 32 }}>
          A per-payment cap exists to bound the risk of a single purchase. Split the purchase and every payment is
          legal - the numbers pass at every threshold. Only a reading of intent against a written mandate catches it.
        </p>
        <div className="compare">
          <div className="col">
            <h3>Arithmetic can check</h3>
            <ul>
              <li>No single payment above 0.2 GEN</li>
              <li>At most 0.5 GEN in any 24 hours</li>
              <li>Only vendors on the allowlist</li>
            </ul>
          </div>
          <div className="col jury">
            <h3>Only judgment can check</h3>
            <ul>
              <li>Is this one purchase split to stay under the cap?</li>
              <li>Does this invoice match something actually delivered?</li>
              <li>Does this purchase serve the brief it was bought for?</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section wrap">
        <span className="eyebrow">How it works</span>
        <h2 className="h2" style={{ marginTop: 14 }}>
          Fast when it can be. <em>Careful</em> when it must be.
        </h2>
        <div className="steps" style={{ marginTop: 36 }}>
          <div className="step">
            <div className="n">i.</div>
            <h3>Write a mandate</h3>
            <p>
              Rules are typed. <b>Reflex</b> rules are arithmetic. <b>Judgment</b> rules ask one question, and each
              carries a deterministic trigger that decides when it’s worth asking.
            </p>
          </div>
          <div className="step">
            <div className="n">ii.</div>
            <h3>Most spends clear instantly</h3>
            <p>
              Every request is checked in the same transaction. If no trigger fires, it’s authorized on the spot - no
              jury, no wait. If a limit is broken, it’s refused just as fast.
            </p>
          </div>
          <div className="step">
            <div className="n">iii.</div>
            <h3>The rest go to a jury</h3>
            <p>
              When a trigger fires, authorization is withheld and GenLayer validators each answer the rule’s question
              independently - from the ledger and from evidence pinned by its digest.
            </p>
          </div>
        </div>
      </section>

      <section className="section wrap">
        <div className="panel">
          <h2 className="panel-title">
            Authority you can <em>audit</em>
          </h2>
          <div className="features">
            <Feature icon={<Pin />} title="Evidence pinned by digest">
              An agent commits the invoice or order by its sha256. Every validator fetches it and checks the hash
              itself - a document that changed is marked unverified, never trusted.
            </Feature>
            <Feature icon={<Vault />} title="Holds no funds">
              Remit decides; your treasury or payment rail pays. A gate that holds nothing can’t lose anything, and a
              provisional refusal costs nothing to reverse.
            </Feature>
            <Feature icon={<Key />} title="Your key outranks it">
              The principal can release or refuse any held spend in one transaction. Remit adds authority; it never
              takes yours away.
            </Feature>
            <Feature icon={<Eye />} title="Shadow mode first">
              Run with no authority at all. Every case lands on a public docket, so you can read the false-positive
              rate before you grant real power.
            </Feature>
          </div>
          <div className="btn-stack">
            <a className="btn black lg" href={href({ name: "new" })}>
              Create a guard
            </a>
            <a className="btn white lg" href={href({ name: "docs", slug: "integration" })}>
              Integration guide
            </a>
          </div>
        </div>
      </section>

      <Proof data={data} />
      <Faq />

      <section className="section wrap">
        <h2 className="h2">From the docs</h2>
        <div className="cards" style={{ marginTop: 28 }}>
          <DocCard slug="getting-started" art="flag" title="From zero to a jury verdict in five minutes" text="Create a guard with a Studio burner and walk a split purchase to a decision." />
          <DocCard slug="integration" art="rail" title="Connecting a settlement rail" text="One view, three answers - and how to read a receipt so you never pay on a rolled-back decision." />
          <DocCard slug="genvm-notes" art="blocks" title="Building on GenVM: field notes" text="What we measured on Studio that no error message will tell you." />
        </div>
      </section>

      <section className="section wrap">
        <div className="cta">
          <h2>
            Give your agent a <em>remit</em>.
          </h2>
          <div className="btn-stack">
            <a className="btn lg" style={{ background: "var(--cyan)", borderColor: "var(--cyan)", color: "#03222e" }} href={href({ name: "overview" })}>
              Open the app
            </a>
            <a className="btn white lg" href={href({ name: "roadmap" })}>
              See the roadmap
            </a>
          </div>
        </div>
      </section>
    </>
  );
}

function Feature({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="feature">
      <div className="ic">{icon}</div>
      <div>
        <h4>{title}</h4>
        <p>{children}</p>
      </div>
    </div>
  );
}

function LiveCase({ data, failed }: { data: ReturnType<typeof useReference>["data"]; failed: boolean }) {
  const view = useMemo(() => {
    if (!data) return null;
    const decided = [...data.docket].reverse().find((s) => s.verdict);
    const bars = data.docket.slice(-18);
    const max = bars.reduce((m, s) => (BigInt(s.amount) > m ? BigInt(s.amount) : m), 1n);
    return { decided, bars, max, mandate: data.mandate };
  }, [data]);

  const rule = view?.decided && view.mandate.rules.find((r) => r.id === view.decided!.rules[0]);
  const amount = view?.decided ? formatGen(view.decided.amount) : "0.15";
  const [whole, frac = ""] = amount.split(".");

  return (
    <div style={{ position: "relative" }}>
      <div className="device" role="figure" aria-label="A case from the reference guard">
        <div className="top">
          <span>{view ? <span className="live">Live · GenLayer Studio</span> : failed ? "Reference case" : "Reading the chain…"}</span>
          <span className="mono">case #{view?.decided?.id ?? "-"}</span>
        </div>
        <div className="amt">
          {whole}
          <span>.{frac || "00"}</span> GEN
        </div>
        <div className="meta">Held for the jury · {view?.decided ? `${view.decided.rules.join(", ")} trigger` : "structuring trigger"}</div>
        <div className="verdict-chip">
          {view?.decided?.verdict === "in_remit" ? "Within the remit" : view?.decided?.verdict === "undetermined" ? "Undetermined" : "Outside the remit"}
          {view?.decided ? <span style={{ fontWeight: 400 }}>· {view.decided.confidence}%</span> : null}
        </div>
        <p className="q">“{rule?.ask ?? "Are these separate purchases, or one purchase split to stay under the cap?"}”</p>
        {view && (
          <>
            <div className="bar" aria-hidden="true">
              {view.bars.map((s) => {
                const p = pathOf(s, view.mandate).path;
                const h = 18 + Number((BigInt(s.amount) * 100n) / view.max) * 0.46;
                return <i key={s.id} className={p === "jury" || p === "pending" ? "jury" : p === "reflex" ? "ref" : ""} style={{ height: `${h}px` }} />;
              })}
            </div>
            <div className="legend">
              <span><b style={{ background: "#1c4a58" }} />cleared instantly</span>
              <span><b style={{ background: "#ff9d8b" }} />refused by arithmetic</span>
              <span><b style={{ background: "#0bbcd4" }} />sent to the jury</span>
            </div>
          </>
        )}
      </div>
      <div className="dots hero-dots" aria-hidden="true" />
    </div>
  );
}

function Proof({ data }: { data: ReturnType<typeof useReference>["data"] }) {
  const docket = data?.docket ?? [];
  const noJury = docket.filter((s) => {
    const p = pathOf(s, data!.mandate).path;
    return p === "none" || p === "reflex";
  }).length;
  return (
    <section className="section wrap">
      <span className="ribbon">Measured, not claimed</span>
      <h2 className="h2" style={{ marginTop: 20 }}>
        Running on GenLayer <em>today</em>
      </h2>
      <div className="stats" style={{ marginTop: 28 }}>
        <div className="stat feature-stat">
          <div className="v">{data ? (docket.length ? `${Math.round((noJury / docket.length) * 100)}%` : "-") : "…"}</div>
          <div className="k">of reference spends decided without a jury · live</div>
        </div>
        <div className="stat">
          <div className="v">8/8</div>
          <div className="k">consecutive jury trials reached consensus with pinned evidence</div>
        </div>
        <div className="stat">
          <div className="v">52/52</div>
          <div className="k">mutants killed - every guard has a test that fails without it</div>
        </div>
        <div className="stat">
          <div className="v">0</div>
          <div className="k">failed checks across the on-chain walkthroughs</div>
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 14 }}>
        Trial and test figures come from the scripts in the repository and can be re-run by anyone. The live figure is
        read from the reference guard as this page loads.
      </p>
    </section>
  );
}

const FAQS: { q: string; a: React.ReactNode }[] = [
  {
    q: "What is Remit?",
    a: (
      <p>
        A spending gate for AI agents, built as a GenLayer Intelligent Contract. You write a mandate; every payment
        your agent requests is checked against it and comes back authorized, refused, or pending while a jury decides.
      </p>
    ),
  },
  {
    q: "Does Remit hold my agent’s money?",
    a: (
      <>
        <p>
          The gate doesn’t. A separate contract, the <b>rail</b>, holds it. The rail’s only payout pays a spend the
          guard authorized - the exact amount, to the exact recipient, once - and only after the decision has had time
          to finalise. The agent’s key has no way to withdraw from it.
        </p>
        <p>
          Fund the rail instead of the agent’s wallet and the check sits on the path the money takes. Money you leave
          in the agent’s own wallet, Remit cannot stop.
        </p>
      </>
    ),
  },
  {
    q: "Why not just use a spending cap?",
    a: (
      <p>
        Caps stop one large payment. They can’t tell whether three small ones are a single purchase split to get
        under the cap - every number passes. Remit keeps caps for what they’re good at and sends only that kind of
        question to a jury.
      </p>
    ),
  },
  {
    q: "Who decides a held payment - and can the agent talk its way past them?",
    a: (
      <>
        <p>
          GenLayer validators. Each fetches the evidence, checks its digest, reads the payment history the contract
          recorded, and answers the mandate’s question independently.
        </p>
        <p>
          The agent’s note and any document it attaches are shown to them as the agent’s own evidence: the ledger wins
          where they conflict. Amounts, recipients and history come from the contract’s own ledger, not from the agent.
        </p>
        <p>
          Each validator votes fail-closed: it accepts a release only if it reaches the same answer itself, and doubt
          falls to the mandate’s default, which in the templates is to refuse. The round is decided by a majority of
          validators, so a convincing forgery can still win: invoices forged to make a split look like two unrelated
          orders were refused or left in doubt in most runs, and released in one of three on Studio. That is why the
          rail waits out the appeal window before it pays.
        </p>
      </>
    ),
  },
  {
    q: "What about a payment that slipped under every trigger?",
    a: (
      <>
        <p>
          It can still be challenged. For the mandate’s clawback window, anyone but the agent can challenge a payment
          that cleared without a jury, naming the rule it evaded and posting a bond. The rail won’t pay it while the
          challenge is open; the agent can answer with evidence; then the jury rules.
        </p>
        <p>
          Upheld, the payment is blocked - or, if the rail already paid it, made good from the agent’s standing bond -
          and a tier-2 or tier-3 rule freezes the agent. Dismissed, the bond goes to the agent, and the challenger’s next
          bond doubles, so griefing prices itself out.
        </p>
      </>
    ),
  },
  {
    q: "What if the jury is slow, unsure, or wrong?",
    a: (
      <p>
        Every hold has a deadline and a default you chose. “Undetermined” falls to that default - unproven is not
        guilty. The principal can release or refuse any held spend at any time, and anyone can appeal a jury’s round
        before it is final - the rail waits out that window before it pays. And shadow mode lets you watch the docket
        before granting authority at all.
      </p>
    ),
  },
  {
    q: "Is it live?",
    a: (
      <p>
        Yes - on GenLayer Studio and on the Bradbury testnet, where the guard, its rail and court, and the registry
        are deployed, and each scenario in the repository is recorded as real transactions. See the{" "}
        <a href={href({ name: "roadmap" })}>roadmap</a> for what’s done and what’s next.
      </p>
    ),
  },
];

function Faq() {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`https://${REPO}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <section className="section wrap">
      <h2 className="h2">Frequently asked</h2>
      <button className="copy-pill" onClick={copy} style={{ margin: "8px 0 40px" }}>
        <span>{copied ? "Link copied" : REPO}</span>
        <Copy />
      </button>
      <div className="faq">
        {FAQS.map((f) => (
          <details key={f.q}>
            <summary>{f.q}</summary>
            <div className="a">{f.a}</div>
          </details>
        ))}
      </div>
    </section>
  );
}

const ART: Record<string, React.ReactNode> = {
  flag: (
    <svg viewBox="0 0 160 120" width="100%" height="100%" aria-hidden="true">
      <rect x="62" y="22" width="4" height="84" rx="2" fill="#03222e" />
      <path d="M66 24h46l-11 13 11 13H66z" fill="#0bbcd4" stroke="#03222e" strokeWidth="2.5" strokeLinejoin="round" />
      <rect x="44" y="100" width="40" height="8" rx="4" fill="#03222e" />
    </svg>
  ),
  rail: (
    <svg viewBox="0 0 160 120" width="100%" height="100%" aria-hidden="true">
      <rect x="22" y="44" width="116" height="32" rx="16" fill="#03222e" />
      <circle cx="58" cy="60" r="10" fill="#0bbcd4" />
      <circle cx="102" cy="60" r="10" fill="#fff" />
      <path d="M52 60l4 4 8-8" stroke="#03222e" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  blocks: (
    <svg viewBox="0 0 160 120" width="100%" height="100%" aria-hidden="true">
      <rect x="54" y="20" width="52" height="86" rx="4" fill="#0bbcd4" stroke="#03222e" strokeWidth="2.5" />
      {[34, 56, 78].map((y) => (
        <g key={y}>
          <path d={`M66 ${y + 14}v-8a5 5 0 0 1 10 0v8z`} fill="#fff" stroke="#03222e" strokeWidth="2" />
          <path d={`M84 ${y + 14}v-8a5 5 0 0 1 10 0v8z`} fill="#fff" stroke="#03222e" strokeWidth="2" />
        </g>
      ))}
    </svg>
  ),
};

function DocCard({ slug, title, text, art }: { slug: string; title: string; text: string; art: keyof typeof ART }) {
  return (
    <a className="card-link" href={href({ name: "docs", slug })}>
      <div className="thumb dots">{ART[art]}</div>
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
    </a>
  );
}
