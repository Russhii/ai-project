"""Impact analysis + transparent risk scoring. Purely graph-derived; the LLM is not involved."""
from app.services.graph_service import CodeGraph

RISK_DISCLAIMER = ("This score is a transparent heuristic built from the factors below. "
                   "It is a guide for review effort, not a mathematical guarantee.")


def _label(n: dict) -> str:
    parts = n["qualname"].split(".")
    if n["kind"] == "method":
        return ".".join(parts[-2:])
    return n["qualname"] if n["kind"] == "module" else parts[-1]


def _points(value: int, steps: list[tuple[int, int]]) -> int:
    """steps: ascending (threshold, points). Returns points of the highest threshold reached."""
    pts = 0
    for threshold, p in steps:
        if value >= threshold:
            pts = p
    return pts


def score_risk(target: dict, dependents: int, files: int, apis: int, tests: int, max_depth: int, db_touched: bool, target_db: bool) -> dict:
    factors = [
        {"factor": "Dependents", "value": dependents,
         "points": _points(dependents, [(1, 1), (4, 2), (11, 3)]),
         "explanation": f"{dependents} functions/classes depend on this directly or indirectly"},
        {"factor": "Affected files", "value": files,
         "points": _points(files, [(2, 1), (4, 2), (8, 3)]),
         "explanation": f"changes could ripple through {files} file(s)"},
        {"factor": "API exposure", "value": apis,
         "points": _points(apis, [(1, 2), (2, 3)]),
         "explanation": f"{apis} HTTP endpoint(s) reach this code"},
        {"factor": "Database interaction", "value": int(db_touched),
         "points": 2 if target_db else (1 if db_touched else 0),
         "explanation": "this code talks to a database" if target_db else
         ("affected code talks to a database" if db_touched else "no database access detected")},
        {"factor": "Test coverage", "value": tests,
         "points": 3 if tests == 0 else (1 if tests < 3 else 0),
         "explanation": "no test reaches this code" if tests == 0 else f"{tests} test(s) reach this code"},
        {"factor": "Dependency depth", "value": max_depth,
         "points": 2 if max_depth >= 4 else (1 if max_depth >= 2 else 0),
         "explanation": f"the longest chain of dependents is {max_depth} level(s) deep"},
    ]
    total = sum(f["points"] for f in factors)
    level = "LOW" if total <= 3 else "MEDIUM" if total <= 7 else "HIGH" if total <= 11 else "CRITICAL"
    return {"level": level, "score": total, "max_score": 17, "factors": factors, "disclaimer": RISK_DISCLAIMER}


def analyze_impact(cg: CodeGraph, target_id: int) -> dict:
    target = cg.node(target_id)
    seeds = cg.contained(target_id) if target["kind"] in ("class", "module") else [target_id]
    depth, pred = cg.dependents(seeds)
    for s in seeds:
        depth.pop(s, None)

    nodes = {n: cg.node(n) for n in depth}
    code_nodes = {n: d for n, d in nodes.items() if d["kind"] != "module" or target["kind"] == "module"}
    tests = {n: d for n, d in code_nodes.items() if d["meta"].get("is_test")}
    prod = {n: d for n, d in code_nodes.items() if n not in tests and d["kind"] in ("function", "method", "class", "module")}
    apis = {n: d for n, d in prod.items() if d["meta"].get("route")}
    seed_nodes = [cg.node(s) for s in seeds]
    files = sorted({d["file_path"] for d in [*prod.values(), target]})
    max_depth = max((depth[n] for n in prod), default=0)

    def path_to(n: int) -> list[dict]:
        chain = [n]
        while chain[-1] in pred:
            chain.append(pred[chain[-1]])
        out = []
        for i, nid in enumerate(chain):
            info = cg.node(nid)
            heuristic = i > 0 and cg.g.edges[(chain[i - 1], nid)]["confidence"] == "heuristic"
            out.append({"id": nid, "label": _label(info), "kind": info["kind"], "file_path": info["file_path"],
                        "heuristic_link": heuristic})
        return out

    risk = score_risk(
        target, len(prod), len(files), len(apis), len(tests), max_depth,
        db_touched=any(d["meta"].get("db_access") for d in [*prod.values(), *seed_nodes]),
        target_db=any(d["meta"].get("db_access") for d in seed_nodes))

    def brief(n: int, d: dict) -> dict:
        return {"id": n, "name": _label(d), "kind": d["kind"], "file_path": d["file_path"],
                "start_line": d["start_line"], "depth": depth[n], "route": d["meta"].get("route")}

    ordered = lambda items: sorted((brief(n, d) for n, d in items.items()), key=lambda x: (x["depth"], x["name"]))
    direct = [b for b in ordered(prod) if b["depth"] == 1]
    reason = _reason(target, direct, apis, len(prod), len(files), len(tests))
    return {
        "target": {"id": target_id, "name": _label(target), "kind": target["kind"], "file_path": target["file_path"]},
        "risk": risk,
        "summary": {"affected_files": len(files), "affected_functions": len(prod), "affected_apis": len(apis),
                    "related_tests": len(tests), "max_depth": max_depth},
        "direct_dependents": direct,
        "affected_functions": ordered(prod),
        "affected_files": files,
        "affected_apis": ordered(apis),
        "related_tests": ordered(tests),
        "dependency_paths": [path_to(n) for n in list(apis)[:10]] or [path_to(n["id"]) for n in direct[:5]],
        "reason": reason,
    }


def _reason(target: dict, direct: list[dict], apis: dict, n_prod: int, n_files: int, n_tests: int) -> str:
    name = _label(target)
    if not n_prod and not n_tests:
        return f"Nothing in the analyzed code depends on {name}, so changing it has no detected effect on other code."
    if direct:
        first = f"{name} is used directly by {', '.join(d['name'] for d in direct[:4])}" + (" and others" if len(direct) > 4 else "")
        if apis:
            first += ", and the change reaches " + ", ".join(sorted(d["meta"]["route"] for d in apis.values()))
        first += "."
    else:
        first = f"{name} is only reached through tests."
    return f"{first} In total {n_prod} function(s) in {n_files} file(s) are affected, and {n_tests} test(s) exercise this code."
