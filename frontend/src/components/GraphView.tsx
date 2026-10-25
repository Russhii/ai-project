import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";
import { api, type Graph } from "../api";
import { useLoad } from "../hooks";
import { ErrorNote, Spinner } from "./ui";

function layout(g: Graph): { nodes: Node[]; edges: Edge[] } {
  const byDepth = new Map<number, Graph["nodes"]>();
  g.nodes.forEach((n) => byDepth.set(n.depth, [...(byDepth.get(n.depth) ?? []), n]));
  const nodes: Node[] = [];
  for (const [depth, list] of byDepth) {
    list.sort((a, b) => a.qualname.localeCompare(b.qualname));
    list.forEach((n, i) => {
      const center = n.depth === 0;
      const isTest = !!n.meta.is_test;
      const isApi = !!n.meta.route;
      nodes.push({
        id: String(n.id), position: { x: depth * 300, y: (i - (list.length - 1) / 2) * 96 },
        data: { label: `${n.kind === "method" ? n.qualname.split(".").slice(-2).join(".") : n.name}${isApi ? `\n${n.meta.route}` : ""}` },
        style: {
          width: 230, whiteSpace: "pre-line", fontSize: 12, fontWeight: 600, borderRadius: 16, padding: 10,
          color: center ? "#fff" : "#14182b",
          border: center ? "1px solid #4338ca" : isApi ? "1px solid #7dd3fc" : isTest ? "1px solid #86efac" : "1px solid #e2e8f0",
          background: center ? "linear-gradient(180deg,#7b78ee,#4f4fc9)" : isApi ? "linear-gradient(180deg,#fff,#e0f2fe)" : isTest ? "linear-gradient(180deg,#fff,#dcfce7)" : "linear-gradient(180deg,#fff,#f1f5f9)",
          boxShadow: "0 1px 0 rgba(255,255,255,.9) inset, 0 8px 20px -10px rgba(52,58,120,.35)",
        },
      });
    });
  }
  const edges: Edge[] = g.edges.map((e, i) => ({
    id: `e${i}`, source: String(e.source), target: String(e.target), markerEnd: { type: MarkerType.ArrowClosed, color: "#8b8fb8" },
    style: { stroke: "#8b8fb8", strokeDasharray: e.confidence === "heuristic" ? "5 4" : undefined }, label: e.kind === "calls" ? undefined : e.kind,
  }));
  return { nodes, edges };
}

export default function GraphView({ repoId, symbolId, symbolName, onPick }: { repoId: number; symbolId: number; symbolName: string; onPick: (id: number) => void }) {
  const [up, setUp] = useState(2);
  const [down, setDown] = useState(2);
  const { data, error, loading } = useLoad(() => api.graph(repoId, symbolId, up, down), [repoId, symbolId, up, down]);
  const flow = useMemo(() => (data ? layout(data) : null), [data]);
  const sel = (v: number, set: (n: number) => void, label: string) => (
    <label className="flex items-center gap-2 text-sm text-slate-600">{label}
      <select className="input !w-auto !py-1.5" value={v} onChange={(e) => set(Number(e.target.value))}>{[0, 1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}</select>
    </label>
  );
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-4 border-b border-slate-100 px-5 py-3">
        <p className="font-bold">Dependency graph for <span className="font-mono text-iris-deep">{symbolName}</span></p>
        {sel(up, setUp, "Callers levels")}{sel(down, setDown, "Callees levels")}
        <p className="ml-auto text-xs text-slate-500">Left: code that depends on it. Right: what it uses. Dashed = matched by name only.</p>
      </div>
      <div className="relative min-h-[460px] flex-1">
        {loading && <div className="absolute left-5 top-4 z-10"><Spinner label="Loading graph…" /></div>}
        {error && <div className="p-5"><ErrorNote message={error} /></div>}
        {flow && (
          <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView fitViewOptions={{ padding: 0.25 }} nodesConnectable={false}
            onNodeClick={(_, n) => onPick(Number(n.id))} proOptions={{ hideAttribution: true }}>
            <Background color="#dfe4f1" gap={22} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
