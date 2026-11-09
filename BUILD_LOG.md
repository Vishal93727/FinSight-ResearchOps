# FinSight ResearchOps — Build Log

## 2026-11-02 — Workspace assembly (pre-Phase 1)

**Starting state:** Existing `FinSight_AI_Foundation_v0.1.zip`, `FinSight_Platform_v1.zip`, and approved 26-section project plan were available in the user's Library.

**Actions completed:**
- Extracted `FinSight_AI_Foundation_v0.1.zip` into the workspace root as the initial codebase.
- Excluded generated Python cache files from the extracted workspace.
- Preserved both original ZIP archives under `archives/`.
- Copied the approved DOCX and PDF project plan into `docs/project_blueprint/`.
- Preserved inherited foundation docs under `docs/inherited_foundation/` before future scope edits.
- Created repository catalogue and Bash/PowerShell scripts for cloning references into `references/cloned/`.
- Created progress tracking and workspace verification scripts.

**GitHub clone status:** Not cloned in this environment. Direct DNS resolution to `codeload.github.com` failed (`Could not resolve host`), and the GitHub connector does not provide repository archive bytes. The supplied scripts will clone repositories on a machine with Git and internet access. This is explicitly not recorded as a successful clone.

**Validation in this workspace:** Extraction and workspace creation completed. A fresh test run will be recorded separately after running the project's backend test command.

**Current end state:** Workspace assembled; no Phase 1 implementation work has begun.

**Next step:** Audit the backend scaffold and inherited docs; then begin Phase 1 Step 1 re-scoping and database/identity foundation design.

## 2026-11-02 — Phase 1 foundation implementation (current workspace)

**Starting state:** Workspace was assembled from the existing FastAPI foundation scaffold. Phase 1 had not been implemented. Existing source documentation was preserved under `docs/inherited_foundation/`.

**Implementation changes made in this session:**

- Rebranded package metadata, API identity and docs for FinSight ResearchOps; removed active fraud/credit product framing while preserving original inherited docs as historical source material.
- Added typed runtime settings, production JWT-secret validation, JSON logging, SQLAlchemy database session/base, ORM entities and initial Alembic migration.
- Added six seeded RBAC roles and seeded `manual_upload` / `sec_edgar` data providers.
- Implemented scrypt password hashing, expiring JWT access tokens, analyst-only self-registration, login/current-user endpoints, administrator CLI provisioning, admin-only user listing/role assignment and server-side role checks.
- Implemented instrument catalogue and provider APIs with role restrictions.
- Implemented SEC EDGAR company-submissions adapter, append-only company ingestion records, hash tracking and audit events.
- Implemented JSON and CSV OHLCV ingestion, input/size/OHLC validation, content-addressed Parquet writer, immutable snapshot manifest/hash and snapshot listing.
- Added persisted job records, idempotency handling, Celery queue adapter, job inspection endpoint and idempotent system-ping worker task.
- Added liveness/readiness endpoints, request-ID middleware and safe error responses.
- Added React/TypeScript/Vite UI source for login, ResearchOps Overview, SEC + OHLCV CSV Research Workspace, instrument catalogue and Operations/role administration.
- Added Docker Compose services, CI configuration, source/architecture/security/data-model docs and updated run instructions.

**Validation commands and actual results:**

- `pytest -q`: 19 passed, 2 skipped.
- `python -m compileall -q backend`: passed.
- `DATABASE_URL=sqlite:///./phase1_migration_release.db alembic upgrade head`: passed; `alembic current` returned `0001_initial_researchops (head)`.
- Earlier in the same work, Alembic upgrade/downgrade/upgrade against a disposable SQLite DB also passed.
- `PYTHONPATH=backend python backend/scripts/create_admin.py --help`: passed.
- `bash -n scripts/clone_references.sh` and `bash -n scripts/verify_workspace.sh`: passed.
- TypeScript/TSX syntax-only transpilation using the system TypeScript compiler: zero syntax diagnostics.

**Skipped/unavailable validation (do not represent as passed):**

- Parquet artifact writer test skipped because PyArrow is not installed locally.
- Live Postgres/Redis test skipped because services are not available in this environment.
- Docker is not installed, so Compose startup and container/worker checks could not run.
- Package installation (`pip install -e '.[dev]'`) failed because package-index DNS/network is unavailable; missing local runtime dependencies include Psycopg, Celery/Redis client and PyArrow.
- `npm install` timed out due package registry networking; React/Vite build and browser tests remain unverified. `tsc --noEmit` could not complete because React/Vite packages and type declarations are not installed.
- SEC route used a mocked SEC adapter in tests; no live SEC call was attempted.
- GitHub clone catalogue contains 16 references, but actual clone folder contains 0 repos because outbound GitHub download host access is unavailable.

**End state:** Phase 1 backend/API/database schema, test suite and frontend source implementation are largely in place. Phase 1 remains **in progress pending environment-dependent integration verification**. No Phase 2 implementation has started.

**Exact next task:** Install the declared dependencies and run Docker Compose on a machine with network access; verify PostgreSQL migration, Redis readiness/Celery queue, real Parquet output, npm frontend build and SEC provider connectivity. Update `PROJECT_PROGRESS.md` only with actual test evidence before marking Phase 1 complete.

