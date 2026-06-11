"""Integration test for vault lockfile contention.

Tests that cerebra write-path commands respect the vault lockfile when
another process holds it. Does NOT require numpy — session commands don't
trigger the embedding pipeline.

Run with: pytest tests/integration/test_vault_lockfile.py -m integration -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


@pytest.mark.integration
class TestVaultLockfile:
    def test_vault_lockfile_respected(self, vault_root: Path) -> None:
        """cerebra session reset exits 2 when another process holds the vault lock.

        The test process holds an exclusive flock on .cerebra.lock; the
        subprocess (different OS process) cannot acquire it and must exit 2.
        flock is not reentrant across processes, so this reliably simulates
        concurrent write-path contention.
        """
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
                ["cerebra", "session", "reset", "--vault", str(vault_root)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 2, (
                f"Expected exit 2, got {result.returncode}. stderr: {result.stderr!r}"
            )
            assert "locked" in result.stderr.lower(), (
                f"Expected 'locked' in stderr: {result.stderr!r}"
            )
        finally:
            fd.close()
            lp.unlink(missing_ok=True)
