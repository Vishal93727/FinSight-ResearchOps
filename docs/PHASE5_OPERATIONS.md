# Phase 5 — Feedback, Monitoring and Production Operations

## Outcome feedback and strategy monitoring

### Prediction versus realised outcome

`POST /api/v1/feedback/outcomes` records a forecast/realised-return pair. A record may retain `model_version_id`, `experiment_run_id`, and `paper_account_id` so an evaluation can be traced to the model, successful experiment run and paper portfolio that produced it. The API validates owner boundaries and model/run snapshot + feature-set lineage, enforces date ordering and supports owner-scoped idempotency. `GET /api/v1/feedback/summary` reports:

- MAE and RMSE in decimal-return units.
- Mean signed forecast bias (predicted minus realised).
- Directional accuracy for non-zero prediction/realisation pairs.
- Latest outcomes, model/run links, strategy snapshots, drift assessments and proposed research suggestions.

These are diagnostics, not profit forecasts or investment advice.

### Strategy performance

`POST /api/v1/feedback/strategies/evaluate` accepts aligned decimal-period returns and optional benchmark returns. The persisted summary contains compounded return, annualised volatility, annualised Sharpe diagnostic, drawdown, win rate and optional benchmark-relative excess return. Annualisation assumes 252 observations per year; callers must provide consistently sampled periods and an aligned benchmark.

For the integrated research workflow, use `POST /api/v1/feedback/strategies/evaluate-run` with a successful Phase 2 `experiment_run_id`. The endpoint:

1. Enforces owner/Admin access to the completed run.
2. Requires a persisted equity-curve path and SHA-256 digest from the worker.
3. Resolves the artifact under `DATA_STORAGE_PATH`, rejects paths outside that directory, verifies the digest and parses the Parquet result.
4. Requires a bounded dated return series and stores the metrics with the experiment-run ID and artifact hash as source lineage. Repeating the same import for the same caller/run/artifact hash returns the existing monitoring snapshot rather than creating a duplicate.

Older runs without a pinned equity-curve hash must be rerun with the current worker before they can be imported. This endpoint requires PyArrow in the API runtime; when it is absent, it returns a service-unavailable response rather than guessing metrics.

## Drift and follow-up research

`POST /api/v1/feedback/drift/check` compares named reference/current numeric samples. Each named feature requires at least ten finite observations. The API can pin a model version and reference/current READY data snapshots; linked records must belong to the caller (unless Admin) and match the model's training instrument/snapshot lineage. It stores PSI and empirical KS diagnostics. PSI below 0.10 is labelled stable, 0.10–0.25 review, and at/above 0.25 drift. These are investigation thresholds—not automatic retraining, risk override or model-promotion triggers.

`POST /api/v1/feedback/suggestions/generate` creates deterministic, deduplicated proposals from saved drift assessments, forecast bias and recent strategy monitoring. Suggestions are advisory. A Quant Researcher or Admin must accept/dismiss each proposal with a comment. A suggestion cannot promote a model, place an order or disable a risk control.

## Operations, health and recovery

`GET /api/v1/operations/summary` reports database counts for jobs, experiment runs, model states, paper accounts/orders and feedback records. It distinguishes Redis connectivity from Celery worker liveness: Redis ping alone does not mean a worker is consuming tasks. The response includes responding worker names, jobs older than the 30-minute operational threshold and recent failure metadata. Exception text is intentionally not exposed to broad read-only operations roles.

`POST /api/v1/operations/recover-stale-jobs` is Admin-only. It defaults to a dry-run listing of QUEUED, QUEUE_FAILED or old RUNNING jobs. Inspect worker health and logs before sending `confirm_requeue=true`. Supported task types are explicitly mapped; unknown types are not dispatched. Requeued task IDs are preserved, with idempotency protection where the task family supports it. Review job status and audit history after recovery.

## Observability

- `GET /metrics` exposes request counters and request-duration histograms with low-cardinality method, route-template and status labels; raw URL IDs are not metric labels. The frontend reverse proxy forwards `/metrics` to the API service.
- OpenTelemetry FastAPI tracing is enabled only when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured and the `observability` extra is installed.
- Compose includes an OTLP collector, Prometheus (15-day local retention), alert rules for API target loss, elevated 5xx rate and high p95 latency, and Grafana provisioning/dashboard files.
- The starter alerts are technical availability/latency indicators, not financial strategy or investment-performance alerts.
- Supplied monitoring ports bind to loopback. Use a TLS/authenticated reverse proxy and network policy before any remote exposure.

