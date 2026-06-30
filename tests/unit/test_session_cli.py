"""Unit tests for cerebra session show and cerebra session reset CLI commands."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli
from cerebra.storage.migrations import run_migrations


def _make_vault() -> tuple[Path, Path]:
    """Return (vault_root, db_path) for a temp vault with migrations applied."""
    d = tempfile.mkdtemp()
    vault = Path(d)
    (vault / "data").mkdir()
    db = vault / "data" / "cerebra.db"
    run_migrations(db)
    return vault, db


@pytest.mark.unit
class TestSessionShow:
    def test_show_no_active_session_text(self) -> None:
        vault, _ = _make_vault()
        result = CliRunner().invoke(cli, ["session", "show", "--vault", str(vault)])
        assert result.exit_code == 0
        assert "No active session" in result.output

    def test_show_no_active_session_json(self) -> None:
        vault, _ = _make_vault()
        result = CliRunner().invoke(
            cli, ["session", "show", "--vault", str(vault), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active_session"] is None

    def test_show_with_active_session_text(self) -> None:
        vault, db = _make_vault()
        from cerebra.cognition.working_memory import new_session

        sid = new_session(db, str(vault))

        result = CliRunner().invoke(cli, ["session", "show", "--vault", str(vault)])
        assert result.exit_code == 0
        assert sid in result.output
        assert "active" in result.output
        assert "Tower" in result.output
        assert "Working memory" in result.output

    def test_show_with_active_session_json(self) -> None:
        vault, db = _make_vault()
        from cerebra.cognition.working_memory import new_session

        sid = new_session(db, str(vault))

        result = CliRunner().invoke(
            cli, ["session", "show", "--vault", str(vault), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_id"] == sid
        assert data["status"] == "active"
        assert data["wm_item_count"] == 0
        assert data["t1_item_count"] == 0
        assert data["t2_item_count"] == 0

    def test_show_json_contains_required_fields(self) -> None:
        vault, db = _make_vault()
        from cerebra.cognition.working_memory import new_session

        new_session(db, str(vault))

        result = CliRunner().invoke(
            cli, ["session", "show", "--vault", str(vault), "--format", "json"]
        )
        data = json.loads(result.output)
        for field in (
            "session_id",
            "vault_path",
            "status",
            "started_at",
            "last_active_at",
            "wm_item_count",
            "wm_by_slot",
            "t1_item_count",
            "t2_item_count",
        ):
            assert field in data, f"Missing field: {field}"


@pytest.mark.unit
class TestSessionReset:
    def test_reset_creates_new_session(self) -> None:
        vault, db = _make_vault()
        result = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])
        assert result.exit_code == 0
        assert "New session:" in result.output

    def test_reset_with_no_prior_session(self) -> None:
        vault, _ = _make_vault()
        result = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])
        assert result.exit_code == 0
        assert "No previous session" in result.output

    def test_reset_closes_existing_session(self) -> None:
        vault, db = _make_vault()
        from cerebra.cognition.working_memory import new_session

        old_id = new_session(db, str(vault))

        result = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])
        assert result.exit_code == 0
        assert old_id in result.output
        assert "closed" in result.output.lower()

        # Confirm old session is closed in DB
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT status FROM sessions WHERE session_id=?", (old_id,)).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "closed"

    def test_reset_creates_different_id_each_time(self) -> None:
        vault, _ = _make_vault()
        r1 = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])
        r2 = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])
        assert r1.exit_code == 0
        assert r2.exit_code == 0

        # Extract new session IDs — look for the word after "New session:"
        def _new_id(output: str) -> str:
            for line in output.splitlines():
                if "New session:" in line:
                    return line.split("New session:")[-1].strip()
            raise AssertionError(f"No 'New session:' in output: {output!r}")

        id1 = _new_id(r1.output)
        id2 = _new_id(r2.output)
        assert id1 != id2

    def test_reset_emits_working_memory_created_event(self) -> None:
        vault, db = _make_vault()
        CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])

        conn = sqlite3.connect(db)
        count = conn.execute(
            "SELECT COUNT(*) FROM inspector_events WHERE event_type='WorkingMemoryCreated'"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_show_after_reset_reflects_new_session(self) -> None:
        vault, db = _make_vault()
        from cerebra.cognition.working_memory import get_active_session

        r_reset = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault)])
        assert r_reset.exit_code == 0

        active = get_active_session(db, str(vault))
        assert active is not None

        r_show = CliRunner().invoke(
            cli, ["session", "show", "--vault", str(vault), "--format", "json"]
        )
        data = json.loads(r_show.output)
        assert data["session_id"] == active
