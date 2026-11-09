"""Idempotent worker tasks for queue verification and future domain jobs."""

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

from sqlalchemy import select

from finsight.infrastructure.database.session import SessionLocal
from finsight.infrastructure.database.models import JobRecord, DataSnapshot
from finsight.experiments.models import Experiment, ExperimentRun
from finsight.experiments.runner import run_baseline_experiment
from finsight.experiments.tracking import create_experiment_tracker
from finsight.experiments.registry import configuration_sha256
from finsight.features.engineering import build_declared_feature_frame
from finsight.features.models import FeatureSetVersion
from finsight.risk.models import ExperimentRiskReview
from finsight.risk.policy import evaluate_backtest_risk
from finsight.core.config import get_settings
from app.workers.celery_app import celery_app
from app.services.document_jobs import process_document_ingestion_job
from app.services.worker_state import mark_failed_after_rollback


def _sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash large immutable market-data artifacts without loading them into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@celery_app.task(name="finsight.jobs.system_ping", autoretry_for=(), acks_late=True)
def ping_job(job_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        job = db.scalar(select(JobRecord).where(JobRecord.id == job_id))
        if job is None:
            return {"status": "missing", "job_id": job_id}
        if job.status == "SUCCEEDED":
            return {"status": "already_succeeded", "job_id": job_id}
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        db.commit()
        try:
            result = {"status": "ok", "worker": "finsight-researchops", "job_id": job_id}
            job.result = result
            job.status = "SUCCEEDED"
            job.completed_at = datetime.now(UTC)
            db.commit()
            return result
        except Exception as exc:
            mark_failed_after_rollback(db, JobRecord, job_id, type(exc).__name__)
            raise


@celery_app.task(name="finsight.experiments.run_baseline", autoretry_for=(), acks_late=True)
def run_baseline_experiment_task(run_id: str) -> dict[str, str]:
    """Execute one queued baseline run and persist metrics/equity-curve artifacts."""
    with SessionLocal() as db:
        run = db.get(ExperimentRun, run_id)
        if run is None:
            return {"status": "missing", "run_id": run_id}
        if run.status == "SUCCEEDED":
            return {"status": "already_succeeded", "run_id": run_id}
        if run.status != "QUEUED":
            return {"status": run.status.lower(), "run_id": run_id}
        run.status = "RUNNING"
        run.started_at = datetime.now(UTC)
        db.commit()
        try:
            experiment = db.get(Experiment, run.experiment_id)
            if experiment is None:
                raise ValueError("Experiment record is missing")
            snapshot = db.get(DataSnapshot, experiment.dataset_snapshot_id)
            if snapshot is None or snapshot.status != "READY":
                raise ValueError("Experiment dataset snapshot is unavailable")
            if snapshot.storage_format.lower() != "parquet":
                raise ValueError("Experiment dataset snapshot must be stored as Parquet")
            if _sha256_file(snapshot.file_path) != snapshot.sha256:
                raise ValueError("Dataset snapshot content hash does not match its immutable manifest")
            if configuration_sha256(experiment.configuration) != experiment.configuration_sha256:
                raise ValueError("Experiment configuration fingerprint mismatch")
            feature_set = db.get(FeatureSetVersion, experiment.feature_set_version_id)
            if feature_set is None or feature_set.source_snapshot_id != snapshot.id:
                raise ValueError("Experiment feature-set lineage is unavailable or mismatched")
            if configuration_sha256(feature_set.definition) != feature_set.definition_sha256:
                raise ValueError("Feature-set definition fingerprint mismatch")
            bars = pd.read_parquet(snapshot.file_path)
            feature_frame = build_declared_feature_frame(bars, feature_set.definition)
            benchmark_bars = None
            benchmark_snapshot = None
            if experiment.benchmark_snapshot_id:
                benchmark_snapshot = db.get(DataSnapshot, experiment.benchmark_snapshot_id)
                if benchmark_snapshot is None or benchmark_snapshot.status != "READY":
                    raise ValueError("Pinned benchmark snapshot is unavailable")
                if benchmark_snapshot.storage_format.lower() != "parquet":
                    raise ValueError("Benchmark snapshot must be stored as Parquet")
                if _sha256_file(benchmark_snapshot.file_path) != benchmark_snapshot.sha256:
                    raise ValueError("Benchmark snapshot content hash does not match its immutable manifest")
                if benchmark_snapshot.instrument_symbol.upper() != experiment.configuration.get("benchmark_symbol", "SPY").upper():
                    raise ValueError("Pinned benchmark snapshot does not match the experiment benchmark symbol")
                benchmark_bars = pd.read_parquet(benchmark_snapshot.file_path)
            result = run_baseline_experiment(bars, experiment.configuration, benchmark_bars=benchmark_bars)
            risk_result = evaluate_backtest_risk(result.metrics)
            result.metrics["risk_decision"] = risk_result["decision"]
            result.metrics["risk_policy_version"] = risk_result["policy_version"]

            settings = get_settings()
            artifact_dir = Path(settings.data_storage_path).resolve() / "experiments" / experiment.id / run.id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            equity_path = artifact_dir / "equity_curve.parquet"
            metrics_path = artifact_dir / "metrics.json"
            risk_path = artifact_dir / "risk_review.json"
            feature_path = artifact_dir / "features.parquet"
            configuration_path = artifact_dir / "experiment_config.json"
            result.equity_curve.to_parquet(equity_path, index=False)
            feature_frame.to_parquet(feature_path, index=False)
            configuration_path.write_text(json.dumps(experiment.configuration, sort_keys=True, indent=2), encoding="utf-8")
            metrics_path.write_text(json.dumps(result.metrics, sort_keys=True, indent=2, default=str, allow_nan=False), encoding="utf-8")
            risk_path.write_text(json.dumps(risk_result, sort_keys=True, indent=2, default=str, allow_nan=False), encoding="utf-8")

            review = ExperimentRiskReview(
                run_id=run.id, decision=risk_result["decision"], policy_version=risk_result["policy_version"],
                limits=risk_result["limits"], observed_metrics=risk_result["observed_metrics"],
                breaches=risk_result["breaches"], warnings=risk_result["warnings"],
                deterministic=True, override_allowed=False,
            )
            db.add(review)
            artifacts = {
                "equity_curve_path": str(equity_path),
                "equity_curve_sha256": _sha256_file(equity_path),
                "metrics_path": str(metrics_path),
                "risk_review_path": str(risk_path),
                "feature_frame_path": str(feature_path),
                "feature_set_version_id": feature_set.id,
                "feature_definition_sha256": feature_set.definition_sha256,
                "configuration_path": str(configuration_path),
                "dataset_snapshot_id": snapshot.id,
                "dataset_sha256": snapshot.sha256,
                "benchmark_snapshot_id": benchmark_snapshot.id if benchmark_snapshot else None,
                "benchmark_sha256": benchmark_snapshot.sha256 if benchmark_snapshot else None,
                "experiment_configuration_sha256": experiment.configuration_sha256,
            }
            tracker = create_experiment_tracker(settings)
            tracker_run_id = tracker.log_run(
                run_id=run.id, experiment_id=experiment.id,
                parameters={"model_family": experiment.configuration.get("model_family"),
                            "baseline": experiment.configuration.get("baseline"),
                            "evaluation_mode": experiment.configuration.get("evaluation_mode", "holdout"),
                            "random_seed": run.random_seed,
                            "benchmark_symbol": experiment.configuration.get("benchmark_symbol")},
                metrics=result.metrics,
                artifacts={"equity_curve": str(equity_path), "features": str(feature_path),
                           "configuration": str(configuration_path), "metrics": str(metrics_path),
                           "risk_review": str(risk_path)},
                tags={"instrument_symbol": experiment.instrument_symbol,
                      "dataset_sha256": snapshot.sha256,
                      "configuration_sha256": experiment.configuration_sha256,
                      "risk_decision": risk_result["decision"]},
            )
            artifacts["tracker_run_id"] = tracker_run_id
            if settings.experiment_tracking_backend == "local":
                artifacts["tracker_manifest_path"] = str(Path(settings.data_storage_path).resolve() / "experiments" / "tracking" / f"{run.id}.json")
            run.metrics = result.metrics
            run.artifacts = artifacts
            run.status = "SUCCEEDED"
            run.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "succeeded", "run_id": run_id, "risk_decision": risk_result["decision"]}
        except Exception as exc:
            mark_failed_after_rollback(db, ExperimentRun, run_id, type(exc).__name__)
            raise


