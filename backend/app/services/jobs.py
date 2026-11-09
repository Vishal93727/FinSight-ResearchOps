"""Celery enqueue adapter. Imported lazily so API unit tests can run without Redis."""


def enqueue_system_ping(job_id: str) -> None:
    from app.workers.celery_app import celery_app

    celery_app.send_task("finsight.jobs.system_ping", args=[job_id])


def enqueue_document_ingestion(job_id: str) -> None:
    """Dispatch a staged document ingestion job to the dedicated Celery task."""
    from app.workers.celery_app import celery_app

    celery_app.send_task("finsight.documents.ingest", args=[job_id])


def enqueue_model_evaluation(job_id: str) -> None:
    """Dispatch a supervised model evaluation to the Celery worker queue."""
    from app.workers.celery_app import celery_app

    celery_app.send_task("finsight.ml.evaluate", args=[job_id])


def enqueue_research_ask(job_id: str) -> None:
    """Dispatch an evidence-grounded research workflow to the Celery worker."""
    from app.workers.celery_app import celery_app

    celery_app.send_task("finsight.research.ask", args=[job_id])


def enqueue_rl_evaluation(job_id: str) -> None:
    """Dispatch an out-of-sample PPO/SAC evaluation to the RL worker queue."""
    from app.workers.celery_app import celery_app

    celery_app.send_task("finsight.rl.evaluate", args=[job_id])
