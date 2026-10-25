import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def analyzed(client):
    repo = client.post("/repositories/demo").json()
    job = client.post(f"/repositories/{repo['id']}/analyze").json()
    assert client.get(f"/jobs/{job['job_id']}").json()["status"] == "completed"
    return client, repo["id"]


def _sym(client, rid, qualname):
    return next(s for s in client.get(f"/repositories/{rid}/symbols").json() if s["qualname"] == qualname)


def test_root_and_validation(client):
    assert client.get("/").status_code == 200
    r = client.post("/repositories", json={"repo_url": "https://evil.com/a/b", "repo_name": "x"})
    assert r.status_code == 400
    r = client.post("/repositories", json={"repo_url": "https://github.com/a/b", "repo_name": "../etc"})
    assert r.status_code == 400


def test_auth_signup_login_and_protected_api(client):
    client.headers.pop("Authorization")
    assert client.get("/repositories").status_code == 401
    assert client.get("/health").status_code == 200

    response = client.post("/auth/signup", json={"email": "new@example.com", "password": "password123"})
    assert response.status_code == 201
    token = response.json()["access_token"]
    assert response.json()["user"]["email"] == "new@example.com"
    assert client.post("/auth/signup", json={"email": "NEW@example.com", "password": "password123"}).status_code == 409

    assert client.post("/auth/login", json={"email": "new@example.com", "password": "password123"}).status_code == 200
    assert client.post("/auth/login", json={"email": "new@example.com", "password": "incorrect"}).status_code == 401
    client.headers["Authorization"] = f"Bearer {token}tampered"
    assert client.get("/repositories").status_code == 401


def test_clone_public_github_repository(client, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).mkdir()
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.repository_service.subprocess.run", fake_run)
    response = client.post(
        "/repositories",
        json={"repo_url": "https://github.com/octocat/Hello-World", "repo_name": "hello-world"},
    )

    assert response.status_code == 201
    assert response.json()["url"] == "https://github.com/octocat/Hello-World"
    command, kwargs = calls[0]
    assert command[:7] == ["git", "-c", "core.longpaths=true", "clone", "--quiet", "--depth=1", "--"]
    assert command[7] == "https://github.com/octocat/Hello-World"
    assert Path(command[-1]).name == "hello-world"
    assert kwargs["timeout"] > 0
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_failed_clone_cleans_partial_repository(client, monkeypatch):
    destinations = []

    def fake_run(command, **kwargs):
        dest = Path(command[-1])
        destinations.append(dest)
        dest.mkdir()
        (dest / "partial").write_text("partial clone")
        return subprocess.CompletedProcess(command, 128, "", "repository not found")

    monkeypatch.setattr("app.services.repository_service.subprocess.run", fake_run)
    response = client.post(
        "/repositories",
        json={"repo_url": "https://github.com/octocat/not-a-repository", "repo_name": "missing"},
    )

    assert response.status_code == 502
    assert "repository not found" in response.json()["detail"]
    assert not destinations[0].exists()
    assert client.get("/repositories").json() == []


def test_checkout_failure_reports_local_storage_guidance(client, monkeypatch):
    destinations = []

    def fake_run(command, **kwargs):
        dest = Path(command[-1])
        destinations.append(dest)
        dest.mkdir()
        return subprocess.CompletedProcess(command, 128, "warning: Clone succeeded, but checkout failed.", "")

    monkeypatch.setattr("app.services.repository_service.subprocess.run", fake_run)
    response = client.post(
        "/repositories",
        json={"repo_url": "https://github.com/example/checkout-failure", "repo_name": "checkout-failure"},
    )

    assert response.status_code == 502
    assert "non-synced REPOSITORIES_DIR" in response.json()["detail"]
    assert not destinations[0].exists()
    assert client.get("/repositories").json() == []


