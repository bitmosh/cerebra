# Cerebra — Sources, Ingest Pipeline & Graph Export

---

## 1. Sources (`cerebra/sources/`)

### SourceRecord (`cerebra/sources/registry.py`)

```python
@dataclass
class SourceRecord:
    source_id: str              # "src_" + sha256(canonical_path)[:16]
    canonical_path: str         # absolute path, normalized
    content_hash: str           # sha256 of file contents (hex)
    size_bytes: int
    detected_type: str          # e.g. "markdown", "text/plain"
    detection_confidence: float # 0.0–1.0
    parser_adapter: str | None  # "markdown" | "text" | None
    parser_version: str | None
    chunker_version: str | None
    parser_status: str          # "pending" → "parsed"
    lifecycle_state: str        # "active" (default)
    created_at: int             # unix ms
    modified_at: int | None
    ingested_at: int | None
    schema_version: int
```

Source ID is stable across re-ingests as long as the canonical path doesn't change.

---

### `register_source()` (`cerebra/sources/registry.py`)

```python
def register_source(
    store: SQLiteStore,
    event_log: SQLiteEventLog,
    path: Path,
    detection: DetectionResult,
    parser_version: str,
    chunker_version: str,
) -> tuple[SourceRecord, RegistrationOutcome]
```

**RegistrationOutcome** (enum):
- `NEW` — first time this path has been seen
- `SKIPPED_UNCHANGED` — `(canonical_path, content_hash, parser_version, chunker_version)` matches existing record; caller should skip all downstream work
- `CHANGED` — content_hash or version changed; marks source + all its documents + chunks + memory records as stale

**On CHANGED:**
- Updates source row with new content_hash, modified_at
- Marks associated documents/chunks/records stale (lifecycle_state = "stale", or triggers re-parse)
- Emits `SourceChanged` inspector event

**On NEW:**
- Inserts source row
- Emits `SourceRegistered` inspector event

---

### Type Detection (`cerebra/sources/detector.py`)

```python
def detect_type(path: Path) -> DetectionResult

@dataclass
class DetectionResult:
    detected_type: str
    confidence: float
    adapter_hint: str | None    # "markdown" | "text" | None
```

Detection is heuristic (extension + content sniff). No ML. Confidence is rule-derived:
- `.md`, `.mdx` → `"markdown"`, confidence=0.95
- `.txt` → `"text/plain"`, confidence=0.90
- Unknown → `"text/plain"`, confidence=0.50

---

### Discovery (`cerebra/sources/discovery.py`)

```python
def discover_files(
    target: Path,
    *,
    extensions: frozenset[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[Path]
```

Walks `target` recursively. If `extensions` is provided, only returns files matching those extensions. `exclude_patterns` are glob patterns matched against the relative path from `target`.

---

### Hashing (`cerebra/sources/hashing.py`)

```python
def content_hash(path: Path) -> str    # sha256 hex digest of file bytes
```

---

## 2. Ingest Pipeline (`cerebra/ingest/pipeline.py`)

### IngestReport

```python
@dataclass
class IngestReport:
    sources_found: int
    sources_new: int
    sources_changed: int
    sources_skipped: int
    sources_failed: int
    chunks_created: int
    records_created: int
    errors: list[str]
```

---

### `ingest_path()` — entry point

```python
def ingest_path(
    vault_path: Path,
    target: Path,
    *,
    dry_run: bool = False,
    exclude_patterns: list[str] | None = None,
    extensions: frozenset[str] | None = None,
    chunk_options: ChunkOptions | None = None,
) -> IngestReport
```

**Event log:** Dual-writes to both `SQLiteEventLog` (inspector_events table) and `NDJSONEventLog` (`vault/events/ingest.ndjson`).

---

### Per-file pipeline: `_ingest_file()` — 17 steps

Each file discovered by `discover_files()` passes through all 17 steps:

1. `detect_type(file_path)` → `DetectionResult`
2. `register_source(store, event_log, path, detection, parser_version, chunker_version)` → `(SourceRecord, outcome)`
3. **If `SKIPPED_UNCHANGED`:** return immediately (no further processing)
4. Upsert Source graph node (`upsert_node(db, "source:<source_id>", "spine", ...)`)
   - Emits `GraphNodeCreated` inspector event
5. Select adapter based on `detection.adapter_hint`:
   - `"markdown"` → `MarkdownAdapter`
   - `"text"` or None → `TextAdapter`
6. `adapter.parse(path, source_record)` → `ParseResult`
   - On failure: emit `SourceParseFailed`, add to `report.errors`, return
