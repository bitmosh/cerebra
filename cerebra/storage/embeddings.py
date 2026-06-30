"""
Embedding generation and vector index — mxbai-embed-large-v1.

All numpy and sentence-transformers imports are lazy (inside functions).
The module loads without either package installed; errors surface only when
embed() or cosine_search() are actually called.

Lazy-load model
───────────────
_get_model() loads SentenceTransformer on first call and caches it at the
module level. In a CLI process this load happens once (~300 ms). Tests that
don't need the real model should monkeypatch embed() directly.

Serialization
─────────────
float32 LE: np.ndarray.astype(np.float32).tobytes() → BLOB.
Round-trip:  np.frombuffer(blob, dtype=np.float32).

Model version
─────────────
_MODEL_VERSION is "v1". When the mxbai revision hash is known (see model card
on HuggingFace), update this constant and re-embed with `cerebra reembed`.
The existing embeddings table rows retain their version string; new rows get
the updated version. cosine_search() accepts explicit model_name/model_version
to query a specific version.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.db import connect
from cerebra.storage.index_state import mark_updated, seed_index_state

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer

_MODEL_NAME = "mixedbread-ai/mxbai-embed-large-v1"
_MODEL_VERSION = "v1"
_DIMENSIONS = 1024

_model: SentenceTransformer | None = None


# ── Model loading ─────────────────────────────────────────────────────────────


def _get_model() -> SentenceTransformer:
    """Load and cache the SentenceTransformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    return _model


# ── Embedding generation ──────────────────────────────────────────────────────


def embed(texts: list[str]) -> np.ndarray:
    """Encode texts to float32 normalized embeddings, shape (N, 1024).

    Requires sentence-transformers and numpy to be installed.
    The returned array has L2-normalized rows (suitable for dot-product cosine).
    """
    import numpy as np

    arr = _get_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return cast(np.ndarray, np.asarray(arr, dtype=np.float32))


def _embedding_id(record_id: str) -> str:
    """Derive a stable embedding_id for a given record + current model."""
    key = f"{record_id}:{_MODEL_NAME}:{_MODEL_VERSION}"
    return f"emb_{hashlib.sha256(key.encode()).hexdigest()[:12]}"


# ── Queue management ──────────────────────────────────────────────────────────


def queue_for_embedding(db_path: Path, record_ids: list[str]) -> int:
    """Add records to the pending_embeddings queue.

    INSERT OR IGNORE — records already queued are not re-added.
    Returns count of rows newly inserted.
    """
    if not record_ids:
        return 0
    now = int(time.time())
    with connect(db_path) as conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO pending_embeddings (record_id, queued_at, attempt)"
            " VALUES (?, ?, 0)",
            [(rid, now) for rid in record_ids],
        )
        inserted = conn.total_changes - before
    return inserted


def pending_count(db_path: Path) -> int:
    """Return number of records waiting for embedding."""
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM pending_embeddings").fetchone()[0])


# ── Drain ─────────────────────────────────────────────────────────────────────


