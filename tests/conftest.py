"""Shared pytest fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cerebra.storage.migrations import run_migrations


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """Return a migrated in-memory SQLite connection."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    """Return an initialized vault in a temp directory."""
    from cerebra.vault.init import init_vault

    vault = init_vault(tmp_path / "test-vault")
    return vault
