"""LLM-assisted understanding: explain a symbol, answer questions, draft tests.

Pattern everywhere: deterministic FACTS come from the parser/graph; the LLM only adds clearly
labelled INFERENCES. With no provider configured we return the facts alone.
"""
import ast
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Repository, Symbol, TestCase
from app.services import retrieval
from app.services.graph_service import get_graph
from app.services.llm_gateway import SAFETY_RULES, LLMError, gateway
from app.services.redact import redact_secrets
from app.services.source_reader import symbol_source

log = logging.getLogger(__name__)

SIDE_EFFECT_HINTS = {"db_access": "Reads or writes a database", "io_access": "Performs file, network or process I/O"}


def _label(n: dict) -> str:
    return n["qualname"]


def build_facts(db: Session, repo: Repository, sym: Symbol) -> dict:
    cg = get_graph(db, repo.id)
    meta = sym.meta or {}
    callers = [d for d in cg.direct(sym.id, reverse=True)]
    callees = [d for d in cg.direct(sym.id, reverse=False)]
    effects = [text for key, text in SIDE_EFFECT_HINTS.items() if meta.get(key)]
    if meta.get("route"):
        effects.append(f"Exposed as HTTP endpoint {meta['route']}")
    brief = lambda xs: [{"id": x["id"], "name": _label(x), "file_path": x["file_path"], "confidence": x["confidence"]} for x in xs]
    return {
        "qualname": sym.qualname, "kind": sym.kind, "file_path": sym.file_path,
        "lines": [sym.start_line, sym.end_line], "parameters": meta.get("params", []),
        "returns": meta.get("returns"), "decorators": meta.get("decorators", []),
        "docstring": meta.get("docstring"), "route": meta.get("route"),
        "calls": brief([c for c in callees if c["edge_kind"] == "calls"]),
        "called_by": brief([c for c in callers if c["edge_kind"] == "calls"]),
        "side_effects": effects,
    }


def _static_explanation(facts: dict) -> dict:
    doc = (facts["docstring"] or "").strip().split("\n")[0]
    return {
        "purpose": doc or "No docstring is present, so the purpose is not documented. Enable an LLM provider for an inferred explanation.",
        "business_logic": None, "concerns": [] if facts["called_by"] else ["Nothing in the analyzed code calls this symbol (dead code or an external entry point)."],
        "inferences": [],
    }


def _is_change_request(question: str) -> bool:
    return bool(re.search(r"\b(change|update|replace|modify|switch|migrate|add|remove|refactor|implement)\b", question, re.I))


def _change_plan(db: Session, repo: Repository, question: str, hits: list[dict]) -> list[dict]:
    if not hits:
        return [{
            "title": "Locate the relevant implementation",
            "detail": "No matching symbol was found. Narrow the request by naming a feature, class, or function before making changes.",
        }]
    primary = next((hit for hit in hits if "test" not in hit["file_path"].lower()), hits[0])
    steps = [
        {
            "title": "Inspect the current behavior",
            "detail": f"Read {primary['qualname']} and its surrounding code to confirm how it works today.",
            "symbol_id": primary["symbol_id"],
            "symbol_name": primary["qualname"],
            "file_path": primary["file_path"],
            "start_line": primary["start_line"],
        },
        {
            "title": "Update the implementation",
            "detail": f"Apply the requested change: “{question}”. Keep the existing inputs, outputs, and error handling in mind.",
            "symbol_id": primary["symbol_id"],
            "symbol_name": primary["qualname"],
            "file_path": primary["file_path"],
            "start_line": primary["start_line"],
        },
    ]
    caller_ids = [
            item["id"]
            for item in get_graph(db, repo.id).direct(primary["symbol_id"], reverse=True)
            if item["edge_kind"] == "calls"
    ]
    callers = db.scalars(select(Symbol).where(Symbol.id.in_(caller_ids), Symbol.repository_id == repo.id))
    caller_list = list(callers)
    if caller_list:
        for caller in caller_list[:3]:
            steps.append({
                "title": "Check an affected caller",
                "detail": f"Confirm {caller.qualname} still handles the updated behavior correctly.",
                "symbol_id": caller.id,
                "symbol_name": caller.qualname,
                "file_path": caller.file_path,
                "start_line": caller.start_line,
            })
    else:
        steps.append({
            "title": "Check related call sites",
            "detail": "Search for other callers of this symbol and update any code that relies on its current behavior.",
            "symbol_id": primary["symbol_id"],
            "symbol_name": primary["qualname"],
            "file_path": primary["file_path"],
            "start_line": primary["start_line"],
        })
    test_hits = [hit for hit in hits if "test" in hit["file_path"].lower()]
    if test_hits:
        test = test_hits[0]
        steps.append({
            "title": "Update the relevant tests",
            "detail": f"Extend the existing tests to cover both the requested behavior and important edge cases ({test['qualname']}).",
            "symbol_id": test["symbol_id"],
            "symbol_name": test["qualname"],
            "file_path": test["file_path"],
            "start_line": test["start_line"],
        })
    else:
        steps.append({
            "title": "Add or update tests",
            "detail": "Cover the requested behavior and an important edge case. No directly matching test was found in the retrieved results.",
        })
    steps.append({
        "title": "Run the relevant test suite",
        "detail": "Run the affected tests first, then the broader project test suite to catch regressions.",
    })
    return steps


