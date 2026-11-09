# FinSight domain package

`src/finsight/` is the canonical Python package. Cross-cutting settings/logging/security are under `core/`; identity under `identity/`; database infrastructure under `infrastructure/database/`; provider and ingestion adapters under `market_data/`; and bounded domains under `research/`, `features/`, `experiments/`, `backtesting/`, `risk/`, `governance/`, `execution/` and `feedback/`.

The FastAPI route adapters and a small set of historical compatibility modules remain under `backend/app/` while endpoint migration is performed incrementally. Those compatibility modules only re-export the canonical package; do not add new domain logic to them.
