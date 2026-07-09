# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the abstention path — Step 10.

Covers: floor trigger logic, --floor flag override, abstained ContextPacket
form, RetrievalAbstained event payload, trace row abstained flag, and CLI
exit codes for both `search` and `context`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _make_plan(trace_id: str = "trace_abs001", mode: str = "hybrid"):
    p = MagicMock()
    p.raw_query = "weather forecast for tomorrow"
    p.mode = mode
    p.query_d1 = None
    p.query_d1_d2_d3 = None
    p.trace_id = trace_id
    p.max_candidates = 200
    p.staleness_warnings = []
    return p


def _make_scored(record_id: str = "rec_001", composite: float = 0.30, rank: int = 1):
    from cerebra._primitives.score_composer import CompositeScore
    from cerebra.retrieval.scorer import ScoredCandidate

    score = CompositeScore(
        composite=composite,
        components={
            "semantic": 0.35,
            "lexical": 0.30,
            "sku_match": 0.0,
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
        step_surfaced="vector_fallback",
        retrieval_path="vector_fallback",
        score=score,
        source_path="docs/example.md",
        content_excerpt="Sample content for abstention testing.",
        sku_address=None,
        created_at=1_720_000_000,
        rank=rank,
    )


def _patched_search(scored_list: list, plan=None):
    """Patch the retrieval stack for `search` tests."""
    import contextlib

    _plan = plan or _make_plan()

    @contextlib.contextmanager
    def _cm():
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", return_value=_plan),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=scored_list),
            patch("cerebra.retrieval.trace.write_trace", return_value="trace_abs001"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings",
                side_effect=lambda scored, *a, **kw: scored,
            ),
        ):
            yield

    return _cm()


def _patched_context(scored_list: list, plan=None):
    """Patch the retrieval stack for `context` tests."""
    import contextlib

    _plan = plan or _make_plan()

    @contextlib.contextmanager
    def _cm():
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", return_value=_plan),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=scored_list),
            patch("cerebra.retrieval.trace.write_trace", return_value="trace_abs001"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings",
                side_effect=lambda scored, *a, **kw: scored,
            ),
        ):
            yield

    return _cm()


def _make_normal_packet(packet_id: str = "ctxpkt_norm001"):
    from cerebra.retrieval.context_packet import ContextPacket, MemoryItem

    item = MemoryItem(
        record_id="rec_001",
        source_id="src_001",
        chunk_id="chk_001",
        content_excerpt="Test content.",
        source_path="docs/example.md",
        sku_address=None,
        score=0.50,
        score_components={"semantic": 0.50},
        retrieval_path="vector_fallback",
        rank=1,
    )
    return ContextPacket(
        context_packet_id=packet_id,
        packet_version=1,
        schema_version=1,
        created_at=1_720_000_000,
        query="test query",
        mode="hybrid",
        is_abstained=False,
        abstention_rationale=None,
        best_score_seen=None,
        retrieval_trace_id="trace_abs001",
        origin_event_ids=[],
        selected_memory=[item],
        token_estimate=3,
        selected_count=1,
        candidate_count=1,
        uncertainties=[],
        excluded_candidate_count=0,
    )


# ── Abstention trigger ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAbstentionTrigger:
    def test_search_abstains_when_max_below_floor(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "weather", "--floor", "0.45"])
        assert result.exit_code == 1

    def test_search_does_not_abstain_when_max_above_floor(self) -> None:
        scored = [_make_scored(composite=0.50)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "leeway network", "--floor", "0.45"])
        assert result.exit_code == 0, result.output

    def test_context_abstains_when_max_below_floor(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(cli, ["context", "weather", "--floor", "0.45"])
        assert result.exit_code == 1

    def test_context_does_not_abstain_when_max_above_floor(self) -> None:
        scored = [_make_scored(composite=0.50)]
        with (
            _patched_context(scored),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet",
                return_value=_make_normal_packet(),
            ),
        ):
            result = CliRunner().invoke(cli, ["context", "leeway network", "--floor", "0.45"])
        assert result.exit_code == 0, result.output

    def test_empty_scored_list_abstains(self) -> None:
        with _patched_search([]):
            result = CliRunner().invoke(cli, ["search", "weather"])
        assert result.exit_code == 1

    def test_floor_equality_does_not_abstain(self) -> None:
        """best_score == floor is passing (not abstained)."""
        scored = [_make_scored(composite=0.35)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "test", "--floor", "0.35"])
        assert result.exit_code == 0, result.output


# ── Floor flag override ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFloorFlagOverride:
    def test_high_floor_triggers_abstention_for_otherwise_passing_score(self) -> None:
        """--floor 0.50 abstains on a score that passes default 0.35."""
        scored = [_make_scored(composite=0.39)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "test", "--floor", "0.50"])
        assert result.exit_code == 1

    def test_default_floor_does_not_abstain_for_score_0_39(self) -> None:
        """Default --floor 0.35 passes a score of 0.39."""
        scored = [_make_scored(composite=0.39)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "test"])
        assert result.exit_code == 0, result.output

    def test_context_high_floor_triggers_abstention(self) -> None:
        scored = [_make_scored(composite=0.39)]
        with _patched_context(scored):
            result = CliRunner().invoke(cli, ["context", "test", "--floor", "0.50"])
        assert result.exit_code == 1

    def test_context_default_floor_does_not_abstain_for_score_0_39(self) -> None:
        scored = [_make_scored(composite=0.39)]
        with (
            _patched_context(scored),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet",
                return_value=_make_normal_packet(),
            ),
        ):
            result = CliRunner().invoke(cli, ["context", "test"])
        assert result.exit_code == 0, result.output


