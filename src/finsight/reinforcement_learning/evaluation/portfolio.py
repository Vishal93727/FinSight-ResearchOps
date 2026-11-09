"""Chronological out-of-sample evaluation of allocation policies against baselines.

A policy is judged on a later interval than it was trained on, over repeated seeds, next to
equal-weight and buy-and-hold baselines that run through the *same* environment (same costs,
same constraints, same next-open execution). RL is a competing allocation method, not an
assumed improvement: the report states how many seeds beat each baseline.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable

import numpy as np

from finsight.reinforcement_learning.environments.multi_asset_env import MultiAssetPortfolioEnv
from finsight.reinforcement_learning.rewards.reward_schemes import RewardConfig
from finsight.risk.allocation import AllocationLimits

TRADING_DAYS = 252


def portfolio_metrics(equity: np.ndarray, period_returns: np.ndarray, turnover: float) -> dict:
    """Standard performance statistics (formulas follow the usual definitions)."""
    curve = np.asarray(equity, dtype=float)
    rets = np.asarray(period_returns, dtype=float)
    drawdown = curve / np.maximum.accumulate(curve) - 1.0
    std = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    downside = rets[rets < 0]
    down_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    return {
        "total_return": float(curve[-1] / curve[0] - 1.0),
        "annualized_volatility": std * float(np.sqrt(TRADING_DAYS)),
        "sharpe_ratio": float(rets.mean() / std * np.sqrt(TRADING_DAYS)) if std > 1e-12 else 0.0,
        "sortino_ratio": float(rets.mean() / down_std * np.sqrt(TRADING_DAYS)) if down_std > 1e-12 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "turnover": float(turnover),
        "observations": int(len(rets)),
    }


def run_allocation(env: MultiAssetPortfolioEnv, policy: Callable[[MultiAssetPortfolioEnv, np.ndarray], np.ndarray]) -> dict:
    """Run ``policy(env, observation) -> proposed weights (assets..., cash)`` to the end."""
    observation, _ = env.reset()
    equity, rets, turnovers = [1.0], [], []
    done = False
    while not done:
        observation, _reward, terminated, truncated, info = env.apply_target_weights(policy(env, observation))
        done = terminated or truncated
        equity.append(info["equity"])
        rets.append(info["period_return"])
        turnovers.append(info["turnover"])
    return {"metrics": portfolio_metrics(np.array(equity), np.array(rets), float(np.sum(turnovers))),
            "equity_curve": equity}


def equal_weight_policy(env: MultiAssetPortfolioEnv, _observation: np.ndarray) -> np.ndarray:
    return np.append(np.full(env.n_assets, 1.0 / env.n_assets), 0.0)


def buy_and_hold_policy(env: MultiAssetPortfolioEnv, _observation: np.ndarray) -> np.ndarray:
    """Equal weights on the first bar, then no rebalancing (current drifted weights)."""
    if env.t == env.start:
        return np.append(np.full(env.n_assets, 1.0 / env.n_assets), 0.0)
    return env.weights.copy()


def evaluate_baselines(opens, closes, **env_kwargs) -> dict:
    return {name: run_allocation(MultiAssetPortfolioEnv(opens, closes, **env_kwargs), policy)["metrics"]
            for name, policy in (("equal_weight", equal_weight_policy), ("buy_and_hold", buy_and_hold_policy))}


def configuration_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def train_and_evaluate_portfolio(opens, closes, algorithm: str, *, seeds: tuple[int, ...] = (0, 1, 2),
                                 total_timesteps: int = 20_000, train_fraction: float = 0.70,
                                 limits: AllocationLimits | None = None, reward: RewardConfig | None = None,
                                 fee_bps: float = 1.0, slippage_bps: float = 5.0) -> dict:
    """Train on the earlier interval per seed; evaluate on the later one beside the baselines."""
    algo = algorithm.upper()
    if algo not in {"PPO", "SAC"}:
        raise ValueError("algorithm must be PPO or SAC")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a non-empty tuple of distinct integers")
    if not 0.60 <= train_fraction <= 0.85:
        raise ValueError("train_fraction must be between 0.60 and 0.85")
    if total_timesteps < 1:
        raise ValueError("total_timesteps must be positive")
    try:
        from stable_baselines3 import PPO, SAC
        from stable_baselines3.common.env_checker import check_env
    except ImportError as exc:
        raise RuntimeError("PPO/SAC training requires the 'rl' extra (Gymnasium and Stable-Baselines3)") from exc

    opens_arr, closes_arr = np.asarray(opens, dtype=float), np.asarray(closes, dtype=float)
    kwargs = {"limits": limits, "reward": reward, "fee_bps": fee_bps, "slippage_bps": slippage_bps}
    split = int(len(opens_arr) * train_fraction)
    context = max(5, 20)  # bars before the split used only to warm up trailing features
    train_o, train_c = opens_arr[:split], closes_arr[:split]
    test_o, test_c = opens_arr[split - context:], closes_arr[split - context:]
    baselines = evaluate_baselines(test_o, test_c, **kwargs)
    model_class = PPO if algo == "PPO" else SAC
    per_seed = []
    for seed in seeds:
        train_env = MultiAssetPortfolioEnv(train_o, train_c, **kwargs)
        if seed == seeds[0]:
            check_env(train_env, warn=True)
        model = model_class("MlpPolicy", train_env, seed=seed, verbose=0, device="cpu")
        model.learn(total_timesteps=total_timesteps)

        def act(env: MultiAssetPortfolioEnv, observation: np.ndarray, model=model) -> np.ndarray:
            action, _ = model.predict(observation, deterministic=True)
            scaled = np.clip(action, -1.0, 1.0) * env.action_scale
            exp = np.exp(scaled - scaled.max())
            return exp / exp.sum()

        per_seed.append({"seed": seed, **run_allocation(MultiAssetPortfolioEnv(test_o, test_c, **kwargs), act)["metrics"]})
    returns = np.array([row["total_return"] for row in per_seed])
    config = {"algorithm": algo, "seeds": list(seeds), "total_timesteps": total_timesteps,
              "train_fraction": train_fraction, "split_index": split, "fee_bps": fee_bps,
              "slippage_bps": slippage_bps, "evaluation_mode": "strict_chronological_oos",
              "max_position_weight": (limits or AllocationLimits()).max_position_weight,
              "max_gross_exposure": (limits or AllocationLimits()).max_gross_exposure,
              "reward_scheme": (reward or RewardConfig()).scheme}
    return {
        "algorithm": algo, "configuration": config, "configuration_sha256": configuration_hash(config),
        "out_of_sample": True, "per_seed": per_seed, "baselines": baselines,
        "summary": {
            "mean_total_return": float(returns.mean()), "std_total_return": float(returns.std(ddof=0)),
            "seeds_beating_equal_weight": int((returns > baselines["equal_weight"]["total_return"]).sum()),
            "seeds_beating_buy_and_hold": int((returns > baselines["buy_and_hold"]["total_return"]).sum()),
            "seed_count": len(seeds),
        },
    }
