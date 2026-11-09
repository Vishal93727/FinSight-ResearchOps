# Phase 2 — Backtesting, Validation and Deterministic Risk

## Experiment specification

An experiment is immutable after creation and is tied to an approved hypothesis, a READY market-data snapshot, a content-hashed feature-set version and a canonical configuration fingerprint. A benchmark snapshot can be pinned separately. The worker verifies the dataset file hash, configuration hash, feature definition hash and feature-to-snapshot lineage before running.

Each configuration carries chronological train, validation and test windows. The minimum boundary purge is `prediction_horizon_days + purge_gap_days`. Train and validation metrics are diagnostic; final reported strategy metrics are calculated on the held-out test window. Walk-forward mode divides the test period into non-overlapping calendar windows, carries causal indicator history into each fold and aggregates only out-of-sample fold returns.

## Feature handling

`build_price_features` creates close-time inputs such as one-day return, five-day momentum, moving-average ratios, rolling volatility and volume change. `target_next_day_return` is shifted from the following session and is never accepted as an input feature. A feature-set version can select only the registered input features; target-only and unknown columns are rejected. Incomplete rolling windows and rows without a next-session target are removed.

## Signal and execution convention

A signal calculated from close(t) is filled at close(t+1). The strategy does not earn the close(t) to close(t+1) move from a position it could not yet hold. Commission and slippage are applied to turnover. Supported deterministic baselines are buy-and-hold, moving-average crossover and RSI mean-reversion. All are long-only and have no broker connectivity.

Two engines are available:

- Vectorized single-instrument and multi-asset accounting for repeatable daily return, turnover, cash and exposure calculations.
- Event-driven multi-asset simulation with explicit BUY/SELL fills, share balances, cash ledger, commission, slippage and next-close execution.

The event-driven simulator sells reductions before funding buys during a portfolio rotation. Long-only weights are capped at the configured gross exposure; shorting and leverage are not supported.

## Benchmark comparison

To produce benchmark-relative statistics, select a READY benchmark snapshot that matches `benchmark_symbol` and fully covers the test window. Its snapshot ID and file hash are retained in run artifacts. The runner aligns strategy and benchmark daily returns and calculates benchmark total return, annualized alpha, beta, tracking error and information ratio. When no benchmark snapshot is pinned or there are insufficient overlapping observations, the result explicitly reports `benchmark_available=false`; no synthetic benchmark data is substituted.

## Deterministic risk review

Every successful run receives a policy evaluation independent of AI or LLM output. The default `phase2-v1` policy uses:

| Rule | Default threshold | Result when breached |
|---|---:|---|
| Absolute maximum drawdown | 20% | REJECT |
| Annualized volatility | 50% | REJECT |
| Average gross exposure | 1.00x | REJECT |
| Total turnover | 25.0x equity | REJECT |
| Minimum observations | 30 | REVIEW |
| Minimum Sharpe ratio | 0.0 | REVIEW |

`PASS` means all evaluated rules pass. `REVIEW` means no hard breach was detected, but evidence or risk-adjusted performance warrants human review. `REJECT` means at least one hard breach exists. Decisions, limits, observed metrics, warnings and breaches are persisted in `experiment_risk_reviews`. The Phase 2 policy is deterministic and cannot be overridden by an LLM. These thresholds are conservative engineering defaults, not investment suitability rules.

## Run tracking and comparison

The default tracking backend writes an atomic JSON manifest per run beneath `DATA_STORAGE_PATH/experiments/tracking/`, containing run parameters, metrics, artifact paths and dataset/configuration fingerprints. An optional MLflow adapter is available through the `mlflow` project extra and `EXPERIMENT_TRACKING_BACKEND=mlflow` with `MLFLOW_TRACKING_URI` configured. The API exposes a run comparison view for successful or queued attempts of the same immutable experiment specification, including risk decision and benchmark-relative metrics when available.

## Interpretation limits

Phase 2 provides deterministic baselines and evaluation infrastructure. It does not claim predictive performance, profitability, investment advice or live execution. Transaction-cost assumptions, historical data quality, corporate-action treatment, survivorship bias, market impact, liquidity constraints and data availability can materially change historical results. These assumptions must be reviewed before using any future model or paper strategy.
