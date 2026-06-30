"""
Unit tests for cerebra context T1 auto-promotion (Phase 5 Step 6).

Tests cover:
- render_text() tower section present / absent
- ContextPacket.to_dict() includes truth_tower when set
- --no-promote flag skips T1 promotion
- abstained packet skips T1 promotion
- normal path populates T1 using a real vault DB
- no active session: auto-creates then promotes
- idempotency: re-running same query doesn't duplicate T1 items
- JSON output includes truth_tower field after promotion
- lockfile acquired during promotion phase
- to_tower_field() result attached to packet
"""

from __future__ import annotations

import contextlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli
from cerebra.cognition.truth_tower import TruthTower
from cerebra.cognition.working_memory import new_session
from cerebra.retrieval.context_packet import (
    ContextPacket,
    MemoryItem,
    _render_tower_lines,
    render_text,
)
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_vault() -> tuple[Path, Path]:
    d = tempfile.mkdtemp()
    vault = Path(d)
    (vault / "data").mkdir()
    db = vault / "data" / "cerebra.db"
    run_migrations(db)
    return vault, db


def _seed_memory_record(db_path: Path, record_id: str = "rec_t6") -> str:
    now = int(time.time())
    src = f"src_{record_id}"
    doc = f"doc_{record_id}"
    chk = f"chk_{record_id}"
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(source_id, canonical_path, content_hash, size_bytes, "
            " detected_type, detection_confidence, parser_status, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (src, f"/test/{record_id}", "h0", 1, "markdown", 1.0, "done", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO documents "
            "(document_id, source_id, document_type, normalization_confidence, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?)",
            (doc, src, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO chunks "
            "(chunk_id, document_id, source_id, heading_path, chunk_index, "
            " depth, content, content_hash, token_estimate, chunk_strategy, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (chk, doc, src, "", 0, 0, "test content", "hc0", 5, "fixed", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO memory_records "
            "(record_id, record_type, source_id, document_id, chunk_id, "
            " content, content_hash, token_estimate, lifecycle_state, "
            " created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (record_id, "source_chunk", src, doc, chk, "test content", "hr0", 5, "active", now, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return record_id


def _seed_trace(db_path: Path, trace_id: str) -> str:
    now = int(time.time())
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO retrieval_traces "
            "(trace_id, query, mode, plan_json, started_at, finished_at, "
            " duration_ms, candidate_count, selected_count, abstained, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (trace_id, "test query", "sku", "{}", now, now, 1, 1, 1, 0, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return trace_id


def _mock_packet(
    record_id: str = "rec_t6",
    trace_id: str = "trace_t6test001",
    selected: bool = True,
) -> ContextPacket:
    items = []
    if selected:
        items = [
            MemoryItem(
                record_id=record_id,
                source_id=f"src_{record_id}",
                chunk_id=f"chk_{record_id}",
                content_excerpt="T6 test content excerpt.",
                source_path="docs/test/EXAMPLE.md",
                sku_address=None,
                score=0.75,
                score_components={"semantic": 0.80},
                retrieval_path="sku",
                rank=1,
            )
        ]
    return ContextPacket(
        context_packet_id="ctxpkt_t6test001",
        packet_version=1,
        schema_version=1,
        created_at=1_720_000_000,
        query="test query",
        mode="sku",
        is_abstained=not selected,
        abstention_rationale="no results" if not selected else None,
        best_score_seen=0.0 if not selected else None,
        retrieval_trace_id=trace_id,
        origin_event_ids=["evt_aaa"],
        selected_memory=items,
        token_estimate=5 if selected else 0,
        selected_count=len(items),
        candidate_count=1 if selected else 3,
        uncertainties=[],
        excluded_candidate_count=0 if selected else 3,
    )


@contextlib.contextmanager
def _base_patches(vault: Path, packet: ContextPacket, scored: bool = True):
    """Shared pipeline patches; does NOT mock the T1 promotion path."""
    plan = MagicMock()
    plan.trace_id = packet.retrieval_trace_id
    plan.raw_query = packet.query
    plan.mode = packet.mode
    plan.query_d1 = None
    plan.query_d1_d2_d3 = None
    plan.max_candidates = 200
    plan.staleness_warnings = []

    from cerebra._primitives.score_composer import CompositeScore
    from cerebra.retrieval.scorer import ScoredCandidate

    scored_list = []
    if scored:
        scored_list = [
            ScoredCandidate(
                record_id="rec_t6",
                step_surfaced="sku",
                retrieval_path="sku",
                score=CompositeScore(
                    composite=0.75,
                    components={"semantic": 0.80},
                    weights={"semantic": 1.0},
                ),
                source_path=str(vault / "docs/test/EXAMPLE.md"),
                content_excerpt="T6 test content excerpt.",
                sku_address=None,
                created_at=1_720_000_000,
                rank=1,
            )
        ]

    with (
        patch("cerebra.cli.main._get_vault", return_value=vault),
        patch("cerebra.storage.migrations.run_migrations"),
        patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
        patch("cerebra.retrieval.planner.query_plan", return_value=plan),
        patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
        patch("cerebra.retrieval.scorer.score_candidates", return_value=scored_list),
        patch("cerebra.retrieval.trace.write_trace"),
        patch("cerebra.retrieval.context_packet.build_context_packet", return_value=packet),
        patch("cerebra.retrieval.context_packet.build_abstained_packet", return_value=packet),
    ):
        yield


# ── render_text() tower section ───────────────────────────────────────────────


@pytest.mark.unit
class TestRenderTextTowerSection:
    def _make_tower_dict(self, n_t1: int = 2, n_t2: int = 1) -> dict:
        t1_items = [
            {
                "tower_item_id": f"tti_t1_{i}",
                "content_summary": f"T1 evidence item {i}",
                "salience_score": 0.75,
                "retrieval_trace_id": "trace_test",
                "is_stale": False,
            }
            for i in range(1, n_t1 + 1)
        ]
        t2_items = []
        if n_t2 and t1_items:
            t2_items = [
                {
                    "tower_item_id": "tti_t2_1",
                    "t1_citation_id": t1_items[0]["tower_item_id"],
                    "content_summary": "T2 interpretation item",
                    "salience_score": 0.60,
                    "is_stale": False,
                }
            ]
        return {
            "t1_items": t1_items,
            "t2_items": t2_items,
            "t1_count": len(t1_items),
            "t2_count": len(t2_items),
            "stale_count": 0,
        }

    def test_no_tower_field_no_tower_section(self) -> None:
        packet = _mock_packet()
        assert packet.truth_tower is None
        rendered = render_text(packet)
        assert "Truth Tower" not in rendered

    def test_tower_field_present_shows_section(self) -> None:
        packet = _mock_packet()
        packet.truth_tower = self._make_tower_dict(n_t1=1, n_t2=0)
        rendered = render_text(packet)
        assert "Truth Tower" in rendered
        assert "T1 [1]" in rendered

    def test_tower_section_after_selected_memory(self) -> None:
        packet = _mock_packet()
        packet.truth_tower = self._make_tower_dict(n_t1=1, n_t2=0)
        rendered = render_text(packet)
        sel_pos = rendered.index("Selected memory")
        tower_pos = rendered.index("Truth Tower")
        assert tower_pos > sel_pos

    def test_tower_section_before_uncertainties(self) -> None:
        packet = _mock_packet()
        packet.truth_tower = self._make_tower_dict(n_t1=1, n_t2=0)
        rendered = render_text(packet)
        tower_pos = rendered.index("Truth Tower")
        uncert_pos = rendered.index("Uncertainties")
        assert tower_pos < uncert_pos

    def test_t2_nested_under_t1(self) -> None:
        packet = _mock_packet()
        packet.truth_tower = self._make_tower_dict(n_t1=1, n_t2=1)
        rendered = render_text(packet)
        assert "T2 [1] ^T1[1]" in rendered

    def test_stale_t2_shows_marker(self) -> None:
        tower = self._make_tower_dict(n_t1=1, n_t2=1)
        tower["t2_items"][0]["is_stale"] = True
        tower["stale_count"] = 1
        packet = _mock_packet()
        packet.truth_tower = tower
        rendered = render_text(packet)
        assert "[stale]" in rendered

    def test_abstained_packet_shows_tower_if_present(self) -> None:
        packet = _mock_packet(selected=False)
        packet.truth_tower = self._make_tower_dict(n_t1=1, n_t2=0)
        rendered = render_text(packet)
        assert "Truth Tower" in rendered
        assert "Abstained" in rendered

    def test_empty_tower_dict_no_section(self) -> None:
        packet = _mock_packet()
        packet.truth_tower = {
            "t1_items": [],
            "t2_items": [],
            "t1_count": 0,
            "t2_count": 0,
            "stale_count": 0,
        }
        rendered = render_text(packet)
        assert "Truth Tower" not in rendered

    def test_render_tower_lines_helper_formats_correctly(self) -> None:
        tower = self._make_tower_dict(n_t1=2, n_t2=1)
        lines = _render_tower_lines(tower)
        combined = "\n".join(lines)
        assert "T1 [1]" in combined
        assert "T1 [2]" in combined
        assert "T2 [1] ^T1[1]" in combined


# ── ContextPacket.to_dict() ───────────────────────────────────────────────────


@pytest.mark.unit
class TestContextPacketTowerField:
    def test_to_dict_omits_truth_tower_when_none(self) -> None:
        packet = _mock_packet()
        assert "truth_tower" not in packet.to_dict()

    def test_to_dict_includes_truth_tower_when_set(self) -> None:
        packet = _mock_packet()
        packet.truth_tower = {
            "t1_count": 1,
            "t2_count": 0,
            "stale_count": 0,
            "t1_items": [],
            "t2_items": [],
        }
        d = packet.to_dict()
        assert "truth_tower" in d
        assert d["truth_tower"]["t1_count"] == 1


# ── CLI --no-promote flag ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestNoPromoteFlag:
    def test_help_mentions_no_promote(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert "--no-promote" in result.output

    def test_no_promote_skips_promotion(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_nopromote")
        _seed_trace(db, "trace_nopromote")
        packet = _mock_packet("rec_nopromote", "trace_nopromote")
        runner = CliRunner()
        with (
            _base_patches(vault, packet),
            patch("cerebra.cli.lockfile.vault_lock") as mock_lock,
        ):
            result = runner.invoke(
                cli, ["context", "test query", "--vault", str(vault), "--no-promote"]
            )
        assert result.exit_code == 0, result.output
        mock_lock.assert_not_called()

    def test_no_promote_t1_unchanged(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_nopromote2")
        _seed_trace(db, "trace_nopromote2")
        sid = new_session(db, str(vault))
        packet = _mock_packet("rec_nopromote2", "trace_nopromote2")
        runner = CliRunner()
        with _base_patches(vault, packet):
            runner.invoke(cli, ["context", "test query", "--vault", str(vault), "--no-promote"])
        tower = TruthTower(db, sid)
        assert tower.load_tier(1) == []

    def test_no_promote_still_attaches_existing_tower_state(self) -> None:
        """--no-promote reads pre-existing tower state (read-only path)."""
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_preexist")
        _seed_trace(db, "trace_preexist")
        sid = new_session(db, str(vault))
        # Pre-populate tower via a direct call
        tower = TruthTower(db, sid)
        t1s = tower.promote_to_t1(
            [_FakeMemoryItem("rec_preexist", "chk_rec_preexist")],
            "trace_preexist",
        )
        assert t1s, "setup: T1 must be pre-populated"

        packet = _mock_packet("rec_other", "trace_nopromote3")
        runner = CliRunner()
        with _base_patches(vault, packet):
            result = runner.invoke(
                cli,
                [
                    "context",
                    "test query",
                    "--vault",
                    str(vault),
                    "--no-promote",
                    "--format",
                    "json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "truth_tower" in data
        assert data["truth_tower"]["t1_count"] >= 1


# ── Abstained packet path ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestAbstainedPath:
    def test_abstained_skips_promotion(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_abst")
        _seed_trace(db, "trace_abst")
        packet = _mock_packet("rec_abst", "trace_abst", selected=False)
        runner = CliRunner()
        with (
            _base_patches(vault, packet, scored=False),
            patch("cerebra.cli.lockfile.vault_lock") as mock_lock,
        ):
            result = runner.invoke(
                cli, ["context", "test query", "--vault", str(vault), "--floor", "0.99"]
            )
        assert result.exit_code == 1  # abstained → exit 1
        mock_lock.assert_not_called()

    def test_abstained_t1_unchanged(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_abst2")
        _seed_trace(db, "trace_abst2")
        sid = new_session(db, str(vault))
        packet = _mock_packet("rec_abst2", "trace_abst2", selected=False)
        runner = CliRunner()
        with _base_patches(vault, packet, scored=False):
            runner.invoke(cli, ["context", "test query", "--vault", str(vault), "--floor", "0.99"])
        tower = TruthTower(db, sid)
        assert tower.load_tier(1) == []


# ── T1 auto-promotion — real vault DB ────────────────────────────────────────


class _FakeMemoryItem:
    def __init__(self, record_id: str, chunk_id: str, score: float = 0.75) -> None:
        self.record_id = record_id
        self.source_id = f"src_{record_id}"
        self.chunk_id = chunk_id
        self.content_excerpt = f"content for {record_id}"
        self.source_path = "/test/example.md"
        self.sku_address = None
        self.score = score
        self.score_components: dict = {}
        self.retrieval_path = "sku"
        self.rank = 0


@pytest.mark.unit
class TestT1AutoPromotion:
    def test_normal_path_populates_t1(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_t6a")
        _seed_trace(db, "trace_t6a")
        packet = _mock_packet("rec_t6a", "trace_t6a")
        runner = CliRunner()
        with _base_patches(vault, packet):
            result = runner.invoke(cli, ["context", "test query", "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        # Discover the session that was auto-created
        conn = connect(db)
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE status='active' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row, "auto-session should have been created"
        tower = TruthTower(db, row["session_id"])
        assert len(tower.load_tier(1)) >= 1

    def test_no_session_auto_creates_then_promotes(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_t6b")
        _seed_trace(db, "trace_t6b")
        # No session created before running context
        packet = _mock_packet("rec_t6b", "trace_t6b")
        runner = CliRunner()
        with _base_patches(vault, packet):
            runner.invoke(cli, ["context", "test query", "--vault", str(vault)])
        conn = connect(db)
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        assert session_count >= 1, "auto-session must have been created"

    def test_existing_session_used_not_recreated(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_t6c")
        _seed_trace(db, "trace_t6c")
        sid = new_session(db, str(vault))
        packet = _mock_packet("rec_t6c", "trace_t6c")
        runner = CliRunner()
        with _base_patches(vault, packet):
            runner.invoke(cli, ["context", "test query", "--vault", str(vault)])
        conn = connect(db)
        session_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE status='active'"
        ).fetchone()[0]
        conn.close()
        assert session_count == 1, "existing active session must not have been duplicated"
        tower = TruthTower(db, sid)
        assert len(tower.load_tier(1)) >= 1

    def test_idempotency_same_record_not_duplicated(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_t6d")
        _seed_trace(db, "trace_t6d")
        sid = new_session(db, str(vault))
        packet = _mock_packet("rec_t6d", "trace_t6d")
        runner = CliRunner()
        with _base_patches(vault, packet):
            runner.invoke(cli, ["context", "test query", "--vault", str(vault)])
        _seed_trace(db, "trace_t6d_2")
        packet2 = _mock_packet("rec_t6d", "trace_t6d_2")
        with _base_patches(vault, packet2):
            runner.invoke(cli, ["context", "test query again", "--vault", str(vault)])
        tower = TruthTower(db, sid)
        t1_items = tower.load_tier(1)
        record_ids = [i.record_id for i in t1_items]
        assert record_ids.count("rec_t6d") == 1

    def test_json_output_includes_truth_tower_field(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_t6e")
        _seed_trace(db, "trace_t6e")
        new_session(db, str(vault))
        packet = _mock_packet("rec_t6e", "trace_t6e")
        runner = CliRunner()
        with _base_patches(vault, packet):
            result = runner.invoke(
                cli,
                ["context", "test query", "--vault", str(vault), "--format", "json"],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "truth_tower" in data
        assert data["truth_tower"]["t1_count"] >= 1

    def test_lockfile_acquired_during_promotion(self) -> None:
        vault, db = _make_vault()
        _seed_memory_record(db, "rec_t6f")
        _seed_trace(db, "trace_t6f")
        packet = _mock_packet("rec_t6f", "trace_t6f")
        runner = CliRunner()
        lock_calls: list[Path] = []

        def _capture_lock(path: Path):  # type: ignore[return]
            import contextlib

            lock_calls.append(path)

            @contextlib.contextmanager
            def _ctx():
                yield

            return _ctx()

        with (
            _base_patches(vault, packet),
            patch("cerebra.cli.lockfile.vault_lock", side_effect=_capture_lock),
        ):
            runner.invoke(cli, ["context", "test query", "--vault", str(vault)])
        assert len(lock_calls) == 1
        assert lock_calls[0] == vault