## 2026-11-02 — Repository structure alignment

- Compared the repository against the requested `apps/`, `src/finsight/`, root migrations/configs/sql/tests/infra/docs structure.
- Moved the React/Vite application to `apps/web/` and updated Compose and GitHub Actions paths.
- Added canonical API and Celery worker entrypoint wrappers under `apps/api/` and `apps/worker/`; they currently delegate to the tested `backend/app` implementation.
- Added the requested domain package directory hierarchy under `src/finsight/`, with core compatibility exports and clear migration notes. Domain folders not yet implemented are explicitly marked as reserved, not falsely represented as completed features.
- Added environment YAML templates, root `migrations/` migration note, SQL folders, test taxonomy folders, infra folders, docs taxonomy, `Makefile`, and `LICENSE`.
- Added root `docker-compose.yml` alias while retaining `compose.yaml`.
- Verification: required path audit reported no missing paths; `pytest -q` => 19 passed, 2 skipped; `compileall` passed; clone/verify shell syntax passed.
- Remaining architecture debt: production business logic and Alembic migrations still reside under `backend/app` and `backend/migrations`. They are intentionally not mass-moved in this structural pass to avoid breaking imports, Docker and tests. Move them in a controlled migration with import compatibility and integration checks.
- GitHub repositories: 16 catalogued; 0 actually cloned in this environment.


## 2026-11-02 — Canonical module migration and Phase 2 foundation

**Starting state:** Existing domain directory skeleton and Phase 1 implementation remained split between `backend/app` and placeholder `src/finsight` modules. Alembic scripts were still under `backend/migrations`.

**Architecture migration completed:**

- Moved canonical Settings into `src/finsight/core/config.py`, JSON logging into `src/finsight/core/logging.py`, and JWT/password/RBAC security into `src/finsight/core/security.py`.
- Moved SQLAlchemy base/session/mixins/model registry into `src/finsight/infrastructure/database/`.
- Moved User/Role entities and identity/auth/admin contracts into `src/finsight/identity/`.
- Moved instrument/provider/snapshot/SEC entities into `src/finsight/market_data/models.py`; SEC EDGAR adapter, market snapshot writer and OHLCV contracts now live under `src/finsight/market_data/`.
- Updated all current API route adapters and worker persistence imports to use canonical `finsight.*` modules directly.
- Kept historic `backend/app` import paths as lightweight `sys.modules` compatibility shims for existing callers/tests.
- Moved Alembic environment and version scripts into root `migrations/`; `alembic.ini` now uses `script_location = migrations` and the migration environment loads canonical metadata.
- Updated package discovery to include `src/finsight*` and transitional `backend/app*`; updated Dockerfile to copy `src/`, `apps/` and root `migrations/`; updated CI lint/compile paths and workspace documentation.

**Phase 2 implementation started:**

- Added `ResearchHypothesis` with evidence references, DRAFT -> UNDER_REVIEW -> APPROVED/REJECTED workflow with separate owner submission and ADMIN/RISK_REVIEWER decision, version increment and audit trail.
- Added immutable `FeatureSetVersion` definitions pinned to a READY snapshot and content hash.
- Added `Experiment` and `ExperimentRun` persistence; experiment specs require an approved hypothesis, READY dataset snapshot, feature-set source snapshot match, same instrument and dataset coverage.
- Added strict baseline experiment configuration with ordered temporal windows, purge gap covering the prediction horizon plus embargo, fixed seed, benchmark and explicit commission/slippage settings. Configuration JSON is canonicalized and SHA-256 fingerprinted.
- Added leakage-aware OHLCV features and baseline buy-and-hold / moving-average signals.
- Added deterministic long-only backtesting using next-bar-close fills for close-time signals, turnover-based commission/slippage and summary performance/risk metrics.
- Added Alembic revision `0002_research_experiment_foundation`. Revision `0001` was bounded to the original Phase 1 table list to ensure new databases do not receive Phase 2 tables before the Phase 2 migration.
- Added Phase 2 API and unit tests covering reviewer permissions, hypothesis decision state, evidence persistence, feature snapshot lineage, experiment config fingerprints, non-overlapping temporal windows, leakage properties and next-bar/cost behavior.

**Verification and actual results:**

- `python -m pytest -q`: **26 passed, 2 skipped**.
- `python -m compileall -q backend src apps migrations`: passed.
- SQLite Alembic lifecycle: `upgrade 0001` confirmed no Phase 2 tables; `upgrade head`, `downgrade 0001`, and `upgrade head` all passed. Final revision: `0002_research_experiment_foundation (head)`.
- Setuptools namespace package discovery includes the canonical `finsight` package; `pip install --no-deps --no-build-isolation -e .` succeeded and `pip wheel --no-deps --no-build-isolation .` produced a wheel containing `finsight` and compatibility `app` modules.
- `compose.yaml` and `docker-compose.yml` both parsed as valid YAML with expected services; `apps.api.main` imported as a FastAPI app.
- `bash -n scripts/clone_references.sh scripts/verify_workspace.sh`: passed.
- `ruff` is not installed in this environment, so lint was not verified.

