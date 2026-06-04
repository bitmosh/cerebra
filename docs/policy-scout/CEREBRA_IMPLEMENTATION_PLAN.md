# Cerebra — Implementation Plan

## 1. Purpose

This document turns Cerebra's architecture into a practical implementation sequence.

Cerebra should be built backend-first.

The first implementation should prove the memory runtime spine:

```text
source -> normalized document -> chunk -> memory record -> index -> retrieval -> ContextPacket -> graph export -> lifecycle event
```

Do not start with the UI.

Do not start with a huge plugin system.

Do not start with a perfect universal parser.

---

## 2. Implementation Doctrine

Build in this order:

```text
vault -> source registry -> ingestion -> memory records -> storage -> indexes -> retrieval -> ContextPacket -> lifecycle -> consolidation -> graph export
```

Every 3-5 planning docs should point toward a prototype milestone.

The first prototype should be small enough to build quickly and strict enough to reveal architectural problems.

---

## 3. Recommended v0.1 Stack

Initial stack recommendation:

```text
Python 3.12+
SQLite
local artifact store
simple lexical search
local vector index
pytest
Typer or argparse
Pydantic or dataclasses
```

Keep dependency pressure low.

Possible later additions:

```text
Rust for hot paths
TypeScript for local UI/context viewer
Qdrant/LanceDB/SQLite-vector for vector backend
tantivy/BM25 library for lexical search
```

Do not over-split services in v0.1.

---

## 4. Initial Repository Layout

Suggested layout:

```text
cerebra/
  pyproject.toml
  README.md

  cerebra/
    __init__.py

    core/
      ids.py
      config.py
      events.py
      errors.py
      time.py

    vault/
      init.py
      paths.py
      manifest.py

    sources/
      registry.py
      detector.py
      hashing.py
      discovery.py

    ingest/
      router.py
      normalization.py
      chunking.py
      adapters/
        text.py
        markdown.py
        json_adapter.py
        yaml_adapter.py
        csv_adapter.py
        code.py

    memory/
      records.py
      schemas.py
      lifecycle.py
      salience.py
      consolidation.py

    storage/
      sqlite_store.py
      artifact_store.py
      migrations.py

    indexes/
      lexical.py
      vector.py
      metadata.py
      graph.py

    retrieval/
      query_planner.py
      hybrid.py
      graph_expand.py
      reranker.py
      trace.py
      context_packet.py

    graph/
      model.py
      export.py

    cli/
      main.py
      init.py
      ingest.py
      search.py
      context.py
      consolidate.py
      lifecycle.py
      export.py

  tests/
    test_vault.py
    test_sources.py
    test_ingestion.py
    test_chunking.py
    test_memory_records.py
    test_storage.py
    test_retrieval.py
    test_context_packet.py
    test_lifecycle.py
    test_consolidation.py
    test_graph_export.py

  docs/
    ...
```

---

## 5. Milestone 0 — Thin Prototype Gate

Before the full implementation, build a tiny spike.

Goal:

```text
ingest three markdown files
create chunks
search them
build a ContextPacket
export tiny graph JSON
```

This prototype can be rough but should validate the spine.

### Done When

- Three markdown files ingest.
- Source records are created.
- Chunks preserve provenance.
- Lexical search works.
- A simple ContextPacket is created.
- A simple graph export exists.

Confidence target after spike:

```text
Architecture confidence should rise from ~92% to 95%+.
```

---

## 6. Milestone 1 — Vault Initialization

### Goal

Create a local Cerebra vault.

Command:

```bash
cerebra init ./cerebra-vault
```

Creates:

```text
config.yaml
data/cerebra.db
artifacts/
indexes/
exports/
events/
```

### Done When

- Vault path initializes.
- Config is written.
- SQLite database is created.
- Schema version is recorded.
- Tests verify idempotent init.

---

## 7. Milestone 2 — Source Registry

### Goal

Track source files before parsing.

Tasks:

1. Discover files.
2. Hash content.
3. Create source IDs.
4. Store source metadata.
5. Detect changed/unchanged sources.

### Done When

- Sources have stable IDs.
- Duplicate content is detected.
- Modified files are detected.
- Unsupported files are recorded, not ignored silently.

---

## 8. Milestone 3 — Type Detection and Adapter Routing

### Goal

Route files to parser adapters.

Initial adapters:

```text
text
markdown
json
yaml
csv
code
```

### Done When

- File type detection returns confidence.
- Adapter routing is explicit.
- Unsupported file fallback works.
- Type detection tests pass.

---

## 9. Milestone 4 — Parser Adapters and Normalization

### Goal

Parse supported sources into normalized documents.

Tasks:

