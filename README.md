# Legacy Code Intelligence & Impact Analysis Platform

Understand a Python codebase and see what a change will affect before you make it.

```
GitHub repo -> clone -> scan -> parse (AST) -> dependency graph (NetworkX) -> retrieval
            -> explain / ask  ->  impact analysis -> transparent risk score -> characterization tests -> Docker sandbox
```

## Run it

**Backend** (Python 3.11+). From `backend/`:
```
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload
```
API docs: http://localhost:8000/docs  |  tests: `python -m pytest -q`

The app includes email/password signup and login. The frontend stores a short-lived JWT in browser storage and sends it to protected API endpoints. Set `JWT_SECRET_KEY` to a unique, random, persistent value in `backend/.env` before deployment (for example, generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`). If unset, a random key is generated at startup, so existing tokens stop working after a backend restart. `JWT_EXPIRATION_MINUTES` defaults to 60.

To add a public GitHub repository, install Git and make sure `git` is available on `PATH`. Repositories are shallow-cloned into `~/.lci/repositories` by default (outside the project folder, which may be OneDrive-synced). Set `REPOSITORIES_DIR` to use another local, non-synced location. Git clones time out after 10 minutes by default; configure `CLONE_TIMEOUT_SECONDS` if needed.

**Frontend** (Node 18+). From `frontend/`:
```
npm install
npm run dev
```
Open http://localhost:5173 and click **Try the demo shop**.

## Deploy on a VPS with Docker Compose

Use a Linux VPS with Docker Engine and the Docker Compose plugin installed. Copy the project to the server, then from its root:

```sh
cp .env.production.example .env.production
openssl rand -hex 24
openssl rand -hex 32
```

Set the first generated value as `POSTGRES_PASSWORD` and the second as `JWT_SECRET_KEY` in `.env.production`. For HTTPS, point a domain's DNS A/AAAA records at the VPS and set `SITE_ADDRESS` to that domain; Caddy will provision and renew certificates automatically. To try it over plain HTTP by IP first, keep `SITE_ADDRESS=:80`. Open port 80 in the VPS firewall; also open port 443 for HTTPS.

Start or update the services:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

The frontend and API are served through Caddy; PostgreSQL, Redis, and the API are not exposed directly to the internet. PostgreSQL data and cloned repositories are kept in named Docker volumes. View service status/logs with `docker compose --env-file .env.production -f docker-compose.prod.yml ps` and `docker compose --env-file .env.production -f docker-compose.prod.yml logs -f backend worker`.

Back up the `postgres_data` and `repositories_data` volumes before upgrades or server maintenance. The generated-test Docker sandbox is not enabled in this deployment because safely exposing the host Docker socket to the API would grant it broad host control; analysis, auth, and other features continue to work.

**Docker sandbox** (only needed to run generated tests): `docker build -t legacy-sandbox backend/sandbox`

**AI features** (optional): set `LLM_PROVIDER=openai|anthropic|ollama` and the matching key in `backend/.env`.
With `LLM_PROVIDER=none` everything still works from static analysis; explanations are limited to what the code states.

## The demo flow
1. Dashboard -> add any public GitHub repository, or *Explore sample project*.
2. The repository overview shows scan coverage, detected languages, parser limitations, dependency confidence, and a dependency spotlight.
3. Code explorer -> pick `PaymentService.process_payment`.
4. *Explain* (facts vs inferences), *Find dependencies* (React Flow graph), *Impact analysis*
   (`process_payment -> OrderService.checkout -> checkout_controller -> POST /checkout`, related tests, risk factors).
5. *Generate tests* -> review -> *Run in Docker sandbox*.
6. In the Assistant, describe a requested change (for example, *“Change payment to reject zero amounts”*) to get an ordered plan linked to the relevant code and callers. The assistant suggests steps; it does not edit files automatically.

Analysis runs are retained in the Jobs view. Download a code-free JSON summary to save or share results. For GitHub repositories, check whether the default branch has advanced; *Update code & re-analyze* refreshes the local checkout before starting a new run. Python files are analyzed for symbols and dependency links; other recognized languages are counted but not yet parsed.

## Layout
```
backend/app/
  api/routes.py            thin HTTP layer
  services/
    repository_service.py  validate + clone (timeout, no password prompts, cleanup on failure)
    scanner.py             file walk, ignore rules, language
    parser.py              deterministic Python AST extraction (no LLM)
    dependency_resolver.py calls / imports / inherits / contains edges, exact vs heuristic
    graph_service.py       NetworkX queries (callers, callees, neighborhoods)
    impact_service.py      impact report + transparent risk scoring
    retrieval.py           function/class-level chunks with metadata, TF-IDF ranking
    llm_gateway.py         OpenAI / Anthropic / Ollama behind one interface
    ai_service.py          explain, ask, test generation (facts first, LLM second)
    sandbox.py             Docker isolation for generated tests
    pipeline.py, jobs.py   analysis pipeline + job tracking (queued/running/completed/failed)
  worker.py                optional Celery entry point
frontend/src               React + TypeScript + Tailwind, Monaco, React Flow
```

## Honest notes: what differs from the original plan
- **Parsing uses Python's built-in `ast`**, not Tree-sitter. It is exact for Python; Tree-sitter becomes useful when you add other languages (the parser sits behind one function, `parse_python_file`).
- **Search uses TF-IDF, not pgvector embeddings.** Chunks are real functions/classes with the metadata you specified, and `retrieval.get_index` is the seam to swap in embeddings. Expect weak results for vague questions.
- **Database defaults to SQLite** so it runs with zero setup. Postgres: `docker compose up -d postgres`, `pip install -r requirements-prod.txt`, set `DATABASE_URL` (see `.env.example`). The pgvector extension is available in that image but unused for now.
- **Jobs run in a thread pool by default.** Celery + Redis is wired (`USE_CELERY=true`, `celery -A app.worker.celery_app worker`) but I could not test it in my environment.
- **Not built yet:** rate limiting, object storage (repos live on local disk), monitoring. Repository data remains shared among authenticated users; accounts currently provide sign-in, not per-user repository isolation.
- **Call graph limits:** dynamic Python (`getattr`, callbacks, duck typing) can't be resolved statically. Links matched only by method name are marked *heuristic* (dashed in the graph, "~" in lists). Treat impact results as a strong starting point, not proof.
- **Sandbox limits:** the container has no network and no third-party packages, so tests for code that imports external libraries will fail inside it. Docker was not available where I built this, so the sandbox run itself is untested; its failure path (Docker missing) is tested.
- The risk score is a heuristic: six factors, each shown with its points. Edit the thresholds in `impact_service.score_risk`.

## Security choices
Passwords are stored using Argon2, and a signed JWT is required for API routes other than health and authentication. Only `https://github.com/owner/repo` URLs are cloned; repo names are validated; file reads are confined to the repo folder; secrets are redacted before code is sent to an LLM; prompts tell the model that code and comments are data, not instructions; generated tests are syntax-checked and screened for dangerous calls, shown for review, then run only in the sandbox; every query is scoped by repository id.