**Not run / not claimed:** Docker Compose, PostgreSQL/Redis, Celery queue execution, live SEC calls, real PyArrow Parquet writes and frontend npm production build. Network/package registry and missing executables/dependencies remain the known blockers. The two test skips remain the Parquet dependency and opt-in live-service checks.

**End state at this earlier checkpoint:** requested module and migration relocation was implemented, and Phase 2 had the research/feature/experiment foundation and first next-bar baseline backtest. The later run-lifecycle and Experiment Lab work is recorded in the following checkpoint.


## 2026-11-02 — Phase 2 run lifecycle and Experiment Lab

- Added idempotency-key support to `ExperimentRun`, including revision `0003_experiment_run_idempotency` and the unique experiment/key index. Kept revision `0002` historical and stable so existing databases can upgrade/downgrade cleanly.
- Added experiment run create/list endpoints, queue adapter, queue-failure status, same-key retry and repeat-submission protection.
- Added pure baseline runner with configured test-window slicing and a Celery task to read the READY snapshot and persist metrics JSON/equity-curve Parquet artifacts with source/config fingerprints.
- Added API acceptance tests for idempotent run submission, duplicate protection, queue-failure retry and run listing, plus pure runner holdout-window and finite-number rejection tests.
- Added finite-number guards to OHLCV request validation, feature inputs and backtest close-price inputs.
- Added `apps/web/src/pages/ExperimentLabPage.tsx`; integrated the route/navigation and role-aware hypothesis/experiment actions into `App.tsx`. Updated the Research Workspace phase description and appended UI styles.
- Updated README/API reference, roadmap, architecture and project tracker for the implemented Phase 2 slice.

**Verification:** `pytest -q` => **29 passed, 2 skipped**; `compileall` passed; TypeScript/TSX syntax transpilation passed; Alembic upgrade/downgrade/re-upgrade lifecycle passed with `0003_experiment_run_idempotency (head)`; clone/verify shell syntax passed.

**Not verified:** full npm/Vite build (no `node_modules`/registry access), actual Celery/Redis worker dispatch, PyArrow Parquet read/write and Docker/Postgres integration (Docker/Celery/PyArrow/Psycopg unavailable). Do not mark Phase 2 complete until those runtime checks and remaining Phase 2 acceptance criteria are satisfied.


## 2026-11-02 — Phase 2 implementation completion

**Purpose:** Complete the Research & Quantitative Experiment Core on top of the existing workspace, without recreating the repository.

**Implementation delivered:**

- `src/finsight/backtesting/portfolio.py`: vectorized multi-asset long-only accounting; delayed target-weight fills; cash, exposure, turnover, transaction costs, equity and drawdown ledger.
- `src/finsight/backtesting/event_engine.py`: event-driven cash/share ledger with explicit fills, commission/slippage costs and sell-before-buy rotation handling.
- `src/finsight/experiments/config.py`, `runner.py`, `models/baselines/strategies.py`: three registered deterministic baseline strategies; chronological holdout and non-overlapping walk-forward folds; train/validation diagnostics; optional aligned benchmark alpha/beta/tracking error/information ratio.
- `src/finsight/features/engineering.py`: version-declared feature-frame construction and explicit future-target separation.
- `src/finsight/risk/policy.py`, `risk/models.py`: deterministic PASS/REVIEW/REJECT risk policy and persisted per-run reviews.
- `src/finsight/experiments/tracking.py`: atomic local JSON run manifest and optional MLflow client adapter; added optional dependency/configuration guard.
- `migrations/versions/0004_phase2_benchmark_risk_review.py`: benchmark snapshot lineage and risk-review schema. Historical migration `0002` is now explicit/frozen instead of reading mutable current ORM metadata.
- `backend/app/api/v1/research.py`, schemas and worker: comparison/risk-review endpoints; snapshot, feature and config integrity checks; persisted metrics and artefacts; streamed SHA-256 file hashing.
- `apps/web/src/pages/StrategyBacktestPage.tsx`, `apps/web/src/App.tsx`, `apps/web/src/styles.css`: added dedicated strategy/backtest comparison and risk-review UI. Corrected Experiment Lab to submit the selected holdout/walk-forward mode and optional benchmark snapshot ID; auto-selects a READY snapshot.
- `docs/api/README.md`, methodology, architecture, roadmap, README and project checkpoint updated.

**Verification evidence:**

- `python -m pytest -ra` => **43 passed, 2 skipped in 3.33s**.
- `python -m compileall -q backend src apps migrations` => passed.
- Fresh SQLite Alembic: upgrade head (`0004_phase2_benchmark_risk_review`), downgrade to `0003_experiment_run_idempotency`, re-upgrade to head => passed; benchmark column and risk-review schema assertions passed.
- FastAPI OpenAPI import check => 25 paths; Phase 2 comparison and risk-review paths present.
- TypeScript/TSX syntax transpilation => 9 frontend source files, zero syntax diagnostics. No Vite bundle/typecheck claim.
- TOML/YAML parsing => passed for `pyproject.toml`, Compose, CI and environment config files.
- Shell syntax checks => passed.

