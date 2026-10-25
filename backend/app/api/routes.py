from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import AnalysisJob, AnalysisResult, Dependency, File, Repository, Symbol, TestCase, User
from app.schemas import AskRequest, CloneRequest, Credentials, JobOut, RepositoryOut, TestOut, TokenOut
from app.services import ai_service, jobs, repository_service as repos, sandbox
from app.services.errors import NotFound
from app.services.graph_service import get_graph
from app.services.impact_service import analyze_impact
from app.services.source_reader import read_file

router = APIRouter(dependencies=[Depends(get_current_user)])
public_router = APIRouter()
auth_router = APIRouter(prefix="/auth")


def _repo_out(db: Session, repo: Repository) -> RepositoryOut:
    out = RepositoryOut.model_validate(repo)
    out.file_count = db.scalar(select(func.count(File.id)).where(File.repository_id == repo.id)) or 0
    out.symbol_count = db.scalar(select(func.count(Symbol.id)).where(Symbol.repository_id == repo.id)) or 0
    return out


def _symbol(db: Session, repo_id: int, symbol_id: int) -> Symbol:
    sym = db.get(Symbol, symbol_id)
    if not sym or sym.repository_id != repo_id:  # never cross repositories
        raise NotFound("Symbol not found in this repository")
    return sym


def _symbol_out(s: Symbol) -> dict:
    m = s.meta or {}
    return {"id": s.id, "qualname": s.qualname, "name": s.name, "kind": s.kind, "file_path": s.file_path,
            "start_line": s.start_line, "end_line": s.end_line, "params": m.get("params", []),
            "route": m.get("route"), "is_test": bool(m.get("is_test"))}


@public_router.get("/health")
def health():
    from app.services.llm_gateway import gateway
    return {"status": "ok", "llm_provider": gateway.provider, "docker": sandbox.docker_ready() is None}


@auth_router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(body: Credentials, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user), "user": user}


@auth_router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return {"access_token": create_access_token(user), "user": user}


# ---- repositories -------------------------------------------------------------
@router.post("/repositories", response_model=RepositoryOut, status_code=201)
def add_repository(body: CloneRequest, db: Session = Depends(get_db)):
    return _repo_out(db, repos.clone_repository(db, body.repo_url, body.repo_name))


@router.post("/repositories/demo", response_model=RepositoryOut, status_code=201)
def add_demo(db: Session = Depends(get_db)):
    return _repo_out(db, repos.load_demo(db))


@router.get("/repositories", response_model=list[RepositoryOut])
def list_repositories(db: Session = Depends(get_db)):
    return [_repo_out(db, r) for r in db.scalars(select(Repository).order_by(Repository.id.desc()))]


@router.get("/repositories/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: int, db: Session = Depends(get_db)):
    return _repo_out(db, repos.get_repository(db, repo_id))


@router.get("/repositories/{repo_id}/summary")
def repository_summary(repo_id: int, db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    languages = dict(db.execute(
        select(File.language, func.count(File.id))
        .where(File.repository_id == repo_id)
        .group_by(File.language)
    ).all())
    confidence = dict(db.execute(
        select(Dependency.confidence, func.count(Dependency.id))
        .where(Dependency.repository_id == repo_id)
        .group_by(Dependency.confidence)
    ).all())

    degrees: dict[int, int] = {}
    for symbol_id, count in db.execute(
        select(Dependency.source_id, func.count(Dependency.id))
        .where(Dependency.repository_id == repo_id)
        .group_by(Dependency.source_id)
    ):
        degrees[symbol_id] = degrees.get(symbol_id, 0) + count
    for symbol_id, count in db.execute(
        select(Dependency.target_id, func.count(Dependency.id))
        .where(Dependency.repository_id == repo_id)
        .group_by(Dependency.target_id)
    ):
        degrees[symbol_id] = degrees.get(symbol_id, 0) + count
    spotlight_symbol = db.get(Symbol, max(degrees, key=degrees.get)) if degrees else None

    latest = db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.repository_id == repo_id, AnalysisJob.kind.in_(("analyze", "refresh")), AnalysisJob.status == "completed")
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )
    result = latest.result if latest and latest.result else {}
    return {
        "repository_id": repo_id,
        "languages": languages,
        "supported_files": languages.get("python", 0),
        "unsupported_files": sum(count for language, count in languages.items() if language != "python"),
        "confidence": confidence,
        "analysis": {
            "job_id": latest.id if latest else None,
            "created_at": latest.finished_at if latest else None,
            "source_commit": result.get("source_commit"),
            "files": result.get("files", 0),
            "symbols": result.get("symbols", 0),
            "dependencies": result.get("dependencies", 0),
            "parse_error_count": result.get("parse_error_count", 0),
            "parse_errors": result.get("parse_errors", []),
        },
        "spotlight": ({
            "symbol_id": spotlight_symbol.id,
            "name": spotlight_symbol.name,
            "qualname": spotlight_symbol.qualname,
            "file_path": spotlight_symbol.file_path,
            "links": degrees[spotlight_symbol.id],
        } if spotlight_symbol else None),
    }


