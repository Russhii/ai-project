import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type UpdateCheck } from "../api";
import Assistant from "../components/Assistant";
import CodePane from "../components/CodePane";
import ExplainPanel from "../components/ExplainPanel";
import FileTree from "../components/FileTree";
import GraphView from "../components/GraphView";
import ImpactPanel from "../components/ImpactPanel";
import TestsPanel from "../components/TestsPanel";
import { Badge, Card, Empty, ErrorNote, Spinner } from "../components/ui";
import { useAction, useLoad } from "../hooks";
import { JobsTable } from "./Jobs";

type Tab = "explorer" | "graph" | "assistant" | "jobs";
type Panel = "explain" | "impact" | "tests";

export default function RepoPage() {
  const id = Number(useParams().id);
  const repo = useLoad(() => api.repo(id), [id], 2500);
  const status = repo.data?.status;
  const files = useLoad(() => api.files(id), [id, status]);
  const symbols = useLoad(() => api.symbols(id), [id, status]);
  const overview = useLoad(() => api.repositorySummary(id), [id, status], 10000);
  const analyze = useAction(() => api.analyze(id));
  const checkUpdates = useAction(() => api.checkUpdates(id));
  const refresh = useAction(() => api.refresh(id));

  const [tab, setTab] = useState<Tab>("explorer");
  const [panel, setPanel] = useState<Panel>("explain");
  const [filePath, setFilePath] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState("");
  const [tourStep, setTourStep] = useState<number | null>(null);
  const [freshness, setFreshness] = useState<UpdateCheck | null>(null);

  const syms = useMemo(() => symbols.data ?? [], [symbols.data]);
  const selected = syms.find((s) => s.id === selectedId) ?? null;
  const content = useLoad(() => (filePath ? api.file(id, filePath) : Promise.resolve(null)), [id, filePath]);
  const inFile = syms.filter((s) => s.file_path === filePath);
  const analyzing = status === "analyzing";
  const ready = status === "analyzed" && syms.length > 0;

  useEffect(() => { setFilePath(null); setSelectedId(null); }, [id]);
  useEffect(() => {
    if (!filePath && files.data?.length) {
      const first = files.data.find((f) => f.language === "python" && !f.path.includes("test")) ?? files.data.find((f) => f.language === "python");
      if (first) setFilePath(first.path);
    }
  }, [files.data, filePath]);

  const pick = (sid: number) => {
    const s = syms.find((x) => x.id === sid);
    if (s) { setSelectedId(sid); setFilePath(s.file_path); }
  };
  useEffect(() => {
    setTourStep(null);
    if (ready && !window.localStorage.getItem(`lci-tour-seen-${id}`)) setTourStep(0);
  }, [ready, id]);
  useEffect(() => {
    if (tourStep === 1) {
      setTab("explorer");
      if (!selected && syms[0]) pick(syms[0].id);
    } else if (tourStep === 2) {
      setTab("graph");
    } else if (tourStep === 3) {
      setTab("explorer");
      setPanel("impact");
      if (!selected && syms[0]) pick(syms[0].id);
    } else if (tourStep === 4) {
      setTab("assistant");
    }
  }, [tourStep]);
  const closeTour = () => {
    window.localStorage.setItem(`lci-tour-seen-${id}`, "true");
    setTourStep(null);
  };
  const nextTourStep = () => {
    if (tourStep === 4) closeTour();
    else setTourStep((step) => step === null ? 0 : step + 1);
  };
  const checkForUpdates = async () => {
    const result = await checkUpdates.run();
    if (result) setFreshness(result);
  };
  const updateAndAnalyze = async () => {
    const result = await refresh.run();
    if (result) {
      setFreshness(null);
      void repo.reload();
      void overview.reload();
    }
  };
  const downloadReport = () => {
    if (!repo.data || !overview.data) return;
    const report = {
      title: `Code intelligence report: ${repo.data.name}`,
      generated_at: new Date().toISOString(),
      repository: { name: repo.data.name, url: repo.data.url },
      analyzed_at: overview.data.analysis.created_at,
      source_commit: overview.data.analysis.source_commit,
      summary: {
        files: overview.data.analysis.files,
        supported_python_files: overview.data.supported_files,
        unsupported_files: overview.data.unsupported_files,
        symbols: overview.data.analysis.symbols,
        dependencies: overview.data.analysis.dependencies,
        dependency_confidence: overview.data.confidence,
        languages: overview.data.languages,
        parse_error_count: overview.data.analysis.parse_error_count,
      },
      dependency_spotlight: overview.data.spotlight,
      note: "Summary only. Source code is not included. Links marked heuristic are matched by name and may be inaccurate.",
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${repo.data.name}-analysis-report.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const visible = syms.filter((s) => s.qualname.toLowerCase().includes(filter.toLowerCase())).slice(0, 80);

  const tabs: [Tab, string][] = [["explorer", "Code explorer"], ["graph", "Dependency graph"], ["assistant", "Assistant"], ["jobs", "Jobs"]];
  const tour = [
    { title: "Start with the code map", text: "The overview summarizes what was scanned, which files the Python analyzer supports, and any unsupported files or parse errors." },
    { title: "Explore a symbol", text: "Browse files or search functions and classes. Select a symbol to see its explanation, tests, and change-impact panel." },
    { title: "Trace dependencies", text: "The graph shows callers on the left and dependencies on the right. Dashed edges are name-based heuristic matches." },
    { title: "Understand change impact", text: "Impact reports show affected code, APIs, tests, and a transparent heuristic risk score. Treat it as a guide, not proof." },
    { title: "Ask and revisit", text: "Ask questions using the example prompts, then revisit saved analysis runs in Jobs or download a code-free report." },
  ];

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-extrabold tracking-tight">{repo.data?.name ?? "Repository"}</h1>
          {status && <Badge value={status} />}
          {repo.data && <span className="text-sm text-slate-500">{repo.data.file_count} files · {repo.data.symbol_count} symbols</span>}
        </div>
        <div className="flex items-center gap-3">
          {analyzing && <Spinner label="Analyzing…" />}
          <button className="btn-ghost" disabled={analyzing || analyze.busy} onClick={async () => { await analyze.run(); void repo.reload(); }}>{ready ? "Re-analyze" : "Analyze repository"}</button>
        </div>
      </div>
      <ErrorNote message={repo.error ?? analyze.error ?? symbols.error} />

      {ready && (
        <Card className="mb-4 p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold">Analysis overview</h2>
              <p className="text-sm text-slate-500">
                {overview.data?.analysis.created_at ? `Latest completed analysis ${new Date(overview.data.analysis.created_at).toLocaleString()}` : "Analysis results are saved in this repository's job history."}
                {overview.data?.analysis.source_commit && <span className="ml-1 font-mono">· {overview.data.analysis.source_commit.slice(0, 10)}</span>}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-ghost" disabled={checkUpdates.busy} onClick={() => void checkForUpdates()}>{checkUpdates.busy ? "Checking…" : "Check for updates"}</button>
              {repo.data?.url.startsWith("https://github.com/") && <button className="btn-ghost" disabled={analyzing || refresh.busy} onClick={() => void updateAndAnalyze()}>{refresh.busy ? "Updating…" : "Update code & re-analyze"}</button>}
              <button className="btn-primary" disabled={!overview.data} onClick={downloadReport}>Download report</button>
              <button className="btn-ghost" onClick={() => setTourStep(0)}>Guided tour</button>
            </div>
          </div>
          {overview.error && <div className="mt-3"><ErrorNote message={overview.error} /></div>}
          {(checkUpdates.error || refresh.error) && <div className="mt-3"><ErrorNote message={checkUpdates.error ?? refresh.error} /></div>}
          {freshness && (
            <div className={`mt-4 rounded-xl px-4 py-3 text-sm ${freshness.stale ? "border border-amber-200 bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}>
              {!freshness.supported ? "Freshness check is unavailable until this repository has a GitHub commit recorded." : freshness.stale
                ? "A newer commit is available on GitHub. Update the checkout and re-analyze to refresh these results."
                : "This analysis matches the latest commit on the repository's default branch."}
            </div>
          )}
          {overview.data && (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <OverviewStat label="Files scanned" value={overview.data.analysis.files} detail={`${overview.data.analysis.symbols} symbols indexed`} />
                <OverviewStat label="Python analyzer" value={`${overview.data.supported_files} files`} detail="Python files are parsed for symbols and dependencies." />
                <OverviewStat label="Other languages" value={`${overview.data.unsupported_files} files`} detail="Detected and counted, but not analyzed for code relationships." />
                <OverviewStat label="Dependency links" value={overview.data.analysis.dependencies} detail={`${overview.data.confidence.exact ?? 0} exact · ${overview.data.confidence.heuristic ?? 0} heuristic`} />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                <span className="font-semibold">Detected:</span>
                {Object.entries(overview.data.languages).sort((a, b) => b[1] - a[1]).map(([language, count]) => <Badge key={language} value="queued" label={`${language} ${count}`} />)}
                {overview.data.analysis.parse_error_count > 0 && <Badge value="failed" label={`${overview.data.analysis.parse_error_count} parse issues`} />}
              </div>
              {overview.data.spotlight && (
                <button className="mt-4 w-full rounded-xl border border-iris/20 bg-iris-soft/50 p-3 text-left transition hover:bg-iris-soft"
                  onClick={() => { pick(overview.data!.spotlight!.symbol_id); setTab("explorer"); setPanel("impact"); }}>
                  <span className="text-xs font-bold uppercase tracking-wide text-iris-deep">Dependency spotlight · {overview.data.spotlight.links} links</span>
                  <span className="mt-1 block font-semibold">{overview.data.spotlight.qualname}</span>
                  <span className="block text-xs text-slate-500">{overview.data.spotlight.file_path} · Open impact analysis</span>
                </button>
              )}
              {overview.data.analysis.parse_error_count > 0 && (
                <details className="mt-3 text-sm text-slate-600">
                  <summary className="cursor-pointer font-semibold">Review parse issues</summary>
                  <ul className="mt-2 space-y-1">{overview.data.analysis.parse_errors.map((issue) => <li key={`${issue.file}:${issue.error}`}><span className="font-mono">{issue.file}</span>: {issue.error}</li>)}</ul>
                  {overview.data.analysis.parse_error_count > overview.data.analysis.parse_errors.length && <p className="mt-1 text-xs">Showing first {overview.data.analysis.parse_errors.length} of {overview.data.analysis.parse_error_count} issues.</p>}
                </details>
              )}
              <p className="mt-3 text-xs text-slate-500">Exact links resolve through imports or scope. Heuristic links match by name and may be wrong. Impact scores are estimates, not guarantees. Past completed runs remain available in the Jobs tab.</p>
            </>
          )}
        </Card>
      )}
      {ready && tourStep !== null && (
        <Card className="mb-4 border border-iris/20 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-xs font-bold uppercase tracking-wide text-iris-deep">Guided tour · {tourStep + 1} of {tour.length}</p><p className="font-bold">{tour[tourStep].title}</p><p className="text-sm text-slate-600">{tour[tourStep].text}</p></div>
            <div className="flex gap-2"><button className="btn-ghost" onClick={closeTour}>Skip</button><button className="btn-primary" onClick={nextTourStep}>{tourStep === tour.length - 1 ? "Finish" : "Next"}</button></div>
          </div>
        </Card>
      )}
      <div className="mb-4 inline-flex gap-1 rounded-2xl border border-white/90 bg-white/60 p-1 shadow-gloss backdrop-blur" role="tablist">
        {tabs.map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${tab === t ? "bg-white text-iris-deep shadow" : "text-slate-600 hover:text-ink"}`}>{label}</button>
        ))}
      </div>

      {tab === "jobs" && <Card className="p-5"><JobsTable repoId={id} /></Card>}
      {tab !== "jobs" && !ready && (
        <Card>{analyzing ? <div className="p-10 text-center"><Spinner label="Scanning files, parsing code and building the dependency graph…" /></div>
          : <Empty title={status === "failed" ? "The last analysis failed" : "This repository has not been analyzed yet"} hint={status === "failed" ? "Open the Jobs tab to see the error, then try again." : "Run the analysis to index its functions and dependencies."} />}</Card>
      )}

      {ready && tab === "assistant" && <Card className="h-[calc(100vh-230px)] min-h-[480px] overflow-hidden"><Assistant repoId={id} onPick={(sid) => { pick(sid); setTab("explorer"); setPanel("impact"); }} /></Card>}
      {ready && tab === "graph" && (
        <Card className="h-[calc(100vh-230px)] min-h-[520px] overflow-hidden">
          {selected ? <GraphView repoId={id} symbolId={selected.id} symbolName={selected.name} onPick={pick} />
            : <Empty title="Pick a function first" hint="Select a symbol in the Code explorer, then come back to see its graph." />}
        </Card>
      )}
      {ready && tab === "explorer" && (
        <div className="grid h-[calc(100vh-230px)] min-h-[520px] gap-4 lg:grid-cols-[270px_minmax(0,1fr)_400px]">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              <p className="px-2 pb-1 pt-2 text-sm font-bold">Files</p>
              {files.data && <FileTree files={files.data} selected={filePath} onSelect={(p) => { setFilePath(p); }} />}
            </div>
            <div className="flex max-h-[45%] min-h-0 flex-col border-t border-slate-100 p-2">
              <input className="input !py-1.5 text-xs" placeholder="Find a function or class…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter symbols" />
              <ul className="mt-2 min-h-0 flex-1 overflow-y-auto">
                {(filter ? visible : inFile).map((s) => (
                  <li key={s.id}>
                    <button onClick={() => pick(s.id)} className={`w-full truncate rounded-lg px-2 py-1 text-left font-mono text-xs transition hover:bg-white ${selectedId === s.id ? "bg-iris-soft font-semibold text-iris-deep" : "text-slate-700"}`} title={s.qualname}>
                      <span className="mr-1.5 text-slate-400">{s.kind === "class" ? "C" : "ƒ"}</span>{filter ? s.qualname : s.name}{s.route ? "  ·  " + s.route : ""}
                    </button>
                  </li>
                ))}
                {!filter && inFile.length === 0 && <li className="px-2 py-2 text-xs text-slate-500">No symbols in this file.</li>}
              </ul>
            </div>
          </Card>

          <Card className="min-h-0 overflow-hidden">
            {content.data ? <CodePane path={content.data.path} content={content.data.content} selected={selected} />
              : <div className="p-6">{content.error ? <ErrorNote message={content.error} /> : <Empty title="Choose a file" hint="Pick a file on the left to read it here." />}</div>}
          </Card>

          <Card className="flex min-h-0 flex-col overflow-hidden">
            {selected ? (
              <>
                <div className="border-b border-slate-100 p-4">
                  <p className="truncate font-bold" title={selected.qualname}>{selected.name}</p>
                  <p className="truncate font-mono text-xs text-slate-500">{selected.file_path}:{selected.start_line}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {([["explain", "Explain"], ["impact", "Impact analysis"], ["tests", "Generate tests"]] as [Panel, string][]).map(([p, label]) => (
                      <button key={p} onClick={() => setPanel(p)} className={panel === p ? "btn-primary !px-3 !py-1.5" : "btn-ghost !px-3 !py-1.5"}>{label}</button>
                    ))}
                    <button className="btn-ghost !px-3 !py-1.5" onClick={() => setTab("graph")}>Find dependencies</button>
                  </div>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                  {panel === "explain" && <ExplainPanel repoId={id} sym={selected} onPick={pick} />}
                  {panel === "impact" && <ImpactPanel repoId={id} sym={selected} onPick={pick} />}
                  {panel === "tests" && <TestsPanel repoId={id} sym={selected} />}
                </div>
              </>
            ) : <Empty title="Select a function or class" hint="Choose one in the file's symbol list to explain it, trace its impact or generate tests." />}
          </Card>
        </div>
      )}
    </>
  );
}

function OverviewStat({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <div className="glass-flat px-3 py-3"><p className="text-xs font-semibold text-slate-500">{label}</p><p className="mt-1 text-xl font-extrabold text-ink">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div>;
}
