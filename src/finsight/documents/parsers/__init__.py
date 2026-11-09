"""Safe, bounded parsers for research document uploads."""
from __future__ import annotations
import csv
import io
import json
from html.parser import HTMLParser
from pathlib import PurePath
from typing import Any


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        elif tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag.lower() in {"p", "div", "li", "tr", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _flatten_json(value: Any, prefix: str = "") -> list[str]:
    rows: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_flatten_json(child, f"{prefix}{key}."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_flatten_json(child, f"{prefix}[{index}]."))
    else:
        rows.append(f"{prefix.rstrip('.')} : {value}")
    return rows


def parse_document(filename: str, media_type: str | None, content: bytes) -> tuple[str, dict]:
    """Parse an allow-listed format. Never execute macros, HTML scripts or embedded code."""
    suffix = PurePath(filename).suffix.lower()
    detected = (media_type or "").lower()
    metadata: dict[str, Any] = {"parser": "finsight-safe-parser-v1", "extension": suffix}
    try:
        if suffix in {".txt", ".md", ".markdown"}:
            text = content.decode("utf-8-sig")
        elif suffix == ".csv":
            decoded = content.decode("utf-8-sig")
            rows = list(csv.reader(io.StringIO(decoded)))
            text = "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
            metadata["row_count"] = max(0, len(rows) - 1)
        elif suffix == ".json":
            value = json.loads(content.decode("utf-8-sig"))
            text = "\n".join(_flatten_json(value))
        elif suffix in {".html", ".htm"}:
            parser = _TextHTMLParser()
            parser.feed(content.decode("utf-8-sig", errors="replace"))
            text = " ".join(" ".join(parser.parts).split())
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise ValueError("PDF parsing requires the optional 'pdf' dependency") from exc
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are not accepted")
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                pages.append(f"[Page {number}]\n{page.extract_text() or ''}")
            text = "\n\n".join(pages)
            metadata["page_count"] = len(reader.pages)
        else:
            raise ValueError("Supported formats: TXT, Markdown, CSV, JSON, HTML and PDF")
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise ValueError("Document contents could not be decoded or parsed") from exc
    normalized = "\n".join(line.strip() for line in text.replace("\x00", "").splitlines() if line.strip())
    if not normalized:
        raise ValueError("Document contains no extractable text")
    metadata["declared_media_type"] = detected[:120]
    return normalized, metadata
