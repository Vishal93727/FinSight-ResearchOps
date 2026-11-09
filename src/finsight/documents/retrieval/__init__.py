"""Hybrid lexical/vector retrieval and strict evidence citation validation."""
from __future__ import annotations
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Protocol
from finsight.documents.embeddings import EmbeddingProvider, FeatureHashEmbeddingProvider, cosine_similarity

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.'%-]+", re.I)


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: str
    document_id: str
    document_title: str
    filename: str
    chunk_index: int
    text: str
    text_sha256: str
    embedding: list[float]


class CrossEncoderReranker(Protocol):
    name: str
    model_name: str

    def score(self, query: str, texts: list[str]) -> list[float]: ...


class SentenceTransformerCrossEncoder:
    """Optional CPU cross-encoder reranker. Model weights are loaded lazily by the library."""

    name = "sentence_transformers_cross_encoder"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Cross-encoder reranking requires the optional 'semantic' extra") from exc
        try:
            self._model = CrossEncoder(model_name, device="cpu")
        except Exception as exc:
            raise RuntimeError(f"Could not load cross-encoder model {model_name!r}") from exc

    def score(self, query: str, texts: list[str]) -> list[float]:
        values = self._model.predict([(query, text) for text in texts], show_progress_bar=False)
        return [float(value) for value in values]


def get_reranker(provider_name: str = "none", model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    if provider_name == "none":
        return None
    if provider_name == "cross_encoder":
        return SentenceTransformerCrossEncoder(model_name)
    raise ValueError(f"Unsupported document reranker: {provider_name}")


@dataclass(frozen=True)
class RetrievedEvidence:
    citation_id: str
    chunk_id: str
    document_id: str
    title: str
    filename: str
    chunk_index: int
    text: str
    text_sha256: str
    lexical_score: float
    vector_score: float
    combined_score: float
    embedding: list[float]
    rerank_score: float | None = None


def _lexical_score(query_tokens: list[str], text: str) -> float:
    words = Counter(token.lower() for token in WORD_RE.findall(text))
    if not query_tokens:
        return 0.0
    matched = sum(1 for token in set(query_tokens) if words[token])
    coverage = matched / max(1, len(set(query_tokens)))
    saturation = sum(math.log1p(words[token]) for token in set(query_tokens) if words[token])
    return min(1.0, coverage * 0.75 + saturation / (len(set(query_tokens)) * 5.0))


def hybrid_retrieve(query: str, candidates: Iterable[RetrievalCandidate], top_k: int = 6,
                    lexical_weight: float = 0.45, diversity_weight: float = 0.15,
                    embedding_provider: EmbeddingProvider | None = None,
                    reranker: CrossEncoderReranker | None = None) -> list[RetrievedEvidence]:
    if not query.strip():
        raise ValueError("query cannot be empty")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")
    if not 0 <= lexical_weight <= 1:
        raise ValueError("lexical_weight must be between 0 and 1")
    if not 0 <= diversity_weight <= 0.5:
        raise ValueError("diversity_weight must be between 0 and 0.5")
    query_tokens = [token.lower() for token in WORD_RE.findall(query)]
    candidate_list = list(candidates)
    dimensions = len(candidate_list[0].embedding) if candidate_list else 384
    provider = embedding_provider or FeatureHashEmbeddingProvider(dimensions)
    query_vector = provider.embed(query)
    if candidate_list and any(len(item.embedding) != len(query_vector) for item in candidate_list):
        raise ValueError("Stored document embeddings do not match the configured query embedding model")
    ranked = []
    for item in candidate_list:
        lexical = _lexical_score(query_tokens, item.text)
        vector = max(0.0, cosine_similarity(query_vector, item.embedding))
        combined = lexical_weight * lexical + (1.0 - lexical_weight) * vector
        if combined > 0:
            ranked.append((combined, lexical, vector, item))
    ranked.sort(key=lambda row: (-row[0], row[3].document_id, row[3].chunk_index))
    # Maximal marginal relevance selects a small diverse shortlist after hybrid scoring.
    shortlist = ranked[:min(len(ranked), max(top_k * 8, top_k))]
    if reranker is not None and shortlist:
        rerank_scores = reranker.score(query, [row[3].text for row in shortlist])
        if len(rerank_scores) != len(shortlist) or any(not math.isfinite(value) for value in rerank_scores):
            raise ValueError("Cross-encoder returned an invalid score vector")
        low, high = min(rerank_scores), max(rerank_scores)
        span = high - low
        normalized = [(value - low) / span if span > 1e-12 else 1.0 for value in rerank_scores]
        shortlist = [(*row[:3], row[3], float(score)) for row, score in zip(shortlist, normalized)]
        shortlist.sort(key=lambda row: (-(0.25 * row[0] + 0.75 * row[4]), row[3].document_id, row[3].chunk_index))
    else:
        shortlist = [(*row, row[0]) for row in shortlist]
    selected = []
    remaining = list(shortlist)
    relevance_weight = 1.0 - diversity_weight
    while remaining and len(selected) < top_k:
        def mmr_value(row):
            redundancy = max((max(0.0, cosine_similarity(row[3].embedding, chosen[3].embedding))
                              for chosen in selected), default=0.0)
            relevance = 0.25 * row[0] + 0.75 * row[4] if reranker is not None else row[0]
            return relevance_weight * relevance - diversity_weight * redundancy
        best = max(remaining, key=mmr_value)
        selected.append(best)
        remaining.remove(best)
    output = []
    for rank, row in enumerate(selected, start=1):
        combined, lexical, vector, item = row[:4]
        output.append(RetrievedEvidence(citation_id=f"E{rank}", chunk_id=item.chunk_id,
            document_id=item.document_id, title=item.document_title, filename=item.filename,
            chunk_index=item.chunk_index, text=item.text, text_sha256=item.text_sha256,
            lexical_score=round(lexical, 6), vector_score=round(vector, 6),
            combined_score=round(combined, 6), embedding=item.embedding,
            rerank_score=round(row[4], 6) if reranker is not None else None))
    return output


def verify_citations(answer: str, citations: list[dict]) -> bool:
    """Verify citation-ID linkage, not semantic entailment or factual truth."""
    if not citations:
        return False
    allowed = {str(item.get("citation_id")) for item in citations if item.get("citation_id")}
    referenced = set(re.findall(r"\[(E\d+)\]", answer))
    return bool(referenced) and referenced.issubset(allowed)


_CLAIM_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "by", "with",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "it", "its", "we", "our", "their", "they", "company", "reported",
}
_IGNORED_RESEARCH_LINES = (
    "evidence summary for:", "this is an extractive research summary", "this output is",
    "this is a research summary", "this report is not", "not an investment recommendation",
    "no investment recommendation", "no sufficiently relevant evidence was found",
)


