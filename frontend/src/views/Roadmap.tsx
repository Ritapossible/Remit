import { useMemo } from "react";
import plan from "../../../PLAN.md?raw";
import { inline, REPO_URL } from "../lib/docs";

// Generated from PLAN.md - the plan the project is actually built from - so the
// roadmap cannot claim progress the plan does not record.

type Status = "done" | "progress" | "planned";
interface Phase {
  label: string;
  title: string;
  status: Status;
  items: { done: boolean; text: string }[];
}

function parse(md: string) {
  const lines = md.split("\n");
  const phases: Phase[] = [];
  const beyond: { title: string; text: string }[] = [];
  const nonGoals: string[] = [];
  let section: "phase" | "beyond" | "non" | null = null;
  let lastItem: { text: string } | null = null;

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const ph = line.match(/^## (Phase \d+[a-z]?) - (.+?) `\[(x|~| )\]`$/);
    if (ph) {
      phases.push({ label: ph[1], title: ph[2], status: ph[3] === "x" ? "done" : ph[3] === "~" ? "progress" : "planned", items: [] });
      section = "phase";
      lastItem = null;
      continue;
    }
    if (line.startsWith("## ")) {
      section = line === "## Beyond v1" ? "beyond" : line === "## Non-goals" ? "non" : null;
      lastItem = null;
      continue;
    }
    if (section === "phase") {
      const it = line.match(/^- \[(x| )\] (.*)$/);
      if (it) {
        lastItem = { text: it[2] };
        phases[phases.length - 1].items.push({ done: it[1] === "x", text: it[2] });
        continue;
      }
      // Continuation of a wrapped item; nested sub-items are folded into it.
      if (lastItem && /^\s{2,}\S/.test(line) && !/^\s+- \[/.test(line)) {
        const list = phases[phases.length - 1].items;
        list[list.length - 1].text += " " + line.trim();
        continue;
      }
      if (!/^\s/.test(line)) lastItem = null;
    }
    if (section === "beyond") {
      const b = line.match(/^- \*\*(.+?)\*\*\s*(.*)$/);
      if (b) {
        beyond.push({ title: b[1].replace(/\.$/, ""), text: b[2] });
        lastItem = beyond[beyond.length - 1];
        continue;
      }
      if (lastItem && /^\s{2,}\S/.test(line)) {
        beyond[beyond.length - 1].text += " " + line.trim();
        continue;
      }
    }
    if (section === "non") {
      const n = line.match(/^- (.*)$/);
      if (n) nonGoals.push(n[1]);
    }
  }
  return { phases, beyond, nonGoals };
}

const STATUS_TEXT: Record<Status, string> = { done: "Done", progress: "In progress", planned: "Planned" };

export function Roadmap() {
  const { phases, beyond, nonGoals } = useMemo(() => parse(plan), []);
  const items = phases.flatMap((p) => p.items);
  const done = items.filter((i) => i.done).length;

  return (
    <div className="wrap" style={{ paddingTop: 48 }}>
      <span className="ribbon">Roadmap</span>
      <h1 className="display" style={{ fontSize: "clamp(48px, 7vw, 84px)" }}>
        A project, not a <em>demo</em>
      </h1>
      <p className="lede">
        Generated from <span className="mono">PLAN.md</span>, the plan Remit is built from. A phase is done when a test or
        a transaction proves it - not when the code exists.
      </p>

      <div className="stats" style={{ margin: "36px 0 44px" }}>
        <div className="stat feature-stat">
          <div className="v">
            {phases.filter((p) => p.status === "done").length}/{phases.length}
          </div>
          <div className="k">phases complete</div>
        </div>
        <div className="stat">
          <div className="v">
            {done}/{items.length}
          </div>
          <div className="k">milestones checked off</div>
        </div>
        <div className="stat">
          <div className="v">{phases.filter((p) => p.status === "progress").length}</div>
          <div className="k">in progress now</div>
        </div>
        <div className="stat">
          <div className="v">{beyond.length}</div>
          <div className="k">directions beyond v1</div>
        </div>
      </div>

      <div className="phases">
        {phases.map((p) => {
          const n = p.items.filter((i) => i.done).length;
          return (
            <section key={p.label} className={`phase ${p.status}`}>
              <div className="phase-head">
                <div>
                  <div className="eyebrow">{p.label}</div>
                  <h3>{p.title}</h3>
                </div>
                <span className={`badge b-${p.status}`}>{STATUS_TEXT[p.status]}</span>
              </div>
              {p.items.length > 0 && (
                <>
                  <div className="progress-bar" aria-label={`${n} of ${p.items.length} done`}>
                    <i style={{ width: `${(n / p.items.length) * 100}%` }} />
                  </div>
                  <div className="small muted">
                    {n} of {p.items.length}
                  </div>
                  <ul className="checklist">
                    {p.items.map((i, k) => (
                      <li key={k} className={i.done ? "on" : ""}>
                        <span className="box" aria-hidden="true">
                          {i.done ? "✓" : ""}
                        </span>
                        <span dangerouslySetInnerHTML={{ __html: inline(i.text) }} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
          );
        })}
      </div>

      <h2 className="h2" style={{ marginTop: 72 }}>
        Beyond <em>v1</em>
      </h2>
      <p className="lede" style={{ marginBottom: 28 }}>
        Not scheduled. Listed so the direction is visible - and so nobody mistakes any of it for something already built.
      </p>
      <div className="grid-2">
        {beyond.map((b) => (
          <div key={b.title} className="card">
            <h3 className="h3" style={{ fontSize: 22 }}>
              {b.title}
            </h3>
            <p style={{ margin: 0, color: "var(--ink-2)" }} dangerouslySetInnerHTML={{ __html: inline(b.text) }} />
          </div>
        ))}
      </div>

      {nonGoals.length > 0 && (
        <>
          <h2 className="h2" style={{ marginTop: 72 }}>
            Deliberately <em>not</em> in scope
          </h2>
          <ul className="faq" style={{ listStyle: "none", padding: 0 }}>
            {nonGoals.map((g) => (
              <li key={g} style={{ background: "var(--surface-2)", borderRadius: 16, padding: "18px 22px" }} dangerouslySetInnerHTML={{ __html: inline(g) }} />
            ))}
          </ul>
        </>
      )}
      <p className="small muted" style={{ marginTop: 32 }}>
        <a href={`${REPO_URL}/blob/main/PLAN.md`} target="_blank" rel="noreferrer">
          Read PLAN.md on GitHub
        </a>{" "}
        for the reasoning behind the sequencing.
      </p>
    </div>
  );
}
