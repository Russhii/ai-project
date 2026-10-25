"""Deterministic Python source analysis using the standard-library `ast` module.

No LLM is involved here. We extract structure (modules, classes, functions, methods),
decorators, parameters, return annotations, imports and raw call expressions.
(Tree-sitter would slot in behind the same `parse_python_file` interface for other languages.)
"""
import ast
import re
from dataclasses import dataclass, field

ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "route", "head", "options"}
_ROUTE_RE = re.compile(r"^[\w.]+\.(get|post|put|delete|patch|route|head|options)\((.*)\)$", re.S)
DB_HINTS = ("execute", "commit", "cursor", "query", "session.", "objects.", "executemany", "fetchall", "fetchone")
IO_HINTS = ("open", "write", "read_text", "write_text", "requests.", "httpx.", "urlopen", "subprocess", "os.remove", "shutil")
DB_LIBS = ("sqlalchemy", "sqlite3", "psycopg2", "pymysql", "django.db", "pymongo", "peewee")


@dataclass
class ParsedSymbol:
    qualname: str
    name: str
    kind: str  # module | class | function | method
    start_line: int
    end_line: int
    parent_qualname: str | None = None
    meta: dict = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)  # raw dotted call names, e.g. "self.payment.process_payment"
    bases: list[str] = field(default_factory=list)


@dataclass
class ParsedFile:
    path: str
    module: str
    symbols: list[ParsedSymbol]
    imports: dict[str, str]  # local alias -> fully qualified target
    error: str | None = None


def module_name(path: str) -> str:
    parts = path[:-3].split("/") if path.endswith(".py") else path.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "__init__"


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr  # f().g() -> "g"
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return None


def _unparse(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _params(args: ast.arguments) -> list[str]:
    out = []
    for a in [*args.posonlyargs, *args.args]:
        out.append(f"{a.arg}: {_unparse(a.annotation)}" if a.annotation else a.arg)
    if args.vararg:
        out.append("*" + args.vararg.arg)
    for a in args.kwonlyargs:
        out.append(f"{a.arg}: {_unparse(a.annotation)}" if a.annotation else a.arg)
    if args.kwarg:
        out.append("**" + args.kwarg.arg)
    return out


def _route_of(decorators: list[str]) -> str | None:
    for dec in decorators:
        m = _ROUTE_RE.match(dec)
        if not m:
            continue
        verb = m.group(1).upper()
        first = re.search(r"""['"]([^'"]*)['"]""", m.group(2))
        if first:
            return f"{'ANY' if verb == 'ROUTE' else verb} {first.group(1)}"
    return None


def _collect_calls(fn: ast.AST) -> list[str]:
    calls: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name:
                calls.append(name)
    return calls


def _is_test_path(path: str) -> bool:
    low = path.lower()
    name = low.rsplit("/", 1)[-1]
    return "/tests/" in f"/{low}" or "/test/" in f"/{low}" or name.startswith("test_") or name.endswith("_test.py")


def parse_python_file(path: str, source: str) -> ParsedFile:
    mod = module_name(path)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        return ParsedFile(path, mod, [], {}, error=f"{type(exc).__name__}: {exc}")

    imports: dict[str, str] = {}
    pkg = mod if path.endswith("__init__.py") else mod.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    imports[a.asname] = a.name
                else:
                    top = a.name.split(".")[0]
                    imports[top] = top
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = pkg.split(".") if pkg else []
                parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
                base = ".".join([*parts, base]) if base else ".".join(parts)
            for a in node.names:
                imports[a.asname or a.name] = f"{base}.{a.name}" if base else a.name

    is_test_file = _is_test_path(path)
    uses_db_lib = any(t.split(".")[0] in DB_LIBS or t.startswith(DB_LIBS) for t in imports.values())
    total_lines = source.count("\n") + 1
    symbols: list[ParsedSymbol] = [ParsedSymbol(
        mod, mod.rsplit(".", 1)[-1], "module", 1, total_lines,
        meta={"docstring": ast.get_docstring(tree), "is_test": is_test_file, "db_import": uses_db_lib,
              "imports": sorted(set(imports.values()))})]

    def visit(body: list[ast.stmt], parent: str, parent_kind: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                q = f"{parent}.{node.name}"
                sym = ParsedSymbol(q, node.name, "class", node.lineno, node.end_lineno or node.lineno, parent,
                                   meta={"decorators": [ast.unparse(d) for d in node.decorator_list],
                                         "docstring": ast.get_docstring(node), "is_test": is_test_file},
                                   bases=[b for b in (_dotted(x) for x in node.bases) if b])
                symbols.append(sym)
                visit(node.body, q, "class")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{parent}.{node.name}"
                decs = [ast.unparse(d) for d in node.decorator_list]
                calls = _collect_calls(node)
                route = _route_of(decs)
                sym = ParsedSymbol(
                    q, node.name, "method" if parent_kind == "class" else "function", node.lineno,
                    node.end_lineno or node.lineno, parent, calls=calls,
                    meta={"params": _params(node.args), "returns": _unparse(node.returns), "decorators": decs,
                          "docstring": ast.get_docstring(node), "route": route, "async": isinstance(node, ast.AsyncFunctionDef),
                          "is_test": is_test_file and node.name.startswith("test"),
                          "db_access": any(h in c for c in calls for h in DB_HINTS),
                          "io_access": any(c.startswith(h) or f".{h}" in c for c in calls for h in IO_HINTS)})
                symbols.append(sym)
                # nested defs are attributed to their enclosing function's calls; not separate symbols
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                for block in (getattr(node, "body", []), getattr(node, "orelse", []), getattr(node, "finalbody", [])):
                    visit(block, parent, parent_kind)

    visit(tree.body, mod, "module")
    return ParsedFile(path, mod, symbols, imports)