# ── Search stderr message ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchAbstentionMessage:
    def test_message_mentions_floor_and_best_score(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "test", "--floor", "0.45"])
        assert result.exit_code == 1
        assert "No relevant results above floor" in result.stderr
        assert "0.45" in result.stderr
        assert "0.30" in result.stderr

    def test_message_goes_to_stderr_not_stdout(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_search(scored):
            result = CliRunner().invoke(cli, ["search", "test", "--floor", "0.45"])
        assert result.stdout == ""

    def test_search_json_format_also_abstains_to_stderr(self) -> None:
        """--format json doesn't change the abstention path — still stderr + exit 1."""
        scored = [_make_scored(composite=0.30)]
        with _patched_search(scored):
            result = CliRunner().invoke(
                cli, ["search", "test", "--floor", "0.45", "--format", "json"]
            )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "No relevant results above floor" in result.stderr


# ── Abstained ContextPacket form ───────────────────────────────────────────────


@pytest.mark.unit
class TestAbstainedPacketForm:
    def test_context_json_is_abstained_true(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        assert result.exit_code == 1
        packet = json.loads(result.output)
        assert packet["is_abstained"] is True

    def test_context_json_selected_memory_empty(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        packet = json.loads(result.output)
        assert packet["selected_memory"] == []
        assert packet["selected_count"] == 0

    def test_context_json_abstention_rationale_present(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        packet = json.loads(result.output)
        assert packet.get("abstention_rationale") is not None

    def test_context_json_best_score_seen_matches_actual(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        packet = json.loads(result.output)
        assert "best_score_seen" in packet
        assert abs(packet["best_score_seen"] - 0.30) < 0.01

    def test_context_json_candidate_count_correct(self) -> None:
        scored = [_make_scored(f"rec_{i}", composite=0.20, rank=i + 1) for i in range(4)]
        with _patched_context(scored):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        packet = json.loads(result.output)
        assert packet["candidate_count"] == 4
        assert packet["excluded_candidate_count"] == 4

    def test_context_json_required_fields_present(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        packet = json.loads(result.output)
        for field in (
            "context_packet_id",
            "packet_version",
            "schema_version",
            "created_at",
            "query",
            "mode",
            "is_abstained",
            "retrieval_trace_id",
            "origin_event_ids",
            "selected_memory",
            "token_estimate",
            "selected_count",
            "candidate_count",
            "excluded_candidate_count",
        ):
            assert field in packet, f"Missing field: {field}"

    def test_context_text_abstained_shows_rationale(self) -> None:
        scored = [_make_scored(composite=0.30)]
        with _patched_context(scored):
            result = CliRunner().invoke(cli, ["context", "test", "--floor", "0.45"])
        assert result.exit_code == 1
        assert "Abstained" in result.output


# ── RetrievalAbstained event ───────────────────────────────────────────────────


@pytest.mark.unit
class TestRetrievalAbstainedEvent:
    def _run_context_capture_log(self, scored_list: list, floor: float = 0.45):
        plan = _make_plan()
        event_log_instance = MagicMock()
        event_log_class = MagicMock(return_value=event_log_instance)
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog", event_log_class),
            patch("cerebra.retrieval.planner.query_plan", return_value=plan),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=scored_list),
            patch("cerebra.retrieval.trace.write_trace", return_value="trace_abs001"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings",
                side_effect=lambda scored, *a, **kw: scored,
            ),
        ):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", str(floor), "--format", "json"]
            )
        return result, event_log_instance

    def test_event_emitted_on_abstention(self) -> None:
        scored = [_make_scored(composite=0.30)]
        result, log = self._run_context_capture_log(scored, floor=0.45)
        assert result.exit_code == 1
        written = [call.args[0] for call in log.write.call_args_list]
        abstained = [e for e in written if e.event_type == "RetrievalAbstained"]
        assert len(abstained) == 1

    def test_event_payload_has_required_fields(self) -> None:
        scored = [_make_scored(composite=0.30)]
        _, log = self._run_context_capture_log(scored, floor=0.45)
        written = [call.args[0] for call in log.write.call_args_list]
        evt = next(e for e in written if e.event_type == "RetrievalAbstained")
        for key in ("trace_id", "query", "mode", "candidate_count", "best_score_seen", "floor"):
            assert key in evt.data, f"Missing key in event data: {key}"

    def test_event_payload_values_correct(self) -> None:
        scored = [_make_scored(composite=0.30)]
        _, log = self._run_context_capture_log(scored, floor=0.45)
        written = [call.args[0] for call in log.write.call_args_list]
        evt = next(e for e in written if e.event_type == "RetrievalAbstained")
        assert abs(evt.data["best_score_seen"] - 0.30) < 0.01
        assert evt.data["floor"] == pytest.approx(0.45)
        assert evt.data["candidate_count"] == 1

    def test_event_subject_id_matches_trace_id(self) -> None:
        scored = [_make_scored(composite=0.30)]
        _, log = self._run_context_capture_log(scored, floor=0.45)
        written = [call.args[0] for call in log.write.call_args_list]
        evt = next(e for e in written if e.event_type == "RetrievalAbstained")
        assert evt.subject_id == evt.data["trace_id"]

    def test_event_not_emitted_on_normal_path(self) -> None:
        scored = [_make_scored(composite=0.50)]
        plan = _make_plan()
        event_log_instance = MagicMock()
        event_log_class = MagicMock(return_value=event_log_instance)
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog", event_log_class),
            patch("cerebra.retrieval.planner.query_plan", return_value=plan),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=scored),
            patch("cerebra.retrieval.trace.write_trace", return_value="trace_abs001"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings", side_effect=lambda s, *a, **kw: s
            ),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet",
                return_value=_make_normal_packet(),
            ),
        ):
            result = CliRunner().invoke(
                cli, ["context", "test", "--floor", "0.45", "--format", "json"]
            )
        assert result.exit_code == 0, result.output
        written = [call.args[0] for call in event_log_instance.write.call_args_list]
        abstained = [e for e in written if e.event_type == "RetrievalAbstained"]
        assert len(abstained) == 0

    def test_event_also_emitted_on_search_abstention(self) -> None:
        """RetrievalAbstained event is emitted by `search` as well as `context`."""
        scored = [_make_scored(composite=0.30)]
        plan = _make_plan()
        event_log_instance = MagicMock()
        event_log_class = MagicMock(return_value=event_log_instance)
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog", event_log_class),
            patch("cerebra.retrieval.planner.query_plan", return_value=plan),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=scored),
            patch("cerebra.retrieval.trace.write_trace", return_value="trace_abs001"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings", side_effect=lambda s, *a, **kw: s
            ),
        ):
            result = CliRunner().invoke(cli, ["search", "weather", "--floor", "0.45"])
        assert result.exit_code == 1
        written = [call.args[0] for call in event_log_instance.write.call_args_list]
        abstained = [e for e in written if e.event_type == "RetrievalAbstained"]
        assert len(abstained) == 1


