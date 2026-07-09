# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the inspector event schema and log infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cerebra.inspector.event import make_event
from cerebra.inspector.ndjson_log import NDJSONEventLog
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.migrations import run_migrations


@pytest.mark.unit
class TestInspectorEvent:
    def test_event_id_is_unique(self) -> None:
        e1 = make_event("VaultCreated", "test", "s1")
        e2 = make_event("VaultCreated", "test", "s2")
        assert e1.event_id != e2.event_id

    def test_to_dict_contains_all_envelope_fields(self) -> None:
        e = make_event("MigrationRun", "vault_init", "ran migration 1", {"version": 1})
        d = e.to_dict()
        required = {
            "event_id",
            "event_type",
            "schema_version",
            "timestamp",
            "session_id",
            "cycle_id",
            "step_id",
            "subject_id",
            "actor",
            "summary",
            "data",
        }
        assert required.issubset(d.keys())

    def test_nullable_context_fields_default_none(self) -> None:
        e = make_event("VaultCreated", "test", "summary")
        assert e.session_id is None
        assert e.cycle_id is None
        assert e.step_id is None
        assert e.subject_id is None

    def test_to_json_is_valid(self) -> None:
        e = make_event("ConfigLoaded", "init", "loaded", {"key": "val"})
        parsed = json.loads(e.to_json())
        assert parsed["event_type"] == "ConfigLoaded"
        assert parsed["data"] == {"key": "val"}

    def test_schema_version_is_one(self) -> None:
        e = make_event("VaultCreated", "test", "s")
        assert e.schema_version == 1


@pytest.mark.unit
class TestSQLiteEventLog:
    def _log_with_db(self, tmp_path: Path) -> SQLiteEventLog:
        db = tmp_path / "test.db"
        run_migrations(db)
        return SQLiteEventLog(db)

    def test_write_and_query_by_type(self, tmp_path: Path) -> None:
        log = self._log_with_db(tmp_path)
        e = make_event("VaultCreated", "test", "created vault")
        log.write(e)
        results = log.query_by_type("VaultCreated")
        assert len(results) == 1
        assert results[0]["event_id"] == e.event_id

    def test_query_recent_returns_latest_first(self, tmp_path: Path) -> None:
        log = self._log_with_db(tmp_path)
        for i in range(3):
            log.write(make_event("MigrationRun", "test", f"run {i}", {"i": i}))
        results = log.query_recent(limit=3)
        assert len(results) == 3

    def test_query_by_session(self, tmp_path: Path) -> None:
        log = self._log_with_db(tmp_path)
        e = make_event("CycleStarted", "test", "started", session_id="sess_abc")
        log.write(e)
        results = log.query_by_session("sess_abc")
        assert len(results) == 1
        results_other = log.query_by_session("sess_xyz")
        assert len(results_other) == 0

    def test_event_data_round_trips(self, tmp_path: Path) -> None:
        log = self._log_with_db(tmp_path)
        payload = {"vault_path": "/tmp/vault", "config": {"v": 1}}
        e = make_event("VaultCreated", "test", "s", payload)
        log.write(e)
        results = log.query_by_type("VaultCreated")
        stored = json.loads(results[0]["data_json"])
        assert stored == payload


@pytest.mark.unit
class TestNDJSONEventLog:
    def test_write_creates_file(self, tmp_path: Path) -> None:
        log = NDJSONEventLog(tmp_path / "events" / "test.ndjson")
        e = make_event("VaultCreated", "test", "created")
        log.write(e)
        assert (tmp_path / "events" / "test.ndjson").exists()

    def test_each_line_is_valid_json(self, tmp_path: Path) -> None:
        log = NDJSONEventLog(tmp_path / "test.ndjson")
        for i in range(3):
            log.write(make_event("MigrationRun", "test", f"run {i}"))
        lines = log.read_all()
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert "event_id" in parsed

    def test_append_does_not_overwrite(self, tmp_path: Path) -> None:
        log = NDJSONEventLog(tmp_path / "test.ndjson")
        log.write(make_event("VaultCreated", "test", "first"))
        log.write(make_event("VaultCreated", "test", "second"))
        lines = log.read_all()
        assert len(lines) == 2

    def test_read_all_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        log = NDJSONEventLog(tmp_path / "nonexistent.ndjson")
        assert log.read_all() == []
