"""Acceptance tests for Phase 2 walk-forward, benchmark, risk and tracking capabilities."""
import json

import numpy as np
import pandas as pd
import pytest

from finsight.backtesting.portfolio import run_portfolio_backtest
from finsight.backtesting.event_engine import run_event_driven_backtest
from finsight.experiments.runner import run_baseline_experiment
from finsight.experiments.tracking import LocalJSONExperimentTracker
from finsight.models.baselines.strategies import rsi_mean_reversion_signal
from finsight.risk.policy import RiskPolicy, evaluate_backtest_risk


def make_bars(rows: int = 400, *, drift: float = 0.08, phase: float = 0.0) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=rows)
    index = np.arange(rows, dtype=float)
    close = 100 + drift * index + 2.5 * np.sin(index / 8 + phase) + 0.7 * np.sin(index / 2.9)
    return pd.DataFrame({
        "date": dates,
        "open": close * 0.999,
        "high": close * 1.012,
        "low": close * 0.988,
        "close": close,
        "volume": 1_000_000 + index * 10,
    })


def config(**overrides):
    value = {
        "model_family": "baseline", "baseline": "moving_average_crossover", "target": "next_day_return",
        "prediction_horizon_days": 1, "purge_gap_days": 1,
        "train_start": "2023-01-02", "train_end": "2023-06-30",
        "validation_start": "2023-07-04", "validation_end": "2023-08-31",
        "test_start": "2023-09-05", "test_end": "2024-07-15",
        "evaluation_mode": "holdout", "walk_forward_test_days": 63, "walk_forward_step_days": 63,
        "short_window": 5, "long_window": 20, "rsi_window": 14,
        "rsi_oversold": 30, "rsi_overbought": 70,
        "random_seed": 42, "commission_bps": 5, "slippage_bps": 5, "benchmark_symbol": "SPY",
    }
    value.update(overrides)
    return value


def test_walk_forward_emits_non_overlapping_out_of_sample_folds() -> None:
    bars = make_bars()
    result = run_baseline_experiment(bars, config(evaluation_mode="walk_forward"))
    dates = pd.to_datetime(result.equity_curve["date"], utc=True)
    assert result.metrics["evaluation_mode"] == "walk_forward"
    assert result.metrics["fold_count"] >= 4
    assert dates.min() >= pd.Timestamp("2023-09-05", tz="UTC")
    assert dates.max() <= pd.Timestamp("2024-07-15", tz="UTC")
    assert dates.is_monotonic_increasing and not dates.duplicated().any()
    assert result.metrics["observations"] == len(dates)
    assert len(result.metrics["folds"]) == result.metrics["fold_count"]
    assert set(result.metrics["split_metrics"]) == {"train", "validation", "test"}
    assert result.metrics["split_metrics"]["validation"]["observations"] > 0


def test_benchmark_comparison_includes_alpha_beta_tracking_error_and_ir() -> None:
    asset = make_bars(drift=0.10, phase=0.2)
    benchmark = make_bars(drift=0.06, phase=0.9)
    result = run_baseline_experiment(asset, config(baseline="buy_and_hold"), benchmark_bars=benchmark)
    assert result.metrics["benchmark_available"] is True
    assert result.metrics["benchmark_symbol"] == "SPY"
    for field in ("benchmark_total_return", "alpha_annualized", "beta", "tracking_error", "information_ratio"):
        assert np.isfinite(result.metrics[field])
    assert result.metrics["benchmark_observations"] > 30


def test_missing_benchmark_is_explicit_not_silently_inferred() -> None:
    result = run_baseline_experiment(make_bars(), config())
    assert result.metrics["benchmark_available"] is False
    assert result.metrics["benchmark_symbol"] == "SPY"


def test_rsi_strategy_returns_valid_long_only_weights() -> None:
    signal = rsi_mean_reversion_signal(make_bars(), window=14, oversold=30, overbought=70)
    assert signal.notna().all()
    assert signal.isin([0.0, 1.0]).all()


def test_portfolio_accounting_delays_fill_and_return_accrual_and_keeps_cash() -> None:
    dates = pd.bdate_range("2025-01-01", periods=4)
    prices = pd.DataFrame({"AAA": [100, 110, 121, 133.1], "BBB": [100, 100, 100, 100]}, index=dates)
    weights = pd.DataFrame({"AAA": [0.5, 0.5, 0.5, 0.5], "BBB": [0.2, 0.2, 0.2, 0.2]}, index=dates)
    result = run_portfolio_backtest(prices, weights, commission_bps=0, slippage_bps=0)
    ledger = result.ledger
    assert ledger.loc[0, "portfolio_return"] == pytest.approx(0.0)
    assert ledger.loc[1, "portfolio_return"] == pytest.approx(0.0)
    assert ledger.loc[2, "portfolio_return"] > 0
    assert ledger.loc[1, "gross_exposure"] == pytest.approx(0.7)
    assert ledger.loc[1, "cash_weight"] == pytest.approx(0.3)
    assert result.metrics["observations"] == 4


def test_portfolio_rejects_overexposure_and_short_weights() -> None:
    dates = pd.bdate_range("2025-01-01", periods=3)
    prices = pd.DataFrame({"AAA": [10, 11, 12]}, index=dates)
    too_much = pd.DataFrame({"AAA": [1.1, 1.1, 1.1]}, index=dates)
    with pytest.raises(ValueError, match="gross exposure"):
        run_portfolio_backtest(prices, too_much)
    short = pd.DataFrame({"AAA": [-0.1, 0.0, 0.0]}, index=dates)
    with pytest.raises(ValueError, match="Short weights"):
        run_portfolio_backtest(prices, short)


