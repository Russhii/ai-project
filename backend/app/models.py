"""Relational schema. Every row that belongs to a repository carries repository_id,
so queries are always scoped to one repository (no cross-repository leakage)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    url: Mapped[str] = mapped_column(String(500))
    path: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="cloned")  # cloned|analyzing|analyzed|failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    files: Mapped[list["File"]] = relationship(cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    path: Mapped[str] = mapped_column(String(1000))
    extension: Mapped[str] = mapped_column(String(20), default="")
    language: Mapped[str] = mapped_column(String(30), default="unknown")
    size: Mapped[int] = mapped_column(Integer, default=0)
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (Index("ix_files_repo_path", "repository_id", "path"),)


class Symbol(Base):
    __tablename__ = "symbols"
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    qualname: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # module|class|function|method
    parent_qualname: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1000))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        Index("ix_symbols_repo_qualname", "repository_id", "qualname"),
        Index("ix_symbols_repo_name", "repository_id", "name"),
    )


class Dependency(Base):
    __tablename__ = "dependencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # calls|imports|inherits|contains
    confidence: Mapped[str] = mapped_column(String(20), default="exact")  # exact|heuristic


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|failed
    message: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TestCase(Base):
    __test__ = False  # not a pytest class
    __tablename__ = "test_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), index=True)
    code: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))  # llm|template
    status: Mapped[str] = mapped_column(String(20), default="generated")  # generated|passed|failed|error|timeout|blocked
    output: Mapped[str] = mapped_column(Text, default="")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    symbol_id: Mapped[int | None] = mapped_column(ForeignKey("symbols.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # explain|impact
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
