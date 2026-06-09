"""Unit tests for cerebra/storage/artifact_store.py."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.artifact_store import (
    artifact_exists,
    artifact_path_for,
    write_artifact,
)
from cerebra.storage.migrations import run_migrations


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Minimal vault: just a root directory. Subdirs created by write_artifact."""
    return tmp_path / "vault"


@pytest.fixture
def vault_with_db(tmp_path: Path) -> tuple[Path, Path]:
    """Vault + migrated db for tests that need event_log."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "data").mkdir()
    db_path = root / "data" / "cerebra.db"
    run_migrations(db_path)
    return root, db_path


# ── write_artifact — basic behaviour ──────────────────────────────────────────


@pytest.mark.unit
class TestWriteArtifact:
    def test_creates_file(self, vault: Path) -> None:
        result = write_artifact(vault, "doc_001", "hello world")
        assert result.artifact_path.exists()
        assert result.artifact_path.read_text(encoding="utf-8") == "hello world"

    def test_returns_written_true_on_first_write(self, vault: Path) -> None:
        result = write_artifact(vault, "doc_001", "hello world")
        assert result.written is True

    def test_size_bytes_matches_utf8_encoding(self, vault: Path) -> None:
        content = "café"  # 5 bytes in UTF-8 (é is 2 bytes)
        result = write_artifact(vault, "doc_001", content)
        assert result.size_bytes == len(content.encode("utf-8"))

    def test_content_hash_is_sha256_of_utf8(self, vault: Path) -> None:
        content = "test content"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        result = write_artifact(vault, "doc_001", content)
        assert result.content_hash == expected_hash

    def test_artifact_path_is_absolute(self, vault: Path) -> None:
        result = write_artifact(vault, "doc_001", "x")
        assert result.artifact_path.is_absolute()

    def test_artifact_path_uses_document_id(self, vault: Path) -> None:
        result = write_artifact(vault, "doc_abc123", "x")
        assert result.artifact_path.name == "doc_abc123.txt"

    def test_creates_artifacts_subdir(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "x")
        assert (vault / "artifacts").is_dir()

    def test_multiple_documents_coexist(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "content one")
        write_artifact(vault, "doc_002", "content two")
        assert (vault / "artifacts" / "doc_001.txt").exists()
        assert (vault / "artifacts" / "doc_002.txt").exists()


# ── Idempotency ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIdempotency:
    def test_skip_on_identical_content(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "same content")
        result = write_artifact(vault, "doc_001", "same content")
        assert result.written is False

    def test_skip_preserves_existing_file(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "original")
        write_artifact(vault, "doc_001", "original")
        content = (vault / "artifacts" / "doc_001.txt").read_text(encoding="utf-8")
        assert content == "original"

    def test_overwrite_on_changed_content(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "old content")
        result = write_artifact(vault, "doc_001", "new content")
        assert result.written is True

    def test_overwrite_updates_file_on_disk(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "old content")
        write_artifact(vault, "doc_001", "new content")
        content = (vault / "artifacts" / "doc_001.txt").read_text(encoding="utf-8")
        assert content == "new content"

    def test_result_has_correct_hash_after_skip(self, vault: Path) -> None:
        content = "same content"
        write_artifact(vault, "doc_001", content)
        result = write_artifact(vault, "doc_001", content)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result.content_hash == expected

    def test_result_has_correct_hash_after_overwrite(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "old")
        new_content = "new content"
        result = write_artifact(vault, "doc_001", new_content)
        expected = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        assert result.content_hash == expected


# ── Inspector event ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestInspectorEvent:
    def test_event_emitted_on_write(
        self, vault_with_db: tuple[Path, Path]
    ) -> None:
        vault, db_path = vault_with_db
        log = SQLiteEventLog(db_path)
        write_artifact(vault, "doc_001", "hello", event_log=log)
        events = log.query_by_type("DocumentArtifactWritten")
        assert len(events) == 1
        data = events[0]["data_json"]
        import json
        d = json.loads(data)
        assert d["document_id"] == "doc_001"
        assert d["size_bytes"] > 0
        assert "artifact_path" in d

    def test_no_event_on_idempotent_skip(
        self, vault_with_db: tuple[Path, Path]
    ) -> None:
        vault, db_path = vault_with_db
        log = SQLiteEventLog(db_path)
        write_artifact(vault, "doc_001", "same", event_log=log)
        write_artifact(vault, "doc_001", "same", event_log=log)
        events = log.query_by_type("DocumentArtifactWritten")
        # Only one event — the second call was a skip
        assert len(events) == 1

    def test_event_emitted_on_overwrite(
        self, vault_with_db: tuple[Path, Path]
    ) -> None:
        vault, db_path = vault_with_db
        log = SQLiteEventLog(db_path)
        write_artifact(vault, "doc_001", "old", event_log=log)
        write_artifact(vault, "doc_001", "new", event_log=log)
        events = log.query_by_type("DocumentArtifactWritten")
        assert len(events) == 2

    def test_no_event_when_log_is_none(self, vault: Path) -> None:
        # Just verify no exception when event_log=None (the default)
        result = write_artifact(vault, "doc_001", "hello")
        assert result.written is True

    def test_event_artifact_path_is_relative(
        self, vault_with_db: tuple[Path, Path]
    ) -> None:
        vault, db_path = vault_with_db
        log = SQLiteEventLog(db_path)
        write_artifact(vault, "doc_001", "hello", event_log=log)
        events = log.query_by_type("DocumentArtifactWritten")
        import json
        d = json.loads(events[0]["data_json"])
        # artifact_path in the event should be relative (e.g. "artifacts/doc_001.txt")
        assert not Path(d["artifact_path"]).is_absolute()


# ── Helper functions ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestHelpers:
    def test_artifact_path_for(self, vault: Path) -> None:
        path = artifact_path_for(vault, "doc_xyz")
        assert path == vault / "artifacts" / "doc_xyz.txt"

    def test_artifact_exists_false_before_write(self, vault: Path) -> None:
        assert artifact_exists(vault, "doc_001") is False

    def test_artifact_exists_true_after_write(self, vault: Path) -> None:
        write_artifact(vault, "doc_001", "content")
        assert artifact_exists(vault, "doc_001") is True
