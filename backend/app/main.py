"""FinSight ResearchOps FastAPI application entry point."""
import logging
import uuid
from contextlib import asynccontextmanager
from time import perf_counter
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from app.api.v1.router import api_router
from finsight.core.config import get_settings
from finsight.core.logging import configure_logging
from finsight.infrastructure.observability.metrics import HTTP_REQUESTS, HTTP_DURATION, render_metrics
from finsight.infrastructure.observability.tracing import configure_fastapi_tracing

settings = get_settings()
configure_logging("DEBUG" if settings.debug else settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    debug=settings.debug,
    description=(
        "Traceable financial research, data ingestion, quantitative strategy operations and "
        "paper simulation. It does not execute live trades."
    ),
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
    )


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        if request.url.path != "/metrics":
            route = getattr(request.scope.get("route"), "path", "unmatched")
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route).observe(perf_counter() - start)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger("finsight.api").exception("Unhandled request error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", None)},
    )


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    body, media_type = render_metrics()
    return Response(content=body, media_type=media_type)


app.include_router(api_router, prefix="/api/v1")
configure_fastapi_tracing(app, service_name=settings.otel_service_name,
                          endpoint=settings.otel_exporter_otlp_endpoint)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"service": "finsight-researchops-api", "version": settings.api_version, "docs": "/docs"}
