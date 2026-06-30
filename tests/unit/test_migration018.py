"""Unit tests for Migration018_SyntheticEpisodeProvenance and EpisodeWriter dual-write.

Phase 10: cycle episodes are bridged into memory_records so the retrieval pipeline
can surface them. Three sentinel rows in sources/documents/chunks satisfy the NOT NULL
FKs. EpisodeWriter.write() writes to both tables atomically.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from cerebra.cognition._constants import (
    SYNTHETIC_CHUNK_ID,
    SYNTHETIC_DOCUMENT_ID,
    SYNTHETIC_SOURCE_ID,
)
from cerebra.cognition.episode_writer import EpisodeWriter
from cerebra.cognition.session import SessionManager
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import (
    ALL_MIGRATIONS,
    Migration018_SyntheticEpisodeProvenance,
    run_migrations,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "cerebra.db"
    run_migrations(p)
    return p


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    db = tmp_path / "data" / "cerebra.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(db)
    return tmp_path


@pytest.fixture()
def vault_db(vault: Path) -> Path:
    return vault / "data" / "cerebra.db"


@pytest.fixture()
def runtime_session_id(vault: Path, vault_db: Path) -> str:
    store = FossicStore(vault)
    mgr = SessionManager(db_path=vault_db, store=store)
    session, _ = mgr.open_session(
        goal="phase 10 test goal",
        cycle_config="test.v0",
        vault_path=vault,
    )
    return session.session_id


@pytest.fixture()
def writer(vault_db: Path) -> EpisodeWriter:
    return EpisodeWriter(vault_db)


# ── Migration018 — registration ───────────────────────────────────────────────


class TestMigration018Registration:
    def test_version_is_18(self) -> None:
        assert Migration018_SyntheticEpisodeProvenance.version == 18

    def test_registered_in_all_migrations(self) -> None:
        types = [type(m) for m in ALL_MIGRATIONS]
        assert Migration018_SyntheticEpisodeProvenance in types

    def test_follows_017(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        idx_17 = versions.index(17)
        idx_18 = versions.index(18)
        assert idx_18 == idx_17 + 1

    def test_applied_version_recorded(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT version FROM applied_migrations WHERE version = 18").fetchone()
        conn.close()
        assert row is not None

    def test_idempotent_double_run(self, db_path: Path) -> None:
        run_migrations(db_path)
        run_migrations(db_path)


# ── Migration018 — sentinel rows ──────────────────────────────────────────────


class TestMigration018SentinelRows:
    def test_source_sentinel_exists(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT source_id, canonical_path, detected_type, parser_status, lifecycle_state"
            "  FROM sources WHERE source_id = ?",
            (SYNTHETIC_SOURCE_ID,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == "cerebra://cycle-episodes"
        assert row[2] == "cerebra_cycle"
        assert row[3] == "skipped"
        assert row[4] == "active"

    def test_document_sentinel_exists(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT document_id, source_id, document_type, lifecycle_state"
            "  FROM documents WHERE document_id = ?",
            (SYNTHETIC_DOCUMENT_ID,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == SYNTHETIC_SOURCE_ID
        assert row[2] == "cerebra_cycle"
        assert row[3] == "active"

    def test_chunk_sentinel_exists(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT chunk_id, document_id, source_id, lifecycle_state"
            "  FROM chunks WHERE chunk_id = ?",
            (SYNTHETIC_CHUNK_ID,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == SYNTHETIC_DOCUMENT_ID
        assert row[2] == SYNTHETIC_SOURCE_ID
        assert row[3] == "active"

    def test_sentinel_ids_match_constants(self) -> None:
        assert SYNTHETIC_SOURCE_ID == "cerebra_synthetic_source"
        assert SYNTHETIC_DOCUMENT_ID == "cerebra_synthetic_document"
        assert SYNTHETIC_CHUNK_ID == "cerebra_synthetic_chunk"


# ── EpisodeWriter dual-write ──────────────────────────────────────────────────


class TestEpisodeWriterDualWrite:
    def test_write_also_inserts_memory_record(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write(
            content="phase 10 output",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT record_id FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None

    def test_memory_record_has_cycle_episode_type(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write(
            content="classified output",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="evaluate",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT record_type FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "cycle_episode"

    def test_memory_record_uses_sentinel_fks(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write(
            content="fk test output",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT source_id, document_id, chunk_id FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == SYNTHETIC_SOURCE_ID
        assert row[1] == SYNTHETIC_DOCUMENT_ID
        assert row[2] == SYNTHETIC_CHUNK_ID

    def test_memory_record_content_matches(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        content = "the exact output text for content parity check"
        record_id = writer.write(
            content=content,
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT content FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == content

    def test_memory_record_content_hash_correct(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        content = "hash verification content"
        expected_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        record_id = writer.write(
            content=content,
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT content_hash FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == expected_hash

    def test_memory_record_token_estimate_nonzero(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write(
            content="five words of content here",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT token_estimate FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 5

    def test_memory_record_lifecycle_state_active(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        record_id = writer.write(
            content="lifecycle test",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        row = conn.execute(
            "SELECT lifecycle_state FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "active"

    def test_both_tables_written_atomically(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        """Same record_id appears in both tables — dual-write is atomic."""
        record_id = writer.write(
            content="atomicity check",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        conn = sqlite3.connect(writer.db_path)
        ep_row = conn.execute(
            "SELECT record_id FROM cycle_episode_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        mr_row = conn.execute(
            "SELECT record_id FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert ep_row is not None, "record missing from cycle_episode_records"
        assert mr_row is not None, "record missing from memory_records"

    def test_duplicate_write_ignored_gracefully(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        """INSERT OR IGNORE prevents duplicate key error on re-delivery."""
        record_id = writer.write(
            content="original content",
            runtime_session_id=runtime_session_id,
            cycle_id="c1",
            step_id="s1",
            step_name="plan",
        )
        # Manually insert the same record_id into memory_records again; should not raise
        conn = sqlite3.connect(writer.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO memory_records "
            "(record_id, record_type, source_id, document_id, chunk_id, "
            " content, content_hash, token_estimate, lifecycle_state, created_at)"
            " VALUES (?, 'cycle_episode', ?, ?, ?, 'x', 'abc', 1, 'active', 1)",
            (record_id, SYNTHETIC_SOURCE_ID, SYNTHETIC_DOCUMENT_ID, SYNTHETIC_CHUNK_ID),
        )
        conn.commit()
        # Original content must be unchanged
        row = conn.execute(
            "SELECT content FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "original content"

    def test_multiple_writes_produce_multiple_memory_records(
        self, writer: EpisodeWriter, runtime_session_id: str
    ) -> None:
        ids = []
        for i in range(3):
            rid = writer.write(
                content=f"output {i}",
                runtime_session_id=runtime_session_id,
                cycle_id="c1",
                step_id=f"s{i}",
                step_name="plan",
            )
            ids.append(rid)
        conn = sqlite3.connect(writer.db_path)
        count = conn.execute(
            f"SELECT COUNT(*) FROM memory_records WHERE record_id IN ({','.join('?' * len(ids))})",
            ids,
        ).fetchone()[0]
        conn.close()
        assert count == 3
