"""
Unit tests for cerebra/retrieval/lattice_dedup.py.

11 scenarios covering the D2 routing rules, tiebreakers, non-lattice passthrough,
DB column updates, and event emission.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cerebra._primitives.score_composer import CompositeScore
from cerebra.retrieval.lattice_dedup import dedup_siblings
from cerebra.retrieval.scorer import ScoredCandidate
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations

# ── helpers ───────────────────────────────────────────────────────────────────

def _score(composite: float) -> CompositeScore:
    return CompositeScore(composite=composite, components={}, weights={})


def _candidate(
    record_id: str,
    composite: float,
    sku_address: str | None = None,
    created_at: int | None = None,
) -> ScoredCandidate:
    return ScoredCandidate(
        record_id=record_id,
        step_surfaced="vector",
        retrieval_path="vector",
        score=_score(composite),
        source_path=f"/test/{record_id}.md",
        content_excerpt=f"content for {record_id}",
        sku_address=sku_address,
        created_at=created_at or int(time.time()),
        rank=1,
    )


def _seed_record(
    conn,
    record_id: str,
    *,
    is_lattice_member: int = 0,
    lattice_lineage_id: str | None = None,
    created_at: int | None = None,
) -> None:
    now = created_at or int(time.time())
    src_id = f"src_{record_id}"
    doc_id = f"doc_{record_id}"
    chunk_id = f"chk_{record_id}"
    conn.execute(
        "INSERT OR IGNORE INTO sources "
        "(source_id, canonical_path, content_hash, size_bytes, "
        " detected_type, detection_confidence, parser_status, "
        " lifecycle_state, created_at, schema_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (src_id, f"/test/{record_id}", "h0", 1, "markdown", 1.0, "done", "active", now, 1),
    )
    conn.execute(
        "INSERT OR IGNORE INTO documents "
        "(document_id, source_id, document_type, normalization_confidence, "
        " lifecycle_state, created_at, schema_version) "
        "VALUES (?,?,?,?,?,?,?)",
        (doc_id, src_id, "markdown", 1.0, "active", now, 1),
    )
    conn.execute(
        "INSERT OR IGNORE INTO chunks "
        "(chunk_id, document_id, source_id, heading_path, chunk_index, "
        " depth, content, content_hash, token_estimate, chunk_strategy, "
        " lifecycle_state, created_at, schema_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (chunk_id, doc_id, src_id, "", 0, 0, "test content", "hc0", 5, "fixed", "active", now, 1),
    )
    conn.execute(
        "INSERT OR IGNORE INTO memory_records "
        "(record_id, record_type, source_id, document_id, chunk_id, "
        " content, content_hash, token_estimate, lifecycle_state, "
        " is_lattice_member, lattice_lineage_id, created_at, schema_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            record_id, "source_chunk", src_id, doc_id, chunk_id,
            f"content for {record_id}", "hr0", 5, "active",
            is_lattice_member, lattice_lineage_id, now, 1,
        ),
    )


def _seed_trace(conn, trace_id: str) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO retrieval_traces "
        "(trace_id, query, mode, plan_json, started_at, finished_at, duration_ms, "
        " candidate_count, selected_count, abstained, schema_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (trace_id, "test", "sku", "{}", now, now, 1, 1, 1, 0, 1),
    )


def _seed_candidate(conn, trace_id: str, record_id: str, composite: float) -> None:
    candidate_id = f"cand_{trace_id}_{record_id}"
    score_json = json.dumps({"composite": composite, "components": {}, "weights": {}})
    conn.execute(
        "INSERT OR IGNORE INTO retrieval_candidates "
        "(candidate_id, trace_id, record_id, step_surfaced, retrieval_path, "
        " salience_score, score_json, selected, schema_version) "
        "VALUES (?,?,?,?,?,?,?,?,1)",
        (candidate_id, trace_id, record_id, "vector", "vector", composite, score_json, 1),
    )


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "cerebra.db"
    run_migrations(db_path)
    return db_path


# ── 1. No lattice members → passthrough ──────────────────────────────────────

@pytest.mark.unit
class TestNoLatticeMembers:
    def test_passthrough_unchanged(self, db: Path) -> None:
        """Records with is_lattice_member=0 return unchanged; no DB updates."""
        conn = connect(db)
        _seed_record(conn, "rec_a", is_lattice_member=0)
        _seed_record(conn, "rec_b", is_lattice_member=0)
        _seed_trace(conn, "trace_x")
        _seed_candidate(conn, "trace_x", "rec_a", 0.9)
        _seed_candidate(conn, "trace_x", "rec_b", 0.8)
        conn.commit()
        conn.close()

        candidates = [_candidate("rec_a", 0.9), _candidate("rec_b", 0.8)]
        result = dedup_siblings(candidates, None, db, "trace_x")

        assert len(result) == 2
        assert {c.record_id for c in result} == {"rec_a", "rec_b"}


# ── 2. Single-member lineage → passthrough ───────────────────────────────────

@pytest.mark.unit
class TestSingleMemberLineage:
    def test_single_sibling_passthrough(self, db: Path) -> None:
        """One lattice member with no sibling: passes through, no event emitted."""
        conn = connect(db)
        _seed_record(conn, "rec_lone", is_lattice_member=1, lattice_lineage_id="lin_001")
        _seed_trace(conn, "trace_lone")
        _seed_candidate(conn, "trace_lone", "rec_lone", 0.75)
        conn.commit()
        conn.close()

        candidates = [_candidate("rec_lone", 0.75)]
        mock_log = MagicMock()
        result = dedup_siblings(candidates, None, db, "trace_lone", event_log=mock_log)

        assert len(result) == 1
        assert result[0].record_id == "rec_lone"
        mock_log.write.assert_not_called()


# ── 3. Two siblings, no query D1 → highest composite wins ────────────────────

@pytest.mark.unit
class TestTwoSiblingsNoQueryD1:
    def test_higher_score_wins(self, db: Path) -> None:
        """No query_d1 → composite_score basis; higher-score sibling wins."""
        conn = connect(db)
        _seed_record(conn, "rec_hi", is_lattice_member=1, lattice_lineage_id="lin_002")
        _seed_record(conn, "rec_lo", is_lattice_member=1, lattice_lineage_id="lin_002")
        _seed_trace(conn, "trace_nosq")
        _seed_candidate(conn, "trace_nosq", "rec_hi", 0.90)
        _seed_candidate(conn, "trace_nosq", "rec_lo", 0.70)
        conn.commit()
        conn.close()

        candidates = [_candidate("rec_hi", 0.90), _candidate("rec_lo", 0.70)]
        result = dedup_siblings(candidates, None, db, "trace_nosq")

        assert len(result) == 1
        assert result[0].record_id == "rec_hi"

    def test_loser_has_lattice_sibling_exclusion(self, db: Path) -> None:
        """Loser row in retrieval_candidates gets exclusion_reason='lattice_sibling'."""
        conn = connect(db)
        _seed_record(conn, "rec_w2", is_lattice_member=1, lattice_lineage_id="lin_003")
        _seed_record(conn, "rec_l2", is_lattice_member=1, lattice_lineage_id="lin_003")
        _seed_trace(conn, "trace_ex")
        _seed_candidate(conn, "trace_ex", "rec_w2", 0.85)
        _seed_candidate(conn, "trace_ex", "rec_l2", 0.65)
        conn.commit()
        conn.close()

        candidates = [_candidate("rec_w2", 0.85), _candidate("rec_l2", 0.65)]
        dedup_siblings(candidates, None, db, "trace_ex")

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT exclusion_reason FROM retrieval_candidates "
                "WHERE candidate_id = ?",
                ("cand_trace_ex_rec_l2",),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["exclusion_reason"] == "lattice_sibling"


# ── 4. query_d1 exact match → sku_match ──────────────────────────────────────

@pytest.mark.unit
class TestSKUMatchRouting:
    def test_sku_match_picks_matching_sibling(self, db: Path) -> None:
        """Exactly one sibling matches query_d1 → routing_basis=sku_match."""
        conn = connect(db)
        _seed_record(conn, "rec_ma", is_lattice_member=1, lattice_lineage_id="lin_004",
                     created_at=1000)
        _seed_record(conn, "rec_mb", is_lattice_member=1, lattice_lineage_id="lin_004",
                     created_at=1001)
        _seed_trace(conn, "trace_sk")
        _seed_candidate(conn, "trace_sk", "rec_ma", 0.70)
        _seed_candidate(conn, "trace_sk", "rec_mb", 0.90)  # higher score but wrong D1
        conn.commit()
        conn.close()

        # rec_ma has D1="alpha"; rec_mb has D1="beta"; query_d1="alpha" → rec_ma wins
        ca = _candidate("rec_ma", 0.70, sku_address="alpha::d2::d3")
        cb = _candidate("rec_mb", 0.90, sku_address="beta::d2::d3")
        result = dedup_siblings([ca, cb], "alpha", db, "trace_sk")

        assert len(result) == 1
        assert result[0].record_id == "rec_ma"

    def test_sku_match_basis_stored_in_db(self, db: Path) -> None:
        """Winner's retrieval_candidates row gets lattice_routing_basis='sku_match'."""
        conn = connect(db)
        _seed_record(conn, "rec_ska", is_lattice_member=1, lattice_lineage_id="lin_005")
        _seed_record(conn, "rec_skb", is_lattice_member=1, lattice_lineage_id="lin_005")
        _seed_trace(conn, "trace_skb")
        _seed_candidate(conn, "trace_skb", "rec_ska", 0.70)
        _seed_candidate(conn, "trace_skb", "rec_skb", 0.80)
        conn.commit()
        conn.close()

        ca = _candidate("rec_ska", 0.70, sku_address="zz::d2::d3")
        cb = _candidate("rec_skb", 0.80, sku_address="qq::d2::d3")
        dedup_siblings([ca, cb], "zz", db, "trace_skb")

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT lattice_routing_basis, lattice_sibling_count, "
                "       lattice_winner_record_id "
                "FROM retrieval_candidates WHERE candidate_id = ?",
                ("cand_trace_skb_rec_ska",),
            ).fetchone()
        finally:
            conn.close()
        assert row["lattice_routing_basis"] == "sku_match"
        assert row["lattice_sibling_count"] == 2
        assert row["lattice_winner_record_id"] == "rec_ska"


