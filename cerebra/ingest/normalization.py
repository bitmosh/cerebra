"""
Normalization layer — writes NormalizedDocument artifacts to vault storage.

Uses write-then-rename for atomicity on POSIX systems: write to a .tmp
file in the same directory, then os.replace() to the final path.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from cerebra.ingest.models import NormalizedDocument


def write_artifact(doc: NormalizedDocument, artifacts_dir: Path) -> Path:
    """
    Serialize document to JSON artifact file using write-then-rename.

    Returns the final artifact path.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / f"{doc.document_id}.json"
    tmp_path = artifact_path.with_suffix(".tmp")

    payload = {
        "document_id": doc.document_id,
        "source_id": doc.source_id,
        "document_type": doc.document_type,
        "title": doc.title,
        "sections": [
            {
                "heading": s.heading,
                "heading_path": s.heading_path,
                "depth": s.depth,
                "content": s.content,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            for s in doc.sections
        ],
        "metadata": doc.metadata,
        "normalization_confidence": doc.normalization_confidence,
        "schema_version": doc.schema_version,
        "written_at": int(time.time()),
    }

    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, artifact_path)  # atomic on POSIX
    return artifact_path