@router.post("/repositories/{repo_id}/check-updates")
def check_repository_updates(repo_id: int, db: Session = Depends(get_db)):
    repo = repos.get_repository(db, repo_id)
    if repo.url.startswith("bundled://"):
        return {"supported": False, "stale": False, "analyzed_commit": None, "remote_commit": None}
    summary = repository_summary(repo_id, db)
    analyzed_commit = summary["analysis"]["source_commit"]
    if not analyzed_commit:
        return {"supported": False, "stale": False, "analyzed_commit": None, "remote_commit": None}
    remote_commit = repos.check_remote_commit(repo.url)
    return {
        "supported": True,
        "stale": remote_commit != analyzed_commit,
        "analyzed_commit": analyzed_commit,
        "remote_commit": remote_commit,
    }


@router.post("/repositories/{repo_id}/analyze", status_code=202)
def analyze(repo_id: int, db: Session = Depends(get_db)):
    job = jobs.submit_analysis(db, repos.get_repository(db, repo_id))
    return {"job_id": job.id, "status": job.status}


@router.post("/repositories/{repo_id}/refresh", status_code=202)
def refresh_and_analyze(repo_id: int, db: Session = Depends(get_db)):
    repo = repos.get_repository(db, repo_id)
    job = jobs.submit_refresh(db, repo)
    return {"job_id": job.id, "status": job.status}


