# Cerebra — Storage Layer

All persistent state lives in `<vault>/cerebra.db` (SQLite, WAL mode) and `<vault>/.fossic/store.db` (Fossic content-addressed store). This document covers every table, the connection factory, all 18 migrations, and the storage module implementations.

---

## 1. Connection Factory (`cerebra/storage/db.py`)

```python
def connect(db_path: Path) -> sqlite3.Connection
```

Applied pragmas (every connection):
- `PRAGMA journal_mode=WAL` — enables concurrent readers + one writer
- `PRAGMA foreign_keys=ON` — enforces FK constraints
- `PRAGMA synchronous=NORMAL` — balances durability vs. write speed
- `row_factory = sqlite3.Row` — all rows accessible as dicts

**Rule:** Every SQLite connection in the codebase must use this factory. Direct `sqlite3.connect()` calls are forbidden — they bypass the WAL + FK setup.

**WAL discipline for inspector events:** All inspector event writes must happen *after* `conn.close()` on any connection that just modified related tables. This prevents "database is locked" under WAL concurrency. Enforced by pattern in `TruthTower`, `LifecycleManager`, and other modules that do a DB write then emit an inspector event.

---

## 2. Migrations (`cerebra/storage/migrations.py`)

```python
def run_migrations(db_path: Path) -> None
```

Idempotent. Tracks applied versions in `applied_migrations` table (created if absent). Runs all unapplied migrations in order. Safe to call on every startup.

### Migration table index

| Migration | Tables Created | Notes |
|---|---|---|
| M001 | `inspector_events`, `sources`, `documents`, `chunks`, `memory_records` | Core schema |
| M002 | `sku_assignments` | Phase 2 SKU classification |
| M003 | `embeddings`, `pending_embeddings` | Phase 3 vector search |
| M004 | `index_state` | FTS5 staleness tracking |
| M005 | `graph_nodes`, `graph_edges` | Phase 4 graph model |
| M006 | `retrieval_traces`, `retrieval_steps`, `retrieval_candidates` | Retrieval audit |
| M007 | `sessions` | Phase 5 WM sessions |
| M008 | `working_memory_items` | Phase 5 attention items |
| M009 | `truth_tower_items` | Phase 5 tower |
| M010 | `evaluations` | Phase 6 signal evaluation |
| M011 | `predictions`, `outcomes` | Phase 6 prediction pipeline |
| M012 | `runtime_sessions` | Phase 7 cycle sessions |
| M013 | `continuation_bundles` | Phase 7 checkpointing |
| M014 | `cycle_episode_records` | Phase 10 episode writer |
| M015 | ADD COLUMN `is_lattice_member` to `memory_records` | Lattice support |
| M016 | ADD COLUMN `lattice_lineage_id` to `memory_records` | |
| M017 | ADD COLUMN `lattice_confidence` to `memory_records` | |
| M018 | Synthetic provenance sentinels | FK anchor for cycle episodes |

### M018 — Synthetic provenance sentinels

Inserts three sentinel rows so cycle episodes can have valid FK references in `memory_records`:

```sql
INSERT OR IGNORE INTO sources (source_id, ...) VALUES ('src_synthetic', ...)
INSERT OR IGNORE INTO documents (document_id, ...) VALUES ('doc_synthetic', ...)
INSERT OR IGNORE INTO chunks (chunk_id, ...) VALUES ('chk_synthetic', ...)
```

These are referenced by `EpisodeWriter` when inserting cycle episodes into `memory_records`. Without them, the FK constraints would reject episode rows (which have no real source file).

Constants in `_constants.py`:
- `SYNTHETIC_SOURCE_ID = "src_synthetic"`
- `SYNTHETIC_DOCUMENT_ID = "doc_synthetic"`
- `SYNTHETIC_CHUNK_ID = "chk_synthetic"`

---

## 3. Table Schemas

### `inspector_events`

```sql
CREATE TABLE inspector_events (
    event_id        TEXT PRIMARY KEY,   -- "evt_" + uuid[:12]
    event_type      TEXT NOT NULL,
    actor           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    data            TEXT NOT NULL,      -- JSON blob
    schema_version  INT NOT NULL DEFAULT 1,
    timestamp       INT NOT NULL,       -- unix seconds
    session_id      TEXT,
    cycle_id        TEXT,
    step_id         TEXT,
    subject_id      TEXT
)
```

