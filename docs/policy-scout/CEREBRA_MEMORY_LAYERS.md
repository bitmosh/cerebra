# Cerebra — Memory Layers

## 1. Purpose

This document defines Cerebra's memory layer architecture.

Cerebra should not treat memory as one flat vector database.

It should maintain multiple memory layers with different roles, retrieval methods, lifecycle behaviors, and consolidation rules.

---

## 2. Core Memory Doctrine

Memory should be:

```text
source-grounded
layered
retrievable
consolidated
graph-ready
inspectable
lifecycle-managed
```

Do not collapse memory into only embeddings.

Embeddings are one index over memory, not memory itself.

---

## 3. Memory Layer Overview

Initial memory layers:

```text
L0 Source Artifacts
L1 Normalized Documents
L2 Chunks
L3 Memory Records
L4 Derived Summaries
L5 Relationship Graph
L6 ContextPackets
L7 Consolidated Long Memory
L8 Archive / Tombstone Layer
```

---

## 4. L0 — Source Artifacts

Raw or referenced source material.

Examples:

- original file path
- content hash
- raw text copy if configured
- parser metadata
- file stats
- source provenance

Purpose:

```text
Preserve where memory came from.
```

Important fields:

```text
source_id
uri/path
content_hash
source_type
created_at
modified_at
ingested_at
parser_status
```

---

## 5. L1 — Normalized Documents

Parser output after normalization.

Examples:

- Markdown with normalized headings
- extracted PDF text
- JSON flattened/explained structure
- code file with symbol hints
- CSV summary plus rows metadata

Purpose:

```text
Create a stable representation for chunking and extraction.
```

---

## 6. L2 — Chunks

Retrievable content units.

Chunk types:

```text
heading_chunk
paragraph_chunk
code_symbol_chunk
table_chunk
semantic_chunk
sliding_window_chunk
```

Each chunk must know:

```text
source_id
document_id
chunk_id
position
heading path
content
token estimate
extraction confidence
```

Chunks are retrieval candidates.

---

## 7. L3 — Memory Records

Structured memory records created from chunks and extraction.

Types:

```text
source_chunk
fact
note
decision
entity
relationship
task
project_context
conversation_context
report_summary
contradiction
question_answer
```

Memory records are the main durable objects.

A record can point back to one or more chunks/sources.

---

## 8. L4 — Derived Summaries

Summaries created from records or clusters.

Summary types:

```text
document_summary
topic_summary
project_summary
session_summary
entity_summary
archive_summary
incident_summary
```

Summaries should preserve links to supporting records.

Summaries are not replacements for sources.

---

## 9. L5 — Relationship Graph

Graph edges between records, entities, topics, sources, projects, and summaries.

Relationship types:

```text
mentions
supports
contradicts
duplicates
updates
belongs_to
derived_from
related_to
caused_by
used_by
part_of
```

Each relationship should carry:

```text
confidence
evidence
created_by
created_at
```

---

## 10. L6 — ContextPackets

Agent-ready bundles of selected memory.

A ContextPacket includes:

- query/task
- selected memory records
- supporting summaries
- source references
- graph neighborhood
- uncertainty notes
- token budget
- retrieval trace

ContextPackets should be stored, at least optionally, so users can inspect what an agent saw.

---

## 11. L7 — Consolidated Long Memory

Stable memory created by consolidation.

Examples:

- "User prefers local-first architecture."
- "Project LumaWeave is the graph visualization layer."
- "Policy Scout is separate from Cerebra."
- "Echoes of the Glade plants are aesthetic only."

Consolidated memory must be provenance-aware.

It should know what sources support it.

---

## 12. L8 — Archive / Tombstone Layer

Lifecycle layer for old, stale, deleted, or intentionally suppressed memory.

States:

```text
active
warm
cold
archived
tombstoned
deleted
quarantined
```

Archive summaries can preserve usefulness without keeping everything hot.

Tombstones prevent deleted/suppressed memory from reappearing accidentally.

---

## 13. Retrieval by Layer

Different layers support different retrieval.

| Layer | Retrieval Method |
|---|---|
| L0 Source Artifacts | metadata/path/hash |
| L1 Normalized Documents | lexical/metadata |
| L2 Chunks | lexical/vector |
| L3 Memory Records | hybrid/metadata/salience |
| L4 Summaries | vector/semantic/topic |
| L5 Graph | neighborhood expansion |
| L6 ContextPackets | task/session lookup |
| L7 Consolidated Long Memory | high-salience retrieval |
| L8 Archive/Tombstone | explicit/archive-aware retrieval |

---

## 14. Layer Interactions

Typical retrieval path:

```text
query
  -> L3 memory records
  -> L2 supporting chunks
  -> L4 summaries
  -> L5 graph expansion
  -> L7 consolidated memory
  -> ContextPacket
```

Archive path:

```text
low-access records
  -> summarize cluster
  -> create archive summary
  -> move raw records to cold/archive state
  -> keep graph pointer
```

Tombstone path:

```text
user deletes/suppresses memory
  -> mark tombstone
  -> remove from normal retrieval
  -> preserve deletion marker
```

---

## 15. Memory Layer Doctrine

Cerebra's strength comes from not flattening memory.

Raw sources, chunks, records, summaries, graph relationships, context packets, and archives each have different jobs.

Treat them differently.
