"""Unit tests for working_memory session management functions."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from cerebra.cognition.working_memory import (
    close_session,
    count_tower_items,
    count_wm_items,
    get_active_session,
    get_session_row,
    new_session,
)
from cerebra.storage.migrations import run_migrations


@pytest.mark.unit
class TestSessionManagement:
    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Path(f.name)
        run_migrations(db)
        return db

    def test_new_session_returns_valid_id_format(self) -> None:
        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            assert sid.startswith("sess_")
            assert len(sid) == 5 + 12  # "sess_" + 12 hex
        finally:
            db.unlink(missing_ok=True)

    def test_new_session_ids_are_unique(self) -> None:
        db = self._fresh_db()
        try:
            # Two calls on different vault paths → two different IDs
            s1 = new_session(db, "/vault/a")
            s2 = new_session(db, "/vault/b")
            assert s1 != s2
        finally:
            db.unlink(missing_ok=True)

    def test_get_active_session_none_on_fresh_db(self) -> None:
        db = self._fresh_db()
        try:
            result = get_active_session(db, "/vault/test")
            assert result is None
        finally:
            db.unlink(missing_ok=True)

    def test_get_active_session_returns_created_session(self) -> None:
        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            retrieved = get_active_session(db, "/vault/test")
            assert retrieved == sid
        finally:
            db.unlink(missing_ok=True)

    def test_get_active_session_scoped_to_vault_path(self) -> None:
        db = self._fresh_db()
        try:
            new_session(db, "/vault/a")
            # Different vault path returns None
            assert get_active_session(db, "/vault/b") is None
        finally:
            db.unlink(missing_ok=True)

    def test_new_session_closes_existing_active_session(self) -> None:
        db = self._fresh_db()
        try:
            s1 = new_session(db, "/vault/test")
            s2 = new_session(db, "/vault/test")

            # Only s2 should be active
            assert get_active_session(db, "/vault/test") == s2
            assert s1 != s2

            # s1 should be closed in the DB
            row = get_session_row(db, s1)
            assert row is not None
            assert row["status"] == "closed"
        finally:
            db.unlink(missing_ok=True)

    def test_new_session_only_one_active_per_vault(self) -> None:
        db = self._fresh_db()
        try:
            for _ in range(3):
                new_session(db, "/vault/test")
            active = get_active_session(db, "/vault/test")
            assert active is not None

            import sqlite3
            conn = sqlite3.connect(db)
            count = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE vault_path='/vault/test' AND status='active'"
            ).fetchone()[0]
            conn.close()
            assert count == 1
        finally:
            db.unlink(missing_ok=True)

    def test_close_session_marks_closed(self) -> None:
        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            close_session(db, sid)

            row = get_session_row(db, sid)
            assert row is not None
            assert row["status"] == "closed"
        finally:
            db.unlink(missing_ok=True)

    def test_close_session_updates_last_active_at(self) -> None:
        db = self._fresh_db()
        try:
            before = int(time.time())
            sid = new_session(db, "/vault/test")
            close_session(db, sid)
            after = int(time.time())

            row = get_session_row(db, sid)
            assert row is not None
            assert before <= row["last_active_at"] <= after + 1
        finally:
            db.unlink(missing_ok=True)

    def test_get_session_row_returns_none_for_unknown(self) -> None:
        db = self._fresh_db()
        try:
            assert get_session_row(db, "sess_nonexistent") is None
        finally:
            db.unlink(missing_ok=True)

    def test_get_session_row_returns_all_fields(self) -> None:
        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            row = get_session_row(db, sid)
            assert row is not None
            assert row["session_id"] == sid
            assert row["vault_path"] == "/vault/test"
            assert row["status"] == "active"
            assert row["started_at"] > 0
            assert row["last_active_at"] > 0
        finally:
            db.unlink(missing_ok=True)


@pytest.mark.unit
class TestSessionEventEmission:
    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Path(f.name)
        run_migrations(db)
        return db

    def test_working_memory_created_event_emitted(self) -> None:
        import sqlite3

        db = self._fresh_db()
        try:
            from cerebra.inspector.sqlite_log import SQLiteEventLog
            event_log = SQLiteEventLog(db)
            sid = new_session(db, "/vault/test", event_log=event_log)

            conn = sqlite3.connect(db)
            row = conn.execute(
                "SELECT event_type, subject_id, data_json FROM inspector_events "
                "WHERE event_type='WorkingMemoryCreated' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            conn.close()

            assert row is not None
            assert row[0] == "WorkingMemoryCreated"
            assert row[1] == sid
            data = json.loads(row[2])
            assert data["session_id"] == sid
            assert data["vault_path"] == "/vault/test"
            assert data["started_at"] > 0
        finally:
            db.unlink(missing_ok=True)

    def test_no_event_when_event_log_is_none(self) -> None:
        import sqlite3

        db = self._fresh_db()
        try:
            new_session(db, "/vault/test", event_log=None)

            conn = sqlite3.connect(db)
            count = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type='WorkingMemoryCreated'"
            ).fetchone()[0]
            conn.close()
            assert count == 0
        finally:
            db.unlink(missing_ok=True)


@pytest.mark.unit
class TestSessionItemCounts:
    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Path(f.name)
        run_migrations(db)
        return db

    def test_count_wm_items_empty(self) -> None:
        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            assert count_wm_items(db, sid) == {}
        finally:
            db.unlink(missing_ok=True)

    def test_count_tower_items_empty(self) -> None:
        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            assert count_tower_items(db, sid) == {}
        finally:
            db.unlink(missing_ok=True)

    def test_count_wm_items_with_rows(self) -> None:
        import sqlite3 as _sq3

        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            conn = _sq3.connect(db)
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, content_summary, promoted_at) "
                "VALUES ('wmi_1', ?, 'goal', 'test goal', 1)",
                (sid,),
            )
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, content_summary, promoted_at) "
                "VALUES ('wmi_2', ?, 'context', 'test context', 1)",
                (sid,),
            )
            conn.commit()
            conn.close()

            counts = count_wm_items(db, sid)
            assert counts["goal"] == 1
            assert counts["context"] == 1
            assert sum(counts.values()) == 2
        finally:
            db.unlink(missing_ok=True)

    def test_count_wm_items_excludes_evicted(self) -> None:
        import sqlite3 as _sq3

        db = self._fresh_db()
        try:
            sid = new_session(db, "/vault/test")
            conn = _sq3.connect(db)
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, content_summary, promoted_at, evicted_at) "
                "VALUES ('wmi_1', ?, 'goal', 'evicted goal', 1, 2)",
                (sid,),
            )
            conn.commit()
            conn.close()

            counts = count_wm_items(db, sid)
            assert counts == {}
        finally:
            db.unlink(missing_ok=True)


