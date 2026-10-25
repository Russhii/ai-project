"""Repository ingestion: validate, clone, register. No FastAPI code in here."""
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Repository
from app.services.errors import Conflict, NotFound, UpstreamFailure, ValidationFailed

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_GH_PATH = re.compile(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?")


def validate_url(repo_url: str) -> None:
    u = urlsplit(repo_url)
    if (
        u.scheme != "https" or u.hostname != "github.com" or u.port not in (None, 443)
        or u.username or u.password or u.query or u.fragment or not _GH_PATH.fullmatch(u.path)
    ):
        raise ValidationFailed("repo_url must be an HTTPS GitHub repository URL, e.g. https://github.com/owner/repo")


def validate_name(name: str) -> None:
    if not _NAME.fullmatch(name) or name in {".", ".."}:
        raise ValidationFailed("repo_name may only contain letters, digits, '.', '_' and '-'")


def _register(db: Session, name: str, url: str, dest: Path) -> Repository:
    repo = Repository(name=name, url=url, path=str(dest), status="cloned")
    db.add(repo)
    db.commit()
    return repo


def _check_free(db: Session, name: str, url: str | None) -> Path:
    dest = settings.repositories_dir / name
    if db.scalar(select(Repository).where(Repository.name == name)) or dest.exists():
        raise Conflict(f"A repository named '{name}' already exists")
    if url and db.scalar(select(Repository).where(Repository.url == url)):
        raise Conflict("This repository URL was already added")
    return dest


def clone_repository(db: Session, repo_url: str, repo_name: str) -> Repository:
    validate_url(repo_url)
    validate_name(repo_name)
    dest = _check_free(db, repo_name, repo_url)
    settings.repositories_dir.mkdir(parents=True, exist_ok=True)
    try:
        # GIT_TERMINAL_PROMPT=0: never hang waiting for a password on private repos.
        result = subprocess.run(
            ["git", "-c", "core.longpaths=true", "clone", "--quiet", "--depth=1", "--", repo_url, str(dest)],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True,
            text=True,
            timeout=settings.clone_timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(dest, ignore_errors=True)  # remove half-finished clone
        raise UpstreamFailure("Git is not installed or not available on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise UpstreamFailure(f"Git clone exceeded the {settings.clone_timeout}-second timeout.") from exc
    if result.returncode:
        shutil.rmtree(dest, ignore_errors=True)
        detail = (result.stderr.strip() or result.stdout.strip())[-2000:]
        if "checkout failed" in detail.lower():
            detail = (
                "Git downloaded the repository but could not check out its files. "
                "Use a local, non-synced REPOSITORIES_DIR (for example, C:\\lci\\repositories) "
                "and retry. Git's Windows long-path support was enabled for this clone."
            )
        elif not detail:
            detail = "Check that the repository exists and is public."
        raise UpstreamFailure(f"Git clone failed: {detail}")
    return _register(db, repo_name, repo_url, dest)


def check_remote_commit(repo_url: str) -> str:
    validate_url(repo_url)
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo_url, "HEAD"],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpstreamFailure("Git is not installed or not available on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpstreamFailure("Checking the remote repository timed out. Please try again.") from exc
    if result.returncode:
        detail = result.stderr.strip() or "Could not read the public repository's current commit."
        raise UpstreamFailure(f"Could not check repository updates: {detail}")
    commit = result.stdout.split(maxsplit=1)
    if not commit:
        raise UpstreamFailure("GitHub did not return a commit for the repository's default branch.")
    return commit[0]


def refresh_repository(repo: Repository) -> None:
    validate_url(repo.url)
    try:
        fetch = subprocess.run(
            ["git", "-C", repo.path, "fetch", "--depth=1", "origin"],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True,
            text=True,
            timeout=settings.clone_timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpstreamFailure("Git is not installed or not available on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpstreamFailure(f"Updating the repository exceeded the {settings.clone_timeout}-second timeout.") from exc
    if fetch.returncode:
        detail = fetch.stderr.strip() or "Could not fetch the latest public repository."
        raise UpstreamFailure(f"Repository update failed: {detail}")
    try:
        reset = subprocess.run(
            ["git", "-C", repo.path, "reset", "--hard", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpstreamFailure("Switching to the latest repository commit timed out.") from exc
    if reset.returncode:
        detail = reset.stderr.strip() or "Could not switch to the latest repository commit."
        raise UpstreamFailure(f"Repository update failed: {detail}")


def load_demo(db: Session, name: str = "demo-shop") -> Repository:
    """Copy the bundled sample project so the platform can be tried without GitHub."""
    existing = db.scalar(select(Repository).where(Repository.name == name))
    if existing:
        return existing
    dest = _check_free(db, name, None)
    shutil.copytree(settings.sample_repo_dir, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return _register(db, name, "bundled://sample_repo", dest)


def get_repository(db: Session, repo_id: int) -> Repository:
    repo = db.get(Repository, repo_id)
    if not repo:
        raise NotFound("Repository not found")
    return repo


def safe_path(repo: Repository, rel_path: str) -> Path:
    """Resolve a user-supplied relative path and make sure it stays inside the repo (path traversal guard)."""
    root = Path(repo.path).resolve()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise NotFound("File not found")
    return target