def evaluate_claim_support(answer: str, citations: list[dict], min_token_overlap: float = 0.20) -> dict:
    """Conservatively check every factual sentence against its adjacent cited excerpt.

    This deterministic lexical/numeric screen is deliberately not described as semantic
    entailment. Short factual sentences are checked too, so a compact statement such as
    ``Revenue rose 18%. [E1]`` cannot bypass review merely because it is short. When more
    than one sentence appears on a line, citations remain attached to the sentence they
    immediately follow instead of being shared across the entire line.
    """
    if not 0.0 < min_token_overlap <= 1.0:
        raise ValueError("min_token_overlap must be between 0 and 1")
    allowed = {str(item.get("citation_id")): item for item in citations if item.get("citation_id")}
    source_text = {key: str(value.get("excerpt", value.get("text", ""))) for key, value in allowed.items()}
    claims: list[dict] = []

    for raw_line in answer.splitlines() or [answer]:
        line = raw_line.strip().lstrip(" -*\t#").strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith(_IGNORED_RESEARCH_LINES):
            continue
        # Split sentences, then attach citation markers that follow punctuation to the
        # preceding sentence. This keeps adjacent claims from borrowing one another's
        # source IDs when an LLM formats multiple sentences on one line.
        raw_parts = re.split(r"(?<=[.!?])\s+", line)
        sentences: list[str] = []
        for part in raw_parts:
            leading_refs = re.match(r"^((?:\[E\d+\]\s*)+)(.*)$", part.strip())
            if leading_refs and sentences:
                sentences[-1] = (sentences[-1].rstrip() + " " + leading_refs.group(1).strip()).strip()
                if leading_refs.group(2).strip():
                    sentences.append(leading_refs.group(2).strip())
            else:
                sentences.append(part)
        for raw_sentence in sentences:
            sentence = raw_sentence.strip()
            if not sentence or sentence.lower().startswith(_IGNORED_RESEARCH_LINES):
                continue
            refs = set(re.findall(r"\[(E\d+)\]", sentence))
            claim_text = re.sub(r"\[(E\d+)\]", "", sentence).strip(" .:-\t")
            tokens = {token.lower() for token in WORD_RE.findall(claim_text)
                      if token.lower() not in _CLAIM_STOPWORDS}
            numeric = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", claim_text))
            # Ignore headings/labels and genuinely non-factual fragments, not short claims.
            if len(tokens) < 2 and not numeric:
                continue
            if not refs or not refs.issubset(allowed):
                claims.append({"claim": claim_text[:500], "status": "UNSUPPORTED",
                    "reason": "missing_or_unknown_citation", "citation_ids": sorted(refs),
                    "numeric_tokens": sorted(numeric)})
                continue

            best_overlap = 0.0
            best_citation = None
            supported_by_one_source = False
            for ref in sorted(refs):
                source = source_text[ref]
                source_tokens = {token.lower() for token in WORD_RE.findall(source)
                                 if token.lower() not in _CLAIM_STOPWORDS}
                overlap = len(tokens & source_tokens) / max(1, len(tokens))
                source_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", source))
                if overlap > best_overlap:
                    best_overlap, best_citation = overlap, ref
                if numeric.issubset(source_numbers) and overlap >= min_token_overlap:
                    supported_by_one_source = True
                    best_citation = ref
                    best_overlap = max(best_overlap, overlap)
            passed = supported_by_one_source
            claims.append({"claim": claim_text[:500], "status": "SUPPORTED" if passed else "REVIEW",
                "reason": "lexical_and_numeric_support" if passed else (
                    "numeric_value_not_found" if numeric else "low_source_overlap"),
                "best_citation_id": best_citation, "token_overlap": round(best_overlap, 4),
                "numeric_tokens": sorted(numeric)})

    has_claims = bool(claims)
    supported_count = sum(item["status"] == "SUPPORTED" for item in claims)
    return {
        "passed": bool(has_claims and supported_count == len(claims)),
        "claim_count": len(claims),
        "supported_count": supported_count,
        "checks": claims,
        "method": "lexical_numeric_screen_v2",
        "note": "This deterministic screen is not semantic entailment or factuality proof; independent human review is still required.",
    }
