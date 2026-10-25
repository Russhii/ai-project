import { api, type Impact, type Sym } from "../api";
import { useLoad } from "../hooks";
import { Badge, ErrorNote, Spinner } from "./ui";

export default function ImpactPanel({ repoId, sym, onPick }: { repoId: number; sym: Sym; onPick: (id: number) => void }) {
  const { data, error, loading } = useLoad<Impact>(() => api.impact(repoId, sym.id), [repoId, sym.id]);
  if (loading) return <Spinner label="Tracing dependents…" />;
  if (error || !data) return <ErrorNote message={error} />;
  const { risk, summary } = data;
  return (
    <div className="space-y-4">
      <section className="glass-flat p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-500">Change risk for {data.target.name}</p>
            <p className="text-3xl font-extrabold tracking-tight">{risk.level}</p>
          </div>
          <div className="text-right"><Badge value={risk.level} label={`${risk.score} / ${risk.max_score} points`} /></div>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">{data.reason}</p>
      </section>
      <div className="grid grid-cols-4 gap-2 text-center">
        {[["Files", summary.affected_files], ["Functions", summary.affected_functions], ["APIs", summary.affected_apis], ["Tests", summary.related_tests]].map(([l, v]) => (
          <div key={l} className="glass-flat px-2 py-2.5"><p className="text-xl font-extrabold">{v}</p><p className="text-xs text-slate-500">{l}</p></div>
        ))}
      </div>
      <section className="glass-flat p-4">
        <h4 className="mb-2 font-bold">Why this score</h4>
        <ul className="space-y-2">
          {risk.factors.map((f) => (
            <li key={f.factor} className="text-sm">
              <div className="flex justify-between"><span className="font-semibold">{f.factor}</span><span className="text-slate-500">+{f.points}</span></div>
              <div className="my-1 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-iris" style={{ width: `${Math.min(100, (f.points / 3) * 100)}%` }} /></div>
              <p className="text-xs text-slate-500">{f.explanation}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-slate-400">{risk.disclaimer}</p>
      </section>
      {data.dependency_paths.length > 0 && (
        <section className="glass-flat p-4">
          <h4 className="mb-2 font-bold">Dependency paths</h4>
          <ul className="space-y-2">
            {data.dependency_paths.map((p, i) => (
              <li key={i} className="flex flex-wrap items-center gap-1 text-xs">
                {p.map((n, k) => (
                  <span key={n.id} className="flex items-center gap-1">
                    {k > 0 && <span className="text-slate-400">{p[k - 1].heuristic_link ? "⇢" : "→"}</span>}
                    <button onClick={() => onPick(n.id)} className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 font-mono hover:border-iris/50">{n.label}</button>
                  </span>
                ))}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-400">Paths read from the affected code toward the changed function. A dashed arrow is a link matched by name only.</p>
        </section>
      )}
      <List title="Affected APIs" items={data.affected_apis.map((a) => ({ id: a.id, text: a.route ?? a.name, sub: `${a.name} · ${a.file_path}` }))} onPick={onPick} />
      <List title="Related tests" items={data.related_tests.map((t) => ({ id: t.id, text: t.name, sub: t.file_path }))} onPick={onPick} empty="No test reaches this code. Generate characterization tests next." />
      <section className="glass-flat p-4">
        <h4 className="mb-2 font-bold">Affected files <span className="font-normal text-slate-400">({data.affected_files.length})</span></h4>
        <ul className="space-y-0.5 font-mono text-xs text-slate-600">{data.affected_files.map((f) => <li key={f}>{f}</li>)}</ul>
      </section>
    </div>
  );
}

function List({ title, items, onPick, empty }: { title: string; items: { id: number; text: string; sub: string }[]; onPick: (id: number) => void; empty?: string }) {
  if (items.length === 0 && !empty) return null;
  return (
    <section className="glass-flat p-4">
      <h4 className="mb-2 font-bold">{title} <span className="font-normal text-slate-400">({items.length})</span></h4>
      {items.length === 0 ? <p className="text-sm text-slate-500">{empty}</p> : (
        <ul className="space-y-1.5">{items.map((i) => (
          <li key={i.id}><button onClick={() => onPick(i.id)} className="text-left text-sm hover:text-iris-deep"><span className="font-semibold">{i.text}</span><span className="block text-xs text-slate-500">{i.sub}</span></button></li>
        ))}</ul>
      )}
    </section>
  );
}
