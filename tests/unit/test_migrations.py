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
