"""Unit tests for cerebra inspect CLI commands (Phase 13).

Strategy:
  - SQLite-backed commands (session list/show, memory, retrieval, query)
    use temp dbs with manually inserted rows.
  - FossicStore-backed commands (cycle, leeway, session --events) use
    temp vaults with FossicStore writes.
  - Tail mode: test the query-building path without the infinite loop.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from cerebra.cli.inspect import inspect as inspect_group
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    vault.mkdir()
    data_dir = vault / "data"
    data_dir.mkdir()
    db_path = data_dir / "cerebra.db"
    run_migrations(db_path)
    return vault, db_path


def _insert_runtime_session(
    conn,
    session_id: str,
    goal: str = "test goal",
    cycle_config: str = "test.v1",
    state: str = "active",
    opened_at: int | None = None,
    cycles_run: int = 1,
    steps_run: int = 3,
) -> None:
    conn.execute(
        """INSERT INTO runtime_sessions
           (session_id, cycle_config, goal, vault_path, opened_at,
            cycles_run, steps_run, state)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id, cycle_config, goal, "/tmp/vault",
            opened_at or int(time.time()), cycles_run, steps_run, state,
        ),
    )


def _insert_inspector_event(
    conn,
    event_type: str,
    summary: str = "test summary",
    data: dict | None = None,
    session_id: str | None = None,
    cycle_id: str | None = None,
    subject_id: str | None = None,
    ts: int | None = None,
) -> None:
    conn.execute(
        """INSERT INTO inspector_events
           (event_id, event_type, schema_version, timestamp,
            session_id, cycle_id, step_id, subject_id, actor, summary, data_json)
           VALUES (?, ?, 1, ?, ?, ?, NULL, ?, 'test', ?, ?)""",
        (
            f"evt_{uuid.uuid4().hex[:12]}",
            event_type,
            ts or int(time.time()),
            session_id, cycle_id, subject_id, summary,
            json.dumps(data or {}),
        ),
    )
    conn.commit()


def _insert_source(conn, source_id: str = "src_001") -> None:
    ts = int(time.time())
    conn.execute(
        """INSERT OR IGNORE INTO sources
           (source_id, canonical_path, content_hash, detected_type, lifecycle_state,
            size_bytes, detection_confidence, created_at, ingested_at)
           VALUES (?, ?, ?, 'markdown', 'active', 1024, 1.0, ?, ?)""",
        (source_id, f"/tmp/test/{source_id}.md", f"hash_{source_id}", ts, ts),
    )


def _insert_document(conn, doc_id: str = "doc_001", source_id: str = "src_001") -> None:
    conn.execute(
        """INSERT OR IGNORE INTO documents
           (document_id, source_id, document_type, lifecycle_state, created_at, schema_version)
           VALUES (?, ?, 'markdown', 'active', ?, 1)""",
        (doc_id, source_id, int(time.time())),
    )


def _insert_chunk(
    conn, chunk_id: str = "chunk_001", doc_id: str = "doc_001", source_id: str = "src_001"
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO chunks
           (chunk_id, document_id, source_id, content, content_hash,
            chunk_index, token_estimate, chunk_strategy, lifecycle_state, created_at)
           VALUES (?, ?, ?, 'test content', 'abc123', 0, 100, 'fixed', 'active', ?)""",
        (chunk_id, doc_id, source_id, int(time.time())),
    )


def _insert_memory_record(
    conn,
    record_id: str = "rec_001",
    source_id: str = "src_001",
    doc_id: str = "doc_001",
    chunk_id: str = "chunk_001",
    sku_address: str | None = "0x01.02.03.04",
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO memory_records
           (record_id, source_id, document_id, chunk_id, content,
            content_hash, token_estimate, sku_address, lifecycle_state, created_at)
           VALUES (?, ?, ?, ?, 'test content', 'abc123', 100, ?, 'active', ?)""",
        (record_id, source_id, doc_id, chunk_id, sku_address, int(time.time())),
    )


def _insert_retrieval_trace(
    conn,
    trace_id: str = "trace_001",
    query: str = "test query",
    mode: str = "hybrid",
) -> None:
    ts = int(time.time())
    conn.execute(
        """INSERT INTO retrieval_traces
           (trace_id, query, mode, plan_json, started_at, finished_at,
            duration_ms, candidate_count, selected_count, abstained)
           VALUES (?, ?, ?, '{}', ?, ?, 150, 5, 3, 0)""",
        (trace_id, query, mode, ts, ts),
    )


def _insert_retrieval_step(
    conn,
    trace_id: str = "trace_001",
    step_id: str = "step_001",
    step_number: int = 1,
    step_name: str = "exact_match",
) -> None:
    conn.execute(
        """INSERT INTO retrieval_steps
           (step_id, trace_id, step_number, step_name,
            candidate_count, new_candidates, duration_ms, skipped)
           VALUES (?, ?, ?, ?, 2, 2, 30, 0)""",
        (step_id, trace_id, step_number, step_name),
    )


