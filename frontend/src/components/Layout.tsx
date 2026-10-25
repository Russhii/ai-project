import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/repositories", label: "Repositories" },
  { to: "/jobs", label: "Analysis jobs" },
];

export default function Layout({ children, onSignOut }: { children: ReactNode; onSignOut: () => void }) {
  const health = useLoad(api.health, [], 15000);
  const h = health.data;
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 p-4 md:block">
        <div className="glass flex h-full flex-col p-5">
          <div className="mb-8 flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-2xl text-lg font-extrabold text-white"
              style={{ background: "linear-gradient(160deg,#8f8cf5,#4f4fc9)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.5), 0 8px 18px -8px rgba(79,70,229,.7)" }}>L</div>
            <div className="leading-tight">
              <p className="font-extrabold text-ink">Legacy Code</p>
              <p className="text-xs text-slate-500">Intelligence</p>
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) => `rounded-xl px-3 py-2.5 text-sm font-semibold transition ${isActive ? "bg-iris-soft text-iris-deep shadow-sm" : "text-slate-600 hover:bg-white hover:text-ink"}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <button type="button" className="btn-ghost mt-3 w-full" onClick={onSignOut}>Sign out</button>
          <div className="mt-auto space-y-2 text-xs text-slate-500">
            <div className="glass-flat px-3 py-2">
              <p className="font-semibold text-ink">{h ? "API connected" : health.error ? "API offline" : "Connecting…"}</p>
              {h && <p>AI provider: {h.llm_provider === "none" ? "off (static analysis)" : h.llm_provider}</p>}
              {h && <p>Docker sandbox: {h.docker ? "ready" : "not available"}</p>}
              {!h && health.error && <p className="text-rose-600">Start the backend on port 8000.</p>}
            </div>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:py-4 md:pl-0 md:pr-6">
        <div className="mx-auto max-w-[1500px] px-2 py-4 md:px-4">{children}</div>
      </main>
    </div>
  );
}
