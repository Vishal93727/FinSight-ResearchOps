# FinSight ResearchOps — Five-Phase Roadmap

## Phase 1 — Platform Foundation & Data Layer

Repository hygiene, modular configuration, Docker services, FastAPI, React/TypeScript, PostgreSQL migrations, Redis/Celery worker, logging/health, authentication/RBAC, instrument/provider catalogue, SEC submissions ingestion, historical OHLCV ingestion, immutable Parquet snapshots, and initial overview/research/operations UI.

**Acceptance:** clean setup, successful database migration, tested identity/RBAC, persisted catalogue and ingestion records, hashed Parquet snapshots, documented provider provenance, and frontend build/start verification.

## Phase 2 — Research & Quantitative Experiment Core

Implementation delivered: independently reviewed evidence-linked hypotheses; immutable feature sets and strict target separation; content fingerprints and snapshot verification; chronological train/validation/test windows with purge/embargo; buy-and-hold, moving-average and RSI baselines; train/validation diagnostics; holdout and rolling walk-forward evaluation; pinned benchmark comparisons; vectorized and event-driven portfolio accounting; next-close fills, cash, holdings and transaction costs; deterministic persisted risk reviews; local JSON experiment tracking plus optional MLflow; idempotent runs; run-comparison and risk-review APIs; Experiment Lab and Strategy & Backtest Lab UI. Automated offline tests and SQLite migration lifecycle pass. Live Celery/Redis/PostgreSQL/PyArrow execution and a Vite production build remain external runtime checks, so they are not represented as tested in this environment.

## Phase 3 — Financial Research AI & Advanced ML

**Source implementation delivered in this workspace:**

- Bounded TXT/Markdown/CSV/JSON/HTML/PDF ingestion with content hashes, safe parsing, section-aware overlapping chunks, source metadata and exact duplicate detection.
- Provider/model-versioned embeddings: deterministic feature hashing by default and optional CPU SentenceTransformer embeddings. The optional pgvector/HNSW schema, ingestion writes, provider-safe JSON-to-pgvector backfill script and pgvector retrieval path are implemented for the 384-dimensional index.
- Hybrid lexical/vector retrieval with MMR diversification and optional CPU cross-encoder reranking.
- Bounded evidence workflow (`validate_query -> retrieve_evidence -> synthesize -> verify_citations -> human_review`), deterministic extractive sentence citations by default, optional LangGraph StateGraph and optional LangChain/OpenAI synthesis.
- Per-node persisted checkpoint records containing exact evidence chunk IDs, bounded answer/citation recovery state and claim checks. A failed report can resume from its last committed checkpoint via `/research/reports/{id}/resume`; resume verifies document readiness and chunk/answer hashes and never performs fresh retrieval.
- Claim-level lexical/numeric support screening, source-ID validation and mandatory independent ADMIN/RISK_REVIEWER approval. The screen is explicitly heuristic, not semantic entailment or proof of factual truth.
- Durable Celery job flows for document ingestion, research Q&A and supervised model evaluation, with owner-scoped idempotency, queue-failure states, retry, deterministic report IDs, worker-redelivery recovery and rollback-safe worker failure handling.
- Chronological Ridge, Random Forest, XGBoost, LightGBM and CPU PyTorch LSTM evaluation pinned to immutable market snapshots and feature versions; model-family comparison by RMSE; transparent finance lexicon baseline and optional FinBERT probability adapter.
- Research Intelligence UI for document ingestion, queued jobs/retry, evidence-grounded research, checkpoint resume, human review, sentiment, supervised ML and model comparison.
- API/methodology/operations documentation and focused acceptance tests.

**Offline verification in this sandbox:** 84 tests passed and 2 environment-dependent tests skipped in the latest full run. Python compilation, SQLite migration upgrade/downgrade/re-upgrade through `0006_phase3_evidence_vector_checkpoints`, FastAPI OpenAPI route inspection (42 paths), and TypeScript/TSX syntax transpilation (10 source files, zero syntax diagnostics) have passed. These are source and offline checks, not a live production deployment.

**External runtime validation still open (environment gates, not missing source adapters):** live PostgreSQL/pgvector HNSW and backfill query; Redis/Celery execution/retry for all queued task families; PyArrow Parquet artifacts for model jobs; actual SentenceTransformer and cross-encoder weights; real LangGraph/LangChain/OpenAI execution (credentials are not stored); FinBERT weights/calibration; MLflow server integration; and frontend `npm ci`/Vite/browser acceptance. The current sandbox has no Docker executable, no PostgreSQL/Redis service, no node_modules, and no external model weights/credentials. Do not report those as verified until run in an environment that provides them.

