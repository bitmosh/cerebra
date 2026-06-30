"""Phase 8 v0.3.5a unit tests — EpisodeWriter, EpisodeRecord, Migration016.

Run with: pytest tests/unit/test_episode_writer.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.cognition.episode_writer import EpisodeRecord, EpisodeWriter, _now_ms
from cerebra.cognition.session import SessionManager
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import (
    ALL_MIGRATIONS,
    Migration016_CycleEpisodeRecords,
    run_migrations,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    db_path = tmp_path / "data" / "cerebra.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(db_path)
    return tmp_path


@pytest.fixture()
def db_path(vault: Path) -> Path:
    return vault / "data" / "cerebra.db"


@pytest.fixture()
def store(vault: Path) -> FossicStore:
    return FossicStore(vault)


@pytest.fixture()
def runtime_session_id(db_path: Path, store: FossicStore, vault: Path) -> str:
    mgr = SessionManager(db_path=db_path, store=store)
    session, _ = mgr.open_session(
        goal="episode test goal",
        cycle_config="test.v0",
        vault_path=vault,
    )
    return session.session_id


@pytest.fixture()
def writer(db_path: Path) -> EpisodeWriter:
    return EpisodeWriter(db_path)


# ── Migration016 ──────────────────────────────────────────────────────────────


class TestMigration016:
    def test_table_exists_after_migration(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cycle_episode_records'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_all_four_indexes_created(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='cycle_episode_records'"
            ).fetchall()
        }
        conn.close()
        assert "idx_episodes_runtime_session" in indexes
        assert "idx_episodes_working_memory" in indexes
        assert "idx_episodes_cycle" in indexes
        assert "idx_episodes_created" in indexes

    def test_migration_version_is_16(self) -> None:
        assert Migration016_CycleEpisodeRecords.version == 16

    def test_migration_in_all_migrations(self) -> None:
        types = [type(m) for m in ALL_MIGRATIONS]
        assert Migration016_CycleEpisodeRecords in types

    def test_migration_follows_015(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        idx_15 = versions.index(15)
        idx_16 = versions.index(16)
        assert idx_16 == idx_15 + 1

    def test_applied_version_recorded(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT version FROM applied_migrations WHERE version = 16").fetchone()
        conn.close()
        assert row is not None

    def test_fk_to_runtime_sessions_enforced(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO cycle_episode_records
                (record_id, runtime_session_id, cycle_id, step_id, step_name,
                 content, created_at)
                VALUES ('ep_test', 'sess_doesnotexist', 'c1', 's1', 'step', 'x', 1)
                """
            )
            conn.commit()
        conn.close()

    def test_nullable_working_memory_session(self, db_path: Path, runtime_session_id: str) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO cycle_episode_records
            (record_id, runtime_session_id, working_memory_session_id,
             cycle_id, step_id, step_name, content, created_at)
            VALUES (?, ?, NULL, 'c1', 's1', 'step', 'content', ?)
            """,
            ("ep_null_wm", runtime_session_id, _now_ms()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT working_memory_session_id FROM cycle_episode_records WHERE record_id = 'ep_null_wm'"
        ).fetchone()
        conn.close()
        assert row[0] is None


# ── EpisodeRecord dataclass ───────────────────────────────────────────────────


class TestEpisodeRecordDataclass:
    def _make(self, **overrides) -> EpisodeRecord:
        defaults = {
            "record_id": "ep_abc123456789",
            "runtime_session_id": "sess_parent001",
            "cycle_id": "cycle_001",
            "step_id": "step_001",
            "step_name": "plan",
            "content": "The output of step one.",
            "created_at": 1700000000000,
        }
        defaults.update(overrides)
        return EpisodeRecord(**defaults)

    def test_frozen(self) -> None:
        rec = self._make()
        with pytest.raises((AttributeError, TypeError)):
            rec.content = "mutated"  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        rec = self._make()
        assert rec.record_id == "ep_abc123456789"
        assert rec.runtime_session_id == "sess_parent001"
        assert rec.content == "The output of step one."

    def test_optional_fields_default_none(self) -> None:
        rec = self._make()
        assert rec.working_memory_session_id is None
        assert rec.content_summary is None
        assert rec.metadata is None
        assert rec.leeway_grant_event_id is None
        assert rec.cited_record_ids is None


# ── EpisodeWriter.write() ─────────────────────────────────────────────────────


class TestEpisodeWriterWrite:
    def test_write_returns_record_id(self, writer: EpisodeWriter, runtime_session_id: str) -> None:
        record_id = writer.write(
            content="step output",
            runtime_session_id=runtime_session_id,
            cycle_id="cycle_001",
            step_id="step_001",
            step_name="plan",
        )
        assert isinstance(record_id, str)
        assert record_id.startswith("ep_")

    def test_record_id_unique_per_call(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        r1 = writer.write("out1", runtime_session_id, "c1", "s1", "plan")
        r2 = writer.write("out2", runtime_session_id, "c1", "s2", "plan")
        assert r1 != r2

    def test_write_with_null_wm_session(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write(
            content="output",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
            working_memory_session_id=None,
        )
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.working_memory_session_id is None

    def test_write_persists_content(self, writer: EpisodeWriter, runtime_session_id: str) -> None:
        record_id = writer.write(
            content="the full LLM output text",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.content == "the full LLM output text"

    def test_write_persists_step_name(self, writer: EpisodeWriter, runtime_session_id: str) -> None:
        record_id = writer.write(
            content="x",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="critique",
        )
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.step_name == "critique"

    def test_content_summary_truncated_at_200(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        long = "x" * 300
        record_id = writer.write(long, runtime_session_id, "c1", "s1", "plan")
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.content_summary is not None
        assert len(loaded.content_summary) == 200

    def test_content_summary_exact_for_short(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        short = "hello"
        record_id = writer.write(short, runtime_session_id, "c1", "s1", "plan")
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.content_summary == "hello"

    def test_cited_record_ids_roundtrip(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        cited = ["rec_aabbccddeeff", "rec_112233445566"]
        record_id = writer.write(
            content="x",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
            cited_record_ids=cited,
        )
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.cited_record_ids == cited

    def test_metadata_roundtrip(self, writer: EpisodeWriter, runtime_session_id: str) -> None:
        meta = {"step_index": 2, "step_executions_count": 3}
        record_id = writer.write(
            content="x",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
            metadata=meta,
        )
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.metadata == meta

    def test_leeway_grant_event_id_roundtrip(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        event_id = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        record_id = writer.write(
            content="x",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
            leeway_grant_event_id=event_id,
        )
        loaded = writer.read(record_id)
        assert loaded is not None
        assert loaded.leeway_grant_event_id == event_id

    def test_nonexistent_runtime_session_raises(self, writer: EpisodeWriter) -> None:
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            writer.write(
                content="x",
                runtime_session_id="sess_doesnotexist",
                cycle_id="c1",
                step_id="s1",
                step_name="plan",
            )


# ── EpisodeWriter.read() ──────────────────────────────────────────────────────


class TestEpisodeWriterRead:
    def test_read_nonexistent_returns_none(self, writer: EpisodeWriter) -> None:
        assert writer.read("ep_doesnotexist") is None

    def test_read_returns_episode_record(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write("content", runtime_session_id, "c1", "s1", "plan")
        result = writer.read(record_id)
        assert isinstance(result, EpisodeRecord)

    def test_read_runtime_session_id_matches(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write("content", runtime_session_id, "c1", "s1", "plan")
        result = writer.read(record_id)
        assert result is not None
        assert result.runtime_session_id == runtime_session_id


# ── EpisodeWriter.list_for_runtime_session() ──────────────────────────────────


class TestEpisodeWriterList:
    def test_empty_session_returns_empty(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        assert writer.list_for_runtime_session(runtime_session_id) == []

    def test_lists_all_for_session(self, writer: EpisodeWriter, runtime_session_id: str) -> None:
        writer.write("out1", runtime_session_id, "cycle_001", "s1", "plan")
        writer.write("out2", runtime_session_id, "cycle_001", "s2", "evaluate")
        records = writer.list_for_runtime_session(runtime_session_id)
        assert len(records) == 2

    def test_filters_to_session(
        self,
        db_path: Path,
        store: FossicStore,
        vault: Path,
        writer: EpisodeWriter,
        runtime_session_id: str,
    ) -> None:
        mgr = SessionManager(db_path=db_path, store=store)
        other_session, _ = mgr.open_session("other goal", "test.v0", vault)

        writer.write("for session A", runtime_session_id, "c1", "s1", "plan")
        writer.write("for session B", other_session.session_id, "c2", "s1", "plan")

        records_a = writer.list_for_runtime_session(runtime_session_id)
        records_b = writer.list_for_runtime_session(other_session.session_id)
        assert len(records_a) == 1
        assert len(records_b) == 1
        assert records_a[0].content == "for session A"

    def test_ordered_by_created_at(self, writer: EpisodeWriter, runtime_session_id: str) -> None:
        import sqlite3

        # Insert with explicit created_at to control ordering
        conn = sqlite3.connect(writer.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        for i, ts in enumerate([1000000000003, 1000000000001, 1000000000002]):
            conn.execute(
                """
                INSERT INTO cycle_episode_records
                (record_id, runtime_session_id, cycle_id, step_id, step_name, content, created_at)
                VALUES (?, ?, 'c1', ?, 'plan', ?, ?)
                """,
                (f"ep_{i:012d}", runtime_session_id, f"s{i}", f"output {i}", ts),
            )
        conn.commit()
        conn.close()
        records = writer.list_for_runtime_session(runtime_session_id)
        assert [r.created_at for r in records] == [1000000000001, 1000000000002, 1000000000003]
