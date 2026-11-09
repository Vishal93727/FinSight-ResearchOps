"""RL feature lineage and training split tests that run without the optional SB3 extra."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.rl import align_rl_observations
from finsight.reinforcement_learning.evaluation.training import scale_features_train_only


def _ohlcv(rows: int = 150) -> pd.DataFrame:
    start = date(2023, 1, 1)
    result = []
    prior = 100.0
    for index in range(rows):
        close = 100.0 + index * 0.2 + np.sin(index / 5.0)
        open_price = prior
        result.append({
            "date": start + timedelta(days=index),
            "open": open_price,
            "high": max(open_price, close) + 0.5,
            "low": min(open_price, close) - 0.5,
            "close": close,
            "volume": 1_000_000 + index * 100,
        })
        prior = close
    return pd.DataFrame(result)


def test_rl_observation_matrix_uses_declared_features_and_excludes_next_return_target():
    frame = _ohlcv()
    definition = {"features": ["return_1d", "momentum_5d", "sma_ratio_20d"], "target": "next_day_return"}
    prices, features, names = align_rl_observations(frame, definition)
    assert len(prices) == features.shape[0]
    assert features.shape[1] == 3
    assert names == definition["features"]
    assert "target_next_day_return" not in names
    assert np.isfinite(features).all()
    # The engineered frame omits its early rolling window and final row with no next target.
    assert prices[0] == pytest.approx(float(frame.iloc[20]["close"]))
    assert prices[-1] == pytest.approx(float(frame.iloc[-2]["close"]))


def test_rl_feature_scaler_fits_statistics_on_training_rows_only():
    train = np.array([[0.0, 10.0], [2.0, 10.0], [4.0, 10.0]])
    future = np.array([[100.0, 10.0], [200.0, 10.0]])
    train_scaled, future_scaled, means, scales = scale_features_train_only(train, future)
    assert means.tolist() == pytest.approx([2.0, 10.0])
    assert scales.tolist() == pytest.approx([np.std([0.0, 2.0, 4.0]), 1.0])
    assert train_scaled.mean(axis=0).tolist() == pytest.approx([0.0, 0.0])
    assert future_scaled[0, 0] > 50.0  # future observations did not influence training scaler


def test_rl_feature_scaler_rejects_shape_mismatch_and_non_finite_values():
    with pytest.raises(ValueError, match="equal column counts"):
        scale_features_train_only(np.ones((3, 2)), np.ones((4, 1)))
    with pytest.raises(ValueError, match="finite"):
        scale_features_train_only(np.array([[1.0], [np.nan]]), np.ones((2, 1)))


def test_rl_feature_engineering_rejects_target_as_an_input_feature():
    with pytest.raises(ValueError, match="unsupported or target-only"):
        align_rl_observations(_ohlcv(), {"features": ["target_next_day_return"], "target": "next_day_return"})
