"""API contracts for Phase 2 hypotheses, feature sets and experiments."""
from datetime import datetime
import hashlib
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.common import ORMModel
from finsight.experiments.config import ExperimentConfiguration


class EvidenceItem(BaseModel):
    source_type: Literal["SEC_FILING", "DATA_SNAPSHOT", "URL", "NOTE"]
    title: str = Field(min_length=1, max_length=240)
    source_uri: str | None = Field(default=None, max_length=1000)
    source_id: str | None = Field(default=None, max_length=100)
    excerpt: str = Field(default="", max_length=2000)
    excerpt_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @field_validator("source_uri")
    @classmethod
    def require_safe_web_uri(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Evidence URI must be an http(s) URL without embedded credentials")
        return value

    @model_validator(mode="after")
    def fingerprint_excerpt(self) -> "EvidenceItem":
        if self.excerpt:
            digest = hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()
            if self.excerpt_sha256 and self.excerpt_sha256.lower() != digest:
                raise ValueError("excerpt_sha256 does not match the supplied excerpt")
            self.excerpt_sha256 = digest
        return self


class HypothesisCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.\-^]+$")
    thesis: str = Field(min_length=20, max_length=5000)
    rationale: str = Field(default="", max_length=5000)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=50)


class HypothesisDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(default="", max_length=2000)


class HypothesisResponse(ORMModel):
    id: str
    title: str
    symbol: str
    thesis: str
    rationale: str
    status: str
    evidence: list[dict]
    decision_note: str
    version: int
    owner_user_id: str
    created_at: datetime
    updated_at: datetime


class FeatureSetCreate(BaseModel):
    feature_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(default="", max_length=2000)
    definition: dict = Field(min_length=1)
    source_snapshot_id: str

    @field_validator("definition")
    @classmethod
    def validate_feature_definition(cls, value: dict) -> dict:
        allowed = {"return_1d", "momentum_5d", "sma_ratio_5d", "sma_ratio_20d", "volatility_20d", "volume_change_1d"}
        features = value.get("features")
        if not isinstance(features, list) or not features or any(not isinstance(item, str) for item in features):
            raise ValueError("Feature definition must contain a non-empty features list")
        if set(features) - allowed:
            raise ValueError("Feature definition contains unsupported or target-only columns")
        if value.get("target", "next_day_return") not in {"next_day_return", "target_next_day_return"}:
            raise ValueError("Feature target must be next_day_return")
        return value


class FeatureSetResponse(ORMModel):
    id: str
    feature_key: str
    version: int
    description: str
    definition: dict
    source_snapshot_id: str
    definition_sha256: str
    created_by: str
    created_at: datetime


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    hypothesis_id: str
    dataset_snapshot_id: str
    feature_set_version_id: str
    benchmark_snapshot_id: str | None = None
    configuration: ExperimentConfiguration


class ExperimentResponse(ORMModel):
    id: str
    name: str
    hypothesis_id: str
    instrument_symbol: str
    dataset_snapshot_id: str
    feature_set_version_id: str
    benchmark_snapshot_id: str | None
    configuration: dict
    configuration_sha256: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class ExperimentRunCreate(BaseModel):
    random_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class ExperimentRunResponse(ORMModel):
    id: str
    experiment_id: str
    run_number: int
    status: str
    random_seed: int
    idempotency_key: str | None
    metrics: dict
    artifacts: dict
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ExperimentRiskReviewResponse(ORMModel):
    id: str
    run_id: str
    decision: str
    policy_version: str
    limits: dict
    observed_metrics: dict
    breaches: list[dict]
    warnings: list[dict]
    deterministic: bool
    override_allowed: bool
    created_at: datetime


class ExperimentComparisonItem(BaseModel):
    run_id: str
    run_number: int
    status: str
    total_return: float | None = None
    annualized_return: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    annualized_volatility: float | None = None
    benchmark_total_return: float | None = None
    information_ratio: float | None = None
    risk_decision: str | None = None
