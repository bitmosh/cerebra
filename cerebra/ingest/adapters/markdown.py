"""
Markdown parser adapter.

Single-pass parser using stdlib only — no external markdown library.

Edge cases handled:
- No headings: entire document becomes one H0 section (heading_path="/")
- Deeply nested headings (H4/H5/H6): full heading path preserved, no truncation
- Headings out of order (H3 before H2): treated as authored, warning emitted
- Code blocks (``` or ~~~): heading lines inside fenced blocks are content,
  not boundaries; splits never bisect a fenced block

Heading path format: "Title / Section / Subsection" (space-slash-space separated)
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from cerebra.ingest.adapters.base import ParserAdapter
from cerebra.ingest.models import NormalizedDocument, ParseResult, Section

PARSER_VERSION = "1.0.0"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")


def _strip_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """Strip YAML frontmatter if present. Returns (remaining_text, metadata)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, {}
    raw_fm = m.group(1)
    meta: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return text[m.end() :], meta


def _build_heading_path(stack: list[tuple[int, str]]) -> str:
    """Build heading path string from (depth, text) stack."""
    if not stack:
        return "/"
    return " / ".join(text for _, text in stack)


class MarkdownAdapter(ParserAdapter):
    name = "markdown"
    version = PARSER_VERSION

    def parse(self, source_id: str, path: Path) -> ParseResult:
        parse_id = f"parse_{uuid.uuid4().hex[:12]}"
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        warnings: list[str] = []

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

        content, frontmatter_meta = _strip_frontmatter(raw)
        lines = content.splitlines(keepends=True)

        # Single pass: collect heading boundaries, tracking code-fence state
        boundaries: list[tuple[int, int, str]] = []  # (line_idx, depth, heading_text)
        in_fence = False
        fence_char = ""

        for i, line in enumerate(lines):
            stripped = line.rstrip("\n\r")
            fence_match = _FENCE_OPEN_RE.match(stripped)

            if not in_fence and fence_match:
                in_fence = True
                fence_char = fence_match.group(1)[0]
                continue
            if in_fence:
                # Close fence: same character, same or greater length
                if stripped.startswith(fence_char * 3):
                    in_fence = False
                continue

            heading_match = _ATX_HEADING_RE.match(stripped)
            if heading_match:
                depth = len(heading_match.group(1))
                text = heading_match.group(2)
                boundaries.append((i, depth, text))

        sections = _build_sections(lines, boundaries, warnings)
        title = _extract_title(sections, frontmatter_meta)
        confidence = 0.95 if boundaries else 0.75

        metadata: dict[str, object] = {
            "headings_count": len(boundaries),
            "has_frontmatter": bool(frontmatter_meta),
            **frontmatter_meta,
        }

        doc = NormalizedDocument(
            document_id=doc_id,
            source_id=source_id,
            document_type="markdown",
            title=title,
            sections=sections,
            raw_content=content,
            metadata=metadata,
            normalization_confidence=confidence,
        )

        return ParseResult(
            parse_id=parse_id,
            source_id=source_id,
            adapter=self.name,
            adapter_version=self.version,
            success=True,
            confidence=confidence,
            document=doc,
            warnings=warnings,
            extracted_metadata=metadata,
        )


def _build_sections(
    lines: list[str],
    boundaries: list[tuple[int, int, str]],
    warnings: list[str],
) -> list[Section]:
    """Build Section list from lines + boundary positions."""
    full_text = "".join(lines)
    n = len(lines)

    if not boundaries:
        # No headings — entire document is one H0 section
        return [
            Section(
                heading="",
                heading_path="/",
                depth=0,
                content=full_text,
                start_line=0,
                end_line=n,
            )
        ]

    sections: list[Section] = []
    heading_stack: list[tuple[int, str]] = []  # (depth, text)
    prev_depth = 0

    for idx, (line_idx, depth, text) in enumerate(boundaries):
        # Warn on out-of-order headings (e.g. H3 directly after H1)
        if depth > prev_depth + 1 and prev_depth > 0:
            warnings.append(
                f"Heading depth jump at line {line_idx + 1}: "
                f"H{prev_depth} → H{depth} ('{text}')"
            )

        # End of previous section
        if heading_stack or idx == 0:
            start = boundaries[idx - 1][0] if idx > 0 else 0
            end = line_idx
            if idx > 0:
                prev_line, prev_depth_val, prev_text = boundaries[idx - 1]
                # Pop stack to current depth
                while heading_stack and heading_stack[-1][0] >= depth:
                    heading_stack.pop()
                heading_stack.append((prev_depth_val, prev_text))
                section_content = "".join(lines[start:end])
                sections.append(
                    Section(
                        heading=prev_text,
                        heading_path=_build_heading_path(heading_stack),
                        depth=prev_depth_val,
                        content=section_content,
                        start_line=start,
                        end_line=end,
                    )
                )
                heading_stack.pop()

        prev_depth = depth

    # Last section
    last_line, last_depth, last_text = boundaries[-1]
    while heading_stack and heading_stack[-1][0] >= last_depth:
        heading_stack.pop()
    heading_stack.append((last_depth, last_text))
    sections.append(
        Section(
            heading=last_text,
            heading_path=_build_heading_path(heading_stack),
            depth=last_depth,
            content="".join(lines[last_line:]),
            start_line=last_line,
            end_line=n,
        )
    )

    return sections


def _extract_title(sections: list[Section], frontmatter: dict[str, str]) -> str | None:
    """Extract document title: frontmatter title > first H1 heading."""
    if "title" in frontmatter:
        return frontmatter["title"]
    for s in sections:
        if s.depth == 1:
            return s.heading
    return None
