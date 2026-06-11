"""Unit tests for cerebra memory status / promote / evict CLI commands."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli
from cerebra.cognition.working_memory import WorkingMemory, new_session
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


def _seed_memory_record(db_path: Path, record_id: str = "rec_test") -> str:
    conn = connect(db_path)
    try:
        now = int(time.time())
        src_id = f"src_{record_id}"
        doc_id = f"doc_{record_id}"
        chk_id = f"chk_{record_id}"
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(source_id, canonical_path, content_hash, size_bytes, "
            " detected_type, detection_confidence, parser_status, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (src_id, f"/test/{record_id}", "h0", 1, "markdown", 1.0, "done", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO documents "
            "(document_id, source_id, document_type, normalization_confidence, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, src_id, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO chunks "
            "(chunk_id, document_id, source_id, heading_path, chunk_index, "
            " depth, content, content_hash, token_estimate, chunk_strategy, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chk_id, doc_id, src_id, "", 0, 0, "test content here", "hc0", 5,
             "fixed", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO memory_records "
            "(record_id, record_type, source_id, document_id, chunk_id, "
            " content, content_hash, token_estimate, lifecycle_state, "
            " created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, "source_chunk", src_id, doc_id, chk_id,
             "test content here", "hr0", 5, "active", now, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return record_id


def _invoke(args: list[str]):  # type: ignore[return]
    return CliRunner(mix_stderr=False).invoke(cli, args)


# ── memory status ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMemoryStatus:
    def test_status_no_active_session_text(self) -> None:
        vault, _ = _make_vault()
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert result.exit_code == 0
        assert "No active session" in result.output

    def test_status_no_active_session_json(self) -> None:
        vault, _ = _make_vault()
        result = _invoke(["memory", "status", "--vault", str(vault), "--format", "json"])
        assert result.exit_code == 0
        d = json.loads(result.output)
        assert d["active_session"] is None

    def test_status_text_shows_session_id(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert result.exit_code == 0
        assert sid in result.output

    def test_status_text_shows_vault_path(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert str(vault) in result.output

    def test_status_text_shows_all_10_slots(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke(["memory", "status", "--vault", str(vault)])
        from cerebra.cognition._constants import SLOT_CAPACITIES
        for slot in SLOT_CAPACITIES:
            assert f"[{slot}]" in result.output, f"slot {slot!r} not in output"

    def test_status_text_shows_item_content(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        wm.promote("goal", None, "find the answer", salience_score=0.7)
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert "find the answer" in result.output

    def test_status_text_shows_pinned_marker(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        wm.promote("goal", None, "important goal", salience_score=0.9, is_pinned=True)
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert "[pinned]" in result.output

    def test_status_text_shows_tower_cited_marker(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        item = wm.promote("evidence", None, "tower evidence", salience_score=0.5)
        # Plant tower citation
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO truth_tower_items "
                "(tower_item_id, session_id, wm_item_id, tier, content_summary, "
                " salience_score, promoted_at, schema_version) "
                "VALUES (?, ?, ?, 1, 'tower cite', 0.9, ?, 1)",
                (f"twr_{item.item_id[-8:]}", sid, item.item_id, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert "^T1" in result.output

    def test_status_json_contains_slots_key(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke(["memory", "status", "--vault", str(vault), "--format", "json"])
        assert result.exit_code == 0
        d = json.loads(result.output)
        assert "slots" in d
        assert "session_id" in d
        assert "vault_path" in d

    def test_status_json_item_round_trip(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        item = wm.promote("context", None, "context text", salience_score=0.5)
        result = _invoke(["memory", "status", "--vault", str(vault), "--format", "json"])
        d = json.loads(result.output)
        ctx_items = d["slots"]["context"]
        assert any(i["item_id"] == item.item_id for i in ctx_items)

    def test_status_emits_working_memory_rendered_event(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        _invoke(["memory", "status", "--vault", str(vault)])
        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM inspector_events "
                "WHERE event_type = 'WorkingMemoryRendered'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count >= 1

    def test_status_capacity_fraction_in_text(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        wm.promote("evidence", None, "some evidence", salience_score=0.5)
        result = _invoke(["memory", "status", "--vault", str(vault)])
        assert "1/5" in result.output  # evidence capacity is 5


# ── memory promote ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMemoryPromote:
    def test_promote_text_item_success(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "my synthetic goal",
            "--slot", "goal",
        ])
        assert result.exit_code == 0
        assert "Promoted:" in result.output
        assert "goal" in result.output

    def test_promote_record_id_success(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        _seed_memory_record(db, "rec_001")
        result = _invoke([
            "memory", "promote", "rec_001",
            "--vault", str(vault),
            "--slot", "evidence",
        ])
        assert result.exit_code == 0
        assert "Promoted:" in result.output
        assert "rec_001" in result.output

    def test_promote_pin_flag(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "pinned goal",
            "--slot", "goal",
            "--pin",
        ])
        assert result.exit_code == 0
        assert "[pinned]" in result.output

    def test_promote_salience_override(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "custom salience",
            "--slot", "context",
            "--salience", "0.42",
        ])
        assert result.exit_code == 0
        assert "0.4200" in result.output

    def test_promote_unknown_slot_exits_2(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "bad slot",
            "--slot", "nonexistent_slot",
        ])
        assert result.exit_code == 2
        assert "unknown slot" in result.output.lower() or "unknown slot" in (result.stderr or "").lower()

    def test_promote_missing_slot_flag_exits_2(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "no slot flag",
        ])
        assert result.exit_code == 2

    def test_promote_missing_required_input_exits_2(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--slot", "goal",
        ])
        assert result.exit_code == 2

    def test_promote_record_id_not_found_exits_2(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote", "rec_missing",
            "--vault", str(vault),
            "--slot", "evidence",
        ])
        assert result.exit_code == 2
        assert "not found" in (result.output + (result.stderr or "")).lower()

    def test_promote_tier_2_exits_2_with_message(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "will fail",
            "--slot", "goal",
            "--tier", "2",
        ])
        assert result.exit_code == 2
        combined = result.output + (result.stderr or "")
        assert "Step 7" in combined

    def test_promote_tier_1_exits_2(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "will fail",
            "--slot", "goal",
            "--tier", "1",
        ])
        assert result.exit_code == 2

    def test_promote_auto_creates_session_if_none(self) -> None:
        vault, _db = _make_vault()
        # No session created
        result = _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "auto session item",
            "--slot", "goal",
        ])
        assert result.exit_code == 0, f"Unexpected failure: {result.output}"

    def test_promote_text_and_record_id_mutually_exclusive(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "promote", "rec_001",
            "--vault", str(vault),
            "--text", "also text",
            "--slot", "goal",
        ])
        assert result.exit_code == 2

    def test_promote_item_persists_in_wm(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        _invoke([
            "memory", "promote",
            "--vault", str(vault),
            "--text", "persisted item",
            "--slot", "context",
        ])
        wm = WorkingMemory(db, sid)
        active = wm.load_slot("context")
        assert any(i.content_summary == "persisted item" for i in active)


# ── memory evict ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMemoryEvict:
    def test_evict_success(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        item = wm.promote("goal", None, "to be evicted", salience_score=0.5)
        result = _invoke([
            "memory", "evict", item.item_id,
            "--vault", str(vault),
        ])
        assert result.exit_code == 0
        assert item.item_id in result.output

    def test_evict_removes_item_from_slot(self) -> None:
        vault, db = _make_vault()
        sid = new_session(db, str(vault))
        wm = WorkingMemory(db, sid)
        item = wm.promote("goal", None, "gone soon", salience_score=0.5)
        _invoke(["memory", "evict", item.item_id, "--vault", str(vault)])
        assert wm.load_slot("goal") == []

    def test_evict_missing_item_exits_2(self) -> None:
        vault, db = _make_vault()
        new_session(db, str(vault))
        result = _invoke([
            "memory", "evict", "wmi_nonexistent",
            "--vault", str(vault),
        ])
        assert result.exit_code == 2
        assert "not found" in (result.output + (result.stderr or "")).lower()

    def test_evict_no_session_exits_2(self) -> None:
        vault, _db = _make_vault()
        result = _invoke([
            "memory", "evict", "wmi_any",
            "--vault", str(vault),
        ])
        assert result.exit_code == 2
        assert "no active session" in (result.output + (result.stderr or "")).lower()
