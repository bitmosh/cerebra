"""Unit tests for the Markdown parser adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.ingest.adapters.markdown import MarkdownAdapter


@pytest.fixture
def adapter() -> MarkdownAdapter:
    return MarkdownAdapter()


@pytest.mark.unit
class TestMarkdownAdapter:
    def test_parses_simple_document(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome content.\n")
        result = adapter.parse("src_1", f)
        assert result.success
        assert result.document is not None
        assert result.document.title == "Title"

    def test_heading_path_preserved(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Top\n\nContent.\n\n## Sub\n\nSub content.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        paths = [s.heading_path for s in result.document.sections]
        assert any("Sub" in p for p in paths)

    def test_no_headings_produces_h0_section(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Just some plain text.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        assert len(result.document.sections) == 1
        assert result.document.sections[0].heading_path == "/"
        assert result.document.sections[0].depth == 0

    def test_frontmatter_extracted(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("---\ntitle: My Doc\nauthor: Test\n---\n\n# Heading\n\nContent.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        assert result.document.title == "My Doc"
        assert result.extracted_metadata.get("author") == "Test"

    def test_code_block_heading_not_parsed_as_boundary(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Real heading\n\n```\n# not a heading\n```\n\nAfter.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        # Only 1 real heading section (the code block heading is not counted)
        heading_sections = [s for s in result.document.sections if s.depth > 0]
        assert len(heading_sections) == 1

    def test_out_of_order_headings_produces_warning(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Top\n\n### Jumped\n\nContent.\n")
        result = adapter.parse("src_1", f)
        assert result.warnings  # at least one warning for depth jump

    def test_tilde_fence_also_ignored(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Outer\n\n~~~\n# inner\n~~~\n\nText.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        headings = [s for s in result.document.sections if s.depth > 0]
        assert len(headings) == 1

    def test_deeply_nested_heading_path(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# H1\n## H2\n### H3\n#### H4\n\nContent.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        paths = [s.heading_path for s in result.document.sections]
        assert any("H4" in p for p in paths)

    def test_missing_file_returns_failure(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        result = adapter.parse("src_1", tmp_path / "nonexistent.md")
        assert not result.success
        assert result.errors

    def test_parse_id_unique(self, adapter: MarkdownAdapter, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# A\n")
        r1 = adapter.parse("src_1", f)
        r2 = adapter.parse("src_1", f)
        assert r1.parse_id != r2.parse_id


@pytest.mark.unit
class TestBuildSections:
    """Regression tests for _build_sections — verifies the multi-section fix."""

    def test_multi_section_produces_correct_count(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "# Title\n\n## One\n\nContent.\n\n## Two\n\nContent.\n\n## Three\n\nContent.\n"
        )
        result = adapter.parse("src_1", f)
        assert result.document is not None
        assert len(result.document.sections) == 4  # H1 + 3 H2s

    def test_section_content_does_not_bleed_into_next(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# A\n\nOnly A content.\n\n# B\n\nOnly B content.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        sections = result.document.sections
        assert len(sections) == 2
        assert "Only A content." in sections[0].content
        assert "Only A content." not in sections[1].content
        assert "Only B content." in sections[1].content
        assert "Only B content." not in sections[0].content

    def test_h1_h2_h3_heading_path_hierarchy(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Root\n\n## Child\n\n### Grandchild\n\nDeep.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        paths = [s.heading_path for s in result.document.sections]
        assert "Root" in paths
        assert "Root / Child" in paths
        assert "Root / Child / Grandchild" in paths

    def test_h2_at_same_depth_resets_path_correctly(
        self, adapter: MarkdownAdapter, tmp_path: Path
    ) -> None:
        """Second H2 must not carry the first H2 in its path."""
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n\n## Alpha\n\nA.\n\n## Beta\n\nB.\n")
        result = adapter.parse("src_1", f)
        assert result.document is not None
        paths = [s.heading_path for s in result.document.sections]
        assert "Doc / Alpha" in paths
        assert "Doc / Beta" in paths
        assert "Doc / Alpha / Beta" not in paths  # Alpha must not be an ancestor of Beta
