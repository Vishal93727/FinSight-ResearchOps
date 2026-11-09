"""Descriptive technical context, a testable hypothesis proposal and a methodology critic.

These are deterministic steps: they describe data and propose a *test*, they never claim a
return, and they cannot approve anything. Approval stays with the existing human review of
hypotheses (DRAFT -> UNDER_REVIEW -> APPROVED/REJECTED).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

import pandas as pd

from finsight.research.agents.analysts import AnalystFinding

DECLARED_FEATURES = ("return_1d", "momentum_5d", "sma_ratio_5d", "sma_ratio_20d",
                     "volatility_20d", "volume_change_1d")
SUPPORTED_TARGET = "target_next_day_return"
EVALUATION = "walk_forward_out_of_sample"
_FORBIDDEN_FEATURE_WORDS = ("target", "forward", "future", "next", "label")
_PERFORMANCE_CLAIM = re.compile(r"(guarantee|will outperform|will beat|risk[- ]free|certain to|\d+(\.\d+)?\s*%)", re.I)


def describe_technical(bars: pd.DataFrame) -> dict:
    """Describe trailing price behaviour using only the supplied bars (no forecast)."""
    if not {"date", "close"} <= set(bars.columns):
        raise ValueError("bars must contain date and close columns")
    frame = bars.sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(frame["close"], errors="raise").astype(float)
    if len(close) < 21 or (close <= 0).any():
        raise ValueError("at least 21 positive closes are required")
    daily = close.pct_change()
    sma20 = close.rolling(20).mean().iloc[-1]
    gain = daily.clip(lower=0).rolling(14).mean().iloc[-1]
    loss = (-daily.clip(upper=0)).rolling(14).mean().iloc[-1]
    rsi = 100.0 if loss == 0 and gain > 0 else 50.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return {
        "as_of": str(pd.to_datetime(frame["date"].iloc[-1], utc=True).date()),
        "last_close": float(close.iloc[-1]),
        "return_5d": float(close.iloc[-1] / close.iloc[-6] - 1.0),
        "sma_ratio_20d": float(close.iloc[-1] / sma20 - 1.0),
        "volatility_20d": float(daily.rolling(20).std().iloc[-1]),
        "rsi_14": float(rsi),
        "trend": "above_20d_average" if close.iloc[-1] > sma20 else "below_20d_average",
        "method": "descriptive_trailing_features_v1",
    }


@dataclass(frozen=True)
class HypothesisProposal:
    title: str
    symbol: str
    thesis: str
    rationale: str
    features: tuple[str, ...]
    target: str
    benchmark: str
    evaluation: str
    evidence: tuple[dict, ...] = field(default_factory=tuple)

    def to_hypothesis_payload(self) -> dict:
        """Payload accepted by ``research.hypotheses.service.create_hypothesis``."""
        return {"title": self.title, "symbol": self.symbol, "thesis": self.thesis,
                "rationale": self.rationale, "evidence": list(self.evidence)}


def propose_hypothesis(symbol: str, findings: list[AnalystFinding], technical: dict,
                       benchmark: str = "SPY") -> HypothesisProposal:
    symbol = symbol.upper().strip()
    statements = [(f.analyst, s) for f in findings for s in f.statements]
    evidence = tuple({"citation_id": s.citation_id, "analyst": analyst, "excerpt": s.text[:300]}
                     for analyst, s in statements[:8])
    counts = {f.analyst: len(f.statements) for f in findings}
    features = ("momentum_5d", "sma_ratio_20d", "volatility_20d")
    thesis = (f"Test whether {', '.join(features)}, each known at the close of day t, predict the "
              f"next-session return of {symbol} out of sample, net of costs, against {benchmark}.")
    rationale = (f"Cited evidence available: {counts}. Trailing price context as of {technical['as_of']}: "
                 f"trend {technical['trend']}, 20-day volatility {technical['volatility_20d']:.4f}. "
                 "This is a question to test, not a prediction.")
    return HypothesisProposal(f"{symbol}: trailing momentum and volatility test", symbol, thesis, rationale,
                              features, SUPPORTED_TARGET, benchmark.upper(), EVALUATION, evidence)


@dataclass(frozen=True)
class CritiqueResult:
    passed: bool
    issues: tuple[str, ...]


def review_methodology(proposal: HypothesisProposal) -> CritiqueResult:
    issues: list[str] = []
    unknown = [f for f in proposal.features if f not in DECLARED_FEATURES]
    if unknown:
        issues.append(f"features are not declared point-in-time features: {unknown}")
    leaky = [f for f in proposal.features if any(word in f.lower() for word in _FORBIDDEN_FEATURE_WORDS)]
    if leaky:
        issues.append(f"feature names suggest future information: {leaky}")
    if not proposal.features:
        issues.append("at least one feature is required")
    if proposal.target != SUPPORTED_TARGET:
        issues.append(f"unsupported target {proposal.target!r}")
    if proposal.target in proposal.features:
        issues.append("the target must not be an input feature")
    if not proposal.benchmark or proposal.benchmark == proposal.symbol:
        issues.append("a benchmark different from the studied symbol is required")
    if proposal.evaluation != EVALUATION:
        issues.append("evaluation must be walk-forward and out of sample")
    if not proposal.evidence:
        issues.append("the proposal has no cited evidence")
    if _PERFORMANCE_CLAIM.search(proposal.thesis):
        issues.append("the thesis states a performance claim before any test")
    return CritiqueResult(not issues, tuple(issues))
