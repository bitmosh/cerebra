"""Unit tests for the migration framework."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cerebra.storage.index_state import get_state, is_stale, mark_updated, seed_index_state
from cerebra.storage.migrations import ALL_MIGRATIONS, run_migrations


@pytest.mark.unit
class TestMigrations:
    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            return Path(f.name)

    def test_migration_creates_inspector_events_table(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "inspector_events" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration_creates_applied_migrations_table(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "applied_migrations" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migrations_are_idempotent(self) -> None:
        db = self._fresh_db()
        try:
            first = run_migrations(db)
            second = run_migrations(db)
            assert len(first) > 0
            assert second == []  # nothing new applied
        finally:
            db.unlink(missing_ok=True)

    def test_returns_applied_version_numbers(self) -> None:
        db = self._fresh_db()
        try:
            applied = run_migrations(db)
            assert 1 in applied
        finally:
            db.unlink(missing_ok=True)

    def test_all_migrations_have_unique_versions(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert len(versions) == len(set(versions))

    def test_all_migrations_have_descriptions(self) -> None:
        for m in ALL_MIGRATIONS:
            assert m.description, f"Migration {m.version} has no description"

    def test_migration006_creates_phase3_tables(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "embeddings" in tables
            assert "pending_embeddings" in tables
            assert "index_state" in tables
            assert "graph_nodes" in tables
            assert "graph_edges" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration006_graph_edges_on_delete_restrict(self) -> None:
        """graph_edges FKs must be RESTRICT — hard-delete of a node with live edges is a bug."""
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            # Insert a node
            conn.execute(
                "INSERT INTO graph_nodes (node_id, node_type, label, lifecycle_state, "
                "payload_json, created_at, updated_at, schema_version) "
                "VALUES ('gn_1', 'Source', 'test', 'active', '{}', 1, 1, 1)"
            )
            conn.execute(
                "INSERT INTO graph_nodes (node_id, node_type, label, lifecycle_state, "
                "payload_json, created_at, updated_at, schema_version) "
                "VALUES ('gn_2', 'Document', 'test', 'active', '{}', 1, 1, 1)"
            )
            # Insert an edge
            conn.execute(
                "INSERT INTO graph_edges (edge_id, edge_type, source_node_id, target_node_id, "
                "confidence, weight, created_by, lifecycle_state, payload_json, "
                "created_at, updated_at, schema_version) "
                "VALUES ('ge_1', 'CONTAINS', 'gn_1', 'gn_2', 1.0, 1.0, "
                "'test', 'active', '{}', 1, 1, 1)"
            )
            conn.commit()
            # Attempting to delete a node that has edges must fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM graph_nodes WHERE node_id = 'gn_1'")
            conn.close()
        finally:
            db.unlink(missing_ok=True)


@pytest.mark.unit
class TestMigration007:
    """Migration007 seeds index_state and queues active memory_records for embedding."""

    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            return Path(f.name)

    def _insert_record(self, conn: sqlite3.Connection, record_id: str) -> None:
        """Insert a minimal active memory_record chain for testing."""
        src_id = f"src_{record_id}"
        doc_id = f"doc_{record_id}"
        chk_id = f"chk_{record_id}"
        conn.execute(
            "INSERT INTO sources (source_id, canonical_path, content_hash, size_bytes,"
            " detected_type, detection_confidence, lifecycle_state, created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (src_id, f"/fake/{record_id}.md", "h", 1, "markdown", 1.0, "active", 1, 1),
        )
        conn.execute(
            "INSERT INTO documents (document_id, source_id, document_type,"
            " normalization_confidence, lifecycle_state, created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?)",
            (doc_id, src_id, "markdown", 1.0, "active", 1, 1),
        )
        conn.execute(
            "INSERT INTO chunks (chunk_id, document_id, source_id, heading_path,"
            " chunk_index, depth, content, content_hash, token_estimate,"
            " chunk_strategy, lifecycle_state, created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (chk_id, doc_id, src_id, "", 0, 0, "text", "h", 1, "fixed", "active", 1, 1),
        )
        conn.execute(
            "INSERT INTO memory_records (record_id, record_type, source_id, document_id,"
            " chunk_id, content, content_hash, token_estimate, lifecycle_state,"
            " created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (record_id, "source_chunk", src_id, doc_id, chk_id, "text", "h", 1, "active", 1, 1),
        )

    def test_migration007_seeds_index_state_on_fresh_vault(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT index_name, last_updated_at FROM index_state ORDER BY index_name"
            ).fetchall()
            conn.close()
            names = {r[0] for r in rows}
            assert names == {"graph", "lexical", "vector"}
            assert all(r[1] == 0 for r in rows), "seed rows should have last_updated_at=0"
        finally:
            db.unlink(missing_ok=True)

    def test_migration007_queues_active_records_on_fresh_vault(self) -> None:
        db = self._fresh_db()
        try:
            # Apply migrations up to 006 only, then insert records, then apply 007
            from cerebra.storage.migrations import (
                ALL_MIGRATIONS,
                Migration001_InitSchema,
                Migration006_Phase3Schema,
            )
            import sqlite3 as _sq3
            conn = _sq3.connect(db)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS applied_migrations"
                " (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at INTEGER NOT NULL)"
            )
            conn.commit()
            applied = set()
            for m in ALL_MIGRATIONS:
                if m.version > 6:
                    break
                m.up(conn)
                conn.execute(
                    "INSERT INTO applied_migrations VALUES (?,?,?)",
                    (m.version, m.description, 1),
                )
                conn.commit()
                applied.add(m.version)

            # Insert two active records before Migration007
            self._insert_record(conn, "rec_a")
            self._insert_record(conn, "rec_b")
            conn.commit()
            conn.close()

            # Now apply 007
            run_migrations(db)

            conn = _sq3.connect(db)
            pending = {r[0] for r in conn.execute("SELECT record_id FROM pending_embeddings").fetchall()}
            conn.close()
            assert "rec_a" in pending
            assert "rec_b" in pending
        finally:
            db.unlink(missing_ok=True)

    def test_migration007_is_idempotent_when_already_backfilled(self) -> None:
        """Running Migration007 twice (or after a manual backfill) must not duplicate rows."""
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            self._insert_record(conn, "rec_x")
            conn.commit()
            # Manually queue rec_x before any re-run
            conn.execute(
                "INSERT OR IGNORE INTO pending_embeddings (record_id, queued_at, attempt)"
                " VALUES ('rec_x', 1, 0)"
            )
            conn.commit()
            conn.close()

            # Running migrations again must be a no-op (007 already applied)
            run_migrations(db)

            conn = sqlite3.connect(db)
            count = conn.execute(
                "SELECT COUNT(*) FROM pending_embeddings WHERE record_id='rec_x'"
            ).fetchone()[0]
            conn.close()
            assert count == 1, "duplicate row after re-run"
        finally:
            db.unlink(missing_ok=True)

    def test_migration007_skips_inactive_records(self) -> None:
        """archived / tombstoned records must not be queued by Migration007."""
        db = self._fresh_db()
        try:
            from cerebra.storage.migrations import ALL_MIGRATIONS
            import sqlite3 as _sq3
            conn = _sq3.connect(db)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS applied_migrations"
                " (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at INTEGER NOT NULL)"
            )
            conn.commit()
            for m in ALL_MIGRATIONS:
                if m.version > 6:
                    break
                m.up(conn)
                conn.execute(
                    "INSERT INTO applied_migrations VALUES (?,?,?)",
                    (m.version, m.description, 1),
                )
                conn.commit()

            self._insert_record(conn, "rec_active")
            self._insert_record(conn, "rec_archived")
            conn.execute(
                "UPDATE memory_records SET lifecycle_state='archived' WHERE record_id='rec_archived'"
            )
            conn.commit()
            conn.close()

            run_migrations(db)

            conn = _sq3.connect(db)
            pending = {r[0] for r in conn.execute("SELECT record_id FROM pending_embeddings").fetchall()}
            conn.close()
            assert "rec_active" in pending
            assert "rec_archived" not in pending
        finally:
            db.unlink(missing_ok=True)


@pytest.mark.unit
class TestMigration008:
    """Migration008 creates the three Phase 4 retrieval trace tables."""

    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            return Path(f.name)

    def test_migration008_creates_retrieval_tables(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "retrieval_traces" in tables
            assert "retrieval_steps" in tables
            assert "retrieval_candidates" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration008_is_idempotent(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            second = run_migrations(db)
            assert 8 not in second, "Migration008 should not re-apply on second run"
        finally:
            db.unlink(missing_ok=True)

    def test_migration008_retrieval_steps_fk_to_traces(self) -> None:
        """retrieval_steps must REJECT inserts with unknown trace_id."""
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO retrieval_steps "
                    "(step_id, trace_id, step_number, step_name, duration_ms) "
                    "VALUES ('s1', 'nonexistent_trace', 1, 'exact_sku', 5)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration008_retrieval_candidates_fk_to_traces(self) -> None:
        """retrieval_candidates must REJECT inserts with unknown trace_id."""
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO retrieval_candidates "
                    "(candidate_id, trace_id, record_id, step_surfaced, "
                    " retrieval_path, salience_score) "
                    "VALUES ('c1', 'nonexistent_trace', 'rec_001', "
                    "'exact_sku', 'exact_sku:D1=0x5', 0.73)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration008_full_trace_roundtrip(self) -> None:
        """A trace + step + candidate can be inserted and queried."""
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")

            # Insert a trace
            conn.execute(
                "INSERT INTO retrieval_traces "
                "(trace_id, query, mode, started_at, finished_at, duration_ms) "
                "VALUES ('tr_001', 'test query', 'hybrid', 1720000000, 1720000001, 50)"
            )
            # Insert a step
            conn.execute(
                "INSERT INTO retrieval_steps "
                "(step_id, trace_id, step_number, step_name, "
                " candidate_count, new_candidates, duration_ms) "
                "VALUES ('st_001', 'tr_001', 2, 'exact_sku', 3, 3, 4)"
            )
            # Insert a candidate
            conn.execute(
                "INSERT INTO retrieval_candidates "
                "(candidate_id, trace_id, record_id, step_surfaced, "
                " retrieval_path, salience_score, selected, rank) "
                "VALUES ('cd_001', 'tr_001', 'rec_001', 'exact_sku', "
                "'exact_sku:D1=0x5', 0.83, 1, 1)"
            )
            conn.commit()

            row = conn.execute(
                "SELECT candidate_count FROM retrieval_traces WHERE trace_id='tr_001'"
            ).fetchone()
            assert row is not None
            step = conn.execute(
                "SELECT step_name FROM retrieval_steps WHERE trace_id='tr_001'"
            ).fetchone()
            assert step[0] == "exact_sku"
            cand = conn.execute(
                "SELECT salience_score, selected FROM retrieval_candidates "
                "WHERE trace_id='tr_001'"
            ).fetchone()
            assert cand[0] == pytest.approx(0.83)
            assert cand[1] == 1
            conn.close()
        finally:
            db.unlink(missing_ok=True)


@pytest.mark.unit
class TestIndexState:
    def _migrated_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Path(f.name)
        run_migrations(db)
        return db

    def test_seed_creates_three_rows(self) -> None:
        db = self._migrated_db()
        try:
            seed_index_state(db)
            for name in ("lexical", "vector", "graph"):
                state = get_state(db, name)
                assert state is not None
                assert state["last_updated_at"] == 0
        finally:
            db.unlink(missing_ok=True)

    def test_seed_is_idempotent(self) -> None:
        db = self._migrated_db()
        try:
            seed_index_state(db)
            seed_index_state(db)  # second call must not raise or duplicate
            conn = sqlite3.connect(db)
            count = conn.execute("SELECT COUNT(*) FROM index_state").fetchone()[0]
            assert count == 3
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_is_stale_before_update(self) -> None:
        db = self._migrated_db()
        try:
            seed_index_state(db)
            assert is_stale(db, "lexical") is True
            assert is_stale(db, "vector") is True
            assert is_stale(db, "graph") is True
        finally:
            db.unlink(missing_ok=True)

    def test_mark_updated_clears_stale(self) -> None:
        db = self._migrated_db()
        try:
            seed_index_state(db)
            mark_updated(db, "lexical", record_count=42)
            assert is_stale(db, "lexical") is False
            state = get_state(db, "lexical")
            assert state is not None
            assert state["record_count"] == 42
            assert state["last_updated_at"] > 0
        finally:
            db.unlink(missing_ok=True)

    def test_mark_updated_vector_records_model(self) -> None:
        db = self._migrated_db()
        try:
            seed_index_state(db)
            mark_updated(
                db,
                "vector",
                record_count=100,
                model_name="mixedbread-ai/mxbai-embed-large-v1",
                model_version="v1",
            )
            state = get_state(db, "vector")
            assert state is not None
            assert state["model_name"] == "mixedbread-ai/mxbai-embed-large-v1"
            assert state["model_version"] == "v1"
        finally:
            db.unlink(missing_ok=True)

    def test_is_stale_missing_index(self) -> None:
        db = self._migrated_db()
        try:
            # No seed — rows don't exist yet
            assert is_stale(db, "lexical") is True
        finally:
            db.unlink(missing_ok=True)
