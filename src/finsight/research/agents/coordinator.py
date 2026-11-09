"""Coordinator that merges analyst findings into one citation-bound memo.

It implements the ``ResearchSynthesizer`` protocol, so the existing workflow still runs
citation-linkage checks, claim-support screening, checkpointing and mandatory human review
on its output. The coordinator adds no new factual sentence of its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from finsight.documents.retrieval import RetrievedEvidence
from finsight.research.agents.analysts import DEFAULT_ANALYSTS, AnalystFinding


@dataclass(frozen=True)
class MultiAnalystSynthesizer:
    analysts: tuple = field(default=DEFAULT_ANALYSTS)

    def findings(self, evidence: list[RetrievedEvidence]) -> list[AnalystFinding]:
        return [analyst.analyze(evidence) for analyst in self.analysts]

    def synthesize(self, query: str, evidence: list[RetrievedEvidence]) -> str:
        if not evidence:
            return ("No sufficiently relevant evidence was found in the ingested research library. "
                    "Do not infer a financial conclusion from missing evidence.")
        lines = [f"Evidence summary for: {query.strip()}", ""]
        gaps: list[str] = []
        for finding in self.findings(evidence):
            lines.append(f"## {finding.heading}")
            for statement in finding.statements:
                lines.append(f"- {statement.text} [{statement.citation_id}]")
            gaps.extend(f"{finding.analyst}: {gap}" for gap in finding.gaps)
            lines.append("")
        if gaps:
            lines.append("This output is incomplete: " + "; ".join(gaps) + ".")
        lines.append("This is an extractive research summary, not an investment recommendation.")
        return "\n".join(lines)
