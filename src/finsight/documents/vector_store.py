"""Portable validation helpers for the PostgreSQL pgvector storage adapter."""

from __future__ import annotations

import math
from collections.abc import Sequence


def pgvector_literal(values: Sequence[float], dimensions: int = 384) -> str:
    """Return a validated pgvector text literal without accepting NaN/Infinity.

    The SQL call site must still bind this string as a parameter and cast it to
    ``vector``; this helper never interpolates values into SQL text.
    """
    if len(values) != dimensions:
        raise ValueError(f"Embedding must contain exactly {dimensions} dimensions")
    normalized: list[str] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError("Embedding values must be finite real numbers")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Embedding values must be finite real numbers") from exc
        if not math.isfinite(number):
            raise ValueError("Embedding values must be finite real numbers")
        normalized.append(format(number, ".9g"))
    return "[" + ",".join(normalized) + "]"
