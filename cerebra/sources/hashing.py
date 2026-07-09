# SPDX-License-Identifier: Apache-2.0
"""Content hashing utilities."""

from __future__ import annotations

import hashlib
from pathlib import Path


def hash_file(path: Path) -> str:
    """SHA256 of file bytes, returned as hex string."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    """SHA256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_string(s: str) -> str:
    """SHA256 of a UTF-8 encoded string."""
    return hash_bytes(s.encode("utf-8"))
