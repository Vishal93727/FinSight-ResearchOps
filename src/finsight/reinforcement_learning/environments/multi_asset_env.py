"""Multi-asset, long-only portfolio environment with next-bar-open execution.

Structure adapted from the portfolio environment in
``MustafaBeratYavas/rl-based-algorithmic-trading-and-portfolio-management`` (MIT): a flat
observation, a softmax action over assets plus cash, swappable reward schemes and a cost
model. Differences by design:

* Timing. The policy decides with information through close(t). Orders trade at open(t+1)
  and the position earns the open(t+1) -> open(t+2) return, so a decision is never filled on
  the bar that produced it.
* Constraints. Every action, and every externally supplied target, passes through
  ``finsight.risk.allocation.constrain_weights`` before it is used.
* Observations contain only trailing quantities known at close(t).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from finsight.reinforcement_learning.rewards.reward_schemes import RewardConfig, compute_reward
from finsight.risk.allocation import AllocationLimits, constrain_weights

try:
    import gymnasium as gym
    from gymnasium import spaces

    _GymBase = gym.Env
except ImportError:  # keep the package importable without the optional RL extra
    gym = None
    spaces = None
    _GymBase = object

VOL_WINDOW = 20


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max()
    exp = np.exp(shifted)
    return exp / exp.sum()


class MultiAssetPortfolioEnv(_GymBase):
    metadata = {"render_modes": []}

    def __init__(self, opens, closes, *, limits: AllocationLimits | None = None,
                 reward: RewardConfig | None = None, fee_bps: float = 1.0, slippage_bps: float = 5.0,
                 lookback: int = 5, action_scale: float = 3.0) -> None:
        super().__init__()
        self.opens = np.asarray(opens, dtype=float)
        self.closes = np.asarray(closes, dtype=float)
        if self.opens.ndim != 2 or self.opens.shape != self.closes.shape:
            raise ValueError("opens and closes must be 2-D arrays of the same shape (bars x assets)")
        if not (np.isfinite(self.opens).all() and np.isfinite(self.closes).all()):
            raise ValueError("prices must be finite")
        if (self.opens <= 0).any() or (self.closes <= 0).any():
            raise ValueError("prices must be positive")
        if fee_bps < 0 or slippage_bps < 0 or lookback < 1 or action_scale <= 0:
            raise ValueError("fee_bps and slippage_bps must be >= 0; lookback >= 1; action_scale > 0")
        self.bars, self.n_assets = self.opens.shape
        self.start = max(lookback, VOL_WINDOW)
        if self.bars < self.start + 4:
            raise ValueError(f"at least {self.start + 4} bars are required")
        self.limits = limits or AllocationLimits()
        self.reward_config = reward or RewardConfig()
        self.cost_rate = (fee_bps + slippage_bps) / 10_000.0
        self.lookback = lookback
        self.action_scale = action_scale
        log_returns = np.zeros_like(self.closes)
        log_returns[1:] = np.log(self.closes[1:] / self.closes[:-1])
        self.log_returns = log_returns
        vol = np.zeros_like(self.closes)
        for t in range(2, self.bars):
            vol[t] = log_returns[max(1, t - VOL_WINDOW + 1): t + 1].std(axis=0)
        self.vol = vol
        if spaces is not None:
            self.action_space = spaces.Box(-1.0, 1.0, shape=(self.n_assets + 1,), dtype=np.float32)
            width = self.lookback * self.n_assets + self.n_assets + (self.n_assets + 1) + 1
            self.observation_space = spaces.Box(-np.inf, np.inf, shape=(width,), dtype=np.float32)
        self._reset_state()

    def _reset_state(self) -> None:
        self.t = self.start
        self.equity = 1.0
        self.peak = 1.0
        self.weights = np.append(np.zeros(self.n_assets), 1.0)
        self.net_returns: list[float] = []

    def _observation(self) -> np.ndarray:
        t = self.t
        window = self.log_returns[t - self.lookback + 1: t + 1].ravel()
        drawdown = 1.0 - self.equity / self.peak
        return np.concatenate([window, self.vol[t], self.weights, [drawdown]]).astype(np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if gym is not None:
            super().reset(seed=seed)
        self._reset_state()
        return self._observation(), {}

    def step(self, action):
        scaled = np.clip(np.asarray(action, dtype=float), -1.0, 1.0) * self.action_scale
        return self.apply_target_weights(_softmax(scaled))

    def apply_target_weights(self, proposal) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        """Constrain a proposed allocation, trade it at the next open and advance one bar."""
        target = constrain_weights(np.asarray(proposal, dtype=float), self.limits)
        t = self.t
        turnover = float(np.abs(target[:-1] - self.weights[:-1]).sum())
        cost = turnover * self.cost_rate
        asset_return = self.opens[t + 2] / self.opens[t + 1] - 1.0
        gross_return = float(target[:-1] @ asset_return)
        previous = self.equity
        self.equity = previous * (1.0 + gross_return - cost)
        self.peak = max(self.peak, self.equity)
        drawdown = 1.0 - self.equity / self.peak
        log_return = float(np.log(self.equity / previous))
        self.net_returns.append(self.equity / previous - 1.0)
        reward = compute_reward(self.reward_config, log_return=log_return, cost=cost, turnover=turnover,
                                drawdown=drawdown, recent_net_returns=self.net_returns)
        drifted = np.append(target[:-1] * (1.0 + asset_return), target[-1]) / (1.0 + gross_return)
        self.weights = drifted
        self.t += 1
        terminated = self.t + 2 >= self.bars
        info = {"equity": float(self.equity), "period_return": self.net_returns[-1], "turnover": turnover,
                "cost": cost, "drawdown": float(drawdown), "target_weights": target.tolist()}
        return self._observation(), float(reward), terminated, False, info