@celery_app.task(name="finsight.documents.ingest", autoretry_for=(), acks_late=True)
def ingest_research_document_task(job_id: str) -> dict:
    """Process a staged document upload; database state is authoritative for idempotency."""
    with SessionLocal() as db:
        job = db.get(JobRecord, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        if job.status == "SUCCEEDED":
            return {"status": "already_succeeded", "job_id": job_id, **(job.result or {})}
        if job.task_name != "documents.ingest":
            return {"status": "wrong_task_type", "job_id": job_id}
        if job.status not in {"QUEUED", "QUEUE_FAILED", "RUNNING"}:
            return {"status": job.status.lower(), "job_id": job_id}
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.error_message = None
        db.commit()
        try:
            return process_document_ingestion_job(db, job)
        except Exception as exc:
            mark_failed_after_rollback(db, JobRecord, job_id, type(exc).__name__)
            raise


@celery_app.task(name="finsight.ml.evaluate", autoretry_for=(), acks_late=True)
def run_model_evaluation_job(job_id: str) -> dict:
    """Run a queued evaluation through the same validated API service path."""
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api.v1.ml import create_model_evaluation
    from app.schemas.ml import ModelEvaluationCreate
    from finsight.identity.models import User
    from finsight.documents.models import ModelEvaluation

    with SessionLocal() as db:
        job = db.get(JobRecord, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        if job.status == "SUCCEEDED":
            return {"status": "already_succeeded", "job_id": job_id, **(job.result or {})}
        if job.task_name != "ml.evaluate" or job.status not in {"QUEUED", "QUEUE_FAILED", "RUNNING"}:
            return {"status": job.status.lower(), "job_id": job_id}
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.error_message = None
        db.commit()
        user = db.get(User, job.created_by)
        if user is None:
            job.status = "FAILED"
            job.error_message = "Job owner is unavailable"
            job.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "failed", "job_id": job_id}
        try:
            # The evaluation API commits its ModelEvaluation. Recover that record if a
            # worker died after the model commit but before the JobRecord success commit.
            recent = db.scalars(select(ModelEvaluation).where(ModelEvaluation.created_by == user.id)
                .order_by(ModelEvaluation.created_at.desc()).limit(500)).all()
            existing = next((item for item in recent if (item.configuration or {}).get("queued_job_id") == job_id), None)
            if existing is not None:
                job.status = "SUCCEEDED"
                job.result = {"model_evaluation_id": existing.id, "model_family": existing.model_family,
                    "dataset_snapshot_id": existing.dataset_snapshot_id, "configuration_sha256": existing.configuration_sha256,
                    "recovered_after_worker_restart": True}
                job.completed_at = datetime.now(UTC)
                db.commit()
                return {"status": "succeeded", "job_id": job_id, **job.result}
            payload = ModelEvaluationCreate.model_validate(job.payload or {})
            request = SimpleNamespace(state=SimpleNamespace(request_id=None, job_id=job_id))
            result = create_model_evaluation(payload, request, db, user)
            job.status = "SUCCEEDED"
            job.result = {"model_evaluation_id": result.id, "model_family": result.model_family,
                "dataset_snapshot_id": result.dataset_snapshot_id, "configuration_sha256": result.configuration_sha256}
            job.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "succeeded", "job_id": job_id, **job.result}
        except HTTPException as exc:
            mark_failed_after_rollback(
                db, JobRecord, job_id, f"Evaluation rejected by validation (HTTP {exc.status_code})"
            )
            raise
        except Exception as exc:
            mark_failed_after_rollback(db, JobRecord, job_id, type(exc).__name__)
            raise


