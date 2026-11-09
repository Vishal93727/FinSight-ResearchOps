"""Small-sample-safe population stability and empirical KS drift diagnostics."""
from __future__ import annotations
import math
from typing import Iterable


def _clean(values: Iterable[float], label: str) -> list[float]:
    cleaned = [float(value) for value in values]
    if len(cleaned) < 10:
        raise ValueError(f"{label} requires at least 10 observations")
    if any(not math.isfinite(value) for value in cleaned):
        raise ValueError(f"{label} contains a non-finite observation")
    if max(cleaned) == min(cleaned):
        # Constant features are valid; a single infinite-width bin would otherwise break quantiles.
        return cleaned
    return cleaned


def _quantile(sorted_values: list[float], q: float) -> float:
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def _psi(reference: list[float], current: list[float], bins: int = 10) -> float:
    ref_sorted = sorted(reference)
    boundaries = sorted(set(_quantile(ref_sorted, i / bins) for i in range(1, bins)))
    if not boundaries:
        return 0.0 if max(current) == min(current) == ref_sorted[0] else 20.0
    def counts(values: list[float]) -> list[int]:
        result = [0] * (len(boundaries) + 1)
        for value in values:
            index = 0
            while index < len(boundaries) and value > boundaries[index]:
                index += 1
            result[index] += 1
        return result
    ref_counts, cur_counts = counts(reference), counts(current)
    ref_total, cur_total = len(reference), len(current)
    score = 0.0
    for ref_count, cur_count in zip(ref_counts, cur_counts):
        # Additive smoothing keeps empty bins finite and deterministic.
        expected = (ref_count + 0.5) / (ref_total + 0.5 * len(ref_counts))
        observed = (cur_count + 0.5) / (cur_total + 0.5 * len(cur_counts))
        score += (observed - expected) * math.log(observed / expected)
    return float(score)


def _ks_statistic(reference: list[float], current: list[float]) -> float:
    ref_sorted, cur_sorted = sorted(reference), sorted(current)
    points = sorted(set(ref_sorted + cur_sorted))
    i = j = 0
    maximum = 0.0
    for point in points:
        while i < len(ref_sorted) and ref_sorted[i] <= point:
            i += 1
        while j < len(cur_sorted) and cur_sorted[j] <= point:
            j += 1
        maximum = max(maximum, abs(i / len(ref_sorted) - j / len(cur_sorted)))
    return float(maximum)


def assess_feature_drift(reference_features: dict[str, list[float]], current_features: dict[str, list[float]]) -> dict:
    """Compare named, numeric feature samples; input samples are not persisted."""
    if not reference_features or set(reference_features) != set(current_features):
        raise ValueError("Reference and current feature sets must have identical non-empty keys")
    results: dict[str, dict] = {}
    for feature in sorted(reference_features):
        ref = _clean(reference_features[feature], f"Reference {feature}")
        cur = _clean(current_features[feature], f"Current {feature}")
        psi = _psi(ref, cur)
        ks = _ks_statistic(ref, cur)
        status = "DRIFT" if psi >= 0.25 else "REVIEW" if psi >= 0.10 else "STABLE"
        results[feature] = {
            "psi": round(psi, 8), "ks_statistic": round(ks, 8), "status": status,
            "reference_count": len(ref), "current_count": len(cur),
            "reference_mean": sum(ref) / len(ref), "current_mean": sum(cur) / len(cur),
        }
    statuses = [item["status"] for item in results.values()]
    overall = "DRIFT" if "DRIFT" in statuses else "REVIEW" if "REVIEW" in statuses else "STABLE"
    return {
        "overall_status": overall, "features": results,
        "summary": {"feature_count": len(results), "drifted_features": sum(s == "DRIFT" for s in statuses),
                    "review_features": sum(s == "REVIEW" for s in statuses),
                    "stable_features": sum(s == "STABLE" for s in statuses),
                    "thresholds": {"stable_psi_below": 0.10, "drift_psi_at_or_above": 0.25},
                    "interpretation": "PSI is a screening diagnostic, not a standalone retraining or promotion decision."},
    }
