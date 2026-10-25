import { api } from "../api";
import { Badge, Card, Empty, ErrorNote, PageTitle, timeAgo } from "../components/ui";
import { useLoad } from "../hooks";

export function JobsTable({ repoId }: { repoId?: number }) {
  const jobs = useLoad(() => api.jobs(repoId), [repoId], 3000);
  const rows = jobs.data ?? [];
  if (jobs.error) return <ErrorNote message={jobs.error} />;
  if (!rows.length) return <Empty title="No jobs yet" hint="Start an analysis from a repository page." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-slate-500"><tr><th className="py-2 pr-4 font-semibold">Job</th><th className="pr-4 font-semibold">Status</th><th className="pr-4 font-semibold">Progress</th><th className="pr-4 font-semibold">Result</th><th className="font-semibold">Started</th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((j) => (
            <tr key={j.id} className="align-top">
              <td className="py-3 pr-4"><p className="font-semibold">{j.kind}</p><p className="font-mono text-xs text-slate-400">{j.id.slice(0, 8)}</p></td>
              <td className="pr-4"><Badge value={j.status} /></td>
              <td className="pr-4 text-slate-600">{j.error ?? j.message}</td>
              <td className="pr-4 text-slate-600">{j.result ? `${j.result.files} files, ${j.result.symbols} symbols, ${j.result.dependencies} links` : "–"}</td>
              <td className="text-slate-500">{timeAgo(j.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Jobs() {
  return (
    <>
      <PageTitle title="Analysis jobs" sub="Heavy work runs in the background. Each job moves through queued, running, then completed or failed." />
      <Card className="p-5"><JobsTable /></Card>
    </>
  );
}
