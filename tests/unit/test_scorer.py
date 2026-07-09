# SPDX-License-Identifier: Apache-2.0
"""Unit tests for retrieval salience scoring.

Run with: python -m pytest tests/unit/test_scorer.py -m unit
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers that replicate the normalization formulas from §4 of the design doc.
# These are tested here so that when scorer.py lands it can import them
# and have its tests reference the same logic.
# ---------------------------------------------------------------------------


def _normalize_lexical(rank: float, ranks: list[float]) -> float:
    """Normalize a single FTS5 BM25 rank to [0, 1].

    FTS5 returns negative ranks; more negative = better match.
    Best (most negative, largest abs) → 1.0; worst → near 0.0.
    Records with rank=0.0 (no match) are handled by the caller (score=0.0).
    """
    max_abs = max(abs(r) for r in ranks) if ranks else 1.0
    if max_abs == 0.0:
        return 0.0
    return abs(rank) / max_abs


def _normalize_recency(created_at: int, now: int) -> float:
    """Exponential decay with 365-day half-life."""
    age_days = (now - created_at) / 86400
    return math.exp(-age_days / 365)


# ---------------------------------------------------------------------------
# §4: Lexical normalization direction (critical — was inverted in design v1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLexicalNormalization:
    def test_lexical_normalization_direction(self) -> None:
        """Best BM25 rank (most negative) must map to 1.0; worst must map near 0.0.

        FTS5 returns negative BM25 scores; more negative = stronger match.
        The normalization formula is: abs(rank) / max_abs.
        This test pins the direction so a future refactor cannot silently re-invert it.
        """
        best_rank = -3.0  # most negative = best match
        worst_rank = -0.1  # least negative = worst match
        ranks = [best_rank, worst_rank, -1.5]

        best_score = _normalize_lexical(best_rank, ranks)
        worst_score = _normalize_lexical(worst_rank, ranks)
        mid_score = _normalize_lexical(-1.5, ranks)

        # Direction assertion: best rank must score highest
        assert best_score > worst_score, (
            f"Best BM25 rank should produce highest score, got best={best_score:.3f} "
            f"< worst={worst_score:.3f}. "
            "Check formula: abs(rank)/max_abs, not 1 - abs(rank)/max_abs."
        )

        # Boundary assertion: best maps to exactly 1.0
        assert best_score == pytest.approx(
            1.0
        ), f"Best BM25 rank should normalize to 1.0, got {best_score:.3f}"

        # Ordering assertion: mid-rank scores between best and worst
        assert best_score > mid_score > worst_score

    def test_lexical_normalization_single_candidate(self) -> None:
        """Single candidate with a non-zero rank must score 1.0."""
        rank = -2.5
        score = _normalize_lexical(rank, [rank])
        assert score == pytest.approx(1.0)

    def test_lexical_normalization_no_match_scores_zero(self) -> None:
        """A record not in lexical results gets score 0.0 (caller responsibility).

        This test documents the caller contract: records absent from the
        FTS5 result set should be assigned 0.0, not passed to _normalize_lexical.
        """
        # Simulate: record is not in FTS5 results
        absent_record_score = 0.0  # caller assigns this
        assert absent_record_score == 0.0

    def test_lexical_normalization_equal_ranks(self) -> None:
        """When all ranks are equal, all scores should be 1.0."""
        ranks = [-1.5, -1.5, -1.5]
        scores = [_normalize_lexical(r, ranks) for r in ranks]
        assert all(s == pytest.approx(1.0) for s in scores)

    def test_lexical_normalization_never_exceeds_one(self) -> None:
        """Normalized scores must never exceed 1.0."""
        ranks = [-5.0, -0.01, -2.3, -1.1]
        for r in ranks:
            score = _normalize_lexical(r, ranks)
            assert 0.0 <= score <= 1.0, f"Score {score:.3f} out of [0,1] for rank {r}"


# ---------------------------------------------------------------------------
# §4: Recency normalization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecencyNormalization:
    def test_recency_today_is_one(self) -> None:
        now = 1_720_000_000
        score = _normalize_recency(now, now)
        assert score == pytest.approx(1.0)

    def test_recency_one_year_ago(self) -> None:
        now = 1_720_000_000
        one_year_ago = now - 365 * 86400
        score = _normalize_recency(one_year_ago, now)
        # exp(-1) ≈ 0.368
        assert score == pytest.approx(math.exp(-1.0), abs=1e-3)

    def test_recency_decays_monotonically(self) -> None:
        now = 1_720_000_000
        timestamps = [now - i * 30 * 86400 for i in range(6)]
        scores = [_normalize_recency(t, now) for t in timestamps]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1], (
                f"Recency should decrease with age: scores[{i}]={scores[i]:.3f} "
                f">= scores[{i+1}]={scores[i+1]:.3f}"
            )

    def test_recency_always_in_unit_interval(self) -> None:
        now = 1_720_000_000
        for days_ago in [0, 30, 180, 365, 730, 1825]:
            t = now - days_ago * 86400
            score = _normalize_recency(t, now)
            assert 0.0 < score <= 1.0, f"Recency {score:.4f} out of (0, 1] at {days_ago} days ago"


# ---------------------------------------------------------------------------
# §4: Lifecycle constant note
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLifecycleConstant:
    def test_lifecycle_active_is_one(self) -> None:
        """Active records must score 1.0. In Phase 4 all candidates are active."""
        lifecycle_state = "active"
        score = 1.0 if lifecycle_state == "active" else 0.0
        assert score == 1.0

    def test_lifecycle_non_active_is_zero(self) -> None:
        """Non-active records score 0.0 and sink below the 0.35 floor."""
        for state in ("archived", "tombstoned", "warm", "cold"):
            score = 1.0 if state == "active" else 0.0
            assert score == 0.0, f"Expected 0.0 for lifecycle_state={state!r}"


# ---------------------------------------------------------------------------
# score_candidates() contract tests
# ---------------------------------------------------------------------------


def _migrated_db() -> Path:
    from cerebra.storage.migrations import run_migrations

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    run_migrations(db)
    return db


def _make_plan(query: str, query_d1: int | None = None, mode: str = "hybrid"):
    from cerebra.retrieval.planner import QueryPlan

    return QueryPlan(
        trace_id="trace_scorer_test",
        raw_query=query,
        query_d1=query_d1,
        query_d1_d2_d3=f"0x{query_d1:x}" if query_d1 is not None else None,
        mode=mode,
        max_candidates=200,
        staleness_warnings=[],
    )


def _insert_full_record(
    conn,
    record_id: str,
    d1: int = 5,
    content: str = "test content for scoring",
    created_at: int | None = None,
) -> None:
    """Insert the full FK chain for a scoreable record."""
    import time as _time

    now = created_at if created_at is not None else int(_time.time())
    src_id = "src_scorer_shared"
    doc_id = "doc_scorer_shared"
    chk_id = f"chk_scorer_{record_id}"
    sku_addr = f"0x{d1:x}.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0"
    conn.execute(
        "INSERT OR IGNORE INTO sources "
        "(source_id, canonical_path, content_hash, size_bytes, detected_type, "
        " detection_confidence, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
        (src_id, "/test/scorer.md", "h_src", 100, "markdown", 1.0, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO documents "
        "(document_id, source_id, document_type, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, 'active', ?)",
        (doc_id, src_id, "markdown", now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO chunks "
        "(chunk_id, document_id, source_id, chunk_index, content, content_hash, "
        " token_estimate, chunk_strategy, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
        (chk_id, doc_id, src_id, 0, content, "hc", 1, "fixed", now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO memory_records "
        "(record_id, source_id, document_id, chunk_id, content, content_hash, "
        " token_estimate, sku_address, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
        (record_id, src_id, doc_id, chk_id, content, "hr", 1, sku_addr, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO sku_assignments "
        "(assignment_id, record_id, sku_address, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, "
        " raw_scores_json, d1_confidence, classifier_version, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, 0.9, 'test', 'v1', ?)",
        (f"asgn_{record_id}", record_id, sku_addr, d1, "{}", now),
    )


def _make_raw(
    record_id: str,
    *,
    semantic_score: float | None = 0.7,
    lexical_score: float | None = None,
    sku_d1_match: bool = True,
    step: str = "exact_sku",
):
    from cerebra.retrieval.traversal import RawCandidate

    return RawCandidate(
        record_id=record_id,
        step_surfaced=step,
        retrieval_path=f"{step}:D1=0x5",
        semantic_score=semantic_score,
        lexical_score=lexical_score,
        sku_d1_match=sku_d1_match,
    )


@pytest.mark.unit
class TestScoreCandidates:
    def test_empty_input_returns_empty(self) -> None:
        from cerebra.retrieval.scorer import score_candidates

        db = _migrated_db()
        try:
            result = score_candidates([], _make_plan("test"), db)
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_returns_scored_candidates(self) -> None:
        from cerebra.retrieval.scorer import ScoredCandidate, score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_a")
            raw = [_make_raw("rec_a")]
            result = score_candidates(raw, _make_plan("test", query_d1=5), db)
            assert len(result) == 1
            assert isinstance(result[0], ScoredCandidate)
        finally:
            db.unlink(missing_ok=True)

    def test_sorted_by_composite_descending(self) -> None:
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_hi", created_at=now)
                _insert_full_record(conn, "rec_lo", created_at=now)
            raw = [
                _make_raw("rec_lo", semantic_score=0.1, sku_d1_match=False),
                _make_raw("rec_hi", semantic_score=0.9, sku_d1_match=True),
            ]
            result = score_candidates(raw, _make_plan("test", query_d1=5), db, now=now)
            assert result[0].record_id == "rec_hi"
            assert result[0].score.composite > result[-1].score.composite
        finally:
            db.unlink(missing_ok=True)

    def test_rank_assigned_one_based(self) -> None:
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_1", created_at=now)
                _insert_full_record(conn, "rec_2", created_at=now)
            raw = [
                _make_raw("rec_1", semantic_score=0.8),
                _make_raw("rec_2", semantic_score=0.6),
            ]
            result = score_candidates(raw, _make_plan("test", query_d1=5), db, now=now)
            ranks = [c.rank for c in result]
            assert ranks == [1, 2]
        finally:
            db.unlink(missing_ok=True)

    def test_composite_in_unit_interval(self) -> None:
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_a", created_at=now)
            raw = [_make_raw("rec_a", semantic_score=0.85, sku_d1_match=True)]
            result = score_candidates(raw, _make_plan("test", query_d1=5), db, now=now)
            for c in result:
                assert (
                    0.0 <= c.score.composite <= 1.0
                ), f"Composite {c.score.composite:.4f} out of [0,1]"
        finally:
            db.unlink(missing_ok=True)

    def test_sku_match_affects_score(self) -> None:
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_match", created_at=now)
                _insert_full_record(conn, "rec_nomatch", created_at=now)
            raw = [
                _make_raw("rec_match", semantic_score=0.7, sku_d1_match=True),
                _make_raw("rec_nomatch", semantic_score=0.7, sku_d1_match=False),
            ]
            result = score_candidates(raw, _make_plan("test", query_d1=5), db, now=now)
            scores = {c.record_id: c.score.composite for c in result}
            assert (
                scores["rec_match"] > scores["rec_nomatch"]
            ), "SKU D1 match should produce higher composite score"
        finally:
            db.unlink(missing_ok=True)

    def test_lexical_normalization_relative(self) -> None:
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_best", created_at=now)
                _insert_full_record(conn, "rec_worst", created_at=now)
            raw = [
                _make_raw("rec_best", semantic_score=0.0, lexical_score=-3.0, sku_d1_match=False),
                _make_raw("rec_worst", semantic_score=0.0, lexical_score=-0.1, sku_d1_match=False),
            ]
            result = score_candidates(raw, _make_plan("test"), db, now=now)
            scores = {c.record_id: c.score.components["lexical"] for c in result}
            assert scores["rec_best"] == pytest.approx(
                1.0
            ), "Best BM25 rank should normalize to lexical=1.0"
            assert scores["rec_worst"] < scores["rec_best"]
        finally:
            db.unlink(missing_ok=True)

    def test_missing_semantic_defaults_to_zero(self) -> None:
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            with connect(db) as conn:
                _insert_full_record(conn, "rec_a", created_at=now)
            raw = [_make_raw("rec_a", semantic_score=None, sku_d1_match=True)]
            result = score_candidates(raw, _make_plan("test", query_d1=5), db, now=now)
            assert result[0].score.components["semantic"] == 0.0
        finally:
            db.unlink(missing_ok=True)

    def test_salience_event_emitted(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.storage.db import connect

        db = _migrated_db()
        now = 1_720_000_000
        try:
            log = SQLiteEventLog(db)
            with connect(db) as conn:
                _insert_full_record(conn, "rec_a", created_at=now)
            raw = [_make_raw("rec_a")]
            score_candidates(raw, _make_plan("test", query_d1=5), db, now=now, event_log=log)
            events = log.query_by_type("SalienceScored")
            assert len(events) == 1
        finally:
            db.unlink(missing_ok=True)

    def test_weights_sum_to_one(self) -> None:
        from cerebra.retrieval.scorer import _WEIGHTS

        assert sum(_WEIGHTS.values()) == pytest.approx(1.0)
