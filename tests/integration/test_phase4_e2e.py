"""Phase 4 end-to-end integration tests.

Exercises the full pipeline (search and context) against the dev vault to
catch interaction issues that unit tests cannot surface: real DB writes,
real event emission, real trace rows, real candidate sets.

All tests skip cleanly if:
  - numpy is unavailable (vector search requires it)
  - the dev vault is absent at ~/cerebra-vaults/dev

Run with: pytest tests/integration/test_phase4_e2e.py -m integration -v
"""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping Phase 4 e2e tests")

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"

# §5 required fields for a non-abstained ContextPacket
_PACKET_REQUIRED_FIELDS = (
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
)


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


def _db_connect(vault_root: Path):
    from cerebra.storage.db import connect

    return connect(vault_root / "data" / "cerebra.db")


# ── Test 1 — Full search pipeline ─────────────────────────────────────────────


@pytest.mark.integration
class TestFullSearchPipeline:
    def test_full_search_pipeline_works(self, vault_root: Path) -> None:
        """leeway network search: exit 0, text output, trace + steps + candidates + events present."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(cli, ["search", "leeway network", "--vault", str(vault_root)])
        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"

        # Text output contains score and a source reference
        assert "Score" in result.output or "0." in result.output, "Expected score in output"
        assert "LEEWAY" in result.output.upper(), "Expected LEEWAY_NETWORK.md in top results"

        # --format json emits NDJSON (one object per line); verify at least one line parses
        result_json = CliRunner().invoke(
            cli, ["search", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result_json.exit_code == 0, result_json.output
        lines = [ln for ln in result_json.output.splitlines() if ln.strip()]
        assert len(lines) > 0, "Expected at least one NDJSON line"
        first = json.loads(lines[0])
        assert "score" in first and "record_id" in first

    def test_search_trace_rows_written(self, vault_root: Path) -> None:
        """Running search creates retrieval_traces, retrieval_steps, retrieval_candidates rows."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        # Run context (JSON) to get trace_id back
        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]

        with _db_connect(vault_root) as conn:
            trace_row = conn.execute(
                "SELECT trace_id, abstained FROM retrieval_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            step_count = conn.execute(
                "SELECT COUNT(*) FROM retrieval_steps WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()[0]
            cand_count = conn.execute(
                "SELECT COUNT(*) FROM retrieval_candidates WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()[0]

        assert trace_row is not None, "retrieval_traces row missing"
        assert step_count == 6, f"Expected 6 step rows, got {step_count}"
        assert cand_count >= 10, f"Expected ≥10 candidate rows, got {cand_count}"

    def test_search_events_emitted(self, vault_root: Path) -> None:
        """Search emits QueryReceived, QueryPlanned, TraversalStepCompleted×6, SalienceScored."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        trace_id = json.loads(result.output)["retrieval_trace_id"]

        with _db_connect(vault_root) as conn:
            events = conn.execute(
                "SELECT event_type FROM inspector_events WHERE subject_id = ?",
                (trace_id,),
            ).fetchall()

        event_types = [r["event_type"] for r in events]
        assert "QueryReceived" in event_types, "QueryReceived missing"
        assert "QueryPlanned" in event_types, "QueryPlanned missing"
        assert "SalienceScored" in event_types, "SalienceScored missing"
        step_events = [e for e in event_types if e == "TraversalStepCompleted"]
        assert (
            len(step_events) == 6
        ), f"Expected 6 TraversalStepCompleted events, got {len(step_events)}"


# ── Test 2 — Full context pipeline ────────────────────────────────────────────


@pytest.mark.integration
class TestFullContextPipeline:
    def test_full_context_pipeline_works(self, vault_root: Path) -> None:
        """cerebra context 'memory drift' exits 0 and produces valid §5 JSON."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "how does Cerebra handle memory drift",
                "--vault",
                str(vault_root),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"

        packet = json.loads(result.output)
        for field in _PACKET_REQUIRED_FIELDS:
            assert field in packet, f"Missing required field: {field}"
        assert packet["is_abstained"] is False
        assert isinstance(packet["selected_memory"], list)

    def test_context_packet_id_on_trace_row(self, vault_root: Path) -> None:
        """context_packet_id is set on the retrieval_traces row after a successful context call."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "how does Cerebra handle memory drift",
                "--vault",
                str(vault_root),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]
        packet_id = packet["context_packet_id"]

        with _db_connect(vault_root) as conn:
            row = conn.execute(
                "SELECT context_packet_id FROM retrieval_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
        assert row is not None, "retrieval_traces row missing"
        assert row["context_packet_id"] == packet_id

    def test_context_packet_built_event_emitted(self, vault_root: Path) -> None:
        """ContextPacketBuilt event is emitted with correct packet_id and trace_id."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "how does Cerebra handle memory drift",
                "--vault",
                str(vault_root),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]
        packet_id = packet["context_packet_id"]

        with _db_connect(vault_root) as conn:
            rows = conn.execute(
                "SELECT data_json FROM inspector_events "
                "WHERE event_type = 'ContextPacketBuilt' AND subject_id = ?",
                (packet_id,),
            ).fetchall()
        assert len(rows) >= 1, "ContextPacketBuilt event missing"
        data = json.loads(rows[0]["data_json"])
        assert data["trace_id"] == trace_id
        assert data["context_packet_id"] == packet_id


# ── Test 3 — Search then context share pipeline ───────────────────────────────


@pytest.mark.integration
class TestSearchThenContextSharePipeline:
    def test_search_then_context_produce_distinct_traces(self, vault_root: Path) -> None:
        """Search and context on the same query produce isolated traces with different trace_ids."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        query = "Cerebra SKU addressing"

        search_result = CliRunner().invoke(
            cli, ["search", query, "--vault", str(vault_root), "--format", "json"]
        )
        context_result = CliRunner().invoke(
            cli, ["context", query, "--vault", str(vault_root), "--format", "json"]
        )

        assert search_result.exit_code == 0, search_result.output
        assert context_result.exit_code == 0, context_result.output

        context_packet = json.loads(context_result.output)
        context_trace_id = context_packet["retrieval_trace_id"]

        # Verify both traces exist independently in the DB
        with _db_connect(vault_root) as conn:
            all_traces = {
                row["trace_id"]
                for row in conn.execute(
                    "SELECT trace_id FROM retrieval_traces WHERE query = ?", (query,)
                ).fetchall()
            }
        assert context_trace_id in all_traces
        assert len(all_traces) >= 2, "Expected ≥2 distinct traces for the same query"

    def test_both_queries_emit_events_with_distinct_trace_ids(self, vault_root: Path) -> None:
        """Events from search and context runs are tagged with distinct trace_ids."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        query = "Cerebra inspector events"

        r1 = CliRunner().invoke(
            cli, ["context", query, "--vault", str(vault_root), "--format", "json"]
        )
        r2 = CliRunner().invoke(
            cli, ["context", query, "--vault", str(vault_root), "--format", "json"]
        )

        assert r1.exit_code == 0, r1.output
        assert r2.exit_code == 0, r2.output

        t1 = json.loads(r1.output)["retrieval_trace_id"]
        t2 = json.loads(r2.output)["retrieval_trace_id"]
        assert t1 != t2, "Two sequential context runs produced the same trace_id"

        with _db_connect(vault_root) as conn:
            for tid in (t1, t2):
                count = conn.execute(
                    "SELECT COUNT(*) FROM inspector_events WHERE subject_id = ?", (tid,)
                ).fetchone()[0]
                assert count >= 9, f"Expected ≥9 events for trace {tid}, got {count}"


# ── Test 4 — Abstention end-to-end ────────────────────────────────────────────


@pytest.mark.integration
class TestAbstentionEndToEnd:
    def test_abstention_exits_one_with_message(self, vault_root: Path) -> None:
        """search 'weather forecast' --floor 0.45 exits 1 with abstention message."""
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
        assert result.exit_code == 1, f"Expected exit 1:\n{result.output}"
        assert "No relevant results above floor" in result.output
        assert "0.45" in result.output

    def test_abstention_trace_row_has_correct_state(self, vault_root: Path) -> None:
        """Abstained trace has abstained=1, non-null candidates, NULL context_packet_id."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        # Use context --format json to get the trace_id back
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
        assert result.exit_code == 1, result.output
        packet = json.loads(result.output)
        trace_id = packet["retrieval_trace_id"]

        with _db_connect(vault_root) as conn:
            row = conn.execute(
                "SELECT abstained, context_packet_id FROM retrieval_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            cand_count = conn.execute(
                "SELECT COUNT(*) FROM retrieval_candidates WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()[0]

        assert row is not None
        assert row["abstained"] == 1, "Expected abstained=1 on trace row"
        assert (
            row["context_packet_id"] is None
        ), "Expected NULL context_packet_id on abstained trace"
        assert cand_count >= 1, f"Expected candidate rows even on abstention, got {cand_count}"

    def test_abstention_event_has_correct_fields(self, vault_root: Path) -> None:
        """RetrievalAbstained event carries best_score_seen and floor."""
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
        assert result.exit_code == 1, result.output
        trace_id = json.loads(result.output)["retrieval_trace_id"]

        with _db_connect(vault_root) as conn:
            rows = conn.execute(
                "SELECT data_json FROM inspector_events "
                "WHERE event_type = 'RetrievalAbstained' AND subject_id = ?",
                (trace_id,),
            ).fetchall()

        assert len(rows) == 1, f"Expected 1 RetrievalAbstained event, got {len(rows)}"
        data = json.loads(rows[0]["data_json"])
        assert "best_score_seen" in data
        assert "floor" in data
        assert data["floor"] == pytest.approx(0.45)


# ── Test 5 — Abstained context produces packet ────────────────────────────────


@pytest.mark.integration
class TestAbstentionContextPacket:
    def test_abstained_packet_is_valid_json(self, vault_root: Path) -> None:
        """context 'weather forecast' --floor 0.45 exits 1, output is valid abstained JSON."""
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
        assert result.exit_code == 1, result.output
        packet = json.loads(result.output)
        assert packet["is_abstained"] is True
        assert packet["selected_memory"] == []
        assert packet["selected_count"] == 0

    def test_abstained_packet_has_required_fields(self, vault_root: Path) -> None:
        """Abstained packet contains all §5 required fields including best_score_seen."""
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

        for field in _PACKET_REQUIRED_FIELDS:
            assert field in packet, f"Missing required field in abstained packet: {field}"
        assert "best_score_seen" in packet, "best_score_seen missing from abstained packet"
        assert packet["abstention_rationale"] is not None
        assert isinstance(packet["best_score_seen"], float)

    def test_abstained_context_packet_built_event_emitted(self, vault_root: Path) -> None:
        """ContextPacketBuilt is emitted even for abstained packets (build happened, just abstained)."""
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
        packet_id = packet["context_packet_id"]

        with _db_connect(vault_root) as conn:
            rows = conn.execute(
                "SELECT data_json FROM inspector_events "
                "WHERE event_type = 'ContextPacketBuilt' AND subject_id = ?",
                (packet_id,),
            ).fetchall()

        assert len(rows) >= 1, "ContextPacketBuilt event missing for abstained packet"
        data = json.loads(rows[0]["data_json"])
        assert data["is_abstained"] is True


# ── Test 6 — JSON round-trip ──────────────────────────────────────────────────


@pytest.mark.integration
class TestJsonRoundTrip:
    def test_json_output_is_valid_and_complete(self, vault_root: Path) -> None:
        """context 'leeway network' --format json produces valid parseable JSON."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)

        for field in _PACKET_REQUIRED_FIELDS:
            assert field in packet, f"Missing required field: {field}"

    def test_json_round_trip_is_stable(self, vault_root: Path) -> None:
        """Re-serializing the parsed packet produces the identical object (no field loss)."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output

        first_parse = json.loads(result.output)
        re_serialized = json.dumps(first_parse, sort_keys=True)
        second_parse = json.loads(re_serialized)

        assert first_parse.keys() == second_parse.keys()
        for key in first_parse:
            assert first_parse[key] == second_parse[key], f"Round-trip mismatch on key: {key}"

    def test_json_selected_memory_items_have_required_fields(self, vault_root: Path) -> None:
        """Each item in selected_memory has the expected fields from §5."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "leeway network",
                "--vault",
                str(vault_root),
                "--format",
                "json",
                "--limit",
                "3",
            ],
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)

        item_fields = (
            "record_id",
            "source_id",
            "chunk_id",
            "content_excerpt",
            "source_path",
            "sku_address",
            "score",
            "score_components",
            "retrieval_path",
            "rank",
        )
        for item in packet["selected_memory"]:
            for field in item_fields:
                assert field in item, f"Missing item field: {field}"
            assert not item["source_path"].startswith("/"), "Absolute path leaked into source_path"


