"""Multi-analyst research agents (structure adapted from financial-research-agent, MIT)."""
from finsight.research.agents.analysts import (DEFAULT_ANALYSTS, FUNDAMENTALS_ANALYST, RISK_ANALYST,
                                               AnalystFinding, KeywordAnalyst, SentimentAnalyst, Statement)
from finsight.research.agents.coordinator import MultiAnalystSynthesizer
from finsight.research.agents.hypothesis import (CritiqueResult, HypothesisProposal, describe_technical,
                                                 propose_hypothesis, review_methodology)

__all__ = ["DEFAULT_ANALYSTS", "FUNDAMENTALS_ANALYST", "RISK_ANALYST", "AnalystFinding", "KeywordAnalyst",
           "SentimentAnalyst", "Statement", "MultiAnalystSynthesizer", "CritiqueResult", "HypothesisProposal",
           "describe_technical", "propose_hypothesis", "review_methodology"]
