"""Unit checks for outcome summaries, strategy metrics and drift screening."""
import math
import pytest
from finsight.feedback.monitoring import summarize_outcomes, summarize_strategy_returns
from finsight.feedback.drift import assess_feature_drift


def test_prediction_realisation_error_metrics_are_correct():
    metrics = summarize_outcomes([0.1, 0.0, -0.1], [0.08, 0.02, -0.04])
    assert metrics["sample_count"] == 3
    assert metrics["mae"] == pytest.approx(0.10 / 3)
    assert metrics["mean_bias"] == pytest.approx(-0.02)


def test_strategy_metrics_compound_returns_and_compare_benchmark():
    metrics = summarize_strategy_returns([0.1, -0.05], [0.03, 0.02])
    assert metrics["cumulative_return"] == pytest.approx(1.1 * 0.95 - 1)
    assert metrics["excess_return"] == pytest.approx(metrics["cumulative_return"] - (1.03 * 1.02 - 1))
    assert 0 <= metrics["max_drawdown"] <= 1


def test_drift_detects_shift_and_rejects_invalid_feature_contract():
    reference = {"momentum": [0.0, 0.01, -0.01, 0.02, -0.02, 0.005, -0.005, 0.015, -0.015, 0.0, 0.01]}
    current = {"momentum": [0.2, 0.21, 0.22, 0.19, 0.23, 0.2, 0.18, 0.24, 0.21, 0.22, 0.2]}
    result = assess_feature_drift(reference, current)
    assert result["overall_status"] == "DRIFT"
    with pytest.raises(ValueError):
        assess_feature_drift(reference, {"other": current["momentum"]})
    with pytest.raises(ValueError):
        assess_feature_drift({"momentum": [math.nan] * 10}, current)


def test_future_realised_outcome_is_rejected():
    from pydantic import ValidationError
    from app.schemas.phase5 import OutcomeCreate

    with pytest.raises(ValidationError):
        OutcomeCreate(
            instrument_symbol="MSFT", forecast_date="2099-01-01", realised_date="2099-01-08",
            horizon_sessions=5, predicted_return=0.01, realised_return=0.02,
        )
