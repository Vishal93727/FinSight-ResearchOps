# FinSight ResearchOps — Initial Data Model

## Implemented entities (Phases 1–3)

| Table | Purpose | Key fields |
|---|---|---|
| `users` | Application identities | id, email, full_name, password_hash, is_active, timestamps |
| `roles` | Backend permission roles | id, key, name, description |
| `user_roles` | Many-to-many role assignments | user_id, role_id |
| `instruments` | US equity/ETF catalogue | symbol, name, exchange, asset_type, currency, is_active |
| `data_providers` | Provider registry (no secrets) | key, display_name, provider_type, is_enabled, config |
| `data_snapshots` | Immutable point-in-time data artifacts | provider_key, instrument_symbol, dates, interval, status, file_path, format, sha256, row_count, manifest |
| `sec_company_records` | Latest stored SEC submissions payload per CIK | cik, company_name, URL, payload hash, submissions JSON, ingested_at |
| `audit_events` | Append-only event history | actor_user_id, action, resource_type/id, request_id, details, created_at |
| `research_hypotheses` | Evidence-linked research thesis and approval state | symbol, thesis, evidence JSON, status, owner_user_id, version |
| `feature_set_versions` | Immutable feature definitions pinned to one source snapshot | feature_key, version, definition JSON, definition hash, source_snapshot_id |
| `experiments` | Reproducible experiment configuration and lineage | hypothesis_id, dataset_snapshot_id, optional benchmark_snapshot_id, feature_set_version_id, configuration hash, status |
| `experiment_runs` | Individual execution attempts | experiment_id, run_number, status, random_seed, unique per-experiment idempotency_key, metrics, artifacts, timestamps |
| `experiment_risk_reviews` | Immutable deterministic risk result for a run | run_id (unique), decision, policy_version, limits, observed_metrics, breaches, warnings, deterministic flag |
| `research_documents` | Uploaded research sources with immutable content hash and parsed text | title, filename, media_type, content_sha256, character_count, chunk_count, parser metadata, owner |
| `document_chunks` | Bounded source chunks and deterministic embedding vectors | document_id, chunk_index, text, text_sha256, embedding JSON, token_count, section metadata |
| `research_reports` | Evidence-grounded report with review checkpoint | query, answer, citations, workflow_trace, evidence_verified, status, reviewer, review time |
| `model_evaluations` | Reproducible supervised ML evaluation manifest | dataset_snapshot_id, feature_set_version_id, model_family, features, target, configuration hash, metrics, artifact path |

## Phase 3 provenance and review rules

- Exact duplicate document bytes are blocked by a unique SHA-256 index.
- Every chunk links to a document and stores its own text hash, chunk index and embedding. The parent document metadata records the embedding provider/model/dimensions; queries filter out mismatched embedding spaces.
- Every report citation links to a document and chunk identifier plus source text hash; report workflow traces are persisted.
- Only ADMIN/RISK_REVIEWER can decide reports; non-admin report authors cannot approve their own reports.
- Every ML evaluation pins the READY market snapshot and immutable `feature_set_version_id`; the API verifies both data and feature-definition fingerprints before fitting. Comparisons are restricted to the same snapshot and optional feature-set lineage.

## Role catalogue

- `ADMIN`: platform configuration and user/role administration.
- `RESEARCH_ANALYST`: permitted public documents, provider data and research creation.
- `QUANT_RESEARCHER`: instrument catalogue writes, features, experiments and backtests.
- `RISK_REVIEWER`: restricted audit inspection and later risk/promotion decisions.
- `PORTFOLIO_ANALYST`: later paper positions, fills and performance.
- `READ_ONLY_VIEWER`: future approved report/dashboard access.

Self-registration assigns only `RESEARCH_ANALYST`. A first administrator is created with `backend/scripts/create_admin.py` after migrations. No public endpoint can grant the ADMIN role.

## Snapshot manifest

Each successfully ingested daily market dataset stores a content-addressed Parquet artifact and a manifest containing snapshot identifier, provider, instrument, date range, interval, timezone, adjustment policy, schema version, row count, SHA-256 and provenance. The database records the storage location and manifest. The exact incoming bars are validated for duplicate dates and OHLC invariants before persistence.

## Research-to-Outcome lineage (Phases 2–5)

```text
Research Hypothesis (DRAFT -> APPROVED/REJECTED)
  -> Evidence References
  -> Experiment Specification (canonical configuration hash)
      -> Data Snapshot + optional pinned Benchmark Snapshot
      -> Feature Set Version (definition hash) -> Experiment Run (idempotency key, metrics/artifacts)
          -> Experiment Risk Review (deterministic PASS / REVIEW / REJECT)
          -> Model Version -> Strategy -> Backtest
              -> Promotion Request -> Approval Decision
              -> Paper Order -> Fill -> Position
                  -> Outcome Evaluation -> Drift Event / New Hypothesis
```

The shared Research-to-Outcome Ledger identifiers are `hypothesis_id`, `experiment_id`, `model_version_id`, `strategy_id`, `decision_id`, `order_id`, `fill_id` and `outcome_id`.

## Data rules

- Preserve provider/source provenance and collection time.
- Keep historical snapshots immutable; new inputs produce new records.
- Use foreign keys, unique keys and idempotency keys where applicable.
- Store secrets only in environment/secret manager, never in provider JSON.
- Financial time-series training later requires `available_at <= decision_time` checks.
