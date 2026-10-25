import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Badge, Card, Empty, ErrorNote, PageTitle, Stat, timeAgo } from "../components/ui";
import { useAction, useLoad } from "../hooks";

export default function Dashboard() {
  const nav = useNavigate();
  const repos = useLoad(api.repos, [], 8000);
  const jobs = useLoad(() => api.jobs(), [], 4000);
  const demo = useAction(api.addDemo);
  const list = repos.data ?? [];
  const symbols = list.reduce((n, r) => n + r.symbol_count, 0);

  const loadDemo = async () => {
    const r = await demo.run();
    if (!r) return;
    await api.analyze(r.id);
    nav(`/repositories/${r.id}`);
  };

  return (
    <>
      <PageTitle
        title="Understand legacy code before you change it"
        sub="Analyze a public GitHub repository or explore the sample project. Python code gets symbol and dependency analysis; other languages are detected and counted."
        right={<div className="flex flex-wrap gap-2"><button className="btn-primary" onClick={() => nav("/repositories")}>Add a repository</button><button className="btn-ghost" onClick={loadDemo} disabled={demo.busy}>{demo.busy ? "Loading sample…" : "Explore sample project"}</button></div>}
      />
      <ErrorNote message={demo.error ?? repos.error} />
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Repositories" value={list.length} />
        <Stat label="Analyzed" value={list.filter((r) => r.status === "analyzed").length} />
        <Stat label="Symbols indexed" value={symbols} />
        <Stat label="Jobs run" value={jobs.data?.length ?? 0} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 text-lg font-bold">Repositories</h2>
          {list.length === 0 ? <Empty title="Start with any public GitHub repository" hint="Or explore the bundled sample project to learn the workflow." /> : (
            <ul className="divide-y divide-slate-100">
              {list.slice(0, 6).map((r) => (
                <li key={r.id}>
                  <button className="flex w-full items-center justify-between py-3 text-left hover:text-iris-deep" onClick={() => nav(`/repositories/${r.id}`)}>
                    <span><span className="font-semibold">{r.name}</span><span className="ml-2 text-xs text-slate-500">{r.symbol_count} symbols</span></span>
                    <Badge value={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 text-lg font-bold">Recent analysis jobs</h2>
          {(jobs.data ?? []).length === 0 ? <Empty title="No jobs yet" hint="Jobs appear when you analyze a repository." /> : (
            <ul className="divide-y divide-slate-100">
              {(jobs.data ?? []).slice(0, 6).map((j) => (
                <li key={j.id} className="flex items-center justify-between py-3 text-sm">
                  <span><span className="font-semibold">{j.kind}</span><span className="ml-2 text-slate-500">{j.message} · {timeAgo(j.created_at)}</span></span>
                  <Badge value={j.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
