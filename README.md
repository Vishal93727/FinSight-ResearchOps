# FinSight ResearchOps

**AI-Powered Financial Research & Quantitative Strategy Operations Platform**

FinSight ResearchOps connects financial research, reproducible quantitative experiments, model governance, controlled paper execution and measured outcomes through a traceable Research-to-Outcome Ledger.

## Product boundary

- Initial coverage: US-listed equities and ETFs, public SEC filings, and permitted historical market data.
- Implemented research/quant slice: evidence-linked hypothesis review, immutable feature versions, reproducible baseline experiments, leakage-aware features, holdout/walk-forward evaluation, pinned benchmark analytics, vectorized and event-driven portfolio accounting, deterministic risk reviews and local/optional MLflow run tracking. Phase 3 adds document and research-question jobs with idempotency/retry, source/chunk provenance, hybrid lexical/vector retrieval with MMR, optional PostgreSQL pgvector/HNSW storage and backfill, optional cross-encoder reranking, provider-versioned embeddings (deterministic by default, optional SentenceTransformer), deterministic or optional LangGraph workflows with persisted per-node checkpoints and explicit evidence-preserving resume, extractive or optional LangChain OpenAI evidence synthesis, claim-level lexical/numeric evidence screening plus independent human review, and snapshot/feature-version-pinned Ridge, Random Forest, XGBoost, LightGBM and PyTorch LSTM evaluation with queued jobs, model comparison and transparent lexicon sentiment plus an optional FinBERT probability adapter.
- No live/real-money trading endpoint and no investment-advice claims.
- The deterministic risk engine is independent of LLM-generated outputs.
- External market-data, SEC, LLM and paper-broker services are accessed through adapters.

## Workspace structure

```text
FinSight_ResearchOps/
├── apps/
│   ├── api/                 # FastAPI entrypoint / compatibility launcher
│   ├── worker/              # Celery worker entrypoint
│   └── web/                 # React + TypeScript + Vite UI
├── src/finsight/
│   ├── core/                # Settings, JSON logging, security, shared schemas
│   ├── identity/            # Users, roles and identity contracts
│   ├── infrastructure/      # Database sessions, ORM registry, storage/messaging
│   ├── market_data/         # Providers, ingestion, OHLCV/SEC contracts and models
│   ├── research/            # Hypotheses and bounded research workflows
│   ├── features/            # Feature definitions and leakage-aware engineering
│   ├── experiments/         # Versioned experiment configs and run records
│   ├── documents/           # Safe parsers, chunking, hashing embeddings and hybrid retrieval
│   ├── models/              # Baseline, XGBoost, PyTorch and sentiment packages
│   └── backtesting/         # Next-bar, cost-aware simulation engine
├── backend/app/api/         # Versioned FastAPI route adapters during migration
├── backend/tests/           # Existing API and service acceptance tests
├── migrations/              # Root Alembic environment and version history
├── configs/                 # Environment configuration templates
├── sql/                     # Schema and analytics SQL areas
├── infra/                   # Docker, monitoring and deployment assets
├── data/                    # Local runtime data (ignored by Git)
├── docs/                    # Architecture, data model, security and plan
├── references/cloned/       # Isolated upstream repositories (git-ignored)
├── archives/                # Original starter ZIPs and plan
├── PROJECT_PROGRESS.md      # Current phase/step checkpoint
└── BUILD_LOG.md              # Append-only implementation/test log
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Engine + Docker Compose plugin (recommended local full-stack setup)
- Git (for fetching reference repositories)

## Start with Docker Compose

```bash
cp .env.example .env
# Edit .env: set unique POSTGRES_PASSWORD, JWT_SECRET and GRAFANA_ADMIN_PASSWORD values, then replace SEC_EDGAR_USER_AGENT with a monitored contact.
docker compose config
docker compose up --build -d
```

Compose starts PostgreSQL/pgvector, Redis, FastAPI, Celery worker, React/Nginx, OpenTelemetry Collector, Prometheus and Grafana. The API container runs `alembic upgrade head` before starting. The web container proxies `/api` to the API service, so the browser uses same-origin API requests.

- Web UI: http://localhost:5173
- API docs: http://localhost:5173/docs
- API liveness: http://localhost:5173/health
- API readiness: http://localhost:5173/api/v1/health/ready
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- API Prometheus metrics (internal scrape target): `http://localhost:8000/metrics`

