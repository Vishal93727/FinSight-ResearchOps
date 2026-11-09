# Database migrations

Alembic is configured by the root `alembic.ini` and all version scripts live under `migrations/versions/`.

- `0001_initial_researchops`: original Phase 1 identity, catalogue, snapshot, job and audit schema.
- `0002_research_experiment_foundation`: Phase 2 hypothesis, feature-set version and experiment/run tables.

The migration environment imports the canonical SQLAlchemy metadata from `src/finsight/infrastructure/database/`.
