"""Low-cardinality Prometheus HTTP metrics."""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.registry import REGISTRY

HTTP_REQUESTS = Counter(
    "finsight_http_requests_total", "HTTP requests served by the API",
    labelnames=("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "finsight_http_request_duration_seconds", "HTTP request duration in seconds",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