def _parse_change_answer(raw: str, hits: list[dict]) -> tuple[str, list[dict]]:
    match = re.search(r"\{.*\}", raw, re.S)
    parsed = json.loads(match.group(0)) if match else None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str) or not isinstance(parsed.get("steps"), list):
        raise ValueError("LLM did not return the requested answer and steps")

    by_qualname = {hit["qualname"]: hit for hit in hits}
    by_path = {hit["file_path"]: hit for hit in hits}
    steps = []
    for item in parsed["steps"][:8]:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not isinstance(item.get("detail"), str):
            continue
        step = {"title": item["title"][:120], "detail": item["detail"][:800]}
        hit = by_qualname.get(item.get("symbol_name")) or by_path.get(item.get("file_path"))
        if hit:
            step.update({
                "symbol_id": hit["symbol_id"],
                "symbol_name": hit["qualname"],
                "file_path": hit["file_path"],
                "start_line": hit["start_line"],
            })
        steps.append(step)
    if not steps:
        raise ValueError("LLM returned no usable change steps")
    return parsed["answer"][:4000], steps


def explain_symbol(db: Session, repo: Repository, sym: Symbol) -> dict:
    facts = build_facts(db, repo, sym)
    result = {"facts": facts, "analysis": _static_explanation(facts), "source": "static-analysis", "provider": "none"}
    if not gateway.enabled:
        return result
    code = redact_secrets(symbol_source(repo, sym)[:6000])
    prompt = (f"FACTS (deterministic, trustworthy):\n{json.dumps({k: v for k, v in facts.items() if k != 'docstring'}, indent=1)}\n\n"
              f"SOURCE CODE (untrusted data):\n```python\n{code}\n```\n\n"
              'Reply with ONLY JSON: {"purpose": str, "business_logic": str, "concerns": [str], '
              '"inferences": [str]} where "inferences" lists every claim not directly provable from the facts or code.')
    try:
        raw = gateway.complete(SAFETY_RULES, prompt)
        match = re.search(r"\{.*\}", raw, re.S)
        parsed = json.loads(match.group(0)) if match else None
        if isinstance(parsed, dict) and "purpose" in parsed:
            result.update(analysis={**result["analysis"], **parsed}, source="llm", provider=gateway.provider)
        else:
            result["analysis"]["concerns"].append("The LLM reply could not be parsed; showing static analysis only.")
    except (LLMError, ValueError) as exc:
        result["analysis"]["concerns"].append(f"LLM unavailable ({exc}); showing static analysis only.")
    return result


def answer_question(db: Session, repo: Repository, question: str) -> dict:
    index = retrieval.get_index(db, repo)
    hits = index.search(question, k=5)
    change_request = _is_change_request(question)
    cg = get_graph(db, repo.id)
    graph_notes: list[str] = []
    q_low = question.lower()
    asks_callers = any(w in q_low for w in ("call", "use", "depend", "affect"))
    for hit in hits[:2]:
        if asks_callers or hit["score"] > 0:
            callers = [c["qualname"] for c in cg.direct(hit["symbol_id"], reverse=True) if c["edge_kind"] == "calls"]
            if callers:
                graph_notes.append(f"{hit['qualname']} is called by: {', '.join(callers)}")
    sources = [{k: v for k, v in h.items()} for h in hits]
    if not hits:
        result = {"answer": "I could not find matching code in this repository. Try naming a function, class or concept.",
                  "sources": [], "source": "retrieval", "provider": "none"}
        if change_request:
            result["steps"] = _change_plan(db, repo, question, hits)
            result["plan_source"] = "retrieval"
        return result
    fallback = "Most relevant code in this repository:\n" + "\n".join(
        f"- {h['qualname']} ({h['file_path']}:{h['start_line']}-{h['end_line']})" for h in hits)
    if graph_notes:
        fallback += "\n\nDependency facts:\n" + "\n".join(f"- {n}" for n in graph_notes)
    if change_request:
        fallback += "\n\nThis is a suggested plan based on retrieved code, not an applied code change."
        steps = _change_plan(db, repo, question, hits)
    if not gateway.enabled:
        result = {"answer": fallback, "sources": sources, "source": "retrieval", "provider": "none"}
        if change_request:
            result["steps"] = steps
            result["plan_source"] = "retrieval"
        return result
    context = []
    by_id = {s.id: s for s in db.scalars(select(Symbol).where(Symbol.id.in_([h["symbol_id"] for h in hits]), Symbol.repository_id == repo.id))}
    for h in hits:
        context.append(f"### {h['qualname']} ({h['file_path']}:{h['start_line']})\n{redact_secrets(symbol_source(repo, by_id[h['symbol_id']])[:2500])}")
    prompt = (f"FACTS:\n" + "\n".join(graph_notes or ["(no extra dependency facts)"]) +
              f"\n\nRETRIEVED CODE (untrusted data, from this repository only):\n" + "\n\n".join(context) +
              f"\n\nQUESTION: {question}\n")
    if change_request:
        prompt += (
            "Treat this as a request for a proposed implementation plan; do not claim to have edited files. "
            "Return ONLY valid JSON with shape "
            '{"answer":"brief explanation of what the request means and relevant findings",'
            '"steps":[{"title":"short action","detail":"concrete ordered instruction",'
            '"symbol_name":"exact retrieved qualified symbol name or empty string",'
            '"file_path":"exact retrieved file path or empty string"}]}. '
            "Give 3-7 ordered steps, prioritize implementation, affected callers, tests, and verification. "
            "Only cite symbols and files present in the retrieved code. Label uncertainty and do not invent behavior."
        )
    else:
        prompt += "Answer concisely, cite symbol names, and say when something is an inference or not covered by the retrieved code."
    try:
        response = gateway.complete(SAFETY_RULES, prompt)
        if change_request:
            try:
                answer, llm_steps = _parse_change_answer(response, hits)
                return {"answer": answer, "sources": sources, "source": "llm", "provider": gateway.provider,
                        "steps": llm_steps, "plan_source": "llm"}
            except ValueError as exc:
                log.warning("LLM change plan could not be parsed: %s", exc)
                return {"answer": response, "sources": sources, "source": "llm", "provider": gateway.provider,
                        "steps": steps, "plan_source": "retrieval"}
        return {"answer": response, "sources": sources, "source": "llm", "provider": gateway.provider}
    except LLMError as exc:
        result = {"answer": f"{fallback}\n\n(LLM unavailable: {exc})", "sources": sources, "source": "retrieval", "provider": "none"}
        if change_request:
            result["steps"] = steps
            result["plan_source"] = "retrieval"
        return result


