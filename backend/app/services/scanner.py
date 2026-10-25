"""Walk a repository and describe its files."""
import os
from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist",
                ".tox", ".mypy_cache", ".pytest_cache", "site-packages", ".idea", ".vscode"}
LANGUAGES = {".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java", ".go": "go",
             ".rb": "ruby", ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".md": "markdown",
             ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".txt": "text",
             ".html": "html", ".css": "css", ".sql": "sql", ".sh": "shell"}
MAX_LINECOUNT_BYTES = 2_000_000


@dataclass
class ScannedFile:
    path: str  # POSIX style, relative to repo root
    extension: str
    language: str
    size: int
    line_count: int


def scan_repository(root: Path) -> list[ScannedFile]:
    root = root.resolve()
    found: list[ScannedFile] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not os.path.islink(os.path.join(dirpath, d)))
        for fname in sorted(filenames):
            full = Path(dirpath) / fname
            if full.is_symlink():
                continue
            ext = full.suffix.lower()
            size = full.stat().st_size
            lines = 0
            if ext in LANGUAGES and size <= MAX_LINECOUNT_BYTES:
                with open(full, "rb") as fh:
                    lines = sum(1 for _ in fh)
            found.append(ScannedFile(full.relative_to(root).as_posix(), ext, LANGUAGES.get(ext, "unknown"), size, lines))
    return found
