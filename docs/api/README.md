# Research and Quantitative Experiment API

All routes below are under `/api/v1`. Authenticated endpoints require `Authorization: Bearer <access-token>`. Permissions are enforced by the API; frontend controls are not a security boundary.

## Research hypothesis lifecycle

### Create a hypothesis

`POST /research/hypotheses` — `ADMIN`, `RESEARCH_ANALYST` or `QUANT_RESEARCHER`.

```json
{
  "title": "MSFT short-horizon momentum",
  "symbol": "MSFT",
  "thesis": "Positive five-session momentum may predict next-session returns.",
  "rationale": "A falsifiable explanation for an offline baseline evaluation.",
  "evidence": [
    {"source_type": "sec_filing", "source_id": "filing-or-url", "excerpt": "Evidence excerpt"}
  ]
}
```

A new hypothesis is `DRAFT`. Its owner (or an administrator) submits it with `POST /research/hypotheses/{id}/submit-review`. An `ADMIN` or `RISK_REVIEWER` decides with `POST /research/hypotheses/{id}/decision` and `{ "decision": "APPROVE", "note": "..." }` or `REJECT`. Only approved hypotheses can be used to create experiments. Mutations are audit logged.

## Versioned feature definitions

`POST /features/versions` — `ADMIN` or `QUANT_RESEARCHER`.

```json
{
  "feature_key": "ohlcv_momentum",
  "description": "Close-derived price features",
  "source_snapshot_id": "<ready-data-snapshot-id>",
  "definition": {
    "inputs": ["open", "high", "low", "close", "volume"],
    "features": ["return_1d", "momentum_5d", "sma_ratio_5d", "volatility_20d"],
    "target": "next_day_return",
    "target_shift": -1
  }
}
```

The API assigns a monotonically increasing version per feature key and a canonical SHA-256 definition fingerprint. The selected input features must be from the registered feature catalogue; the future target is not a valid input feature. Feature versions are pinned to one READY source snapshot.

## Experiment specification

`POST /experiments` — `ADMIN` or `QUANT_RESEARCHER`. `GET /experiments` lists authorized specifications.

The body includes `name`, `hypothesis_id`, `dataset_snapshot_id`, `feature_set_version_id`, optional `benchmark_snapshot_id`, and a strict `configuration`. The configuration supports:

- `model_family`: currently `baseline`.
- `baseline`: `buy_and_hold`, `moving_average_crossover` or `rsi_mean_reversion`.
- `target`: currently `next_day_return`; prediction horizon and purge/embargo days are explicit.
- Chronological `train_start`, `train_end`, `validation_start`, `validation_end`, `test_start`, `test_end`.
- `evaluation_mode`: `holdout` or `walk_forward`, plus walk-forward test/step days.
- Baseline parameters, deterministic random seed, commission and slippage in basis points, and `benchmark_symbol`.

Date windows must be ordered, separated by the configured target-horizon plus purge gap, and covered by the source snapshot. A pinned benchmark snapshot must be READY, match `benchmark_symbol`, and cover the test window. The server stores the canonical configuration and SHA-256 fingerprint.

## Run lifecycle

`POST /experiments/{experiment_id}/runs` — `ADMIN` or `QUANT_RESEARCHER`.

Optional `Idempotency-Key` header: 1–128 printable ASCII characters. A repeated key returns the original run instead of enqueuing another. A run can be `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` or `QUEUE_FAILED`; a `QUEUE_FAILED` run can be retried with the same key. Without a key, each submission creates a new numbered run.

`GET /experiments/{experiment_id}/runs` returns run status, metrics, error category and artifact manifest. The worker verifies dataset, feature-definition and configuration hashes before evaluation. It persists feature frame, configuration, metrics, risk review and equity-curve artifacts when the worker runtime dependencies are available.

## Metrics and risk review

`GET /experiments/{experiment_id}/runs/comparison` returns per-run status, total/annualized return, Sharpe ratio, drawdown, annualized volatility, benchmark return, information ratio and risk decision.

`GET /experiments/{experiment_id}/runs/{run_id}/risk-review` returns the policy version, thresholds, observed metrics, hard breaches, warnings and `deterministic` / `override_allowed` flags. The Phase 2 policy returns `PASS`, `REVIEW` or `REJECT`; no LLM can override it.

## Execution and interpretation boundaries

Close-time signals are filled at the next close; newly established positions do not receive the preceding close-to-close move. Commission and slippage are charged against turnover. Portfolio engines are long-only and capped at 1.0x gross exposure by default. The API is for research and historical paper simulation only: no live broker orders, real-money execution, investment advice or profitability guarantees are provided.

