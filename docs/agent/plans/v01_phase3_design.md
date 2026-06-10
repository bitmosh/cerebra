# Phase 3 Design — Storage and Index Layer

**Status:** Draft v2 — amendments applied 2026-06-09; awaiting final review before Migration006  
**Date:** 2026-06-09  
**Scope:** Design only. No implementation. Three locked decisions (D1/D2/D3) that every subsequent phase depends on.

---

## §1. Current State

### What exists (implemented, tested, on `main`)

| Area | Files | State |
|------|-------|-------|
| Migration framework | `cerebra/storage/migrations.py` | Migrations 1–5 applied. Schema v5 in production with 745 records. WAL journal mode. |
| SQLite store | `cerebra/storage/sqlite_store.py` | Full CRUD for sources, documents, chunks, memory_records, sku_assignments. |
| DB connection | `cerebra/storage/db.py` | WAL mode, row_factory. |
| Inspector events | `cerebra/inspector/event.py`, `ndjson_log.py`, `sqlite_log.py` | Envelope, NDJSON writer, SQLite writer implemented. Phase 0 event type subset live. |
| Graph module | `cerebra/graph/__init__.py` | Empty stub — just `__init__.py`. |
| Storage `__init__` | `cerebra/storage/__init__.py` | Empty. |

### Schema as of Migration005 (current production state)

Tables live: `applied_migrations`, `inspector_events`, `sources`, `documents`, `chunks`, `memory_records`, `sku_assignments`.

Key gaps vs the Phase 3 roadmap target:
- No embeddings column or table on `memory_records`
- No lexical FTS5 index
- No `index_state` freshness table
- No `graph_nodes` or `graph_edges` tables
- No `artifact_store` module
- No `lifecycle_states` table (lifecycle is currently a column on each table, not a separate table)

### Phase 3 roadmap tasks (from CEREBRA_DEV_ROADMAP_v8.1.md §Phase 3)

```
1. Complete SQLite schemas: sources, documents, chunks, memory_records,
   sku_assignments, lifecycle_states, events, graph_nodes, graph_edges
2. Artifact store for normalized documents
3. Lexical index using SQLite FTS5
4. Vector index (numpy + cosine MVP)
5. Embedding generation (sentence-transformers, local)
6. Graph store (SQLite)
7. Index freshness tracking
8. Schema migration tooling (already exists; extend with new migrations)
9. Inspector events for all storage operations
```

Tasks 1 (partially), 8, and 9 (partially) are already in place. Tasks 2–7 are not started.

---

## §2. D1 — Embedding Model Decision

### Decision: mixedbread-ai/mxbai-embed-large-v1

- 1024-dimensional float32 embeddings
- Loaded via `sentence-transformers` library
- Fully local — no cloud API calls, no network dependency at inference time
- Symmetric similarity (query and document encoded the same way)
- **Matryoshka representation learning:** embeddings can be truncated to 768/512/256 dims at query or training time without re-embedding the corpus. This is the forward-training argument: when LoRA work resumes (see `docs/agent/deferred/v02_lora_track.md`), the same stored embeddings can be used at reduced dimensionality as a training signal or retrieval auxiliary without incurring a full re-embed pass. bge-base-en-v1.5 does not support Matryoshka truncation; mxbai-embed-large-v1 does.

### 2.1 Model Loading Pattern

**Lazy-load, single instance, module-level sentinel.**

```python
# cerebra/storage/embeddings.py
from __future__ import annotations
from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODEL_NAME = "mixedbread-ai/mxbai-embed-large-v1"
_model: "SentenceTransformer | None" = None

def _get_model() -> "SentenceTransformer":
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model

def embed(texts: list[str]) -> np.ndarray:
    """Return float32 array of shape (N, 1024)."""
    return _get_model().encode(texts, normalize_embeddings=True).astype(np.float32)
```

**Rationale:** sentence-transformers takes ~300ms to load the first time. Lazy-loading means tests and CLI commands that don't touch embeddings pay zero cost. A module-level sentinel means the model is loaded at most once per process. No singleton class, no DI container — this is a one-process CLI tool.

### 2.2 Storage Format: Separate `embeddings` Table

**Decision: separate `embeddings` table, not a BLOB column on `memory_records`.**

```sql
CREATE TABLE embeddings (
    embedding_id       TEXT     PRIMARY KEY,
    record_id          TEXT     NOT NULL REFERENCES memory_records(record_id),
    embedding_model    TEXT     NOT NULL,   -- "mixedbread-ai/mxbai-embed-large-v1"
    model_version      TEXT     NOT NULL,   -- revision hash or short version string
    vector_bytes       BLOB     NOT NULL,   -- float32 LE, 1024 dims = 4096 bytes
    dimensions         INTEGER  NOT NULL,   -- 1024
    -- Reserved for future LoRA training: secondary embedding alongside primary.
    -- Populating these is deferred; columns reserved now to avoid a costly ALTER
    -- TABLE on a large embeddings table.
    embedding_alt      BLOB     NULL,
    embedding_alt_model TEXT    NULL,
    embedding_alt_dim  INTEGER  NULL,
    created_at         INTEGER  NOT NULL,
    schema_version     INTEGER  NOT NULL DEFAULT 1,
    UNIQUE (record_id, embedding_model, model_version)
);

CREATE INDEX IF NOT EXISTS idx_emb_record ON embeddings(record_id);
CREATE INDEX IF NOT EXISTS idx_emb_model  ON embeddings(embedding_model, model_version);
```

