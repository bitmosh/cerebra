# SPDX-License-Identifier: Apache-2.0
"""Unit tests for cerebra/storage/embeddings.py.

sentence-transformers is mocked — the real model is never loaded here.
See tests/integration/test_embeddings_integration.py for the live model test.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.db import connect
from cerebra.storage.embeddings import (
    _DIMENSIONS,
    _MODEL_NAME,
    _MODEL_VERSION,
    _embedding_id,
    cosine_search,
    drain_pending,
    pending_count,
    queue_for_embedding,
)
from cerebra.storage.index_state import get_state, seed_index_state
from cerebra.storage.migrations import run_migrations

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    seed_index_state(db_path)
    return db_path


def _insert_record(db_path: Path, record_id: str, content: str = "hello") -> str:
    """Insert a minimal source→document→chunk→memory_record chain."""
    now = int(time.time())
    src_id, doc_id, chk_id = f"src_{record_id}", f"doc_{record_id}", f"chk_{record_id}"
    h = f"hash_{record_id}"
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (source_id, canonical_path, content_hash, size_bytes,"
            " detected_type, detection_confidence, lifecycle_state, created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (src_id, f"/fake/{record_id}.md", h, 100, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            "INSERT INTO documents (document_id, source_id, document_type,"
            " normalization_confidence, lifecycle_state, created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?)",
            (doc_id, src_id, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            "INSERT INTO chunks (chunk_id, document_id, source_id, heading_path,"
            " chunk_index, depth, content, content_hash, token_estimate,"
            " chunk_strategy, lifecycle_state, created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (chk_id, doc_id, src_id, "", 0, 0, content, h, 10, "fixed", "active", now, 1),
        )
        conn.execute(
            "INSERT INTO memory_records (record_id, record_type, source_id, document_id,"
            " chunk_id, content, content_hash, token_estimate, lifecycle_state,"
            " created_at, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (record_id, "source_chunk", src_id, doc_id, chk_id, content, h, 10, "active", now, 1),
        )
    return record_id


def _fake_embed(texts: list[str]) -> np.ndarray:
    """Produce unit-vector float32 embeddings without loading any model."""
    n = len(texts)
    vecs = np.zeros((n, _DIMENSIONS), dtype=np.float32)
    for i in range(n):
        vecs[i, i % _DIMENSIONS] = 1.0
    return vecs


# ── _embedding_id ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEmbeddingId:
    def test_is_deterministic(self) -> None:
        assert _embedding_id("rec_001") == _embedding_id("rec_001")

    def test_prefix(self) -> None:
        assert _embedding_id("rec_001").startswith("emb_")

    def test_different_records_differ(self) -> None:
        assert _embedding_id("rec_001") != _embedding_id("rec_002")


# ── queue_for_embedding ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestQueueForEmbedding:
    def test_inserts_record(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        assert pending_count(db) == 1

    def test_idempotent(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        queue_for_embedding(db, ["rec_001"])
        assert pending_count(db) == 1

    def test_returns_inserted_count(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        _insert_record(db, "rec_002")
        assert queue_for_embedding(db, ["rec_001", "rec_002"]) == 2

    def test_empty_list_returns_zero(self, db: Path) -> None:
        assert queue_for_embedding(db, []) == 0

    def test_pending_count_zero_initially(self, db: Path) -> None:
        assert pending_count(db) == 0


# ── drain_pending ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDrainPending:
    def test_inserts_embedding_row(self, db: Path) -> None:
        _insert_record(db, "rec_001", content="test content")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        with connect(db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE record_id = 'rec_001'"
            ).fetchone()[0]
        assert count == 1

    def test_removes_from_pending_queue(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        assert pending_count(db) == 0

    def test_returns_count_embedded(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        _insert_record(db, "rec_002")
        queue_for_embedding(db, ["rec_001", "rec_002"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            assert drain_pending(db) == 2

    def test_empty_queue_returns_zero(self, db: Path) -> None:
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            assert drain_pending(db) == 0

    def test_skips_archived_records(self, db: Path) -> None:
        _insert_record(db, "rec_archived")
        with connect(db) as conn:
            conn.execute(
                "UPDATE memory_records SET lifecycle_state='archived' WHERE record_id='rec_archived'"
            )
        queue_for_embedding(db, ["rec_archived"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            assert drain_pending(db) == 0

    def test_vector_bytes_stored(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        with connect(db) as conn:
            row = conn.execute(
                "SELECT vector_bytes, dimensions FROM embeddings WHERE record_id='rec_001'"
            ).fetchone()
        assert row is not None
        assert row["dimensions"] == _DIMENSIONS
        assert len(row["vector_bytes"]) == _DIMENSIONS * 4  # float32 = 4 bytes

    def test_serialization_round_trip(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        with connect(db) as conn:
            blob = conn.execute(
                "SELECT vector_bytes FROM embeddings WHERE record_id='rec_001'"
            ).fetchone()["vector_bytes"]
        recovered = np.frombuffer(blob, dtype=np.float32)
        assert recovered.shape == (_DIMENSIONS,)
        # First record gets a unit vector along axis 0
        assert recovered[0] == pytest.approx(1.0)
        assert recovered[1:].sum() == pytest.approx(0.0)

    def test_model_metadata_stored(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        with connect(db) as conn:
            row = conn.execute(
                "SELECT embedding_model, model_version FROM embeddings WHERE record_id='rec_001'"
            ).fetchone()
        assert row["embedding_model"] == _MODEL_NAME
        assert row["model_version"] == _MODEL_VERSION

    def test_updates_index_state_vector(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        state = get_state(db, "vector")
        assert state is not None
        assert state["last_updated_at"] > 0
        assert state["model_name"] == _MODEL_NAME
        assert state["model_version"] == _MODEL_VERSION

    def test_emits_embedding_generated_event(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db, event_log=log)
        events = log.query_by_type("EmbeddingGenerated")
        assert len(events) == 1
        data = json.loads(events[0]["data_json"])
        assert data["record_id"] == "rec_001"
        assert data["model_name"] == _MODEL_NAME
        assert data["dimensions"] == _DIMENSIONS

    def test_emits_vector_index_updated_event(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db, event_log=log)
        events = log.query_by_type("VectorIndexUpdated")
        assert len(events) == 1
        data = json.loads(events[0]["data_json"])
        assert data["records_embedded"] == 1

    def test_no_vector_index_event_when_queue_empty(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db, event_log=log)
        assert log.query_by_type("VectorIndexUpdated") == []

    def test_batching_processes_all_records(self, db: Path) -> None:
        for i in range(5):
            _insert_record(db, f"rec_{i:03}", content=f"content {i}")
        queue_for_embedding(db, [f"rec_{i:03}" for i in range(5)])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            count = drain_pending(db, batch_size=2)
        assert count == 5
        assert pending_count(db) == 0

    def test_re_embed_replaces_existing(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        queue_for_embedding(db, ["rec_001"])
        with patch("cerebra.storage.embeddings.embed", _fake_embed):
            drain_pending(db)
        with connect(db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE record_id='rec_001'"
            ).fetchone()[0]
        assert count == 1  # INSERT OR REPLACE keeps exactly one row


# ── cosine_search ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCosineSearch:
    def _store_embedding(self, db: Path, record_id: str, vec: np.ndarray) -> None:
        """Directly insert an embedding row for test setup."""
        with connect(db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings"
                " (embedding_id, record_id, embedding_model, model_version,"
                "  vector_bytes, dimensions, created_at, schema_version)"
                " VALUES (?,?,?,?,?,?,?,1)",
                (
                    _embedding_id(record_id),
                    record_id,
                    _MODEL_NAME,
                    _MODEL_VERSION,
                    vec.astype(np.float32).tobytes(),
                    int(vec.shape[0]),
                    int(time.time()),
                ),
            )

    def test_returns_empty_when_no_embeddings(self, db: Path) -> None:
        q = np.zeros(_DIMENSIONS, dtype=np.float32)
        assert cosine_search(db, q) == []

    def test_returns_record_id_and_score(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        vec = np.ones(_DIMENSIONS, dtype=np.float32) / np.sqrt(_DIMENSIONS)
        self._store_embedding(db, "rec_001", vec)
        results = cosine_search(db, vec)
        assert len(results) == 1
        record_id, score = results[0]
        assert record_id == "rec_001"
        assert isinstance(score, float)

    def test_score_for_identical_vector_is_one(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        vec = np.ones(_DIMENSIONS, dtype=np.float32) / np.sqrt(_DIMENSIONS)
        self._store_embedding(db, "rec_001", vec)
        assert cosine_search(db, vec)[0][1] == pytest.approx(1.0, abs=1e-5)

    def test_higher_similarity_ranked_first(self, db: Path) -> None:
        _insert_record(db, "rec_high")
        _insert_record(db, "rec_low")
        query = np.zeros(_DIMENSIONS, dtype=np.float32)
        query[0] = 1.0
        high_vec = np.zeros(_DIMENSIONS, dtype=np.float32)
        high_vec[0] = 1.0
        low_vec = np.zeros(_DIMENSIONS, dtype=np.float32)
        low_vec[1] = 1.0
        self._store_embedding(db, "rec_high", high_vec)
        self._store_embedding(db, "rec_low", low_vec)
        results = cosine_search(db, query)
        assert results[0][0] == "rec_high"
        assert results[1][0] == "rec_low"

    def test_limit_respected(self, db: Path) -> None:
        for i in range(5):
            _insert_record(db, f"rec_{i:03}")
            vec = np.zeros(_DIMENSIONS, dtype=np.float32)
            vec[i] = 1.0
            self._store_embedding(db, f"rec_{i:03}", vec)
        query = np.ones(_DIMENSIONS, dtype=np.float32) / np.sqrt(_DIMENSIONS)
        assert len(cosine_search(db, query, limit=3)) <= 3

    def test_skips_archived_records(self, db: Path) -> None:
        _insert_record(db, "rec_archived")
        vec = np.ones(_DIMENSIONS, dtype=np.float32) / np.sqrt(_DIMENSIONS)
        self._store_embedding(db, "rec_archived", vec)
        with connect(db) as conn:
            conn.execute(
                "UPDATE memory_records SET lifecycle_state='archived' WHERE record_id='rec_archived'"
            )
        assert cosine_search(db, vec) == []

    def test_model_version_filter(self, db: Path) -> None:
        _insert_record(db, "rec_001")
        vec = np.ones(_DIMENSIONS, dtype=np.float32) / np.sqrt(_DIMENSIONS)
        self._store_embedding(db, "rec_001", vec)
        assert cosine_search(db, vec, model_name=_MODEL_NAME, model_version="v99") == []