**Skipped / not verified:**

- Live PostgreSQL/Redis checks skipped (opt-in; services not present).
- Parquet integration skipped because PyArrow is not installed.
- Docker Compose/Celery queue execution and worker artifact lifecycle not executed because Docker/Celery/Redis client/Psycopg are unavailable.
- Full `npm install`, Vite production build and browser acceptance not run because frontend packages are not present and package-registry access is unavailable.
- Optional MLflow adapter not exercised against an MLflow server; dependency and settings integration are implemented, local JSON tracker has an offline acceptance test.

**Status:** Phase 2 implementation is complete and offline acceptance is green. Environment-dependent integration checks remain external validation gates; the workspace does not claim they passed.


## 2026-11-02 — Phase 3 integration continuation

**Starting state:** document parsing, chunking, feature-hash retrieval, extractive reports and snapshot-pinned supervised ML APIs had been persisted in the workspace. The previous Phase 3 update was a first implementation increment, not a complete Phase 3 delivery.

**Implementation changes in this continuation:**

- Added a formal `EmbeddingProvider` protocol, deterministic `FeatureHashEmbeddingProvider` and lazy CPU `SentenceTransformerEmbeddingProvider`; stored provider/model/dimensions in document metadata and reject mixed embedding spaces at query time.
- Added the optional real LangGraph `StateGraph` execution engine (`RESEARCH_WORKFLOW_ENGINE=langgraph`) while retaining a deterministic dependency-free default.
- Added `LangChainOpenAISynthesizer` behind the `research-ai` optional extra and `OPENAI_API_KEY`; evidence is serialized as untrusted input, source text cannot supply instructions, factual answers are asked to cite exact IDs, and only cited IDs in the retrieved set can pass the linkage check. No automatic approval is possible.
- Changed citation verification to permit valid subsets of retrieved evidence and to persist only the sources actually referenced in the generated answer. Empty retrieval remains `NO_EVIDENCE` and does not require an LLM API call.
- Added `GET /api/v1/ml/evaluations/compare` to rank completed models by RMSE only for the same pinned dataset and optional feature-set lineage; added the model-family comparison table to `ResearchIntelligencePage`.
- Added tests for custom embedding-provider injection/dimension mismatch, missing optional LangGraph fail-closed behaviour, untrusted-source LLM prompting, invalid citation blocking and model evaluation comparison.
- Updated README, API/architecture/data model/research methodology/roadmap and current project progress to distinguish implemented adapters from unverified external services.

**Verification:**

- `PYTHONPATH=src:backend pytest -ra` => **64 passed, 2 skipped** (live PostgreSQL/Redis opt-in check and PyArrow Parquet integration skipped because dependencies/services are unavailable).
- `python -m compileall -q backend src apps migrations` => passed.
- Fresh SQLite Alembic lifecycle through migration `0005_phase3_document_ai_ml`, downgrade to `0004`, re-upgrade to `0005` => passed; all Phase 3 tables and feature-set foreign-key column checked.
- FastAPI OpenAPI schema => 34 paths; all Phase 3 document, research, ML and comparison paths included.
- TypeScript/TSX transpilation => 10 source files, zero syntax diagnostics. No full Vite build/typecheck claim.
- TOML/YAML parsing and Bash script syntax checks => passed.

**Not run / not claimed:** SentenceTransformer weights/provider, LangGraph StateGraph, LangChain/OpenAI API, pgvector indexing, FinBERT, PostgreSQL/Redis/Celery, PyArrow artifact creation, Docker Compose and browser/Vite production build were not executed in this sandbox. These remain explicitly open Phase 3/runtime gates.


## 2026-11-02 — Phase 3 sentiment model adapter

- Added lazy optional FinBERT inference (`ProsusAI/finbert`) through Transformers with CPU PyTorch inference, 512-token truncation, positive/negative/neutral probabilities and explicit model provenance. The local lexicon baseline remains the default and is still tagged `pretrained_model=false`.
- Added `provider=lexicon|finbert` to the sentiment API contract and a provider selector/results panel to Research Intelligence. Added the `finbert` optional dependency extra.
- Added tests using a stub tokenizer/model (no weight download) for probability normalization, label selection, text bounds and method provenance.
- Verification after this increment: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:backend pytest -ra` => **66 passed, 2 skipped**. The optional pretrained weights were not downloaded or executed.


## 2026-11-02 — Phase 3 final offline checkpoint (current workspace state)

- Added optional FinBERT provider (`score_finbert_sentiment`) with lazy `ProsusAI/finbert` loading, `trust_remote_code=False`, 512-token truncation, CPU inference, positive/negative/neutral probability output and bounded input validation. The lexicon method remains the default.
- Added `provider=lexicon|finbert` to the sentiment API and selector/result UI. Added unit tests using a stub tokenizer/model and an API route test using a stub provider; no external model weights were downloaded.
- Tightened model-comparison lineage: both a READY snapshot ID and a feature-set version derived from that same snapshot are now required; the API only ranks successful evaluations with the exact same pair.
- Updated Phase 3 README, API, methodology, architecture, roadmap and progress documentation.

**Final offline verification for this checkpoint:**

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src:backend pytest -ra` => **67 passed, 2 skipped in 13.13s**. Skips are the opt-in live PostgreSQL/Redis check and PyArrow Parquet integration because the services/package are unavailable. Thread caps and plugin-autoload disablement keep the ML test process cleanly exiting in this sandbox.
- `python -m compileall -q backend src apps migrations` => passed.
- Fresh SQLite Alembic lifecycle: upgrade to `0005_phase3_document_ai_ml`, assert `research_documents`, `document_chunks`, `research_reports`, `model_evaluations` and model-evaluation feature-set lineage; downgrade to `0004_phase2_benchmark_risk_review`; re-upgrade to `0005`; passed. Current head: `0005_phase3_document_ai_ml`.
- FastAPI OpenAPI check: **35 paths** total; 10 Phase 3 document/research/ML paths including model comparison and sentiment provider endpoint.
- TypeScript/TSX source transpilation: **10 files**, zero syntax diagnostics. No full typecheck, Vite bundle or browser acceptance claim.
- `pyproject.toml`, Compose, CI and all environment YAML files parse successfully; `bash -n scripts/clone_references.sh scripts/verify_workspace.sh` passed.