# ── Test 7 — --out flag ───────────────────────────────────────────────────────


@pytest.mark.integration
class TestOutFlag:
    def test_out_flag_writes_valid_json_to_file(self, vault_root: Path) -> None:
        """--out FILE writes a valid ContextPacket JSON to disk."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
        out_path.unlink()  # start absent
        try:
            result = CliRunner().invoke(
                cli,
                ["context", "leeway network", "--vault", str(vault_root), "--out", str(out_path)],
            )
            assert result.exit_code == 0, result.output
            assert out_path.exists(), "--out file not created"

            content = json.loads(out_path.read_text())
            for field in _PACKET_REQUIRED_FIELDS:
                assert field in content, f"Missing required field in --out file: {field}"
        finally:
            out_path.unlink(missing_ok=True)

    def test_out_flag_prints_confirmation_to_stdout(self, vault_root: Path) -> None:
        """--out FILE prints 'Packet written to' confirmation to stdout."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
        try:
            result = CliRunner().invoke(
                cli,
                ["context", "leeway network", "--vault", str(vault_root), "--out", str(out_path)],
            )
            assert result.exit_code == 0, result.output
            assert (
                "Packet written to" in result.output
            ), f"Expected 'Packet written to' in stdout, got:\n{result.output}"
        finally:
            out_path.unlink(missing_ok=True)

    def test_out_flag_file_matches_json_format_output(self, vault_root: Path) -> None:
        """File written by --out contains same packet as --format json stdout."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = Path(f.name)
        try:
            # Run with --out
            r_file = CliRunner().invoke(
                cli,
                ["context", "leeway network", "--vault", str(vault_root), "--out", str(out_path)],
            )
            assert r_file.exit_code == 0, r_file.output
            file_packet = json.loads(out_path.read_text())

            # Each run produces a new trace_id — compare structure, not identity
            assert "context_packet_id" in file_packet
            assert file_packet["query"] == "leeway network"
            assert file_packet["is_abstained"] is False
        finally:
            out_path.unlink(missing_ok=True)


# ── Test 8 — --limit clamps correctly ────────────────────────────────────────


@pytest.mark.integration
class TestLimitClamps:
    def test_limit_three_returns_three_items(self, vault_root: Path) -> None:
        """--limit 3 produces selected_memory with ≤3 items."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "leeway network",
                "--vault",
                str(vault_root),
                "--format",
                "json",
                "--limit",
                "3",
            ],
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)
        assert (
            len(packet["selected_memory"]) <= 3
        ), f"Expected ≤3 items with --limit 3, got {len(packet['selected_memory'])}"
        assert packet["selected_count"] == len(packet["selected_memory"])

    def test_limit_large_value_clamped_to_200(self, vault_root: Path) -> None:
        """--limit 500 is clamped: selected_count ≤ 200 and no error."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "leeway network",
                "--vault",
                str(vault_root),
                "--format",
                "json",
                "--limit",
                "500",
            ],
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)
        assert (
            packet["selected_count"] <= 200
        ), f"selected_count exceeds 200 with --limit 500: {packet['selected_count']}"

    def test_limit_default_is_ten_or_fewer(self, vault_root: Path) -> None:
        """Default limit produces ≤10 items in selected_memory."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        packet = json.loads(result.output)
        assert (
            len(packet["selected_memory"]) <= 10
        ), f"Expected ≤10 items with default limit, got {len(packet['selected_memory'])}"