**Rationale vs BLOB on `memory_records`:**
- A BLOB column on `memory_records` bloats every `SELECT *` that doesn't need embeddings — the ingest pipeline, the SKU classifier, the lifecycle manager. These all query memory_records heavily and would pay the BLOB transfer cost for no reason.
- The separate table makes model migration explicit: future-model rows coexist with mxbai rows during a re-embedding pass. A BLOB column can only hold one embedding per record and requires an in-place UPDATE, which is harder to roll back.
- The UNIQUE constraint on `(record_id, embedding_model, model_version)` prevents duplicate embeddings naturally.
- The main downside is one extra JOIN for retrieval — acceptable at 745 records, acceptable at 10k records, acceptable at 100k records (vector search is bounded at 200 candidates by the retrieval architecture).

**Serialization:** `np.ndarray.astype(np.float32).tobytes()` → BLOB. Round-trip: `np.frombuffer(blob, dtype=np.float32)`. No additional library needed.

### 2.3 Embedding Model Versioning

The `embedding_model` and `model_version` columns on the `embeddings` table are the version record. Every embedding row knows which model produced it.

**`model_version` value:** use the sentence-transformers model card revision hash when available; fall back to the model's short name version string (e.g., `"v1"`). Record at embed time so the exact checkpoint is traceable. For `mxbai-embed-large-v1`, the expected value is `"v1"` until a revision hash is known.

**Freshness detection:** a `memory_records` row has a stale embedding when:
1. No row exists in `embeddings` for that `record_id`, OR
2. The row's `embedding_model` or `model_version` doesn't match the currently configured model.

The `index_state` table (§3) tracks this at the vault level, not per-record. Per-record staleness is queried via the JOIN.

### 2.4 Upgrade Path

| Stage | When | Mechanism |
|-------|------|-----------|
| **v0.1 — numpy + cosine** | Now, through ~10k records | `np.dot(query_vec, candidate_vecs.T)` over the full embeddings table. Loaded entirely into memory at query time. |
| **turbovec** | ~10k records | Drop-in replacement for the cosine scan. Same BLOB format, same table schema, faster SIMD scan. No schema migration needed. |
| **qdrant/lancedb** | Multi-vault federation OR >100k records per vault | Schema migration: add an `external_index_id` column on `embeddings` table; the external index stores the vector by `embedding_id`. The BLOB column becomes optional (can be retained as backup or dropped). No data loss — all embeddings already serialized. |

**Model swap procedure (mxbai-embed-large-v1 → future-model):**
1. Update `_MODEL_NAME` and `model_version` in `embeddings.py`.
2. Run `cerebra reembed --model <new-model>` — this inserts new rows in `embeddings` for all active records with the new model/version, leaving old rows in place.
3. Update `index_state` to point to the new model version as current.
4. Old rows remain queryable for audit; a cleanup pass can delete them after validation.
5. No record is left unembedded mid-migration — the old embeddings remain valid for retrieval until the new ones are confirmed.

---

## §3. D2 — Index Freshness Mechanics

### 3.1 Index Freshness Table

```sql
CREATE TABLE index_state (
    index_name       TEXT     PRIMARY KEY,   -- 'lexical', 'vector', 'graph'
    last_updated_at  INTEGER  NOT NULL,
    record_count     INTEGER  NOT NULL DEFAULT 0,
    model_name       TEXT,                   -- for vector: "mixedbread-ai/mxbai-embed-large-v1"
    model_version    TEXT,                   -- for vector: model_version string
    is_building      INTEGER  NOT NULL DEFAULT 0,  -- 1 = rebuild in progress
    schema_version   INTEGER  NOT NULL DEFAULT 1
);
```

Populated at vault init with rows for `'lexical'`, `'vector'`, `'graph'`. `last_updated_at = 0` means never built.

### 3.2 When Is a Record "Out of Date"?

**Lexical index:** a record is out of date when `memory_records.created_at > index_state.last_updated_at` for the lexical row, OR when a record's `lifecycle_state` changed since `last_updated_at`. FTS5 does not auto-sync with the base table — any write to `memory_records` that isn't reflected in the FTS5 virtual table is a staleness.

**Vector index:** a record is out of date when:
- No `embeddings` row exists for that `record_id` with the current `model_name`+`model_version`, OR
- The record's `lifecycle_state` is `active` but the embedding predates a model swap (detected via `model_version` mismatch against `index_state.model_version`)

**Graph index:** a record is out of date when:
- No `graph_nodes` row of type `MemoryRecord` exists with `entity_id = record_id`, OR
- The record's `sku_address` changed since the corresponding node was last written (future concern; track via `sku_assigned_at > graph_node.created_at`)

### 3.3 Freshness Detection Strategy: Event-Driven via Inspector Events

**Decision: event-driven, not polled.**

**Rationale:**
- Timestamp polling requires scanning `memory_records` to find rows newer than `index_state.last_updated_at`. At 745 records this is trivial; at 100k records it's a full table scan on every freshness check.
- Transactional foreign-key cascades would require triggers, which SQLite supports but which are notoriously hard to debug and test. Triggers also fire silently — no inspector event, no visibility.
- Event-driven: every write path that creates or modifies a `memory_records` row already emits an inspector event (`MemoryRecordCreated`, `MemoryActivated`, `MemoryTombstoned`, etc.). The index updater subscribes to these events and marks the affected index as needing an update.

