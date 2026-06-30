"""Unit tests for the `cerebra search` CLI command.

Tests argparse handling, output formats, exit codes, and flag behaviour
using Click's CliRunner. Retrieval is mocked so tests are fast and offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli

# ── Test fixtures ──────────────────────────────────────────────────────────────


def _make_scored(
    record_id: str = "rec_001",
    composite: float = 0.75,
    rank: int = 1,
    source_path: str = "docs/example.md",
    retrieval_path: str = "vector_fallback",
) -> MagicMock:
    """Build a mock ScoredCandidate."""
    from cerebra._primitives.score_composer import CompositeScore

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
    c = MagicMock()
    c.record_id = record_id
    c.rank = rank
    c.score = score
    c.source_path = source_path
    c.retrieval_path = retrieval_path
    c.sku_address = "0x5.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0"
    c.created_at = 1_720_000_000
    c.content_excerpt = "This is a test memory record for the leeway network."
    return c


def _make_plan(mode: str = "hybrid", query_d1: int | None = None) -> MagicMock:
    """Build a mock QueryPlan."""
    p = MagicMock()
    p.raw_query = "test query"
    p.mode = mode
    p.query_d1 = query_d1
    p.query_d1_d2_d3 = None
    p.trace_id = "trace_testtest001"
    p.max_candidates = 200
    p.staleness_warnings = []
    return p


def _patched_runner(scored_list: list, plan: MagicMock | None = None):
    """Context manager that patches the retrieval pipeline for search tests."""
    import contextlib

    _plan = plan or _make_plan()

    @contextlib.contextmanager
    def _cm():
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("cerebra.cli.main.json.dumps", wraps=json.dumps),
        ):
            with (
                patch("cerebra.storage.migrations.run_migrations"),
                patch("cerebra.inspector.sqlite_log.SQLiteEventLog"),
                patch("cerebra.retrieval.planner.query_plan", return_value=_plan),
                patch("cerebra.retrieval.traversal.run_traversal", return_value=[]),
                patch(
                    "cerebra.retrieval.scorer.score_candidates",
                    return_value=scored_list,
                ),
                patch("cerebra.retrieval.trace.write_trace", return_value="trace_testtest001"),
                patch("pathlib.Path.exists", return_value=True),
                patch(
                    "cerebra.retrieval.lattice_dedup.dedup_siblings",
                    side_effect=lambda scored, *a, **kw: scored,
                ),
            ):
                yield

    return _cm()


# ── Help and basic invocation ──────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchHelp:
    def test_help_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0

    def test_help_mentions_query(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "QUERY" in result.output

    def test_help_mentions_limit(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--limit" in result.output

    def test_help_mentions_floor(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--floor" in result.output

    def test_help_mentions_format(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--format" in result.output

    def test_help_mentions_explain(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--explain" in result.output


# ── Exit codes ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchExitCodes:
    def test_results_above_floor_exits_zero(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(composite=0.75)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert result.exit_code == 0, result.output

    def test_no_results_above_floor_exits_one(self) -> None:
        runner = CliRunner()
        # All scored below floor
        scored = [_make_scored(composite=0.20, rank=1)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--floor", "0.50"])
        assert result.exit_code == 1

    def test_empty_scored_list_exits_one(self) -> None:
        runner = CliRunner()
        with _patched_runner([]):
            result = runner.invoke(cli, ["search", "test query"])
        assert result.exit_code == 1

    def test_vault_not_found_exits_two(self) -> None:
        runner = CliRunner()
        with patch("cerebra.cli.main._get_vault", side_effect=Exception("vault missing")):
            result = runner.invoke(cli, ["search", "test query"])
        assert result.exit_code == 2


# ── Output format — text ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchTextOutput:
    def test_output_contains_query(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "test query" in result.output

    def test_output_contains_mode(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored, plan=_make_plan(mode="hybrid")):
            result = runner.invoke(cli, ["search", "test query"])
        assert "hybrid" in result.output

    def test_output_contains_rank(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(rank=1)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "1" in result.output

    def test_output_contains_score(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(composite=0.75)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "0.75" in result.output

    def test_output_contains_source_path(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(source_path="docs/example.md")]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "docs/example.md" in result.output or "example.md" in result.output

    def test_output_contains_retrieval_paths_section(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(retrieval_path="vector_fallback")]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "Retrieval paths" in result.output

    def test_output_contains_retrieval_path_value(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(retrieval_path="vector_fallback")]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "vector_fallback" in result.output

    def test_explain_flag_adds_score_breakdown(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--explain"])
        assert "semantic" in result.output or "Score breakdown" in result.output

    def test_no_explain_by_default(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query"])
        assert "Score breakdown" not in result.output

    def test_d1_none_shows_none(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored, plan=_make_plan(query_d1=None)):
            result = runner.invoke(cli, ["search", "test query"])
        assert "D1: none" in result.output

    def test_d1_five_shows_design(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored, plan=_make_plan(query_d1=5)):
            result = runner.invoke(cli, ["search", "test query"])
        assert "DESIGN" in result.output


# ── Output format — JSON ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchJsonOutput:
    def test_json_output_is_parseable(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        assert result.exit_code == 0
        line = result.output.strip().splitlines()[0]
        obj = json.loads(line)
        assert isinstance(obj, dict)

    def test_json_output_has_rank(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(rank=1)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        obj = json.loads(result.output.strip().splitlines()[0])
        assert obj["rank"] == 1

    def test_json_output_has_score(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(composite=0.75)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        obj = json.loads(result.output.strip().splitlines()[0])
        assert abs(obj["score"] - 0.75) < 0.01

    def test_json_output_has_components(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        obj = json.loads(result.output.strip().splitlines()[0])
        assert "components" in obj
        assert "semantic" in obj["components"]

    def test_json_explain_flag_adds_explain_key(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json", "--explain"])
        obj = json.loads(result.output.strip().splitlines()[0])
        assert "explain" in obj

    def test_json_no_explain_key_without_flag(self) -> None:
        runner = CliRunner()
        scored = [_make_scored()]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        obj = json.loads(result.output.strip().splitlines()[0])
        assert "explain" not in obj

    def test_json_empty_result_exits_one(self) -> None:
        runner = CliRunner()
        with _patched_runner([]):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        assert result.exit_code == 1

    def test_json_one_line_per_candidate(self) -> None:
        runner = CliRunner()
        scored = [
            _make_scored(record_id="rec_a", rank=1),
            _make_scored(record_id="rec_b", rank=2),
        ]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 2


# ── Limit flag ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchLimit:
    def test_limit_caps_output_lines(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(record_id=f"rec_{i}", rank=i + 1) for i in range(20)]
        with _patched_runner(scored):
            result = runner.invoke(
                cli, ["search", "test query", "--format", "json", "--limit", "3"]
            )
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_limit_default_is_ten(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(record_id=f"rec_{i}", rank=i + 1) for i in range(15)]
        with _patched_runner(scored):
            result = runner.invoke(cli, ["search", "test query", "--format", "json"])
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 10

    def test_limit_clamped_to_200(self) -> None:
        runner = CliRunner()
        scored = [_make_scored(record_id=f"rec_{i}", rank=i + 1) for i in range(5)]
        with _patched_runner(scored):
            # --limit 999 should be clamped to 200 internally, but only 5 candidates exist
            result = runner.invoke(
                cli, ["search", "test query", "--format", "json", "--limit", "999"]
            )
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 5  # only 5 candidates available


# ── Floor flag ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchFloor:
    def test_floor_filters_below_threshold(self) -> None:
        runner = CliRunner()
        scored = [
            _make_scored(record_id="hi", composite=0.80, rank=1),
            _make_scored(record_id="lo", composite=0.20, rank=2),
        ]
        with _patched_runner(scored):
            result = runner.invoke(
                cli, ["search", "test query", "--format", "json", "--floor", "0.50"]
            )
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["record_id"] == "hi"

    def test_floor_zero_shows_all(self) -> None:
        runner = CliRunner()
        scored = [
            _make_scored(record_id="a", composite=0.10, rank=1),
            _make_scored(record_id="b", composite=0.05, rank=2),
        ]
        with _patched_runner(scored):
            result = runner.invoke(
                cli, ["search", "test query", "--format", "json", "--floor", "0.0"]
            )
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 2