# ── 5. No D1 match → composite_score ─────────────────────────────────────────

@pytest.mark.unit
class TestNoD1Match:
    def test_no_match_uses_composite(self, db: Path) -> None:
        """query_d1 provided but no sibling matches → composite_score routing."""
        conn = connect(db)
        _seed_record(conn, "rec_nm1", is_lattice_member=1, lattice_lineage_id="lin_006")
        _seed_record(conn, "rec_nm2", is_lattice_member=1, lattice_lineage_id="lin_006")
        _seed_trace(conn, "trace_nm")
        _seed_candidate(conn, "trace_nm", "rec_nm1", 0.60)
        _seed_candidate(conn, "trace_nm", "rec_nm2", 0.85)
        conn.commit()
        conn.close()

        ca = _candidate("rec_nm1", 0.60, sku_address="aaa::d2")
        cb = _candidate("rec_nm2", 0.85, sku_address="bbb::d2")
        result = dedup_siblings([ca, cb], "zzz", db, "trace_nm")

        assert len(result) == 1
        assert result[0].record_id == "rec_nm2"


# ── 6. Multiple D1 matches → sku_match_multi ─────────────────────────────────

@pytest.mark.unit
class TestSKUMatchMulti:
    def test_multi_match_highest_composite_wins(self, db: Path) -> None:
        """Multiple siblings match query_d1 → sku_match_multi; highest composite wins."""
        conn = connect(db)
        for rec in ("rec_mm1", "rec_mm2", "rec_mm3"):
            _seed_record(conn, rec, is_lattice_member=1, lattice_lineage_id="lin_007")
        _seed_trace(conn, "trace_mm")
        for rec, score in [("rec_mm1", 0.70), ("rec_mm2", 0.85), ("rec_mm3", 0.60)]:
            _seed_candidate(conn, "trace_mm", rec, score)
        conn.commit()
        conn.close()

        ca = _candidate("rec_mm1", 0.70, sku_address="xx::d2")
        cb = _candidate("rec_mm2", 0.85, sku_address="xx::d2")  # highest, same D1
        cc = _candidate("rec_mm3", 0.60, sku_address="xx::d2")
        result = dedup_siblings([ca, cb, cc], "xx", db, "trace_mm")

        assert len(result) == 1
        assert result[0].record_id == "rec_mm2"

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT lattice_routing_basis FROM retrieval_candidates "
                "WHERE candidate_id = 'cand_trace_mm_rec_mm2'"
            ).fetchone()
        finally:
            conn.close()
        assert row["lattice_routing_basis"] == "sku_match_multi"


