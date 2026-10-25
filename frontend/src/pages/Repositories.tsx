import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Badge, Card, Empty, ErrorNote, PageTitle, timeAgo } from "../components/ui";
import { useAction, useLoad } from "../hooks";

export default function Repositories() {
  const nav = useNavigate();
  const repos = useLoad(api.repos, [], 6000);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const add = useAction(api.addRepo);
  const demo = useAction(api.addDemo);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await add.run(url.trim(), name.trim());
    if (r) {
      await api.analyze(r.id);
      nav(`/repositories/${r.id}`);
    }
  };
  const suggest = (u: string) => {
    setUrl(u);
    if (!name) setName(u.split("/").filter(Boolean).pop()?.replace(/\.git$/, "") ?? "");
  };

  return (
    <>
      <PageTitle title="Repositories" sub="Public GitHub repositories are cloned (shallow) into the server's repositories folder, then analyzed in the background." />
      <Card className="mb-6 p-5">
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-[2fr_1fr_auto]">
          <input className="input" placeholder="https://github.com/owner/repository" value={url} onChange={(e) => suggest(e.target.value)} required aria-label="Repository URL" />
          <input className="input" placeholder="Name (letters, digits, - _ .)" value={name} onChange={(e) => setName(e.target.value)} required aria-label="Repository name" />
          <button className="btn-primary" disabled={add.busy}>{add.busy ? "Cloning…" : "Clone and analyze"}</button>
        </form>
        <div className="mt-3 flex items-center gap-3">
          <ErrorNote message={add.error ?? demo.error} />
          <button className="btn-ghost ml-auto" disabled={demo.busy} onClick={async () => { const r = await demo.run(); if (r) { await api.analyze(r.id); nav(`/repositories/${r.id}`); } }}>
            Use the bundled demo shop
          </button>
        </div>
      </Card>
      <ErrorNote message={repos.error} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(repos.data ?? []).map((r) => (
          <button key={r.id} onClick={() => nav(`/repositories/${r.id}`)} className="glass p-5 text-left transition hover:-translate-y-0.5 hover:shadow-lift">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-lg font-bold">{r.name}</h3>
              <Badge value={r.status} />
            </div>
            <p className="mt-1 truncate text-xs text-slate-500">{r.url}</p>
            <p className="mt-4 text-sm text-slate-600">{r.file_count} files · {r.symbol_count} symbols</p>
            <p className="text-xs text-slate-400">Added {timeAgo(r.created_at)}</p>
          </button>
        ))}
      </div>
      {!repos.loading && (repos.data ?? []).length === 0 && <Card><Empty title="Nothing here yet" hint="Paste a GitHub URL above to add your first repository." /></Card>}
    </>
  );
}