Bootstrap an administrator in a one-off API container shell:

```bash
docker compose exec api python backend/scripts/create_admin.py --email admin@example.com --name "Platform Admin"
```

The command prompts for the password; it is not passed as a command-line argument or stored in the repository.

Self-registration creates Research Analyst users only. An admin or Quant Researcher can create instrument catalogue entries from the API.

## Local backend development

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -e '.[dev,observability]'
cp .env.example .env
# For local backend-only use, set DATABASE_URL=sqlite:///./finsight_dev.db in .env.
alembic upgrade head
PYTHONPATH=src:backend uvicorn app.main:app --app-dir backend --reload
```

For a local PostgreSQL/Redis backend use Compose services, then set `DATABASE_URL` and `REDIS_URL` as shown in `.env`.

## Optional Phase 4 reinforcement learning runtime

To execute PPO/SAC training, install the optional ML/RL dependencies with `pip install -e '.[ml,rl]'` (or set `PYTHON_EXTRAS=ml,pdf,rl` in `.env` before rebuilding the Docker API and worker images). The worker also requires the configured Redis/Celery and database services, a READY Parquet market-data snapshot, and a feature-set version created from that exact snapshot. The RL Strategy Lab queues training and displays job status, retry, out-of-sample metrics and same-lineage comparisons. Merely receiving `202 Accepted` confirms queue acceptance, not training completion. See [Phase 4 operations](docs/operations/PHASE4_OPERATIONS.md) for the dataset requirements, worker startup, chronological training/evaluation protocol, governance gates and paper-only workflow.

## Optional Phase 3 AI providers

The default configuration is offline and extractive. Failed research reports can be resumed from their last committed checkpoint without changing the evidence chunk set. To enable learned local embeddings, cross-encoder reranking and LangGraph/LangChain synthesis, install `pip install -e '.[semantic,research-ai]'` and configure `DOCUMENT_EMBEDDING_PROVIDER=sentence_transformers`, `DOCUMENT_RERANKER=cross_encoder`, `RESEARCH_WORKFLOW_ENGINE=langgraph`, and/or `RESEARCH_SYNTHESIS_PROVIDER=langchain_openai`. Cache the configured SentenceTransformer/cross-encoder weights before use and provide `OPENAI_API_KEY` through a secret manager/environment only; never commit the key. Re-ingest documents after changing the embedding provider/model. To enable PostgreSQL ANN retrieval, set `DOCUMENT_VECTOR_BACKEND=pgvector`, keep the configured embedding size at 384, apply `alembic upgrade head`, and backfill existing chunks with `python scripts/backfill_pgvector_embeddings.py` (see [Phase 3 operations](docs/operations/PHASE3_OPERATIONS.md)).

For the optional pretrained FinBERT classifier, install `pip install -e '.[finbert]'`; it lazily loads `ProsusAI/finbert` model weights and returns class probabilities. The lexicon remains the default.

These optional services do not override the deterministic risk engine or the independent report-review checkpoint. Citation-ID validation does not prove semantic entailment.

## Frontend development

```bash
cd apps/web
npm install
npm run dev
npm run build
```

The Vite dev server proxies `/api`, `/health` and `/docs` to `http://localhost:8000`. Set `VITE_API_BASE_URL` only when using a different reverse-proxy/API topology.

## API surface

