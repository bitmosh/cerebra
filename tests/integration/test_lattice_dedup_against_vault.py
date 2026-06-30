"""
Integration tests: lattice sibling deduplication against the dev vault.

Seeds synthetic lattice-member records into the dev vault, runs
dedup_siblings() directly, and verifies winner selection and DB column
updates. Does NOT call `cerebra search` or `cerebra context` (those require
a fully indexed vault); instead exercises the dedup function directly against
a real SQLite DB with full migration schema.

All tests skip if the dev vault is absent or numpy is unavailable.

Run with: pytest tests/integration/test_lattice_dedup_against_vault.py -m integration -v
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

numpy = pytest.importorskip(
    "numpy", reason="numpy not available — skipping lattice dedup integration tests"
)

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_db() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    from cerebra.storage.migrations import run_migrations

    run_migrations(_VAULT_DB)
    return _VAULT_DB


# ── seeding helpers ───────────────────────────────────────────────────────────


def _seed_sibling_pair(
    db: Path,
    lineage_id: str,
    rec_a: str,
    rec_b: str,
    score_a: float = 0.90,
    score_b: float = 0.70,
) -> None:
    from cerebra.storage.db import connect

    now = int(time.time())
    src_id = f"src_it_{lineage_id}"
    doc_id = f"doc_it_{lineage_id}"
    chunk_a = f"chk_it_{rec_a}"
    chunk_b = f"chk_it_{rec_b}"
    conn = connect(db)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(source_id, canonical_path, content_hash, size_bytes, "
            " detected_type, detection_confidence, parser_status, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                src_id,
                f"/it/sibling_{lineage_id}",
                "h0",
                1,
                "markdown",
                1.0,
                "done",
                "active",
                now,
                1,
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO documents "
            "(document_id, source_id, document_type, normalization_confidence, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?)",
            (doc_id, src_id, "markdown", 1.0, "active", now, 1),
        )
        for chunk_id in (chunk_a, chunk_b):
            conn.execute(
                "INSERT OR IGNORE INTO chunks "
                "(chunk_id, document_id, source_id, heading_path, chunk_index, "
                " depth, content, content_hash, token_estimate, chunk_strategy, "
                " lifecycle_state, created_at, schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    chunk_id,
                    doc_id,
                    src_id,
                    "",
                    0,
                    0,
                    f"content for {chunk_id}",
                    f"hc_{chunk_id}",
                    5,
                    "fixed",
                    "active",
                    now,
                    1,
                ),
            )
        for rec_id, chunk_id in ((rec_a, chunk_a), (rec_b, chunk_b)):
            conn.execute(
                "INSERT OR IGNORE INTO memory_records "
                "(record_id, record_type, source_id, document_id, chunk_id, "
                " content, content_hash, token_estimate, lifecycle_state, "
                " is_lattice_member, lattice_lineage_id, created_at, schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,1,?,?,1)",
                (
                    rec_id,
                    "source_chunk",
                    src_id,
                    doc_id,
                    chunk_id,
                    f"content for {rec_id}",
                    f"hr_{rec_id}",
                    5,
                    "active",
                    lineage_id,
                    now,
                ),
            )
        trace_id = f"trace_it_{lineage_id}"
        conn.execute(
            "INSERT OR IGNORE INTO retrieval_traces "
            "(trace_id, query, mode, plan_json, started_at, finished_at, "
            " duration_ms, candidate_count, selected_count, abstained, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,1)",
            (trace_id, "it test", "sku", "{}", now, now, 1, 2, 2, 0),
        )
        for rec_id, score in ((rec_a, score_a), (rec_b, score_b)):
            candidate_id = f"cand_{trace_id}_{rec_id}"
            score_json = json.dumps({"composite": score, "components": {}, "weights": {}})
            conn.execute(
                "INSERT OR IGNORE INTO retrieval_candidates "
                "(candidate_id, trace_id, record_id, step_surfaced, retrieval_path, "
                " salience_score, score_json, selected, schema_version) "
                "VALUES (?,?,?,?,?,?,?,1,1)",
                (candidate_id, trace_id, rec_id, "vector", "vector", score, score_json),
            )
        conn.commit()
    finally:
        conn.close()


def _make_scored(
    record_id: str,
    composite: float,
    sku_address: str | None = None,
    created_at: int | None = None,
):
    from cerebra._primitives.score_composer import CompositeScore
    from cerebra.retrieval.scorer import ScoredCandidate

    return ScoredCandidate(
        record_id=record_id,
        step_surfaced="vector",
        retrieval_path="vector",
        score=CompositeScore(composite=composite, components={}, weights={}),
        source_path=f"/it/{record_id}.md",
        content_excerpt=f"content for {record_id}",
        sku_address=sku_address,
        created_at=created_at or int(time.time()),
        rank=1,
    )


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestLatticeDedupAgainstVault:
    def test_two_siblings_winner_by_composite(self, vault_db: Path) -> None:
        """Higher-composite sibling wins in a two-sibling group (no query_d1)."""
        from cerebra.retrieval.lattice_dedup import dedup_siblings

        ts = int(time.time())
        lin = f"it_lin_{ts}_a"
        rec_a, rec_b = f"it_rec_{ts}_a1", f"it_rec_{ts}_a2"
        _seed_sibling_pair(vault_db, lin, rec_a, rec_b, score_a=0.88, score_b=0.65)
        trace_id = f"trace_it_{lin}"

        candidates = [_make_scored(rec_a, 0.88), _make_scored(rec_b, 0.65)]
        result = dedup_siblings(candidates, None, vault_db, trace_id)

        assert len(result) == 1
        assert result[0].record_id == rec_a

    def test_loser_candidate_row_updated(self, vault_db: Path) -> None:
        """Loser's retrieval_candidates row gets exclusion_reason and lattice columns."""
        from cerebra.retrieval.lattice_dedup import dedup_siblings
        from cerebra.storage.db import connect

        ts = int(time.time())
        lin = f"it_lin_{ts}_b"
        rec_a, rec_b = f"it_rec_{ts}_b1", f"it_rec_{ts}_b2"
        _seed_sibling_pair(vault_db, lin, rec_a, rec_b, score_a=0.80, score_b=0.55)
        trace_id = f"trace_it_{lin}"

        candidates = [_make_scored(rec_a, 0.80), _make_scored(rec_b, 0.55)]
        dedup_siblings(candidates, None, vault_db, trace_id)

        conn = connect(vault_db)
        try:
            row = conn.execute(
                "SELECT exclusion_reason, lattice_sibling_count, "
                "       lattice_winner_record_id, lattice_routing_basis "
                "FROM retrieval_candidates WHERE candidate_id = ?",
                (f"cand_{trace_id}_{rec_b}",),
            ).fetchone()
        finally:
            conn.close()

        assert row is not None
        assert row["exclusion_reason"] == "lattice_sibling"
        assert row["lattice_sibling_count"] == 2
        assert row["lattice_winner_record_id"] == rec_a
        assert row["lattice_routing_basis"] == "composite_score"

    def test_winner_candidate_row_updated(self, vault_db: Path) -> None:
        """Winner's retrieval_candidates row gets lattice columns (no exclusion_reason)."""
        from cerebra.retrieval.lattice_dedup import dedup_siblings
        from cerebra.storage.db import connect

        ts = int(time.time())
        lin = f"it_lin_{ts}_c"
        rec_a, rec_b = f"it_rec_{ts}_c1", f"it_rec_{ts}_c2"
        _seed_sibling_pair(vault_db, lin, rec_a, rec_b, score_a=0.75, score_b=0.40)
        trace_id = f"trace_it_{lin}"

        candidates = [_make_scored(rec_a, 0.75), _make_scored(rec_b, 0.40)]
        dedup_siblings(candidates, None, vault_db, trace_id)

        conn = connect(vault_db)
        try:
            row = conn.execute(
                "SELECT exclusion_reason, lattice_sibling_count, "
                "       lattice_winner_record_id, lattice_routing_basis "
                "FROM retrieval_candidates WHERE candidate_id = ?",
                (f"cand_{trace_id}_{rec_a}",),
            ).fetchone()
        finally:
            conn.close()

        assert row is not None
        assert row["exclusion_reason"] is None
        assert row["lattice_sibling_count"] == 2
        assert row["lattice_winner_record_id"] == rec_a

    def test_sku_match_routing_against_vault(self, vault_db: Path) -> None:
        """query_d1 matches one sibling → sku_match basis even if that sibling scores lower."""
        from cerebra.retrieval.lattice_dedup import dedup_siblings
        from cerebra.storage.db import connect

        ts = int(time.time())
        lin = f"it_lin_{ts}_d"
        rec_a, rec_b = f"it_rec_{ts}_d1", f"it_rec_{ts}_d2"
        _seed_sibling_pair(vault_db, lin, rec_a, rec_b, score_a=0.60, score_b=0.90)
        trace_id = f"trace_it_{lin}"

        # rec_a has D1="alpha" (lower score), rec_b has D1="beta" (higher score)
        # query_d1="alpha" → rec_a wins despite lower score
        ca = _make_scored(rec_a, 0.60, sku_address="alpha::d2::d3")
        cb = _make_scored(rec_b, 0.90, sku_address="beta::d2::d3")
        result = dedup_siblings([ca, cb], "alpha", vault_db, trace_id)

        assert len(result) == 1
        assert result[0].record_id == rec_a

        conn = connect(vault_db)
        try:
            row = conn.execute(
                "SELECT lattice_routing_basis FROM retrieval_candidates " "WHERE candidate_id = ?",
                (f"cand_{trace_id}_{rec_a}",),
            ).fetchone()
        finally:
            conn.close()
        assert row["lattice_routing_basis"] == "sku_match"

    def test_event_written_to_inspector(self, vault_db: Path) -> None:
        """LatticeSiblingResolved event is written to inspector_events table."""
        from cerebra.inspector.sqlite_log import SQLiteEventLog
        from cerebra.retrieval.lattice_dedup import dedup_siblings

        ts = int(time.time())
        lin = f"it_lin_{ts}_e"
        rec_a, rec_b = f"it_rec_{ts}_e1", f"it_rec_{ts}_e2"
        _seed_sibling_pair(vault_db, lin, rec_a, rec_b, score_a=0.70, score_b=0.50)
        trace_id = f"trace_it_{lin}"

        event_log = SQLiteEventLog(vault_db)
        candidates = [_make_scored(rec_a, 0.70), _make_scored(rec_b, 0.50)]
        dedup_siblings(candidates, None, vault_db, trace_id, event_log=event_log)

        from cerebra.storage.db import connect

        conn = connect(vault_db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM inspector_events "
                "WHERE event_type = 'LatticeSiblingResolved' "
                "AND subject_id = ?",
                (trace_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        assert count >= 1