**Unverified / not claimed:** actual SentenceTransformer weights, LangGraph StateGraph execution, LangChain/OpenAI call, FinBERT weights/model inference, pgvector ANN search, cross-encoder reranker, persistent LangGraph checkpointing, FinBERT calibration, queued large document/ML jobs, MLflow model registry, Docker, PostgreSQL/Redis/Celery, real PyArrow Parquet artifacts and frontend Vite/browser runtime. Optional provider integration code is present, but these require their packages, weights, services and/or credentials.


## 2026-11-02 — Phase 3 queued research Q&A and final offline verification

- Implemented `POST /api/v1/research/ask/jobs` with owner-scoped idempotency, payload-collision protection, durable `QUEUE_FAILED` state and same-job retry.
- Added Celery dispatch adapter and `finsight.research.ask` task. The worker uses `backend/app/services/research_jobs.py` and a deterministic report ID equal to the job ID; a redelivered task recovers an already-completed report/checkpoint history rather than duplicating it.
- Preserved synchronous `/research/ask` for local/test use. Updated the Research Intelligence UI to queue the Q&A workflow and display the resulting report ID in the job list.
- Added tests for queue failure, replay idempotency, key collision, owner retry, role restrictions, checkpoint persistence and worker-redelivery recovery.
- Fixed/verified the previously reported queue failure path: `datetime` is imported in `documents.py`; document job dispatch failure and retry acceptance tests pass.

**Final verification:**

- Full suite: **83 passed, 2 skipped in 17.50s**. Skips are opt-in live PostgreSQL/Redis and PyArrow Parquet tests.
- Python compileall: passed.
- SQLite Alembic upgrade to `0006_phase3_evidence_vector_checkpoints`, downgrade to `0005`, re-upgrade to `0006`: passed.
- FastAPI OpenAPI: 42 paths, including research ask job, synchronous ask, explicit report resume, document upload job, ML evaluation job and generic queue retry.
- TypeScript/TSX transpilation: 10 files, zero syntax diagnostics; full Vite bundle/typecheck not run because project npm dependencies are absent.
- TOML/YAML and Bash syntax checks: passed.

**Not verified:** live Docker/PostgreSQL/pgvector/Redis/Celery execution, PyArrow artifacts, optional SentenceTransformer/cross-encoder/LangGraph/LangChain/OpenAI/FinBERT runtime and pretrained weights, and full Vite/browser acceptance. No claim is made that these integrations were executed.


## 2026-11-02 — Phase 3 source implementation completion and recovery hardening

**Starting state:** The Phase 3 document/RAG/ML paths, pgvector and cross-encoder adapters, and queued document/research/ML task families were present in the workspace. The prior checkpoint still described some of those items as missing, the full latest test count had not been recorded, and workflow checkpoints were durable audit snapshots but not yet resumable.

**Implementation and corrections in this continuation:**

- Added explicit failed-report resume at `POST /api/v1/research/reports/{report_id}/resume`. Recovery includes reconciliation of a committed human-review checkpoint as well as resuming unfinished nodes. Checkpoints now retain bounded recovery state (query, exact evidence chunk IDs, bounded answer/citation state, claim checks and workflow trace). Resume reuses those exact chunk IDs, requires source documents to remain READY, verifies source chunk hashes and validates the stored answer SHA-256 before continuing only the remaining workflow nodes. It does not run fresh retrieval or substitute a different evidence set.
- Added the Resume from checkpoint action to Research Intelligence for failed research reports.
- Documented the asynchronous research ask path (`research.ask`), along with existing document ingestion and supervised ML queues. Queue retry supports system ping, documents, research and ML job types and preserves the original job ID.
- Fixed document-upload idempotency collision handling so a key used by another task type cannot be treated as the same document job.
- Hardened document worker redelivery so wrong-task and terminal FAILED jobs are not silently rerun. Worker failure marking now protects already-SUCCEEDED records and rolls back incomplete ORM changes before persisting failure.
- Strengthened claim-level sentence-local evidence checking and source hash validation across checkpoint recovery. Updated API, operations, methodology, architecture, roadmap, README and current progress documentation.
- Kept optional components fail-closed and accurately labelled: feature-hash embeddings are not learned semantic embeddings; lexical/numeric claim checks are not semantic entailment; sentiment results are not profitability predictions; research approval remains a separate human action.