| Method | Endpoint | Permission |
|---|---|---|
| POST | `/api/v1/auth/register` | Self-registration; Research Analyst only |
| POST | `/api/v1/auth/login` | Public login |
| GET | `/api/v1/auth/me` | Authenticated |
| GET/POST | `/api/v1/instruments` | Authenticated read; ADMIN/QUANT_RESEARCHER write |
| GET | `/api/v1/providers` | Authenticated |
| POST | `/api/v1/data/ingestions/market` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER (JSON OHLCV) |
| POST | `/api/v1/data/ingestions/market/csv` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER (CSV upload) |
| GET | `/api/v1/data/snapshots` | Authenticated |
| POST | `/api/v1/data/ingestions/sec/{cik}` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER |
| GET | `/api/v1/audit/events` | ADMIN/RISK_REVIEWER |
| GET | `/api/v1/users` | ADMIN |
| PATCH | `/api/v1/users/{id}/roles` | ADMIN |
| POST | `/api/v1/documents/upload` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER; synchronous bounded parse, hash, chunk and index |
| POST | `/api/v1/documents/upload/jobs` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER; stage and queue idempotent document ingestion |
| GET | `/api/v1/documents` | Authenticated; list indexed research documents |
| GET | `/api/v1/documents/{id}` | Authenticated; inspect document provenance metadata |
| POST | `/api/v1/research/ask` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER; synchronous hybrid retrieval and citation-linked report for small/local workflows |
| POST | `/api/v1/research/ask/jobs` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER; idempotently queue evidence-grounded research synthesis and checkpoint creation |
| GET | `/api/v1/research/reports` | Authenticated; list report status, citations and workflow traces |
| GET | `/api/v1/research/reports/{id}/checkpoints` | Authenticated; inspect persisted per-node workflow checkpoints |
| POST | `/api/v1/research/reports/{id}/decision` | ADMIN/RISK_REVIEWER; independent report approval/rejection |
| POST | `/api/v1/ml/evaluations` | ADMIN/QUANT_RESEARCHER; synchronous bounded chronological model evaluation |
| POST | `/api/v1/ml/evaluations/jobs` | ADMIN/QUANT_RESEARCHER; idempotently queue model evaluation in Celery |
| GET | `/api/v1/ml/evaluations` | Authenticated; list model metrics and reproducibility records |
| GET | `/api/v1/ml/evaluations/compare?snapshot_id=...&feature_set_version_id=...` | Authenticated; rank evaluations on the same snapshot/feature lineage by RMSE |
| POST | `/api/v1/ml/sentiment` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER; lexicon or optional FinBERT sentiment |
| POST | `/api/v1/research/hypotheses` | ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER; create evidence-linked draft |
| GET | `/api/v1/research/hypotheses` | Authenticated; list hypotheses |
| POST | `/api/v1/research/hypotheses/{id}/submit-review` | Owner/ADMIN; submit a draft for review |
| POST | `/api/v1/research/hypotheses/{id}/decision` | ADMIN/RISK_REVIEWER; approve or reject a hypothesis under review |
| POST/GET | `/api/v1/features/versions` | ADMIN/QUANT_RESEARCHER create; authorized research roles read |
| POST/GET | `/api/v1/experiments` | ADMIN/QUANT_RESEARCHER create; authorized research roles read |
| POST | `/api/v1/experiments/{id}/runs` | ADMIN/QUANT_RESEARCHER; queue baseline run; supports `Idempotency-Key` |
| GET | `/api/v1/experiments/{id}/runs` | Authorized research roles; inspect run status and metrics |
| GET | `/api/v1/experiments/{id}/runs/comparison` | Compare completed runs, benchmark-relative metrics and risk decisions |
| GET | `/api/v1/experiments/{id}/runs/{run_id}/risk-review` | Read persisted deterministic risk findings |
| POST | `/api/v1/jobs/ping` | Authenticated; asynchronous queue smoke test |
| GET | `/api/v1/jobs` and `/api/v1/jobs/{id}` | Job owner or ADMIN; list/inspect queued work |
| POST | `/api/v1/jobs/{id}/retry` | Job owner or ADMIN; retry a queue-dispatch failure without creating a duplicate job |
| GET | `/api/v1/health` | Public liveness |
| POST | `/api/v1/rl/evaluations/jobs` | ADMIN/QUANT_RESEARCHER; queue PPO/SAC evaluation on a matching READY Parquet snapshot + feature version |
| GET | `/api/v1/rl/evaluations` and `/api/v1/rl/evaluations/comparison` | Authorized readers; inspect results and compare exact same-lineage OOS evaluations |
| GET/POST | `/api/v1/governance/models` | Authorized readers list; ADMIN/QUANT_RESEARCHER register a model candidate |
| GET | `/api/v1/governance/models/{id}/risk-review` and `/decisions` | Inspect deterministic risk and independent reviewer decision history |
| POST | `/api/v1/governance/models/{id}/decision` | ADMIN/RISK_REVIEWER; independent approval/rejection; authors cannot approve their own models |
| POST | `/api/v1/governance/models/{id}/promote` and `/rollback` | ADMIN only; promotion requires APPROVED + deterministic risk PASS |
| POST/GET | `/api/v1/execution/accounts` | Create/list internal paper accounts |
| POST/GET | `/api/v1/execution/accounts/{id}/orders` | Simulated orders from explicit reference price; no external/live broker |
| GET | `/api/v1/execution/accounts/{id}/summary` and `/audit` | Inspect paper cash, equity, positions, fills, ledger and audit history |
| POST | `/api/v1/execution/accounts/{id}/kill-switch` and `/reconcile` | Halt new orders and reconcile paper ledger; repair/deactivation are admin-restricted |
| POST/GET | `/api/v1/feedback/outcomes` | ADMIN/QUANT_RESEARCHER/PORTFOLIO_ANALYST create; authorized readers inspect forecast vs realised outcomes; model/run/account links are owner- and snapshot-lineage-checked |
| GET | `/api/v1/feedback/summary` | Authorized readers; MAE/RMSE/bias/directional accuracy, latest strategy snapshots, drift and proposals |
| POST/GET | `/api/v1/feedback/strategies/evaluate` and `/strategies` | ADMIN/QUANT_RESEARCHER/PORTFOLIO_ANALYST evaluate; authorized readers inspect benchmark-relative strategy metrics |
| POST | `/api/v1/feedback/strategies/evaluate-run` | Import a succeeded Phase 2 experiment run after artifact path and SHA-256 verification; requires Parquet support |
| POST/GET | `/api/v1/feedback/drift/check` and `/drift-assessments` | ADMIN/QUANT_RESEARCHER/RISK_REVIEWER; PSI/KS feature diagnostics |
| POST/GET | `/api/v1/feedback/suggestions/generate` and `/suggestions` | Generate deduplicated evidence-linked proposals; ADMIN/QUANT_RESEARCHER decide ACCEPTED/DISMISSED |
| GET | `/api/v1/operations/summary` | ADMIN/RISK_REVIEWER/PORTFOLIO_ANALYST/READ_ONLY_VIEWER; database counts, Redis and Celery worker health, stale-job and failure metadata |
| POST | `/api/v1/operations/recover-stale-jobs` | ADMIN only; dry-run by default, explicit confirmed requeue |
| GET | `/metrics` | Prometheus scrape endpoint; low-cardinality route-template labels |
| GET | `/api/v1/health/ready` | Public readiness |

