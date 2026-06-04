"""Unit tests for file type detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.sources.detector import detect_type


@pytest.mark.unit
class TestDetector:
    def test_detects_markdown_by_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Hello")
        result = detect_type(f)
        assert result.detected_type == "markdown"
        assert result.confidence >= 0.80

    def test_detects_markdown_with_headings_sniff(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome text.")
        result = detect_type(f)
        assert result.confidence >= 0.90

    def test_detects_text_by_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("plain text")
        result = detect_type(f)
        assert result.detected_type == "text"

    def test_detects_unknown_for_binary(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.bin"
        f.write_bytes(bytes(range(256)))
        result = detect_type(f)
        assert result.detected_type == "unknown"

    def test_detects_rst_as_text(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.rst"
        f.write_text("Title\n=====\n\nContent.")
        result = detect_type(f)
        assert result.detected_type == "text"

    def test_unknown_extension_with_headings_sniff(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.xyz"
        f.write_text("# A heading\nsome content")
        result = detect_type(f)
        assert result.detected_type == "markdown"
        assert result.confidence < 0.80  # lower confidence for extension mismatch

    def test_content_sample_passed_directly(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("no headings here")
        result = detect_type(f, content_sample=b"# Override heading")
        assert result.detected_type == "markdown"

    def test_signals_dict_populated(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# H")
        result = detect_type(f)
        assert "extension" in result.signals