# ---- jobs ---------------------------------------------------------------------
@router.get("/jobs", response_model=list[JobOut])
def list_jobs(repository_id: int | None = None, db: Session = Depends(get_db)):
    q = select(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(50)
    if repository_id:
        q = q.where(AnalysisJob.repository_id == repository_id)
    return list(db.scalars(q))


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    return jobs.get_job(db, job_id)


# ---- code ---------------------------------------------------------------------
@router.get("/repositories/{repo_id}/files")
def list_files(repo_id: int, db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    rows = db.scalars(select(File).where(File.repository_id == repo_id).order_by(File.path))
    return [{"path": f.path, "language": f.language, "size": f.size, "line_count": f.line_count} for f in rows]


@router.get("/repositories/{repo_id}/file")
def get_file(repo_id: int, path: str = Query(...), db: Session = Depends(get_db)):
    repo = repos.get_repository(db, repo_id)
    if not db.scalar(select(File.id).where(File.repository_id == repo_id, File.path == path)):
        raise NotFound("File not found")
    return {"path": path, "content": read_file(repo, path)}


@router.get("/repositories/{repo_id}/symbols")
def list_symbols(repo_id: int, q: str | None = None, db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    query = select(Symbol).where(Symbol.repository_id == repo_id, Symbol.kind != "module").order_by(Symbol.file_path, Symbol.start_line)
    if q:
        query = query.where(Symbol.qualname.ilike(f"%{q}%"))
    return [_symbol_out(s) for s in db.scalars(query.limit(2000))]


# ---- intelligence ---------------------------------------------------------------
@router.get("/repositories/{repo_id}/symbols/{symbol_id}/graph")
def symbol_graph(repo_id: int, symbol_id: int, up: int = Query(2, ge=0, le=6), down: int = Query(2, ge=0, le=6), db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    _symbol(db, repo_id, symbol_id)
    return get_graph(db, repo_id).neighborhood(symbol_id, up, down)


@router.get("/repositories/{repo_id}/symbols/{symbol_id}/dependencies")
def symbol_dependencies(repo_id: int, symbol_id: int, db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    _symbol(db, repo_id, symbol_id)
    cg = get_graph(db, repo_id)
    return {"depends_on": cg.direct(symbol_id, reverse=False), "depended_on_by": cg.direct(symbol_id, reverse=True)}


def _cached(db: Session, repo_id: int, symbol_id: int, kind: str, compute):
    row = db.scalar(select(AnalysisResult).where(AnalysisResult.repository_id == repo_id, AnalysisResult.symbol_id == symbol_id, AnalysisResult.kind == kind).order_by(AnalysisResult.id.desc()))
    payload = compute()
    if row:
        row.payload = payload
    else:
        db.add(AnalysisResult(repository_id=repo_id, symbol_id=symbol_id, kind=kind, payload=payload))
    db.commit()
    return payload


@router.post("/repositories/{repo_id}/symbols/{symbol_id}/explain")
def explain(repo_id: int, symbol_id: int, db: Session = Depends(get_db)):
    repo = repos.get_repository(db, repo_id)
    sym = _symbol(db, repo_id, symbol_id)
    return _cached(db, repo_id, symbol_id, "explain", lambda: ai_service.explain_symbol(db, repo, sym))


@router.post("/repositories/{repo_id}/symbols/{symbol_id}/impact")
def impact(repo_id: int, symbol_id: int, db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    _symbol(db, repo_id, symbol_id)
    return _cached(db, repo_id, symbol_id, "impact", lambda: analyze_impact(get_graph(db, repo_id), symbol_id))


@router.post("/repositories/{repo_id}/ask")
def ask(repo_id: int, body: AskRequest, db: Session = Depends(get_db)):
    return ai_service.answer_question(db, repos.get_repository(db, repo_id), body.question.strip()[:1000])


# ---- tests ----------------------------------------------------------------------
@router.post("/repositories/{repo_id}/symbols/{symbol_id}/tests", response_model=TestOut, status_code=201)
def generate_tests(repo_id: int, symbol_id: int, db: Session = Depends(get_db)):
    repo = repos.get_repository(db, repo_id)
    return ai_service.generate_tests(db, repo, _symbol(db, repo_id, symbol_id))


@router.get("/repositories/{repo_id}/tests", response_model=list[TestOut])
def list_tests(repo_id: int, symbol_id: int | None = None, db: Session = Depends(get_db)):
    repos.get_repository(db, repo_id)
    q = select(TestCase).where(TestCase.repository_id == repo_id).order_by(TestCase.id.desc())
    if symbol_id:
        q = q.where(TestCase.symbol_id == symbol_id)
    return list(db.scalars(q.limit(50)))


@router.post("/repositories/{repo_id}/tests/{test_id}/run", response_model=TestOut)
def run_test(repo_id: int, test_id: int, db: Session = Depends(get_db)):
    repo = repos.get_repository(db, repo_id)
    tc = db.get(TestCase, test_id)
    if not tc or tc.repository_id != repo_id:
        raise NotFound("Test not found")
    if tc.status == "blocked":
        return tc
    problem = ai_service.validate_generated_test(tc.code)  # re-validate: code may have been edited
    if problem:
        tc.status, tc.output = "blocked", problem
    else:
        res = sandbox.run_tests(repo.path, tc.code)
        tc.status, tc.exit_code, tc.output = res.status, res.exit_code, res.output
    db.commit()
    return tc