**Final offline verification in this environment:**

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src:backend pytest -ra` => **84 passed, 2 skipped**. The two skips are the opt-in PostgreSQL/Redis live-service test and the PyArrow Parquet integration test (PyArrow is not installed).
- `python -m compileall -q backend src apps migrations` and `python -m py_compile scripts/backfill_pgvector_embeddings.py` => passed.
- Fresh SQLite Alembic lifecycle: upgrade to `0006_phase3_evidence_vector_checkpoints`, assert Phase 3 tables, downgrade to `0005_phase3_document_ai_ml`, re-upgrade to `0006` => passed.
- PostgreSQL offline SQL generation for `0005 -> 0006` => passed and confirmed `CREATE EXTENSION vector`, `vector(384)` and HNSW cosine index statements. This verifies generated SQL only, not an actual PostgreSQL extension/index creation.
- FastAPI OpenAPI => **42 paths**, including document/research/ML queued operations, retry, checkpoints and resume.
- TypeScript/TSX syntax transpilation => **10 files**, no syntax diagnostics. This is not a complete TypeScript typecheck, Vite bundle or browser acceptance test.
- TOML/YAML parsing and `bash -n scripts/clone_references.sh scripts/verify_workspace.sh` => passed.

**Environment/runtime validation not run or not claimed:**

- Docker Compose is unavailable in the sandbox. No live PostgreSQL/pgvector HNSW search or backfill, Redis/Celery worker dispatch/recovery, or production service run was performed.
- PyArrow is absent; real Parquet generation and worker artifact processing remain unverified.
- `apps/web/node_modules` is absent; `npm ci`, full TypeScript typecheck, Vite production build and browser end-to-end tests remain unverified.
- SentenceTransformer and cross-encoder model weights, LangGraph/LangChain runtime packages, OpenAI credentials and FinBERT weights were not available. Optional adapter source and stubbed contract tests pass, but those pretrained/live calls are not claimed as executed.
- FinBERT has no domain-calibration claim, and lexical/numeric source screening is not a semantic entailment system. Human review remains mandatory.

**Status:** Phase 3 source implementation and offline acceptance are complete. Environment-dependent runtime/provider validation remains open and is tracked as deployment validation, not silently marked as passed. Phase 4 has not started.


## 2026-11-02 — Phase 4 RL navigation, OpenAPI verification and governance/paper execution checkpoint

**Starting point:** The Phase 4 routes, migration `0007`, RL environment/training service, governance/paper broker and frontend panel were present. The RL panel had not been mounted into application navigation, documentation still said Phase 4 was not started, and the first focused paper broker tests exposed a fee calculation bug that referenced `fee` before it was assigned.

**Implementation and corrections completed:**

- Fixed `src/finsight/execution/broker.py`: calculate simulated notional and fees before cash delta; evaluate risk against proposed post-trade exposure; only create a new position after risk passes; persist internal PaperOrder/PaperFill/PaperLedgerEntry records. Rejected orders do not create empty positions. No network calls or live broker adapter are used.
- Improved `src/finsight/reinforcement_learning/environments/portfolio_env.py` to accept aligned feature observations and correctly allow the final valid close-to-close transition.
- Improved PPO/SAC training in `src/finsight/reinforcement_learning/evaluation/training.py`: chronological train/holdout split, training-only feature scaling, deterministic evaluation, recorded normalization metadata and content fingerprint.
- Updated `backend/app/services/rl.py` so the selected versioned feature set is actually built and aligned to close prices by date. The target column is not used as an input; snapshot and feature-definition hashes are rechecked by the worker.
- Constrained RL API data columns to canonical `date` and `close`; expanded authorized evaluation-read roles. Queue creation remains restricted to ADMIN/QUANT_RESEARCHER.
- Mounted `ReinforcementLearningPage` in `apps/web/src/App.tsx`; added a sidebar navigation entry; built the RL Strategy Lab UI for matching READY Parquet snapshot/feature-set selection, PPO/SAC selection, timestep bounds, queue status, retry, completed OOS metrics and exact-lineage comparisons. Added role-aware navigation and actions: Research Analysts do not see governance/paper pages whose list APIs deny access; candidate registration requires ADMIN/QUANT_RESEARCHER; paper kill-switch actions require ADMIN/RISK_REVIEWER; reconciliation requires ADMIN/PORTFOLIO_ANALYST/RISK_REVIEWER; read-only viewers see no mutation controls. Backend authorization remains authoritative.
- Added OpenAPI contract tests for RL/governance/paper routes, algorithm/timestep/date/price request constraints and absence of live execution routes. Added RL feature alignment, target exclusion and train-only-scaler tests.
- Removed an unused HTTP `Idempotency-Key` header from the Paper Execution UI; the backend uses the account-scoped `client_order_id` as the supported order replay key. Updated operation/API documentation accordingly.
- Added `docs/operations/PHASE4_OPERATIONS.md`, updated `docs/api/README.md`, `README.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `.env.example` and operations documentation with worker startup, RL dataset protocol, `PYTHON_EXTRAS=ml,pdf,rl` setup, approval/promotion roles, paper order risk checks and runtime gates.

