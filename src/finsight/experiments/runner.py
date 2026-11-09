"""Deterministic baseline experiment runner with holdout and rolling walk-forward modes."""
from __future__ import annotations

import math
import pandas as pd

from finsight.backtesting.engine import BacktestResult, run_long_only_backtest
from finsight.experiments.config import ExperimentConfiguration
from finsight.models.baselines.strategies import BASELINE_STRATEGIES


def _performance_metrics(returns: pd.Series, turnover: pd.Series, costs: pd.Series, periods_per_year: int = 252) -> dict:
    returns = pd.to_numeric(returns, errors="raise").astype(float)
    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    mean_return = float(returns.mean()) if len(returns) else 0.0
    sharpe = mean_return / volatility * math.sqrt(periods_per_year) if volatility > 0 else 0.0
    equity_end = float(equity.iloc[-1]) if len(equity) else 1.0
    annualized_return = equity_end ** (periods_per_year / max(len(returns), 1)) - 1.0 if equity_end > 0 else -1.0
    return {
        "total_return": equity_end - 1.0,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility * math.sqrt(periods_per_year),
        "sharpe_ratio": sharpe,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "turnover": float(turnover.sum()),
        "estimated_cost_bps": float(costs.sum() * 10_000.0),
        "observations": int(len(returns)),
    }


def _add_benchmark_comparison(
    result: BacktestResult, benchmark_bars: pd.DataFrame | None, benchmark_symbol: str,
) -> BacktestResult:
    if benchmark_bars is None:
        result.metrics["benchmark_available"] = False
        result.metrics["benchmark_symbol"] = benchmark_symbol
        return result
    benchmark_signal = pd.Series(1.0, index=benchmark_bars.index, name="signal")
    benchmark = run_long_only_backtest(
        benchmark_bars, benchmark_signal, commission_bps=0.0, slippage_bps=0.0,
        evaluation_start=pd.to_datetime(result.equity_curve["date"], utc=True).min(),
        evaluation_end=pd.to_datetime(result.equity_curve["date"], utc=True).max(),
    ).equity_curve.loc[:, ["date", "strategy_return"]].rename(columns={"strategy_return": "benchmark_return"})
    strategy = result.equity_curve.copy()
    strategy["date"] = pd.to_datetime(strategy["date"], utc=True)
    benchmark["date"] = pd.to_datetime(benchmark["date"], utc=True)
    aligned = strategy.merge(benchmark, on="date", how="inner", validate="one_to_one")
    if len(aligned) < 2:
        result.metrics["benchmark_available"] = False
        result.metrics["benchmark_symbol"] = benchmark_symbol
        result.metrics["benchmark_note"] = "Insufficient overlapping daily observations"
        return result
    active = aligned["strategy_return"] - aligned["benchmark_return"]
    benchmark_variance = float(aligned["benchmark_return"].var(ddof=1))
    beta = float(aligned["strategy_return"].cov(aligned["benchmark_return"]) / benchmark_variance) if benchmark_variance > 0 else 0.0
    active_volatility = float(active.std(ddof=1))
    result.metrics.update({
        "benchmark_available": True,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_total_return": float((1.0 + aligned["benchmark_return"]).prod() - 1.0),
        "benchmark_annualized_volatility": float(aligned["benchmark_return"].std(ddof=1) * math.sqrt(252)),
        "alpha_annualized": float((aligned["strategy_return"].mean() - beta * aligned["benchmark_return"].mean()) * 252),
        "beta": beta,
        "tracking_error": active_volatility * math.sqrt(252),
        "information_ratio": float(active.mean() / active_volatility * math.sqrt(252)) if active_volatility > 0 else 0.0,
        "benchmark_observations": int(len(aligned)),
    })
    return result


def _run_walk_forward(bars: pd.DataFrame, signal: pd.Series, config: ExperimentConfiguration) -> BacktestResult:
    start = pd.Timestamp(config.test_start, tz="UTC")
    end = pd.Timestamp(config.test_end, tz="UTC")
    fold_start = start
    fold_curves: list[pd.DataFrame] = []
    fold_metrics: list[dict] = []
    while fold_start <= end:
        fold_end = min(fold_start + pd.Timedelta(days=config.walk_forward_test_days - 1), end)
        fold = run_long_only_backtest(
            bars, signal, commission_bps=config.commission_bps, slippage_bps=config.slippage_bps,
            evaluation_start=fold_start, evaluation_end=fold_end,
        )
        curve = fold.equity_curve.copy()
        curve["fold"] = len(fold_metrics) + 1
        fold_curves.append(curve)
        fold_metrics.append({"fold": len(fold_metrics) + 1, "start": fold_start.date().isoformat(),
                             "end": fold_end.date().isoformat(), **fold.metrics})
        fold_start = fold_start + pd.Timedelta(days=config.walk_forward_step_days)
    if not fold_curves:
        raise ValueError("Walk-forward schedule produced no test folds")
    combined = pd.concat(fold_curves, ignore_index=True).sort_values("date").reset_index(drop=True)
    if combined["date"].duplicated().any():
        raise ValueError("Walk-forward test folds overlap; adjust the step or test window")
    combined["equity"] = (1.0 + combined["strategy_return"]).cumprod()
    combined["drawdown"] = combined["equity"] / combined["equity"].cummax() - 1.0
    metrics = _performance_metrics(combined["strategy_return"], combined["turnover"], combined["trading_cost"])
    metrics["evaluation_mode"] = "walk_forward"
    metrics["fold_count"] = len(fold_metrics)
    metrics["folds"] = fold_metrics
    metrics["average_gross_exposure"] = float(combined["executed_position"].mean())
    return BacktestResult(equity_curve=combined, metrics=metrics)


def run_baseline_experiment(
    bars: pd.DataFrame,
    configuration: dict,
    *,
    benchmark_bars: pd.DataFrame | None = None,
) -> BacktestResult:
    """Run a registered baseline on the test holdout or non-overlapping rolling folds."""
    config = ExperimentConfiguration.model_validate(configuration)
    strategy = BASELINE_STRATEGIES[config.baseline]
    if config.baseline == "moving_average_crossover":
        signal = strategy(bars, config.short_window, config.long_window)
    elif config.baseline == "rsi_mean_reversion":
        signal = strategy(bars, window=config.rsi_window, oversold=config.rsi_oversold,
                          overbought=config.rsi_overbought)
    else:
        signal = strategy(bars)

    train_result = run_long_only_backtest(
        bars, signal, commission_bps=config.commission_bps, slippage_bps=config.slippage_bps,
        evaluation_start=config.train_start.isoformat(), evaluation_end=config.train_end.isoformat(),
    )
    validation_result = run_long_only_backtest(
        bars, signal, commission_bps=config.commission_bps, slippage_bps=config.slippage_bps,
        evaluation_start=config.validation_start.isoformat(), evaluation_end=config.validation_end.isoformat(),
    )
    if config.evaluation_mode == "walk_forward":
        result = _run_walk_forward(bars, signal, config)
    else:
        result = run_long_only_backtest(
            bars, signal, commission_bps=config.commission_bps, slippage_bps=config.slippage_bps,
            evaluation_start=config.test_start.isoformat(), evaluation_end=config.test_end.isoformat(),
        )
        result.metrics["evaluation_mode"] = "holdout"
        result.metrics["fold_count"] = 1
    result.metrics["split_metrics"] = {
        "train": train_result.metrics,
        "validation": validation_result.metrics,
        "test": result.metrics.copy(),
    }
    return _add_benchmark_comparison(result, benchmark_bars, config.benchmark_symbol)