See [`docs/api/README.md`](docs/api/README.md) for request contracts, roles, lifecycle states and response behaviour. See [`docs/operations/PHASE3_OPERATIONS.md`](docs/operations/PHASE3_OPERATIONS.md) for pgvector, workers and optional research providers, and [`docs/operations/PHASE4_OPERATIONS.md`](docs/operations/PHASE4_OPERATIONS.md) for RL, model governance and paper-only execution.

## Phase 5 — outcome feedback and production operations

The app includes dedicated **Feedback & Monitoring** and **Operations & Administration** pages. Alongside the original eight product pages—Overview, Research Workspace, Research Intelligence, Experiment Lab, Strategy & Backtests, RL Strategy Lab, Model Governance and Paper Execution—the two Phase 5 pages complete a ten-page navigation experience. Feedback records prediction-versus-realised outcomes with optional model/experiment/paper-account lineage; imports strategy metrics from a succeeded backtest run after verifying its equity-curve hash; calculates MAE/RMSE/bias/directional diagnostics; screens numeric feature drift using PSI/KS; and creates deduplicated, human-reviewed follow-up suggestions. Operations displays database-backed job/run/order/model/account counts, distinguishes Redis connectivity from Celery worker liveness, reports stale/recently failed jobs and supports an Admin-only stale-job dry-run/confirmed requeue workflow.

