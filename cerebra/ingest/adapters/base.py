# SPDX-License-Identifier: Apache-2.0
"""Base parser adapter ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from cerebra.ingest.models import ParseResult


class ParserAdapter(ABC):
    """Every parser adapter implements this contract.

    Adapters parse; the ingest pipeline writes. Adapters must not
    open database connections or write to storage.
    """

    name: str
    version: str

    @abstractmethod
    def parse(self, source_id: str, path: Path) -> ParseResult:
        """Parse source at path and return a ParseResult."""
