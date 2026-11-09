"""Queue adapter for long-running quantitative experiment executions."""


def enqueue_experiment_run(run_id: str) -> None:
    """Dispatch a persisted run ID; imports Celery lazily for API testability."""
    from app.workers.celery_app import celery_app

    celery_app.send_task("finsight.experiments.run_baseline", args=[run_id])
