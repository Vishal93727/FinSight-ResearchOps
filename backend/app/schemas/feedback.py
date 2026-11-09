"""API contracts for prediction outcomes, strategy monitoring and drift feedback."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PredictionOutcomeCreate(BaseModel):
    instrument_symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    predicted_value: float = Field(allow_inf_nan=False)
    realized_value: float = Field(allow_inf_nan=False)
    prediction_timestamp: datetime
    observed_at: datetime | None = None
    horizon_days: int = Field(default=1, ge=1, le=365)
    model_version_id: str | None = Field(default=None, max_length=36)
    strategy_key: str | None = Field(default=None, max_length=120)
    source_reference: str | None = Field(default=None, max_length=160)
    metadata_json: dict = Field(default_factory=dict, max_length=30)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class PredictionOutcomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    instrument_symbol: str
    predicted_value: float
    realized_value: float
    prediction_timestamp: datetime
    observed_at: datetime
    horizon_days: int
    model_version_id: str | None
    strategy_key: str | None
    source_reference: str | None
    metadata_json: dict
    created_by: str
    created_at: datetime


class StrategyEvaluationCreate(BaseModel):
    strategy_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    returns: list[float] = Field(min_length=2, max_length=10000)
    benchmark_returns: list[float] | None = Field(default=None, min_length=2, max_length=10000)
    period_start: datetime
    period_end: datetime
    source_reference: str | None = Field(default=None, max_length=160)

    @field_validator("returns", "benchmark_returns")
    @classmethod
    def finite_return_values(cls, values):
        if values is not None:
            import math
            if any(not math.isfinite(float(x)) or float(x) < -1 for x in values):
                raise ValueError("Returns must be finite decimal values no less than -1")
        return values

    @model_validator(mode="after")
    def validate_period_and_benchmark(self):
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        if self.benchmark_returns is not None and len(self.benchmark_returns) != len(self.returns):
            raise ValueError("benchmark_returns must match returns length")
        return self


class DriftCheckCreate(BaseModel):
    monitor_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    feature_name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    baseline_values: list[float] = Field(min_length=10, max_length=10000)
    current_values: list[float] = Field(min_length=10, max_length=10000)
    threshold: float = Field(default=0.2, gt=0, le=5, allow_inf_nan=False)
    dataset_snapshot_id: str | None = Field(default=None, max_length=36)

    @field_validator("baseline_values", "current_values")
    @classmethod
    def finite_values(cls, values):
        import math
        if any(not math.isfinite(float(x)) for x in values):
            raise ValueError("Drift samples must be finite numeric values")
        return values


class DriftAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    monitor_key: str
    feature_name: str
    drift_score: float
    threshold: float
    severity: str
    status: str
    baseline_summary: dict
    current_summary: dict
    dataset_snapshot_id: str | None
    resolution_note: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    created_by: str
    created_at: datetime


class DriftResolution(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class ResearchSuggestionDecision(BaseModel):
    decision: Literal["ACCEPT", "DISMISS"]
    note: str = Field(default="", max_length=1000)


class ResearchSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    suggestion_key: str
    title: str
    rationale: str
    priority: str
    status: str
    evidence: dict
    decision_note: str | None
    decided_by: str | None
    decided_at: datetime | None
    created_by: str
    created_at: datetime