**Concrete mechanism (MVP):**
- After each ingest batch completes, the pipeline calls `update_lexical_index(new_record_ids)` and `schedule_embedding(new_record_ids)`.
- `schedule_embedding` inserts rows into a `pending_embeddings` queue table (see below).
- Graph nodes are written synchronously during ingestion (lightweight operation).
- `index_state` is updated after each batch completes.

**`pending_embeddings` queue table:**

```sql
CREATE TABLE pending_embeddings (
    record_id    TEXT     PRIMARY KEY REFERENCES memory_records(record_id),
    queued_at    INTEGER  NOT NULL,
    attempt      INTEGER  NOT NULL DEFAULT 0
);
```

Records land here when they need embedding. A background step (or the next `cerebra ingest` call) drains the queue. This decouples the slow embedding generation from the ingest pipeline and makes re-embedding after a model swap trivially expressible: `INSERT OR IGNORE INTO pending_embeddings SELECT record_id, <now>, 0 FROM memory_records WHERE lifecycle_state = 'active'`.

### 3.4 Embedding Model Version Migration Procedure

When switching from `mxbai-embed-large-v1` to a future model:

```
1. Update embeddings.py: _MODEL_NAME and model_version constant.
2. Queue all active records: INSERT OR IGNORE INTO pending_embeddings ...
3. Run embedding drain: cerebra reembed (or next ingest run with --reembed flag).
4. Validate: count(embeddings WHERE model_version = new_version) == count(active memory_records)
5. Update index_state SET model_name = new, model_version = new.
6. Old embeddings table rows remain; clean up with: DELETE FROM embeddings WHERE model_version = old_version (after validation window).
```

No data is lost during the transition. Retrieval uses whichever embedding version is current in `index_state`. Mid-migration, records with only old-version embeddings fall back to lexical-only retrieval (acceptable for a solo vault during a manual upgrade window).

---

## §4. D3 — Graph Store Schema

### Design Principles

- Polymorphic node/edge tables with a `node_type` / `edge_type` discriminator
- JSON payload column (`payload_json`) for type-specific fields
- Foreign keys connecting to `memory_records`, `sku_assignments`, `sources`
- All 16 D4 relationship types from CEREBRA_SKU_ADDRESSING.md §6 present as edge type values
- Provenance edges as first-class citizens: every node references the inspector event that created it (`origin_event_id`)
- Indexes for: 1-hop neighbor lookup (both directions), sibling pointer traversal, parent/child walks, type-filtered traversal

### 4.1 `graph_nodes` Table

```sql
CREATE TABLE graph_nodes (
    node_id         TEXT     PRIMARY KEY,
    node_type       TEXT     NOT NULL,   -- discriminator; see §4.3
    label           TEXT     NOT NULL,   -- human-readable name/title
    entity_id       TEXT,               -- FK to the underlying entity (nullable)
    entity_table    TEXT,               -- 'memory_records' | 'sources' | 'sku_assignments' | NULL
    sku_address     TEXT,               -- denormalized for fast SKU-graph joins
    lifecycle_state TEXT     NOT NULL DEFAULT 'active',
    origin_event_id TEXT,               -- inspector_events.event_id that created this node (soft ref)
    payload_json    TEXT     NOT NULL DEFAULT '{}',
    created_at      INTEGER  NOT NULL,
    updated_at      INTEGER  NOT NULL,  -- set to created_at on insert; updated application-side on any change
    schema_version  INTEGER  NOT NULL DEFAULT 1
);

-- Lookup by underlying entity (e.g., "give me the node for memory_record X")
CREATE INDEX IF NOT EXISTS idx_gn_entity
    ON graph_nodes(entity_id, entity_table);

-- Type-filtered traversal (single-column; used for node_type-only queries)
CREATE INDEX IF NOT EXISTS idx_gn_type
    ON graph_nodes(node_type);

-- Type + lifecycle compound (used in most real queries: "give me active MemoryRecord nodes")
CREATE INDEX IF NOT EXISTS idx_gn_type_state
    ON graph_nodes(node_type, lifecycle_state);

-- SKU-graph join
CREATE INDEX IF NOT EXISTS idx_gn_sku
    ON graph_nodes(sku_address);

-- Lifecycle filter
CREATE INDEX IF NOT EXISTS idx_gn_state
    ON graph_nodes(lifecycle_state);

-- Time-ordered node listing (inspector queries, debugging)
CREATE INDEX IF NOT EXISTS idx_gn_created
    ON graph_nodes(created_at);
```

### 4.2 `graph_edges` Table