**OpenAPI inspection:** FastAPI emits **57 paths** in the current app. Phase 4 contributes **15 distinct paths / 18 HTTP operations**. Routes present:

- `POST /api/v1/rl/evaluations/jobs`; `GET /api/v1/rl/evaluations`; `GET /api/v1/rl/evaluations/comparison`.
- `GET/POST /api/v1/governance/models`; `GET /risk-review`; `GET /decisions`; `POST /decision`; `POST /promote`; `POST /rollback`.
- `GET/POST /api/v1/execution/accounts`; `GET /summary`; `GET/POST /orders`; `POST /kill-switch`; `POST /reconcile`; `GET /audit`.
- No path contains `live`; there is no live broker order path.

**Verification in this environment:**

- Full backend suite command: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src:backend pytest -p no:cacheprovider -ra -o addopts=''` => exit code **0**, 100 collected, **98 passed, 2 skipped**. The cache-provider plugin is disabled because, with it enabled in this sandbox, pytest completed all test dots but hung during interpreter teardown. Without the cache provider the full test process exits normally.
- Focused Phase 4: **14/14 passing** — 8 governance/paper execution tests, 2 OpenAPI contract tests and 4 RL alignment/scaling tests.
- SQLite Alembic lifecycle: upgrade to `0007_phase4_governance_rl_paper_execution`, assert all nine Phase 4 tables (`rl_policy_evaluations`, model versions/reviews/decisions, paper accounts/orders/fills/positions/ledger), downgrade to `0006_phase3_evidence_vector_checkpoints`, then re-upgrade to `0007`: passed.
- OpenAPI check: **57 paths**, expected Phase 4 methods found and no live execution paths.
- `python -m compileall -q backend src apps migrations`: passed.
- TypeScript/TSX syntax transpilation: **14 files, zero syntax diagnostics**. Full dependency-aware typecheck, Vite build and browser checks are not claimed.

**Unverified runtime dependencies:** Gymnasium and Stable-Baselines3 are absent, so actual PPO/SAC training/artifact loading was not run. Docker, PostgreSQL, Redis/Celery and PyArrow are unavailable; live queue dispatch, Postgres runtime, true Parquet worker output and live service recovery were not exercised. Frontend `node_modules` are absent; no npm typecheck/Vite bundle/browser end-to-end claim is made.

**Phase 4 status:** Source, API, schema/migration, test, frontend navigation and role-aware action implementation are delivered and offline-verified. Runtime integration remains pending. All order functionality remains strictly paper-only; there is no live broker adapter or real-money order endpoint.


## 2026-11-02 — Phase 5 feedback, operations, security and offline acceptance checkpoint

**Starting point:** Phase 5 had feedback/outcome models, strategy monitoring, drift/suggestion APIs, feedback and operations pages, observability and backup/deployment assets. This continuation strengthened the final research-to-outcome path and production-operations checks.

**Implementation and corrections in this increment:**

- Extended `backend/tests/test_phase5_feedback_operations.py` with a joined end-to-end workflow: one owner records model/run/paper-account-linked outcomes, adds a ten-observation forecast history, evaluates benchmark-relative strategy returns, performs model/reference/current-snapshot drift screening, generates drift/performance/bias suggestions, accepts a proposal and verifies the final feedback summary.
- Kept the Phase 5 run-import endpoint bound to succeeded owner-scoped experiment runs and worker-recorded equity artifact SHA-256; the API enforces path containment below `DATA_STORAGE_PATH`, validates the dated return frame and records run/artifact provenance. Replaying the same caller/run/hash returns the original monitoring snapshot; tampered files return conflict and foreign runs return not found.
- Hardened drift model/snapshot ownership and training/reference/current snapshot lineage. Operations health differentiates Redis from live Celery ping, reports worker names, stale jobs and recent failure metadata without disclosing exception text.
- Added archive path validation to data-volume backup/restore, including rejection of path traversal, absolute paths, symlinks/hardlinks/special members and oversized expansion; changed checksum sidecars to remain valid after moving the backup directory.
- Updated Prometheus alert rules, monitoring/operator guides, API list, README, roadmap, project progress and recruiter demo scenario. Corrected Compose API readiness to `/api/v1/health/ready` and Nginx/Vite `/health` aliases to `/api/v1/health`; added a regression test because the previous unversioned targets would return 404 and mark a healthy container unhealthy.

**Verification:**

- Full offline suite: **114 passed, 2 skipped** (116 collected; opt-in live PostgreSQL/Redis and PyArrow Parquet). `pytest.main()` returned exit code 0 under the isolated runner wrapper; the wrapper exits after the completed run because this sandbox intermittently retains interpreter threads at shutdown. The isolated health-proxy test exits normally.
- Phase 5 focused API suite: **12 passed**.
- SQLite migration lifecycle to `0009_phase5_outcome_lineage`, downgrade to `0008` and upgrade to head: passed; Phase 5 tables asserted.
- OpenAPI inspected: **69 paths**; all expected feedback/operations methods including `/feedback/strategies/evaluate-run` are registered; no live broker/order route exists.
- `python -m compileall`, targeted `py_compile`, `bash -n` and TOML/YAML parsing: passed.
- TypeScript/TSX syntax transpilation: **15 files, zero diagnostics** (not a full project typecheck or Vite build).
- `scripts/tests/test_data_archive_validator.sh`, `test_backup_scripts.sh`, and `test_data_volume_backup_restore.sh`: passed. These use mocked Docker/PostgreSQL command boundaries plus real tar where noted; they are not a live service restore drill.

**Files touched in this continuation include:** `backend/tests/test_phase5_feedback_operations.py`, `backend/app/api/v1/feedback.py`, `compose.yaml`, `docker-compose.yml`, `apps/web/nginx.conf`, `apps/web/vite.config.ts`, `README.md`, `PROJECT_PROGRESS.md`, `docs/api/README.md`, `docs/PHASE5_OPERATIONS.md`, `docs/ROADMAP.md`, `docs/interview/DEMO_SCENARIOS.md` and `docs/operations/README.md`. Prior Phase 5 implementation files, migrations, frontend pages, monitoring assets, GitHub workflows and safety scripts remain part of the same workspace.

**Not claimed:** Docker Compose deployment, live Postgres/pgvector or Redis/Celery runtime, real PyArrow import, Vite production/browser build, actual pg_dump/pg_restore or Docker-volume restore drill, live Prometheus/Grafana/OTel, load testing, or executed GitHub security scans. These require service-enabled infrastructure and are explicitly tracked as external validation.


**CI dependency correction (2026-11-02):** NumPy and scikit-learn are declared as base project dependencies because the RL environment and core Ridge/Random Forest evaluation paths import them unconditionally. The `ml` extra now contains only optional joblib, XGBoost, LightGBM and PyTorch dependencies. Updated model error messages and installation guidance to match. This ensures the GitHub backend CI install (`.[dev,observability]`) receives the packages required by the non-optional baseline tests.


### Final Phase 5 validation after dependency correction

- Promoted NumPy and scikit-learn to base dependencies so core RL and Ridge/Random Forest test paths are installed by the clean CI command; optional `ml` now installs joblib, XGBoost, LightGBM and PyTorch. Corrected user-facing import errors and docs.
- Backend: **114 passed, 2 skipped** after the dependency change (116 collected, `pytest.main()` return code 0); skipped live PostgreSQL/Redis and PyArrow integration remain gated by unavailable services/packages in this sandbox.
- Alembic: fresh SQLite upgrade to `0009_phase5_outcome_lineage`, downgrade to `0008`, re-upgrade to `0009`: passed.
- FastAPI OpenAPI: **69 paths**, all Phase 5 methods asserted; no live execution route.
- Frontend syntax: **15 implementation TS/TSX files**, zero syntax diagnostics (the `.d.ts` declaration file is intentionally not passed to `transpileModule`).
- `compileall`, YAML/TOML parsing, shell syntax, archive validator, backup script contract and tar round-trip tests: passed.
- Fresh ZIP regenerated after these changes; local database, caches, runtime artifacts and `.env` secrets excluded.


### Reference integration (2026-11-07)

- Read the five supplied reference archives against the existing code. Licences: four MIT, Stock Agent System has none (architecture-only, nothing used). Banking Fraud ML added nothing because `feedback/drift.py` (PSI and KS), the CI workflows and the tracking hooks already cover its patterns.
- New modules: `research/agents/{analysts,coordinator,hypothesis}.py`; `risk/allocation.py`; `reinforcement_learning/{environments/multi_asset_env,rewards/reward_schemes,evaluation/portfolio}.py`; `backtesting/universe.py`; `bollinger_mean_reversion_signal`. Edits to existing files: `research/graphs/workflow.py` (`multi_analyst` provider), `core/config.py` (provider literal), `models/baselines/strategies.py` (registry entry).
- Corrected a design point from the reference RL environment: it earns the close-to-close return starting at the decision bar; the new environment fills at the next open and earns open(t+1) to open(t+2).
- Tests added: `test_phase6_multi_analyst.py` (13), `test_phase6_multi_asset_rl.py` (15), `test_phase6_universe_and_baselines.py` (9). Full suite: 150 passed, 3 skipped. PPO and SAC were trained for real in this environment (CPU PyTorch from conda-forge, because the PyPI CUDA wheels did not fit the sandbox disk).
- Documentation: `docs/SOURCES_AND_ATTRIBUTION.md` rewritten with archive and licence hashes and adaptation notes; `third_party/licenses/` added; `references/REPOSITORY_CATALOG.md` and `PROJECT_PROGRESS.md` updated.
