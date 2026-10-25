import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config, db as dbmod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fresh SQLite DB + fresh repositories dir per test; jobs run synchronously."""
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.setattr("app.services.jobs.SessionLocal", Session)
    monkeypatch.setattr(config.settings, "repositories_dir", tmp_path / "repos")
    monkeypatch.setattr(config.settings, "llm_provider", "none")
    monkeypatch.setattr(config.settings, "jwt_secret_key", "test-signing-key-with-more-than-32-bytes")
    dbmod.Base.metadata.create_all(engine)

    from app.main import app

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_db] = override

    class Sync:  # run submitted jobs immediately
        def submit(self, fn, *a):
            fn(*a)

    monkeypatch.setattr("app.services.jobs._executor", Sync())
    with TestClient(app) as c:
        response = c.post("/auth/signup", json={"email": "test@example.com", "password": "test-password"})
        assert response.status_code == 201
        c.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield c
    app.dependency_overrides.clear()
