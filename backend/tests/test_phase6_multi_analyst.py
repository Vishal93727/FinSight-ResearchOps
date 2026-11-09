"""Multi-analyst research agents: evidence binding, workflow compatibility and hypothesis checks."""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from finsight.core.config import Settings
from finsight.documents.retrieval import RetrievedEvidence
from finsight.research.agents import (DEFAULT_ANALYSTS, MultiAnalystSynthesizer, describe_technical,
                                      propose_hypothesis, review_methodology)
from finsight.research.agents.analysts import evidence_sentences
from finsight.research.graphs.workflow import build_evidence_report, get_research_synthesizer

TEXTS = [
    "Revenue grew 12 percent year over year, driven by cloud demand and subscription renewals. "
    "Operating margin improved as the company controlled operating expenses.",
    "Management expects demand to remain strong, but guidance assumes stable enterprise spending. "
    "A decline in enterprise spending would hurt revenue and margin.",
    "The company faces risk from increased competition and from changes in regulation. "
    "Supply constraints could reduce growth in hardware revenue.",
]


def _evidence(texts=TEXTS) -> list[RetrievedEvidence]:
    return [RetrievedEvidence(citation_id=f"E{i}", chunk_id=f"c{i}", document_id="d1", title="Filing",
                              filename="f.txt", chunk_index=i, text=text, text_sha256=f"h{i}",
                              lexical_score=0.5, vector_score=0.5, combined_score=1.0 - i / 10, embedding=[])
            for i, text in enumerate(texts, start=1)]


def _bars(n: int = 60) -> pd.DataFrame:
    close = 100 + np.cumsum(np.random.default_rng(3).normal(0.1, 1.0, n))
    return pd.DataFrame({"date": pd.bdate_range("2024-01-02", periods=n, tz="UTC"), "close": close})


def test_every_statement_is_a_verbatim_sentence_with_its_own_citation():
    evidence = _evidence()
    sentences_by_id = {item.citation_id: evidence_sentences(item) for item in evidence}
    for analyst in DEFAULT_ANALYSTS:
        finding = analyst.analyze(evidence)
        assert finding.statements, analyst.name
        for statement in finding.statements:
            source = sentences_by_id[statement.citation_id]
            assert any(sentence in statement.text for sentence in source)


def test_memo_passes_the_existing_citation_and_claim_checks_and_stops_for_human_review():
    report = build_evidence_report("What drives revenue and what are the main risks?", _evidence(),
                                   MultiAnalystSynthesizer())
    assert report["evidence_verified"] is True
    assert report["claim_checks"]["passed"] is True
    assert report["status"] == "AWAITING_REVIEW"
    for heading in ("## Fundamentals", "## Risks", "## Sentiment"):
        assert heading in report["answer"]
    assert "not an investment recommendation" in report["answer"]


def test_missing_evidence_is_blocked_not_summarised():
    report = build_evidence_report("What drives revenue and what are the main risks?", [],
                                   MultiAnalystSynthesizer())
    assert report["status"] == "NO_EVIDENCE"
    assert report["evidence_verified"] is False


def test_gaps_are_reported_without_inventing_content():
    only_growth = _evidence(["Revenue grew 12 percent year over year, driven by cloud demand."])
    memo = MultiAnalystSynthesizer().synthesize("How is revenue developing?", only_growth)
    assert "This output is incomplete" in memo
    assert "risk: no risk evidence was found" in memo
    report = build_evidence_report("How is revenue developing?", only_growth, MultiAnalystSynthesizer())
    assert report["evidence_verified"] is True


def test_provider_name_and_settings_accept_multi_analyst():
    assert isinstance(get_research_synthesizer("multi_analyst"), MultiAnalystSynthesizer)
    assert Settings(research_synthesis_provider="multi_analyst").research_synthesis_provider == "multi_analyst"
    with pytest.raises(ValueError):
        get_research_synthesizer("unknown")


def test_technical_description_needs_enough_history_and_is_descriptive_only():
    with pytest.raises(ValueError):
        describe_technical(_bars(10))
    summary = describe_technical(_bars())
    assert summary["method"] == "descriptive_trailing_features_v1"
    assert summary["trend"] in {"above_20d_average", "below_20d_average"}
    assert 0.0 <= summary["rsi_14"] <= 100.0


def _proposal():
    findings = [analyst.analyze(_evidence()) for analyst in DEFAULT_ANALYSTS]
    return propose_hypothesis("msft", findings, describe_technical(_bars()))


def test_generated_proposal_is_evidence_linked_testable_and_passes_the_critic():
    proposal = _proposal()
    assert proposal.symbol == "MSFT" and proposal.evidence
    assert review_methodology(proposal).passed
    payload = proposal.to_hypothesis_payload()
    assert set(payload) == {"title", "symbol", "thesis", "rationale", "evidence"}


@pytest.mark.parametrize("change,fragment", [
    ({"features": ("momentum_5d", "target_next_day_return")}, "not declared"),
    ({"features": ("forward_return",)}, "future information"),
    ({"benchmark": "MSFT"}, "benchmark"),
    ({"evaluation": "in_sample"}, "walk-forward"),
    ({"evidence": ()}, "no cited evidence"),
    ({"thesis": "This will outperform the market by 12%."}, "performance claim"),
])
def test_methodology_critic_rejects_unsound_proposals(change, fragment):
    result = review_methodology(dataclasses.replace(_proposal(), **change))
    assert not result.passed
    assert any(fragment in issue for issue in result.issues)