# ── 7. Tiebreak by created_at ─────────────────────────────────────────────────

@pytest.mark.unit
class TestTiebreakByCreatedAt:
    def test_earlier_created_at_wins_on_tie(self, db: Path) -> None:
        """Equal composite scores → earliest created_at wins; basis=earliest_promotion."""
        conn = connect(db)
        _seed_record(conn, "rec_early", is_lattice_member=1, lattice_lineage_id="lin_008",
                     created_at=500)
        _seed_record(conn, "rec_late", is_lattice_member=1, lattice_lineage_id="lin_008",
                     created_at=9999)
        _seed_trace(conn, "trace_tie")
        _seed_candidate(conn, "trace_tie", "rec_early", 0.75)
        _seed_candidate(conn, "trace_tie", "rec_late", 0.75)
        conn.commit()
        conn.close()

        ca = _candidate("rec_early", 0.75, created_at=500)
        cb = _candidate("rec_late", 0.75, created_at=9999)
        result = dedup_siblings([ca, cb], None, db, "trace_tie")

        assert len(result) == 1
        assert result[0].record_id == "rec_early"

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT lattice_routing_basis FROM retrieval_candidates "
                "WHERE candidate_id = 'cand_trace_tie_rec_early'"
            ).fetchone()
        finally:
            conn.close()
        assert row["lattice_routing_basis"] == "earliest_promotion"


