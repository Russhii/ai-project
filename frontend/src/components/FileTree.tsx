import { useMemo, useState } from "react";
import type { FileInfo } from "../api";

interface Node { name: string; path: string; children: Map<string, Node>; file?: FileInfo }

function build(files: FileInfo[]): Node {
  const root: Node = { name: "", path: "", children: new Map() };
  for (const f of files) {
    let cur = root;
    f.path.split("/").forEach((part, i, arr) => {
      const path = arr.slice(0, i + 1).join("/");
      if (!cur.children.has(part)) cur.children.set(part, { name: part, path, children: new Map() });
      cur = cur.children.get(part)!;
      if (i === arr.length - 1) cur.file = f;
    });
  }
  return root;
}

function Row({ node, depth, selected, onSelect }: { node: Node; depth: number; selected: string | null; onSelect: (p: string) => void }) {
  const [open, setOpen] = useState(depth < 1);
  const isDir = !node.file;
  const kids = [...node.children.values()].sort((a, b) => Number(!!a.file) - Number(!!b.file) || a.name.localeCompare(b.name));
  return (
    <li>
      <button
        onClick={() => (isDir ? setOpen(!open) : onSelect(node.path))}
        className={`flex w-full items-center gap-1.5 rounded-lg py-1 pr-2 text-left text-[13px] transition hover:bg-white ${selected === node.path ? "bg-iris-soft font-semibold text-iris-deep" : "text-slate-700"}`}
        style={{ paddingLeft: 8 + depth * 14 }}
      >
        <span className="w-3 text-slate-400">{isDir ? (open ? "▾" : "▸") : ""}</span>
        <span className="truncate">{node.name}</span>
      </button>
      {isDir && open && <ul>{kids.map((k) => <Row key={k.path} node={k} depth={depth + 1} selected={selected} onSelect={onSelect} />)}</ul>}
    </li>
  );
}

export default function FileTree({ files, selected, onSelect }: { files: FileInfo[]; selected: string | null; onSelect: (p: string) => void }) {
  const root = useMemo(() => build(files), [files]);
  const top = [...root.children.values()].sort((a, b) => Number(!!a.file) - Number(!!b.file) || a.name.localeCompare(b.name));
  return <ul>{top.map((n) => <Row key={n.path} node={n} depth={0} selected={selected} onSelect={onSelect} />)}</ul>;
}
