"""Unit tests for the vault lockfile mechanism."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cerebra.cli.lockfile import _pid_alive, _read_pid, lock_path, vault_lock


@pytest.mark.unit
class TestLockfilePath:
    def test_lock_path_is_in_vault_root(self) -> None:
        lp = lock_path(Path("/vault/root"))
        assert lp == Path("/vault/root/.cerebra.lock")

    def test_lock_path_name(self) -> None:
        assert lock_path(Path("/any/path")).name == ".cerebra.lock"


@pytest.mark.unit
class TestPidHelpers:
    def test_own_pid_is_alive(self) -> None:
        assert _pid_alive(os.getpid()) is True

    def test_dead_pid_is_not_alive(self) -> None:
        # PID 1 is init/systemd on Linux (alive), but we need a dead PID.
        # Use os.fork() to create a child that exits immediately.
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        os.waitpid(pid, 0)  # reap child so it doesn't become zombie
        assert _pid_alive(pid) is False

    def test_read_pid_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lock", delete=False) as f:
            f.write(str(os.getpid()))
            name = f.name
        try:
            assert _read_pid(Path(name)) == os.getpid()
        finally:
            Path(name).unlink(missing_ok=True)

    def test_read_pid_returns_none_on_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lock", delete=False) as f:
            name = f.name
        try:
            assert _read_pid(Path(name)) is None
        finally:
            Path(name).unlink(missing_ok=True)

    def test_read_pid_returns_none_on_missing_file(self) -> None:
        assert _read_pid(Path("/no/such/file.lock")) is None


@pytest.mark.unit
class TestVaultLock:
    def _temp_vault(self) -> Path:
        d = tempfile.mkdtemp()
        return Path(d)

    def test_lock_acquired_and_released(self) -> None:
        vault = self._temp_vault()
        try:
            lp = lock_path(vault)
            assert not lp.exists()
            with vault_lock(vault):
                assert lp.exists()
            assert not lp.exists()
        finally:
            import shutil
            shutil.rmtree(vault, ignore_errors=True)

    def test_lock_writes_pid(self) -> None:
        vault = self._temp_vault()
        try:
            with vault_lock(vault):
                pid = _read_pid(lock_path(vault))
                assert pid == os.getpid()
        finally:
            import shutil
            shutil.rmtree(vault, ignore_errors=True)

    def test_lock_deleted_after_exception(self) -> None:
        vault = self._temp_vault()
        try:
            lp = lock_path(vault)
            with pytest.raises(RuntimeError):
                with vault_lock(vault):
                    raise RuntimeError("test error")
            assert not lp.exists()
        finally:
            import shutil
            shutil.rmtree(vault, ignore_errors=True)

    def test_contention_exits_2(self) -> None:
        """When flock raises BlockingIOError with a live PID, exit 2."""
        vault = self._temp_vault()
        try:
            lp = lock_path(vault)
            lp.write_text(str(os.getpid()))  # alive PID — written BEFORE vault_lock opens file

            with patch("cerebra.cli.lockfile.fcntl.flock", side_effect=BlockingIOError):
                with pytest.raises(SystemExit) as exc_info:
                    with vault_lock(vault):
                        pass
            assert exc_info.value.code == 2
        finally:
            import shutil
            shutil.rmtree(vault, ignore_errors=True)

    def test_stale_lock_reclaimed(self) -> None:
        """A lockfile with a dead PID is removed and the lock is acquired."""
        vault = self._temp_vault()
        try:
            # Create a child that exits immediately
            pid = os.fork()
            if pid == 0:
                os._exit(0)
            os.waitpid(pid, 0)

            # Plant lockfile with dead PID
            lp = lock_path(vault)
            lp.write_text(str(pid))

            # vault_lock should reclaim it (dead PID → remove → retry)
            # The mock ensures the *first* flock call raises BlockingIOError
            # (simulating the dead-PID scenario), then succeeds on retry.
            original_flock = __import__("fcntl").flock
            call_count = {"n": 0}

            def fake_flock(fd, flags):  # type: ignore[no-untyped-def]
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise BlockingIOError
                return original_flock(fd, flags)

            with patch("cerebra.cli.lockfile.fcntl.flock", side_effect=fake_flock):
                with vault_lock(vault):
                    assert _read_pid(lock_path(vault)) == os.getpid()

            assert not lock_path(vault).exists()
        finally:
            import shutil
            shutil.rmtree(vault, ignore_errors=True)
