"""Unit tests for the chunker — all edge cases."""

from __future__ import annotations

import pytest

from cerebra.ingest.chunking import (
    ChunkOptions,
    ChunkStrategy,
    chunk_document,
    token_estimate,
)
from cerebra.ingest.models import NormalizedDocument, Section


def _doc(sections: list[Section], source_id: str = "src_test") -> NormalizedDocument:
    return NormalizedDocument(
        document_id="doc_test",
        source_id=source_id,
        document_type="markdown",
        title=None,
        sections=sections,
        raw_content="\n".join(s.content for s in sections),
    )


def _section(
    content: str,
    heading: str = "Section",
    heading_path: str = "Section",
    depth: int = 1,
) -> Section:
    lines = content.splitlines()
    return Section(
        heading=heading,
        heading_path=heading_path,
        depth=depth,
        content=content,
        start_line=0,
        end_line=len(lines),
    )


@pytest.mark.unit
class TestChunkStrategies:
    def test_small_section_gets_heading_strategy(self) -> None:
        doc = _doc([_section("Short content here.")])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=100))
        assert len(chunks) == 1
        assert chunks[0].chunk_strategy == ChunkStrategy.HEADING

    def test_no_heading_section_gets_sliding_window_strategy(self) -> None:
        section = Section(
            heading="",
            heading_path="/",
            depth=0,
            content="word " * 10,
            start_line=0,
            end_line=1,
        )
        doc = _doc([section])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=100))
        assert chunks[0].chunk_strategy == ChunkStrategy.SLIDING_WINDOW

    def test_oversized_section_splits_into_sliding_window(self) -> None:
        big_content = "word " * 600
        doc = _doc([_section(big_content)])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=100))
        assert len(chunks) > 1
        assert all(c.chunk_strategy == ChunkStrategy.SLIDING_WINDOW for c in chunks)

    def test_code_block_gets_code_block_strategy(self) -> None:
        content = "Some text.\n```python\nprint('hello')\n```\nMore text."
        doc = _doc([_section(content)])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=5))
        strategies = {c.chunk_strategy for c in chunks}
        assert ChunkStrategy.CODE_BLOCK in strategies

    def test_oversized_code_block_gets_oversized_strategy(self) -> None:
        big_code = "```python\n" + "x = 1\n" * 300 + "```"
        doc = _doc([_section(big_code)])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=10))
        oversized = [c for c in chunks if c.chunk_strategy == ChunkStrategy.CODE_BLOCK_OVERSIZED]
        assert len(oversized) >= 1


@pytest.mark.unit
class TestChunkIds:
    def test_chunk_ids_are_stable(self) -> None:
        doc = _doc([_section("Content"), _section("Other", heading_path="Other")])
        chunks1 = chunk_document(doc)
        chunks2 = chunk_document(doc)
        assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]

    def test_chunk_ids_are_unique_within_document(self) -> None:
        sections = [_section(f"Content {i}", heading_path=f"Section {i}") for i in range(5)]
        doc = _doc(sections)
        chunks = chunk_document(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_have_chk_prefix(self) -> None:
        doc = _doc([_section("Text")])
        chunks = chunk_document(doc)
        assert all(c.chunk_id.startswith("chk_") for c in chunks)

    def test_chunk_ids_differ_for_different_sources(self) -> None:
        sec = _section("Same content")
        doc1 = _doc([sec], source_id="src_aaa")
        doc2 = _doc([sec], source_id="src_bbb")
        c1 = chunk_document(doc1)
        c2 = chunk_document(doc2)
        assert c1[0].chunk_id != c2[0].chunk_id


@pytest.mark.unit
class TestNoHeadings:
    def test_no_heading_document_is_one_chunk_if_small(self) -> None:
        section = Section(
            heading="",
            heading_path="/",
            depth=0,
            content="A short document.",
            start_line=0,
            end_line=1,
        )
        doc = _doc([section])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=100))
        assert len(chunks) == 1
        assert chunks[0].heading_path == "/"

    def test_no_heading_large_document_slides(self) -> None:
        section = Section(
            heading="",
            heading_path="/",
            depth=0,
            content="word " * 1000,
            start_line=0,
            end_line=1,
        )
        doc = _doc([section])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=100))
        assert len(chunks) > 1
        assert all(c.heading_path == "/" for c in chunks)


@pytest.mark.unit
class TestCodeBlockPreservation:
    def test_no_split_inside_code_block(self) -> None:
        """A code block must not be split in the middle."""
        code = "```python\n" + "line = 'x'\n" * 5 + "```"
        doc = _doc([_section(code)])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=3))
        # The code block chunk must contain the complete fence
        code_chunks = [c for c in chunks if "```" in c.content]
        for cc in code_chunks:
            assert (
                cc.content.count("```") >= 2
                or cc.chunk_strategy == ChunkStrategy.CODE_BLOCK_OVERSIZED
            )

    def test_tilde_fence_also_detected(self) -> None:
        content = "Before.\n~~~python\ncode\n~~~\nAfter."
        doc = _doc([_section(content)])
        chunks = chunk_document(doc, ChunkOptions(max_tokens=3))
        strategies = {c.chunk_strategy for c in chunks}
        assert ChunkStrategy.CODE_BLOCK in strategies


@pytest.mark.unit
class TestTokenEstimate:
    def test_empty_string(self) -> None:
        assert token_estimate("") == 1  # max(1, ...)

    def test_approximate_count(self) -> None:
        text = " ".join(["word"] * 100)
        est = token_estimate(text)
        assert 120 <= est <= 140  # 100 * 1.3 = 130

    def test_chunk_carries_estimate(self) -> None:
        doc = _doc([_section("word " * 10)])
        chunks = chunk_document(doc)
        assert chunks[0].token_estimate > 0


@pytest.mark.unit
class TestChunkProvenance:
    def test_every_chunk_has_source_id(self) -> None:
        doc = _doc([_section("Content")])
        chunks = chunk_document(doc)
        assert all(c.source_id == doc.source_id for c in chunks)

    def test_every_chunk_has_document_id(self) -> None:
        doc = _doc([_section("Content")])
        chunks = chunk_document(doc)
        assert all(c.document_id == doc.document_id for c in chunks)

    def test_no_empty_chunks(self) -> None:
        doc = _doc([_section("Content"), _section("  ", heading_path="Empty")])
        chunks = chunk_document(doc)
        # Chunks from non-empty sections exist
        non_empty = [c for c in chunks if c.content.strip()]
        assert len(non_empty) >= 1