1. Implement Markdown parser.
2. Implement text parser.
3. Implement JSON/YAML parser.
4. Implement CSV parser.
5. Implement basic code parser.
6. Normalize headings/sections/content.
7. Preserve metadata.

### Done When

- Supported files produce `NormalizedDocument`.
- Metadata is extracted.
- Parser warnings/errors are stored.
- Source provenance is preserved.

---

## 10. Milestone 5 — Chunking

### Goal

Create retrievable chunks.

Chunking strategies:

```text
heading-based for Markdown
paragraph-based for text
structure-aware for JSON/YAML
row/summary-aware for CSV
symbol-ish fallback for code
```

### Done When

- Chunks have source/document IDs.
- Chunks preserve position and heading path.
- Token estimates exist.
- Chunker version is stored.
- Tests verify no orphan chunks.

---

## 11. Milestone 6 — Memory Records

### Goal

Turn chunks into durable memory records.

Initial record types:

```text
source_chunk
document_summary
project_note
entity_stub
relationship_stub
```

MVP can start with `source_chunk` and summaries.

### Done When

- Memory records link to chunks and sources.
- Records have lifecycle state.
- Records have confidence.
- Records can be retrieved by ID.

---

## 12. Milestone 7 — Storage Layer

### Goal

Persist records and artifacts.

Storage:

```text
SQLite for structured records
artifact store for normalized docs and larger outputs
```

### Done When

- Sources persist.
- Documents persist.
- Chunks persist.
- Memory records persist.
- Events persist.
- Basic migrations exist.

---

## 13. Milestone 8 — Indexing

### Goal

Make memory retrievable.

Indexes:

```text
lexical index
vector index
metadata index
basic graph index
```

MVP can begin with SQLite FTS or a simple lexical strategy and a simple local vector index.

### Done When

- Lexical index returns results.
- Vector index returns results.
- Index metadata tracks freshness.
- Index tests pass.

---

## 14. Milestone 9 — Hybrid Retrieval

### Goal

Combine lexical and vector retrieval.

Tasks:

1. Implement query planner v0.
2. Run lexical retrieval.
3. Run vector retrieval.
4. Apply metadata filters.
5. Fuse results.
6. Score salience v0.
7. Produce retrieval trace.

### Done When

- `cerebra search "query"` works.
- Results include score components.
- Retrieval trace is stored.
- Archived/tombstoned filtering works.

---

## 15. Milestone 10 — ContextPacket Builder

### Goal

Create agent-ready memory bundles.

Command:

```bash
cerebra context "Plan ingestion architecture" --project Cerebra
```

### Done When

- ContextPacket JSON is created.
- Plain text rendering is created.
- Selected records include provenance.
- Token estimate exists.
- Retrieval trace ID is attached.

---

## 16. Milestone 11 — Lifecycle Manager

### Goal

Support controlled memory state.

States for MVP:

```text
active
archived
tombstoned
deleted marker
```

### Done When

- Archive changes retrieval behavior.
- Tombstone excludes memory.
- Restore works for archive.
- Lifecycle events are logged.

---

## 17. Milestone 12 — Consolidation v0

### Goal

Start memory maintenance.

MVP consolidation:

```text
duplicate detection
document summary creation
project/topic summary creation
archive retrieval card creation
basic relationship creation
```

### Done When

- `cerebra consolidate` creates summaries.
- Summaries link to support.
- Consolidation run is logged.
- No sources are deleted.

---

## 18. Milestone 13 — Graph Export

### Goal

Export graph-ready memory.

Command:

```bash
cerebra export graph --project Cerebra --out graph.json
```

### Done When

- Nodes export.
- Edges export.
- Provenance chain exists.
- Lifecycle state included.
- JSON schema is stable enough for LumaWeave experiments.

---

## 19. Milestone 14 — Integration Prep

### Goal

Prepare for later agent and LumaWeave usage.

Tasks:

```text
document ContextPacket contract
document graph export contract
add JSON outputs
add basic CLI examples
write AGENT_HANDOFF
```

Do not build full UI yet.

---

## 20. Build Confidence Targets

```text
After prototype gate: 95% architecture confidence
After ingestion: 88-92% ingestion confidence
After retrieval: 92-95% retrieval confidence
After ContextPacket: 94% agent-context confidence
After lifecycle: 88-92% lifecycle confidence
After consolidation v0: 84-88% consolidation confidence
After graph export: 90-93% LumaWeave bridge confidence
```

---

## 21. Implementation Doctrine

The first Cerebra implementation should be small but real.

Do not build 10,000 more lines of docs before proving the spine.

Build the spine, then let test results tell us what planning was wrong.
