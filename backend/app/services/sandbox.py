"""Run generated tests inside a locked-down Docker container.

Security model (the repository and the generated test are both untrusted):
  --network none          no outbound/inbound network
  --read-only + tmpfs     the container filesystem is not writable except a small /tmp
  -v repo:ro              repository mounted read-only; tests mounted read-only
  --cap-drop ALL, no-new-privileges, --pids-limit, --memory, --cpus   resource and privilege limits
  hard wall-clock timeout, then the container is force-removed
Nothing from the repository is ever imported or executed in the API process.
"""
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

OUTPUT_LIMIT = 20_000


@dataclass
class SandboxResult:
    status: str  # passed | failed | error | timeout
    exit_code: int | None
    output: str


def _docker(*args: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def docker_ready() -> str | None:
    """Returns None when ready, otherwise a human-readable reason."""
    if not shutil.which("docker"):
        return "Docker is not installed or not on PATH."
    try:
        if _docker("info", timeout=10).returncode != 0:
            return "The Docker daemon is not running."
        if _docker("image", "inspect", settings.sandbox_image, timeout=10).returncode != 0:
            return f"Sandbox image '{settings.sandbox_image}' not found. Build it: docker build -t {settings.sandbox_image} backend/sandbox"
    except subprocess.TimeoutExpired:
        return "Docker did not respond in time."
    return None


def run_tests(repo_path: str, test_code: str) -> SandboxResult:
    problem = docker_ready()
    if problem:
        return SandboxResult("error", None, problem)
    name = f"lci-sandbox-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "test_generated.py").write_text(test_code, encoding="utf-8")
        cmd = ["run", "--rm", "--name", name, "--network", "none", "--memory", "256m", "--memory-swap", "256m",
               "--cpus", "0.5", "--pids-limit", "128", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "-v", f"{Path(repo_path).resolve()}:/repo:ro", "-v", f"{tmp}:/tests:ro", "-w", "/repo",
               "-e", "PYTHONPATH=/repo:/repo/src", "-e", "PYTHONDONTWRITEBYTECODE=1",
               settings.sandbox_image, "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir=/tmp", "/tests"]
        try:
            proc = _docker(*cmd, timeout=settings.sandbox_timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            return SandboxResult("timeout", None, f"Test run exceeded {settings.sandbox_timeout}s and was killed.")
    out = (proc.stdout + proc.stderr)[-OUTPUT_LIMIT:]
    status = "passed" if proc.returncode == 0 else "failed" if proc.returncode == 1 else "error"
    return SandboxResult(status, proc.returncode, out)
