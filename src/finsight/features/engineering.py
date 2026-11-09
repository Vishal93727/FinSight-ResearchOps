"""Leakage-aware OHLCV feature calculations for next-session research targets."""
from __future__ import annotations
import math
import pandas as pd

_REQUIRED = {"date", "open", "high", "low", "close", "volume"}


def build_price_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Build features available at close(t) and a separate next-session return target.

    The target is intentionally shifted by -1. It must never be used as an input feature.
    Rows without a complete feature window or a next-session target are dropped.
    """
    missing = _REQUIRED - set(bars.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(sorted(missing))}")
    frame = bars.loc[:, sorted(_REQUIRED)].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise", utc=True)
    frame = frame.sort_values("date").reset_index(drop=True)
    if frame["date"].duplicated().any():
        raise ValueError("Duplicate dates are not allowed")
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if not frame[numeric_columns].apply(lambda column: column.map(math.isfinite)).all().all():
        raise ValueError("OHLCV values must be finite numbers")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame["volume"] < 0).any():
        raise ValueError("Prices must be positive and volume must be non-negative")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high must be at least open, close and low")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low must be at most open, close and high")

    close = frame["close"].astype(float)
    daily_return = close.pct_change()
    result = pd.DataFrame({"date": frame["date"]})
    result["return_1d"] = daily_return
    result["momentum_5d"] = close.pct_change(5)
    result["sma_ratio_5d"] = close / close.rolling(5, min_periods=5).mean() - 1.0
    result["sma_ratio_20d"] = close / close.rolling(20, min_periods=20).mean() - 1.0
    result["volatility_20d"] = daily_return.rolling(20, min_periods=20).std()
    result["volume_change_1d"] = frame["volume"].astype(float).pct_change().replace([float("inf"), -float("inf")], pd.NA)
    result["target_next_day_return"] = daily_return.shift(-1)
    feature_columns = ["return_1d", "momentum_5d", "sma_ratio_5d", "sma_ratio_20d", "volatility_20d", "volume_change_1d"]
    result = result.dropna(subset=feature_columns + ["target_next_day_return"]).reset_index(drop=True)
    return result


def build_declared_feature_frame(bars: pd.DataFrame, definition: dict) -> pd.DataFrame:
    """Build only the feature columns declared by one immutable feature-set version."""
    if not isinstance(definition, dict):
        raise ValueError("Feature-set definition must be an object")
    declared = definition.get("features")
    if not isinstance(declared, list) or not declared or any(not isinstance(item, str) for item in declared):
        raise ValueError("Feature-set definition must declare a non-empty string feature list")
    available = build_price_features(bars)
    allowed_features = {
        "return_1d", "momentum_5d", "sma_ratio_5d", "sma_ratio_20d",
        "volatility_20d", "volume_change_1d",
    }
    unknown = sorted(set(declared) - allowed_features)
    if unknown:
        raise ValueError(f"Feature-set declares unsupported or target-only columns: {', '.join(unknown)}")
    target = definition.get("target", "next_day_return")
    if target not in {"next_day_return", "target_next_day_return"}:
        raise ValueError("Feature-set target must be next_day_return")
    return available.loc[:, ["date", *declared, "target_next_day_return"]].copy()