A missing benchmark is explicitly reported as unavailable; the platform does not synthesize benchmark data. The current Phase 2 worker uses immutable Parquet snapshots and therefore requires PyArrow, Celery, Redis and a configured database at runtime. Those external worker integrations still need deployment-level verification where those services are available.

## Phase 3 — document intelligence and advanced ML

### Document ingestion and indexing

- `POST /documents/upload` — synchronous bounded multipart upload for small local/test jobs. Accepts TXT/Markdown/CSV/JSON/HTML/PDF and returns content SHA-256, parser metadata, chunk count and document ID.
- `POST /documents/upload/jobs` — stages the validated upload under the configured data directory and creates a durable `documents.ingest` job. Supports a multipart `idempotency_key`; replay with the same key and same content returns the existing job, while reuse with different content returns 409. A queue outage is persisted as `QUEUE_FAILED` and can be retried through `POST /jobs/{job_id}/retry`.
- `GET /documents` and `GET /documents/{document_id}` — inspect indexed document metadata and provenance.
- `GET /jobs` and `GET /jobs/{job_id}` — inspect owner-scoped job status. `ADMIN` can inspect all jobs. `POST /jobs/{job_id}/retry` is owner/ADMIN scoped and retries only a `QUEUE_FAILED` dispatch for supported job types (`system.ping`, `documents.ingest`, `research.ask`, `ml.evaluate`, `rl.evaluate`); it does not make a failed business operation appear successful.

### Evidence-grounded research

- `POST /research/ask` — synchronous hybrid lexical/vector retrieval, optional cross-encoder reranking, evidence synthesis, claim screening and report creation. Body: `{ "query": "...", "top_k": 6, "lexical_weight": 0.45, "diversity_weight": 0.15, "document_ids": null }`.
- Reports with checked source linkage and all lexical/numeric claim checks passing enter `AWAITING_REVIEW`; no evidence or a failed claim screen produces `NO_EVIDENCE`.
- `POST /research/ask/jobs` — same research roles and request fields plus required `idempotency_key` (8–128 characters). Creates a `research.ask` job; same-key/same-payload replay returns the original job, while a key collision returns 409. Queue dispatch failure is stored as `QUEUE_FAILED` and can be retried with `POST /jobs/{job_id}/retry`. A successful job returns `report_id` in `job.result`. Worker redelivery recovers a completed report by deterministic job/report ID rather than generating a duplicate.
- `GET /research/reports` and `GET /research/reports/{report_id}` — inspect report status, cited chunk hashes and workflow trace.
- `GET /research/reports/{report_id}/checkpoints` — inspect durable per-node snapshots (query, exact evidence chunk IDs, bounded answer/citation recovery state and claim-check summary). A failed report can be resumed through `POST /research/reports/{report_id}/resume`; the endpoint reloads the exact evidence chunk IDs and verifies their source hashes and answer hash before continuing from the last supported node.
- `POST /research/reports/{report_id}/decision` — ADMIN/RISK_REVIEWER only; body `{ "decision": "APPROVE"|"REJECT", "comment": "..." }`. A non-admin report author cannot approve their own report.

The default path is deterministic feature-hash embeddings plus extractive sentence-level citations. Optional local SentenceTransformer embeddings, cross-encoder reranking, LangGraph `StateGraph`, and LangChain OpenAI synthesis require the `semantic`/`research-ai` extras and cached weights/credentials. Citation screening validates every factual sentence's adjacent citation, lexical overlap and numeric tokens; this is a conservative heuristic, **not semantic entailment or a factuality guarantee**. Human review remains mandatory.

### Supervised model evaluation and sentiment

- `POST /ml/evaluations` — bounded synchronous supervised evaluation pinned to a READY Parquet snapshot and a feature-set version created from that snapshot.
- `POST /ml/evaluations/jobs` — queue the same evaluation via `ml.evaluate`; supports an idempotency key. The Celery worker calls the same validated evaluation service and persists a model artifact/metrics. Queue dispatch failure is retryable through `/jobs/{job_id}/retry`.
- `GET /ml/evaluations` — list stored training/evaluation manifests and metrics.
- `GET /ml/evaluations/compare?snapshot_id=...&feature_set_version_id=...` — rank completed evaluations by RMSE for the exact same pinned snapshot and feature set. Prediction metrics are not strategy returns.
- `POST /ml/sentiment` — body `{ "text": "...", "provider": "lexicon"|"finbert" }`; the lexicon is the default, while FinBERT requires the optional `finbert` extra and cached pretrained model weights.

