import { useEffect, useState } from "react";
import { api, type Sym, type TestCase } from "../api";
import { useAction } from "../hooks";
import { Badge, ErrorNote, Spinner } from "./ui";

export default function TestsPanel({ repoId, sym }: { repoId: number; sym: Sym }) {
  const [tc, setTc] = useState<TestCase | null>(null);
  const gen = useAction(() => api.genTests(repoId, sym.id));
  const run = useAction((id: number) => api.runTest(repoId, id));
  useEffect(() => setTc(null), [sym.id]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">Characterization tests record what {sym.name} does <em>today</em>, so you notice when a change alters it. Review the code before running it.</p>
      <button className="btn-primary" onClick={async () => setTc((await gen.run()) ?? null)} disabled={gen.busy}>{tc ? "Generate again" : "Generate tests"}</button>
      {gen.busy && <div><Spinner label="Drafting tests…" /></div>}
      <ErrorNote message={gen.error ?? run.error} />
      {tc && (
        <section className="glass-flat p-4">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="font-bold">Generated pytest code</h4>
            <div className="flex gap-2"><Badge value="generated" label={tc.source === "llm" ? "AI drafted" : "Signature template"} /><Badge value={tc.status} /></div>
          </div>
          <pre className="max-h-72 overflow-auto rounded-xl bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-800">{tc.code}</pre>
          <div className="mt-3 flex items-center gap-3">
            <button className="btn-ghost" disabled={run.busy || tc.status === "blocked"} onClick={async () => { const r = await run.run(tc.id); if (r) setTc(r); }}>
              Run in Docker sandbox
            </button>
            {run.busy && <Spinner label="Running (no network, read-only)…" />}
          </div>
          {tc.output && <pre className="mt-3 max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-3 font-mono text-xs text-slate-100">{tc.output}</pre>}
        </section>
      )}
    </div>
  );
}
