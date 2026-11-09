"""Durable experiment run tracking with local JSON and optional MLflow backends."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Protocol


class ExperimentTracker(Protocol):
    def log_run(self, *, run_id: str, experiment_id: str, parameters: dict[str, Any],
                metrics: dict[str, Any], artifacts: dict[str, Any], tags: dict[str, str]) -> str: ...


class LocalJSONExperimentTracker:
    """Atomic local tracking manifest; useful offline and deterministic in tests."""
    def __init__(self, tracking_dir: str | Path):
        self.tracking_dir = Path(tracking_dir).resolve()

    def log_run(self, *, run_id: str, experiment_id: str, parameters: dict[str, Any],
                metrics: dict[str, Any], artifacts: dict[str, Any], tags: dict[str, str]) -> str:
        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        target = self.tracking_dir / f"{run_id}.json"
        payload = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "parameters": parameters,
            "metrics": metrics,
            "artifacts": artifacts,
            "tags": tags,
        }
        fd, temporary = tempfile.mkstemp(prefix=f".{run_id}.", suffix=".tmp", dir=self.tracking_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True, ensure_ascii=False, indent=2, default=str, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return str(target)


class MLflowExperimentTracker:
    """Optional MLflow adapter. Install the `mlflow` project extra to enable it."""
    def __init__(self, tracking_uri: str):
        try:
            from mlflow.tracking import MlflowClient
        except ImportError as exc:  # pragma: no cover - depends on optional deployment extra
            raise RuntimeError("MLflow backend requested; install finsight-researchops[mlflow]") from exc
        self.client = MlflowClient(tracking_uri=tracking_uri)
        experiment = self.client.get_experiment_by_name("FinSight ResearchOps")
        self.experiment_id = experiment.experiment_id if experiment else self.client.create_experiment("FinSight ResearchOps")

    def log_run(self, *, run_id: str, experiment_id: str, parameters: dict[str, Any],
                metrics: dict[str, Any], artifacts: dict[str, Any], tags: dict[str, str]) -> str:
        mlrun = self.client.create_run(self.experiment_id, tags={"finsight.run_id": run_id, **tags})
        for key, value in parameters.items():
            self.client.log_param(mlrun.info.run_id, str(key)[:250], str(value)[:500])
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                self.client.log_metric(mlrun.info.run_id, str(key)[:250], float(value))
        for key, value in artifacts.items():
            path = Path(str(value))
            if path.is_file():
                self.client.log_artifact(mlrun.info.run_id, str(path))
        self.client.set_terminated(mlrun.info.run_id, status="FINISHED")
        return mlrun.info.run_id


def create_experiment_tracker(settings: Any) -> ExperimentTracker:
    backend = getattr(settings, "experiment_tracking_backend", "local")
    if backend == "mlflow":
        uri = getattr(settings, "mlflow_tracking_uri", None)
        if not uri:
            raise RuntimeError("MLFLOW_TRACKING_URI must be set when EXPERIMENT_TRACKING_BACKEND=mlflow")
        return MLflowExperimentTracker(uri)
    return LocalJSONExperimentTracker(Path(settings.data_storage_path) / "experiments" / "tracking")
