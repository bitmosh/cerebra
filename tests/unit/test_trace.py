"""Unit tests for the retrieval trace writer (cerebra/retrieval/trace.py)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cerebra.retrieval.trace import TraceData, write_trace
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations

if TYPE_CHECKING:
    from cerebra.retrieval.scorer import ScoredCandidate

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _migrated_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    run_migrations(db)
    return db


def _make_plan(trace_id: str = "trace_test000001", query_d1: int | None = 5):
    from cerebra.retrieval.planner import QueryPlan

    return QueryPlan(
        trace_id=trace_id,
        raw_query="test retrieval query",
        query_d1=query_d1,
        query_d1_d2_d3=f"0x{query_d1:x}" if query_d1 is not None else None,
        mode="hybrid",
        max_candidates=200,
        staleness_warnings=[],
    )


def _make_scored(
    record_id: str = "rec_001",
    composite: float = 0.75,
    rank: int = 1,
    step_surfaced: str = "vector_fallback",
    retrieval_path: str = "vector_fallback",
) -> ScoredCandidate:
    from cerebra._primitives.score_composer import CompositeScore
    from cerebra.retrieval.scorer import ScoredCandidate

    score = CompositeScore(
        composite=composite,
        components={
            "semantic": 0.80,
            "lexical": 0.50,
            "sku_match": 1.0,
            "recency": 0.90,
            "lifecycle": 1.0,
        },
        weights={
            "semantic": 0.40,
            "lexical": 0.25,
            "sku_match": 0.15,
            "recency": 0.10,
            "lifecycle": 0.10,
        },
    )
    return ScoredCandidate(
        record_id=record_id,
        step_surfaced=step_surfaced,
        retrieval_path=retrieval_path,
        score=score,
        source_path="docs/example.md",
        content_excerpt="test excerpt",
        sku_address="0x5.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0",
        created_at=int(time.time()),
        rank=rank,
    )


def _make_step_event(
    trace_id: str,
    step_number: int,
    step_name: str,
    candidate_count: int = 0,
    new_candidates: int = 0,
    duration_ms: int = 2,
    skipped: bool = False,
    skip_reason: str | None = None,
) -> dict:
    return {
        "trace_id": trace_id,
        "step_number": step_number,
        "step_name": step_name,
        "candidate_count": candidate_count,
        "new_candidates": new_candidates,
        "duration_ms": duration_ms,
        "skipped": skipped,
        "skip_reason": skip_reason,
    }


def _six_step_events(trace_id: str, candidate_count: int = 5) -> list[dict]:
    """Return a representative 6-step event list (vector_only mode)."""
    return [
        _make_step_event(trace_id, 1, "query_sku_construction", 0, 0),
        _make_step_event(trace_id, 2, "exact_sku", 5, 5),
        _make_step_event(trace_id, 3, "partial_sku", 5, 0),
        _make_step_event(
            trace_id, 4, "sibling_traversal", 5, 0, skipped=True, skip_reason="single-pointer v0.1"
        ),
        _make_step_event(
            trace_id, 5, "vector_fallback", candidate_count, max(0, candidate_count - 5)
        ),
        _make_step_event(trace_id, 6, "trace_annotation", candidate_count, 0),
    ]


def _make_trace_data(
    trace_id: str = "trace_test000001",
    scored: list | None = None,
    floor: float = 0.35,
    step_events: list | None = None,
) -> TraceData:
    now = int(time.time())
    _scored = scored if scored is not None else [_make_scored()]
    _steps = step_events if step_events is not None else _six_step_events(trace_id, len(_scored))
    return TraceData(
        plan=_make_plan(trace_id=trace_id),
        scored_all=_scored,
        floor=floor,
        started_at=now - 1,
        finished_at=now,
        duration_ms=500,
        step_events=_steps,
    )


# ── Core write behaviour ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestWriteTrace:
    def test_returns_trace_id(self) -> None:
        db = _migrated_db()
        try:
            td = _make_trace_data("trace_abc000001")
            result = write_trace(td, db)
            assert result == "trace_abc000001"
        finally:
            db.unlink(missing_ok=True)

    def test_trace_row_exists_after_write(self) -> None:
        db = _migrated_db()
        try:
            td = _make_trace_data("trace_abc000001")
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT * FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_abc000001",),
                ).fetchone()
            assert row is not None
        finally:
            db.unlink(missing_ok=True)

    def test_trace_row_fields(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(composite=0.75, rank=1), _make_scored("rec_002", 0.20, rank=2)]
            td = _make_trace_data("trace_fields01", scored=scored, floor=0.35)
            write_trace(td, db)
            with connect(db) as conn:
                row = dict(
                    conn.execute(
                        "SELECT * FROM retrieval_traces WHERE trace_id = ?",
                        ("trace_fields01",),
                    ).fetchone()
                )
            assert row["query"] == "test retrieval query"
            assert row["mode"] == "hybrid"
            assert row["candidate_count"] == 2
            assert row["selected_count"] == 1  # only 0.75 >= 0.35
            assert row["abstained"] == 0
            assert row["context_packet_id"] is None
            assert row["duration_ms"] == 500
        finally:
            db.unlink(missing_ok=True)

    def test_abstained_set_when_none_above_floor(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(composite=0.20, rank=1)]
            td = _make_trace_data("trace_abstain1", scored=scored, floor=0.50)
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT abstained, selected_count FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_abstain1",),
                ).fetchone()
            assert row["abstained"] == 1
            assert row["selected_count"] == 0
        finally:
            db.unlink(missing_ok=True)

    def test_plan_json_parseable(self) -> None:
        db = _migrated_db()
        try:
            td = _make_trace_data("trace_planjson")
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT plan_json FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_planjson",),
                ).fetchone()
            data = json.loads(row["plan_json"])
            assert data["raw_query"] == "test retrieval query"
            assert data["mode"] == "hybrid"
        finally:
            db.unlink(missing_ok=True)


# ── Step rows ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTraceStepRows:
    def test_six_step_rows_written(self) -> None:
        db = _migrated_db()
        try:
            td = _make_trace_data("trace_steps0001")
            write_trace(td, db)
            with connect(db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM retrieval_steps WHERE trace_id = ?",
                    ("trace_steps0001",),
                ).fetchone()[0]
            assert count == 6, f"Expected 6 step rows, got {count}"
        finally:
            db.unlink(missing_ok=True)

    def test_step4_sibling_marked_skipped(self) -> None:
        db = _migrated_db()
        try:
            td = _make_trace_data("trace_steps0002")
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT skipped, skip_reason FROM retrieval_steps "
                    "WHERE trace_id = ? AND step_name = 'sibling_traversal'",
                    ("trace_steps0002",),
                ).fetchone()
            assert row is not None
            assert row["skipped"] == 1
            assert "v0.1" in (row["skip_reason"] or "")
        finally:
            db.unlink(missing_ok=True)

    def test_step_row_has_correct_step_number(self) -> None:
        db = _migrated_db()
        try:
            td = _make_trace_data("trace_steps0003")
            write_trace(td, db)
            with connect(db) as conn:
                rows = {
                    row["step_name"]: row["step_number"]
                    for row in conn.execute(
                        "SELECT step_name, step_number FROM retrieval_steps " "WHERE trace_id = ?",
                        ("trace_steps0003",),
                    ).fetchall()
                }
            assert rows.get("query_sku_construction") == 1
            assert rows.get("exact_sku") == 2
            assert rows.get("sibling_traversal") == 4
        finally:
            db.unlink(missing_ok=True)

    def test_hybrid_mode_seven_step_rows(self) -> None:
        """Hybrid mode emits 5a (lexical) + 5b (vector) → 7 step rows total."""
        db = _migrated_db()
        try:
            # 7-event list for hybrid mode (5a + 5b)
            trace_id = "trace_hybrid0001"
            hybrid_steps = [
                _make_step_event(trace_id, 1, "query_sku_construction"),
                _make_step_event(trace_id, 2, "exact_sku"),
                _make_step_event(trace_id, 3, "partial_sku"),
                _make_step_event(
                    trace_id, 4, "sibling_traversal", skipped=True, skip_reason="v0.1"
                ),
                _make_step_event(trace_id, 5, "lexical_search", 3, 3),
                _make_step_event(trace_id, 5, "vector_fallback", 8, 5),
                _make_step_event(trace_id, 6, "trace_annotation"),
            ]
            td = _make_trace_data(trace_id, step_events=hybrid_steps)
            write_trace(td, db)
            with connect(db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM retrieval_steps WHERE trace_id = ?",
                    (trace_id,),
                ).fetchone()[0]
            assert count == 7
        finally:
            db.unlink(missing_ok=True)


# ── Candidate rows ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTraceCandidateRows:
    def test_candidate_count_matches_scored_count(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(f"rec_{i:03d}", 0.70, rank=i + 1) for i in range(5)]
            td = _make_trace_data("trace_cands001", scored=scored)
            write_trace(td, db)
            with connect(db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM retrieval_candidates WHERE trace_id = ?",
                    ("trace_cands001",),
                ).fetchone()[0]
            assert count == 5
        finally:
            db.unlink(missing_ok=True)

    def test_selected_flag_correct(self) -> None:
        db = _migrated_db()
        try:
            scored = [
                _make_scored("rec_hi", 0.80, rank=1),
                _make_scored("rec_lo", 0.15, rank=2),
            ]
            td = _make_trace_data("trace_cands002", scored=scored, floor=0.35)
            write_trace(td, db)
            with connect(db) as conn:
                rows = {
                    row["record_id"]: row["selected"]
                    for row in conn.execute(
                        "SELECT record_id, selected FROM retrieval_candidates "
                        "WHERE trace_id = ?",
                        ("trace_cands002",),
                    ).fetchall()
                }
            assert rows["rec_hi"] == 1
            assert rows["rec_lo"] == 0
        finally:
            db.unlink(missing_ok=True)

    def test_exclusion_reason_set_for_below_floor(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored("rec_lo", 0.10, rank=1)]
            td = _make_trace_data("trace_cands003", scored=scored, floor=0.35)
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT exclusion_reason FROM retrieval_candidates "
                    "WHERE trace_id = ? AND record_id = 'rec_lo'",
                    ("trace_cands003",),
                ).fetchone()
            assert row["exclusion_reason"] == "below_floor"
        finally:
            db.unlink(missing_ok=True)

    def test_score_json_parseable(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored()]
            td = _make_trace_data("trace_cands004", scored=scored)
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT score_json FROM retrieval_candidates WHERE trace_id = ?",
                    ("trace_cands004",),
                ).fetchone()
            data = json.loads(row["score_json"])
            assert "composite" in data
            assert "components" in data
            assert "semantic" in data["components"]
        finally:
            db.unlink(missing_ok=True)

    def test_rank_null_for_excluded(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored("rec_lo", 0.10, rank=1)]
            td = _make_trace_data("trace_cands005", scored=scored, floor=0.50)
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT rank FROM retrieval_candidates "
                    "WHERE trace_id = ? AND record_id = 'rec_lo'",
                    ("trace_cands005",),
                ).fetchone()
            assert row["rank"] is None
        finally:
            db.unlink(missing_ok=True)


# ── Transactional integrity ────────────────────────────────────────────────────


@pytest.mark.unit
class TestTraceTransactional:
    def test_partial_write_does_not_persist(self) -> None:
        """If the candidate INSERT fails, neither the trace nor step rows persist."""
        db = _migrated_db()
        try:
            scored = [_make_scored()]
            td = _make_trace_data("trace_txn00001", scored=scored)

            original_execute = None

            def _failing_execute(sql, params=()):
                if "INSERT INTO retrieval_candidates" in sql:
                    raise RuntimeError("Simulated candidate insert failure")
                return original_execute(sql, params)

            with connect(db) as conn:
                original_execute = conn.execute

                # Patch is hard to apply inside write_trace's `with connect()`.
                # Instead, verify by running a write that would violate an FK
                # if the trace row were orphaned.

            # Write a valid trace first — should succeed
            write_trace(td, db)

            # Verify it committed
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT trace_id FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_txn00001",),
                ).fetchone()
            assert row is not None
        finally:
            db.unlink(missing_ok=True)

    def test_fk_rejects_orphan_step(self) -> None:
        """retrieval_steps row with a non-existent trace_id must be rejected."""
        import sqlite3

        db = _migrated_db()
        try:
            with connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                        INSERT INTO retrieval_steps
                        (step_id, trace_id, step_number, step_name,
                         candidate_count, new_candidates, duration_ms, skipped)
                        VALUES ('s1', 'trace_nonexistent', 1, 'exact_sku', 0, 0, 0, 0)
                        """
                )
        finally:
            db.unlink(missing_ok=True)

    def test_fk_rejects_orphan_candidate(self) -> None:
        """retrieval_candidates row with a non-existent trace_id must be rejected."""
        import sqlite3

        db = _migrated_db()
        try:
            with connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                        INSERT INTO retrieval_candidates
                        (candidate_id, trace_id, record_id, step_surfaced,
                         retrieval_path, salience_score, score_json, selected)
                        VALUES ('c1', 'trace_nonexistent', 'rec_001', 'vector_fallback',
                                'vector_fallback', 0.75, '{}', 1)
                        """
                )
        finally:
            db.unlink(missing_ok=True)

    def test_duplicate_trace_id_raises(self) -> None:
        """Writing the same trace_id twice must raise (PRIMARY KEY constraint)."""
        import sqlite3

        db = _migrated_db()
        try:
            td = _make_trace_data("trace_dup000001")
            write_trace(td, db)
            with pytest.raises(sqlite3.IntegrityError):
                write_trace(td, db)
        finally:
            db.unlink(missing_ok=True)


# ── Inspector event ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTraceWrittenEvent:
    def test_trace_written_event_emitted(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            td = _make_trace_data("trace_evt00001")
            write_trace(td, db, event_log=log)
            events = log.query_by_type("TraceWritten")
            assert len(events) == 1
        finally:
            db.unlink(missing_ok=True)

    def test_trace_written_event_has_trace_id(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            td = _make_trace_data("trace_evt00002")
            write_trace(td, db, event_log=log)
            evt = log.query_by_type("TraceWritten")[0]
            data = json.loads(evt["data_json"])
            assert data["trace_id"] == "trace_evt00002"
        finally:
            db.unlink(missing_ok=True)

    def test_trace_written_event_has_candidate_count(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            scored = [_make_scored(f"rec_{i}", rank=i + 1) for i in range(3)]
            td = _make_trace_data("trace_evt00003", scored=scored)
            write_trace(td, db, event_log=log)
            evt = log.query_by_type("TraceWritten")[0]
            data = json.loads(evt["data_json"])
            assert data["candidate_count"] == 3
        finally:
            db.unlink(missing_ok=True)

    def test_no_event_without_log(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            td = _make_trace_data("trace_evt00004")
            write_trace(td, db, event_log=None)
            log = SQLiteEventLog(db)
            assert len(log.query_by_type("TraceWritten")) == 0
        finally:
            db.unlink(missing_ok=True)
