# FinSight ResearchOps — Project Progress

Last updated: 2026-11-02

## Overall status

- [x] Five-phase implementation roadmap agreed.
- [x] Approved 26-section project blueprint included in `docs/project_blueprint/`.
- [x] Existing `FinSight_AI_Foundation_v0.1.zip` extracted as the editable starting codebase (not built from scratch).
- [x] Original starter/demo/DocuMind archives preserved under `archives/`.
- [x] Live project documentation re-scoped to FinSight ResearchOps; inherited source docs retained separately under `docs/inherited_foundation/`.
- [x] GitHub repository catalogue and clone scripts created for 16 references.
- [ ] GitHub source repositories cloned: **0 of 16 currently present**. *(Update 2026-11-07: five of the repositories were supplied as ZIP archives and studied/integrated; they are not Git clones. See the final checkpoint.)* The script's `--all` mode clones 15; `--all-including-openbb` also attempts the very large OpenBB repository (16 total).

## Phase status

| Phase | Name | Status |
|---|---|---|
| 1 | Platform Foundation & Data Layer | Implementation largely in place; external runtime validation pending |
| 2 | Research & Quantitative Experiment Core | **Implementation complete** — research/feature lineage, reproducible runs, baseline and walk-forward evaluation, benchmarks, portfolio accounting, deterministic risk, tracking and both Phase 2 UI pages implemented; live service/build verification remains environment-dependent |
| 3 | Financial Research AI & Advanced ML | **Implementation complete (offline-verified)** — document intelligence, hybrid RAG, optional pgvector/reranking/learned embeddings, deterministic/optional LangGraph workflow, durable node checkpoints and explicit resume, claim screening/HITL, supervised ML, FinBERT adapter, and idempotent Celery jobs for document ingestion, research Q&A and ML evaluation; live external integration validation remains |
| 4 | Governance, RL & Paper Execution | **Source/API/UI implementation complete; offline acceptance verified; live runtime validation pending** |
| 5 | Outcome Feedback & Production Readiness | **Implementation complete; offline acceptance verified; live deployment and restore validation pending** |

## Previous verified checkpoint — Phase 3 source implementation

- **Automated tests:** 84 passed, 2 skipped. Skips: opt-in live PostgreSQL/Redis tests and the PyArrow Parquet integration test (PyArrow is not installed in this environment).
- **Build/structure checks:** Python compilation passed; SQLite Alembic upgrade to `0006_phase3_evidence_vector_checkpoints`, downgrade to `0005`, and re-upgrade passed; PostgreSQL offline SQL for migration `0005 -> 0006` includes `vector(384)` and the HNSW cosine index; FastAPI OpenAPI includes 42 paths; TypeScript/TSX syntax transpilation passed for 10 files; TOML/YAML and Bash syntax checks passed.
- **Runtime gates still open:** no Docker executable, live PostgreSQL/Redis/Celery, PyArrow, frontend `node_modules`, model weights or LLM credentials were available. The Vite production build, live pgvector search/backfill, queued worker execution, pretrained model execution and live OpenAI/LangGraph calls are not claimed as verified.
- **Phase 3 status meaning:** source implementation and offline acceptance are complete. External runtime/provider validation is deployment work; semantic claim entailment and domain calibration of FinBERT remain limitations, not features claimed as solved.


## Latest verified checkpoint — Phase 4 governance, RL and paper execution