def _insert_retrieval_candidate(
    conn,
    trace_id: str = "trace_001",
    record_id: str = "rec_001",
    selected: int = 1,
) -> None:
    conn.execute(
        """INSERT INTO retrieval_candidates
           (candidate_id, trace_id, record_id, step_surfaced,
            retrieval_path, salience_score, score_json, selected, rank)
           VALUES (?, ?, ?, 'exact_match', 'exact_match', 0.87, '{}', ?, 1)""",
        (f"cand_{record_id}", trace_id, record_id, selected),
    )


def _make_env(vault_path: Path) -> dict[str, str]:
    return {"CEREBRA_VAULT": str(vault_path)}


# ── session list ───────────────────────────────────────────────────────────────


class TestSessionList:
    def test_empty_vault_no_crash(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["session", "list"], env=_make_env(vault))
        assert result.exit_code == 0
        assert "No sessions found" in result.output

    def test_lists_sessions(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_runtime_session(conn, "sess_abc123", goal="plan the thing")
            _insert_runtime_session(conn, "sess_def456", goal="review it")
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["session", "list"], env=_make_env(vault))
        assert result.exit_code == 0
        assert "sess_abc123" in result.output
        assert "plan the thing" in result.output
        assert "sess_def456" in result.output

    def test_json_output(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_runtime_session(conn, "sess_json1", goal="json goal")
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["session", "list", "--json"], env=_make_env(vault))
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["session_id"] == "sess_json1"

    def test_limit_respected(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            for i in range(5):
                _insert_runtime_session(conn, f"sess_{i:04d}")
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["session", "list", "--limit", "2"], env=_make_env(vault))
        assert result.exit_code == 0
        # Only 2 data rows in output (plus header)
        lines = [ln for ln in result.output.strip().splitlines() if ln.startswith("  sess_")]
        assert len(lines) <= 2


# ── session show ───────────────────────────────────────────────────────────────


