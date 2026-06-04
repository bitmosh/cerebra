"""
Ingest pipeline — orchestrates source discovery → registration →
detection → parsing → normalization → chunking → record building →
batch storage → inspector event emission.

All inspector events for a file are emitted here, not in sub-components,
so the event log accurately reflects the full per-file lifecycle.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from cerebra.ingest.adapters.markdown import PARSER_VERSION as MD_PARSER_VERSION
from cerebra.ingest.adapters.markdown import MarkdownAdapter
from cerebra.ingest.adapters.text import PARSER_VERSION as TXT_PARSER_VERSION
from cerebra.ingest.adapters.text import TextAdapter
from cerebra.ingest.chunking import CHUNKER_VERSION, ChunkOptions, chunk_document
from cerebra.ingest.normalization import write_artifact
from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.memory.records import build_records_for_document
from cerebra.sources.detector import detect_type
from cerebra.sources.discovery import DEFAULT_EXCLUDE_PATTERNS, discover_files
from cerebra.sources.registry import RegistrationOutcome, register_source
from cerebra.storage.migrations import run_migrations
from cerebra.storage.sqlite_store import SQLiteStore

_MARKDOWN_ADAPTER = MarkdownAdapter()
_TEXT_ADAPTER = TextAdapter()

_PARSER_VERSION_MAP = {
    "markdown": MD_PARSER_VERSION,
    "text": TXT_PARSER_VERSION,
}


@dataclass
class IngestReport:
    sources_found: int = 0
    sources_new: int = 0
    sources_changed: int = 0
    sources_skipped: int = 0
    sources_failed: int = 0
    chunks_created: int = 0
    records_created: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "sources_found": self.sources_found,
            "sources_new": self.sources_new,
            "sources_changed": self.sources_changed,
            "sources_skipped": self.sources_skipped,
            "sources_failed": self.sources_failed,
            "chunks_created": self.chunks_created,
            "records_created": self.records_created,
            "errors": self.errors,
        }


def ingest_path(
    vault_path: Path,
    target: Path,
    *,
    dry_run: bool = False,
    exclude_patterns: list[str] | None = None,
    extensions: frozenset[str] | None = None,
    chunk_options: ChunkOptions | None = None,
) -> IngestReport:
    """
    Ingest all supported files under target into the vault.

    Args:
        vault_path: initialized Cerebra vault root
        target: file or directory to ingest
        dry_run: if True, discover and detect but do not write anything
        exclude_patterns: override default exclude patterns
        extensions: override default file extensions
        chunk_options: chunking parameters

    Returns:
        IngestReport with counts for this run.
    """
    db_path = vault_path / "data" / "cerebra.db"
    artifacts_dir = vault_path / "artifacts"
    events_log = vault_path / "events" / "ingest.ndjson"

    run_migrations(db_path)
    store = SQLiteStore(db_path)
    event_log = SQLiteEventLog(db_path)

    from cerebra.inspector.ndjson_log import NDJSONEventLog

    ndjson = NDJSONEventLog(events_log)

    def emit(
        evt_type: str,
        actor: str,
        summary: str,
        data: dict[str, object],
        subject_id: str | None = None,
    ) -> None:
        e = make_event(evt_type, actor, summary, data, subject_id=subject_id)
        event_log.write(e)
        ndjson.write(e)

    report = IngestReport()

    # Discover files
    if target.is_file():
        files = [target.resolve()]
    else:
        files = discover_files(
            root=target,
            extensions=extensions,
            exclude_patterns=(
                exclude_patterns if exclude_patterns is not None else DEFAULT_EXCLUDE_PATTERNS
            ),
        )

    report.sources_found = len(files)

    if dry_run:
        for f in files:
            detection = detect_type(f)
            emit(
                "SourceRegistered",
                "ingest_pipeline",
                f"[dry-run] would ingest {f.name}",
                {"path": str(f), "detected_type": detection.detected_type, "dry_run": True},
            )
        return report

    opts = chunk_options or ChunkOptions()

    for file_path in files:
        try:
            _ingest_file(
                file_path=file_path,
                store=store,
                event_log=event_log,
                ndjson=ndjson,
                artifacts_dir=artifacts_dir,
                opts=opts,
                report=report,
                emit=emit,
            )
        except Exception as e:
            report.sources_failed += 1
            report.errors.append(f"{file_path}: {e}")
            emit(
                "SourceParseFailed",
                "ingest_pipeline",
                f"Failed to ingest {file_path.name}: {e}",
                {"path": str(file_path), "error": str(e)},
            )

    return report


def _ingest_file(
    file_path: Path,
    store: SQLiteStore,
    event_log: SQLiteEventLog,
    ndjson: object,
    artifacts_dir: Path,
    opts: ChunkOptions,
    report: IngestReport,
    emit: object,
) -> None:
    from cerebra.inspector.ndjson_log import NDJSONEventLog

    assert isinstance(ndjson, NDJSONEventLog)
    assert callable(emit)

    detection = detect_type(file_path)
    parser_version = _PARSER_VERSION_MAP.get(detection.detected_type)

    source, outcome = register_source(
        store=store,
        event_log=event_log,
        path=file_path,
        detection=detection,
        parser_version=parser_version,
        chunker_version=CHUNKER_VERSION,
    )

    if outcome == RegistrationOutcome.SKIPPED_UNCHANGED:
        report.sources_skipped += 1
        return

    if outcome == RegistrationOutcome.NEW:
        report.sources_new += 1
    else:
        report.sources_changed += 1

    # Select adapter
    adapter = _MARKDOWN_ADAPTER if detection.detected_type == "markdown" else _TEXT_ADAPTER

    parse_result = adapter.parse(source.source_id, file_path)

    if not parse_result.success or parse_result.document is None:
        report.sources_failed += 1
        report.errors.append(f"{file_path}: parse failed: {parse_result.errors}")
        emit(
            "SourceParseFailed",
            "ingest_pipeline",
            f"Parse failed: {file_path.name}",
            {"source_id": source.source_id, "errors": parse_result.errors},
            subject_id=source.source_id,
        )
        return

    doc = parse_result.document
    now = int(time.time())

    # Emit parse warnings as DocumentParseWarning events AND store on document row
    for warning in parse_result.warnings:
        emit(
            "DocumentParseWarning",
            "ingest_pipeline",
            f"Parse warning in {file_path.name}: {warning}",
            {"source_id": source.source_id, "warning": warning},
            subject_id=source.source_id,
        )

    # Write artifact (write-then-rename)
    artifact_path = write_artifact(doc, artifacts_dir)

    emit(
        "DocumentNormalized",
        "ingest_pipeline",
        f"Document normalized: {file_path.name}",
        {
            "source_id": source.source_id,
            "document_id": doc.document_id,
            "sections": len(doc.sections),
            "artifact_path": str(artifact_path),
        },
        subject_id=doc.document_id,
    )

    # Persist document row
    store.insert_document(
        {
            "document_id": doc.document_id,
            "source_id": source.source_id,
            "document_type": doc.document_type,
            "title": doc.title,
            "artifact_path": str(artifact_path),
            "normalization_confidence": doc.normalization_confidence,
            "parse_warnings": (
                json.dumps(parse_result.warnings) if parse_result.warnings else None
            ),
            "lifecycle_state": "active",
            "created_at": now,
            "schema_version": 1,
        }
    )

    # Chunk and batch-insert
    chunks = chunk_document(doc, opts)
    chunk_dicts = []
    for c in chunks:
        d = c.as_dict()
        d["created_at"] = now
        chunk_dicts.append(d)

    store.insert_chunks_batch(chunk_dicts)

    for c in chunks:
        emit(
            "ChunkCreated",
            "ingest_pipeline",
            f"Chunk {c.chunk_index} ({c.chunk_strategy.value}): {c.heading_path or '/'}",
            {
                "chunk_id": c.chunk_id,
                "document_id": doc.document_id,
                "source_id": source.source_id,
                "heading_path": c.heading_path,
                "token_estimate": c.token_estimate,
                "strategy": c.chunk_strategy.value,
            },
            subject_id=c.chunk_id,
        )

    # Build and batch-insert memory records
    records = build_records_for_document(chunks, source)
    record_dicts = [r.as_dict() for r in records]
    store.insert_records_batch(record_dicts)

    for r in records:
        emit(
            "MemoryRecordCreated",
            "ingest_pipeline",
            f"MemoryRecord created for chunk {r.chunk_id}",
            {
                "record_id": r.record_id,
                "source_id": r.source_id,
                "chunk_id": r.chunk_id,
                "sku_address": None,
            },
            subject_id=r.record_id,
        )

    # Update source as ingested
    source_update = source.as_dict()
    source_update["parser_status"] = "parsed"
    source_update["ingested_at"] = now
    source_update["parser_adapter"] = adapter.name
    store.upsert_source(source_update)

    emit(
        "SourceParsed",
        "ingest_pipeline",
        f"Source parsed: {file_path.name} → {len(chunks)} chunks",
        {
            "source_id": source.source_id,
            "document_id": doc.document_id,
            "chunks": len(chunks),
            "records": len(records),
        },
        subject_id=source.source_id,
    )

    report.chunks_created += len(chunks)
    report.records_created += len(records)
