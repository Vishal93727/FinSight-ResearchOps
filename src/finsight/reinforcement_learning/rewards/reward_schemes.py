"""Configurable reward schemes for the multi-asset portfolio environment.

The scheme names and the idea of swappable reward functions follow the reference
``MustafaBeratYavas/rl-based-algorithmic-trading-and-portfolio-management`` (MIT). The
``cost_turnover_drawdown`` scheme implements the project plan's formula:

    r_t = log(V_t / V_{t-1}) - l1 * C_t - l2 * T_t - l3 * D_t

with V portfolio value, C transaction cost, T turnover and D the current drawdown. The
weights are configuration, and this reward is a design choice, not a claim of optimality.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

REWARD_SCHEMES = ("log_return", "risk_adjusted", "cost_turnover_drawdown")


@dataclass(frozen=True)
class RewardConfig:
    scheme: str = "cost_turnover_drawdown"
    lambda_cost: float = 1.0
    lambda_turnover: float = 0.001
    lambda_drawdown: float = 0.10
    window: int = 20

    def __post_init__(self) -> None:
        if self.scheme not in REWARD_SCHEMES:
            raise ValueError(f"scheme must be one of {REWARD_SCHEMES}")
        if min(self.lambda_cost, self.lambda_turnover, self.lambda_drawdown) < 0:
            raise ValueError("penalty weights must be non-negative")
        if self.window < 2:
            raise ValueError("window must be at least 2")


def compute_reward(config: RewardConfig, *, log_return: float, cost: float, turnover: float,
                   drawdown: float, recent_net_returns: list[float]) -> float:
    if config.scheme == "log_return":
        return float(log_return)
    if config.scheme == "risk_adjusted":
        window = np.asarray(recent_net_returns[-config.window:], dtype=float)
        if len(window) < 5 or window.std() < 1e-12:
            return float(log_return)
        return float(window.mean() / window.std())
    return float(log_return - config.lambda_cost * cost
                 - config.lambda_turnover * turnover - config.lambda_drawdown * drawdown)