## Phase 4 — Governance, Reinforcement Learning & Paper Execution

**Source/API/UI implementation delivered; runtime integration validation remains open.** Phase 4 includes a Gymnasium long-only portfolio environment; PPO/SAC Stable-Baselines3 training adapters; immutable READY-Parquet and feature-set lineage checks; target-free feature observations; training-only feature normalization; chronological out-of-sample evaluation; cost-aware rewards and artifacts; queued/idempotent RL jobs with retry; RL evaluation history/comparison APIs; model registry with artifact integrity and deterministic risk review; independent reviewer approval, admin promotion/rollback; paper accounts, deterministic order-risk checks, simulated fills/fees/slippage, positions, cash/ledger/audit, reconciliation and kill switch. React navigation now mounts an RL Strategy Lab, Model Governance and Paper Execution pages. There is no live broker adapter or live-order endpoint.

The RL UI supports READY snapshot and matching feature-set selection, PPO/SAC selection, bounded timesteps, queue status/retry, completed OOS metrics and same-lineage comparisons. Backend authorization remains authoritative; only ADMIN/QUANT_RESEARCHER can queue training. Governance requires a separate reviewer/admin decision, prohibits an author approving their own candidate, requires deterministic risk PASS for approval and reserves promotion/rollback to ADMIN. Paper execution accepts only internal account IDs and explicit simulation reference prices; kill-switch and exposure checks are deterministic.

**Offline verification recorded for the current Phase 4 increment:** full suite exit code 0 with **98 passed, 2 skipped** (100 collected). The two skips are the opt-in live PostgreSQL/Redis test and PyArrow Parquet test. Focused Phase 4 tests pass **14/14**. SQLite Alembic lifecycle through revision `0007_phase4_governance_rl_paper_execution`, OpenAPI inspection (57 total paths; 15 Phase 4 paths / 18 HTTP operations; no live routes), Python compilation and TypeScript/TSX syntax transpilation (14 files, zero diagnostics) pass. The test command disables pytest cache-provider (`-p no:cacheprovider`) because its presence causes a process-shutdown hang in this sandbox; with it disabled the suite exits normally. PostgreSQL/Redis/Celery runtime, actual Stable-Baselines3 PPO/SAC training, and a Vite browser build still need external verification. Exact results are in `PROJECT_PROGRESS.md` and `BUILD_LOG.md`.

## Phase 5 — Outcome Feedback & Production Readiness

**Source/API/UI and offline acceptance implementation delivered; external runtime validation remains open.** Phase 5 includes prediction-versus-realised outcome records with model/run/paper-account lineage; MAE/RMSE/bias/directional metrics; strategy performance monitoring both from manual aligned returns and from hash-verified Phase 2 equity-curve artifacts; PSI/KS drift screening with owner and snapshot-lineage checks; deduplicated follow-up research suggestions with human decisions; and Feedback & Monitoring plus Operations & Administration pages. Operations exposes separate Redis/Celery worker health, stale job counts, safe failure metadata and Admin-only dry-run/confirmed requeue.

Production-readiness assets include FastAPI Prometheus metrics, optional OpenTelemetry tracing, Compose Prometheus/Grafana/OTel services and alert rules, CI and dependency/security/release workflows, Docker health checks/restart policies, PostgreSQL and app-data backup/restore scripts, archive path/symlink validation, checksum verification, API security/recovery tests, operational runbooks and an interview demonstration script. A full research-to-outcome acceptance test covers outcome lineage, strategy evaluation, drift, suggestion generation and a human decision.

Offline acceptance includes the full unit/API suite, SQLite migration lifecycle, OpenAPI route inspection, Python compilation, frontend syntax checks, Compose/config parsing and mocked backup/restore/archive tests. This does not certify a live production deployment: Docker, PostgreSQL/pgvector, Redis/Celery, PyArrow Parquet, full npm/Vite/browser build, real database/volume restore drill, load tests and external dependency/container scans still need to run in a service-enabled CI/deployment environment.

## Delivery discipline

A feature is complete only when code, tests and a working demonstration support the claim. The current `PROJECT_PROGRESS.md` is the single phase checkpoint, and `BUILD_LOG.md` records exact file changes and verification outcomes.
