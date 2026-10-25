"""Turn parsed symbols into dependency edges (deterministic, name-resolution based).

Edge kinds: calls, imports, inherits, contains.
Confidence: "exact" when the target is resolved through imports / self / module scope;
"heuristic" when we only matched an attribute-call name (e.g. `svc.process_payment()`)
to a unique-ish method elsewhere in the repository. Heuristic edges are always labelled.
"""
from collections import defaultdict

from app.services.parser import ParsedFile

# attribute names that are almost always builtin/stdlib methods; never guess these
_COMMON = {"get", "append", "items", "keys", "values", "update", "pop", "join", "format", "split", "strip",
           "add", "remove", "read", "write", "close", "open", "extend", "copy", "clear", "lower", "upper",
           "startswith", "endswith", "encode", "decode", "info", "debug", "warning", "error", "exception",
           "commit", "execute", "run", "send", "save", "delete", "put", "post", "count", "index", "sort"}
MAX_HEURISTIC_CANDIDATES = 3

Edge = tuple[str, str, str, str]  # (source_qualname, target_qualname, kind, confidence)


def build_edges(parsed: list[ParsedFile]) -> list[Edge]:
    by_qual = {s.qualname: s for pf in parsed for s in pf.symbols}
    modules = {pf.module for pf in parsed}
    imports_by_mod = {pf.module: pf.imports for pf in parsed}
    by_name: dict[str, list[str]] = defaultdict(list)
    for q, s in by_qual.items():
        if s.kind in ("function", "method", "class"):
            by_name[s.name].append(q)

    edges: dict[tuple[str, str, str], str] = {}

    def add(src: str, tgt: str, kind: str, conf: str = "exact") -> None:
        if src != tgt and (src, tgt, kind) not in edges:
            edges[(src, tgt, kind)] = conf

    def lookup(full: str, depth: int = 0) -> str | None:
        """Find a symbol by qualified name, following `from x import y` re-exports a few hops."""
        if full in by_qual:
            return full
        if depth > 3:
            return None
        parts = full.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in imports_by_mod and parts[i] in imports_by_mod[prefix]:
                nxt = ".".join([imports_by_mod[prefix][parts[i]], *parts[i + 1:]])
                if nxt != full:
                    return lookup(nxt, depth + 1)
        return None

    def to_module(target: str) -> str | None:
        if target in modules:
            return target
        head = target.rpartition(".")[0]
        while head:
            if head in modules:
                return head
            head = head.rpartition(".")[0]
        return None

    for pf in parsed:
        imports = pf.imports
        for s in pf.symbols:
            if s.parent_qualname and s.parent_qualname in by_qual:
                add(s.parent_qualname, s.qualname, "contains")
            if s.kind == "module":
                for target in imports.values():
                    m = to_module(target)
                    if m:
                        add(s.qualname, m, "imports")
            elif s.kind == "class":
                for base in s.bases:
                    head, _, rest = base.partition(".")
                    full = ".".join([imports[head], *([rest] if rest else [])]) if head in imports else f"{pf.module}.{base}"
                    tgt = lookup(full)
                    if tgt and by_qual[tgt].kind == "class":
                        add(s.qualname, tgt, "inherits")
            else:
                for call in s.calls:
                    _resolve_call(call, s, pf, by_qual, by_name, imports, lookup, add)
    return [(a, b, k, c) for (a, b, k), c in edges.items()]


def _resolve_call(call, sym, pf, by_qual, by_name, imports, lookup, add) -> None:
    parts = call.split(".")
    head = parts[0]
    target: str | None = None

    if head in ("self", "cls") and sym.kind == "method" and len(parts) == 2:
        cand = f"{sym.parent_qualname}.{parts[1]}"
        target = cand if cand in by_qual else None
    elif head in imports:
        target = lookup(".".join([imports[head], *parts[1:]]))
    else:
        target = lookup(f"{pf.module}.{call}")

    if target:
        add(sym.qualname, target, "calls")
        tsym = by_qual[target]
        if tsym.kind == "class":  # instantiation also runs __init__
            init = f"{target}.__init__"
            if init in by_qual:
                add(sym.qualname, init, "calls")
        return

    last = parts[-1]
    if len(parts) > 1 and last not in _COMMON and not last.startswith("__"):
        cands = [q for q in by_name.get(last, []) if q != sym.qualname]
        if 1 <= len(cands) <= MAX_HEURISTIC_CANDIDATES:
            for q in cands:
                add(sym.qualname, q, "calls", "heuristic")