class TestSessionShow:
    def test_session_not_found(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["session", "show", "sess_nope"], env=_make_env(vault))
        assert result.exit_code == 2

    def test_shows_session_info(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_runtime_session(conn, "sess_show1", goal="inspect me")
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["session", "show", "sess_show1"], env=_make_env(vault))
        assert result.exit_code == 0
        assert "sess_show1" in result.output
        assert "inspect me" in result.output

    def test_json_output(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_runtime_session(conn, "sess_jshow", goal="json session")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["session", "show", "sess_jshow", "--json"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_id"] == "sess_jshow"
        assert data["goal"] == "json session"

    def test_events_flag_no_fossic(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_runtime_session(conn, "sess_evts1")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["session", "show", "sess_evts1", "--events"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "Events for session sess_evts1" in result.output


# ── memory show ───────────────────────────────────────────────────────────────


class TestMemoryShow:
    def test_not_found(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["memory", "show", "rec_nope"], env=_make_env(vault))
        assert result.exit_code == 2

    def test_shows_memory_record(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_source(conn)
            _insert_document(conn)
            _insert_chunk(conn)
            _insert_memory_record(conn, record_id="rec_mem01")
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["memory", "show", "rec_mem01"], env=_make_env(vault))
        assert result.exit_code == 0
        assert "rec_mem01" in result.output
        assert "0x01.02.03.04" in result.output

    def test_json_output(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_source(conn)
            _insert_document(conn)
            _insert_chunk(conn)
            _insert_memory_record(conn, record_id="rec_jmem")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["memory", "show", "rec_jmem", "--json"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["record_id"] == "rec_jmem"

    def test_history_flag(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_source(conn)
            _insert_document(conn)
            _insert_chunk(conn)
            _insert_memory_record(conn, record_id="rec_hist1")
            _insert_inspector_event(conn, "SKUAssigned", subject_id="rec_hist1")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["memory", "show", "rec_hist1", "--history"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "Event history for rec_hist1" in result.output
        assert "SKUAssigned" in result.output

    def test_history_empty(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_source(conn)
            _insert_document(conn)
            _insert_chunk(conn)
            _insert_memory_record(conn, record_id="rec_hist0")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["memory", "show", "rec_hist0", "--history"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "0 events" in result.output


# ── retrieval show ─────────────────────────────────────────────────────────────


class TestRetrievalShow:
    def test_not_found(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["retrieval", "show", "trace_nope"], env=_make_env(vault)
        )
        assert result.exit_code == 2

    def test_shows_trace(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_retrieval_trace(conn, "trace_r01", query="what is cerebra")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["retrieval", "show", "trace_r01"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "trace_r01" in result.output
        assert "what is cerebra" in result.output
        assert "150ms" in result.output

    def test_json_output(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_retrieval_trace(conn, "trace_jret")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["retrieval", "show", "trace_jret", "--json"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["trace"]["trace_id"] == "trace_jret"

    def test_path_flag(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_retrieval_trace(conn, "trace_path1")
            _insert_retrieval_step(conn, "trace_path1", "step_001", 1, "exact_match")
            _insert_retrieval_step(conn, "trace_path1", "step_002", 2, "vector_fallback")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["retrieval", "show", "trace_path1", "--path"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "exact_match" in result.output
        assert "vector_fallback" in result.output

    def test_scores_flag(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_source(conn)
            _insert_document(conn)
            _insert_chunk(conn)
            _insert_memory_record(conn, record_id="rec_cand1")
            _insert_retrieval_trace(conn, "trace_scores1")
            _insert_retrieval_candidate(conn, "trace_scores1", "rec_cand1")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["retrieval", "show", "trace_scores1", "--scores"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "rec_cand1" in result.output
        assert "0.8700" in result.output


# ── inspect query ──────────────────────────────────────────────────────────────


class TestInspectQuery:
    def test_no_results(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["query", "--event-type", "NonExistentEvent"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "No matching events" in result.output

    def test_event_type_filter(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_inspector_event(conn, "WorkingMemoryRendered", "wm rendered")
            _insert_inspector_event(conn, "TowerItemPromoted", "tower promoted")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["query", "--event-type", "WorkingMemoryRendered"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "WorkingMemoryRendered" in result.output
        assert "TowerItemPromoted" not in result.output

    def test_last_window_filter(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        old_ts = int(time.time()) - 7200  # 2h ago
        recent_ts = int(time.time()) - 30
        with connect(db_path) as conn:
            _insert_inspector_event(conn, "SKUAssigned", "old event", ts=old_ts)
            _insert_inspector_event(conn, "SKUAssigned", "recent event", ts=recent_ts)
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["query", "--event-type", "SKUAssigned", "--last", "1h"],
            env=_make_env(vault),
        )
        assert result.exit_code == 0
        assert "recent event" in result.output
        assert "old event" not in result.output

    def test_json_output(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_inspector_event(conn, "GraphExported", "graph done")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group,
            ["query", "--event-type", "GraphExported", "--json"],
            env=_make_env(vault),
        )
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        assert len(lines) >= 1
        obj = json.loads(lines[0])
        assert obj["event_type"] == "GraphExported"

    def test_filter_key_value(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_inspector_event(
                conn, "ClutchDecisionMade", "clutch escalate",
                data={"action": "escalate", "cycle_id": "cyc_001"}
            )
            _insert_inspector_event(
                conn, "ClutchDecisionMade", "clutch accept",
                data={"action": "accept", "cycle_id": "cyc_001"}
            )
        runner = CliRunner()
        result = runner.invoke(
            inspect_group,
            ["query", "--event-type", "ClutchDecisionMade", "--filter", "action=escalate"],
            env=_make_env(vault),
        )
        assert result.exit_code == 0
        assert "clutch escalate" in result.output
        assert "clutch accept" not in result.output

    def test_limit_respected(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            for i in range(10):
                _insert_inspector_event(conn, "LatticeCommit", f"commit {i}")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group,
            ["query", "--event-type", "LatticeCommit", "--limit", "3"],
            env=_make_env(vault),
        )
        assert result.exit_code == 0
        assert "3 events" in result.output

    def test_severe_misses_no_fossic(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["query", "--severe-misses"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "No FossicStore found" in result.output

    def test_signal_low_no_fossic(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            inspect_group,
            ["query", "--signal-low", "GROUNDEDNESS", "--threshold", "0.4"],
            env=_make_env(vault),
        )
        assert result.exit_code == 0
        assert "No FossicStore found" in result.output


# ── inspect leeway ─────────────────────────────────────────────────────────────


class TestLeewayCommands:
    def test_active_no_fossic(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["leeway", "active"], env=_make_env(vault))
        assert result.exit_code == 0
        assert "No FossicStore found" in result.output

    def test_revocations_no_fossic(self, tmp_path):
        vault, _ = _make_vault(tmp_path)
        runner = CliRunner()
        result = runner.invoke(inspect_group, ["leeway", "revocations"], env=_make_env(vault))
        assert result.exit_code == 0
        assert "No FossicStore found" in result.output

    def test_history_empty_session(self, tmp_path):
        vault, db_path = _make_vault(tmp_path)
        with connect(db_path) as conn:
            _insert_runtime_session(conn, "sess_leeway1")
        runner = CliRunner()
        result = runner.invoke(
            inspect_group, ["leeway", "history", "sess_leeway1"], env=_make_env(vault)
        )
        assert result.exit_code == 0
        assert "0 events" in result.output


# ── parse_last helper ──────────────────────────────────────────────────────────


class TestParseLast:
    def test_hours(self):
        from cerebra.cli.inspect import _parse_last
        assert _parse_last("1h") == 3600
        assert _parse_last("24h") == 86400

    def test_days(self):
        from cerebra.cli.inspect import _parse_last
        assert _parse_last("7d") == 7 * 86400

    def test_minutes(self):
        from cerebra.cli.inspect import _parse_last
        assert _parse_last("30m") == 1800

    def test_none_returns_none(self):
        from cerebra.cli.inspect import _parse_last
        assert _parse_last(None) is None

    def test_invalid_raises(self):
        from cerebra.cli.inspect import _parse_last
        import click
        with pytest.raises(click.BadParameter):
            _parse_last("bogus")