def test_deterministic_risk_policy_passes_reviews_and_rejects_hard_breaches() -> None:
    passing = evaluate_backtest_risk({
        "max_drawdown": -0.10, "annualized_volatility": 0.20, "sharpe_ratio": 1.1,
        "turnover": 8.0, "observations": 100, "average_gross_exposure": 0.8,
    })
    assert passing["decision"] == "PASS"
    assert passing["deterministic"] is True and passing["override_allowed"] is False

    review = evaluate_backtest_risk({
        "max_drawdown": -0.10, "annualized_volatility": 0.20, "sharpe_ratio": -0.2,
        "turnover": 8.0, "observations": 10, "average_gross_exposure": 0.8,
    })
    assert review["decision"] == "REVIEW"
    assert len(review["warnings"]) == 2

    reject = evaluate_backtest_risk({
        "max_drawdown": -0.35, "annualized_volatility": 0.20, "sharpe_ratio": 1.0,
        "turnover": 8.0, "observations": 100, "average_gross_exposure": 0.8,
    }, policy=RiskPolicy(max_drawdown_abs=0.20))
    assert reject["decision"] == "REJECT"
    assert reject["breaches"][0]["rule"] == "max_drawdown_abs"


def test_local_tracker_writes_atomic_reproducibility_manifest(tmp_path) -> None:
    tracker = LocalJSONExperimentTracker(tmp_path)
    path = tracker.log_run(
        run_id="run-123", experiment_id="experiment-456",
        parameters={"baseline": "buy_and_hold", "seed": 42},
        metrics={"sharpe_ratio": 0.5, "total_return": 0.1},
        artifacts={"metrics": "/tmp/metrics.json"},
        tags={"dataset_sha256": "a" * 64, "configuration_sha256": "b" * 64},
    )
    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload["run_id"] == "run-123"
    assert payload["tags"]["dataset_sha256"] == "a" * 64
    assert not list(tmp_path.glob("*.tmp"))


def test_event_driven_engine_generates_next_close_fills_and_cash_ledger() -> None:
    dates = pd.bdate_range("2025-01-01", periods=4)
    prices = pd.DataFrame({"AAA": [100.0, 110.0, 121.0, 133.1]}, index=dates)
    weights = pd.DataFrame({"AAA": [0.5, 0.5, 0.5, 0.5]}, index=dates)
    result = run_event_driven_backtest(prices, weights, initial_cash=100_000, commission_bps=5, slippage_bps=5)
    assert result.ledger.loc[0, "equity"] == pytest.approx(100_000)
    assert result.ledger.loc[0, "portfolio_return"] == pytest.approx(0)
    assert len(result.fills) >= 1
    first_fill = result.fills.iloc[0]
    assert first_fill["side"] == "BUY"
    assert first_fill["timestamp"].startswith(dates[1].date().isoformat())
    assert first_fill["fill_price"] > first_fill["reference_close"]
    assert result.ledger.loc[1, "cash"] >= 0
    assert result.ledger.loc[2, "portfolio_return"] > 0
    assert result.metrics["fill_count"] == len(result.fills)


def test_feature_builder_enforces_versioned_declaration_and_target_separation() -> None:
    from finsight.features.engineering import build_declared_feature_frame

    bars = make_bars(80)
    frame = build_declared_feature_frame(
        bars, {"features": ["return_1d", "momentum_5d"], "target": "next_day_return"}
    )
    assert list(frame.columns) == ["date", "return_1d", "momentum_5d", "target_next_day_return"]
    assert frame["target_next_day_return"].notna().all()
    with pytest.raises(ValueError, match="unsupported"):
        build_declared_feature_frame(bars, {"features": ["target_next_day_return"]})


def test_event_engine_sells_before_buying_during_asset_rotation() -> None:
    dates = pd.bdate_range("2025-02-03", periods=4)
    prices = pd.DataFrame({"AAA": [100.0, 100.0, 100.0, 100.0], "BBB": [100.0, 100.0, 100.0, 100.0]}, index=dates)
    weights = pd.DataFrame({"AAA": [1.0, 0.0, 0.0, 0.0], "BBB": [0.0, 1.0, 1.0, 1.0]}, index=dates)
    result = run_event_driven_backtest(
        prices, weights, initial_cash=10_000, commission_bps=100, slippage_bps=100,
    )
    first_rotation_fills = result.fills.loc[result.fills["timestamp"].str.startswith(dates[2].date().isoformat())]
    assert len(first_rotation_fills) == 2
    assert first_rotation_fills.iloc[0]["side"] == "SELL"
    assert first_rotation_fills.iloc[1]["side"] == "BUY"
    assert (result.ledger["cash"] >= 0).all()


def test_mlflow_backend_requires_tracking_uri() -> None:
    from pydantic import ValidationError
    from finsight.core.config import Settings

    with pytest.raises(ValidationError, match="MLFLOW_TRACKING_URI"):
        Settings(experiment_tracking_backend="mlflow", mlflow_tracking_uri=None)


def test_baseline_backtest_reports_observed_average_exposure() -> None:
    from finsight.backtesting.engine import run_long_only_backtest

    bars = make_bars(50)
    signal = pd.Series(0.5, index=bars.index)
    result = run_long_only_backtest(bars, signal)
    assert 0.0 <= result.metrics["average_gross_exposure"] <= 1.0


def test_risk_policy_rejects_missing_required_exposure_metric() -> None:
    result = evaluate_backtest_risk({
        "max_drawdown": -0.05, "annualized_volatility": 0.15, "sharpe_ratio": 1.0,
        "turnover": 2.0, "observations": 100,
    })
    assert result["decision"] == "REJECT"
    assert any(item["rule"] == "average_gross_exposure" for item in result["breaches"])