The Phase 5 dashboard uses [`POST /api/v1/feedback/strategies/evaluate-run`](docs/api/README.md) to connect a persisted Phase 2 equity curve to the outcome monitoring ledger. The OpenAPI feedback/operations routes include outcomes, manual and run-based strategy evaluation, drift, suggestions, recovery, and summary views.

See [`docs/PHASE5_OPERATIONS.md`](docs/PHASE5_OPERATIONS.md) for implemented contracts, alert rules, metrics, Docker, worker recovery and backup/restore procedures. Interview demo and engineering Q&A scenarios are in [`docs/interview/DEMO_SCENARIOS.md`](docs/interview/DEMO_SCENARIOS.md). PostgreSQL logical backup uses `scripts/backup_postgres.sh`, verification uses `scripts/verify_backup.sh`, and destructive restore requires `CONFIRM_RESTORE=YES` through `scripts/restore_postgres.sh`. App-data archive validation is performed by `scripts/validate_data_archive.py` before backup/restore operations.

GitHub Actions includes backend/frontend/Compose CI, Python and npm dependency audits, filesystem vulnerability/secret/config scanning, Dependabot and tag-triggered GHCR container releases. The Compose monitoring stack provides Prometheus, Grafana, alert rules and optional OTLP traces.

## Verify backend

```bash
pytest -q
python -m compileall -q backend src apps migrations
ruff check backend src apps migrations
```

Run migrations against a new database with `alembic upgrade head`; use `alembic downgrade base` only for disposable development databases.

## GitHub reference repositories

Reference repositories are isolated under `references/cloned/` and are not merged wholesale. Run `bash scripts/clone_references.sh --all` for the normal set, or `--all-including-openbb` to also fetch the very large OpenBB repository. Review `references/REPOSITORY_CATALOG.md` and `docs/SOURCES_AND_ATTRIBUTION.md` before reuse.

## Progress

Read `PROJECT_PROGRESS.md` and the latest entry in `BUILD_LOG.md` before resuming. Phase 1–4 source implementations are in place. Phase 5 source, API, UI, migrations, acceptance tests, CI/CD configuration, metrics/tracing, Docker monitoring stack, alert rules, backup/restore scripts and operator/interview documentation are implemented and offline-verified. Live Docker/PostgreSQL/Redis/Celery, browser production build, real backup/restore drill and external security scans must still be verified in a service-enabled CI/deployment environment; they are not claimed as executed in this workspace. Phase 3 includes synchronous and queued document ingestion, bounded chunking, provider-versioned embeddings, hybrid retrieval/MMR, optional pgvector/HNSW and cross-encoder paths, extractive or optional LLM reports with per-sentence claim screening, evidence-preserving checkpoint resume and independent review, queued snapshot/feature-lineage-pinned supervised ML, model comparison and sentiment adapters. The default answer remains extractive; live LLM, LangGraph, learned-embedding and FinBERT model execution is not claimed as validated. PostgreSQL/Redis/Celery/PyArrow runtime and Vite/browser production checks remain deployment validation gates.
