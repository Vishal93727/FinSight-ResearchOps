"""API contracts for reproducible Phase 3 supervised model evaluations."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORMModel


class ModelEvaluationCreate(BaseModel):
    dataset_snapshot_id: str
    feature_set_version_id: str
    date_column: str = Field(default="date", min_length=1, max_length=80)
    model_family: Literal["ridge", "random_forest", "xgboost", "lightgbm", "lstm"] = "ridge"
    random_seed: int = Field(default=42, ge=0, le=2**31 - 1)
    test_fraction: float = Field(default=0.2, ge=0.1, le=0.4)
    sequence_length: int = Field(default=12, ge=5, le=60)
    epochs: int = Field(default=35, ge=5, le=50)


class ModelEvaluationResponse(ORMModel):
    id: str
    dataset_snapshot_id: str
    instrument_symbol: str
    feature_set_version_id: str
    model_family: str
    target_column: str
    feature_columns: list
    configuration: dict
    configuration_sha256: str
    metrics: dict
    artifact_path: str | None
    status: str
    created_at: datetime


class SentimentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    provider: Literal["lexicon", "finbert"] = "lexicon"


class ModelEvaluationJobCreate(ModelEvaluationCreate):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