- **Phase 4 source implementation:** Gymnasium portfolio environment; PPO/SAC Stable-Baselines3 training adapter; target-free point-in-time feature observations; training-only feature scaling; strict chronological out-of-sample evaluation; trading costs and artifact hashing; durable/idempotent RL Celery job queue and retry; model registry and artifact integrity checks; deterministic model risk review; independent reviewer approval; admin-only promotion/rollback; paper accounts; simulated orders/fills; fee/slippage accounting; portfolio positions/cash/ledger/audit; deterministic post-trade exposure checks; kill switch and fill-history reconciliation.
- **Frontend:** `RL Strategy Lab` is registered in `apps/web/src/App.tsx` and mounted from `apps/web/src/pages/ReinforcementLearningPage.tsx`. The page selects a READY Parquet snapshot and feature version from the same snapshot, queues PPO/SAC, shows job status/retry, completed OOS metrics and exact-lineage comparisons. `Model Governance` and `Paper Execution` pages are also mounted in the same app navigation. Navigation and action controls match the backend role matrix: Research Analysts do not see governance/paper pages whose list APIs deny them; candidate registration, paper kill-switch, reconciliation, repair and read-only controls are role-gated.
- **OpenAPI:** 57 paths total. Phase 4 includes 15 distinct OpenAPI paths / 18 HTTP operations, all inspected and contract-tested: RL job creation/list/comparison; model list/register/risk-review/decision-history/decision/promote/rollback; paper account list/create/summary/orders/kill-switch/reconcile/audit. No live broker route or `/live` path exists.
- **Automated tests:** full suite reached exit code 0 with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src:backend pytest -p no:cacheprovider -ra -o addopts=''`; 100 tests collected, 98 passed and 2 skipped. Skips: opt-in live PostgreSQL/Redis integration and PyArrow Parquet integration (PyArrow unavailable). The `-p no:cacheprovider` flag avoids a pytest process-shutdown hang seen with the default cache provider in this sandbox.
- **Focused Phase 4 tests:** 14/14 pass (8 governance/paper execution, 2 OpenAPI contract, 4 RL feature/scaler tests).
- **Migrations:** SQLite Alembic upgrade to `0007_phase4_governance_rl_paper_execution`, assertion of all nine Phase 4 tables, downgrade to `0006_phase3_evidence_vector_checkpoints`, and re-upgrade to `0007`: passed.
- **Static checks:** `python -m compileall -q backend src apps migrations`: passed. TypeScript/TSX syntax transpilation: 14 source files, zero diagnostics. This is syntax-only, not a complete `tsc` typecheck or Vite build.
- **Runtime gates still open:** Docker and live PostgreSQL/Redis/Celery unavailable; Gymnasium and Stable-Baselines3 are not installed, so no PPO/SAC model was trained here; PyArrow missing, so true Parquet artifact generation remains untested; frontend `node_modules` are missing, so npm typecheck/Vite production build/browser acceptance remains open.
- **Safety boundary:** paper broker accepts explicit simulation reference prices and writes internal simulated fills only. No live broker adapter, account credential integration, or real-money order route was added.

## Phase 1 — implemented in this workspace

### Repository and engineering foundation

- [x] Rebranded Python package and FastAPI service as `finsight-researchops`.
- [x] Typed environment configuration, production secret validation and JSON logging.
- [x] Dockerfile and multi-service Compose configuration for PostgreSQL/pgvector, Redis, FastAPI, Celery worker and React frontend.
- [x] GitHub Actions CI workflow for backend checks, PostgreSQL/Redis-backed migrations/readiness and frontend build.
- [x] Root Git workspace, ignore rules, source attribution and project progress/build logs.

### Backend, database and identity

- [x] FastAPI versioned API and OpenAPI docs.
- [x] SQLAlchemy entities for users, roles, role assignments, instruments, providers, market snapshots, SEC ingestion records, jobs and append-only audit events.
- [x] Alembic initial migration (`0001_initial_researchops`) with seeded six-role catalogue and initial providers.
- [x] Scrypt password hashing, expiring JWT access tokens and backend-enforced RBAC.
- [x] Analyst-only self-registration, login/me, admin-only user listing and role assignment.
- [x] Secure first-admin CLI bootstrap.
- [x] Instrument catalogue read/write endpoints; writes restricted to ADMIN/QUANT_RESEARCHER.
- [x] Provider catalogue endpoint.

### Financial data ingestion and jobs

- [x] SEC EDGAR company-submissions adapter and append-only hashed ingestion records.
- [x] JSON OHLCV ingestion endpoint with date/duplicate/OHLC validation.
- [x] CSV OHLCV upload endpoint with file-size, extension, column, row-count and OHLCV validation.
- [x] Content-addressed Parquet persistence implementation and SHA-256 manifest, using the declared PyArrow dependency.
- [x] Snapshot listing endpoint and audit logging for identity/data actions.
- [x] Persisted job records, idempotency key handling, queue enqueue adapter, worker task and owner/admin job status endpoint.
- [x] Liveness and DB/Redis readiness endpoints; request IDs and response-safe exception handling.

### Frontend

- [x] React + TypeScript + Vite source scaffold.
- [x] Sign-in interface.
- [x] ResearchOps Overview showing instruments, providers and data snapshots.
- [x] Research Workspace for SEC submissions and OHLCV CSV upload.
- [x] Experiment Lab source UI for hypotheses/review, feature versioning, experiment setup and run status.
- [x] Strategy & Backtest Lab source UI for cross-experiment completed-run comparison and risk-review inspection.
- [x] Operations page for account roles, readiness, instrument catalogue and admin role management.

## Verification completed in the current environment

- Latest full suite after Phase 2 completion increment: **43 passed, 2 skipped** (details in the 2026-11-02 Phase 2 completion checkpoint below).
  - Parquet writer integration test skipped because PyArrow is not installed in this sandbox. It will run when project dependencies are installed.
  - Live PostgreSQL/Redis readiness test skipped unless `FINSIGHT_RUN_LIVE_CHECKS=1` and both services are available.
- `python -m compileall -q backend`: passed.
- SQLite Alembic migration upgrade/current: passed; upgrade/downgrade/upgrade was also exercised earlier.
- `PYTHONPATH=backend python backend/scripts/create_admin.py --help`: passed.
- `bash -n scripts/clone_references.sh` and `bash -n scripts/verify_workspace.sh`: passed.
- Frontend TypeScript/TSX syntax transpilation: zero syntax diagnostics.

## Remaining blockers before Phase 1 can honestly be marked complete

These are environment/runtime verification gaps, not features to silently treat as passed:

1. The sandbox has no Docker executable; PostgreSQL/Redis Compose startup and the Celery worker have not been run.
2. `psycopg`, Celery/Redis client and PyArrow are declared in `pyproject.toml` but not installed in this sandbox. Package installation failed because the package index could not be reached. The SQLite migration and API tests passed without them.
3. PyArrow Parquet write/read test is present but skipped locally. A true Parquet artifact has not yet been verified here.
4. `npm install` timed out because package-registry networking is unavailable. React/Vite dependencies are declared, and source syntax passes, but `npm run build` and browser end-to-end checks remain unverified.
5. SEC integration was tested with a mocked adapter; a real SEC request requires working outbound access and a real monitored `SEC_EDGAR_USER_AGENT` contact value.
6. Live Postgres/Redis readiness and Celery queue execution must be verified after dependencies/services are available.

## GitHub reference clone count

- Clone-script catalogue: **16 repositories**.
- Actually cloned into `references/cloned/`: **0**.
- `bash scripts/clone_references.sh --all`: attempts 15 repositories (4 primary, 4 focused/extended, 6 larger study references and the user's DocuMind repository); excludes OpenBB.
- `bash scripts/clone_references.sh --all-including-openbb`: attempts all 16, including very large OpenBB.
- GitHub download-host/network access failed earlier in this sandbox. Do not describe these repositories as downloaded until `references/cloned/<name>/.git` exists.

## Exact next step to close Phase 1

On a machine with internet, Docker Engine/Compose, Node.js 20+ and Python 3.11+:

1. Install dependencies with `pip install -e '.[dev]'` and `cd apps/web && npm install`.
2. Copy `.env.example` to `.env`; set a strong unique `POSTGRES_PASSWORD`, `JWT_SECRET`, and real monitored SEC contact email.
3. Run `docker compose up --build -d` and verify PostgreSQL/Redis/API/worker/frontend health.
4. Run `pytest -q`, `ruff check backend`, `npm run build`, test a CSV-to-Parquet snapshot, SEC submissions fetch, role enforcement and queued worker ping.
5. Resolve every failure, update this file and `BUILD_LOG.md` with actual outputs, then mark Phase 1 complete.

**Current resume point:** Phase 1 implementation is in place with environment-dependent runtime checks outstanding. Phase 2 development is proceeding in parallel; Phase 1 must still be runtime-verified before any production-readiness claim.

## Repository structure alignment checkpoint — 2026-11-02

The React UI is located at `apps/web/`; Compose and CI paths point to it. The API/worker launchers in `apps/` continue to delegate to the HTTP route and Celery task adapters under `backend/app`, while the domain logic being migrated now lives in `src/finsight/`. The canonical package layout is installable under the `src/` package discovery configuration.

Structure audit: requested paths present. Latest earlier test result at this checkpoint: 26 passed, 2 skipped; see the Phase 2 run-execution checkpoint below for the current result. Python compileall and shell syntax checks passed. GitHub references: 16 catalogued, 0 cloned.

The selected core, identity, database, market-data and migration modules have now been moved into their canonical locations. See the 2026-11-02 migration checkpoint below for the exact module map and verification.


## Controlled domain and Alembic migration — 2026-11-02

### Canonical module locations

- Core: `src/finsight/core/config.py`, `logging.py`, `security.py`, and shared `schemas.py`.
- Identity: `src/finsight/identity/models.py` and `contracts.py`.
- Database: `src/finsight/infrastructure/database/base.py`, `mixins.py`, `session.py`, and `models.py`.
- Market data: `src/finsight/market_data/providers/sec_edgar.py`, `ingestion/service.py`, `contracts/ingestion.py`, and `models.py`.
- Alembic: root `migrations/env.py`, `migrations/script.py.mako`, and `migrations/versions/`.
- API route adapters were updated to import the canonical core, identity, database and market-data modules directly.
- Historic `backend/app/core`, `db`, `models`, adapter and market-data schema/service imports remain thin compatibility shims. They are not the source of truth.
- `pyproject.toml` now discovers both `src/finsight*` and the transitional `backend/app*` packages. `alembic.ini`, Docker build context and CI migration paths point to root migrations.

### Phase 2 — first working increment

- Added evidence-linked research hypotheses with DRAFT -> UNDER_REVIEW -> APPROVED/REJECTED flow with risk-review/admin decision, version incrementing and audit events.
- Added immutable feature-set versions pinned to a READY market-data snapshot and SHA-256 definition fingerprint.
- Added experiment specifications tied to an APPROVED hypothesis, READY dataset snapshot and a matching feature-set version. Experiment config is strict, canonicalized and SHA-256 fingerprinted.
- Added chronological train/validation/test window validation and a purged calendar gap covering the prediction horizon plus embargo. Experiment windows must be covered by the source snapshot.
- Added OHLCV feature construction (returns, momentum, moving-average ratios, rolling volatility and volume change) with chronological sorting, duplicate/invalid OHLC rejection and next-session return target separation.
- Added deterministic buy-and-hold and moving-average-crossover signal functions.
- Added long-only baseline backtest engine. Signals formed at close(t) are applied from the next bar; turnover incurs explicit commission and slippage; summary includes total/annualized return, volatility, Sharpe, drawdown, turnover and estimated costs.
- Added Alembic revision `0002_research_experiment_foundation` for hypotheses, feature-set versions, experiments and experiment-run records.

### Verification from this checkpoint

- `python -m pytest -q`: **26 passed, 2 skipped**.
- `python -m compileall -q backend src apps migrations`: passed.
- Alembic lifecycle on SQLite: upgrade to `0001_initial_researchops` (confirmed Phase 2 tables absent), upgrade to head, downgrade to Phase 1 revision, re-upgrade to head; all passed. Final `alembic current`: `0002_research_experiment_foundation (head)`.
- `setuptools.find_namespace_packages(where="src")` includes `finsight` and its modules.
- `bash -n scripts/clone_references.sh scripts/verify_workspace.sh`: passed.
- `ruff` is not installed in this sandbox; lint command was attempted and could not run.
- Docker/PostgreSQL/Redis, Celery queue, real SEC network, PyArrow Parquet and frontend npm build remain unverified in this environment. The two pytest skips remain the previously documented PyArrow and opt-in live-service checks.

### Remaining Phase 2 work

1. Verify Celery/Redis dispatch and real Parquet artifact production end-to-end in a provisioned runtime.
2. Add MLflow tracking and baseline model evaluation/benchmark comparisons.
3. Add walk-forward split runner, benchmark alignment, event/portfolio accounting and richer fill/cost models.
4. Add deterministic experiment/strategy risk review and temporal-integrity acceptance tests for the complete pipeline.
5. Expand Experiment Lab with benchmark comparison, complete run artifacts and Strategy & Backtest Lab views; perform a real Vite build and browser acceptance test.

**Status at the foundation checkpoint:** requested module/migration relocation was implemented. Phase 2 had started with test-backed foundations; the later run lifecycle and final implementation completion checkpoints below supersede this earlier state. Phase 1 remains pending external runtime validation.


## Historical checkpoint: Phase 2 run execution and Experiment Lab — 2026-11-02

### Implemented in this increment

- Added `ExperimentRun` idempotency key persistence and unique `(experiment_id, idempotency_key)` index through Alembic revision `0003_experiment_run_idempotency`.
- Added `POST /api/v1/experiments/{id}/runs` with strict key validation, deterministic seed selection, queue-failure state and safe retry semantics; repeating a successful enqueue request with the same key returns the existing run without dispatching another task.
- Added `GET /api/v1/experiments/{id}/runs` for authorized run-status inspection.
- Added a Celery task `finsight.experiments.run_baseline` that loads the READY snapshot, calls the pure baseline runner, and persists metrics JSON plus an equity-curve Parquet artifact with dataset/config fingerprints. Task code is present but not runtime-executed here because Celery, PyArrow, Redis and PostgreSQL services are unavailable.
- Added a pure baseline experiment runner that enforces the configured test holdout window.
- Added an Experiment Lab React page with hypothesis creation/submission/role-gated approval, feature-set version creation, date-window experiment setup, run submission and run metrics/status display. Added the page to the app navigation.
- Added acceptance tests for run API idempotency, queue-failure retry, run listing, holdout-only evaluation and rejection of non-finite prices/market values.
- Added finite-number checks to OHLCV contracts, feature engineering and the backtest input validation.

### Verification

- `python -m pytest -q`: **29 passed, 2 skipped**. The skips remain the PyArrow snapshot integration and opt-in live Postgres/Redis check.
- `python -m compileall -q backend src apps migrations`: passed.
- TypeScript/TSX `transpileModule` syntax validation across all frontend source files: passed with zero syntax diagnostics. This is syntax-only; `npm run build`/full TypeScript type-check was not run because `apps/web/node_modules` is absent and package-registry network access is unavailable.
- Alembic SQLite lifecycle: revision `0002` confirmed that `experiment_runs` does not yet contain `idempotency_key`; upgrade to `head` (`0003_experiment_run_idempotency`) added the column and unique index; downgrade to `0002` removed them; re-upgrade to `head` passed.
- Shell syntax: `bash -n scripts/clone_references.sh scripts/verify_workspace.sh` passed.

### Runtime limitations still open

- Docker is not installed; PostgreSQL, Redis and Celery worker end-to-end execution remain unverified.
- Celery, PyArrow and Psycopg are not installed in this sandbox. The worker task and artifact paths are implemented but not executed against real Parquet data.
- Vite production build and browser-level UI testing remain unverified because frontend dependencies are not installed.
- Phase 2 is **not complete**. MLflow, multi-model comparisons, benchmarks, complete walk-forward evaluation, expanded portfolio accounting, deterministic risk checks and full worker runtime acceptance tests remain.


## Phase 2 — implementation completion checkpoint — 2026-11-02

**Status: implementation complete; external runtime verification is still pending.** This means the Phase 2 code paths, schemas, API contracts, UI source, methodology docs and offline acceptance tests are implemented. It does not mean the sandbox executed a real Redis/Celery worker against real Parquet and PostgreSQL services or built the Vite bundle.

### Phase 2 acceptance checklist

- [x] Evidence-linked hypotheses with owner submission, independent ADMIN/RISK_REVIEWER decision and audit records.
- [x] Immutable feature-set versions pinned to READY market snapshots with SHA-256 definition fingerprints and declared-feature/target separation.
- [x] Reproducible experiment specs tied to approved hypotheses, source snapshots and feature lineage; canonical configuration hashes and validated chronological train/validation/test windows with target-horizon purge/embargo.
- [x] Three registered deterministic long-only baselines: buy-and-hold, moving-average crossover and RSI mean-reversion.
- [x] Holdout and rolling non-overlapping walk-forward evaluation, with train/validation diagnostic metrics and out-of-sample test metrics.
- [x] Optional pinned benchmark snapshot validation and aligned benchmark return, alpha, beta, tracking-error and information-ratio metrics; missing benchmark is explicit.
- [x] Vectorized and event-driven multi-asset portfolio accounting with next-close fills, cash, holdings, long-only gross-exposure limit, turnover, commission and slippage.
- [x] Persisted deterministic PASS/REVIEW/REJECT risk reviews with policy version, limits, observed metrics, warnings and breaches; LLM override prohibited.
- [x] Idempotent experiment-run submission, queue-failure state and same-key retry; worker verifies source/config/feature fingerprints and persists run artifacts.
- [x] Atomic local JSON experiment-tracking backend and optional MLflow adapter.
- [x] Run-comparison and risk-review APIs, Experiment Lab, and Strategy & Backtest Lab.
- [x] Phase 2 API/methodology documentation and acceptance tests.
- [ ] Live PostgreSQL + Redis + Celery worker test — services/dependencies unavailable in this environment.
- [ ] Real PyArrow Parquet snapshot and worker-artifact read/write test — PyArrow unavailable in this environment.
- [ ] Full Vite/TypeScript production build and browser test — npm packages are not installed; package-registry access has been unavailable.

### Implemented in this completion increment

- Added `src/finsight/backtesting/portfolio.py`: multi-asset vectorized long-only accounting with delayed fills, returns after execution, cash weight, exposure, turnover and costs.
- Added `src/finsight/backtesting/event_engine.py`: event-driven share/cash accounting with explicit BUY/SELL fill records, commission, slippage and sell-before-buy rotation handling.
- Expanded baseline registry with RSI mean-reversion and experiment configuration with holdout/walk-forward settings and benchmark symbol.
- Added walk-forward fold execution/aggregation and optional benchmark-relative analytics in `src/finsight/experiments/runner.py`.
- Added strict declared-feature materialization, deterministic risk policy/models and risk-review persistence.
- Added local atomic JSON tracking and optional MLflow adapter, including an optional `mlflow` dependency extra and settings validation.
- Added migration `0004_phase2_benchmark_risk_review` for pinned benchmark snapshots and persisted risk reviews; froze migration `0002` to its historical schema so future ORM changes do not rewrite old migration contents.
- Added experiment comparison and risk-review GET endpoints; worker validates snapshot/feature/config hashes and writes configuration, feature frame, equity, metrics and risk artifacts. File hashing now streams large snapshots rather than reading them wholly into memory.
- Added `apps/web/src/pages/StrategyBacktestPage.tsx` and navigation for completed cross-experiment baseline comparison and risk-finding inspection. Corrected Experiment Lab submission so selected `evaluation_mode` and benchmark snapshot ID are actually persisted; initial snapshot selection now chooses a READY snapshot.
- Added API contracts and backtesting/risk methodology documentation; updated README, architecture and roadmap.

### Final verification in this sandbox

- `python -m pytest -ra`: **43 passed, 2 skipped in 3.33s**.
  - Skip: opt-in PostgreSQL/Redis live-check suite (`FINSIGHT_RUN_LIVE_CHECKS=1` required with services available).
  - Skip: PyArrow Parquet integration (`pyarrow` not installed).
- `python -m compileall -q backend src apps migrations`: passed.
- Alembic on a fresh disposable SQLite DB: upgrade to `0004_phase2_benchmark_risk_review (head)`, downgrade to `0003_experiment_run_idempotency`, re-upgrade to head; passed. Schema assertions confirmed benchmark snapshot field and risk-review table/columns.
- FastAPI application import/OpenAPI check: passed; 25 paths, including comparison and risk-review endpoints.
- TypeScript/TSX syntax transpilation: passed for 9 non-declaration source files, including the new Strategy & Backtest Lab and the corrected Experiment Lab payload (walk-forward mode and benchmark snapshot now persist from the UI). This is syntax-only, not a full Vite bundle or typecheck.
- `pyproject.toml`, Compose files, CI YAML and environment YAML parse: passed.
- `bash -n scripts/clone_references.sh scripts/verify_workspace.sh`: passed.

### Remaining external validation (not implementation backlog)

To close the deployment verification gates, the workspace needs a runtime with Docker, PostgreSQL, Redis, Celery, PyArrow, Psycopg and Node/npm package access. Run the live dependency test, build and run the worker, produce/read a real market snapshot and execute a queued experiment end-to-end; run `npm install && npm run build` and browser acceptance. The current sandbox did not have Docker, Celery, Redis client, Psycopg, PyArrow, MLflow or frontend node_modules available, and package-registry networking was unavailable. These checks are explicitly left open rather than reported as passed.

**Next product phase:** Phase 3 — Financial Research AI & Advanced ML (document parsing, grounded RAG, bounded LangGraph analyst workflow, and reproducible supervised-model experiments). Phase 2 implementation is not waiting on Phase 3 code; only the environment-dependent runtime checks above remain.


## Phase 3 — first integrated increment — 2026-11-02

**Status: in progress.** This increment is implemented and offline-tested; Phase 3 is not marked complete because semantic/vector infrastructure, persistent graph execution, validated pretrained sentiment, queued workloads and external runtime checks remain.

### Implemented

- Added persistent `ResearchDocument`, `DocumentChunk`, `ResearchReport` and `ModelEvaluation` entities with migration `0005_phase3_document_ai_ml`; evaluation records now pin both the immutable READY snapshot and feature-set version.
- Added allow-listed TXT/Markdown/CSV/JSON/HTML/PDF parsers, upload limits, exact-content SHA-256 deduplication, section-aware bounded overlapping chunks, chunk hashes and source metadata. PDF extraction uses the optional `pypdf` package.
- Added a pluggable embedding provider contract: deterministic 384-dimension signed unigram/bigram feature hashing is the default; a local SentenceTransformer adapter is optional. Each source records provider/model/dimensions, and retrieval excludes mismatched embedding spaces. JSON vectors are still used; pgvector is not yet wired.
- Added hybrid lexical/cosine retrieval and MMR diversification, with citation IDs linked to source/chunk hashes. Citation checking validates source-ID linkage only, not semantic entailment.
- Added a bounded research workflow with query validation, retrieval, synthesis, citation validation and a required ADMIN/RISK_REVIEWER decision. Default output is extractive; optional LangChain OpenAI synthesis treats uploaded source text as untrusted and requires factual citations. Optional LangGraph `StateGraph` execution is available through the `research-ai` extra. Missing configured extras/API key fail closed with service errors; no silent provider fallback.
- Added chronological supervised evaluation for Ridge, Random Forest, XGBoost, LightGBM and CPU PyTorch LSTM; train-only LSTM scaling; snapshot/feature lineage fingerprints; model artifact persistence; transparent lexicon sentiment baseline plus an optional lazy FinBERT provider with class probabilities; evaluation listing and same-lineage model comparison by RMSE.
- Added `ResearchIntelligencePage` with document library, evidence queries, reviewer decisions, supervised evaluation and model comparison.
- Updated docs, API reference, `.env.example` and optional dependency groups `semantic`, `research-ai` and `finbert`.

### Current verification

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:backend pytest -ra`: **67 passed, 2 skipped**.
- Skipped: optional live PostgreSQL/Redis checks (not enabled/services unavailable) and Phase 1 Parquet write/read integration (PyArrow unavailable).
- `python -m compileall -q backend src apps migrations`: passed.
- Fresh SQLite Alembic lifecycle: upgrade to `0005_phase3_document_ai_ml (head)`, assert all four Phase 3 tables and `feature_set_version_id`, downgrade to `0004_phase2_benchmark_risk_review`, re-upgrade to `0005`; passed.
- FastAPI OpenAPI: 34 paths at this checkpoint; document, research report, ML evaluation, sentiment and evaluation-comparison routes present.
- TypeScript/TSX transpilation: 10 frontend source files, zero syntax diagnostics. This is syntax-only; no Vite bundle/typecheck claim.
- Python compileall, TOML/YAML parsing and shell syntax checks: passed.

