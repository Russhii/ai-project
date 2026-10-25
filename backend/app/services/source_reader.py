from pathlib import Path

from app.models import Repository, Symbol
from app.services.repository_service import safe_path


def read_file(repo: Repository, rel_path: str, limit: int = 1_000_000) -> str:
    path: Path = safe_path(repo, rel_path)
    return path.read_bytes()[:limit].decode("utf-8", errors="replace")


def symbol_source(repo: Repository, sym: Symbol) -> str:
    lines = read_file(repo, sym.file_path).splitlines()
    return "\n".join(lines[sym.start_line - 1: sym.end_line])
