"""Versioned, deterministic risk policy for historical strategy evaluation."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True)
class RiskPolicy:
    version: str = "phase2-v1"
    max_drawdown_abs: float = 0.20
    max_annualized_volatility: float = 0.50
    max_average_gross_exposure: float = 1.00
    max_total_turnover: float = 25.0
    min_observations: int = 30
    min_sharpe_ratio: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_backtest_risk(
    metrics: dict[str, Any],
    *,
    policy: RiskPolicy | None = None,
) -> dict[str, Any]:
    """Return PASS, REVIEW or REJECT using only explicit numeric policy rules.

    REJECT means a hard policy breach. REVIEW means the evidence is insufficient or
    risk-adjusted performance is below the policy's review threshold. No LLM can
    alter these calculations or override this decision.
    """
    policy = policy or RiskPolicy()
    breaches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def numeric(key: str, default: float = 0.0) -> float:
        raw = metrics.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            breaches.append({"rule": key, "observed": str(raw), "limit": "finite numeric value", "severity": "HARD"})
            return float("nan")
        if not math.isfinite(value):
            breaches.append({"rule": key, "observed": str(raw), "limit": "finite numeric value", "severity": "HARD"})
        return value

    drawdown = numeric("max_drawdown")
    volatility = numeric("annualized_volatility")
    gross = numeric("average_gross_exposure", float("nan"))
    turnover = numeric("turnover", metrics.get("total_turnover", 0.0))
    sharpe = numeric("sharpe_ratio")
    try:
        observations = int(metrics.get("observations", 0))
    except (TypeError, ValueError):
        observations = 0

    hard_rules = [
        ("max_drawdown_abs", abs(drawdown) > policy.max_drawdown_abs, drawdown, policy.max_drawdown_abs),
        ("max_annualized_volatility", volatility > policy.max_annualized_volatility, volatility, policy.max_annualized_volatility),
        ("max_average_gross_exposure", gross > policy.max_average_gross_exposure + 1e-9, gross, policy.max_average_gross_exposure),
        ("max_total_turnover", turnover > policy.max_total_turnover, turnover, policy.max_total_turnover),
    ]
    for rule, breached, observed, limit in hard_rules:
        if breached:
            breaches.append({"rule": rule, "observed": observed, "limit": limit, "severity": "HARD"})

    if observations < policy.min_observations:
        warnings.append({"rule": "min_observations", "observed": observations,
                         "limit": policy.min_observations, "severity": "WARNING"})
    if math.isfinite(sharpe) and sharpe < policy.min_sharpe_ratio:
        warnings.append({"rule": "min_sharpe_ratio", "observed": sharpe,
                         "limit": policy.min_sharpe_ratio, "severity": "WARNING"})

    decision = "REJECT" if breaches else "REVIEW" if warnings else "PASS"
    limits = policy.as_dict()
    return {
        "decision": decision,
        "policy_version": policy.version,
        "limits": limits,
        "observed_metrics": {key: metrics.get(key) for key in (
            "total_return", "annualized_return", "annualized_volatility", "sharpe_ratio",
            "max_drawdown", "turnover", "total_turnover", "average_gross_exposure", "observations",
            "benchmark_total_return", "alpha_annualized", "beta", "tracking_error", "information_ratio",
        ) if key in metrics},
        "breaches": breaches,
        "warnings": warnings,
        "deterministic": True,
        "override_allowed": False,
    }