### Not verified / remaining Phase 3 work

- `sentence-transformers`, `langgraph`, `langchain-openai` and `transformers` optional packages/model weights are not installed; learned embeddings, StateGraph execution, live LLM calls and actual FinBERT weights have not been runtime-tested. No API key is stored in the workspace.
- Embeddings are stored in SQL JSON; pgvector indexing/ANN retrieval and true cross-encoder reranking are not implemented.
- Citation validation is an ID/source-link check, not claim-level entailment/factuality evaluation. FinBERT adapter code is implemented but pretrained weights and domain calibration have not been verified; the lexicon baseline remains the default.
- Document ingestion, RAG and model fit run synchronously with strict size/row/chunk bounds; queued scalable workers, persistent graph checkpoints and production MLflow registry integration remain.
- PostgreSQL/Redis/Celery, real Parquet snapshots, Docker and full browser/Vite production build remain unverified in this environment.

**Next Phase 3 increment:** add pgvector migration/index and vector-store adapter; connect document/ML jobs to bounded Celery workers; add persistent LangGraph checkpointing; validate FinBERT weights on a labeled finance corpus and add stronger claim-level evidence scoring; then run full service/browser integration where services are available.


## 2026-11-02 — Phase 3 completion increment: queued research workflows

**Starting point:** Phase 3 document/RAG/ML source was present through Alembic revision `0006_phase3_evidence_vector_checkpoints`. The previous continuation had stopped while testing queue-failure retry handling. The `datetime` import in document upload dispatch-failure handling was already corrected in the current workspace; the full baseline suite passed before this increment.

