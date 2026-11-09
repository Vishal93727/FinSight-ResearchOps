"""Strict, serializable experiment configuration with temporal validation."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExperimentConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_family: Literal["baseline"] = "baseline"
    baseline: Literal["buy_and_hold", "moving_average_crossover", "rsi_mean_reversion"] = "buy_and_hold"
    target: Literal["next_day_return"] = "next_day_return"
    prediction_horizon_days: int = Field(default=1, ge=1, le=20)
    purge_gap_days: int = Field(default=1, ge=1, le=30)
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date
    evaluation_mode: Literal["holdout", "walk_forward"] = "holdout"
    walk_forward_test_days: int = Field(default=63, ge=10, le=365)
    walk_forward_step_days: int = Field(default=63, ge=10, le=365)
    short_window: int = Field(default=5, ge=2, le=100)
    long_window: int = Field(default=20, ge=3, le=500)
    rsi_window: int = Field(default=14, ge=2, le=100)
    rsi_oversold: float = Field(default=30.0, ge=1, le=49)
    rsi_overbought: float = Field(default=70.0, ge=51, le=99)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    commission_bps: float = Field(default=5.0, ge=0, le=500)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)
    benchmark_symbol: str = Field(default="SPY", min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.\-^]+$")

    @model_validator(mode="after")
    def validate_time_windows(self) -> "ExperimentConfiguration":
        if not self.train_start < self.train_end:
            raise ValueError("Training window start must be before its end")
        if not self.train_end < self.validation_start < self.validation_end:
            raise ValueError("Validation window must start after training ends and have positive duration")
        if not self.validation_end < self.test_start < self.test_end:
            raise ValueError("Test window must start after validation ends and have positive duration")
        required_gap = self.prediction_horizon_days + self.purge_gap_days
        if (self.validation_start - self.train_end).days < required_gap:
            raise ValueError("Training/validation boundary does not purge the full target horizon and embargo")
        if (self.test_start - self.validation_end).days < required_gap:
            raise ValueError("Validation/test boundary does not purge the full target horizon and embargo")
        if self.long_window <= self.short_window:
            raise ValueError("long_window must exceed short_window")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("RSI oversold threshold must be below overbought threshold")
        if self.evaluation_mode == "walk_forward" and self.walk_forward_step_days < self.walk_forward_test_days:
            raise ValueError("Walk-forward step must be at least the test window to avoid overlapping folds")
        return self