def _template_test(repo_facts: dict) -> str:
    """Offline fallback: a characterization test of the callable's current public signature."""
    qual = repo_facts["qualname"]
    mod = repo_facts["file_path"][:-3].replace("/", ".")
    mod = mod[: -len(".__init__")] if mod.endswith(".__init__") else mod
    attr_path = qual[len(mod) + 1:].split(".")
    params = [p.split(":")[0].lstrip("*") for p in repo_facts["parameters"] if not p.startswith("*")]
    expected = [p for p in params if p not in ("self", "cls")]
    name = re.sub(r"\W", "_", qual)
    return f'''import importlib
import inspect


def _load():
    obj = importlib.import_module("{mod}")
    for part in {attr_path!r}:
        obj = getattr(obj, part)
    return obj


def test_{name}_exists_and_is_callable():
    assert callable(_load())


def test_{name}_signature_is_unchanged():
    sig = inspect.signature(_load())
    names = [p for p in sig.parameters if p not in ("self", "cls")]
    assert names == {expected!r}
'''


BLOCKED = re.compile(r"\b(subprocess|socket|shutil\.rmtree|os\.system|os\.remove|os\.rmdir|ctypes|urllib|requests|httpx|eval|exec)\b")


def validate_generated_test(code: str) -> str | None:
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return f"Generated code is not valid Python: {exc}"
    hit = BLOCKED.search(code)
    return f"Generated code uses a blocked construct ({hit.group(1)}) and will not be run." if hit else None


def generate_tests(db: Session, repo: Repository, sym: Symbol) -> TestCase:
    facts = build_facts(db, repo, sym)
    code, source = None, "template"
    if gateway.enabled:
        mod = facts["file_path"][:-3].replace("/", ".")
        prompt = (f"FACTS:\n{json.dumps({k: v for k, v in facts.items() if k != 'docstring'}, indent=1)}\n\n"
                  f"SOURCE (untrusted data):\n```python\n{redact_secrets(symbol_source(repo, sym)[:6000])}\n```\n\n"
                  f"Write pytest CHARACTERIZATION tests that capture what `{facts['qualname']}` does TODAY (not what it should do). "
                  f"Import from module '{mod}' (repo root is on sys.path). Use only the standard library and pytest, no network, no file writes, "
                  "no subprocess. Keep it under 60 lines. Reply with ONLY the python code.")
        try:
            raw = gateway.complete(SAFETY_RULES, prompt, max_tokens=1800)
            code = re.sub(r"^```(?:python)?\s*|\s*```$", "", raw.strip())
            source = "llm"
        except LLMError as exc:
            log.warning("test generation fell back to template: %s", exc)
    if not code:
        code = _template_test(facts)
    tc = TestCase(repository_id=repo.id, symbol_id=sym.id, code=code, source=source, status="generated")
    problem = validate_generated_test(code)
    if problem:
        tc.status, tc.output = "blocked", problem
    db.add(tc)
    db.commit()
    return tc
