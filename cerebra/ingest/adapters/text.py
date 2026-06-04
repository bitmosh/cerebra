"""
Plain text parser adapter.

No structural parsing — treats entire document as a single H0 section.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from cerebra.ingest.adapters.base import ParserAdapter
from cerebra.ingest.models import NormalizedDocument, ParseResult, Section

PARSER_VERSION = "1.0.0"


class TextAdapter(ParserAdapter):
    name = "text"
    version = PARSER_VERSION

    def parse(self, source_id: str, path: Path) -> ParseResult:
        parse_id = f"parse_{uuid.uuid4().hex[:12]}"
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ParseResult(
                parse_id=parse_id,
                source_id=source_id,
                adapter=self.name,
                adapter_version=self.version,
                success=False,
                confidence=0.0,
                document=None,
                errors=[str(e)],
            )

        lines = raw.splitlines()
        section = Section(
            heading="",
            heading_path="/",
            depth=0,
            content=raw,
            start_line=0,
            end_line=len(lines),
        )
        metadata: dict[str, object] = {"line_count": len(lines)}
        doc = NormalizedDocument(
            document_id=doc_id,
            source_id=source_id,
            document_type="text",
            title=None,
            sections=[section],
            raw_content=raw,
            metadata=metadata,
            normalization_confidence=0.90,
        )
        return ParseResult(
            parse_id=parse_id,
            source_id=source_id,
            adapter=self.name,
            adapter_version=self.version,
            success=True,
            confidence=0.90,
            document=doc,
            extracted_metadata=metadata,
        )
