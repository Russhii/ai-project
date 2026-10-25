import { api, type Explanation, type Sym } from "../api";
import { Badge, ErrorNote, Spinner } from "./ui";
import { useAction } from "../hooks";
import { useEffect, useState } from "react";

function Links({ title, items, onPick }: { title: string; items: { id: number; name: string; confidence: string }[]; onPick: (id: number) => void }) {
  return (
    <div>
      <h4 className="mb-1.5 text-sm font-bold">{title} <span className="font-normal text-slate-400">({items.length})</span></h4>
      {items.length === 0 ? <p className="text-sm text-slate-500">None found in the analyzed code.</p> : (
        <div className="flex flex-wrap gap-1.5">
          {items.map((c) => (
            <button key={c.id} onClick={() => onPick(c.id)} className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono text-xs hover:border-iris/50 hover:text-iris-deep"
              title={c.confidence === "heuristic" ? "Matched by name; verify manually" : "Resolved through imports"}>
              {c.name.split(".").slice(-2).join(".")}{c.confidence === "heuristic" && " ~"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExplainPanel({ repoId, sym, onPick }: { repoId: number; sym: Sym; onPick: (id: number) => void }) {
  const [data, setData] = useState<Explanation | null>(null);
  const act = useAction(() => api.explain(repoId, sym.id));
  useEffect(() => setData(null), [sym.id]);
  const run = async () => setData((await act.run()) ?? null);

  return (
    <div className="space-y-4">
      <button className="btn-primary" onClick={run} disabled={act.busy}>{data ? "Explain again" : `Explain ${sym.name}`}</button>
      {act.busy && <div><Spinner label="Analyzing…" /></div>}
      <ErrorNote message={act.error} />
      {data && (
        <>
          <section className="glass-flat p-4">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="font-bold">Purpose</h4>
              <Badge value={data.source === "llm" ? "completed" : "queued"} label={data.source === "llm" ? `AI · ${data.provider}` : "Static analysis"} />
            </div>
            <p className="text-sm leading-relaxed text-slate-700">{data.analysis.purpose}</p>
            {data.analysis.business_logic && <><h4 className="mb-1 mt-3 font-bold">Business logic</h4><p className="text-sm leading-relaxed text-slate-700">{data.analysis.business_logic}</p></>}
          </section>
          <section className="glass-flat space-y-3 p-4">
            <h4 className="font-bold">Known facts from the code</h4>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-500">Location</dt><dd className="font-mono text-xs">{data.facts.file_path}:{data.facts.lines[0]}-{data.facts.lines[1]}</dd>
              <dt className="text-slate-500">Inputs</dt><dd className="font-mono text-xs">{data.facts.parameters.join(", ") || "none"}</dd>
              <dt className="text-slate-500">Returns</dt><dd className="font-mono text-xs">{data.facts.returns ?? "not annotated"}</dd>
              <dt className="text-slate-500">Side effects</dt><dd>{data.facts.side_effects.join("; ") || "none detected"}</dd>
            </dl>
            <Links title="Calls" items={data.facts.calls} onPick={onPick} />
            <Links title="Called by" items={data.facts.called_by} onPick={onPick} />
            <p className="text-xs text-slate-400">A trailing “~” marks a link matched by name only, so double-check it.</p>
          </section>
          {(data.analysis.inferences.length > 0 || data.analysis.concerns.length > 0) && (
            <section className="glass-flat space-y-2 p-4">
              {data.analysis.inferences.length > 0 && <><h4 className="font-bold">Inferences <span className="font-normal text-slate-400">(not provable from the code)</span></h4>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">{data.analysis.inferences.map((i, k) => <li key={k}>{i}</li>)}</ul></>}
              {data.analysis.concerns.length > 0 && <><h4 className="pt-1 font-bold">Potential concerns</h4>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">{data.analysis.concerns.map((i, k) => <li key={k}>{i}</li>)}</ul></>}
            </section>
          )}
        </>
      )}
    </div>
  );
}
