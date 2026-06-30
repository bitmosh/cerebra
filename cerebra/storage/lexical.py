"""
Lexical index — SQLite FTS5 full-text search over memory_records.

FTS5 content table
──────────────────
`memory_records_fts` is a FTS5 content table pointing at `memory_records`.
FTS5 reads content from `memory_records` at query time rather than storing a
second copy. The FTS index (token frequencies / positions) is maintained
separately and must be updated explicitly — FTS5 does NOT auto-sync when
memory_records is modified.

Update discipline
─────────────────
- build_fts_index: full rebuild from all memory_records. Use after bulk
  lifecycle-state changes or when the index is first created.
- update_fts_index: incremental — intended for NEW records added in an ingest
  batch. Deletes then re-inserts each record in the FTS index. Safe for new
  records (delete is a no-op) and re-indexed unchanged content. If content
  changed since the last index, call build_fts_index for a full rebuild
  instead — incremental delete relies on the current content matching the
  previously indexed content, which may not hold if content was mutated.

Drift detection
───────────────
is_lexical_stale() compares max(memory_records.created_at) against
index_state.last_updated_at for the 'lexical' index. It returns True if any
active record was created after the last build/update, indicating that the
FTS index may be behind. Note: this does not detect lifecycle-state changes
(archived records still in FTS); use build_fts_index to reconcile those.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.db import connect
from cerebra.storage.index_state import get_state, mark_updated, seed_index_state

FTS_TABLE = "memory_records_fts"


# ── Index construction ────────────────────────────────────────────────────────


def build_fts_index(
    db_path: Path,
    *,
    event_log: SQLiteEventLog | None = None,
) -> int:
    """Create or fully rebuild the FTS5 index from all memory_records.

    Creates `memory_records_fts` if it doesn't exist. Clears and repopulates
    the FTS index from all active memory_records rows.

    Uses `content=''` (external content) rather than `content='memory_records'`
    (content table) because FTS5 external content tables support the 'delete'
    command needed for incremental updates, while content tables do not.

    Returns the count of active records indexed. Also updates index_state
    and emits LexicalIndexUpdated.
    """
    t0 = time.monotonic()
    with connect(db_path) as conn:
        # Drop and recreate FTS table for a clean rebuild. DROP removes all
        # shadow tables; CREATE starts fresh. This is the only reliable way
        # to do a full rebuild on external content FTS5 tables in SQLite 3.45
        # (the 'deleteall' command is unsupported in this version).
        conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")
        conn.execute(f"CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5(content, content='')")
        # Only active records are indexed; lifecycle_state filter here avoids
        # returning archived/tombstoned records in search results without needing
        # the JOIN filter (we still filter in search() for safety).
        conn.execute(
            f"INSERT INTO {FTS_TABLE}(rowid, content) "
            "SELECT rowid, content FROM memory_records WHERE lifecycle_state = 'active'"
        )
        count: int
        max_ts: int
        count, max_ts = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(created_at), 0) "
            "FROM memory_records WHERE lifecycle_state = 'active'"
        ).fetchone()

    seed_index_state(db_path)
    # Set last_updated_at to the later of now and max(created_at) so that
    # records with future-looking timestamps are covered by this build.
    ts = max(int(time.time()), max_ts)
    mark_updated(db_path, "lexical", count, timestamp=ts)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if event_log is not None:
        event_log.write(
            make_event(
                event_type="LexicalIndexUpdated",
                actor="lexical",
                summary=f"FTS5 index rebuilt: {count} active records",
                data={
                    "records_indexed": count,
                    "total_records_in_index": count,
                    "duration_ms": duration_ms,
                },
            )
        )

    return count


def update_fts_index(
    db_path: Path,
    record_ids: list[str],
    *,
    event_log: SQLiteEventLog | None = None,
) -> int:
    """Register new records in the FTS index. Returns count found and indexed.

    Intended for use after an ingest batch — pass the newly added record_ids.
    Returns 0 immediately if record_ids is empty.

    Implementation note: uses a full drop-recreate-repopulate rather than
    incremental delete+insert. Reason: SQLite 3.45.1 has a bug where the FTS5
    'delete' command raises "database disk image is malformed" when the FTS
    table was built with zero rows (uninitialized shadow table pages). Since
    build_fts_index is always called before ingest begins and the vault may
    start with zero records, incremental delete is not safe here. The full
    rebuild is correct and fast enough for this use case (sub-millisecond at
    current vault sizes).
    """
    if not record_ids:
        return 0

    t0 = time.monotonic()
    placeholders = ",".join("?" * len(record_ids))

    with connect(db_path) as conn:
        found: int = conn.execute(
            f"SELECT COUNT(*) FROM memory_records WHERE record_id IN ({placeholders})",
            record_ids,
        ).fetchone()[0]

        if found == 0:
            return 0

        # Full rebuild from active records (includes newly inserted ones).
        conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")
        conn.execute(f"CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5(content, content='')")
        conn.execute(
            f"INSERT INTO {FTS_TABLE}(rowid, content) "
            "SELECT rowid, content FROM memory_records WHERE lifecycle_state = 'active'"
        )
        total: int
        max_ts: int
        total, max_ts = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(created_at), 0) "
            "FROM memory_records WHERE lifecycle_state = 'active'"
        ).fetchone()

    seed_index_state(db_path)
    ts = max(int(time.time()), max_ts)
    mark_updated(db_path, "lexical", total, timestamp=ts)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if event_log is not None:
        event_log.write(
            make_event(
                event_type="LexicalIndexUpdated",
                actor="lexical",
                summary=f"FTS5 index updated: {found} records added",
                data={
                    "records_indexed": found,
                    "total_records_in_index": total,
                    "duration_ms": duration_ms,
                },
            )
        )

    return found


# ── Search ────────────────────────────────────────────────────────────────────

_FTS5_SAFE = re.compile(r"[^a-zA-Z0-9\s]")


def _sanitize_fts_query(query: str) -> str:
    """Strip non-alphanumeric characters so raw LLM output is safe for FTS5 MATCH.

    FTS5's query language treats many punctuation characters as operators or
    syntax elements. We keep only alphanumerics and whitespace; everything
    else is replaced with a space, then tokens are rejoined.
    """
    clean = _FTS5_SAFE.sub(" ", query)
    tokens = clean.split()
    if not tokens:
        return ""
    return " ".join(tokens)


def search(
    db_path: Path,
    query: str,
    *,
    limit: int = 20,
) -> list[tuple[str, float]]:
    """Full-text search over active memory_records.

    Returns list of (record_id, rank) ordered by relevance. FTS5 rank is
    negative — more negative means a better match. Returns an empty list if
    the query matches nothing or if the FTS table doesn't exist yet.
    """
    safe_query = _sanitize_fts_query(query)
    if not safe_query:
        return []

    with connect(db_path) as conn:
        # Verify FTS table exists before querying
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (FTS_TABLE,),
        ).fetchone()
        if not exists:
            return []

        rows = conn.execute(
            f"""
            SELECT m.record_id, fts.rank
              FROM {FTS_TABLE} fts
              JOIN memory_records m ON fts.rowid = m.rowid
             WHERE {FTS_TABLE} MATCH ?
               AND m.lifecycle_state = 'active'
             ORDER BY fts.rank
             LIMIT ?
            """,
            (safe_query, limit),
        ).fetchall()
    return [(row["record_id"], float(row["rank"])) for row in rows]


# ── Drift detection ───────────────────────────────────────────────────────────


def is_lexical_stale(db_path: Path) -> bool:
    """Return True if the FTS index may be behind memory_records.

    Stale when:
    - index_state has no row for 'lexical', OR
    - last_updated_at == 0 (never built), OR
    - any active memory_record has created_at > last_updated_at
    """
    state = get_state(db_path, "lexical")
    if state is None or state["last_updated_at"] == 0:
        return True
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(created_at) FROM memory_records WHERE lifecycle_state = 'active'"
        ).fetchone()
    if row and row[0] is not None:
        return int(row[0]) > int(state["last_updated_at"])
    return False