Indexed by: `event_type`, `session_id`, `subject_id`, `timestamp`.

---

### `sources`

```sql
CREATE TABLE sources (
    source_id           TEXT PRIMARY KEY,   -- "src_" + sha256(canonical_path)[:16]
    canonical_path      TEXT NOT NULL UNIQUE,
    content_hash        TEXT NOT NULL,
    size_bytes          INT NOT NULL,
    detected_type       TEXT NOT NULL,
    detection_confidence REAL NOT NULL,
    parser_adapter      TEXT,
    parser_version      TEXT,
    chunker_version     TEXT,
    parser_status       TEXT NOT NULL DEFAULT 'pending',  -- "pending" | "parsed"
    lifecycle_state     TEXT NOT NULL DEFAULT 'active',
    created_at          INT NOT NULL,
    modified_at         INT,
    ingested_at         INT,
    schema_version      INT NOT NULL DEFAULT 1
)
```

---

### `documents`

```sql
CREATE TABLE documents (
    document_id     TEXT PRIMARY KEY,   -- "doc_" + uuid[:12]
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    title           TEXT,
    doc_type        TEXT,
    word_count      INT,
    schema_version  INT NOT NULL DEFAULT 1,
    created_at      INT NOT NULL
)
```

---

### `chunks`

```sql
CREATE TABLE chunks (
    chunk_id        TEXT PRIMARY KEY,   -- "chk_" + uuid[:12]
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    content         TEXT NOT NULL,
    chunk_index     INT NOT NULL,       -- position within document
    token_estimate  INT NOT NULL,
    schema_version  INT NOT NULL DEFAULT 1,
    created_at      INT NOT NULL
)
```

---

### `memory_records`

```sql
CREATE TABLE memory_records (
    record_id           TEXT PRIMARY KEY,   -- "rec_" + sha256(chunk_id)[:12]
    record_type         TEXT NOT NULL DEFAULT 'source_chunk',  -- "source_chunk" | "cycle_episode"
    source_id           TEXT NOT NULL REFERENCES sources(source_id),
    document_id         TEXT NOT NULL REFERENCES documents(document_id),
    chunk_id            TEXT NOT NULL REFERENCES chunks(chunk_id),
    content             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    token_estimate      INT NOT NULL,
    sku_address         TEXT,               -- NULL until classified
    sku_assigned_at     INT,
    lifecycle_state     TEXT NOT NULL DEFAULT 'active',  -- "active"|"archived"|"tombstoned"
    created_at          INT NOT NULL,
    schema_version      INT NOT NULL DEFAULT 1,
    -- M015-M017 additions:
    is_lattice_member   INT NOT NULL DEFAULT 0,   -- bool
    lattice_lineage_id  TEXT,
    lattice_confidence  REAL
)
```

---

### `sku_assignments`

```sql
CREATE TABLE sku_assignments (
    assignment_id               TEXT PRIMARY KEY,
    record_id                   TEXT NOT NULL REFERENCES memory_records(record_id),
    sku_address                 TEXT NOT NULL,
    d1_category                 TEXT NOT NULL,
    classifier_version          TEXT NOT NULL,
    prompt_version              TEXT NOT NULL,
    subcategory_strategy_version TEXT NOT NULL,
    confidence                  REAL NOT NULL,
    raw_scores_json             TEXT,       -- full quadrant+category scores JSON
    assigned_at                 INT NOT NULL
)
```

---

### `embeddings`

```sql
CREATE TABLE embeddings (
    embedding_id    TEXT PRIMARY KEY,   -- "emb_" + sha256(record_id:model:version)[:12]
    record_id       TEXT NOT NULL REFERENCES memory_records(record_id),
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    vector_blob     BLOB NOT NULL,      -- float32 LE, 1024 dims
    created_at      INT NOT NULL
)
```

---

### `pending_embeddings`

```sql
CREATE TABLE pending_embeddings (
    record_id   TEXT PRIMARY KEY REFERENCES memory_records(record_id),
    queued_at   INT NOT NULL
)
```

---

### `index_state`

```sql
CREATE TABLE index_state (
    key             TEXT PRIMARY KEY,   -- "fts5_last_updated"
    last_updated_at INT NOT NULL
)
```

Used by `is_lexical_stale()` to compare against `MAX(created_at)` from `memory_records`.

