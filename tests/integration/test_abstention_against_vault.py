# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the abstention path against the real dev vault.

Verifies that the floor check, exit codes, abstained packet shape, and
RetrievalAbstained event behave correctly end-to-end with real embeddings.

Skips automatically when numpy is unavailable or the dev vault is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping abstention vault tests")

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


@pytest.mark.integration
class TestSearchAbstentionAgainstVault:
    def test_weather_query_abstains_with_high_floor(self, vault_root: Path) -> None:
        """cerebra search 'weather forecast for tomorrow' --floor 0.45 → exit 1."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "search",
                "weather forecast for tomorrow",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
            ],
        )
        assert (
            result.exit_code == 1
        ), f"Expected exit 1 (abstain), got {result.exit_code}.\n{result.output}"
        assert "No relevant results above floor" in result.output
        assert "0.45" in result.output

    def test_weather_query_does_not_abstain_with_default_floor(self, vault_root: Path) -> None:
        """cerebra search 'weather forecast for tomorrow' (default floor 0.35) → exit 0."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            ["search", "weather forecast for tomorrow", "--vault", str(vault_root)],
        )
        assert (
            result.exit_code == 0
        ), f"Expected exit 0 (no abstain), got {result.exit_code}.\n{result.output}"

    def test_leeway_query_does_not_abstain_with_high_floor(self, vault_root: Path) -> None:
        """cerebra search 'leeway network' --floor 0.45 → exit 0 (score ~0.47)."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            ["search", "leeway network", "--vault", str(vault_root), "--floor", "0.45"],
        )
        assert (
            result.exit_code == 0
        ), f"Expected exit 0 (no abstain), got {result.exit_code}.\n{result.output}"

    def test_weather_abstention_message_contains_best_score(self, vault_root: Path) -> None:
        """The abstention message includes the actual best score seen."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "search",
                "weather forecast for tomorrow",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
            ],
        )
        assert result.exit_code == 1
        # Message format: "No relevant results above floor 0.45 (best score: X.XX)"
        assert "best score:" in result.output


@pytest.mark.integration
class TestContextAbstentionAgainstVault:
    def test_weather_context_abstains_json_format(self, vault_root: Path) -> None:
        """cerebra context 'weather...' --floor 0.45 --format json → exit 1, abstained packet."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "weather forecast for tomorrow",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
                "--format",
                "json",
            ],
        )
        assert (
            result.exit_code == 1
        ), f"Expected exit 1 (abstain), got {result.exit_code}.\n{result.output}"
        packet = json.loads(result.output)
        assert packet["is_abstained"] is True
        assert packet["selected_memory"] == []
        assert packet["selected_count"] == 0

    def test_weather_context_abstained_packet_shape(self, vault_root: Path) -> None:
        """Abstained packet from context has all required §5 fields."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "weather forecast for tomorrow",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 1
        packet = json.loads(result.output)

        required = (
            "context_packet_id",
            "packet_version",
            "schema_version",
            "created_at",
            "query",
            "mode",
            "is_abstained",
            "abstention_rationale",
            "retrieval_trace_id",
            "origin_event_ids",
            "selected_memory",
            "token_estimate",
            "selected_count",
            "candidate_count",
            "excluded_candidate_count",
            "best_score_seen",
        )
        for field in required:
            assert field in packet, f"Missing required field in abstained packet: {field}"

        assert packet["abstention_rationale"] is not None
        assert isinstance(packet["best_score_seen"], float)
        assert isinstance(packet["selected_memory"], list)

    def test_leeway_context_not_abstained(self, vault_root: Path) -> None:
        """cerebra context 'leeway network' --floor 0.45 → exit 0, is_abstained=False."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "leeway network",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}.\n{result.output}"
        packet = json.loads(result.output)
        assert packet["is_abstained"] is False

    def test_weather_context_text_format_abstained(self, vault_root: Path) -> None:
        """cerebra context 'weather...' --floor 0.45 (text) → exit 1, 'Abstained' in output."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "weather forecast for tomorrow",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
            ],
        )
        assert result.exit_code == 1
        assert "Abstained" in result.output


@pytest.mark.integration
class TestRetrievalAbstainedEventAgainstVault:
    def test_abstained_event_written_to_db_on_weather_query(self, vault_root: Path) -> None:
        """Running an abstaining query writes a RetrievalAbstained event to inspector_events."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.storage.db import connect

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "weather forecast for tomorrow",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 1

        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]

        db_path = vault_root / "data" / "cerebra.db"
        with connect(db_path) as conn:
            rows = conn.execute(
                "SELECT event_type, data_json FROM inspector_events "
                "WHERE subject_id = ? AND event_type = 'RetrievalAbstained'",
                (trace_id,),
            ).fetchall()

        assert len(rows) == 1, f"Expected 1 RetrievalAbstained event, got {len(rows)}"
        data = json.loads(rows[0]["data_json"])
        assert "best_score_seen" in data
        assert "floor" in data

    def test_abstained_event_not_written_for_leeway_query(self, vault_root: Path) -> None:
        """A non-abstaining query does NOT produce a RetrievalAbstained event."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.storage.db import connect

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "leeway network",
                "--vault",
                str(vault_root),
                "--floor",
                "0.45",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output

        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]

        db_path = vault_root / "data" / "cerebra.db"
        with connect(db_path) as conn:
            rows = conn.execute(
                "SELECT 1 FROM inspector_events "
                "WHERE subject_id = ? AND event_type = 'RetrievalAbstained'",
                (trace_id,),
            ).fetchall()

        assert (
            len(rows) == 0
        ), "RetrievalAbstained event should NOT be present for non-abstaining query"
