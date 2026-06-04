"""Unit tests for content hashing."""

from __future__ import annotations

import pytest

from cerebra.sources.hashing import hash_bytes, hash_file, hash_string


@pytest.mark.unit
class TestHashing:
    def test_hash_string_is_64_hex_chars(self) -> None:
        h = hash_string("hello")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_string_is_stable(self) -> None:
        assert hash_string("hello") == hash_string("hello")

    def test_different_strings_differ(self) -> None:
        assert hash_string("hello") != hash_string("world")

    def test_hash_bytes_matches_string(self) -> None:
        assert hash_bytes(b"hello") == hash_string("hello")

    def test_hash_file(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"content")
        h = hash_file(f)
        assert len(h) == 64

    def test_hash_file_stable(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"abc")
        assert hash_file(f) == hash_file(f)

    def test_hash_file_changes_with_content(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"v1")
        h1 = hash_file(f)
        f.write_bytes(b"v2")
        h2 = hash_file(f)
        assert h1 != h2
