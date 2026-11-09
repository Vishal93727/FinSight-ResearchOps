"""Deterministic, dependency-light methods for forecast and strategy monitoring."""
from __future__ import annotations
import math
import statistics
from collections.abc import Sequence


def _finite(values: Sequence[float], name: str, minimum: int = 1) -> list[float]:
    out = [float(v) for v in values]
    if len(out) < minimum:
        raise ValueError(f"{name} requires at least {minimum} observations")
    if any(not math.isfinite(v) for v in out):
        raise ValueError(f"{name} must contain only finite values")
    return out


def summarize_outcomes(predicted: Sequence[float], realized: Sequence[float]) -> dict:
    p = _finite(predicted, "predicted")
    r = _finite(realized, "realized")
    if len(p) != len(r):
        raise ValueError("predicted and realized arrays must have equal lengths")
    errors = [a - b for a, b in zip(p, r, strict=True)]
    directional = [(a, b) for a, b in zip(p, r, strict=True) if a != 0 and b != 0]
    return {
        "sample_count": len(p),
        "mae": sum(abs(e) for e in errors) / len(errors),
        "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)),
        "mean_bias": sum(errors) / len(errors),
        "directional_accuracy": (sum((a > 0) == (b > 0) for a, b in directional) / len(directional)) if directional else None,
        "directional_sample_count": len(directional),
    }


def summarize_strategy_returns(returns: Sequence[float], benchmark_returns: Sequence[float] | None = None) -> dict:
    values = _finite(returns, "returns", minimum=2)
    if any(v < -1 for v in values):
        raise ValueError("A period return cannot be less than -100%")
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    mean_return = statistics.fmean(values)
    vol = statistics.stdev(values) if len(values) > 1 else 0.0
    bench_total = None
    excess = None
    if benchmark_returns is not None:
        bench = _finite(benchmark_returns, "benchmark_returns", minimum=2)
        if len(bench) != len(values):
            raise ValueError("benchmark_returns must have the same length as returns")
        bench_total = math.prod(1 + v for v in bench) - 1
        excess = (equity - 1) - bench_total
    values_out = {
        "sample_count": len(values),
        "cumulative_return": equity - 1,
        "annualized_volatility": vol * math.sqrt(252),
        "annualized_sharpe": (mean_return / vol * math.sqrt(252)) if vol > 0 else None,
        "max_drawdown": max_drawdown,
        "win_rate": sum(v > 0 for v in values) / len(values),
        "mean_period_return": mean_return,
        "benchmark_cumulative_return": bench_total,
        "excess_return": excess,
        "return_convention": "period decimal returns; cumulative product compounded; annualization assumes 252 periods/year",
    }
    if any(isinstance(v, float) and not math.isfinite(v) for v in values_out.values()):
        raise ValueError("Strategy metrics produced a non-finite value")
    return values_out


def population_stability_index(baseline: Sequence[float], current: Sequence[float]) -> dict:
    base = _finite(baseline, "baseline", minimum=10)
    curr = _finite(current, "current", minimum=10)
    ordered = sorted(base)
    edges = [ordered[round((len(ordered) - 1) * q / 10)] for q in range(1, 10)]
    # Quantile edges can collapse for constant or low-cardinality baselines. Add finite
    # spread boundaries so a shift away from a constant baseline remains detectable.
    mean = statistics.fmean(base)
    std = statistics.pstdev(base)
    if std == 0:
        scale = max(abs(mean) * 0.01, 1e-6)
        edges = [mean - 3*scale, mean - scale, mean - .25*scale, mean + .25*scale, mean + scale, mean + 3*scale]
    else:
        edges = sorted(set(edges))
        edges = [mean - 4*std, *edges, mean + 4*std]
        edges = sorted(set(edges))
    def bin_counts(arr: list[float]) -> list[float]:
        counts = [0] * (len(edges) + 1)
        for value in arr:
            slot = 0
            while slot < len(edges) and value > edges[slot]:
                slot += 1
            counts[slot] += 1
        return [max(count / len(arr), 1e-6) for count in counts]
    bp, cp = bin_counts(base), bin_counts(curr)
    score = sum((c - b) * math.log(c / b) for b, c in zip(bp, cp, strict=True))
    result = {
        "psi": score,
        "baseline_count": len(base), "current_count": len(curr),
        "baseline_mean": mean, "current_mean": statistics.fmean(curr),
        "baseline_std": std, "current_std": statistics.pstdev(curr),
        "bins": len(bp), "method": "quantile PSI with explicit spread bins for constant baseline",
    }
    if not math.isfinite(score):
        raise ValueError("Drift calculation returned a non-finite score")
    return result
