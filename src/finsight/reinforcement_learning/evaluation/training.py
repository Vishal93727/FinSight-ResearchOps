"""Optional Stable-Baselines3 PPO/SAC training and chronological OOS evaluation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def configuration_hash(config: dict) -> str:
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def scale_features_train_only(
    train_features: np.ndarray,
    evaluation_features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Fit feature scaling on training rows only and apply those statistics everywhere else."""
    train = np.asarray(train_features, dtype=np.float64)
    evaluation = np.asarray(evaluation_features, dtype=np.float64)
    if train.ndim != 2 or evaluation.ndim != 2 or train.shape[1] != evaluation.shape[1]:
        raise ValueError("train and evaluation features must be 2-D matrices with equal column counts")
    if train.shape[0] < 1 or not np.isfinite(train).all() or not np.isfinite(evaluation).all():
        raise ValueError("feature matrices must be non-empty and finite")
    means = train.mean(axis=0)
    scales = train.std(axis=0)
    scales = np.where(scales < 1e-8, 1.0, scales)
    return (train - means) / scales, (evaluation - means) / scales, means, scales


def train_and_evaluate_rl(
    prices: list[float],
    algorithm: str,
    *,
    features: np.ndarray | None = None,
    feature_names: list[str] | None = None,
    seed: int = 42,
    total_timesteps: int = 20_000,
    train_fraction: float = 0.70,
    fee_bps: float = 5.0,
    slippage_bps: float = 5.0,
    artifact_dir: str | Path | None = None,
) -> dict:
    """Train on the earlier interval and evaluate deterministically on the later interval."""
    algo = algorithm.upper()
    if algo not in {"PPO", "SAC"}:
        raise ValueError("algorithm must be PPO or SAC")
    values = np.asarray(prices, dtype=float)
    if values.ndim != 1 or len(values) < 120 or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("at least 120 finite positive chronological prices are required")
    if not 5_000 <= total_timesteps <= 2_000_000:
        raise ValueError("total_timesteps must be between 5,000 and 2,000,000")
    if not 0.60 <= train_fraction <= 0.85:
        raise ValueError("train_fraction must be between 0.60 and 0.85")

    feature_values = None if features is None else np.asarray(features, dtype=np.float64)
    names = list(feature_names or [])
    if feature_values is not None:
        if feature_values.ndim != 2 or feature_values.shape[0] != len(values):
            raise ValueError("features must be a 2-D matrix aligned one-to-one with prices")
        if not np.isfinite(feature_values).all():
            raise ValueError("features must be finite")
        if names and len(names) != feature_values.shape[1]:
            raise ValueError("feature_names must match the feature matrix width")
        if not names:
            names = [f"feature_{index}" for index in range(feature_values.shape[1])]

    try:
        from stable_baselines3 import PPO, SAC
        from stable_baselines3.common.env_checker import check_env
        from finsight.reinforcement_learning.environments.portfolio_env import PortfolioTradingEnv
    except ImportError as exc:
        raise RuntimeError(
            "PPO/SAC training requires the 'rl' extra (Gymnasium and Stable-Baselines3)"
        ) from exc

    split = int(len(values) * train_fraction)
    train_prices = values[:split]
    test_prices = values[split - 20 :]
    train_features = test_features = None
    normalization: dict = {"method": "none", "features": names}
    if feature_values is not None:
        train_scaled, test_scaled, means, scales = scale_features_train_only(
            feature_values[:split], feature_values[split - 20 :]
        )
        train_features = train_scaled
        test_features = test_scaled
        normalization = {
            "method": "train_only_zscore",
            "features": names,
            "means": means.tolist(),
            "scales": scales.tolist(),
        }

    env = PortfolioTradingEnv(
        train_prices,
        features=train_features,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
    check_env(env, warn=True)
    model_class = PPO if algo == "PPO" else SAC
    model = model_class("MlpPolicy", env, seed=seed, verbose=0, device="cpu")
    model.learn(total_timesteps=total_timesteps)

    test_env = PortfolioTradingEnv(
        test_prices,
        features=test_features,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
    observation, _ = test_env.reset(seed=seed)
    equity_curve = [1.0]
    returns: list[float] = []
    exposures: list[float] = []
    turnovers: list[float] = []
    done = False
    while not done:
        action, _ = model.predict(observation, deterministic=True)
        observation, _reward, terminated, truncated, info = test_env.step(action)
        done = terminated or truncated
        equity_curve.append(float(info["equity"]))
        returns.append(float(info["period_return"]))
        exposures.append(float(info["exposure"]))
        turnovers.append(float(info["turnover"]))

    curve = np.asarray(equity_curve)
    period = np.asarray(returns)
    drawdown = curve / np.maximum.accumulate(curve) - 1.0
    volatility = float(period.std(ddof=1) * np.sqrt(252)) if len(period) > 1 else 0.0
    sharpe = (
        float(period.mean() / period.std(ddof=1) * np.sqrt(252))
        if len(period) > 1 and period.std(ddof=1) > 1e-12
        else 0.0
    )
    config = {
        "algorithm": algo,
        "seed": seed,
        "total_timesteps": total_timesteps,
        "train_fraction": train_fraction,
        "split_index": split,
        "train_start_index": 0,
        "train_end_index_exclusive": split,
        "test_start_index": split,
        "test_end_index_exclusive": len(values),
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "evaluation_mode": "strict_chronological_oos",
        "feature_normalization": normalization,
    }
    digest = configuration_hash(config)
    artifact_path = None
    if artifact_dir is not None:
        folder = Path(artifact_dir).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        saved = folder / f"{algo.lower()}-{digest[:16]}"
        model.save(str(saved))
        artifact_path = str(saved.with_suffix(".zip"))
    return {
        "algorithm": algo,
        "configuration": config,
        "configuration_sha256": digest,
        "out_of_sample": True,
        "artifact_path": artifact_path,
        "metrics": {
            "total_return": float(curve[-1] - 1.0),
            "max_drawdown": float(drawdown.min()),
            "annualized_volatility": volatility,
            "sharpe_ratio": sharpe,
            "average_gross_exposure": float(np.mean(exposures)) if exposures else 0.0,
            "turnover": float(np.sum(turnovers)),
            "observations": int(len(period)),
            "train_observations": int(split),
            "test_observations": int(len(period)),
        },
    }