def drain_pending(
    db_path: Path,
    *,
    batch_size: int = 32,
    event_log: SQLiteEventLog | None = None,
) -> int:
    """Embed all pending records and store results in the embeddings table.

    Reads pending_embeddings in batches of batch_size. For each batch:
    - fetches content from memory_records (skips tombstoned/archived records)
    - calls embed() to generate float32 vectors
    - INSERT OR REPLACE into embeddings table
    - DELETE from pending_embeddings
    - emits EmbeddingGenerated per record (if event_log provided)

    Emits VectorIndexUpdated once at the end (if records were embedded).
    Returns total count of records embedded.
    """
    import numpy as np

    total_embedded = 0
    t0 = time.monotonic()

    while True:
        with connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT p.record_id, m.content
                  FROM pending_embeddings p
                  JOIN memory_records m ON p.record_id = m.record_id
                 WHERE m.lifecycle_state = 'active'
                 ORDER BY p.queued_at
                 LIMIT ?
                """,
                (batch_size,),
            ).fetchall()

        if not rows:
            break

        record_ids = [r["record_id"] for r in rows]
        texts = [r["content"] for r in rows]

        t_embed = time.monotonic()
        vectors = embed(texts)
        embed_ms = int((time.monotonic() - t_embed) * 1000)
        per_record_ms = max(1, embed_ms // len(record_ids))

        now = int(time.time())
        batch_events = []
        with connect(db_path) as conn:
            for i, record_id in enumerate(record_ids):
                vec = np.asarray(vectors[i], dtype=np.float32)
                vector_bytes = vec.tobytes()
                dims = int(vec.shape[0])
                emb_id = _embedding_id(record_id)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO embeddings
                        (embedding_id, record_id, embedding_model, model_version,
                         vector_bytes, dimensions, created_at, schema_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (emb_id, record_id, _MODEL_NAME, _MODEL_VERSION, vector_bytes, dims, now),
                )
                conn.execute(
                    "DELETE FROM pending_embeddings WHERE record_id = ?",
                    (record_id,),
                )

                if event_log is not None:
                    batch_events.append(
                        make_event(
                            event_type="EmbeddingGenerated",
                            actor="embeddings",
                            summary=f"Embedding generated for {record_id}",
                            data={
                                "record_id": record_id,
                                "embedding_id": emb_id,
                                "model_name": _MODEL_NAME,
                                "model_version": _MODEL_VERSION,
                                "dimensions": dims,
                                "latency_ms": per_record_ms,
                            },
                            subject_id=record_id,
                        )
                    )

        # Emit after the write transaction commits — event_log.write() opens
        # its own connection and would deadlock if called inside the with block.
        if event_log is not None:
            for ev in batch_events:
                event_log.write(ev)

        total_embedded += len(record_ids)

    if total_embedded > 0:
        duration_ms = int((time.monotonic() - t0) * 1000)
        seed_index_state(db_path)
        with connect(db_path) as conn:
            total_with_emb: int = conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE embedding_model = ? AND model_version = ?",
                (_MODEL_NAME, _MODEL_VERSION),
            ).fetchone()[0]
        mark_updated(
            db_path,
            "vector",
            total_with_emb,
            model_name=_MODEL_NAME,
            model_version=_MODEL_VERSION,
        )
        if event_log is not None:
            event_log.write(
                make_event(
                    event_type="VectorIndexUpdated",
                    actor="embeddings",
                    summary=f"Vector index updated: {total_embedded} records embedded",
                    data={
                        "records_embedded": total_embedded,
                        "total_records_with_embeddings": total_with_emb,
                        "model_name": _MODEL_NAME,
                        "model_version": _MODEL_VERSION,
                        "duration_ms": duration_ms,
                    },
                )
            )

    return total_embedded


# ── Cosine search ─────────────────────────────────────────────────────────────


def cosine_search(
    db_path: Path,
    query_vec: Any,
    *,
    limit: int = 20,
    model_name: str = _MODEL_NAME,
    model_version: str = _MODEL_VERSION,
) -> list[tuple[str, float]]:
    """Return top-k records by cosine similarity to query_vec.

    query_vec must be a 1-D float32 array (or anything np.asarray() accepts)
    of length _DIMENSIONS (1024). Vectors stored in the embeddings table are
    L2-normalized (see embed()), so cosine similarity reduces to a dot product.

    Loads all active embeddings for the given model/version into memory.
    At 745 records this is ~3 MB. Switch to turbovec/qdrant around 50k records
    (see docs/agent/plans/v01_phase3_design.md §2.4).

    Returns list of (record_id, score) ordered by score descending.
    """
    import numpy as np

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT e.record_id, e.vector_bytes
              FROM embeddings e
              JOIN memory_records m ON e.record_id = m.record_id
             WHERE e.embedding_model = ?
               AND e.model_version   = ?
               AND m.lifecycle_state = 'active'
            """,
            (model_name, model_version),
        ).fetchall()

    if not rows:
        return []

    record_ids = [r["record_id"] for r in rows]
    matrix = np.stack(
        [np.frombuffer(r["vector_bytes"], dtype=np.float32) for r in rows]
    )  # shape (N, D)

    q = np.asarray(query_vec, dtype=np.float32)
    scores = matrix @ q  # cosine similarity (vectors already normalized)

    top_indices = np.argsort(scores)[::-1][:limit]
    return [(record_ids[int(i)], float(scores[i])) for i in top_indices]
