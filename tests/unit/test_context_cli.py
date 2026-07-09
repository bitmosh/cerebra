# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the `cerebra context` CLI command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_plan(trace_id: str = "trace_ctxtest001", mode: str = "hybrid"):
    p = MagicMock()
    p.raw_query = "test context query"
    p.mode = mode
    p.query_d1 = None
    p.query_d1_d2_d3 = None
    p.trace_id = trace_id
    p.max_candidates = 200
    p.staleness_warnings = []
    return p


def _make_scored(
    record_id: str = "rec_001",
    composite: float = 0.75,
    rank: int = 1,
    source_path: str = "docs/refined-runtime-model/EXAMPLE.md",
):
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
        step_surfaced="vector_fallback",
        retrieval_path="vector_fallback",
        score=score,
        source_path=source_path,
        content_excerpt="This is a test memory excerpt.",
        sku_address="0x5.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0",
        created_at=1_720_000_000,
        rank=rank,
    )


def _mock_packet(packet_id: str = "ctxpkt_testtest01"):
    from cerebra.retrieval.context_packet import ContextPacket, MemoryItem

    item = MemoryItem(
        record_id="rec_001",
        source_id="src_001",
        chunk_id="chk_001",
        content_excerpt="Test memory excerpt.",
        source_path="docs/refined-runtime-model/EXAMPLE.md",
        sku_address=None,
        score=0.75,
        score_components={
            "semantic": 0.80,
            "lexical": 0.50,
            "sku_match": 1.0,
            "recency": 0.90,
            "lifecycle": 1.0,
        },
        retrieval_path="vector_fallback",
        rank=1,
    )
    return ContextPacket(
        context_packet_id=packet_id,
        packet_version=1,
        schema_version=1,
        created_at=1_720_000_000,
        query="test context query",
        mode="hybrid",
        is_abstained=False,
        abstention_rationale=None,
        best_score_seen=None,
        retrieval_trace_id="trace_ctxtest001",
        origin_event_ids=["evt_aaa", "evt_bbb", "evt_ccc"],
        selected_memory=[item],
        token_estimate=5,
        selected_count=1,
        candidate_count=10,
        uncertainties=[],
        excluded_candidate_count=9,
    )


def _patched_runner(scored_list: list, plan: MagicMock | None = None, packet=None):
    import contextlib

    _plan = plan or _make_plan()
    _packet = packet or _mock_packet()

    # Stub tower — promote_to_t1 returns [], to_tower_field returns None
    _tower_stub = MagicMock()
    _tower_stub.promote_to_t1.return_value = []
    _tower_stub.to_tower_field.return_value = None

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
            patch("cerebra.retrieval.trace.write_trace", return_value="trace_ctxtest001"),
            patch("cerebra.retrieval.context_packet.build_context_packet", return_value=_packet),
            # Mock out T1 promotion path so the fake vault path causes no side-effects
            patch("cerebra.cli.lockfile.vault_lock"),
            patch("cerebra.cognition.working_memory.get_active_session", return_value="sess_fake"),
            patch("cerebra.cognition.truth_tower.TruthTower", return_value=_tower_stub),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings",
                side_effect=lambda scored, *a, **kw: scored,
            ),
        ):
            yield

    return _cm()


