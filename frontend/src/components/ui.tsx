import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass ${className}`}>{children}</div>;
}

const TONES: Record<string, string> = {
  queued: "bg-slate-100 text-slate-600", running: "bg-sky-50 text-sky-700", analyzing: "bg-sky-50 text-sky-700",
  completed: "bg-emerald-50 text-emerald-700", analyzed: "bg-emerald-50 text-emerald-700", passed: "bg-emerald-50 text-emerald-700",
  cloned: "bg-slate-100 text-slate-600", generated: "bg-slate-100 text-slate-600",
  failed: "bg-rose-50 text-rose-700", error: "bg-rose-50 text-rose-700", timeout: "bg-amber-50 text-amber-700", blocked: "bg-amber-50 text-amber-700",
  LOW: "bg-emerald-50 text-emerald-700", MEDIUM: "bg-amber-50 text-amber-700", HIGH: "bg-orange-50 text-orange-700", CRITICAL: "bg-rose-50 text-rose-700",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[value] ?? "bg-slate-100 text-slate-600"}`}>
      {label ?? value}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-iris/30 border-t-iris" />
      {label}
    </span>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50/80 px-3 py-2 text-sm text-rose-700">{message}</p>;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="px-6 py-10 text-center">
      <p className="font-semibold text-ink">{title}</p>
      {hint && <p className="mt-1 text-sm text-slate-500">{hint}</p>}
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="glass-flat px-4 py-3">
      <p className="text-2xl font-extrabold tracking-tight text-ink">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

export function PageTitle({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-sm text-slate-500">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function timeAgo(iso: string): string {
  const utc = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`; // API timestamps are UTC
  const s = Math.max(0, (Date.now() - new Date(utc).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
