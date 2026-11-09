"""Deterministic section-aware chunking with bounded overlap."""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    token_count: int
    section: str | None = None


def chunk_text(text: str, chunk_size: int = 420, overlap: int = 60) -> list[TextChunk]:
    if chunk_size < 50 or chunk_size > 2000:
        raise ValueError("chunk_size must be between 50 and 2000 tokens")
    if overlap < 0 or overlap >= chunk_size // 2:
        raise ValueError("overlap must be non-negative and less than half the chunk size")
    # Preserve headings as metadata while preventing very long paragraphs from bypassing bounds.
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current: list[str] = []
    for paragraph in paragraphs:
        is_heading = len(paragraph) <= 120 and (paragraph.startswith("#") or paragraph.isupper())
        if is_heading and current:
            sections.append((current_heading, current)); current = []
        if is_heading:
            current_heading = paragraph.lstrip("# ").strip()
        else:
            current.append(paragraph)
    if current:
        sections.append((current_heading, current))
    tokens_with_sections: list[tuple[str, str | None]] = []
    for heading, section_paragraphs in sections:
        for paragraph in section_paragraphs:
            for token in paragraph.split():
                tokens_with_sections.append((token, heading))
    if not tokens_with_sections:
        return []
    step = chunk_size - overlap
    output: list[TextChunk] = []
    for start in range(0, len(tokens_with_sections), step):
        block = tokens_with_sections[start:start + chunk_size]
        if not block:
            break
        output.append(TextChunk(index=len(output), text=" ".join(t for t, _ in block),
                                token_count=len(block), section=next((s for _, s in block if s), None)))
        if start + chunk_size >= len(tokens_with_sections):
            break
    return output