7. `write_artifact(doc, artifacts_dir)` → writes `<artifacts_dir>/<doc_id>.json`
8. `write_text_artifact(vault_path, doc_id, raw_content)` → writes `<vault>/data/<doc_id>.txt`
9. Emit `DocumentNormalized` inspector event
10. `store.insert_document(doc)` → inserts to `documents` table
11. Upsert Document graph node + Source→Document CONTAINS edge (`upsert_node`, `upsert_edge`)
12. `chunk_document(doc, opts)` → `list[Chunk]`; `store.insert_chunks_batch(chunks)`
13. For each chunk: upsert Chunk graph node + Document→Chunk CONTAINS edge + Chunk→Document PART_OF edge
14. `build_records_for_document(chunks, source)` → `list[MemoryRecord]`; `store.insert_records_batch(records)`
15. For each record: upsert MemoryRecord graph node + MemoryRecord→Chunk DERIVED_FROM edge
16. `update_fts_index(db_path, record_ids)` — full rebuild (adds new records)
17. `queue_for_embedding(db_path, record_ids)` — inserts to `pending_embeddings`
18. Update source `parser_status = "parsed"`, `ingested_at = now`
19. Emit `SourceParsed` inspector event

---

### Chunking (`cerebra/ingest/chunking.py`)

```python
def chunk_document(doc: ParseResult, opts: ChunkOptions | None = None) -> list[Chunk]

@dataclass
class ChunkOptions:
    max_tokens: int = 512
    overlap_tokens: int = 64
    min_tokens: int = 32
```

Token estimation: character count / 4 (heuristic). Chunks are non-overlapping in text but may overlap in token count (sliding window).

Chunk IDs: `"chk_" + uuid[:12]` (random, not content-addressed — chunk_index is the stable key within a document).

---

### Adapters

**MarkdownAdapter (`cerebra/ingest/adapters/markdown.py`):**

```python
class MarkdownAdapter(BaseAdapter):
    PARSER_VERSION = "1.0.0"
    
    def parse(self, path: Path, source: SourceRecord) -> ParseResult
```

Extracts: title (first H1), sections (H2/H3 boundaries), metadata (frontmatter if present). Joins section text for chunking.

**TextAdapter (`cerebra/ingest/adapters/text.py`):**

```python
class TextAdapter(BaseAdapter):
    PARSER_VERSION = "1.0.0"
    
    def parse(self, path: Path, source: SourceRecord) -> ParseResult
```

Reads raw text, uses filename as title, no section structure. Passes full content to chunker.

**ParseResult (shared, `cerebra/ingest/models.py`):**

```python
@dataclass
class ParseResult:
    document_id: str       # "doc_" + uuid[:12]
    source_id: str
    title: str
    doc_type: str
    sections: list[Section]
    raw_content: str
    word_count: int
    metadata: dict
```

---

## 3. Graph Model (`cerebra/graph/model.py`)

### ExportStats

```python
@dataclass
class ExportStats:
    node_count: int
    edge_count: int
    spine_count: int          # source nodes
    record_count: int         # memory_record nodes
    classified_count: int     # records with sku_address
    unclassified_count: int   # records without sku_address
    edges_by_type: dict[str, int]
    out_path: Path
    elapsed_ms: int
```

---

## 4. Graph Exporter (`cerebra/graph/exporter.py`)

```python
def export_graph(
    vault_path: Path,
    *,
    out_path: Path | None = None,       # default: <vault>/.cerebra/graph.json
    event_log: SQLiteEventLog | None = None,
    hub_store: Any = None,              # FossicStore for hub-direct emission
    triggered_by: str | None = None,   # event_id that triggered this export
) -> ExportStats
```

### Schema version

`"cerebra/v1"` — the schema identifier embedded in the output JSON.

### Node types

**Spine nodes** (one per active, non-`cerebra://` source):
```json
{
  "id": "source:<source_id>",
  "type": "spine",
  "label": "<filename>",
  "cluster": "<detected_type_cluster>",
  "data": {
    "source_id": "...",
    "canonical_path": "...",
    "detected_type": "...",
    "record_count": N
  }
}
```

Cluster colors by `detected_type`:
- `markdown` → `"azure"`
- `text/plain` → `"slate"`
- unknown → `"gray"`
- code types → `"teal"`

**Memory record nodes** (one per active record with an `sku_assignment`):
```json
{
  "id": "record:<record_id>",
  "type": "memory_record",
  "label": "<first 60 chars of content>",
  "cluster": "<d1_quadrant_cluster>",
  "data": {
    "record_id": "...",
    "sku_address": "...",
    "d1_category": "...",
    "lifecycle_state": "active",
    "is_lattice_member": false
  }
}
```

