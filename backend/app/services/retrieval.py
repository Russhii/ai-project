"""Repository-scoped code retrieval over function/class-sized chunks.

Chunks are real symbols (not arbitrary text windows) and every chunk carries metadata
(repository_id, file_path, symbol_name, symbol_type, start_line, end_line).
Ranking is TF-IDF so it works offline; `Retriever` is the seam where embeddings + pgvector
plug in later without touching callers.
"""
import math
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Repository, Symbol
from app.services.graph_service import _fingerprint
from app.services.source_reader import read_file

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_cache: dict[int, tuple[tuple, "Index"]] = {}


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for word in _TOKEN.findall(text):
        out.append(word.lower())
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", word).replace("_", " ").lower().split()
        if len(parts) > 1:
            out.extend(parts)
    return out


class Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.tf = [Counter(tokenize(c["text"] + " " + c["qualname"] * 2)) for c in chunks]
        df: Counter = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = max(len(chunks), 1)
        self.idf = {t: math.log(1 + n / (1 + d)) for t, d in df.items()}

    def search(self, query: str, k: int = 5) -> list[dict]:
        q = tokenize(query)
        scored = []
        for chunk, tf in zip(self.chunks, self.tf):
            total = sum(tf.values()) or 1
            score = sum((tf[t] / total) * self.idf.get(t, 0) for t in q if t in tf)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [{**{k_: v for k_, v in c.items() if k_ != "text"}, "score": round(s, 4)} for s, c in scored[:k]]


def get_index(db: Session, repo: Repository) -> Index:
    fp = _fingerprint(db, repo.id)
    cached = _cache.get(repo.id)
    if cached and cached[0] == fp:
        return cached[1]
    chunks, file_cache = [], {}
    for s in db.scalars(select(Symbol).where(Symbol.repository_id == repo.id, Symbol.kind.in_(["function", "method", "class"]))):
        if s.file_path not in file_cache:
            file_cache[s.file_path] = read_file(repo, s.file_path).splitlines()
        text = "\n".join(file_cache[s.file_path][s.start_line - 1: s.end_line])[:4000]
        chunks.append({"repository_id": repo.id, "symbol_id": s.id, "qualname": s.qualname, "file_path": s.file_path,
                       "symbol_name": s.name, "symbol_type": s.kind, "start_line": s.start_line,
                       "end_line": s.end_line, "text": text})
    index = Index(chunks)
    _cache[repo.id] = (fp, index)
    return index