**New implementation:**

- Added `POST /api/v1/research/ask/jobs`, which accepts the evidence-research request plus a required idempotency key and persists a `research.ask` job before dispatch. Same-key/same-payload replay returns the original job; cross-operation or changed-payload key reuse returns HTTP 409.
- Added `enqueue_research_ask` and Celery task `finsight.research.ask`; research Q&A now runs in the worker instead of blocking the frontend request. The existing synchronous `/research/ask` route remains available for bounded local/test workflows.
- Added `backend/app/services/research_jobs.py` as the shared, directly testable worker service. The report ID is deterministically the research job ID; if a worker is redelivered after report commit but before job completion commit, it recovers the completed report instead of creating a duplicate. Interrupted PROCESSING reports reuse the same ID and rebuild their node checkpoints.
- Added research jobs to the owner/ADMIN queue-retry dispatcher. Queue outages persist `QUEUE_FAILED`; the owner/ADMIN can retry the same job through `/api/v1/jobs/{job_id}/retry`.
- Updated Research Intelligence UI to queue research questions, show job status and report/document/evaluation result IDs, and retry dispatch failures.
- Updated README, API contract and Phase 3 operations guide.
- Added tests for queue-failure persistence, same-key idempotency, payload collision, owner retry, role enforcement, worker report/checkpoint persistence and worker-redelivery recovery.

