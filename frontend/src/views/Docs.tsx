import { useMemo } from "react";
import { href } from "../state";
import { DOCS, REPO_URL, renderDoc } from "../lib/docs";

export function Docs({ slug }: { slug: string }) {
  const index = Math.max(0, DOCS.findIndex((d) => d.slug === slug));
  const doc = DOCS[index];
  const rendered = useMemo(() => renderDoc(doc.source), [doc]);
  const prev = DOCS[index - 1];
  const next = DOCS[index + 1];
  const groups = ["Guides", "Reference"] as const;

  return (
    <div className="wrap docs">
      <aside>
        <select
          className="docs-select"
          aria-label="Choose a page"
          value={doc.slug}
          onChange={(e) => (window.location.hash = href({ name: "docs", slug: e.target.value }))}
        >
          {DOCS.map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.group} · {d.title}
            </option>
          ))}
        </select>
        <nav className="docs-nav" aria-label="Documentation">
          {groups.map((g) => (
            <div key={g} style={{ marginBottom: 22 }}>
              <div className="eyebrow" style={{ padding: "0 12px 10px" }}>
                {g}
              </div>
              {DOCS.filter((d) => d.group === g).map((d) => (
                <a key={d.slug} href={href({ name: "docs", slug: d.slug })} aria-current={d.slug === doc.slug ? "page" : undefined}>
                  {d.title}
                </a>
              ))}
            </div>
          ))}
          <div className="eyebrow" style={{ padding: "0 12px 10px" }}>
            Project
          </div>
          <a href={href({ name: "roadmap" })}>Roadmap</a>
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
        </nav>
      </aside>

      <article>
        <div className="prose" dangerouslySetInnerHTML={{ __html: rendered.html }} />
        <div className="doc-foot">
          {prev ? (
            <a className="btn" href={href({ name: "docs", slug: prev.slug })}>
              ← {prev.title}
            </a>
          ) : (
            <span />
          )}
          {next ? (
            <a className="btn soft" href={href({ name: "docs", slug: next.slug })}>
              {next.title} →
            </a>
          ) : (
            <a className="btn soft" href={href({ name: "roadmap" })}>
              Roadmap →
            </a>
          )}
        </div>
        <p className="small muted" style={{ marginTop: 20 }}>
          This page is <span className="mono">docs/{doc.file}</span> in the repository.{" "}
          <a href={`${REPO_URL}/blob/main/docs/${doc.file}`} target="_blank" rel="noreferrer">
            View or propose a change on GitHub
          </a>
          .
        </p>
      </article>

      <aside className="toc" aria-label="On this page">
        {rendered.toc.length > 0 && (
          <>
            <div className="eyebrow" style={{ marginBottom: 10 }}>
              On this page
            </div>
            {rendered.toc.map((t) => (
              <button key={t.id} onClick={() => document.getElementById(t.id)?.scrollIntoView({ behavior: "smooth" })}>
                {t.text}
              </button>
            ))}
          </>
        )}
      </aside>
    </div>
  );
}
