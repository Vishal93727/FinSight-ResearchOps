# Experiment Tracking Operations

## Default: local tracking

No additional service is required for development. The worker writes one atomic JSON manifest for each run under:

```text
DATA_STORAGE_PATH/experiments/tracking/<run-id>.json
```

The manifest records experiment/run IDs, scalar parameters, metrics, artifact paths and tags for the instrument, dataset hash, configuration hash and deterministic risk decision. It complements the application database; the database remains the source of truth for run state and risk reviews.

## Optional MLflow backend

Install the optional package extra:

```bash
pip install -e '.[mlflow]'
```

Configure the worker environment:

```dotenv
EXPERIMENT_TRACKING_BACKEND=mlflow
MLFLOW_TRACKING_URI=http://mlflow:5000
```

Use a secured private tracking service in shared environments. Do not expose an unauthenticated MLflow server to the public internet. The worker logs scalar parameters/metrics and local artifacts including configuration, declared features, equity curve, metrics and risk review. MLflow is optional; local tracking remains available when the external tracking service is not deployed.

## Verification checklist

- Confirm the Celery worker can read the same data-storage volume as the API.
- Verify the experiment and benchmark Parquet files exist and match their database SHA-256 values.
- Verify feature-set/configuration hashes before running.
- Confirm the run reaches `SUCCEEDED` and the deterministic risk row is present.
- Inspect the tracker manifest or MLflow run and verify all artifact paths.
- Confirm retries with the same idempotency key do not enqueue a duplicate run.