# ── Help ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextHelp:
    def test_help_exits_zero(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert result.exit_code == 0

    def test_help_mentions_query(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert "QUERY" in result.output

    def test_help_mentions_limit(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert "--limit" in result.output

    def test_help_mentions_floor(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert "--floor" in result.output

    def test_help_mentions_format(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert "--format" in result.output

    def test_help_mentions_out(self) -> None:
        result = CliRunner().invoke(cli, ["context", "--help"])
        assert "--out" in result.output


# ── Exit codes ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextExitCodes:
    def test_normal_result_exits_zero(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert result.exit_code == 0, result.output

    def test_no_candidates_abstains_and_exits_one(self) -> None:
        """Step 10: zero candidates → abstention path → exit 1."""
        runner = CliRunner()
        with _patched_runner([]):
            result = runner.invoke(cli, ["context", "test query"])
        assert result.exit_code == 1

    def test_vault_not_found_exits_two(self) -> None:
        runner = CliRunner()
        with patch("cerebra.cli.main._get_vault", side_effect=Exception("vault not found")):
            result = runner.invoke(cli, ["context", "test query"])
        assert result.exit_code == 2

    def test_retrieval_error_exits_two(self) -> None:
        runner = CliRunner()
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", side_effect=RuntimeError("boom")),
        ):
            result = runner.invoke(cli, ["context", "test query"])
        assert result.exit_code == 2

    def test_packet_build_error_exits_two(self) -> None:
        runner = CliRunner()
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", return_value=_make_plan()),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=[_make_scored()]),
            patch("cerebra.retrieval.trace.write_trace", return_value="t"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings",
                side_effect=lambda scored, *a, **kw: scored,
            ),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet",
                side_effect=RuntimeError("packet failure"),
            ),
        ):
            result = runner.invoke(cli, ["context", "test query"])
        assert result.exit_code == 2


# ── Text output ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextTextOutput:
    def test_text_output_contains_packet_id(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "ctxpkt_testtest01" in result.output

    def test_text_output_contains_query(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "test context query" in result.output

    def test_text_output_contains_rank(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "[1]" in result.output

    def test_text_output_contains_score(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "0.75" in result.output

    def test_text_output_contains_source_path(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "EXAMPLE.md" in result.output

    def test_text_output_no_absolute_paths(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "/home/" not in result.output
        assert "/fake/" not in result.output

    def test_text_output_shows_uncertainties_none(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query"])
        assert "Uncertainties: none" in result.output


# ── JSON output ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextJsonOutput:
    def test_json_output_parseable(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query", "--format", "json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert "context_packet_id" in parsed

    def test_json_output_has_selected_memory(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query", "--format", "json"])
        parsed = json.loads(result.output)
        assert isinstance(parsed["selected_memory"], list)

    def test_json_output_has_required_fields(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query", "--format", "json"])
        parsed = json.loads(result.output)
        for field in (
            "context_packet_id",
            "packet_version",
            "query",
            "mode",
            "is_abstained",
            "retrieval_trace_id",
            "token_estimate",
            "selected_count",
            "candidate_count",
        ):
            assert field in parsed, f"Missing field: {field}"

    def test_json_source_paths_not_absolute(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query", "--format", "json"])
        parsed = json.loads(result.output)
        for item in parsed.get("selected_memory", []):
            sp = item.get("source_path", "")
            assert not sp.startswith("/"), f"Absolute path in JSON output: {sp}"

    def test_json_score_components_present(self) -> None:
        runner = CliRunner()
        with _patched_runner([_make_scored()]):
            result = runner.invoke(cli, ["context", "test query", "--format", "json"])
        parsed = json.loads(result.output)
        assert parsed["selected_memory"][0]["score_components"]


# ── --out FILE ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextOutFile:
    def test_out_file_writes_json(self) -> None:
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
        try:
            with _patched_runner([_make_scored()]):
                result = runner.invoke(cli, ["context", "test query", "--out", str(out_path)])
            assert result.exit_code == 0, result.output
            content = json.loads(out_path.read_text())
            assert "context_packet_id" in content
        finally:
            out_path.unlink(missing_ok=True)

    def test_out_file_not_written_on_error(self) -> None:
        """If build fails, no file should be written."""
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
            out_path.unlink()  # ensure it starts absent
        try:
            with patch("cerebra.cli.main._get_vault", side_effect=Exception("vault err")):
                result = runner.invoke(cli, ["context", "test query", "--out", str(out_path)])
            assert result.exit_code == 2
            assert not out_path.exists()
        finally:
            out_path.unlink(missing_ok=True)

    def test_out_implies_json_format(self) -> None:
        """--out FILE writes JSON even without --format json."""
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
        try:
            with _patched_runner([_make_scored()]):
                runner.invoke(cli, ["context", "test query", "--out", str(out_path)])
            content = json.loads(out_path.read_text())
            assert isinstance(content, dict)
        finally:
            out_path.unlink(missing_ok=True)


# ── --limit ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContextLimit:
    def test_limit_passed_to_builder(self) -> None:
        """--limit is forwarded to build_context_packet's limit kwarg."""
        runner = CliRunner()
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", return_value=_make_plan()),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=[_make_scored()]),
            patch("cerebra.retrieval.trace.write_trace", return_value="t"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings", side_effect=lambda s, *a, **kw: s
            ),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet", return_value=_mock_packet()
            ) as mock_build,
        ):
            runner.invoke(cli, ["context", "test query", "--limit", "3"])
        mock_build.assert_called_once()
        _, kwargs = mock_build.call_args
        assert kwargs.get("limit") == 3

    def test_limit_clamped_to_200(self) -> None:
        runner = CliRunner()
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", return_value=_make_plan()),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=[_make_scored()]),
            patch("cerebra.retrieval.trace.write_trace", return_value="t"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings", side_effect=lambda s, *a, **kw: s
            ),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet", return_value=_mock_packet()
            ) as mock_build,
        ):
            runner.invoke(cli, ["context", "test query", "--limit", "999"])
        _, kwargs = mock_build.call_args
        assert kwargs.get("limit") == 200

    def test_limit_default_is_ten(self) -> None:
        runner = CliRunner()
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
            patch("cerebra.retrieval.planner.query_plan", return_value=_make_plan()),
            patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
            patch("cerebra.retrieval.scorer.score_candidates", return_value=[_make_scored()]),
            patch("cerebra.retrieval.trace.write_trace", return_value="t"),
            patch(
                "cerebra.retrieval.lattice_dedup.dedup_siblings", side_effect=lambda s, *a, **kw: s
            ),
            patch(
                "cerebra.retrieval.context_packet.build_context_packet", return_value=_mock_packet()
            ) as mock_build,
        ):
            runner.invoke(cli, ["context", "test query"])
        _, kwargs = mock_build.call_args
        assert kwargs.get("limit") == 10
