"""Unit tests for ContextPacket builder and renderer."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cerebra.retrieval.context_packet import (
    EXCERPT_MAX_CHARS,
    ContextPacket,
    MemoryItem,
    _short_path,
    build_abstained_packet,
    build_context_packet,
    render_text,
)
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations

if TYPE_CHECKING:
    from cerebra.retrieval.scorer import ScoredCandidate

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _migrated_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    run_migrations(db)
    return db


def _make_plan(trace_id: str = "trace_test000001", mode: str = "hybrid"):
    from cerebra.retrieval.planner import QueryPlan

    return QueryPlan(
        trace_id=trace_id,
        raw_query="plan the retrieval architecture",
        query_d1=5,
        query_d1_d2_d3="0x5",
        mode=mode,
        max_candidates=200,
        staleness_warnings=["graph index never built"],
    )


def _make_scored(
    record_id: str = "rec_001",
    composite: float = 0.73,
    rank: int = 1,
    source_path: str = "/home/user/docs/refined-runtime-model/CEREBRA_RETRIEVAL.md",
    retrieval_path: str = "vector_fallback",
    step_surfaced: str = "vector_fallback",
    content: str = "Sample content for testing the context packet builder.",
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
        source_path=source_path,
        content_excerpt=content,
        sku_address="0x5.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0",
        created_at=int(time.time()),
        rank=rank,
    )


def _insert_trace(db: Path, trace_id: str, mode: str = "hybrid") -> None:
    """Insert a minimal retrieval_traces row so UPDATE context_packet_id works."""
    now = int(time.time())
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO retrieval_traces (
                trace_id, query, mode, query_sku_d1, query_sku_pattern,
                plan_json, started_at, finished_at, duration_ms,
                candidate_count, selected_count, abstained, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)
            """,
            (
                trace_id,
                "plan the retrieval architecture",
                mode,
                5,
                "0x5",
                '{"raw_query": "plan the retrieval architecture"}',
                now - 1,
                now,
                500,
                3,
                1,
            ),
        )


def _make_trace_data(
    trace_id: str = "trace_test000001",
    scored: list | None = None,
    floor: float = 0.35,
    mode: str = "hybrid",
):
    from cerebra.retrieval.trace import TraceData

    _scored = scored if scored is not None else [_make_scored()]
    now = int(time.time())
    return TraceData(
        plan=_make_plan(trace_id=trace_id, mode=mode),
        scored_all=_scored,
        floor=floor,
        started_at=now - 1,
        finished_at=now,
        duration_ms=500,
        step_events=[],
    )