```sql
CREATE TABLE graph_edges (
    edge_id         TEXT     PRIMARY KEY,
    edge_type       TEXT     NOT NULL,   -- discriminator; see §4.4
    -- ON DELETE RESTRICT: graph cleanup is lifecycle-state-driven, never hard-delete.
    -- Tombstoned nodes are retained indefinitely for audit and future training utility.
    -- Attempting to DELETE a graph_nodes row with live edges will fail at the DB layer.
    source_node_id  TEXT     NOT NULL REFERENCES graph_nodes(node_id) ON DELETE RESTRICT,
    target_node_id  TEXT     NOT NULL REFERENCES graph_nodes(node_id) ON DELETE RESTRICT,
    confidence      REAL     NOT NULL DEFAULT 1.0,
    weight          REAL     NOT NULL DEFAULT 1.0,
    evidence        TEXT,               -- brief rationale or source citation
    created_by      TEXT     NOT NULL,  -- 'ingest_pipeline' | 'sku_classifier' | 'consolidation' | 'user'
    origin_event_id TEXT,               -- inspector_events.event_id (soft ref)
    lifecycle_state TEXT     NOT NULL DEFAULT 'active',
    payload_json    TEXT     NOT NULL DEFAULT '{}',
    created_at      INTEGER  NOT NULL,
    updated_at      INTEGER  NOT NULL,  -- set to created_at on insert; updated application-side on any change
    schema_version  INTEGER  NOT NULL DEFAULT 1
);

-- 1-hop outbound neighbors from a node
CREATE INDEX IF NOT EXISTS idx_ge_source
    ON graph_edges(source_node_id, edge_type, lifecycle_state);

-- 1-hop inbound neighbors to a node
CREATE INDEX IF NOT EXISTS idx_ge_target
    ON graph_edges(target_node_id, edge_type, lifecycle_state);

-- Type-filtered traversal
CREATE INDEX IF NOT EXISTS idx_ge_type
    ON graph_edges(edge_type, lifecycle_state);

-- Sibling pointer traversal: source_node → all sibling targets
CREATE INDEX IF NOT EXISTS idx_ge_sibling
    ON graph_edges(source_node_id, target_node_id);

-- Time-ordered edge listing (inspector queries, debugging)
CREATE INDEX IF NOT EXISTS idx_ge_created
    ON graph_edges(created_at);
```

### 4.3 Node Type Vocabulary

From CEREBRA_GRAPH_MODEL.md §4, in Phase 3 scope:

| `node_type` | `entity_table` | Phase | Notes |
|-------------|----------------|-------|-------|
| `Source` | `sources` | P3 | One per ingested file |
| `Document` | `documents` | P3 | Parsed/normalized form of source |
| `Chunk` | `chunks` | P3 | Sub-document division |
| `MemoryRecord` | `memory_records` | P3 | Primary cognitive unit |
| `Summary` | `memory_records` | P10 | Consolidation output; same table, different `record_type` |
| `Entity` | NULL | P4+ | Extracted person/project/tool; no FK to a single table |
| `Topic` | NULL | P4+ | Emergent cluster |
| `Project` | NULL | P4+ | Bounded project boundary |
| `RelationshipClaim` | NULL | P4+ | Explicit relationship assertion |
| `ContextPacket` | NULL | P4 | Retrieval output artifact |
| `Decision` | NULL | P8 | Strategic or catalyst decision; session-scoped |
| `ArchivePackage` | NULL | P11 | Lifecycle archival bundle |
| `ScoutReport` | NULL | deferred | Policy Scout integration |

**Note on `updated_at`:** both `graph_nodes` and `graph_edges` carry `updated_at`. There is no SQLite trigger for this; the application is responsible for setting `updated_at = created_at` on insert and updating it on any subsequent write to that row. This is deliberate: SQLite triggers are extra complexity for a single-writer system, add invisible state changes that don't emit inspector events, and are harder to test. Application-level discipline is auditable; trigger-level updates are not.

**Phase 3 ships:** `Source`, `Document`, `Chunk`, `MemoryRecord` only. Other types are valid `node_type` values from day one (no schema migration needed to add them later), but no writer code exists until the relevant phase lands.

### 4.4 Edge Type Vocabulary

Two families: **structural edges** (provenance/containment) and **semantic edges** (SKU D4 relationship types).

**Structural edges:**

Verified against CEREBRA_GRAPH_MODEL.md §5. The amendment list adds 4 new names (REFERENCES, INVALIDATES, ENABLES, BLOCKS) not in the graph model doc. Two amendment names were synonyms for existing types and have been resolved to the canonical graph-model names: DUPLICATE_OF → `DUPLICATES`, MEMBER_OF → `BELONGS_TO`. All are valid `edge_type` values from day one; the "Source" column notes lineage for future readers.

| `edge_type` | Meaning | Example | Phase | Source |
|-------------|---------|---------|-------|--------|
| `CONTAINS` | Parent contains child | Source → Document | P3 | Both |
| `DERIVED_FROM` | Record derived from chunk | MemoryRecord → Chunk | P3 | Both |
| `SUMMARIZES` | Summary covers records | Summary → MemoryRecord | P10 | Both |
| `CONTRADICTS` | Epistemic conflict | MemoryRecord ↔ MemoryRecord | P4+ | Both |
| `SUPPORTS` | Epistemic support | MemoryRecord → MemoryRecord | P4+ | Both |
| `UPDATES` | Newer version of | MemoryRecord → MemoryRecord | P10 | Both |
| `BELONGS_TO` | Scope/collection membership | MemoryRecord → Project/Topic | P4+ | Both |
| `RELATED_TO` | Weak semantic relationship | MemoryRecord ↔ MemoryRecord | P4+ | Both |
| `ARCHIVED_AS` | Archived copy | MemoryRecord → ArchivePackage | P11 | Both |
| `DUPLICATES` | Near-duplicate pair | MemoryRecord → MemoryRecord | P10 | Graph model |
| `MENTIONS` | Soft named-entity reference | MemoryRecord → Entity | P4+ | Graph model |
| `SUPERSEDES` | Full replacement | MemoryRecord → MemoryRecord | P10 | Graph model |
| `PART_OF` | Compositional part | Chunk → Document | P3 | Graph model |
| `USED_IN_CONTEXT` | Contributed to context packet | MemoryRecord → ContextPacket | P4 | Graph model |
| `RESTORED_FROM` | Restored from archive | MemoryRecord → ArchivePackage | P11 | Graph model |
| `REFERENCES` | Explicit reference/citation | MemoryRecord → MemoryRecord | P4+ | Amendment |
| `INVALIDATES` | Supersedes or refutes | MemoryRecord → MemoryRecord | P4+ | Amendment |
| `ENABLES` | Capability dependency (structural) | Tool → Workflow | P4+ | Amendment (distinct from SKU_ENABLES which is a D4 semantic edge between memory records) |
| `BLOCKS` | Capability constraint | Constraint → Action | P4+ | Amendment |