## Docker deployment

1. Copy `.env.example` to `.env`.
2. Set unique strong `POSTGRES_PASSWORD`, `JWT_SECRET` (at least 32 random characters) and `GRAFANA_ADMIN_PASSWORD`; replace the SEC contact placeholder with a monitored contact.
3. Run `docker compose config` and inspect the rendered configuration for accidental secrets and unexpected host bindings.
4. Run `docker compose up --build -d`.
5. Check `docker compose ps`, `docker compose logs --tail=100 api worker`, `http://localhost:5173/health` and `http://localhost:5173/api/v1/health/ready`.
6. Open the UI at `http://localhost:5173`, API docs at `http://localhost:5173/docs`, Prometheus at `http://localhost:9090` and Grafana at `http://localhost:3000`.
7. Bootstrap the first administrator with `docker compose exec api python backend/scripts/create_admin.py --email admin@example.com --name "Platform Admin"`.

For PPO/SAC workers, build with `PYTHON_EXTRAS=ml,pdf,rl,observability`. This installs substantial optional dependencies; training also requires suitable CPU/GPU resources. Do not publish PostgreSQL, Redis, Prometheus, Grafana or OTLP ports to the public internet without network policy and authentication.

## Backup, verify and restore

### PostgreSQL logical backup

The scripts require PostgreSQL client tools (`pg_dump`, `pg_restore`) and Python 3 on the host, plus a host-reachable `DATABASE_URL` (typically the Compose loopback port). Credentials are parsed into a mode-0600 temporary `PGPASSFILE`; the client process receives host/user/database arguments, not the password or full URL.

```bash
DATABASE_URL='postgresql+psycopg://finsight:...@localhost:5432/finsight' \
  BACKUP_DIR=./backups ./scripts/backup_postgres.sh
./scripts/verify_backup.sh ./backups/finsight_YYYYMMDDTHHMMSSZ.dump
```

Keep encrypted copies off-host with restricted access and a retention policy. The archive, SHA-256 sidecar and JSON manifest are created with restrictive permissions. A matching checksum and successful archive listing do not prove the database can be restored.

### App-data volume backup

```bash
BACKUP_FILE=./backups/finsight_app_data_YYYYMMDDTHHMMSSZ.tar.gz \
  ./scripts/backup_data_volume.sh
```

The script backs up the Compose `app_data` volume, validates the resulting tar members, and writes a relocatable checksum sidecar. The validator rejects absolute paths, parent-directory traversal, symbolic/hard links, special files, excessive entry counts and excessive expanded archive sizes.

### Restore drill

Restore is destructive and requires explicit `CONFIRM_RESTORE=YES`. Use a dedicated staging database/volume first:

```bash
DATABASE_URL='postgresql+psycopg://finsight:...@localhost:5432/finsight_restore_test' \
BACKUP_FILE=./backups/finsight_YYYYMMDDTHHMMSSZ.dump \
CONFIRM_RESTORE=YES ./scripts/restore_postgres.sh

BACKUP_FILE=./backups/finsight_app_data_YYYYMMDDTHHMMSSZ.tar.gz \
CONFIRM_RESTORE=YES ./scripts/restore_data_volume.sh
```

The restore scripts verify checksums before writing. The data-volume restore validates archive members before extraction, stops API/worker writers and extracts without preserving archive ownership/permissions. After restore, start only the API and verify migration head, readiness, row counts, application login and document/artifact hashes. Then start the worker and execute a controlled queued job before normal traffic resumes. External object storage requires its own provider-native versioned backup/restore and credential plan. For a consistent recovery point, stop writers and take the database dump and data-volume archive in the same maintenance window.

## Verification performed in this workspace

Offline tests exercise feedback calculations, outcome idempotency and lineage, strategy-run artifact hash validation (with the Parquet reader stubbed), drift ownership, suggestions and human decisions, operations worker/failure metadata, metrics routing, stale-job dry-run/requeue, backup script safety and archive path validation. SQLite migration lifecycle and API/OpenAPI/static-source checks are also run.

These checks do **not** replace a live recovery drill. Docker/PostgreSQL/Redis/Celery runtime, actual Parquet import, real `pg_dump`/`pg_restore` against a database, restoring an actual Compose volume, Prometheus/Grafana/OTel container wiring, browser E2E, load testing and external vulnerability scans remain service-enabled validation gates. The project does not claim those were executed in this restricted workspace.
