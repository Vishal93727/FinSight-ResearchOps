"""Deterministic, model-independent governance and paper-execution risk rules."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ModelGovernancePolicy:
    version: str = "model-governance-v1"
    minimum_test_observations: int = 10
    minimum_directional_accuracy: float = 0.45
    maximum_rmse: float = 0.10
    require_out_of_sample: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_model_candidate(metrics: dict, *, out_of_sample: bool,
                             policy: ModelGovernancePolicy | None = None) -> dict:
    policy = policy or ModelGovernancePolicy()
    breaches: list[dict] = []
    warnings: list[dict] = []
    try:
        observations = int(metrics.get("test_rows", metrics.get("test_observations", metrics.get("observations", 0))))
    except (TypeError, ValueError):
        observations = 0
    if observations < policy.minimum_test_observations:
        warnings.append({"rule": "minimum_test_observations", "observed": observations,
                         "limit": policy.minimum_test_observations, "severity": "WARNING"})
    if policy.require_out_of_sample and not out_of_sample:
        breaches.append({"rule": "out_of_sample_required", "observed": False, "limit": True, "severity": "HARD"})
    artifact_integrity = metrics.get("artifact_integrity")
    if artifact_integrity in {"MISSING", "NOT_PROVIDED"}:
        breaches.append({"rule": "artifact_integrity_required", "observed": artifact_integrity, "limit": "VERIFIED", "severity": "HARD"})
    directional = metrics.get("directional_accuracy")
    if directional is not None:
        try:
            value = float(directional)
        except (TypeError, ValueError):
            value = float("nan")
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            breaches.append({"rule": "directional_accuracy_finite", "observed": str(directional), "limit": "finite [0,1]", "severity": "HARD"})
        elif value < policy.minimum_directional_accuracy:
            warnings.append({"rule": "minimum_directional_accuracy", "observed": value,
                             "limit": policy.minimum_directional_accuracy, "severity": "WARNING"})
    rmse = metrics.get("rmse")
    if rmse is not None:
        try:
            value = float(rmse)
        except (TypeError, ValueError):
            value = float("nan")
        if not math.isfinite(value) or value < 0:
            breaches.append({"rule": "rmse_finite_nonnegative", "observed": str(rmse), "limit": "finite >= 0", "severity": "HARD"})
        elif value > policy.maximum_rmse:
            warnings.append({"rule": "maximum_rmse", "observed": value, "limit": policy.maximum_rmse, "severity": "WARNING"})
    decision = "REJECT" if breaches else "REVIEW" if warnings else "PASS"
    return {"decision": decision, "policy_version": policy.version, "limits": policy.as_dict(),
            "observed_metrics": {k: metrics.get(k) for k in ("rmse", "mae", "r2", "directional_accuracy", "test_rows", "test_observations", "observations", "max_drawdown", "sharpe_ratio") if k in metrics},
            "breaches": breaches, "warnings": warnings, "deterministic": True, "override_allowed": False}


def evaluate_paper_order(*, side: str, quantity: Decimal, reference_price: Decimal,
                         cash_balance: Decimal, current_equity: Decimal,
                         current_gross_exposure: Decimal, symbol_position: Decimal,
                         current_symbol_notional: Decimal | None = None, account_limits: dict, kill_switch: bool) -> dict:
    """Validate a paper order without consulting model/LLM output.

    Exposure checks are performed against the proposed post-fill state. The `reference_price`
    is explicitly a simulation input, not a live quote or a broker price.
    """
    reasons: list[str] = []
    if kill_switch:
        reasons.append("Account kill switch is active")
    if side not in {"BUY", "SELL"}:
        reasons.append("Unsupported order side")
    if quantity <= 0 or reference_price <= 0:
        reasons.append("Quantity and simulation reference price must be positive")
        return {"approved": False, "decision": "REJECT", "reasons": reasons, "deterministic": True}
    notional = quantity * reference_price
    fee_rate = Decimal(str(account_limits.get("fee_bps", 0.0))) / Decimal("10000")
    estimated_fee = notional * fee_rate
    max_order = Decimal(str(account_limits.get("max_order_notional", "0")))
    if max_order > 0 and notional > max_order:
        reasons.append("Order notional exceeds the account limit")
    post_position = symbol_position + quantity if side == "BUY" else symbol_position - quantity
    if side == "SELL" and quantity > symbol_position:
        reasons.append("Sell quantity exceeds the available paper position")
    cash_after = cash_balance - notional - estimated_fee if side == "BUY" else cash_balance + notional - estimated_fee
    if side == "BUY" and cash_after < 0:
        reasons.append("Insufficient paper cash after estimated fees")
    prior_symbol_notional = current_symbol_notional if current_symbol_notional is not None else abs(symbol_position * reference_price)
    exposure_after = current_gross_exposure - abs(prior_symbol_notional) + abs(post_position * reference_price)
    exposure_ratio = exposure_after / current_equity if current_equity > 0 else Decimal("Infinity")
    max_gross = Decimal(str(account_limits.get("max_gross_exposure", 1.0)))
    max_symbol = Decimal(str(account_limits.get("max_symbol_exposure", 0.40)))
    symbol_ratio = abs(post_position * reference_price) / current_equity if current_equity > 0 else Decimal("Infinity")
    if exposure_ratio > max_gross:
        reasons.append("Post-order gross exposure exceeds the account limit")
    if symbol_ratio > max_symbol:
        reasons.append("Post-order symbol exposure exceeds the account limit")
    return {"approved": not reasons, "decision": "PASS" if not reasons else "REJECT", "reasons": reasons,
            "estimated_notional": str(notional), "estimated_fee": str(estimated_fee),
            "post_order_gross_exposure_ratio": str(exposure_ratio),
            "post_order_symbol_exposure_ratio": str(symbol_ratio),
            "deterministic": True, "policy_version": "paper-risk-v1", "llm_override_allowed": False}