# ── 8. Non-lattice candidates preserved ──────────────────────────────────────

@pytest.mark.unit
class TestNonLatticeCandidatesPreserved:
    def test_mix_lattice_and_non_lattice(self, db: Path) -> None:
        """Non-lattice candidates are always included in the output."""
        conn = connect(db)
        _seed_record(conn, "rec_lat1", is_lattice_member=1, lattice_lineage_id="lin_009")
        _seed_record(conn, "rec_lat2", is_lattice_member=1, lattice_lineage_id="lin_009")
        _seed_record(conn, "rec_norm", is_lattice_member=0)
        _seed_trace(conn, "trace_mix")
        _seed_candidate(conn, "trace_mix", "rec_lat1", 0.90)
        _seed_candidate(conn, "trace_mix", "rec_lat2", 0.70)
        _seed_candidate(conn, "trace_mix", "rec_norm", 0.80)
        conn.commit()
        conn.close()

        candidates = [
            _candidate("rec_lat1", 0.90),
            _candidate("rec_lat2", 0.70),
            _candidate("rec_norm", 0.80),
        ]
        result = dedup_siblings(candidates, None, db, "trace_mix")

        record_ids = {c.record_id for c in result}
        assert "rec_lat1" in record_ids   # winner
        assert "rec_lat2" not in record_ids  # loser
        assert "rec_norm" in record_ids   # non-lattice preserved
        assert len(result) == 2


# ── 9. LatticeSiblingResolved event emission ──────────────────────────────────

@pytest.mark.unit
class TestEventEmission:
    def test_event_emitted_per_group(self, db: Path) -> None:
        """One LatticeSiblingResolved event emitted per sibling group resolved."""
        conn = connect(db)
        _seed_record(conn, "rec_ev1", is_lattice_member=1, lattice_lineage_id="lin_010")
        _seed_record(conn, "rec_ev2", is_lattice_member=1, lattice_lineage_id="lin_010")
        _seed_trace(conn, "trace_ev")
        _seed_candidate(conn, "trace_ev", "rec_ev1", 0.80)
        _seed_candidate(conn, "trace_ev", "rec_ev2", 0.60)
        conn.commit()
        conn.close()

        mock_log = MagicMock()
        candidates = [_candidate("rec_ev1", 0.80), _candidate("rec_ev2", 0.60)]
        dedup_siblings(candidates, None, db, "trace_ev", event_log=mock_log)

        mock_log.write.assert_called_once()
        event = mock_log.write.call_args[0][0]
        assert event.event_type == "LatticeSiblingResolved"
        assert event.data["lineage_id"] == "lin_010"
        assert event.data["sibling_count"] == 2
        assert event.data["winner_record_id"] == "rec_ev1"
        assert event.data["routing_basis"] == "composite_score"

    def test_no_event_for_no_siblings(self, db: Path) -> None:
        """No event emitted when no multi-member lineage groups exist."""
        conn = connect(db)
        _seed_record(conn, "rec_noev", is_lattice_member=1, lattice_lineage_id="lin_011")
        _seed_trace(conn, "trace_noev")
        _seed_candidate(conn, "trace_noev", "rec_noev", 0.75)
        conn.commit()
        conn.close()

        mock_log = MagicMock()
        candidates = [_candidate("rec_noev", 0.75)]
        dedup_siblings(candidates, None, db, "trace_noev", event_log=mock_log)

        mock_log.write.assert_not_called()
