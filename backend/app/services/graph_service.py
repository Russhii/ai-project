"""NetworkX graph built from the stored dependency rows. All graph questions go through here."""
from collections import deque
from dataclasses import dataclass

import networkx as nx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Dependency, Symbol
from app.services.errors import NotFound

WALK_KINDS = {"calls", "inherits", "imports"}
_cache: dict[int, tuple[tuple, "CodeGraph"]] = {}


@dataclass
class CodeGraph:
    g: nx.DiGraph

    def node(self, sid: int) -> dict:
        if sid not in self.g:
            raise NotFound("Symbol not found in the dependency graph")
        d = self.g.nodes[sid]
        return {"id": sid, **d}

    def _walk(self, start: list[int], reverse: bool, max_depth: int | None, kinds: set[str]) -> tuple[dict[int, int], dict[int, int]]:
        """BFS. Returns (depth by node, predecessor by node) so callers can rebuild a path."""
        depth = {s: 0 for s in start}
        pred: dict[int, int] = {}
        queue = deque(start)
        while queue:
            cur = queue.popleft()
            if max_depth is not None and depth[cur] >= max_depth:
                continue
            nbrs = self.g.predecessors(cur) if reverse else self.g.successors(cur)
            for nxt in nbrs:
                edge = self.g.edges[(nxt, cur) if reverse else (cur, nxt)]
                if edge["kind"] in kinds and nxt not in depth:
                    depth[nxt] = depth[cur] + 1
                    pred[nxt] = cur
                    queue.append(nxt)
        return depth, pred

    def dependents(self, start: list[int], max_depth: int | None = None):
        """Who depends on `start` (reverse traversal)."""
        return self._walk(start, True, max_depth, WALK_KINDS)

    def dependencies(self, start: list[int], max_depth: int | None = None):
        """What `start` depends on (forward traversal)."""
        return self._walk(start, False, max_depth, WALK_KINDS)

    def direct(self, sid: int, reverse: bool) -> list[dict]:
        nbrs = self.g.predecessors(sid) if reverse else self.g.successors(sid)
        out = []
        for n in nbrs:
            e = self.g.edges[(n, sid) if reverse else (sid, n)]
            if e["kind"] in WALK_KINDS:
                out.append({**self.node(n), "edge_kind": e["kind"], "confidence": e["confidence"]})
        return sorted(out, key=lambda x: x["qualname"])

    def contained(self, sid: int) -> list[int]:
        """The symbol plus everything it contains (a class's methods, a module's contents)."""
        seen, stack = {sid}, [sid]
        while stack:
            cur = stack.pop()
            for n in self.g.successors(cur):
                if self.g.edges[(cur, n)]["kind"] == "contains" and n not in seen:
                    seen.add(n)
                    stack.append(n)
        return list(seen)

    def neighborhood(self, center: int, up: int, down: int) -> dict:
        """Nodes/edges within `up` levels of callers and `down` levels of callees."""
        up_d, _ = self.dependents([center], up)
        down_d, _ = self.dependencies([center], down)
        depths = {**{n: -d for n, d in up_d.items()}, **down_d}
        depths[center] = 0
        nodes = [{**self.node(n), "depth": d} for n, d in depths.items()]
        edges = []
        for a, b, data in self.g.edges(data=True):
            if a in depths and b in depths and data["kind"] in WALK_KINDS:
                edges.append({"source": a, "target": b, "kind": data["kind"], "confidence": data["confidence"]})
        return {"nodes": nodes, "edges": edges}


def _fingerprint(db: Session, repo_id: int) -> tuple:
    deps = db.execute(select(func.count(Dependency.id), func.max(Dependency.id)).where(Dependency.repository_id == repo_id)).one()
    syms = db.execute(select(func.count(Symbol.id), func.max(Symbol.id)).where(Symbol.repository_id == repo_id)).one()
    return (*deps, *syms)


def get_graph(db: Session, repo_id: int) -> CodeGraph:
    fp = _fingerprint(db, repo_id)
    cached = _cache.get(repo_id)
    if cached and cached[0] == fp:
        return cached[1]
    g = nx.DiGraph()
    for s in db.scalars(select(Symbol).where(Symbol.repository_id == repo_id)):
        g.add_node(s.id, qualname=s.qualname, name=s.name, kind=s.kind, file_path=s.file_path,
                   start_line=s.start_line, end_line=s.end_line, meta=s.meta or {})
    for d in db.scalars(select(Dependency).where(Dependency.repository_id == repo_id)):
        g.add_edge(d.source_id, d.target_id, kind=d.kind, confidence=d.confidence)
    graph = CodeGraph(g)
    _cache[repo_id] = (fp, graph)
    return graph