---

### `graph_nodes`

```sql
CREATE TABLE graph_nodes (
    node_id     TEXT PRIMARY KEY,   -- "source:<source_id>" | "record:<record_id>"
    node_type   TEXT NOT NULL,
    label       TEXT,
    data        TEXT,               -- JSON blob
    created_at  INT NOT NULL
)
```

---

### `graph_edges`

```sql
CREATE TABLE graph_edges (
    edge_id     TEXT PRIMARY KEY,   -- "edge_" + uuid[:12]
    source      TEXT NOT NULL REFERENCES graph_nodes(node_id),
    target      TEXT NOT NULL REFERENCES graph_nodes(node_id),
    edge_type   TEXT NOT NULL,
    weight      REAL,
    data        TEXT,               -- JSON blob
    created_at  INT NOT NULL
)
```

---

### `retrieval_traces`

```sql
CREATE TABLE retrieval_traces (
    trace_id            TEXT PRIMARY KEY,   -- "trace_" + uuid[:12]
    query               TEXT NOT NULL,
    mode                TEXT NOT NULL,      -- "lexical" | "vector" | "hybrid"
    context_packet_id   TEXT,               -- filled after build_context_packet()
    created_at          INT NOT NULL
)
```

---

### `retrieval_steps`

```sql
CREATE TABLE retrieval_steps (
    step_id     TEXT PRIMARY KEY,
    trace_id    TEXT NOT NULL REFERENCES retrieval_traces(trace_id),
    step_name   TEXT NOT NULL,      -- "exact_sku" | "lexical_search" | etc.
    candidate_count INT NOT NULL,
    created_at  INT NOT NULL
)
```

---

### `retrieval_candidates`

```sql
CREATE TABLE retrieval_candidates (
    candidate_id        TEXT PRIMARY KEY,
    trace_id            TEXT NOT NULL REFERENCES retrieval_traces(trace_id),
    record_id           TEXT NOT NULL,
    semantic_score      REAL,
    lexical_score       REAL,
    sku_match_score     REAL,
    recency_score       REAL,
    lifecycle_score     REAL,
    composite_score     REAL NOT NULL,
    retrieval_path      TEXT,
    exclusion_reason    TEXT,   -- NULL if selected; "composite_floor" | "lattice_sibling" | etc.
    rank                INT,
    created_at          INT NOT NULL
)
```

---

### `runtime_sessions` (M012)

```sql
CREATE TABLE runtime_sessions (
    session_id          TEXT PRIMARY KEY,   -- "sess_" + uuid[:12]
    cycle_config        TEXT NOT NULL,
    goal                TEXT NOT NULL,
    vault_path          TEXT NOT NULL,
    opened_at           INT NOT NULL,       -- ms
    parent_session_id   TEXT,
    recursion_depth     INT NOT NULL DEFAULT 0,
    max_recursion_depth INT NOT NULL,
    cycles_run          INT NOT NULL DEFAULT 0,
    steps_run           INT NOT NULL DEFAULT 0,
    state               TEXT NOT NULL DEFAULT 'active',  -- "active"|"flushed"|"continued"
    flushed_at          INT,
    final_outcome       TEXT
)
```

---

### `continuation_bundles` (M013)

```sql
CREATE TABLE continuation_bundles (
    bundle_id               TEXT PRIMARY KEY,   -- "bundle_" + uuid[:12]
    parent_session_id       TEXT NOT NULL,
    child_session_id        TEXT,
    distilled_goal          TEXT NOT NULL,
    summarized_prior_prompt TEXT NOT NULL,
    truth_tower_projection  TEXT NOT NULL,  -- JSON
    cognitive_insights      TEXT NOT NULL,  -- JSON array
    next_focus              TEXT NOT NULL,
    open_questions          TEXT NOT NULL,  -- JSON array
    constraints             TEXT NOT NULL,  -- JSON array
    recursion_depth         INT NOT NULL,
    voice_mode              TEXT NOT NULL,
    bundle_size_bytes       INT NOT NULL,
    created_at              INT NOT NULL,
    triggered_at            INT
)
```

---

### `cycle_episode_records` (M014)

