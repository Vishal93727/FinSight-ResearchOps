"""Leakage and determinism tests for the first Phase 2 feature pipeline."""
import pandas as pd
import pytest

from finsight.features.engineering import build_price_features


def make_bars(rows: int = 35) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=rows, freq="B"),
            "open": [100 + i for i in range(rows)],
            "high": [102 + i for i in range(rows)],
            "low": [99 + i for i in range(rows)],
            "close": [101 + i for i in range(rows)],
            "volume": [1000 + 10 * i for i in range(rows)],
        }
    )


def test_feature_pipeline_excludes_future_target_from_feature_columns() -> None:
    result = build_price_features(make_bars())
    assert "target_next_day_return" in result.columns
    assert "close" not in result.columns
    assert result["date"].is_monotonic_increasing
    assert result["target_next_day_return"].notna().all()
    assert result["date"].max() < pd.Timestamp("2025-02-18", tz="UTC")


def test_future_bar_change_does_not_change_prior_day_features() -> None:
    original = make_bars()
    changed = original.copy()
    changed.loc[30, ["open", "high", "low", "close", "volume"]] *= 10
    before = build_price_features(original)
    after = build_price_features(changed)
    date_to_check = pd.Timestamp(original.loc[28, "date"], tz="UTC")
    before_row = before.loc[before["date"] == date_to_check].iloc[0]
    after_row = after.loc[after["date"] == date_to_check].iloc[0]
    feature_columns = ["return_1d", "momentum_5d", "sma_ratio_5d", "sma_ratio_20d", "volatility_20d", "volume_change_1d"]
    pd.testing.assert_series_equal(before_row[feature_columns], after_row[feature_columns])


def test_duplicate_market_dates_are_rejected() -> None:
    bars = make_bars()
    bars.loc[1, "date"] = bars.loc[0, "date"]
    with pytest.raises(ValueError, match="Duplicate dates"):
        build_price_features(bars)


def test_backtest_uses_next_bar_execution_and_deducts_costs() -> None:
    from finsight.backtesting.engine import run_long_only_backtest

    bars = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=3, freq="B"),
            "close": [100.0, 110.0, 121.0],
        }
    )
    signal = pd.Series([1.0, 1.0, 1.0])
    free = run_long_only_backtest(bars, signal, commission_bps=0, slippage_bps=0)
    charged = run_long_only_backtest(bars, signal, commission_bps=10, slippage_bps=10)

    # A signal at close day 0 fills at close day 1; close-to-close P&L starts day 2.
    assert free.equity_curve.loc[0, "strategy_return"] == 0.0
    assert free.equity_curve.loc[1, "strategy_return"] == 0.0
    assert free.equity_curve.loc[2, "strategy_return"] == pytest.approx(0.10)
    assert charged.metrics["total_return"] < free.metrics["total_return"]
    assert charged.metrics["estimated_cost_bps"] == pytest.approx(20.0)


def test_baseline_runner_reports_only_configured_holdout_window() -> None:
    from finsight.experiments.runner import run_baseline_experiment

    bars = pd.DataFrame(
        {
            "date": pd.bdate_range("2023-01-02", periods=500),
            "close": [100.0 + (index * 0.15) for index in range(500)],
        }
    )
    configuration = {
        "model_family": "baseline", "baseline": "buy_and_hold", "target": "next_day_return",
        "prediction_horizon_days": 1, "purge_gap_days": 1,
        "train_start": "2023-01-02", "train_end": "2023-12-29",
        "validation_start": "2024-01-02", "validation_end": "2024-06-28",
        "test_start": "2024-07-02", "test_end": "2024-12-31",
        "random_seed": 42, "commission_bps": 5, "slippage_bps": 5, "benchmark_symbol": "SPY",
    }

    result = run_baseline_experiment(bars, configuration)
    dates = pd.to_datetime(result.equity_curve["date"], utc=True)
    assert dates.min() >= pd.Timestamp("2024-07-02", tz="UTC")
    assert dates.max() <= pd.Timestamp("2024-12-31", tz="UTC")
    assert result.metrics["observations"] == len(result.equity_curve)
    assert result.metrics["observations"] > 0
    assert result.metrics["estimated_cost_bps"] >= 0


def test_non_finite_market_values_are_rejected() -> None:
    from math import inf

    from finsight.market_data.contracts.ingestion import MarketBar
    from finsight.backtesting.engine import run_long_only_backtest

    with pytest.raises(ValueError, match="finite"):
        MarketBar(date="2025-01-01", open=inf, high=inf, low=inf, close=inf, volume=1)

    bars = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=2, freq="B"), "close": [100.0, inf]})
    with pytest.raises(ValueError, match="finite"):
        run_long_only_backtest(bars, pd.Series([1.0, 1.0]))
