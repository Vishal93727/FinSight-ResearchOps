# FinSight production observability

## Signals

- API exposes Prometheus metrics at `/metrics` (excluded from OpenAPI). HTTP counters use bounded labels: method, registered route template and status; request duration is a histogram.
- Optional OpenTelemetry FastAPI tracing exports OTLP/HTTP spans to the collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured and the `observability` extra is installed.
- Prometheus scrapes the API and collector. Three alert rules cover scrape target down, sustained 5xx ratio above 5%, and p95 API latency above two seconds.
- Grafana provisions the Prometheus datasource and the FinSight API dashboard automatically.

## Local Compose endpoints

| Service | URL | Purpose |
|---|---|---|
| API docs | http://localhost:8000/docs | OpenAPI / interactive API docs |
| Frontend | http://localhost:5173 | React application |
| Prometheus | http://localhost:9090 | Metrics and alert state |
| Grafana | http://localhost:3000 | Dashboards (credentials from `.env`) |

All published ports bind to loopback by default. Do not expose these endpoints directly to the public internet. Place a TLS-terminating reverse proxy and network policy in front of a production deployment.

## Operating interpretation

Metrics are operational indicators, not trading or model-quality claims. A high 5xx or latency alert should be investigated using request IDs, logs and traces. Worker availability is separately shown in `/api/v1/operations/summary`; a healthy Redis broker does not prove that a Celery worker is responding.

Prometheus currently retains 15 days in the named volume. Back up Prometheus/Grafana volumes if their history and dashboards must survive a host failure. API custom metrics currently describe HTTP traffic only; no high-cardinality user, instrument, query or job IDs are used as metric labels.