```sql
CREATE TABLE cycle_episode_records (
    record_id                   TEXT PRIMARY KEY,   -- "ep_" + uuid[:12]
    runtime_session_id          TEXT NOT NULL,
    working_memory_session_id   TEXT,
    cycle_id                    TEXT NOT NULL,
    step_id                     TEXT NOT NULL,
    step_name                   TEXT NOT NULL,
    content                     TEXT NOT NULL,
    content_summary             TEXT NOT NULL,  -- first 200 chars
    metadata                    TEXT,           -- JSON
    leeway_grant_event_id       TEXT,
    cited_record_ids            TEXT,           -- JSON array
    created_at                  INT NOT NULL
)
```

---

### `predictions` / `outcomes` (M011)

```sql
CREATE TABLE predictions (
    prediction_id       TEXT PRIMARY KEY,   -- "pred_" + uuid[:12]
    session_id          TEXT NOT NULL,
    cycle_id            TEXT NOT NULL,
    step_id             TEXT NOT NULL,
    expected_composite  REAL NOT NULL,
    expected_per_signal TEXT NOT NULL,  -- JSON dict
    prediction_basis    TEXT NOT NULL,  -- "prior_step_trajectory"|"cycle_config_default"|"static_baseline"
    confidence          REAL NOT NULL,
    made_at             INT NOT NULL
)

CREATE TABLE outcomes (
    outcome_id              TEXT PRIMARY KEY,
    prediction_id           TEXT NOT NULL REFERENCES predictions(prediction_id),
    session_id              TEXT NOT NULL,
    cycle_id                TEXT NOT NULL,
    step_id                 TEXT NOT NULL,
    actual_composite        REAL NOT NULL,
    prediction_error        REAL NOT NULL,  -- signed: actual - expected
    error_classification    TEXT NOT NULL,  -- "noise" | "notable" | "severe"
    per_signal_error        TEXT NOT NULL,  -- JSON dict
    recorded_at             INT NOT NULL
)
```

---

## 4. FossicStore (`cerebra/storage/fossic_store.py`)

Wraps `fossic.Store` — a content-addressed, causation-chained event store.

```python
class FossicStore:
    def __init__(self, vault_path: Path)        # opens <vault>/.fossic/store.db
    
    @classmethod
    def at_platform_path(cls, db_path: Path)    # opens explicit path (hub store)
```

### Key methods

```python
def append(
    stream_id: str,
    event_type: str,
    payload: dict,
    causation_id: bytes | None = None,
    external_id: str | None = None,
    indexed_tags: dict | None = None,
) -> bytes
```

Returns content-addressed event ID bytes. The returned bytes become the `causation_id` for the next event in a chain.

```python
def read_events(
    *,
    stream_id: str | None = None,
    stream_pattern: str | None = None,   # glob, e.g. "cerebra/agent-trace/**"
    event_type: str | None = None,
    branch: str = "main",
    from_version: int | None = None,
) -> list[dict]
```

Each dict: `{event_type, payload, version, stream_id}`

```python
def register_reducer(stream_pattern: str, reducer: Callable) -> None
def read_state(stream_id: str) -> Any
def take_snapshot(stream_id: str) -> SnapshotInfo | None
def current_version(stream_id: str) -> int
def last_snapshot_version(stream_id: str) -> int
```

### Fossic streams (Cerebra)

| Stream pattern | Content |
|---|---|
| `cerebra/agent-trace/<session_id>` | Full per-session cycle event chain |
| `cerebra/control` | Daemon posture events (PostureChanged) |
| `cerebra/lattice/<lineage_id>` | Lattice classification events per lineage |
| `cerebra/graph/<lineage_id>` | GraphSnapshotAvailable (hub-direct only) |

### DEV-005 — CCE dedup

Fossic's content-addressed event engine deduplicates identical `(event_type + payload + causation_id)` tuples. Two events with the same type, payload, and causation_id collapse to one. Cerebra emission paths must vary causation_id to avoid unintended dedup (EventEmitter handles this automatically via chaining).

---

## 5. Embeddings (`cerebra/storage/embeddings.py`)

**Model:** `mixedbread-ai/mxbai-embed-large-v1`
- Dimensions: 1024
- Storage format: float32 little-endian blob
- Embedding ID: `"emb_" + sha256(f"{record_id}:{model_name}:{model_version}")[:12]`

### Functions

```python
def queue_for_embedding(db_path: Path, record_ids: list[str]) -> None
```
Inserts into `pending_embeddings`. Idempotent (INSERT OR IGNORE).

