"""Pydantic contracts for model governance, RL evaluation and paper execution."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelVersionCreate(BaseModel):
    model_key: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._+-]+$")
    source_evaluation_id: str | None = None
    source_rl_evaluation_id: str | None = None

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.source_evaluation_id) == bool(self.source_rl_evaluation_id):
            raise ValueError("Provide exactly one supervised or RL evaluation source")
        return self


class GovernanceDecisionCreate(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    comment: str = Field(default="", max_length=2000)


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    model_key: str
    version: str
    model_family: str
    source_evaluation_id: str | None
    source_rl_evaluation_id: str | None
    artifact_uri: str | None
    artifact_sha256: str | None
    dataset_snapshot_id: str | None
    feature_set_version_id: str | None
    metrics: dict
    configuration: dict
    risk_decision: str
    state: str
    created_by: str


class PaperAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    initial_cash: Decimal = Field(gt=0, le=Decimal("1000000000"))
    currency: Literal["USD"] = "USD"
    max_gross_exposure: float = Field(default=1.0, gt=0, le=1.0)
    max_symbol_exposure: float = Field(default=0.40, gt=0, le=1.0)
    max_order_notional: Decimal = Field(default=Decimal("25000"), gt=0)
    fee_bps: float = Field(default=5.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)


class PaperAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    currency: str
    initial_cash: Decimal
    cash_balance: Decimal
    max_gross_exposure: float
    max_symbol_exposure: float
    max_order_notional: Decimal
    fee_bps: float
    slippage_bps: float
    kill_switch: bool


class PaperOrderCreate(BaseModel):
    client_order_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    model_version_id: str
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.^_-]+$")
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0, le=Decimal("1000000000"))
    simulation_reference_price: Decimal = Field(gt=0, le=Decimal("10000000"))


class PaperOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    account_id: str
    model_version_id: str
    symbol: str
    side: str
    quantity: Decimal
    simulation_reference_price: Decimal
    fill_price: Decimal | None
    status: str
    client_order_id: str
    risk_check: dict
    rejection_reason: str | None


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = Field(min_length=4, max_length=1000)


class ReconcileRequest(BaseModel):
    repair: bool = False


class RLEvaluationCreate(BaseModel):
    dataset_snapshot_id: str
    feature_set_version_id: str
    algorithm: Literal["PPO", "SAC"]
    price_column: Literal["close"] = "close"
    date_column: Literal["date"] = "date"
    seed: int = Field(default=42, ge=0, le=100000)
    total_timesteps: int = Field(default=20000, ge=5000, le=2000000)
    train_fraction: float = Field(default=0.70, ge=0.60, le=0.85)
    fee_bps: float = Field(default=5.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)

class RLEvaluationJobCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    dataset_snapshot_id: str
    feature_set_version_id: str
    algorithm: Literal["PPO", "SAC"]
    price_column: Literal["close"] = "close"
    date_column: Literal["date"] = "date"
    seed: int = Field(default=42, ge=0, le=100000)
    total_timesteps: int = Field(default=20000, ge=5000, le=2000000)
    train_fraction: float = Field(default=0.70, ge=0.60, le=0.85)
    fee_bps: float = Field(default=5.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)
