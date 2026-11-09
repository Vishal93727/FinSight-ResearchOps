"""Evidence-bound specialist analysts for the multi-analyst research workflow.

The team structure (fundamentals / risk / sentiment specialists feeding a coordinator) is
adapted from ``Harshithaaramesh/financial-research-agent`` (MIT). Unlike that reference, the
analysts here never see free text outside the retrieved evidence, never call an LLM, and may
only emit a statement that quotes a sentence from a retrieved chunk together with that
chunk's citation ID. Statements therefore stay checkable by ``evaluate_claim_support``.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from finsight.documents.retrieval import RetrievedEvidence
from finsight.models.sentiment import score_financial_sentiment

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_TOKEN = re.compile(r"[a-z0-9&]+")
MIN_SENTENCE_CHARS = 20
MAX_SENTENCE_CHARS = 400


@dataclass(frozen=True)
class Statement:
    text: str
    citation_id: str


@dataclass(frozen=True)
class AnalystFinding:
    analyst: str
    heading: str
    statements: tuple[Statement, ...]
    gaps: tuple[str, ...] = ()


def evidence_sentences(item: RetrievedEvidence) -> list[str]:
    """Split one evidence chunk into bounded, whitespace-normalised sentences."""
    text = " ".join(item.text.split())
    return [s.strip() for s in _SENTENCE_SPLIT.split(text)
            if MIN_SENTENCE_CHARS <= len(s.strip()) <= MAX_SENTENCE_CHARS]


def _hits(sentence: str, stems: tuple[str, ...]) -> int:
    tokens = _TOKEN.findall(sentence.lower())
    return sum(1 for token in tokens if any(token.startswith(stem) for stem in stems))


@dataclass(frozen=True)
class KeywordAnalyst:
    """Select the evidence sentences that best match a specialist's vocabulary."""

    name: str
    heading: str
    stems: tuple[str, ...]
    max_statements: int = 4

    def analyze(self, evidence: list[RetrievedEvidence]) -> AnalystFinding:
        scored: list[tuple[int, float, int, str, str]] = []
        order = 0
        for item in evidence:
            for sentence in evidence_sentences(item):
                hits = _hits(sentence, self.stems)
                if hits:
                    scored.append((hits, item.combined_score, -order, sentence, item.citation_id))
                order += 1
        scored.sort(reverse=True)
        chosen: list[Statement] = []
        seen: set[str] = set()
        for _, _, _, sentence, citation_id in scored:
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            chosen.append(Statement(sentence, citation_id))
            if len(chosen) == self.max_statements:
                break
        gaps = () if chosen else (f"no {self.name} evidence was found in the retrieved sources",)
        return AnalystFinding(self.name, self.heading, tuple(chosen), gaps)


FUNDAMENTALS_ANALYST = KeywordAnalyst(
    "fundamentals", "Fundamentals",
    ("revenue", "sales", "profit", "income", "margin", "earning", "eps", "cash", "growth",
     "guidance", "ebitda", "debt", "dividend"))

RISK_ANALYST = KeywordAnalyst(
    "risk", "Risks",
    ("risk", "adverse", "uncertain", "litigation", "lawsuit", "regulat", "decline", "volatil",
     "competition", "competitor", "cyber", "default", "impair", "shortage", "disrupt"))


@dataclass(frozen=True)
class SentimentAnalyst:
    """Report the most strongly toned evidence sentences using the lexicon baseline.

    Each statement quotes the source sentence and prefixes the tone label, so the
    citation screen compares real source text, not a paraphrase.
    """

    name: str = "sentiment"
    heading: str = "Sentiment"
    max_statements: int = 3

    def analyze(self, evidence: list[RetrievedEvidence]) -> AnalystFinding:
        scored: list[tuple[float, float, int, str, str, str]] = []
        order = 0
        for item in evidence:
            for sentence in evidence_sentences(item):
                result = score_financial_sentiment(sentence)
                if result["label"] != "NEUTRAL":
                    scored.append((abs(result["score"]), item.combined_score, -order, sentence,
                                   item.citation_id, result["label"]))
                order += 1
        scored.sort(reverse=True)
        statements = tuple(Statement(f"{label.title()} tone: {sentence}", cid)
                           for _, _, _, sentence, cid, label in scored[: self.max_statements])
        gaps = () if statements else ("no clearly toned sentences were found in the retrieved sources",)
        return AnalystFinding(self.name, self.heading, statements, gaps)


DEFAULT_ANALYSTS = (FUNDAMENTALS_ANALYST, RISK_ANALYST, SentimentAnalyst())
