import { useRef, useState } from "react";
import { api, type Answer } from "../api";
import { useAction } from "../hooks";
import { Badge, ErrorNote, Spinner } from "./ui";

interface Turn { q: string; a: Answer }
const IDEAS = ["Where is payment handled?", "Which functions call process_payment?", "Which files access the database?", "Change payment to reject zero amounts"];

export default function Assistant({ repoId, onPick }: { repoId: number; onPick?: (id: number) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const ask = useAction((text: string) => api.ask(repoId, text));
  const end = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    if (!text.trim()) return;
    setQ("");
    const a = await ask.run(text.trim());
    if (a) {
      setTurns((t) => [...t, { q: text.trim(), a }]);
      setTimeout(() => end.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto p-6">
        {turns.length === 0 && (
          <div className="mx-auto max-w-lg py-10 text-center">
            <p className="text-lg font-bold">Ask about this repository</p>
            <p className="mt-1 text-sm text-slate-500">Answers use only this repository's code and its dependency graph.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">{IDEAS.map((i) => <button key={i} className="btn-ghost" onClick={() => send(i)}>{i}</button>)}</div>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-iris px-4 py-2 text-sm text-white">{t.q}</p>
            <div className="glass-flat max-w-[90%] p-4">
              <div className="mb-2"><Badge value={t.a.source === "llm" ? "completed" : "queued"} label={t.a.source === "llm" ? `AI · ${t.a.provider}` : "Retrieval only"} /></div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{t.a.answer}</p>
              {t.a.steps && t.a.steps.length > 0 && (
                <section className="mt-4 border-t border-slate-200 pt-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-bold">Suggested steps</h3>
                    <Badge value={t.a.plan_source === "llm" ? "completed" : "queued"} label={t.a.plan_source === "llm" ? "AI-assisted plan" : "Code-grounded starter plan"} />
                  </div>
                  <ol className="space-y-3">
                    {t.a.steps.map((step, index) => (
                      <li key={`${index}-${step.title}`} className="flex gap-3">
                        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-iris-soft text-xs font-bold text-iris-deep">{index + 1}</span>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold">{step.title}</p>
                          <p className="mt-0.5 text-sm leading-relaxed text-slate-600">{step.detail}</p>
                          {step.file_path && <p className="mt-1 font-mono text-xs text-slate-400">{step.file_path}{step.start_line ? `:${step.start_line}` : ""}</p>}
                          {step.symbol_id && onPick && <button className="mt-1 text-xs font-semibold text-iris-deep hover:underline" onClick={() => onPick(step.symbol_id!)}>Open {step.symbol_name ?? "symbol"}</button>}
                        </div>
                      </li>
                    ))}
                  </ol>
                  <p className="mt-3 text-xs text-slate-400">This is a suggested plan, not an automatic code edit. Review each step and run the project tests.</p>
                </section>
              )}
              {t.a.sources.length > 0 && <p className="mt-3 text-xs text-slate-400">Sources: {t.a.sources.map((s) => `${s.file_path}:${s.start_line}`).join(", ")}</p>}
            </div>
          </div>
        ))}
        {ask.busy && <Spinner label="Searching the codebase…" />}
        <ErrorNote message={ask.error} />
        <div ref={end} />
      </div>
      <form className="flex gap-3 border-t border-slate-100 p-4" onSubmit={(e) => { e.preventDefault(); void send(q); }}>
        <input className="input" placeholder="Ask a question or describe a change (e.g. “Change payment to reject zero amounts”)…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Question or requested change" />
        <button className="btn-primary" disabled={ask.busy}>Ask</button>
      </form>
    </div>
  );
}