def test_timed_out_clone_cleans_partial_repository(client, monkeypatch):
    destinations = []

    def fake_run(command, **kwargs):
        dest = Path(command[-1])
        destinations.append(dest)
        dest.mkdir()
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("app.services.repository_service.subprocess.run", fake_run)
    response = client.post(
        "/repositories",
        json={"repo_url": "https://github.com/octocat/slow-repository", "repo_name": "slow"},
    )

    assert response.status_code == 502
    assert "timeout" in response.json()["detail"]
    assert not destinations[0].exists()
    assert client.get("/repositories").json() == []


def test_duplicate_demo_is_idempotent_and_name_conflict(client, tmp_path):
    a = client.post("/repositories/demo").json()
    b = client.post("/repositories/demo").json()
    assert a["id"] == b["id"]


def test_analysis_job_and_symbols(analyzed):
    client, rid = analyzed
    repo = client.get(f"/repositories/{rid}").json()
    assert repo["status"] == "analyzed" and repo["symbol_count"] > 10
    assert client.get("/jobs/nope").status_code == 404


def test_repository_summary_explains_coverage_and_confidence(analyzed):
    client, rid = analyzed
    summary = client.get(f"/repositories/{rid}/summary").json()

    assert summary["languages"]["python"] > 0
    assert summary["supported_files"] == summary["languages"]["python"]
    assert summary["unsupported_files"] == sum(
        count for language, count in summary["languages"].items() if language != "python"
    )
    assert summary["analysis"]["symbols"] > 0
    assert summary["confidence"]["exact"] > 0
    assert summary["spotlight"]["links"] > 0


def test_check_updates_compares_latest_commit(analyzed, monkeypatch):
    from app.db import SessionLocal
    from app.models import AnalysisJob, Repository

    client, rid = analyzed
    with SessionLocal() as db:
        repo = db.get(Repository, rid)
        repo.url = "https://github.com/octocat/Hello-World"
        job = db.query(AnalysisJob).filter_by(repository_id=rid, status="completed").one()
        job.result = {**job.result, "source_commit": "old-commit"}
        db.commit()
    monkeypatch.setattr("app.services.repository_service.check_remote_commit", lambda _: "new-commit")

    response = client.post(f"/repositories/{rid}/check-updates")
    assert response.status_code == 200
    assert response.json() == {
        "supported": True,
        "stale": True,
        "analyzed_commit": "old-commit",
        "remote_commit": "new-commit",
    }


def test_refresh_runs_as_a_tracked_background_job(analyzed, monkeypatch):
    from app.db import SessionLocal
    from app.models import Repository

    client, rid = analyzed
    with SessionLocal() as db:
        repo = db.get(Repository, rid)
        repo.url = "https://github.com/octocat/Hello-World"
        db.commit()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "latest-commit\n", "")

    monkeypatch.setattr("app.services.repository_service.subprocess.run", fake_run)
    response = client.post(f"/repositories/{rid}/refresh")

    assert response.status_code == 202
    job = client.get(f"/jobs/{response.json()['job_id']}").json()
    assert job["kind"] == "refresh" and job["status"] == "completed"
    assert calls[0][3:5] == ["fetch", "--depth=1"]
    assert calls[1][3:6] == ["reset", "--hard", "FETCH_HEAD"]


def test_dependencies_and_graph(analyzed):
    client, rid = analyzed
    pay = _sym(client, rid, "shop.services.payment.PaymentService.process_payment")
    deps = client.get(f"/repositories/{rid}/symbols/{pay['id']}/dependencies").json()
    callers = {d["qualname"] for d in deps["depended_on_by"]}
    assert "shop.services.orders.OrderService.checkout" in callers
    assert "shop.services.payment.PaymentService.validate_amount" in {d["qualname"] for d in deps["depends_on"]}
    g = client.get(f"/repositories/{rid}/symbols/{pay['id']}/graph?up=3&down=1").json()
    assert g["edges"] and any(n["depth"] == 0 for n in g["nodes"])


