"""Analysis pipeline: scan -> parse -> resolve dependencies -> store."""
import logging
from collections.abc import Callable
from pathlib import Path
import subprocess

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AnalysisResult, Dependency, File, Repository, Symbol, TestCase
from app.services.dependency_resolver import build_edges
from app.services.parser import ParsedFile, parse_python_file
from app.services.scanner import scan_repository

log = logging.getLogger(__name__)


def analyze_repository(db: Session, repo: Repository, progress: Callable[[str], None] = lambda m: None) -> dict:
    root = Path(repo.path)
    if not root.is_dir():
        raise FileNotFoundError(f"Repository directory is missing: {root}")

    progress("Clearing previous analysis")
    for model in (TestCase, AnalysisResult, Dependency, Symbol, File):
        db.execute(delete(model).where(model.repository_id == repo.id))
    db.commit()

    progress("Scanning files")
    scanned = scan_repository(root)
    languages: dict[str, int] = {}
    file_rows: dict[str, File] = {}
    for f in scanned:
        languages[f.language] = languages.get(f.language, 0) + 1
        row = File(repository_id=repo.id, path=f.path, extension=f.extension, language=f.language, size=f.size, line_count=f.line_count)
        db.add(row)
        file_rows[f.path] = row
    db.flush()

    progress("Parsing Python source")
    parsed: list[ParsedFile] = []
    parse_errors: list[dict] = []
    for f in scanned:
        if f.language != "python":
            continue
        if f.size > settings.max_parse_bytes:
            parse_errors.append({"file": f.path, "error": "file too large to parse"})
            continue
        try:
            source = (root / f.path).read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:  # unreadable / corrupted file
            parse_errors.append({"file": f.path, "error": str(exc)})
            continue
        pf = parse_python_file(f.path, source)
        if pf.error:
            parse_errors.append({"file": f.path, "error": pf.error})
        else:
            parsed.append(pf)

    progress("Storing symbols")
    sym_rows: dict[str, Symbol] = {}
    for pf in parsed:
        for s in pf.symbols:
            if s.qualname in sym_rows:  # duplicate qualname (e.g. redefinition): keep the first
                continue
            row = Symbol(repository_id=repo.id, file_id=file_rows[pf.path].id, qualname=s.qualname, name=s.name,
                         kind=s.kind, parent_qualname=s.parent_qualname, file_path=pf.path,
                         start_line=s.start_line, end_line=s.end_line, meta=s.meta)
            db.add(row)
            sym_rows[s.qualname] = row
    db.flush()

    progress("Building dependency graph")
    edges = build_edges(parsed)
    confidence_counts = {"exact": 0, "heuristic": 0}
    for src, tgt, kind, conf in edges:
        if src in sym_rows and tgt in sym_rows:
            db.add(Dependency(repository_id=repo.id, source_id=sym_rows[src].id, target_id=sym_rows[tgt].id, kind=kind, confidence=conf))
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
    repo.status = "analyzed"
    db.commit()
    source_commit = None
    if not repo.url.startswith("bundled://"):
        try:
            commit = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if commit.returncode == 0:
                source_commit = commit.stdout.strip()
            else:
                log.warning("could not identify source commit for repository %s: %s", repo.name, commit.stderr.strip())
        except subprocess.TimeoutExpired:
            log.warning("timed out identifying source commit for repository %s", repo.name)
    summary = {"files": len(scanned), "languages": languages, "python_files": languages.get("python", 0),
               "parsed_python_files": len(parsed), "unsupported_files": len(scanned) - languages.get("python", 0),
               "symbols": len(sym_rows), "dependencies": sum(confidence_counts.values()),
               "confidence": confidence_counts, "source_commit": source_commit,
               "parse_errors": parse_errors[:20], "parse_error_count": len(parse_errors)}
    log.info("analyzed repo %s: %s", repo.name, {k: v for k, v in summary.items() if k != "parse_errors"})
    return summary