# ── Schema validation ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextPacketSchema:
    def test_required_fields_present(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema001")
            td = _make_trace_data("trace_schema001", scored=[_make_scored()])
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            required = {
                "context_packet_id",
                "packet_version",
                "created_at",
                "query",
                "mode",
                "is_abstained",
                "retrieval_trace_id",
                "selected_memory",
                "token_estimate",
                "selected_count",
                "candidate_count",
            }
            d = pkt.to_dict()
            for field in required:
                assert field in d, f"Missing required field: {field}"
        finally:
            db.unlink(missing_ok=True)

    def test_packet_version_is_one(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema002")
            td = _make_trace_data("trace_schema002")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert pkt.packet_version == 1
            assert pkt.schema_version == 1
        finally:
            db.unlink(missing_ok=True)

    def test_selected_memory_always_list(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema003")
            td = _make_trace_data("trace_schema003")
            pkt = build_context_packet(td, [], db)  # empty above-floor
            assert isinstance(pkt.selected_memory, list)
            assert pkt.selected_memory == []
        finally:
            db.unlink(missing_ok=True)

    def test_selected_memory_not_null_in_to_dict(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema004")
            td = _make_trace_data("trace_schema004")
            pkt = build_context_packet(td, [], db)
            d = pkt.to_dict()
            assert d["selected_memory"] is not None
            assert isinstance(d["selected_memory"], list)
        finally:
            db.unlink(missing_ok=True)

    def test_to_dict_json_roundtrip(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema005")
            td = _make_trace_data("trace_schema005", scored=[_make_scored()])
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            serialized = json.dumps(pkt.to_dict())
            parsed = json.loads(serialized)
            assert parsed["context_packet_id"] == pkt.context_packet_id
            assert parsed["query"] == pkt.query
            assert isinstance(parsed["selected_memory"], list)
        finally:
            db.unlink(missing_ok=True)

    def test_context_packet_id_prefix(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema006")
            td = _make_trace_data("trace_schema006")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert pkt.context_packet_id.startswith("ctxpkt_")
        finally:
            db.unlink(missing_ok=True)

    def test_retrieval_trace_id_matches_plan(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema007")
            td = _make_trace_data("trace_schema007")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert pkt.retrieval_trace_id == "trace_schema007"
        finally:
            db.unlink(missing_ok=True)

    def test_mode_matches_plan(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_schema008", mode="vector_only")
            td = _make_trace_data("trace_schema008", mode="vector_only")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert pkt.mode == "vector_only"
        finally:
            db.unlink(missing_ok=True)


# ── Token estimation ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTokenEstimation:
    def test_token_estimate_formula(self) -> None:
        """token_estimate = sum(len(excerpt)) // 4."""
        db = _migrated_db()
        try:
            content = "A" * 400  # 400 chars → 100 tokens
            scored = [_make_scored(content=content)]
            _insert_trace(db, "trace_token001")
            td = _make_trace_data("trace_token001", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert pkt.token_estimate == 100
        finally:
            db.unlink(missing_ok=True)

    def test_token_estimate_zero_when_empty(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_token002")
            td = _make_trace_data("trace_token002")
            pkt = build_context_packet(td, [], db)
            assert pkt.token_estimate == 0
        finally:
            db.unlink(missing_ok=True)

    def test_token_estimate_sums_all_selected(self) -> None:
        db = _migrated_db()
        try:
            scored = [
                _make_scored("rec_a", content="A" * 200, rank=1),
                _make_scored("rec_b", content="B" * 200, rank=2),
            ]
            _insert_trace(db, "trace_token003")
            td = _make_trace_data("trace_token003", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, limit=10)
            assert pkt.token_estimate == (200 + 200) // 4
        finally:
            db.unlink(missing_ok=True)

    def test_excerpt_capped_at_excerpt_max_chars(self) -> None:
        db = _migrated_db()
        try:
            long_content = "X" * 600  # longer than EXCERPT_MAX_CHARS
            scored = [_make_scored(content=long_content)]
            _insert_trace(db, "trace_token004")
            td = _make_trace_data("trace_token004", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert len(pkt.selected_memory[0].content_excerpt) <= EXCERPT_MAX_CHARS
        finally:
            db.unlink(missing_ok=True)


# ── selected_count and excluded_candidate_count ────────────────────────────────


@pytest.mark.unit
class TestCandidateCounts:
    def test_selected_count_matches_visible(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(f"rec_{i}", rank=i + 1) for i in range(5)]
            _insert_trace(db, "trace_cnt001")
            td = _make_trace_data("trace_cnt001", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, limit=3)
            assert pkt.selected_count == 3
        finally:
            db.unlink(missing_ok=True)

    def test_candidate_count_is_total(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(f"rec_{i}", rank=i + 1) for i in range(7)]
            _insert_trace(db, "trace_cnt002")
            td = _make_trace_data("trace_cnt002", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert pkt.candidate_count == 7
        finally:
            db.unlink(missing_ok=True)

    def test_excluded_count_correct(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(f"rec_{i}", rank=i + 1) for i in range(5)]
            _insert_trace(db, "trace_cnt003")
            td = _make_trace_data("trace_cnt003", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, limit=2)
            # 5 total - 2 visible = 3 excluded
            assert pkt.excluded_candidate_count == 3
        finally:
            db.unlink(missing_ok=True)

    def test_excluded_zero_when_all_visible(self) -> None:
        db = _migrated_db()
        try:
            scored = [_make_scored(f"rec_{i}", rank=i + 1) for i in range(3)]
            _insert_trace(db, "trace_cnt004")
            td = _make_trace_data("trace_cnt004", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, limit=10)
            assert pkt.excluded_candidate_count == 0
        finally:
            db.unlink(missing_ok=True)


# ── Abstained form ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAbstainedPacket:
    def test_is_abstained_true(self) -> None:
        td = _make_trace_data("trace_abs001", scored=[_make_scored(composite=0.20)])
        pkt = build_abstained_packet(td, best_score_seen=0.20)
        assert pkt.is_abstained is True

    def test_selected_memory_empty_list(self) -> None:
        td = _make_trace_data("trace_abs002", scored=[_make_scored(composite=0.20)])
        pkt = build_abstained_packet(td, best_score_seen=0.20)
        assert pkt.selected_memory == []

    def test_selected_count_zero(self) -> None:
        td = _make_trace_data("trace_abs003")
        pkt = build_abstained_packet(td, best_score_seen=0.20)
        assert pkt.selected_count == 0

    def test_token_estimate_zero(self) -> None:
        td = _make_trace_data("trace_abs004")
        pkt = build_abstained_packet(td, best_score_seen=0.20)
        assert pkt.token_estimate == 0

    def test_abstention_rationale_present(self) -> None:
        td = _make_trace_data("trace_abs005", floor=0.35)
        pkt = build_abstained_packet(td, best_score_seen=0.22)
        assert pkt.abstention_rationale is not None
        assert "0.35" in pkt.abstention_rationale
        assert "0.22" in pkt.abstention_rationale

    def test_best_score_seen_set(self) -> None:
        td = _make_trace_data("trace_abs006")
        pkt = build_abstained_packet(td, best_score_seen=0.28)
        assert pkt.best_score_seen == pytest.approx(0.28, abs=1e-4)

    def test_best_score_seen_in_to_dict(self) -> None:
        td = _make_trace_data("trace_abs007")
        pkt = build_abstained_packet(td, best_score_seen=0.28)
        d = pkt.to_dict()
        assert "best_score_seen" in d

    def test_excluded_candidate_count_equals_total(self) -> None:
        scored = [_make_scored(f"rec_{i}", composite=0.10, rank=i + 1) for i in range(5)]
        td = _make_trace_data("trace_abs008", scored=scored)
        pkt = build_abstained_packet(td, best_score_seen=0.10)
        assert pkt.excluded_candidate_count == 5
        assert pkt.candidate_count == 5


# ── Provenance fields ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestProvenanceFields:
    def test_origin_event_ids_is_list(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_prov001")
            td = _make_trace_data("trace_prov001")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            assert isinstance(pkt.origin_event_ids, list)
        finally:
            db.unlink(missing_ok=True)

    def test_origin_event_ids_contains_built_id(self) -> None:
        """Last entry in origin_event_ids is the ContextPacketBuilt event_id."""
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            _insert_trace(db, "trace_prov002")
            log = SQLiteEventLog(db)
            td = _make_trace_data("trace_prov002")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, event_log=log)
            assert len(pkt.origin_event_ids) >= 1
            # Last ID is the ContextPacketBuilt event
            built_events = log.query_by_type("ContextPacketBuilt")
            assert built_events
            assert built_events[0]["event_id"] in pkt.origin_event_ids
        finally:
            db.unlink(missing_ok=True)

    def test_origin_event_ids_includes_query_events(self) -> None:
        """QueryReceived and QueryPlanned event_ids are collected when present."""
        from cerebra.inspector.event import make_event
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            _insert_trace(db, "trace_prov003")
            log = SQLiteEventLog(db)
            trace_id = "trace_prov003"
            # Manually insert QueryReceived and QueryPlanned events
            qr = make_event(
                "QueryReceived",
                "retrieval",
                "q received",
                data={"query": "test"},
                subject_id=trace_id,
            )
            qp = make_event(
                "QueryPlanned",
                "retrieval.planner",
                "q planned",
                data={"mode": "hybrid"},
                subject_id=trace_id,
            )
            log.write(qr)
            log.write(qp)
            td = _make_trace_data("trace_prov003")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, event_log=log)
            assert qr.event_id in pkt.origin_event_ids
            assert qp.event_id in pkt.origin_event_ids
        finally:
            db.unlink(missing_ok=True)

    def test_no_event_log_origin_ids_still_has_built_placeholder(self) -> None:
        """Without an event_log, origin_event_ids still has the built event ID."""
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_prov004")
            td = _make_trace_data("trace_prov004")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db, event_log=None)
            # Only the pre-generated built event_id (no log to query from)
            assert len(pkt.origin_event_ids) == 1
            assert pkt.origin_event_ids[0].startswith("evt_")
        finally:
            db.unlink(missing_ok=True)


# ── Persistence ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPersistence:
    def test_trace_row_updated_with_packet_id(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_persist01")
            td = _make_trace_data("trace_persist01")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT context_packet_id FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_persist01",),
                ).fetchone()
            assert row["context_packet_id"] == pkt.context_packet_id
        finally:
            db.unlink(missing_ok=True)

    def test_abstained_does_not_update_trace_row(self) -> None:
        db = _migrated_db()
        try:
            _insert_trace(db, "trace_persist02")
            td = _make_trace_data("trace_persist02")
            build_abstained_packet(td, best_score_seen=0.20)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT context_packet_id FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_persist02",),
                ).fetchone()
            assert row["context_packet_id"] is None
        finally:
            db.unlink(missing_ok=True)

    def test_context_packet_built_event_emitted(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            _insert_trace(db, "trace_persist03")
            log = SQLiteEventLog(db)
            td = _make_trace_data("trace_persist03")
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            build_context_packet(td, above, db, event_log=log)
            events = log.query_by_type("ContextPacketBuilt")
            assert len(events) == 1
            data = json.loads(events[0]["data_json"])
            assert "context_packet_id" in data
            assert data["is_abstained"] is False
        finally:
            db.unlink(missing_ok=True)


# ── Path rendering ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPathRendering:
    def test_short_path_returns_parent_slash_name(self) -> None:
        result = _short_path("/home/user/docs/refined-runtime-model/CEREBRA.md")
        assert result == "refined-runtime-model/CEREBRA.md"

    def test_short_path_no_absolute_components(self) -> None:
        result = _short_path("/home/user/docs/project/FILE.md")
        assert not result.startswith("/")
        assert "home" not in result

    def test_short_path_bare_filename(self) -> None:
        result = _short_path("FILE.md")
        assert result == "FILE.md"

    def test_memory_item_source_path_is_relative(self) -> None:
        """source_path in MemoryItem is stored vault-relative; no absolute paths."""
        db = _migrated_db()
        try:
            path = "/home/user/docs/runtime/CEREBRA.md"
            scored = [_make_scored(source_path=path)]
            _insert_trace(db, "trace_path001")
            td = _make_trace_data("trace_path001", scored=scored)
            above = [c for c in td.scored_all if c.score.composite >= td.floor]
            pkt = build_context_packet(td, above, db)
            # Any form is acceptable as long as no leading slash (= not absolute)
            sp = pkt.selected_memory[0].source_path
            assert not sp.startswith("/"), f"Expected relative path, got: {sp}"
        finally:
            db.unlink(missing_ok=True)

    def test_render_text_uses_source_path_as_is(self) -> None:
        """render_text emits item.source_path directly; builder must supply relative paths."""
        item = MemoryItem(
            record_id="rec_001",
            source_id="src_001",
            chunk_id="chk_001",
            content_excerpt="Test content.",
            source_path="runtime/CEREBRA.md",
            sku_address=None,
            score=0.73,
            score_components={},
            retrieval_path="vector_fallback",
            rank=1,
        )
        pkt = ContextPacket(
            context_packet_id="ctxpkt_abc",
            packet_version=1,
            schema_version=1,
            created_at=int(time.time()),
            query="test query",
            mode="hybrid",
            is_abstained=False,
            abstention_rationale=None,
            best_score_seen=None,
            retrieval_trace_id="trace_001",
            origin_event_ids=[],
            selected_memory=[item],
            token_estimate=3,
            selected_count=1,
            candidate_count=1,
            uncertainties=[],
            excluded_candidate_count=0,
        )
        rendered = render_text(pkt)
        assert "runtime/CEREBRA.md" in rendered


# ── render_text ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRenderText:
    def _make_packet(self, n_items: int = 2, is_abstained: bool = False) -> ContextPacket:
        items = [
            MemoryItem(
                record_id=f"rec_{i}",
                source_id=f"src_{i}",
                chunk_id=f"chk_{i}",
                content_excerpt=f"Content for record {i}.",
                source_path=f"/home/user/docs/project/FILE_{i}.md",
                sku_address=None,
                score=0.80 - i * 0.05,
                score_components={"semantic": 0.80},
                retrieval_path="vector_fallback",
                rank=i + 1,
            )
            for i in range(n_items)
        ]
        return ContextPacket(
            context_packet_id="ctxpkt_testtest01",
            packet_version=1,
            schema_version=1,
            created_at=int(time.time()),
            query="test query",
            mode="hybrid",
            is_abstained=is_abstained,
            abstention_rationale=(
                "No candidates above floor 0.35; best score was 0.20" if is_abstained else None
            ),
            best_score_seen=0.20 if is_abstained else None,
            retrieval_trace_id="trace_test000001",
            origin_event_ids=[],
            selected_memory=[] if is_abstained else items,
            token_estimate=0 if is_abstained else 10,
            selected_count=0 if is_abstained else n_items,
            candidate_count=n_items,
            uncertainties=[],
            excluded_candidate_count=0,
        )

    def test_render_includes_packet_id(self) -> None:
        pkt = self._make_packet()
        rendered = render_text(pkt)
        assert "ctxpkt_testtest01" in rendered

    def test_render_includes_query(self) -> None:
        pkt = self._make_packet()
        rendered = render_text(pkt)
        assert "test query" in rendered

    def test_render_includes_rank(self) -> None:
        pkt = self._make_packet()
        rendered = render_text(pkt)
        assert "[1]" in rendered

    def test_render_includes_score(self) -> None:
        pkt = self._make_packet()
        rendered = render_text(pkt)
        assert "0.80" in rendered

    def test_render_truncates_long_excerpts(self) -> None:
        item = MemoryItem(
            record_id="rec_x",
            source_id="s",
            chunk_id="c",
            content_excerpt="A" * 200,
            source_path="/home/user/docs/project/F.md",
            sku_address=None,
            score=0.7,
            score_components={},
            retrieval_path="vector_fallback",
            rank=1,
        )
        pkt = ContextPacket(
            context_packet_id="ctxpkt_x",
            packet_version=1,
            schema_version=1,
            created_at=0,
            query="q",
            mode="hybrid",
            is_abstained=False,
            abstention_rationale=None,
            best_score_seen=None,
            retrieval_trace_id="t",
            origin_event_ids=[],
            selected_memory=[item],
            token_estimate=50,
            selected_count=1,
            candidate_count=1,
            uncertainties=[],
            excluded_candidate_count=0,
        )
        rendered = render_text(pkt)
        lines = [ln for ln in rendered.split("\n") if "AAA" in ln]
        assert lines
        assert len(lines[0]) <= 120

    def test_render_abstained_shows_rationale(self) -> None:
        pkt = self._make_packet(is_abstained=True)
        rendered = render_text(pkt)
        assert "Abstained" in rendered
        assert "0.35" in rendered

    def test_render_shows_uncertainties_when_present(self) -> None:
        pkt = self._make_packet()
        pkt.uncertainties = ["graph index never built"]
        rendered = render_text(pkt)
        assert "graph index never built" in rendered

    def test_render_shows_none_when_no_uncertainties(self) -> None:
        pkt = self._make_packet()
        rendered = render_text(pkt)
        assert "Uncertainties: none" in rendered