**Note on ENABLES vs SKU_ENABLES:** `ENABLES` (structural) connects system entities (tools, workflows, capabilities). `SKU_ENABLES` (semantic) connects memory records at the D4 axis — it represents how the content of one memory enables the content of another. They are orthogonal and will never be confused in practice because structural edges connect node types like Tool/Project/Constraint, while SKU semantic edges connect MemoryRecord nodes.

**Semantic edges (D4 relationship types from SKU_ADDRESSING.md §6)**:

| `edge_type` | D4 hex | Family |
|-------------|--------|--------|
| `SKU_ANALOGY` | 0x0 | Comparative |
| `SKU_CONTRAST` | 0x1 | Comparative |
| `SKU_UNIFICATION` | 0x2 | Comparative |
| `SKU_TENSION` | 0x3 | Comparative |
| `SKU_ENABLES` | 0x4 | Causal |
| `SKU_PREVENTS` | 0x5 | Causal |
| `SKU_EMERGES_FROM` | 0x6 | Causal |
| `SKU_TRANSFORMS` | 0x7 | Causal |
| `SKU_CONTAINS` | 0x8 | Compositional |
| `SKU_PART_OF` | 0x9 | Compositional |
| `SKU_COMPOSES` | 0xA | Compositional |
| `SKU_DECOMPOSES` | 0xB | Compositional |
| `SKU_APPLIES_TO` | 0xC | Operational |
| `SKU_CRITIQUES` | 0xD | Operational |
| `SKU_SERVES` | 0xE | Operational |
| `SKU_DERIVES_FROM` | 0xF | Operational |

All 16 D4 types are present as valid `edge_type` values from day one. In Phase 3, no writer produces them yet (D4 semantic edge inference belongs to Phase 4+ retrieval). The schema accepts them so Phase 4 code can write them without a migration.

### 4.5 Example Rows

**Source node:**
```
node_id:      'gn_src_a1b2c3'
node_type:    'Source'
label:        'docs/refined-runtime-model/CEREBRA_SKU_ADDRESSING.md'
entity_id:    'src_4f8e...'          -- sources.source_id
entity_table: 'sources'
sku_address:  NULL                   -- sources don't get SKU addresses
lifecycle_state: 'active'
origin_event_id: 'evt_abc123'        -- SourceRegistered event
payload_json: '{"canonical_path": "docs/...", "detected_type": "markdown"}'
created_at:   1749484000
updated_at:   1749484000
```

**MemoryRecord node:**
```
node_id:      'gn_rec_d4e5f6'
node_type:    'MemoryRecord'
label:        'CEREBRA_SKU_ADDRESSING.md §6 relationship axis'
entity_id:    'rec_9a1b...'          -- memory_records.record_id
entity_table: 'memory_records'
sku_address:  '0x8F4000.00.82'
lifecycle_state: 'active'
origin_event_id: 'evt_def456'        -- MemoryRecordCreated event
payload_json: '{"token_estimate": 412, "d1": 8, "d1_name": "NORMATIVE"}'
created_at:   1749484100
updated_at:   1749484100
```

**Structural CONTAINS edge (Source → Document):**
```
edge_id:        'ge_cont_001'
edge_type:      'CONTAINS'
source_node_id: 'gn_src_a1b2c3'
target_node_id: 'gn_doc_b2c3d4'
confidence:     1.0
weight:         1.0
evidence:       'ingest: source contains document'
created_by:     'ingest_pipeline'
origin_event_id: 'evt_abc123'
lifecycle_state: 'active'
payload_json:   '{}'
created_at:     1749484000
updated_at:     1749484000
```

**Structural DERIVED_FROM edge (MemoryRecord → Chunk):**
```
edge_id:        'ge_drv_002'
edge_type:      'DERIVED_FROM'
source_node_id: 'gn_rec_d4e5f6'
target_node_id: 'gn_chk_c3d4e5'
confidence:     1.0
weight:         1.0
evidence:       'ingest: record derived from chunk_index=3'
created_by:     'ingest_pipeline'
origin_event_id: 'evt_def456'
lifecycle_state: 'active'
payload_json:   '{"chunk_index": 3, "heading_path": "§6 Relationship Axis"}'
created_at:     1749484100
updated_at:     1749484100
```

**Semantic SKU_ENABLES edge (future Phase 4 example — not written in Phase 3):**
```
edge_id:        'ge_sku_003'
edge_type:      'SKU_ENABLES'
source_node_id: 'gn_rec_d4e5f6'    -- MECHANISM memory
target_node_id: 'gn_rec_e5f6a7'    -- PRINCIPLE memory
confidence:     0.84
weight:         0.84
evidence:       'sku_classifier: D4=0x4 (enables); d2=MECHANISM, d3=PRINCIPLE'
created_by:     'sku_classifier'
origin_event_id: 'evt_ghi789'
lifecycle_state: 'active'
payload_json:   '{"d4": 4, "d4_name": "enables", "classifier_version": "2.0.0"}'
created_at:     1749490000
updated_at:     1749490000
```