# ── Trace row abstained flag ───────────────────────────────────────────────────


@pytest.mark.unit
class TestTraceAbstainedFlag:
    def _migrated_db(self) -> Path:
        import tempfile

        from cerebra.storage.migrations import run_migrations

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Path(f.name)
        run_migrations(db)
        return db

    def _make_real_plan(self, trace_id: str):
        from cerebra.retrieval.planner import QueryPlan

        return QueryPlan(
            trace_id=trace_id,
            raw_query="weather forecast",
            query_d1=None,
            query_d1_d2_d3=None,
            mode="hybrid",
            max_candidates=200,
            staleness_warnings=[],
        )

    def _make_real_scored(self, record_id: str, composite: float):
        from cerebra._primitives.score_composer import CompositeScore
        from cerebra.retrieval.scorer import ScoredCandidate

        score = CompositeScore(
            composite=composite,
            components={
                "semantic": composite,
                "lexical": 0.0,
                "sku_match": 0.0,
                "recency": 1.0,
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
            step_surfaced="vector_fallback",
            retrieval_path="vector_fallback",
            score=score,
            source_path="docs/example.md",
            content_excerpt="test",
            sku_address=None,
            created_at=int(time.time()),
            rank=1,
        )

    def test_abstained_flag_one_when_all_below_floor(self) -> None:
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.storage.db import connect

        db = self._migrated_db()
        try:
            plan = self._make_real_plan("trace_tf001")
            scored = [self._make_real_scored("rec_001", 0.20)]
            now = int(time.time())
            td = TraceData(
                plan=plan,
                scored_all=scored,
                floor=0.35,
                started_at=now - 1,
                finished_at=now,
                duration_ms=100,
            )
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT abstained FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_tf001",),
                ).fetchone()
            assert row["abstained"] == 1
        finally:
            db.unlink(missing_ok=True)

    def test_abstained_flag_zero_when_any_above_floor(self) -> None:
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.storage.db import connect

        db = self._migrated_db()
        try:
            plan = self._make_real_plan("trace_tf002")
            scored = [self._make_real_scored("rec_001", 0.50)]
            now = int(time.time())
            td = TraceData(
                plan=plan,
                scored_all=scored,
                floor=0.35,
                started_at=now - 1,
                finished_at=now,
                duration_ms=100,
            )
            write_trace(td, db)
            with connect(db) as conn:
                row = conn.execute(
                    "SELECT abstained FROM retrieval_traces WHERE trace_id = ?",
                    ("trace_tf002",),
                ).fetchone()
            assert row["abstained"] == 0
        finally:
            db.unlink(missing_ok=True)
