"""Integration tests for cerebra memory CLI against the dev vault.

Uses ~/cerebra-vaults/dev. Skips if the vault is absent.

Run with: pytest tests/integration/test_memory_cli_against_vault.py -m integration -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli
from cerebra.cognition.working_memory import WorkingMemory, new_session
from cerebra.storage.db import connect

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


@pytest.fixture()
def fresh_session(vault_root: Path) -> tuple[Path, str]:
    """Create a fresh session and return (db_path, session_id)."""
    db = vault_root / "data" / "cerebra.db"
    sid = new_session(db, str(vault_root))
    return db, sid


def _invoke(args: list[str]):  # type: ignore[return]
    return CliRunner().invoke(cli, args)


def _vault_args(vault_root: Path) -> list[str]:
    return ["--vault", str(vault_root)]


# ── full flow ─────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestMemoryCliVaultIntegration:
    def test_full_flow_promote_status_evict(self, vault_root: Path, fresh_session: tuple) -> None:
        """Empty session → promote 3 items → status shows them → evict 1 → status shows 2."""
        db, sid = fresh_session

        # Promote 3 items
        wm = WorkingMemory(db, sid)
        i1 = wm.promote("context", None, "item one", salience_score=0.5)
        i2 = wm.promote("context", None, "item two", salience_score=0.4)
        i3 = wm.promote("evidence", None, "item three", salience_score=0.6)

        # Status should show all 3
        r_status = _invoke(["memory", "status"] + _vault_args(vault_root))
        assert r_status.exit_code == 0
        assert "item one" in r_status.output
        assert "item two" in r_status.output
        assert "item three" in r_status.output

        # Evict one
        r_evict = _invoke(["memory", "evict", i2.item_id] + _vault_args(vault_root))
        assert r_evict.exit_code == 0
        assert i2.item_id in r_evict.output

        # Status shows 2 remaining
        r_after = _invoke(["memory", "status"] + _vault_args(vault_root))
        assert "item one" in r_after.output
        assert "item two" not in r_after.output
        assert "item three" in r_after.output

    def test_json_status_is_valid_json(self, vault_root: Path, fresh_session: tuple) -> None:
        _db, _sid = fresh_session
        r = _invoke(["memory", "status", "--format", "json"] + _vault_args(vault_root))
        assert r.exit_code == 0
        d = json.loads(r.output)
        assert "session_id" in d
        assert "slots" in d
        assert "vault_path" in d

    def test_promote_cli_persists_item(self, vault_root: Path, fresh_session: tuple) -> None:
        db, sid = fresh_session
        r = _invoke(
            [
                "memory",
                "promote",
                "--text",
                "cli promotion test",
                "--slot",
                "hypothesis",
            ]
            + _vault_args(vault_root)
        )
        assert r.exit_code == 0

        wm = WorkingMemory(db, sid)
        items = wm.load_slot("hypothesis")
        assert any("cli promotion test" in i.content_summary for i in items)

    def test_promote_pinned_shows_in_status(self, vault_root: Path, fresh_session: tuple) -> None:
        _db, _sid = fresh_session
        _invoke(
            [
                "memory",
                "promote",
                "--text",
                "pinned integration item",
                "--slot",
                "goal",
                "--pin",
            ]
            + _vault_args(vault_root)
        )
        r_status = _invoke(["memory", "status"] + _vault_args(vault_root))
        assert "[pinned]" in r_status.output

    def test_json_status_slot_structure(self, vault_root: Path, fresh_session: tuple) -> None:
        """JSON status has all 10 slot keys, each mapping to a list."""
        from cerebra.cognition._constants import SLOT_CAPACITIES

        _db, _sid = fresh_session
        r = _invoke(["memory", "status", "--format", "json"] + _vault_args(vault_root))
        d = json.loads(r.output)
        assert set(d["slots"].keys()) == set(SLOT_CAPACITIES.keys())
        for slot, items in d["slots"].items():
            assert isinstance(items, list), f"{slot!r} should be a list"

    def test_lockfile_contention_promote_exits_2(self, vault_root: Path) -> None:
        """Hold the vault lock in-process; subprocess promote must exit 2."""
        import fcntl
        import os
        import subprocess

        from cerebra.cli.lockfile import lock_path

        lp = lock_path(vault_root)
        fd = open(lp, "w")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(str(os.getpid()))
            fd.flush()

            result = subprocess.run(
                [
                    "cerebra",
                    "memory",
                    "promote",
                    "--vault",
                    str(vault_root),
                    "--text",
                    "should not arrive",
                    "--slot",
                    "goal",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert (
                result.returncode == 2
            ), f"Expected exit 2, got {result.returncode}. stderr: {result.stderr!r}"
            assert (
                "locked" in result.stderr.lower()
            ), f"Expected 'locked' in stderr: {result.stderr!r}"
        finally:
            fd.close()
            lp.unlink(missing_ok=True)

    def test_working_memory_rendered_event_emitted(
        self, vault_root: Path, fresh_session: tuple
    ) -> None:
        db, sid = fresh_session
        conn = connect(db)
        try:
            before = conn.execute(
                "SELECT COUNT(*) FROM inspector_events "
                "WHERE event_type = 'WorkingMemoryRendered' AND session_id = ?",
                (sid,),
            ).fetchone()[0]
        finally:
            conn.close()

        _invoke(["memory", "status"] + _vault_args(vault_root))

        conn = connect(db)
        try:
            after = conn.execute(
                "SELECT COUNT(*) FROM inspector_events "
                "WHERE event_type = 'WorkingMemoryRendered' AND session_id = ?",
                (sid,),
            ).fetchone()[0]
        finally:
            conn.close()

        assert after > before, "WorkingMemoryRendered event not emitted"

    def test_evict_missing_exits_2(self, vault_root: Path, fresh_session: tuple) -> None:
        _db, _sid = fresh_session
        r = _invoke(["memory", "evict", "wmi_doesnotexist"] + _vault_args(vault_root))
        assert r.exit_code == 2