The base install includes NumPy, pandas and scikit-learn for core Ridge/Random Forest evaluation. Install optional XGBoost/LightGBM/PyTorch model dependencies with `pip install -e '.[ml]'`, PDF parsing with `pip install -e '.[pdf]'`, learned embeddings/reranking with `pip install -e '.[semantic]'`, LangGraph/LangChain providers with `pip install -e '.[research-ai]'`, and FinBERT with `pip install -e '.[finbert]'`. No API key or model credential is stored in the repository.

### PostgreSQL vector search

Migration `0006_phase3_evidence_vector_checkpoints` enables the `vector` extension on PostgreSQL and creates `document_chunks.embedding_vector vector(384)` plus a cosine HNSW index. Set `DOCUMENT_VECTOR_BACKEND=pgvector` only after applying the migration. Existing JSON embeddings can be copied without re-embedding via `PYTHONPATH=src:backend python scripts/backfill_pgvector_embeddings.py --batch-size 250`; the script rejects provider/model mismatches. New ingestions write the JSON vector and pgvector column together. SQLite continues to use JSON storage.

## Phase 4 — governance, RL evaluation and paper execution

All routes below are under `/api/v1`; permissions are enforced by FastAPI role dependencies and are not controlled by frontend visibility.

### PPO/SAC evaluation

`POST /rl/evaluations/jobs` — `ADMIN` or `QUANT_RESEARCHER`. Required body fields include:

```json
{
  "idempotency_key": "rl-eval-run-001",
  "dataset_snapshot_id": "<ready-parquet-snapshot-id>",
  "feature_set_version_id": "<feature-version-from-that-snapshot>",
  "algorithm": "PPO",
  "price_column": "close",
  "date_column": "date",
  "seed": 42,
  "total_timesteps": 20000,
  "train_fraction": 0.7,
  "fee_bps": 5,
  "slippage_bps": 5
}
```

The endpoint only queues the durable `rl.evaluate` job and returns `202 Accepted`; it does not mean the model has trained. The request accepts only `PPO` or `SAC`, canonical `date`/`close` columns, 5,000–2,000,000 timesteps and a 0.60–0.85 training fraction. The snapshot must be READY Parquet and the selected feature version must originate from that exact snapshot. The worker rechecks file and feature-definition hashes before training. Job status is inspected through `GET /jobs`; owner/ADMIN queue retry uses `POST /jobs/{id}/retry` after a dispatch failure.

`GET /rl/evaluations` lists saved results. `GET /rl/evaluations/comparison?dataset_snapshot_id=...&feature_set_version_id=...` returns only successful out-of-sample results pinned to that exact snapshot and feature-set version; it is not a global leaderboard.

Install `pip install -e '.[rl]'` to enable Gymnasium and Stable-Baselines3. The default offline environment can inspect routes and queue contracts but cannot execute PPO/SAC training without the optional dependencies, a worker, Redis, Parquet data and a compatible runtime. RL environment actions are long-only target exposure in [0, 1], with no shorting or leverage. Features are point-in-time and scaled using training rows only; evaluation uses the later chronological holdout. See [`docs/operations/PHASE4_OPERATIONS.md`](../operations/PHASE4_OPERATIONS.md).

### Model registry and approval lifecycle

- `GET /governance/models` — ADMIN, RISK_REVIEWER, QUANT_RESEARCHER, PORTFOLIO_ANALYST or READ_ONLY_VIEWER.
- `POST /governance/models` — ADMIN or QUANT_RESEARCHER; registers a candidate from a successful chronological supervised evaluation or successful OOS PPO/SAC evaluation. Artifact paths are constrained to the configured data directory and artifact SHA-256 is checked.
- `GET /governance/models/{model_version_id}/risk-review` — inspect deterministic risk policy, thresholds, observed metrics, hard breaches and warnings. An LLM/UI cannot override this decision.
- `GET /governance/models/{model_version_id}/decisions` — inspect reviewer history.
- `POST /governance/models/{model_version_id}/decision` — ADMIN or RISK_REVIEWER. Only CANDIDATE versions can be decided; candidate authors cannot approve their own version; APPROVE requires deterministic risk PASS.
- `POST /governance/models/{model_version_id}/promote` — ADMIN only; requires independent APPROVED state and deterministic risk PASS. An existing promoted version under the same model key becomes SUPERSEDED.
- `POST /governance/models/{model_version_id}/rollback` — ADMIN only; audited rollback operation.

### Paper-only accounts and execution

