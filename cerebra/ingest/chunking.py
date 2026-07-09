# SPDX-License-Identifier: Apache-2.0
"""
Heading-based chunker for Cerebra.

Chunk strategy enum values (always set on every chunk):
  heading             — one heading section fits within token limit
  sliding_window      — no-heading fallback, or oversized section split by overlap windows
  code_block          — a self-contained fenced code block extracted as its own chunk
  code_block_oversized — a code block that exceeds token limit (kept whole, flagged)
  mixed_overflow      — section with mixed text+code that was split at a non-ideal boundary

Chunk ID derivation: sha256(source_id + "|" + heading_path + "|" + str(chunk_index))[:16]
Stable across re-ingests of unchanged content as long as source_id and document
structure are unchanged.

Token estimate: len(content.split()) * 1.3  (no tokenizer dependency in Phase 1)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from cerebra.ingest.models import NormalizedDocument, Section
from cerebra.sources.hashing import hash_string

CHUNKER_VERSION = "1.0.0"

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)


class ChunkStrategy(StrEnum):
    HEADING = "heading"
    SLIDING_WINDOW = "sliding_window"
    CODE_BLOCK = "code_block"
    CODE_BLOCK_OVERSIZED = "code_block_oversized"
    MIXED_OVERFLOW = "mixed_overflow"


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source_id: str
    heading_path: str
    chunk_index: int  # ordinal within the document (global, for stable ID)
    depth: int
    content: str
    content_hash: str
    token_estimate: int
    chunk_strategy: ChunkStrategy
    schema_version: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_id": self.source_id,
            "heading_path": self.heading_path,
            "chunk_index": self.chunk_index,
            "depth": self.depth,
            "content": self.content,
            "content_hash": self.content_hash,
            "token_estimate": self.token_estimate,
            "chunk_strategy": self.chunk_strategy.value,
            "lifecycle_state": "active",
            "created_at": 0,  # set by caller
            "schema_version": self.schema_version,
        }


@dataclass
class ChunkOptions:
    max_tokens: int = 512
    overlap_ratio: float = 0.20


def token_estimate(text: str) -> int:
    """Rough token estimate: word count * 1.3."""
    return max(1, int(len(text.split()) * 1.3))


def _make_chunk_id(source_id: str, heading_path: str, chunk_index: int) -> str:
    key = f"{source_id}|{heading_path}|{chunk_index}"
    return "chk_" + hash_string(key)[:16]


def chunk_document(
    doc: NormalizedDocument,
    options: ChunkOptions | None = None,
) -> list[Chunk]:
    """
    Split a NormalizedDocument into Chunks.

    Each section is split independently; global chunk_index increments
    monotonically to ensure stable IDs across the document.
    """
    opts = options or ChunkOptions()
    chunks: list[Chunk] = []
    global_index = 0

    for section in doc.sections:
        section_chunks, global_index = _chunk_section(
            section=section,
            doc=doc,
            opts=opts,
            start_index=global_index,
        )
        chunks.extend(section_chunks)

    return chunks


def _chunk_section(
    section: Section,
    doc: NormalizedDocument,
    opts: ChunkOptions,
    start_index: int,
) -> tuple[list[Chunk], int]:
    """Chunk a single section. Returns (chunks, next_global_index)."""
    content = section.content
    est = token_estimate(content)
    idx = start_index

    if est <= opts.max_tokens:
        # Section fits — single chunk, strategy = heading (or sliding_window for H0)
        strategy = (
            ChunkStrategy.SLIDING_WINDOW
            if section.depth == 0 and section.heading_path == "/"
            else ChunkStrategy.HEADING
        )
        chunk = _make_chunk(
            content=content,
            section=section,
            doc=doc,
            chunk_index=idx,
            strategy=strategy,
        )
        return [chunk], idx + 1

    # Section too large — check if it's mostly a code block
    code_chunks = _try_extract_code_blocks(content, section, doc, idx, opts)
    if code_chunks is not None:
        return code_chunks, idx + len(code_chunks)

    # Fall back to sliding window over the section
    window_chunks = _sliding_window(content, section, doc, opts, idx)
    return window_chunks, idx + len(window_chunks)


def _try_extract_code_blocks(
    content: str,
    section: Section,
    doc: NormalizedDocument,
    start_index: int,
    opts: ChunkOptions,
) -> list[Chunk] | None:
    """
    If content is dominated by code blocks, extract them as code_block chunks.
    Returns None if content doesn't fit the code-block extraction pattern.
    """
    # Find all fenced code block spans
    lines = content.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []  # (start_line, end_line) of each fence
    in_fence = False
    fence_start = 0
    fence_char = ""

    for i, line in enumerate(lines):
        stripped = line.rstrip("\n\r")
        m = _FENCE_RE.match(stripped)
        if not in_fence and m:
            in_fence = True
            fence_char = m.group(1)[0]
            fence_start = i
        elif in_fence and stripped.startswith(fence_char * 3):
            spans.append((fence_start, i + 1))
            in_fence = False

    if not spans:
        return None  # no code blocks — caller falls through to sliding window

    chunks: list[Chunk] = []
    idx = start_index
    last_end = 0

    for span_start, span_end in spans:
        # Text before this code block
        pre_text = "".join(lines[last_end:span_start])
        if pre_text.strip():
            pre_est = token_estimate(pre_text)
            strategy = (
                ChunkStrategy.HEADING
                if pre_est <= opts.max_tokens
                else ChunkStrategy.MIXED_OVERFLOW
            )
            if pre_est <= opts.max_tokens:
                chunks.append(_make_chunk(pre_text, section, doc, idx, strategy))
                idx += 1
            else:
                # Oversized pre-text: slide it
                for wc in _sliding_window_raw(pre_text, section, doc, opts, idx):
                    chunks.append(wc)
                    idx += 1

        # The code block itself
        code_text = "".join(lines[span_start:span_end])
        code_est = token_estimate(code_text)
        code_strategy = (
            ChunkStrategy.CODE_BLOCK_OVERSIZED
            if code_est > opts.max_tokens
            else ChunkStrategy.CODE_BLOCK
        )
        chunks.append(_make_chunk(code_text, section, doc, idx, code_strategy))
        idx += 1
        last_end = span_end

    # Text after last code block
    tail = "".join(lines[last_end:])
    if tail.strip():
        tail_est = token_estimate(tail)
        if tail_est <= opts.max_tokens:
            chunks.append(_make_chunk(tail, section, doc, idx, ChunkStrategy.HEADING))
            idx += 1
        else:
            for wc in _sliding_window_raw(tail, section, doc, opts, idx):
                chunks.append(wc)
                idx += 1

    return chunks if chunks else None


def _sliding_window(
    content: str,
    section: Section,
    doc: NormalizedDocument,
    opts: ChunkOptions,
    start_index: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = start_index
    for chunk in _sliding_window_raw(content, section, doc, opts, idx):
        chunks.append(chunk)
        idx += 1
    return chunks


def _sliding_window_raw(
    content: str,
    section: Section,
    doc: NormalizedDocument,
    opts: ChunkOptions,
    start_index: int,
) -> list[Chunk]:
    """Yield Chunk objects by sliding window over content."""
    words = content.split()
    if not words:
        return []

    window = opts.max_tokens
    step = max(1, int(window * (1 - opts.overlap_ratio)))
    chunks: list[Chunk] = []
    idx = start_index
    i = 0

    while i < len(words):
        window_words = words[i : i + window]
        window_text = " ".join(window_words)
        chunks.append(_make_chunk(window_text, section, doc, idx, ChunkStrategy.SLIDING_WINDOW))
        idx += 1
        i += step

    return chunks


def _make_chunk(
    content: str,
    section: Section,
    doc: NormalizedDocument,
    chunk_index: int,
    strategy: ChunkStrategy,
) -> Chunk:
    from cerebra.sources.hashing import hash_string as hs

    cid = _make_chunk_id(doc.source_id, section.heading_path, chunk_index)
    return Chunk(
        chunk_id=cid,
        document_id=doc.document_id,
        source_id=doc.source_id,
        heading_path=section.heading_path,
        chunk_index=chunk_index,
        depth=section.depth,
        content=content,
        content_hash=hs(content),
        token_estimate=token_estimate(content),
        chunk_strategy=strategy,
    )