**Decision node (future Phase 8 example — not written in Phase 3):**
```
node_id:      'gn_dec_f7g8h9'
node_type:    'Decision'
label:        'bench v0.2 LoRA training track'
entity_id:    NULL
entity_table: NULL
sku_address:  NULL
lifecycle_state: 'active'
origin_event_id: 'evt_jkl012'      -- CatalystSelectionMade event
payload_json: '{"decision_type": "strategic", "session_id": "sess_xyz", "rationale": "corpus imbalance blocks progress"}'
created_at:   1749494000
updated_at:   1749494000
```

### 4.6 Inspector Events Covered by Graph Schema

The 30-event vocabulary from CEREBRA_INSPECTOR.md maps to graph operations as follows. Phase 3 ships the storage primitives for all of these; the writer code lands per-phase as each subsystem is built.

**Phase 3 events (storage layer — written in Phase 3):**
- `GraphNodeCreated` — when ingest pipeline writes Source/Document/Chunk/MemoryRecord nodes
- `GraphEdgeCreated` — when ingest pipeline writes CONTAINS, DERIVED_FROM edges
- `GraphNodeArchived` — when lifecycle state transitions propagate to graph
- `GraphNodeTombstoned` — tombstone propagation
- `GraphExported` — export operation

**Deferred events (schema supports, writer code in later phases):**
- `GraphEdgeCreated` for semantic edges — Phase 4 (SKU D4 inference)
- `GraphNodeCreated` for Entity, Topic, ContextPacket — Phase 4+
- `GraphNodeCreated` for Summary — Phase 10 (consolidation)
- All non-graph events in §5 vocabulary — unaffected by graph schema; listed in §6 below

### 4.7 `payload_json` Shape per Node Type

The `payload_json` column is unconstrained TEXT. This table is the **convention** — not enforced by schema. Future training relies on payload shape consistency; deviation from these shapes should be treated as a bug.

| `node_type` | Expected `payload_json` keys | Notes |
|-------------|------------------------------|-------|
| `Source` | `{"canonical_path": str, "detected_type": str, "size_bytes": int}` | Mirrors `sources` table fields most useful for graph traversal |
| `Document` | `{"document_type": str, "title": str\|null, "artifact_path": str\|null}` | |
| `Chunk` | `{"chunk_index": int, "heading_path": str, "depth": int, "token_estimate": int}` | |
| `MemoryRecord` | `{"token_estimate": int, "d1": int, "d1_name": str}` | `d1`/`d1_name` added at SKU assignment time; may be absent if record not yet classified |
| `Summary` | `{"source_record_ids": [str], "summary_type": str, "token_estimate": int}` | P10 |
| `Entity` | `{"entity_type": str, "name": str, "aliases": [str]}` | P4+ |
| `Topic` | `{"name": str, "member_count": int}` | P4+ |
| `Project` | `{"name": str, "canonical_path": str\|null}` | P4+ |
| `RelationshipClaim` | `{"claim_type": str, "subject_id": str, "object_id": str, "confidence": float}` | P4+ |
| `ContextPacket` | `{"query": str, "retrieval_strategy": str, "candidate_count": int}` | P4 |
| `Decision` | `{"decision_type": str, "session_id": str, "rationale": str}` | P8 |
| `ArchivePackage` | `{"archived_record_ids": [str], "archive_reason": str}` | P11 |

**Note:** edge `payload_json` conventions follow the same principle. The two most common structural edges:
- `CONTAINS` / `DERIVED_FROM` / `PART_OF`: `{}` (no extra payload needed; the edge itself is the claim)
- `DUPLICATES`: `{"similarity_score": float, "detection_method": str}`
- `SKU_*` edges: `{"d4": int, "d4_name": str, "classifier_version": str}`

---

## §5. Module Structure

Proposed file layout for the Phase 3 storage layer. Extends the existing `cerebra/storage/` directory.

```
cerebra/storage/
    __init__.py            existing empty stub → expose public API
    db.py                  existing — no changes
    migrations.py          existing — add Migration006 (embeddings + index_state + graph tables)
    sqlite_store.py        existing — extend with embedding + graph CRUD methods
    artifact_store.py      NEW — normalized document storage on disk
    lexical.py             NEW — FTS5 index: build, update, search
    embeddings.py          NEW — embed(), model loading, pending queue drain
    index_state.py         NEW — freshness tracking: is_stale(), mark_updated()
    graph_store.py         NEW — graph_nodes + graph_edges CRUD, neighbor queries
```

### Module responsibilities

**`artifact_store.py`**  
Writes normalized document content to `<vault>/artifacts/<document_id>.txt`. No SQLite involvement — pure filesystem. Idempotent: skip if file already exists with matching hash. Inspector event: `DocumentArtifactWritten` (new event, see §6).

**`lexical.py`**  
- `build_fts_index(db_path)` — creates `memory_records_fts` FTS5 virtual table as a content table over `memory_records(content)`.
- `update_fts_index(db_path, record_ids)` — inserts/replaces rows in FTS5 table for specific records.
- `search(db_path, query, limit)` → list of `(record_id, rank)` — FTS5 `MATCH` query with BM25 ranking.
- FTS5 content table approach: avoids duplicating content; reads from `memory_records` on demand.

**`embeddings.py`**  
- `embed(texts)` — calls model, returns float32 ndarray.
- `drain_pending(db_path)` — reads `pending_embeddings` queue, generates embeddings, inserts into `embeddings` table, removes from queue. Batch size configurable (default 32 for memory safety).
- `cosine_search(db_path, query_vec, limit, model_name, model_version)` → list of `(record_id, score)`.