D1 quadrant cluster colors:
- Empirical (D1 `0x0`–`0x3`) → `"azure"`
- Generative (D1 `0x4`–`0x7`) → `"gold"`
- Normative (D1 `0x8`–`0xB`) → `"purple"`
- Relational (D1 `0xC`–`0xF`) → `"teal"`

Unclassified records (no sku_assignment) are **excluded** from the export.

### Edge types

| Type | Weight | Source → Target | Cap |
|---|---|---|---|
| `contains` | 0.4 | source node → record node | none |
| `describes` | 0.65 | record[N] → record[N+1] | chunk_index adjacency within same doc |
| `sku-proximity` | `min(0.5, group_size/20)` | record → record (shared D1) | `_SKU_PROXIMITY_CAP = 5` per node |
| `sku-exact` | 0.9 | record → record (identical sku_address) | none |

`sku-proximity` edges are capped at 5 per node to prevent hub-and-spoke topology when many records share the same D1 category.

### Node cap

`_MAX_NODES = 2000` total nodes. If the vault has more, sources are selected alphabetically (by canonical_path), then records selected in chunk_index order within those sources.

### Output JSON structure

```json
{
  "schemaVersion": "cerebra/v1",
  "metadata": {
    "schemaVersion": "cerebra/v1",
    "generatedAt": 1750000000,
    "generator": "cerebra",
    "vaultPath": "/abs/path/to/vault",
    "cerebraVersion": "0.4.4",
    "stats": {
      "nodeCount": 142,
      "edgeCount": 389,
      "nodesByType": {"spine": 12, "memory_record": 130},
      "edgesByType": {"contains": 130, "describes": 128, "sku-proximity": 87, "sku-exact": 44},
      "activeSourceCount": 12,
      "activeRecordCount": 180,
      "classifiedRecordCount": 130,
      "unclassifiedRecordCount": 50
    }
  },
  "nodes": [...],
  "edges": [...]
}
```

Written to `<vault>/.cerebra/graph.json` (creates `.cerebra/` dir if absent).

### Hub-direct emission

If `hub_store` is provided (or `CEREBRA_PLATFORM_STORE` is set when called from the daemon):

```python
hub_store.append(
    stream_id=f"cerebra/graph/{lineage_id}",
    event_type="GraphSnapshotAvailable",
    payload={
        "graph_path": str(out_path),
        "node_count": stats.node_count,
        "edge_count": stats.edge_count,
        "vault_path": str(vault_path),
        "triggered_by": triggered_by,
    }
)
```

Hub errors are caught and swallowed (non-fatal). The local export always completes regardless of hub status.

### Inspector events emitted

- `GraphExported` — after successful write, includes ExportStats in payload
- `GraphNodeCreated` — during ingest pipeline (not during export_graph; nodes are pre-existing in graph_nodes table)
- `GraphEdgeCreated` — same as above
- `GraphSnapshotAvailable` — only if hub-direct write succeeded

---

## 5. Data Flow: Ingest

```
CLI: cerebra ingest <target>
  └─ discover_files(target, extensions, exclude_patterns)
       └─ for each file:
            detect_type(file) → DetectionResult
            register_source(...) → (SourceRecord, RegistrationOutcome)
            if SKIPPED_UNCHANGED: continue
            MarkdownAdapter | TextAdapter .parse() → ParseResult
            write_artifact() + write_text_artifact()
            store.insert_document()
            upsert_node("source:<id>") + upsert_node("doc:<id>")
            upsert_edge(source→doc, "contains")
            chunk_document() → list[Chunk]
            store.insert_chunks_batch()
            for chunk: upsert_node + edges
            build_records_for_document() → list[MemoryRecord]
            store.insert_records_batch()
            for record: upsert_node + DERIVED_FROM edge
            update_fts_index(record_ids)     ← full FTS5 rebuild
            queue_for_embedding(record_ids)  ← deferred unless --embed
            source.parser_status = "parsed"
            emit SourceParsed
  └─ return IngestReport
```

---

## 6. Data Flow: Graph Export

```
CLI: cerebra export-graph
  └─ export_graph(vault_path)
       └─ SQL: SELECT active sources (canonical_path NOT LIKE 'cerebra://%')
            → spine nodes (up to _MAX_NODES)
          SQL: SELECT active records JOIN sku_assignments
            → memory_record nodes (classified only)
          Build edges:
            contains: source → each of its records
            describes: chunk_index-adjacent record pairs within same doc
            sku-proximity: records sharing D1 category (cap 5/node)
            sku-exact: records with identical sku_address
          Write graph.json (cerebra/v1)
          [If hub_store]: append GraphSnapshotAvailable to cerebra/graph/<lineage_id>
          emit GraphExported inspector event
          return ExportStats
```
