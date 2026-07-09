# SPDX-License-Identifier: Apache-2.0
"""
Inspector NDJSON append-only event log.

Per CEREBRA_INSPECTOR.md §6.2: one event per line, append-only.
The NDJSON file is the authoritative log; SQLite is the queryable index.
If SQLite is lost, it can be rebuilt from NDJSON.
"""

from __future__ import annotations

from pathlib import Path

from cerebra.inspector.event import InspectorEvent


class NDJSONEventLog:
    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: InspectorEvent) -> None:
        """Append one event as a single JSON line. Write is line-atomic."""
        line = event.to_json() + "\n"
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def read_all(self) -> list[str]:
        """Read all lines. Each line is a valid JSON string."""
        if not self._log_path.exists():
            return []
        return self._log_path.read_text(encoding="utf-8").splitlines()
