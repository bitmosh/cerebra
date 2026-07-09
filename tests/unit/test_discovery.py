# SPDX-License-Identifier: Apache-2.0
"""Unit tests for file discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.sources.discovery import canonical_path, discover_files


@pytest.mark.unit
class TestDiscovery:
    def test_discovers_markdown_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")
        found = discover_files(tmp_path)
        assert len(found) == 2

    def test_excludes_by_default_patterns(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git")
        (tmp_path / "doc.md").write_text("# Doc")
        found = discover_files(tmp_path)
        names = [f.name for f in found]
        assert "doc.md" in names
        assert "config" not in names

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.md").write_text("pkg")
        (tmp_path / "real.md").write_text("real")
        found = discover_files(tmp_path)
        assert len(found) == 1
        assert found[0].name == "real.md"

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.txt").write_text("x")
        (tmp_path / "doc.txt").write_text("y")
        found = discover_files(tmp_path, extensions=frozenset({".txt"}))
        assert len(found) == 1

    def test_filters_by_extension(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("md")
        (tmp_path / "doc.rst").write_text("rst")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        found = discover_files(tmp_path, extensions=frozenset({".md"}))
        assert all(f.suffix == ".md" for f in found)

    def test_custom_exclude_patterns(self, tmp_path: Path) -> None:
        (tmp_path / "archive").mkdir()
        (tmp_path / "archive" / "old.md").write_text("old")
        (tmp_path / "current.md").write_text("current")
        found = discover_files(tmp_path, exclude_patterns=["archive"])
        assert len(found) == 1
        assert found[0].name == "current.md"

    def test_result_is_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "z.md").write_text("")
        (tmp_path / "a.md").write_text("")
        (tmp_path / "m.md").write_text("")
        found = discover_files(tmp_path)
        names = [f.name for f in found]
        assert names == sorted(names)

    def test_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "nested.md").write_text("nested")
        found = discover_files(tmp_path)
        assert any(f.name == "nested.md" for f in found)

    def test_canonical_path_resolves(self, tmp_path: Path) -> None:
        f = tmp_path / "file.md"
        f.write_text("x")
        result = canonical_path(f)
        assert result.is_absolute()
