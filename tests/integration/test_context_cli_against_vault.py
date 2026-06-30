"""Integration test: run `cerebra context` CLI against the real dev vault.

Skips automatically if numpy is unavailable or the dev vault is absent.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping context CLI vault tests")

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


@pytest.mark.integration
class TestContextCliAgainstVault:
    def test_leeway_network_packet_generated(self, vault_root: Path) -> None:
        """cerebra context 'leeway network' exits 0 and outputs a ContextPacket."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"
        assert "ContextPacket" in result.output
        assert "ctxpkt_" in result.output

    def test_leeway_network_trace_written(self, vault_root: Path) -> None:
        """Running context creates a retrieval_traces row with context_packet_id set."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.storage.db import connect

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json", "--limit", "3"]
        )
        assert result.exit_code == 0, result.output

        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]
        packet_id = packet["context_packet_id"]

        db_path = vault_root / "data" / "cerebra.db"
        with connect(db_path) as conn:
            row = conn.execute(
                "SELECT context_packet_id FROM retrieval_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
        assert row is not None, "No retrieval_traces row for trace_id"
        assert row["context_packet_id"] == packet_id

    def test_leeway_network_selected_memory_references_real_records(self, vault_root: Path) -> None:
        """selected_memory items have record_ids that exist in memory_records."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.storage.db import connect

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output

        packet = json.loads(result.output)
        if not packet["selected_memory"]:
            pytest.skip("No selected_memory items — cannot verify record references")

        db_path = vault_root / "data" / "cerebra.db"
        with connect(db_path) as conn:
            for item in packet["selected_memory"]:
                rid = item["record_id"]
                row = conn.execute(
                    "SELECT 1 FROM memory_records WHERE record_id = ?", (rid,)
                ).fetchone()
                assert row is not None, f"record_id {rid!r} not found in memory_records"

    def test_context_json_output_schema(self, vault_root: Path) -> None:
        """JSON output matches the ContextPacket §5 schema (required fields present)."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "cognitive cycle runtime design", "--vault", str(vault_root),
                  "--format", "json", "--limit", "5"]
        )
        assert result.exit_code == 0, result.output

        packet = json.loads(result.output)
        required = (
            "context_packet_id", "packet_version", "schema_version",
            "created_at", "query", "mode", "is_abstained", "retrieval_trace_id",
            "origin_event_ids", "selected_memory", "token_estimate",
            "selected_count", "candidate_count", "excluded_candidate_count",
        )
        for field in required:
            assert field in packet, f"Missing required field: {field}"

        assert isinstance(packet["selected_memory"], list)
        assert isinstance(packet["origin_event_ids"], list)
        assert packet["is_abstained"] is False

    def test_out_file_writes_valid_json(self, vault_root: Path) -> None:
        """--out FILE writes a valid JSON ContextPacket to disk."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
        out_path.unlink()

        try:
            result = CliRunner().invoke(
                cli, ["context", "leeway network", "--vault", str(vault_root),
                      "--out", str(out_path), "--limit", "3"]
            )
            assert result.exit_code == 0, result.output
            assert out_path.exists(), "--out FILE was not created"

            content = json.loads(out_path.read_text())
            assert "context_packet_id" in content
            assert isinstance(content["selected_memory"], list)
        finally:
            out_path.unlink(missing_ok=True)

    def test_selected_memory_source_paths_not_absolute(self, vault_root: Path) -> None:
        """source_path in JSON output is vault-relative (no leading slash)."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output

        packet = json.loads(result.output)
        if not packet["selected_memory"]:
            pytest.skip("No selected_memory items")

        for item in packet["selected_memory"]:
            sp = item["source_path"]
            assert not sp.startswith("/"), f"Absolute source_path in JSON: {sp}"