@celery_app.task(name="finsight.research.ask", autoretry_for=(), acks_late=True)
def run_research_question_job(job_id: str) -> dict:
    """Execute one queued evidence-grounded research workflow idempotently."""
    from app.services.research_jobs import process_research_question_job

    with SessionLocal() as db:
        job = db.get(JobRecord, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        if job.status == "SUCCEEDED":
            return {"status": "already_succeeded", "job_id": job_id, **(job.result or {})}
        if job.status not in {"QUEUED", "QUEUE_FAILED", "RUNNING"}:
            return {"status": job.status.lower(), "job_id": job_id}
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.error_message = None
        db.commit()
        try:
            return process_research_question_job(db, job)
        except Exception as exc:
            mark_failed_after_rollback(db, JobRecord, job_id, type(exc).__name__)
            raise


@celery_app.task(name="finsight.rl.evaluate", autoretry_for=(), acks_late=True)
def run_rl_evaluation_task(job_id: str) -> dict:
    """Execute one queued PPO/SAC training/evaluation job with DB-backed recovery."""
    from finsight.identity.models import User
    from finsight.governance.models import RLPolicyEvaluation
    from app.services.rl import run_rl_evaluation

    with SessionLocal() as db:
        job = db.get(JobRecord, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        if job.status == "SUCCEEDED":
            return {"status": "already_succeeded", "job_id": job_id, **(job.result or {})}
        if job.task_name != "rl.evaluate" or job.status not in {"QUEUED", "QUEUE_FAILED", "RUNNING"}:
            return {"status": job.status.lower(), "job_id": job_id}
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.error_message = None
        db.commit()
        user = db.get(User, job.created_by)
        if user is None:
            job.status = "FAILED"
            job.error_message = "Job owner is unavailable"
            job.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "failed", "job_id": job_id}
        try:
            existing = db.scalars(select(RLPolicyEvaluation).where(RLPolicyEvaluation.created_by == user.id)
                .order_by(RLPolicyEvaluation.created_at.desc()).limit(500)).all()
            recovered = next((item for item in existing if (item.configuration or {}).get("queued_job_id") == job_id), None)
            if recovered is None:
                payload = dict(job.payload or {}) | {"_queued_job_id": job_id}
                recovered = run_rl_evaluation(db, user_id=user.id, payload=payload)
                db.flush()
            job.status = "SUCCEEDED"
            job.result = {"rl_evaluation_id": recovered.id, "algorithm": recovered.algorithm,
                "dataset_snapshot_id": recovered.dataset_snapshot_id,
                "configuration_sha256": recovered.configuration_sha256}
            job.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "succeeded", "job_id": job_id, **job.result}
        except Exception as exc:
            mark_failed_after_rollback(db, JobRecord, job_id, type(exc).__name__)
            raise
