"""Celery application for future long-running ingestion and research jobs."""

from celery import Celery

from finsight.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "finsight_researchops",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="finsight",
    timezone="UTC",
    enable_utc=True,
)