- `POST /execution/accounts` — ADMIN or PORTFOLIO_ANALYST; create an internal paper account with cash, fee/slippage and exposure limits.
- `GET /execution/accounts` — authorized account readers.
- `GET /execution/accounts/{account_id}/summary` — cash, market value, equity, gross exposure and positions.
- `POST /execution/accounts/{account_id}/orders` — ADMIN or PORTFOLIO_ANALYST; requires a promoted risk-PASS model, explicit `simulation_reference_price`, positive quantity and a unique per-account `client_order_id`. The broker applies simulated slippage/fees, deterministic pre/post-trade cash and exposure checks, then records an internal fill and ledger entry. The reference price is not fetched from a live quote source.
- `GET /execution/accounts/{account_id}/orders` — authorized account readers.
- `POST /execution/accounts/{account_id}/kill-switch` — ADMIN/RISK_REVIEWER. Activation halts subsequent orders; deactivation is ADMIN-only.
- `POST /execution/accounts/{account_id}/reconcile` — authorized inspection; ledger repair is ADMIN-only and rebuilds state from fill history.
- `GET /execution/accounts/{account_id}/audit` — authorized inspection of orders, fills, ledger entries and audit events.

There is no live broker adapter, broker credential field, `/live` route or real-money order endpoint. These APIs only support internal simulated paper execution. See the full operator sequence and risk constraints in [`docs/operations/PHASE4_OPERATIONS.md`](../operations/PHASE4_OPERATIONS.md).


## Phase 5 — outcome feedback and operations

### Prediction and strategy outcomes

- `POST /feedback/outcomes` — ADMIN/QUANT_RESEARCHER/PORTFOLIO_ANALYST; records predicted and realised decimal returns with an owner-scoped idempotency key. Optional `model_version_id`, `experiment_run_id` and `paper_account_id` are validated for ownership and compatible snapshot/feature lineage.
- `GET /feedback/outcomes` — authorized readers; lists owner-scoped feedback observations.
- `GET /feedback/summary` — authorized readers; outcome MAE/RMSE/bias/directional accuracy, latest outcomes, strategy snapshots, drift and suggestions.
- `POST /feedback/strategies/evaluate` — ADMIN/QUANT_RESEARCHER/PORTFOLIO_ANALYST; stores metrics from an aligned decimal-return array and optional benchmark array. Annualised metrics assume 252 equally spaced observations.
- `POST /feedback/strategies/evaluate-run` — same writer roles; imports a SUCCEEDED Phase 2 experiment run's equity curve. Caller ownership, path containment, worker-recorded SHA-256, Parquet schema and bounded dated rows are checked before a snapshot is stored with `experiment_run:<id>` and artifact hash lineage. Repeating the same caller/run/hash import returns the prior snapshot. Requires PyArrow in the API process.
- `GET /feedback/strategies` — authorized readers; inspect persisted monitoring snapshots.

### Drift and research follow-up

- `POST /feedback/drift/check` — ADMIN/QUANT_RESEARCHER/RISK_REVIEWER; accepts named reference/current feature samples (at least 10 finite observations each). Optional model/reference/current snapshot references are owner-scoped, READY-checked and validated for training snapshot/instrument consistency. Results store PSI and empirical KS as screening diagnostics.
- `GET /feedback/drift-assessments` — authorized readers.
- `POST /feedback/suggestions/generate` — ADMIN/QUANT_RESEARCHER/RISK_REVIEWER; create deterministic, deduplicated proposals from forecast bias, strategy monitoring and drift.
- `GET /feedback/suggestions` — authorized readers.
- `POST /feedback/suggestions/{suggestion_id}/decision` — owner/Admin Quant Researcher; accepts or dismisses one PROPOSED suggestion with a required comment. Suggestions do not perform retraining, promotion or execution.

### Operations and service recovery

- `GET /operations/summary` — ADMIN/RISK_REVIEWER/PORTFOLIO_ANALYST/READ_ONLY_VIEWER; service state, Redis ping and separate Celery worker ping, responding worker names, job/run/order/model/account and feedback counts, stale-job count and recent failure metadata (without raw exception messages).
- `POST /operations/recover-stale-jobs` — ADMIN only; dry-run by default. Requeue requires `confirm_requeue=true`; task types are allow-listed and unsupported work is not dispatched.
- `GET /metrics` — Prometheus scrape endpoint, outside the `/api/v1` prefix; route-template labels avoid high-cardinality resource IDs.

The operations guide [`docs/PHASE5_OPERATIONS.md`](../PHASE5_OPERATIONS.md) documents Compose deployment, monitoring/alerts, worker recovery and backup/restore. The paper-execution API remains simulated only; there is no live broker endpoint.
