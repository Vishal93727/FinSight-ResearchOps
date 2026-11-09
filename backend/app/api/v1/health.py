"""Liveness and dependency-readiness endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from finsight.core.config import get_settings
from finsight.infrastructure.database.session import engine

router = APIRouter(tags=["health"])


@router.get("/health", summary="Check API liveness")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "finsight-researchops-api"}


@router.get("/health/ready", summary="Check database and queue readiness")
async def readiness_check() -> dict:
    checks: dict[str, str] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    is_ready = all(value == "ok" for value in checks.values())
    if not is_ready:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks, "timestamp": datetime.now(UTC).isoformat()}