**Verification in this increment:**

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src:backend pytest -ra` => **83 passed, 2 skipped**. Skips: optional live PostgreSQL/Redis checks (services absent) and Parquet integration (PyArrow absent).
- `python -m compileall -q backend src apps migrations` => passed.
- Fresh SQLite Alembic lifecycle: upgrade to `0006_phase3_evidence_vector_checkpoints`, downgrade to `0005_phase3_document_ai_ml`, re-upgrade to `0006` => passed.
- FastAPI OpenAPI => **42 paths**; queued research, synchronous research, report resume, document jobs, ML jobs and generic job retry routes all present.
- TypeScript/TSX syntax transpilation => **10 frontend source files**, zero syntax diagnostics. This is syntax-only; full Vite build/typecheck/browser tests were not run.
- TOML/YAML parsing and shell syntax checks => passed.

**Phase 3 implementation status:** Complete for the agreed source/API/schema/UI scope and offline acceptance. The default operational path is deterministic and extractive. Optional SentenceTransformer, cross-encoder, LangGraph, LangChain/OpenAI and FinBERT providers are implemented behind extras/configuration but their real weights/API calls were not executed in this environment. pgvector schema/query/backfill paths are implemented but were not exercised against live PostgreSQL. Docker, Redis/Celery worker runtime, PyArrow Parquet and browser/Vite production build remain deployment validation gates, not claimed as passed.

**Next phase:** Phase 4 — Governance, Reinforcement Learning & Paper Execution.


## Latest verified checkpoint — Phase 5 outcome feedback and production readiness

**Phase 5 objective:** close the research-to-outcome loop, integrate the final dashboards and provide repeatable deployment, observability, security and recovery assets. The implementation is present in the workspace and offline acceptance tests pass. This does not mean a live production deployment has been run in this sandbox.

### Implemented source/API/UI

- Added persisted prediction-versus-realised outcome records with owner-scoped idempotency and optional model-version, succeeded experiment-run and paper-account lineage. Model/run links are checked for owner and data-snapshot/feature-set consistency.
- Added outcome metrics (MAE, RMSE, signed bias, directional accuracy) and persisted strategy metrics (compound return, annualised volatility/Sharpe diagnostic, drawdown, win rate and optional benchmark-relative excess return).
- Added `POST /api/v1/feedback/strategies/evaluate-run` to import a succeeded Phase 2 backtest's equity-curve Parquet artifact. It checks caller ownership, path containment beneath `DATA_STORAGE_PATH`, mandatory worker-recorded SHA-256 integrity and bounded dated return rows before persisting monitoring results. A replay for the same caller/run/artifact hash returns the existing monitoring snapshot. Older runs without a pinned artifact hash must be rerun with the current worker.
- Added PSI/empirical-KS drift assessments with ownership, READY state, model training snapshot and same-instrument lineage validation. Drift thresholds remain review signals; they cannot retrain or promote models automatically.
- Added deduplicated follow-up research proposals from drift, forecast bias and strategy degradation with an explicit human ACCEPTED/DISMISSED decision and audit event.
- Added the Feedback & Monitoring UI and optional lineage fields on outcome capture, run-based strategy import, summary metrics, drift history and suggestion decisions.
- Hardened Operations summary to distinguish Redis connectivity from Celery worker liveness, report worker names/stale-job counts/recent failure metadata and avoid exposing raw error messages to broad reader roles. Added refresh and links to docs/metrics/Prometheus/Grafana. Existing stale-job recovery remains Admin-only, dry-run by default and explicit-confirmation for dispatch.
- Added Prometheus HTTP metrics, optional OpenTelemetry tracing, Prometheus alert rules, Grafana dashboard/provisioning, Compose service health checks/restart policies and frontend `/metrics` proxy forwarding.
- Added PostgreSQL and app-data volume backup/restore scripts. Data-volume backups now include relocatable checksums; archive validation rejects absolute paths, parent traversal, symlinks/hardlinks/special files and excessive archive expansion before extraction. Restore requires explicit confirmation and stops API/worker writers.
- Added/maintained CI, security/dependency/container scan and GHCR release workflows, operator documentation, API contracts, roadmap and recruiter demo scenarios.
- The frontend contains ten navigable product pages: Overview, Research Workspace, Research Intelligence, Experiment Lab, Strategy & Backtests, RL Strategy Lab, Model Governance, Paper Execution, Feedback & Monitoring and Operations & Administration.

### End-to-end and security acceptance

- Expanded the lineage acceptance test to run one user's workflow across a succeeded model/experiment/paper-account-linked prediction outcome, ten forecast observations, strategy performance, current-vs-reference snapshot drift, follow-up suggestions, explicit human acceptance and final dashboard summary.
- Added a test proving the completed-run strategy import rejects a tampered equity artifact and hides another user's run; added drift ownership/snapshot lineage and worker-health/failure-redaction tests.
- Added shell acceptance tests for PostgreSQL backup/verify/restore client contracts (using fake PostgreSQL tools), app-data tar archive backup/restore round-trip (real tar with mocked Docker volume execution), checksum handling and archive traversal/symlink rejection.

### Verification in this sandbox

- Full backend suite: **114 passed, 2 skipped** (116 collected). The run used `pytest.main()` with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, numerical thread limits and `-p no:cacheprovider`; `pytest.main()` returned code 0. This wrapper then exits immediately because this sandbox intermittently retains interpreter threads after pytest has printed its summary. The two skips are the opt-in live PostgreSQL/Redis test and the PyArrow Parquet integration test.
- Focused Phase 5 API tests: **12 passed**.
- Fresh SQLite Alembic lifecycle: upgrade to `0009_phase5_outcome_lineage`, assert all Phase 5 feedback tables, downgrade to `0008_phase5_feedback_monitoring`, and re-upgrade to `0009`: passed.
- FastAPI OpenAPI: **69 paths**. Feedback and operations routes/methods inspected, including `POST /api/v1/feedback/strategies/evaluate-run`; no live order/broker route was found.
- Python compileall and targeted script py_compile: passed.
- TypeScript/TSX syntax transpilation: **15 files, zero syntax diagnostics**. This is not a full TypeScript typecheck, Vite production bundle or browser E2E run.
- `bash -n` across project shell scripts: passed. Archive validator, backup client-contract and app-data tar/restore tests passed.
- TOML plus eight Compose/monitoring/GitHub Actions YAML files parsed successfully. Compose API healthcheck and Nginx/Vite `/health` aliases were corrected to target FastAPI's registered `/api/v1/health[/ready]` paths and protected by a regression test. ZIP contents and archive integrity are checked at packaging.

### External runtime validation still pending

- Docker is unavailable in this sandbox; Compose service startup, restart/healthcheck behaviour, API/worker integration and actual deployment reproducibility were not executed.
- Live PostgreSQL/pgvector, Redis and Celery execution/worker recovery have not been run.
- PyArrow is not installed; the `evaluate-run` route was tested with a stubbed Parquet reader, not a real generated/loaded Parquet artifact.
- Frontend npm dependencies are absent and registry access timed out; no `npm run build`, complete `tsc` typecheck or browser-based E2E test is claimed.
- PostgreSQL backup/restore used fake pg_dump/pg_restore tools for argument/secret handling; app-data volume restore used a mocked Docker mount with real tar. A real database restore drill, real Docker volume restore, Prometheus/Grafana/OTel container startup, load test and external vulnerability/secret scans still need a service-enabled CI/deployment environment. GitHub Actions workflows are configured but have not been run by GitHub in this workspace.

**Phase 5 status:** source, API, frontend, migration, documentation and offline acceptance implementation are complete. Production-readiness verification is not complete until the above service-enabled deployment/recovery/security checks have run. Phase 5 is the final planned product phase; no Phase 6 is defined.


### Final CI dependency alignment

- Promoted NumPy and scikit-learn to base dependencies: core RL numeric operations and Ridge/Random Forest evaluations import them directly. The `ml` extra now contains only optional joblib/XGBoost/LightGBM/PyTorch packages.
- Updated model dependency errors and install guidance in research/API/Phase 4 operations documentation. The GitHub CI backend install (`.[dev,observability]`) therefore installs the dependencies needed by baseline evaluation tests.
- Revalidated after the dependency correction: TOML parse and dependency placement passed; full backend suite remains **114 passed, 2 skipped**; Python compilation, shell syntax and YAML parsing passed. SQLite Alembic lifecycle to `0009`/downgrade/re-upgrade passed; OpenAPI remains **69 paths**; 15 TypeScript/TSX implementation files passed syntax transpilation; archive/backup contract tests passed.


## Reference integration checkpoint (2026-11-07)

Five reference repositories were supplied as ZIP archives and integrated under the plan's reuse rules. Details, licences and archive hashes are in `docs/SOURCES_AND_ATTRIBUTION.md`; the licence texts are in `third_party/licenses/`.

**Added (all new code, none copied from upstream):**
- `src/finsight/research/agents/`: fundamentals, risk and sentiment analysts, a coordinator that implements the existing `ResearchSynthesizer` protocol (`RESEARCH_SYNTHESIS_PROVIDER=multi_analyst`), descriptive technical context, a testable hypothesis proposal that maps to the existing hypothesis payload, and a methodology critic. Output goes through the existing citation-linkage check, claim-support screen and mandatory human review. This fills the previously empty `research/agents/` package.
- `src/finsight/risk/allocation.py`, `reinforcement_learning/environments/multi_asset_env.py`, `rewards/reward_schemes.py`, `evaluation/portfolio.py`: a multi-asset long-only allocation environment with next-open execution, deterministic limits applied to every action, three reward schemes including the plan's cost, turnover and drawdown formula, and chronological out-of-sample PPO/SAC evaluation over repeated seeds beside equal-weight and buy-and-hold baselines. The earlier single-asset environment is unchanged.
- `src/finsight/backtesting/universe.py`: frozen, fingerprinted, point-in-time universe with recorded exclusion reasons and a survivorship report.
- `bollinger_mean_reversion` in the baseline strategy registry, and a committed frozen-results regression test (`backend/tests/fixtures/baseline_regression.json`).

**Verified in this session (Python 3.12, CPU PyTorch 2.14.1, Stable-Baselines3 2.9.2, Gymnasium 1.3.0, PyArrow 24.0.0):**
- Full backend suite: **150 passed, 3 skipped** (153 collected). Before these changes the same suite gave 111 passed, 1 failed, 4 skipped in a first environment without PyTorch; the failure was a FinBERT-adapter test and it passes with PyTorch installed. 37 tests are new.
- Real PPO and SAC training ran (256 timesteps, 2 seeds each, on synthetic prices) through `train_and_evaluate_portfolio`, and the Gymnasium environment checker passed. The project's own earlier RL tests, previously skipped for lack of Gymnasium and Stable-Baselines3, also ran and passed. The PyArrow Parquet test ran and passed.
- `ruff check` passes on every new and changed file.

**Still open (not verified here):** Docker, live PostgreSQL/Redis/Celery, XGBoost and LightGBM tests (packages not installed, 2 skips), the opt-in live-dependency test, the frontend `npm` build, and any training on real market data (the tests use synthetic prices and tiny timestep counts, so they prove the machinery, not strategy quality). The multi-asset RL evaluation and the multi-analyst synthesizer are library code with tests; they are not yet exposed through new API routes or UI pages. Exposing the Bollinger baseline in the experiment API needs new `ExperimentConfiguration` fields, which changes canonical configuration hashes, so it was left out pending your decision.
