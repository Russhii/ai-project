"""Central configuration, read from environment variables (see .env.example)."""
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'lci.db'}")
    repositories_dir: Path = Path(os.getenv("REPOSITORIES_DIR", Path.home() / ".lci" / "repositories"))
    sample_repo_dir: Path = BASE_DIR / "sample_repo"
    llm_provider: str = os.getenv("LLM_PROVIDER", "none").lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    use_celery: bool = os.getenv("USE_CELERY", "false").lower() == "true"
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    sandbox_image: str = os.getenv("SANDBOX_IMAGE", "legacy-sandbox")
    sandbox_timeout: int = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "30"))
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
    jwt_expiration_minutes: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    )
    clone_timeout: int = int(os.getenv("CLONE_TIMEOUT_SECONDS", "600"))
    max_parse_bytes: int = 1_000_000


settings = Settings()
