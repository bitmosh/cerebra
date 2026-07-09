# SPDX-License-Identifier: Apache-2.0
"""
Artifact store — normalized document content on disk.

Writes document text to <vault>/artifacts/<document_id>.txt.
No database involvement for the content itself; the file IS the artifact.

Idempotency: if the artifact already exists with identical content (same
SHA256), the write is skipped and ArtifactResult.written is False. If the
hash differs (content changed), the file is overwritten and written is True.

Inspector event: DocumentArtifactWritten — emitted only when content is
actually written (not on idempotent skips). Pass event_log=None to suppress
emission (used in tests and callers that handle event routing themselves).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog


@dataclass(frozen=True)
class ArtifactResult:
    """Returned by write_artifact."""

    artifact_path: Path  # absolute path to the artifact file
    size_bytes: int
    content_hash: str  # sha256 hex of the content
    written: bool  # True = written or overwritten; False = identical, skipped


def write_artifact(
    vault_path: Path,
    document_id: str,
    content: str,
    *,
    event_log: SQLiteEventLog | None = None,
) -> ArtifactResult:
    """Write normalized document content to <vault>/artifacts/<document_id>.txt.

    vault_path: root vault directory (the directory that contains data/, artifacts/, etc.)
    document_id: the document's primary key from the documents table
    content: normalized text content to store
    event_log: if provided, a DocumentArtifactWritten event is emitted on write

    Returns ArtifactResult. The artifact_path in the result is absolute.
    """
    artifacts_dir = vault_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifacts_dir / f"{document_id}.txt"
    encoded = content.encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    size_bytes = len(encoded)

    # Idempotency check: skip if file exists with identical content.
    if artifact_path.exists():
        existing_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if existing_hash == content_hash:
            return ArtifactResult(
                artifact_path=artifact_path,
                size_bytes=size_bytes,
                content_hash=content_hash,
                written=False,
            )

    artifact_path.write_bytes(encoded)

    if event_log is not None:
        event = make_event(
            event_type="DocumentArtifactWritten",
            actor="artifact_store",
            summary=f"Artifact written for document {document_id}",
            data={
                "document_id": document_id,
                "artifact_path": str(artifact_path.relative_to(vault_path)),
                "size_bytes": size_bytes,
            },
            subject_id=document_id,
        )
        event_log.write(event)

    return ArtifactResult(
        artifact_path=artifact_path,
        size_bytes=size_bytes,
        content_hash=content_hash,
        written=True,
    )


def artifact_path_for(vault_path: Path, document_id: str) -> Path:
    """Return the expected artifact path without reading or writing anything."""
    return vault_path / "artifacts" / f"{document_id}.txt"


def artifact_exists(vault_path: Path, document_id: str) -> bool:
    """Return True if the artifact file exists on disk."""
    return artifact_path_for(vault_path, document_id).exists()