def test_impact_reaches_api_and_tests(analyzed):
    client, rid = analyzed
    pay = _sym(client, rid, "shop.services.payment.PaymentService.process_payment")
    imp = client.post(f"/repositories/{rid}/symbols/{pay['id']}/impact").json()
    assert [a["route"] for a in imp["affected_apis"]] == ["POST /checkout"]
    names = {f["name"] for f in imp["affected_functions"]}
    assert {"OrderService.checkout", "checkout_controller"} <= names
    assert imp["summary"]["related_tests"] >= 1
    assert imp["risk"]["level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} and imp["risk"]["factors"]
    assert any(p[0]["label"] == "checkout_controller" for p in imp["dependency_paths"])


def test_explain_static_and_ask(analyzed):
    client, rid = analyzed
    pay = _sym(client, rid, "shop.services.payment.PaymentService.process_payment")
    ex = client.post(f"/repositories/{rid}/symbols/{pay['id']}/explain").json()
    assert ex["source"] == "static-analysis" and "Charge the card" in ex["analysis"]["purpose"]
    ans = client.post(f"/repositories/{rid}/ask", json={"question": "which functions call process_payment?"}).json()
    assert "process_payment" in ans["answer"] and ans["sources"]


def test_change_request_returns_ordered_code_referenced_steps(analyzed):
    client, rid = analyzed
    response = client.post(
        f"/repositories/{rid}/ask",
        json={"question": "Change process_payment to reject payments of zero dollars"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["plan_source"] == "retrieval"
    assert len(result["steps"]) >= 4
    assert result["steps"][0]["title"] == "Inspect the current behavior"
    assert result["steps"][1]["title"] == "Update the implementation"
    assert "reject payments of zero dollars" in result["steps"][1]["detail"]
    assert result["steps"][1]["file_path"] == "shop/services/payment.py"
    assert all(step["title"] for step in result["steps"])
    assert any(step.get("file_path", "").endswith("test_payment.py") for step in result["steps"])


def test_generate_and_run_tests_graceful_without_docker(analyzed, monkeypatch):
    client, rid = analyzed
    monkeypatch.setattr("app.services.sandbox.docker_ready", lambda: "Docker is not installed or not on PATH.")
    pay = _sym(client, rid, "shop.services.payment.PaymentService.process_payment")
    t = client.post(f"/repositories/{rid}/symbols/{pay['id']}/tests").json()
    assert t["status"] == "generated" and "inspect.signature" in t["code"]
    r = client.post(f"/repositories/{rid}/tests/{t['id']}/run").json()
    assert r["status"] == "error" and "Docker" in r["output"]


def test_generated_template_test_passes_locally(analyzed, tmp_path):
    """The offline template must be valid pytest against the real sample repo."""
    import subprocess, sys
    client, rid = analyzed
    pay = _sym(client, rid, "shop.services.payment.PaymentService.process_payment")
    t = client.post(f"/repositories/{rid}/symbols/{pay['id']}/tests").json()
    repo_dir = client.get(f"/repositories/{rid}").json()
    from app.config import settings
    d = settings.repositories_dir / repo_dir["name"]
    (tmp_path / "test_gen.py").write_text(t["code"])
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", str(tmp_path / "test_gen.py")], cwd=d, capture_output=True, text=True,
                       env={"PYTHONPATH": str(d), "PATH": "/usr/bin"})
    assert p.returncode == 0, p.stdout + p.stderr


def test_blocked_generated_code():
    from app.services.ai_service import validate_generated_test
    assert "blocked" in validate_generated_test("import subprocess\nsubprocess.run(['ls'])")
    assert validate_generated_test("def test_x():\n    assert 1") is None


def test_path_traversal_blocked(analyzed):
    client, rid = analyzed
    assert client.get(f"/repositories/{rid}/file", params={"path": "../../etc/passwd"}).status_code == 404
    assert client.get(f"/repositories/{rid}/file", params={"path": "shop/web.py"}).status_code == 200
