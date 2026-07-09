# SPDX-License-Identifier: Apache-2.0
"""
Index freshness tracking per docs/agent/plans/v01_phase3_design.md §3.

Three named indexes: 'lexical', 'vector', 'graph'. Each row in index_state
tracks when it was last fully updated and (for 'vector') which embedding
model version is current.

The index_state table is populated at vault init, not by Migration006.
Migration006 creates the table; vault init inserts the three seed rows.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from cerebra.storage.db import connect

INDEX_NAMES = frozenset({"lexical", "vector", "graph"})


def seed_index_state(db_path: Path) -> None:
    """Insert the three seed rows if they don't exist yet.

    Called at vault init. Idempotent: INSERT OR IGNORE.
    """
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO index_state
                (index_name, last_updated_at, record_count, schema_version)
            VALUES (?, 0, 0, 1)
            """,
            [(name,) for name in sorted(INDEX_NAMES)],
        )


def get_state(db_path: Path, index_name: str) -> dict[str, Any] | None:
    """Return the full index_state row for index_name, or None if missing."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM index_state WHERE index_name = ?", (index_name,)
        ).fetchone()
    return dict(row) if row else None


def is_stale(db_path: Path, index_name: str) -> bool:
    """Return True if index_name has never been built or has never been updated."""
    state = get_state(db_path, index_name)
    if state is None:
        return True
    return bool(state["last_updated_at"] == 0)


def mark_updated(
    db_path: Path,
    index_name: str,
    record_count: int,
    *,
    model_name: str | None = None,
    model_version: str | None = None,
    timestamp: int | None = None,
) -> None:
    """Record a successful index update.

    model_name and model_version are only meaningful for the 'vector' index;
    pass them when updating after an embedding drain.

    timestamp: explicit epoch seconds to record as last_updated_at. Defaults
    to int(time.time()). Pass max(time.time(), max_record_created_at) from
    the lexical index so that records with future created_at values are
    covered without requiring a subsequent rebuild.
    """
    now = timestamp if timestamp is not None else int(time.time())
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE index_state
               SET last_updated_at = ?,
                   record_count    = ?,
                   model_name      = COALESCE(?, model_name),
                   model_version   = COALESCE(?, model_version),
                   is_building     = 0
             WHERE index_name = ?
            """,
            (now, record_count, model_name, model_version, index_name),
        )


def mark_building(db_path: Path, index_name: str) -> None:
    """Flag an index as currently being rebuilt."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE index_state SET is_building = 1 WHERE index_name = ?",
            (index_name,),
        )
