"""Request/response contracts for outcome feedback and production operations."""
from datetime import UTC, date, datetime
from math import isfinite
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OutcomeCreate(BaseModel):
    instrument_symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    forecast_date: date
    realised_date: date
    horizon_sessions: int = Field(default=1, ge=1, le=252)
    predicted_return: float = Field(ge=-10, le=10, allow_inf_nan=False)
    realised_return: float = Field(ge=-10, le=10, allow_inf_nan=False)
    benchmark_return: float | None = Field(default=None, ge=-10, le=10, allow_inf_nan=False)
    model_version_id: str | None = Field(default=None, max_length=36)
    experiment_run_id: str | None = Field(default=None, max_length=36)
    paper_account_id: str | None = Field(default=None, max_length=36)
    observation_source: str = Field(default="MANUAL_RECONCILIATION", min_length=1, max_length=80)
    source_reference: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def chronology(self):
        if self.realised_date < self.forecast_date:
            raise ValueError("realised_date cannot precede forecast_date")
        if self.realised_date > datetime.now(UTC).date():
            raise ValueError("realised_date cannot be in the future")
        return self


class OutcomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    instrument_symbol: str
    forecast_date: date
    realised_date: date
    horizon_sessions: int
    predicted_return: float
    realised_return: float
    benchmark_return: float | None
    model_version_id: str | None
    experiment_run_id: str | None
    paper_account_id: str | None
    observation_source: str
    source_reference: str | None
    idempotency_key: str | None = None
    created_by: str
    created_at: datetime


class StrategyPerformanceCreate(BaseModel):
    strategy_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    period_start: datetime
    period_end: datetime
    returns: list[float] = Field(min_length=2, max_length=10000)
    benchmark_returns: list[float] | None = Field(default=None, min_length=2, max_length=10000)
    source_reference: str | None = Field(default=None, max_length=500)

    @field_validator("returns", "benchmark_returns")
    @classmethod
    def validate_returns(cls, values):
        if values is not None and any(not isfinite(float(v)) or float(v) < -1 for v in values):
            raise ValueError("Returns must be finite decimal values no less than -1")
        return values

    @model_validator(mode="after")
    def chronology_and_alignment(self):
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        if self.benchmark_returns is not None and len(self.benchmark_returns) != len(self.returns):
            raise ValueError("benchmark_returns must have the same length as returns")
        return self


class StrategyRunEvaluationCreate(BaseModel):
    experiment_run_id: str = Field(min_length=1, max_length=36)


class DriftCheckCreate(BaseModel):
    model_version_id: str | None = Field(default=None, max_length=36)
    reference_snapshot_id: str | None = Field(default=None, max_length=36)
    current_snapshot_id: str | None = Field(default=None, max_length=36)
    reference_features: dict[str, list[float]] = Field(min_length=1, max_length=100)
    current_features: dict[str, list[float]] = Field(min_length=1, max_length=100)

    @field_validator("reference_features", "current_features")
    @classmethod
    def validate_samples(cls, values):
        for name, sample in values.items():
            if not name or len(name) > 80 or len(sample) < 10 or len(sample) > 20000:
                raise ValueError("Each named feature requires 10 to 20,000 observations")
            if any(not isfinite(float(item)) for item in sample):
                raise ValueError("Drift samples must contain only finite numbers")
        return values

    @model_validator(mode="after")
    def matching_feature_contract(self):
        if set(self.reference_features) != set(self.current_features):
            raise ValueError("Reference and current feature names must match exactly")
        return self


class SuggestionDecision(BaseModel):
    status: Literal["ACCEPTED", "DISMISSED"]
    comment: str = Field(min_length=3, max_length=1000)


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    rationale: str
    suggested_action: str
    source_type: str
    source_id: str | None
    status: str
    decision_comment: str | None
    created_at: datetime
    decided_at: datetime | None


class MonitoringSummary(BaseModel):
    generated_at: datetime
    services: dict
    jobs: dict
    experiment_runs: dict
    paper_portfolios: dict
    feedback: dict
    notes: list[str]


class StaleJobRecoveryRequest(BaseModel):
    stale_after_minutes: int = Field(default=30, ge=10, le=1440)
    limit: int = Field(default=50, ge=1, le=200)
    confirm_requeue: bool = False
