"""
Ingest pipeline — orchestrates source discovery → registration →
detection → parsing → normalization → chunking → record building →
batch storage → graph wiring → index updates → inspector event emission.

All inspector events for a file are emitted here, not in sub-components,
so the event log accurately reflects the full per-file lifecycle.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
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
from cerebra.storage.artifact_store import write_artifact as write_text_artifact
from cerebra.storage.embeddings import queue_for_embedding
from cerebra.storage.graph_store import make_edge_id, make_node_id, upsert_edge, upsert_node
from cerebra.storage.lexical import update_fts_index
from cerebra.storage.migrations import run_migrations
from cerebra.storage.sqlite_store import SQLiteStore

_MARKDOWN_ADAPTER = MarkdownAdapter()
_TEXT_ADAPTER = TextAdapter()

_PARSER_VERSION_MAP = {
    "markdown": MD_PARSER_VERSION,
    "text": TXT_PARSER_VERSION,
}

# Type alias for the emit helper passed to _ingest_file.
_EmitFn = Callable[..., str]


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
    ) -> str:
        e = make_event(evt_type, actor, summary, data, subject_id=subject_id)
        event_log.write(e)
        ndjson.write(e)
        return e.event_id

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
                vault_path=vault_path,
                db_path=db_path,
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
    vault_path: Path,
    db_path: Path,
    opts: ChunkOptions,
    report: IngestReport,
    emit: _EmitFn,
) -> None:
    from cerebra.inspector.ndjson_log import NDJSONEventLog

    assert isinstance(ndjson, NDJSONEventLog)

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

    now = int(time.time())

    # ── Source graph node ────────────────────────────────────────────────────
    source_node_id = upsert_node(
        db_path,
        {
            "node_id": make_node_id(f"sources:{source.source_id}"),
            "node_type": "Source",
            "label": source.canonical_path,
            "entity_id": source.source_id,
            "entity_table": "sources",
            "lifecycle_state": "active",
            "origin_event_id": None,
            "payload_json": json.dumps(
                {
                    "canonical_path": source.canonical_path,
                    "detected_type": detection.detected_type,
                    "size_bytes": source.size_bytes,
                }
            ),
            "created_at": now,
            "updated_at": now,
        },
    )
    emit(
        "GraphNodeCreated",
        "graph_store",
        f"Source node: {source.source_id}",
        {
            "node_id": source_node_id,
            "node_type": "Source",
            "entity_id": source.source_id,
            "entity_table": "sources",
        },
        subject_id=source_node_id,
    )

    # ── Select adapter ───────────────────────────────────────────────────────
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

    # Emit parse warnings
    for warning in parse_result.warnings:
        emit(
            "DocumentParseWarning",
            "ingest_pipeline",
            f"Parse warning in {file_path.name}: {warning}",
            {"source_id": source.source_id, "warning": warning},
            subject_id=source.source_id,
        )

    # ── Artifacts ────────────────────────────────────────────────────────────
    # JSON structured artifact (write-then-rename, for downstream processing)
    artifact_path = write_artifact(doc, artifacts_dir)

    # Plain-text artifact (for retrieval layer)
    write_text_artifact(vault_path, doc.document_id, doc.raw_content, event_log=event_log)

    doc_evt_id = emit(
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

    # ── Persist document row ─────────────────────────────────────────────────
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

    # ── Document graph node + Source→Document edge ───────────────────────────
    doc_node_id = upsert_node(
        db_path,
        {
            "node_id": make_node_id(f"documents:{doc.document_id}"),
            "node_type": "Document",
            "label": doc.title or doc.document_id,
            "entity_id": doc.document_id,
            "entity_table": "documents",
            "lifecycle_state": "active",
            "origin_event_id": doc_evt_id,
            "payload_json": json.dumps(
                {
                    "document_type": doc.document_type,
                    "title": doc.title,
                    "artifact_path": str(artifact_path),
                }
            ),
            "created_at": now,
            "updated_at": now,
        },
    )
    emit(
        "GraphNodeCreated",
        "graph_store",
        f"Document node: {doc.document_id}",
        {
            "node_id": doc_node_id,
            "node_type": "Document",
            "entity_id": doc.document_id,
            "entity_table": "documents",
        },
        subject_id=doc_node_id,
    )
    src_contains_doc = upsert_edge(
        db_path,
        {
            "edge_id": make_edge_id(),
            "edge_type": "CONTAINS",
            "source_node_id": source_node_id,
            "target_node_id": doc_node_id,
            "confidence": 1.0,
            "weight": 1.0,
            "evidence": "ingest: source contains document",
            "created_by": "ingest_pipeline",
            "origin_event_id": doc_evt_id,
            "lifecycle_state": "active",
            "payload_json": "{}",
            "created_at": now,
            "updated_at": now,
        },
    )
    emit(
        "GraphEdgeCreated",
        "graph_store",
        "Edge: Source CONTAINS Document",
        {
            "edge_id": src_contains_doc,
            "edge_type": "CONTAINS",
            "source_node_id": source_node_id,
            "target_node_id": doc_node_id,
            "confidence": 1.0,
            "weight": 1.0,
        },
        subject_id=src_contains_doc,
    )

    # ── Chunk and batch-insert ───────────────────────────────────────────────
    chunks = chunk_document(doc, opts)
    chunk_dicts = []
    for c in chunks:
        d = c.as_dict()
        d["created_at"] = now
        chunk_dicts.append(d)

    store.insert_chunks_batch(chunk_dicts)

    chunk_node_ids: dict[str, str] = {}
    for c in chunks:
        chunk_evt_id = emit(
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
        chunk_node_id = upsert_node(
            db_path,
            {
                "node_id": make_node_id(f"chunks:{c.chunk_id}"),
                "node_type": "Chunk",
                "label": f"{c.heading_path or '/'} (chunk {c.chunk_index})",
                "entity_id": c.chunk_id,
                "entity_table": "chunks",
                "lifecycle_state": "active",
                "origin_event_id": chunk_evt_id,
                "payload_json": json.dumps(
                    {
                        "chunk_index": c.chunk_index,
                        "heading_path": c.heading_path,
                        "depth": c.depth,
                        "token_estimate": c.token_estimate,
                    }
                ),
                "created_at": now,
                "updated_at": now,
            },
        )
        chunk_node_ids[c.chunk_id] = chunk_node_id
        emit(
            "GraphNodeCreated",
            "graph_store",
            f"Chunk node: {c.chunk_id}",
            {
                "node_id": chunk_node_id,
                "node_type": "Chunk",
                "entity_id": c.chunk_id,
                "entity_table": "chunks",
            },
            subject_id=chunk_node_id,
        )
        doc_contains_chunk = upsert_edge(
            db_path,
            {
                "edge_id": make_edge_id(),
                "edge_type": "CONTAINS",
                "source_node_id": doc_node_id,
                "target_node_id": chunk_node_id,
                "confidence": 1.0,
                "weight": 1.0,
                "evidence": f"ingest: document contains chunk {c.chunk_index}",
                "created_by": "ingest_pipeline",
                "origin_event_id": chunk_evt_id,
                "lifecycle_state": "active",
                "payload_json": "{}",
                "created_at": now,
                "updated_at": now,
            },
        )
        emit(
            "GraphEdgeCreated",
            "graph_store",
            "Edge: Document CONTAINS Chunk",
            {
                "edge_id": doc_contains_chunk,
                "edge_type": "CONTAINS",
                "source_node_id": doc_node_id,
                "target_node_id": chunk_node_id,
                "confidence": 1.0,
                "weight": 1.0,
            },
            subject_id=doc_contains_chunk,
        )
        chunk_part_of_doc = upsert_edge(
            db_path,
            {
                "edge_id": make_edge_id(),
                "edge_type": "PART_OF",
                "source_node_id": chunk_node_id,
                "target_node_id": doc_node_id,
                "confidence": 1.0,
                "weight": 1.0,
                "evidence": f"ingest: chunk {c.chunk_index} is part of document",
                "created_by": "ingest_pipeline",
                "origin_event_id": chunk_evt_id,
                "lifecycle_state": "active",
                "payload_json": "{}",
                "created_at": now,
                "updated_at": now,
            },
        )
        emit(
            "GraphEdgeCreated",
            "graph_store",
            "Edge: Chunk PART_OF Document",
            {
                "edge_id": chunk_part_of_doc,
                "edge_type": "PART_OF",
                "source_node_id": chunk_node_id,
                "target_node_id": doc_node_id,
                "confidence": 1.0,
                "weight": 1.0,
            },
            subject_id=chunk_part_of_doc,
        )

    # ── Build and batch-insert memory records ────────────────────────────────
    records = build_records_for_document(chunks, source)
    record_dicts = [r.as_dict() for r in records]
    store.insert_records_batch(record_dicts)

    record_ids: list[str] = []
    for r in records:
        rec_evt_id = emit(
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
        record_ids.append(r.record_id)
        rec_node_id = upsert_node(
            db_path,
            {
                "node_id": make_node_id(f"memory_records:{r.record_id}"),
                "node_type": "MemoryRecord",
                "label": r.record_id,
                "entity_id": r.record_id,
                "entity_table": "memory_records",
                "lifecycle_state": "active",
                "origin_event_id": rec_evt_id,
                "payload_json": json.dumps({"token_estimate": r.token_estimate}),
                "created_at": now,
                "updated_at": now,
            },
        )
        emit(
            "GraphNodeCreated",
            "graph_store",
            f"MemoryRecord node: {r.record_id}",
            {
                "node_id": rec_node_id,
                "node_type": "MemoryRecord",
                "entity_id": r.record_id,
                "entity_table": "memory_records",
            },
            subject_id=rec_node_id,
        )
        chunk_node_id_or_none: str | None = chunk_node_ids.get(r.chunk_id)
        if chunk_node_id_or_none is not None:
            chunk_node_id = chunk_node_id_or_none
            chunk_for_record = next((c for c in chunks if c.chunk_id == r.chunk_id), None)
            derived_from = upsert_edge(
                db_path,
                {
                    "edge_id": make_edge_id(),
                    "edge_type": "DERIVED_FROM",
                    "source_node_id": rec_node_id,
                    "target_node_id": chunk_node_id,
                    "confidence": 1.0,
                    "weight": 1.0,
                    "evidence": (
                        f"ingest: record derived from chunk_index="
                        f"{chunk_for_record.chunk_index if chunk_for_record else '?'}"
                    ),
                    "created_by": "ingest_pipeline",
                    "origin_event_id": rec_evt_id,
                    "lifecycle_state": "active",
                    "payload_json": json.dumps(
                        {
                            "chunk_index": chunk_for_record.chunk_index,
                            "heading_path": chunk_for_record.heading_path,
                        }
                        if chunk_for_record is not None
                        else {}
                    ),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            emit(
                "GraphEdgeCreated",
                "graph_store",
                "Edge: MemoryRecord DERIVED_FROM Chunk",
                {
                    "edge_id": derived_from,
                    "edge_type": "DERIVED_FROM",
                    "source_node_id": rec_node_id,
                    "target_node_id": chunk_node_id,
                    "confidence": 1.0,
                    "weight": 1.0,
                },
                subject_id=derived_from,
            )

    # ── Index updates ────────────────────────────────────────────────────────
    if record_ids:
        update_fts_index(db_path, record_ids, event_log=event_log)
        queue_for_embedding(db_path, record_ids)

    # ── Update source as ingested ────────────────────────────────────────────
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