```python
def drain_pending(db_path: Path, batch_size: int = 32) -> int
```
Reads from `pending_embeddings`, generates embeddings in batches, inserts to `embeddings`, removes from queue. Returns count processed.

```python
def cosine_search(
    db_path: Path,
    query_text: str,
    limit: int = 20,
) -> list[tuple[str, float]]
```

Loads all active record embeddings into memory, computes cosine similarity via numpy, returns `[(record_id, score)]` sorted DESC. Safe up to ~50k records. For larger vaults, an ANN index would be needed (not yet implemented).

---

## 6. FTS5 / Lexical (`cerebra/storage/lexical.py`)

### Constants

```python
FTS_TABLE = "memory_records_fts"
```

### Functions

```python
def build_fts_index(db_path: Path, *, event_log=None) -> int
```

Full DROP + recreate of `memory_records_fts` from all active records. Returns record count indexed. Emits `LexicalIndexUpdated` inspector event.

```python
def update_fts_index(db_path: Path, record_ids: list[str], *, event_log=None) -> int
```

**Also does a full rebuild** (not incremental). This is intentional: SQLite 3.45 has a bug where incremental FTS5 delete on empty shadow tables raises "database disk image is malformed". The full rebuild avoids this.

```python
def search(db_path: Path, query: str, *, limit: int = 20) -> list[tuple[str, float]]
```

FTS5 MATCH query. Returns `[(record_id, rank)]` where rank is negative (more negative = better match). Callers negate the rank for scoring.

```python
def _sanitize_fts_query(query: str) -> str
```

Strips all non-alphanumeric characters so LLM-generated queries are safe for FTS5 MATCH (prevents syntax errors from special characters).

```python
def is_lexical_stale(db_path: Path) -> bool
```

Compares `MAX(memory_records.created_at)` vs `index_state.last_updated_at`. True means the index is behind the current record set.

---

## 7. ArtifactStore (`cerebra/storage/artifact_store.py`)

Persists structured and plain-text representations of parsed documents to disk.

```python
def write_artifact(doc: ParseResult, artifacts_dir: Path) -> Path
```
Writes `<artifacts_dir>/<doc_id>.json` — full structured JSON of the parsed document (title, sections, metadata).

```python
def write_text_artifact(vault_path: Path, doc_id: str, raw_content: str) -> Path
```
Writes `<vault>/data/<doc_id>.txt` — raw plain-text version. Used for reference and future re-processing.

---

## 8. GraphStore (`cerebra/storage/graph_store.py`)

Wraps the `graph_nodes` + `graph_edges` tables.

```python
def upsert_node(db, node_id: str, node_type: str, label: str, data: dict) -> None
```
INSERT OR REPLACE into `graph_nodes`.

```python
def upsert_edge(
    db,
    source: str,
    target: str,
    edge_type: str,
    weight: float | None = None,
    data: dict | None = None,
) -> str  # returns edge_id
```
INSERT OR IGNORE by `(source, target, edge_type)` uniqueness. Returns existing edge_id if already present.

These tables back the in-vault graph model (not to be confused with the exported `graph.json` — they're the same data in different formats).

---

## 9. IndexState (`cerebra/storage/index_state.py`)

```python
def get_index_state(db_path: Path, key: str) -> int | None
def update_index_state(db_path: Path, key: str, value: int) -> None
```

Currently used for one key: `"fts5_last_updated"` — unix timestamp of last FTS5 rebuild.

---

## 10. SQLiteStore (`cerebra/storage/sqlite_store.py`)

Higher-level store object used by the ingest pipeline and retrieval layer.

Key methods (non-exhaustive):

```python
def insert_document(doc: Document) -> None
def insert_chunks_batch(chunks: list[Chunk]) -> None
def insert_records_batch(records: list[MemoryRecord]) -> None
def get_record(record_id: str) -> MemoryRecord | None
def get_records_for_document(document_id: str) -> list[MemoryRecord]
def get_unclassified_records(limit: int) -> list[MemoryRecord]
def insert_sku_assignment(assignment: SKUAssignment) -> None
def update_record_sku(record_id: str, sku_address: str, assigned_at: int) -> None
def insert_session(session: WorkingMemorySession) -> None
def get_active_session() -> WorkingMemorySession | None
```

All methods use the `connect()` factory — they open and close their own connections per call (no persistent connection state on the object).
