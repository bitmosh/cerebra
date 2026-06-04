"""
Ingest data models — ParseResult, NormalizedDocument, Section.

Adapters return these; the pipeline writes them to storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Section:
    """A structural section of a document (heading + content)."""

    heading: str  # heading text, empty string for H0 (no-heading) sections
    heading_path: str  # e.g. "Architecture / Components / Retrieval"
    depth: int  # 0 for H0, 1 for H1, 2 for H2, etc.
    content: str  # raw text content of this section (excluding sub-sections)
    start_line: int  # 0-based line index in source
    end_line: int  # exclusive


@dataclass
class NormalizedDocument:
    document_id: str
    source_id: str
    document_type: str  # "markdown" | "text"
    title: str | None
    sections: list[Section]
    raw_content: str  # full text of the document
    metadata: dict[str, Any] = field(default_factory=dict)
    normalization_confidence: float = 1.0
    schema_version: int = 1


@dataclass
class ParseResult:
    parse_id: str
    source_id: str
    adapter: str
    adapter_version: str
    success: bool
    confidence: float
    document: NormalizedDocument | None  # None on failure
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    extracted_metadata: dict[str, Any] = field(default_factory=dict)
