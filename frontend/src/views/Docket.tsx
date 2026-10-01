import { useMemo, useState } from "react";
import { useApp, href } from "../state";
import { useDocket } from "../hooks";
import { pathOf, PATH_TEXT } from "../lib/path";
import { ago } from "../lib/format";
import { Addr, Badge, Empty, Gen } from "../components/ui";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "held", label: "Awaiting jury" },
  { id: "jury", label: "Jury decided" },
  { id: "reflex", label: "Refused by arithmetic" },
  { id: "none", label: "Cleared" },
] as const;

export function Docket() {
  const { mandate } = useApp();
  const { docket, error, loading, reload } = useDocket(20000);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");

  const rows = useMemo(() => {
    const list = [...(docket ?? [])].reverse();
    if (filter === "all") return list;
    return list.filter((s) => {
      const p = pathOf(s, mandate).path;
      if (filter === "held") return p === "pending";
      if (filter === "jury") return p === "jury";
      return p === filter;
    });
  }, [docket, filter, mandate]);

  if (!mandate) return <Empty>Load a guard to read its docket.</Empty>;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">Docket</h1>
          <p className="lede" style={{ marginBottom: 16 }}>
            Every spend and how it was decided - including the ones that never needed a jury. This is the public
            record a principal reads before granting real authority.
          </p>
        </div>
        <button className="btn" onClick={() => void reload()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="filters" role="group" aria-label="Filter">
        {FILTERS.map((f) => (
          <button key={f.id} className="chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>

      {error && <div className="notice bad">{error}</div>}
      {!docket && !error && <Empty>Reading the docket…</Empty>}
      {docket && rows.length === 0 && (
        <Empty>
          {docket.length === 0 ? (
            <>
              No spends yet. <a href={href({ name: "spend" })}>Request the first one.</a>
            </>
          ) : (
            "Nothing matches this filter."
          )}
        </Empty>
      )}

      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th className="num">Amount</th>
                <th>Recipient</th>
                <th>How it was decided</th>
                <th>Authorization</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const { path, rule } = pathOf(s, mandate);
                return (
                  <tr
                    key={s.id}
                    className="click"
                    tabIndex={0}
                    onClick={() => (window.location.hash = href({ name: "case", id: s.id }))}
                    onKeyDown={(e) => e.key === "Enter" && (window.location.hash = href({ name: "case", id: s.id }))}
                  >
                    <td className="mono">{s.id}</td>
                    <td className="num">
                      <Gen atto={s.amount} />
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <Addr value={s.recipient} />
                    </td>
                    <td>
                      <div>{PATH_TEXT[path]}</div>
                      <div className="small muted mono">
                        {rule ?? ""}
                        {s.verdict ? ` · ${s.verdict.replace(/_/g, " ")}` : ""}
                      </div>
                    </td>
                    <td>
                      <Badge kind={s.authorization} />
                    </td>
                    <td className="small muted">{ago(s.at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
