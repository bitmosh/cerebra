# SPDX-License-Identifier: Apache-2.0
"""Export data models for the graph exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExportStats:
    node_count: int
    edge_count: int
    spine_count: int
    record_count: int
    classified_count: int
    unclassified_count: int
    edges_by_type: dict[str, int] = field(default_factory=dict)
    out_path: Path = field(default_factory=lambda: Path("."))
    elapsed_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "spine_count": self.spine_count,
            "record_count": self.record_count,
            "classified_count": self.classified_count,
            "unclassified_count": self.unclassified_count,
            "edges_by_type": self.edges_by_type,
            "out_path": str(self.out_path),
            "elapsed_ms": self.elapsed_ms,
        }
