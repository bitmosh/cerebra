"""
Vault write-path lockfile using fcntl.flock.

Linux/POSIX only. Windows support is deferred per Phase 5 §18 R2.
Only write-path CLI commands acquire this lock; read-only commands skip it.
"""

from __future__ import annotations

import fcntl
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import click


def lock_path(vault_path: Path) -> Path:
    return vault_path / ".cerebra.lock"


def _read_pid(lp: Path) -> int | None:
    try:
        content = lp.read_text().strip()
        return int(content) if content else None
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    """Return True if process pid is running (signal 0 = existence check)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we can't signal it


def _contention_exit_with_pid(pid: int | None) -> None:
    pid_msg = f" (PID {pid})" if pid else ""
    click.echo(
        f"Vault is locked by another process{pid_msg}. Try again.",
        err=True,
    )
    sys.exit(2)


@contextmanager
def vault_lock(vault_path: Path) -> Generator[None, None, None]:
    """Acquire an exclusive non-blocking flock on the vault lockfile.

    On contention with a live process: prints error to stderr and exits 2.
    On stale lock (dead PID): removes lockfile and retries once.
    Always releases the lock (and deletes the lockfile) in a finally block.
    """
    lp = lock_path(vault_path)
    # Read any existing PID before we open for writing (open "w" clears the file).
    existing_pid = _read_pid(lp) if lp.exists() else None
    try:
        with open(lp, "w") as fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pid = existing_pid
                if pid is None or _pid_alive(pid):
                    _contention_exit_with_pid(pid)
                # Stale lock — owner process is dead. Reclaim it (after closing fd below).
            else:
                # We hold the lock — write our PID so stale detection works
                fd.write(str(os.getpid()))
                fd.flush()
                yield
                return
        # Stale-lock retry path: previous fd is closed; remove lockfile and retry once.
        lp.unlink(missing_ok=True)
        with open(lp, "w") as fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                _contention_exit_with_pid(None)
            fd.write(str(os.getpid()))
            fd.flush()
            yield
    finally:
        lp.unlink(missing_ok=True)