**`index_state.py`**  
- `is_stale(db_path, index_name)` → bool.
- `mark_updated(db_path, index_name, record_count)` — updates `last_updated_at` + record_count.
- `get_state(db_path, index_name)` → dict.

**`graph_store.py`**  
- `upsert_node(db_path, node)` → `node_id`.
- `upsert_edge(db_path, edge)` → `edge_id`.
- `get_node_for_entity(db_path, entity_id, entity_table)` → node dict or None.
- `get_neighbors(db_path, node_id, direction, edge_type_filter, lifecycle_filter)` → list of node dicts.
- `get_1hop(db_path, node_id)` → `{outbound: [...], inbound: [...]}`.
- `get_sibling_targets(db_path, node_id)` → list of node_ids (follows all edges from node).
- `walk_parent_chain(db_path, node_id)` → list of nodes from node up to root.

---

## §6. Inspector Events — New Storage-Layer Events

These events don't exist yet. They belong to the storage layer and should be added in Phase 3. Each extends the existing `InspectorEvent` envelope (§4 of CEREBRA_INSPECTOR.md).

### `EmbeddingGenerated`
```json
{
  "event_type": "EmbeddingGenerated",
  "actor": "embeddings",
  "data": {
    "record_id": "rec_...",
    "embedding_id": "emb_...",
    "model_name": "mixedbread-ai/mxbai-embed-large-v1",
    "model_version": "v1",
    "dimensions": 1024,
    "latency_ms": 42
  }
}
```

### `LexicalIndexUpdated`
```json
{
  "event_type": "LexicalIndexUpdated",
  "actor": "lexical",
  "data": {
    "records_indexed": 47,
    "total_records_in_index": 745,
    "duration_ms": 120
  }
}
```

### `VectorIndexUpdated`
```json
{
  "event_type": "VectorIndexUpdated",
  "actor": "embeddings",
  "data": {
    "records_embedded": 47,
    "total_records_with_embeddings": 745,
    "model_name": "mixedbread-ai/mxbai-embed-large-v1",
    "model_version": "v1",
    "duration_ms": 8400
  }
}
```

### `GraphNodeCreated`
Already in CEREBRA_INSPECTOR.md §5.9. Data schema:
```json
{
  "event_type": "GraphNodeCreated",
  "actor": "graph_store",
  "data": {
    "node_id": "gn_...",
    "node_type": "MemoryRecord",
    "entity_id": "rec_...",
    "entity_table": "memory_records"
  }
}
```

### `GraphEdgeCreated`
Already in CEREBRA_INSPECTOR.md §5.9. Data schema:
```json
{
  "event_type": "GraphEdgeCreated",
  "actor": "graph_store",
  "data": {
    "edge_id": "ge_...",
    "edge_type": "CONTAINS",
    "source_node_id": "gn_...",
    "target_node_id": "gn_...",
    "confidence": 1.0,
    "weight": 1.0
  }
}
```

**Note:** `confidence` and `weight` are **required** in this event payload even when their value is `1.0`. Edge confidence is a primary signal for future training; default-1.0 values must be inspectable in the event stream rather than absent.

### `GraphNodeArchived` / `GraphNodeTombstoned`
```json
{
  "event_type": "GraphNodeArchived",
  "actor": "graph_store",
  "data": {
    "node_id": "gn_...",
    "node_type": "MemoryRecord",
    "entity_id": "rec_...",
    "reason": "lifecycle_transition"
  }
}
```

### `DocumentArtifactWritten`
```json
{
  "event_type": "DocumentArtifactWritten",
  "actor": "artifact_store",
  "data": {
    "document_id": "doc_...",
    "artifact_path": "artifacts/doc_....txt",
    "size_bytes": 14200
  }
}
```

### `IndexStalenessDetected`
```json
{
  "event_type": "IndexStalenessDetected",
  "actor": "index_state",
  "data": {
    "index_name": "vector",
    "stale_record_count": 47,
    "reason": "new_records_since_last_update"
  }
}
```

---

## §7. Open Questions and Risks

These are genuine uncertainties. Better to surface now than discover mid-implementation.

**Q1: FTS5 content table vs external content table**  
Using a content table (`CREATE VIRTUAL TABLE ... USING fts5(content="memory_records", content_rowid="rowid", ...)`) means FTS5 doesn't copy content — it reads from `memory_records` at query time. This is the right default for a single-writer vault. However, SQLite FTS5 content tables require explicit `INSERT` into the FTS table on every base-table insert (no auto-sync). The ingest pipeline must call `UPDATE memory_records_fts SET ... WHERE rowid = ...` after every batch. If this is missed, the FTS index silently drifts. Risk: medium. Mitigation: `update_fts_index` is the only write path into the FTS table; tests must verify drift detection.

**Q2: `pending_embeddings` queue and concurrency**  
The queue approach assumes a single writer/drainer process. If `cerebra ingest` and `cerebra reembed` run concurrently (e.g., from two terminals), they could double-embed. At v0.1 (single developer, CLI tool), this is acceptable. The UNIQUE constraint on `embeddings(record_id, embedding_model, model_version)` prevents duplicate rows; a concurrent drainer would get a constraint violation, not silent corruption. Risk: low for v0.1.

