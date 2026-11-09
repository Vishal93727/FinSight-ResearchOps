"""Deterministic allocation limits applied to every proposed set of portfolio weights.

Learned policies (reinforcement learning) and rule-based strategies only *propose* target
weights. This module is the single place that turns a proposal into an allowed allocation, so
a policy cannot bypass position or exposure limits whatever it outputs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AllocationLimits:
    max_position_weight: float = 0.40
    max_gross_exposure: float = 1.00

    def __post_init__(self) -> None:
        if not 0.0 < self.max_position_weight <= 1.0:
            raise ValueError("max_position_weight must be in (0, 1]")
        if not 0.0 < self.max_gross_exposure <= 1.0:
            raise ValueError("max_gross_exposure must be in (0, 1] (no leverage)")


def constrain_weights(raw: np.ndarray, limits: AllocationLimits) -> np.ndarray:
    """Map proposed weights (assets..., cash last) to an allowed long-only allocation.

    Asset weights are floored at zero, capped per position, then scaled down if gross
    exposure is above the limit. Whatever is not allocated is held as cash.
    """
    proposal = np.nan_to_num(np.asarray(raw, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    if proposal.ndim != 1 or proposal.size < 2:
        raise ValueError("raw must be a 1-D vector with at least one asset and a cash weight")
    assets = np.minimum(np.maximum(proposal[:-1], 0.0), limits.max_position_weight)
    gross = float(assets.sum())
    if gross > limits.max_gross_exposure:
        assets = assets * (limits.max_gross_exposure / gross)
    return np.append(assets, 1.0 - float(assets.sum()))


def validate_allocation(weights: np.ndarray, limits: AllocationLimits, tolerance: float = 1e-9) -> list[str]:
    """Return human-readable violations; an empty list means the allocation is allowed."""
    w = np.asarray(weights, dtype=float)
    problems: list[str] = []
    if not np.isfinite(w).all():
        return ["weights must be finite"]
    if (w < -tolerance).any():
        problems.append("negative weights (short positions or negative cash) are not allowed")
    if (w[:-1] > limits.max_position_weight + tolerance).any():
        problems.append("a position exceeds max_position_weight")
    if w[:-1].sum() > limits.max_gross_exposure + tolerance:
        problems.append("gross exposure exceeds max_gross_exposure")
    if abs(w.sum() - 1.0) > 1e-6:
        problems.append("weights including cash must sum to 1")
    return problems