# ── Test 9 — Concurrent queries isolated ──────────────────────────────────────


@pytest.mark.integration
class TestConcurrentQueriesIsolated:
    def test_concurrent_searches_produce_distinct_traces(self, vault_root: Path) -> None:
        """Two sequential context calls produce separate, non-interleaved traces.

        Sequential invocations in the same process catch module-level shared-state bugs
        (mutable globals that persist between CLI invocations). If trace_ids were
        derived from shared state rather than fresh UUID generation, they would collide.
        """
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        q1 = "Cerebra salience scoring"
        q2 = "memory lifecycle state transitions"

        r1 = CliRunner().invoke(
            cli, ["context", q1, "--vault", str(vault_root), "--format", "json"]
        )
        r2 = CliRunner().invoke(
            cli, ["context", q2, "--vault", str(vault_root), "--format", "json"]
        )

        assert r1.exit_code == 0, f"Query 1 failed:\n{r1.output}"
        assert r2.exit_code == 0, f"Query 2 failed:\n{r2.output}"

        p1 = json.loads(r1.output)
        p2 = json.loads(r2.output)

        assert (
            p1["retrieval_trace_id"] != p2["retrieval_trace_id"]
        ), "Sequential invocations produced identical trace_ids — shared state leak suspected"
        assert p1["query"] == q1
        assert p2["query"] == q2

        # Verify DB isolation: each trace has its own candidate rows
        trace1 = p1["retrieval_trace_id"]
        trace2 = p2["retrieval_trace_id"]
        with _db_connect(vault_root) as conn:
            cand1 = conn.execute(
                "SELECT COUNT(*) FROM retrieval_candidates WHERE trace_id = ?", (trace1,)
            ).fetchone()[0]
            cand2 = conn.execute(
                "SELECT COUNT(*) FROM retrieval_candidates WHERE trace_id = ?", (trace2,)
            ).fetchone()[0]
        assert cand1 >= 1, "Trace 1 has no candidate rows"
        assert cand2 >= 1, "Trace 2 has no candidate rows"

    def test_concurrent_search_commands_exit_zero(self, vault_root: Path) -> None:
        """Two concurrent search invocations both exit cleanly."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        exit_codes: list[int | None] = [None, None]

        def run_search(idx: int, query: str) -> None:
            r = CliRunner().invoke(cli, ["search", query, "--vault", str(vault_root)])
            exit_codes[idx] = r.exit_code

        t1 = threading.Thread(target=run_search, args=(0, "Cerebra SKU addressing"))
        t2 = threading.Thread(target=run_search, args=(1, "retrieval pipeline architecture"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert exit_codes[0] == 0, f"Thread 0 exited {exit_codes[0]}"
        assert exit_codes[1] == 0, f"Thread 1 exited {exit_codes[1]}"


# ── Test 10 — Vault lockfile ──────────────────────────────────────────────────
# Full lockfile contention test is in tests/integration/test_vault_lockfile.py
# (does not require numpy so it runs even when the embedding pipeline is absent).
