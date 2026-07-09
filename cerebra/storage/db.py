# SPDX-License-Identifier: Apache-2.0
"""
Central SQLite connection factory.

All Cerebra code that opens a database connection must use connect() from
this module. This ensures WAL mode, foreign keys, and row_factory are set
consistently on every connection.

WAL (Write-Ahead Logging) is set here rather than in a migration because
journal_mode is a per-connection pragma — it must be applied each time a
connection is opened, not once in schema history.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """
    Open a SQLite connection with Cerebra's standard settings.

    Always use this instead of sqlite3.connect() directly.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; faster than FULL
    return conn