**Mitigation — CLI lockfile:** any write-path CLI invocation (`ingest`, `reembed`, `archive`, `tombstone`) acquires a lockfile at `<vault>/.cerebra.lock` before touching the database. If the lock file already exists, the command exits immediately with a clear error: `"Another cerebra process is running. If this is stale, delete <vault>/.cerebra.lock"`. Released on clean exit; a stale lock from a crashed process requires manual deletion. This is the simplest correct solution for a single-developer CLI tool — no inter-process signaling, no timeout logic.

**Q3: Graph node identity for tombstoned records**  
When a `memory_records` row is tombstoned, should the corresponding `graph_nodes` row be tombstoned too, or archived? The distinction matters for retrieval: tombstoned means "exclude from all normal queries"; archived means "accessible via explicit archive path." The lifecycle chapter (Phase 11) defines this, but Phase 3 writes the schema. Proposal: `graph_nodes.lifecycle_state` mirrors `memory_records.lifecycle_state` — when a record is tombstoned, its node is tombstoned. Leave the decision documented here for Phase 11 to override if needed.

**Q4: `entity_id` / `entity_table` coupling**  
The `entity_table` column names the source table as a string (`'memory_records'`, `'sources'`, etc.) rather than using a foreign key. This is deliberate — SQLite doesn't support polymorphic foreign keys. The risk is that `entity_table` values drift if table names change (unlikely given the forward-only migration discipline, but not impossible). Mitigation: define a Python enum `EntityTable` with the valid values and validate on write.

**Q5: Embedding BLOB size at scale**  
1024 dims × 4 bytes = 4096 bytes per embedding. At 745 records this is 3.0 MB. At 100k records it's ~391 MB in the `embeddings` table — still SQLite-feasible as a file, but the cosine scan loads all active embeddings into RAM. At ~50k records (~195 MB loaded) consider switching to turbovec (§2.4) before RAM becomes a constraint. The turbovec threshold is approximately 50k records regardless of dimensionality at these sizes.

**Q6: `origin_event_id` referential integrity**  
`graph_nodes.origin_event_id` and `graph_edges.origin_event_id` reference `inspector_events.event_id` but this is NOT declared as a foreign key. Reason: inspector events can be compacted/deleted per retention policy (CEREBRA_INSPECTOR.md §6.3). A foreign key would prevent event compaction from working. The `origin_event_id` is a soft reference — useful for debugging, but not enforced. Risk: low. Document the soft-reference intent in the migration comment.

**Q7: Dual staleness semantics**  
Two functions with similar names check "stale": `index_state.is_stale(name)` returns True only when `last_updated_at = 0` (never built), while `lexical.is_lexical_stale()` returns True when `MAX(record.created_at) > index.last_updated_at` (drift detected). Phase 4 will exercise the staleness API enough to clarify which semantics retrieval needs. Proposal: unify so `index_state.is_stale(name)` delegates to the index-specific drift detector when one exists, or rename one of the two so the contract is unambiguous. Don't fix in Phase 3 — surface in Phase 4 as the retrieval planner queries staleness for real.

---

## §8. Phase 3 Task Ordering

The 9 roadmap tasks have genuine dependencies. Proposed sequence:

### Step 1: Migration006 + index_state stub (day 1)

**Tasks covered:** 1 (schema), 7 (freshness table), 8 (migration tooling — extends existing)

Write `Migration006` that adds `embeddings`, `pending_embeddings`, `index_state`, `graph_nodes`, `graph_edges` tables. Implement `index_state.py` (read-only side — `is_stale`, `get_state`). No writer code yet.

**Why first:** every subsequent step depends on the schema existing. Getting the schema right and reviewed before writing any writer code eliminates refactor risk. This is the smallest possible unit that Ryan can review.

### Step 2: Graph store (day 1–2)

**Task covered:** 6 (graph store)

Implement `graph_store.py` — `upsert_node`, `upsert_edge`, neighbor queries. Write tests against an in-memory SQLite database. No integration with the ingest pipeline yet.

**Why before artifact store:** graph writes are straightforward and self-contained. Getting the graph store correct in isolation is easier than testing it through the pipeline.

### Step 3: Artifact store (day 2)

**Task covered:** 2 (artifact store)

Implement `artifact_store.py`. Simple filesystem write with idempotency check. Wire `DocumentArtifactWritten` event.

### Step 4: Lexical index (day 2–3)

**Task covered:** 3 (FTS5 lexical index)

Implement `lexical.py`. Wire `LexicalIndexUpdated` event. Tests must include a drift-detection test (insert record without updating FTS; verify `is_stale` returns True).

### Step 5: Embedding generation + vector index (day 3–4)

**Tasks covered:** 4 (vector index), 5 (embedding generation)

Implement `embeddings.py`: `embed()`, `drain_pending()`, `cosine_search()`. Wire `EmbeddingGenerated` and `VectorIndexUpdated` events. This is the slowest step (sentence-transformers model load in CI). Tests should mock the model load for unit tests; one integration test hits the real model.

### Step 6: Pipeline integration (day 4)

**Task covered:** 1 (complete schema), 9 (inspector events)

Wire graph node/edge writes and lexical index updates into the ingest pipeline (`cerebra/ingest/pipeline.py`). Queue embeddings for new records. Update `index_state` after each batch. This is the integration step that touches existing Phase 1/2 code — most likely to reveal unexpected interactions.

**Cascade halt rule applies here:** if tests fail at this step, stop and classify before patching.

### Step 7: Verify + inspector events audit (day 4)

Run full test suite. Grep for any storage operation not emitting an event. Fix gaps. This is the "done when" gate check.

---

*This is a design doc. No implementation is in this commit. Phase 3 implementation begins after Ryan's review at STOP GATE.*
