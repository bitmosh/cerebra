"""Integration test: build a ContextPacket from a real vault query.

Skips automatically if numpy is unavailable (vector search requires it)
or the dev vault is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

numpy = pytest.importorskip(
    "numpy", reason="numpy not available — skipping context packet vault tests"
)

_VAULT_DB = Path.home() / "cerebra-vaults" / "dev" / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_db() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_DB


@pytest.mark.integration
class TestContextPacketAgainstVault:
    def test_leeway_network_packet_shape(self, vault_db: Path) -> None:
        """Full pipeline: query → plan → traverse → score → packet; verify shape."""
        import json
        import time

        from cerebra.inspector.sqlite_log import SQLiteEventLog
        from cerebra.retrieval.context_packet import build_context_packet
        from cerebra.retrieval.planner import query_plan
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.retrieval.traversal import run_traversal
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)
        event_log = SQLiteEventLog(vault_db)

        plan = query_plan("leeway network", vault_db, event_log=event_log)
        raw = run_traversal(plan, vault_db, event_log=event_log)
        scored_all = score_candidates(raw, plan, vault_db, event_log=event_log)

        floor = 0.35
        above_floor = [c for c in scored_all if c.score.composite >= floor]

        now = int(time.time())
        step_events = [
            json.loads(e["data_json"])
            for e in event_log.query_by_subject(plan.trace_id, "TraversalStepCompleted")
        ]
        td = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=floor,
            started_at=now - 1,
            finished_at=now,
            duration_ms=0,
            step_events=step_events,
        )
        write_trace(td, vault_db, event_log=event_log)

        pkt = build_context_packet(td, above_floor, vault_db, limit=10, event_log=event_log)

        # Shape checks
        assert pkt.context_packet_id.startswith("ctxpkt_")
        assert pkt.retrieval_trace_id == plan.trace_id
        assert pkt.query == "leeway network"
        assert pkt.is_abstained is False
        assert isinstance(pkt.selected_memory, list)
        assert pkt.selected_count == len(pkt.selected_memory)
        assert pkt.candidate_count == len(scored_all)
        assert pkt.token_estimate >= 0

    def test_packet_selected_memory_item_fields(self, vault_db: Path) -> None:
        """Each selected_memory item has the required §5 fields."""
        import time

        from cerebra.retrieval.context_packet import build_context_packet
        from cerebra.retrieval.planner import query_plan
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.retrieval.traversal import run_traversal
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        plan = query_plan("cognitive cycle runtime design", vault_db)
        raw = run_traversal(plan, vault_db)
        scored_all = score_candidates(raw, plan, vault_db)

        floor = 0.35
        above_floor = [c for c in scored_all if c.score.composite >= floor]
        if not above_floor:
            pytest.skip("No candidates above floor — cannot test item fields")

        now = int(time.time())
        td = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=floor,
            started_at=now - 1,
            finished_at=now,
            duration_ms=0,
        )
        write_trace(td, vault_db)

        pkt = build_context_packet(td, above_floor, vault_db, limit=5)

        for item in pkt.selected_memory:
            assert item.record_id, "record_id must be non-empty"
            assert item.source_path, "source_path must be non-empty"
            assert isinstance(item.score, float)
            assert isinstance(item.score_components, dict)
            assert "semantic" in item.score_components
            assert isinstance(item.retrieval_path, str)
            assert isinstance(item.rank, int) and item.rank >= 1
            assert isinstance(item.content_excerpt, str)

    def test_packet_source_paths_are_strings(self, vault_db: Path) -> None:
        """source_path values are non-empty strings."""
        import time

        from cerebra.retrieval.context_packet import build_context_packet
        from cerebra.retrieval.planner import query_plan
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.retrieval.traversal import run_traversal
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        plan = query_plan("leeway rule schema cognitive safety", vault_db)
        raw = run_traversal(plan, vault_db)
        scored_all = score_candidates(raw, plan, vault_db)

        floor = 0.35
        above_floor = [c for c in scored_all if c.score.composite >= floor]
        if not above_floor:
            pytest.skip("No candidates above floor")

        now = int(time.time())
        td = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=floor,
            started_at=now - 1,
            finished_at=now,
            duration_ms=0,
        )
        write_trace(td, vault_db)
        pkt = build_context_packet(td, above_floor, vault_db, limit=5)

        for item in pkt.selected_memory:
            assert isinstance(item.source_path, str) and item.source_path

    def test_packet_trace_row_updated(self, vault_db: Path) -> None:
        """retrieval_traces.context_packet_id is set after build."""
        import time

        from cerebra.retrieval.context_packet import build_context_packet
        from cerebra.retrieval.planner import query_plan
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.retrieval.traversal import run_traversal
        from cerebra.storage.db import connect
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        plan = query_plan("memory lifecycle decay archival", vault_db)
        raw = run_traversal(plan, vault_db)
        scored_all = score_candidates(raw, plan, vault_db)

        floor = 0.35
        above_floor = [c for c in scored_all if c.score.composite >= floor]

        now = int(time.time())
        td = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=floor,
            started_at=now - 1,
            finished_at=now,
            duration_ms=0,
        )
        write_trace(td, vault_db)
        pkt = build_context_packet(td, above_floor, vault_db)

        with connect(vault_db) as conn:
            row = conn.execute(
                "SELECT context_packet_id FROM retrieval_traces WHERE trace_id = ?",
                (plan.trace_id,),
            ).fetchone()
        assert row["context_packet_id"] == pkt.context_packet_id

    def test_packet_to_dict_json_serializable(self, vault_db: Path) -> None:
        """to_dict() output is fully JSON-serializable."""
        import json
        import time

        from cerebra.retrieval.context_packet import build_context_packet
        from cerebra.retrieval.planner import query_plan
        from cerebra.retrieval.scorer import score_candidates
        from cerebra.retrieval.trace import TraceData, write_trace
        from cerebra.retrieval.traversal import run_traversal
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        plan = query_plan("leeway network", vault_db)
        raw = run_traversal(plan, vault_db)
        scored_all = score_candidates(raw, plan, vault_db)

        floor = 0.35
        above_floor = [c for c in scored_all if c.score.composite >= floor]
        now = int(time.time())
        td = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=floor,
            started_at=now - 1,
            finished_at=now,
            duration_ms=0,
        )
        write_trace(td, vault_db)
        pkt = build_context_packet(td, above_floor, vault_db, limit=5)

        serialized = json.dumps(pkt.to_dict())
        parsed = json.loads(serialized)
        assert parsed["context_packet_id"] == pkt.context_packet_id
        assert isinstance(parsed["selected_memory"], list)
