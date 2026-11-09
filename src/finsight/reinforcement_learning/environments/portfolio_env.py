"""Long-only, cost-aware Gymnasium portfolio environment.

The environment consumes an ordered price series and optional point-in-time features.
Observations are trailing-only: at decision time t, the policy receives history through
close(t), then earns the next close-to-close return after choosing the target exposure.
"""
from __future__ import annotations

from typing import Any

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces

    _GymBase = gym.Env
except ImportError:  # Keep the package importable when the optional RL extra is absent.
    gym = None
    spaces = None
    _GymBase = object


class PortfolioTradingEnv(_GymBase):
    metadata = {"render_modes": []}

    def __init__(
        self,
        prices: list[float] | np.ndarray,
        *,
        features: np.ndarray | None = None,
        window_size: int = 20,
        fee_bps: float = 5.0,
        slippage_bps: float = 5.0,
        max_exposure: float = 1.0,
        drawdown_penalty: float = 0.1,
    ):
        if gym is None or spaces is None:
            raise RuntimeError("Gymnasium is required; install the 'rl' optional dependencies")
        values = np.asarray(prices, dtype=np.float64)
        if values.ndim != 1 or len(values) < window_size + 3:
            raise ValueError("prices must be a 1-D series longer than the observation window")
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("prices must be finite and strictly positive")
        if window_size < 3 or not 0 < max_exposure <= 1:
            raise ValueError("invalid window_size or max_exposure")
        if fee_bps < 0 or slippage_bps < 0 or drawdown_penalty < 0:
            raise ValueError("costs and drawdown penalty cannot be negative")

        if features is None:
            feature_values = np.empty((len(values), 0), dtype=np.float64)
        else:
            feature_values = np.asarray(features, dtype=np.float64)
            if feature_values.ndim != 2 or feature_values.shape[0] != len(values):
                raise ValueError("features must be a 2-D matrix aligned one-to-one with prices")
            if not np.isfinite(feature_values).all():
                raise ValueError("features must contain only finite values")

        self.prices = values
        self.features = feature_values
        self.window_size = int(window_size)
        self.fee_rate = float(fee_bps) / 10_000
        self.slippage_rate = float(slippage_bps) / 10_000
        self.max_exposure = float(max_exposure)
        self.drawdown_penalty = float(drawdown_penalty)
        self.action_space = spaces.Box(
            low=np.array([-1.0], dtype=np.float32),
            high=np.array([1.0], dtype=np.float32),
        )
        observation_size = window_size + self.features.shape[1] + 2
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(observation_size,),
            dtype=np.float32,
        )
        self._index = self.window_size
        self._exposure = 0.0
        self._equity = 1.0
        self._peak = 1.0
        self._done = False

    def _observation(self) -> np.ndarray:
        # Return history ends at close(t); feature row t is available at this decision.
        history = self.prices[self._index - self.window_size : self._index + 1]
        returns = np.diff(np.log(history))
        current_features = self.features[self._index]
        return np.asarray(
            [*returns, *current_features, self._exposure, self._equity - 1.0],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        if gym is not None:
            super().reset(seed=seed)
        self._index = self.window_size
        self._exposure = 0.0
        self._equity = 1.0
        self._peak = 1.0
        self._done = False
        return self._observation(), {"equity": self._equity, "exposure": self._exposure}

    def step(self, action):
        if self._done:
            raise RuntimeError("Episode is complete; call reset() before step()")
        target_action = float(np.asarray(action).reshape(-1)[0])
        if not np.isfinite(target_action):
            raise ValueError("action must be finite")
        target = float(np.clip((target_action + 1.0) / 2.0, 0.0, 1.0) * self.max_exposure)
        turnover = abs(target - self._exposure)
        next_return = self.prices[self._index + 1] / self.prices[self._index] - 1.0
        transaction_cost = turnover * (self.fee_rate + self.slippage_rate)
        period_return = target * next_return - transaction_cost
        self._equity *= max(0.0, 1.0 + period_return)
        self._peak = max(self._peak, self._equity)
        drawdown = (self._equity / self._peak) - 1.0
        reward = float(period_return + self.drawdown_penalty * drawdown)
        self._exposure = target
        self._index += 1
        # The final observable close has now been reached; no future return is available.
        terminated = self._index >= len(self.prices) - 1 or self._equity <= 0
        self._done = bool(terminated)
        info = {
            "equity": self._equity,
            "exposure": self._exposure,
            "turnover": turnover,
            "period_return": period_return,
            "drawdown": drawdown,
            "transaction_cost": transaction_cost,
        }
        return self._observation(), reward, bool(terminated), False, info
