# Cerebra — Architecture

## 1. Purpose

This document defines the backend architecture for Cerebra.

Cerebra is a local-first memory and cognition runtime. It ingests source material, converts it into structured memory, supports layered retrieval, consolidates memory over time, and exports graph-ready structures.

---

## 2. High-Level Architecture

```text
Source Bank
  -> Source Registry
  -> Ingestion Router
  -> Parser Adapters
  -> Normalization Layer
  -> Chunker
  -> Memory Record Builder
  -> Index Writers
  -> Retrieval Engine
  -> ContextPacket Builder
  -> Consolidation Engine
  -> Lifecycle Manager
  -> Graph Exporter
```

---

## 3. Core Runtime Flow

```text
ingest source
  -> detect type
  -> parse source
  -> normalize content
  -> extract metadata
  -> chunk content
  -> create memory records
  -> write records
  -> update indexes
  -> update graph relationships
  -> make retrievable
```

Retrieval flow:

```text
query / agent need
  -> query planner
  -> lexical retrieval
  -> vector retrieval
  -> metadata filtering
  -> graph expansion
  -> salience scoring
  -> reranking
  -> ContextPacket assembly
  -> retrieval trace
```

Consolidation flow:

```text
memory events
  -> consolidation candidate detection
  -> cluster related memories
  -> summarize/compress
  -> resolve duplicates
  -> flag contradictions
  -> update graph relationships
  -> update lifecycle state
```

---

## 4. Major Components

### 4.1 Source Registry

Tracks known sources.

Responsibilities:

- assign source IDs
- track paths/URIs
- track source type
- track modification time
- track content hash
- track ingestion status
- track parser used
- track errors
- track provenance

Source registry is the entry point for source governance.

---

### 4.2 Ingestion Router

Chooses the correct parser/adapter.

Inputs:

- file path
- MIME/type guess
- extension
- magic bytes where available
- source hints
- user-provided override

Outputs:

- parser selection
- confidence
- fallback route

The router should preserve uncertainty.

---

### 4.3 Parser Adapters

Parser adapters convert sources into normalized documents.

Initial adapters:

```text
text
markdown
json
yaml
csv
code
pdf_text
generic_binary_stub
```

Later adapters:

```text
docx
odt
html
email
audio_transcript
image_metadata
notebook
chat_export
```

Adapters should produce structured extraction results, not directly write memory.

---

### 4.4 Normalization Layer

Normalizes parser output.

Responsibilities:

- normalize whitespace
- preserve headings
- preserve code blocks
- preserve source offsets where possible
- extract frontmatter
- classify document sections
- detect language
- detect rough document type
- assign extraction confidence

---

### 4.5 Chunker

Splits normalized content into retrievable units.

Chunking should be structure-aware.

Chunking strategies:

```text
heading-based
paragraph-based
semantic chunking
code-symbol chunking
sliding-window fallback
table-aware chunking
```

Chunks must preserve provenance.

Do not create orphan chunks with no source reference.

---

### 4.6 Memory Record Builder

Converts chunks and extracted facts into durable memory records.

A memory record may represent:

- chunk
- summary
- entity
- relationship
- project note
- conversation note
- decision
- task
- report
- contradiction
- consolidation summary

Memory records should be schema-governed.

---

### 4.7 Storage Layer

Stores durable local data.

Initial storage recommendation:

```text
SQLite for metadata, records, events, graph edges
file store for raw/normalized artifacts
vector index for embeddings
lexical index for BM25/full-text
```

Keep adapters abstract enough that storage can evolve.

---

### 4.8 Index Writers

Maintain retrieval indexes.

Indexes:

```text
lexical index
vector index
metadata index
graph index
recency/salience index
```

Index writes should be idempotent where possible.

---

### 4.9 Retrieval Engine

Runs layered retrieval.

Steps:

1. Receive query/context need.
2. Plan retrieval mode.
3. Run lexical search.
4. Run vector search.
5. Apply metadata filters.
6. Expand through graph neighborhoods.
7. Score salience.
8. Rerank.
9. Return candidates with trace.

---

### 4.10 ContextPacket Builder

Builds agent-ready context.

A ContextPacket includes:

- selected memories
- source provenance
- summaries
- graph neighborhood hints
- contradictions/uncertainties
- token budget
- retrieval trace
- excluded candidates if useful
- recommended follow-up retrieval

The ContextPacket is the main output of Cerebra for agents.

---

### 4.11 Consolidation Engine

Runs memory maintenance.

Responsibilities:

- detect duplicate memories
- summarize large clusters
- create archive summaries
- identify stale records
- flag contradictions
- promote durable insights
- update relationships
- reduce retrieval noise

Consolidation should be cautious and reversible.

---

### 4.12 Lifecycle Manager

Controls memory state.

States may include:

```text
active
warm
cold
archived
tombstoned
deleted
quarantined
```

Lifecycle changes must be logged.

Deletion should be careful and explicit.

---

### 4.13 Graph Exporter

Exports graph-ready structures for LumaWeave.

Exports:

- nodes
- edges
- clusters
- labels
- weights
- confidence
- provenance
- lifecycle state

Graph export should be derived from memory records and relationships.

---

### 4.14 Event Log

Records important memory operations.

Events:

```text
SourceRegistered
SourceParsed
MemoryRecordCreated
IndexUpdated
RetrievalPerformed
ContextPacketBuilt
ConsolidationRun
MemoryArchived
MemoryTombstoned
GraphExported
```

Events make Cerebra inspectable.

---

## 5. Storage Strategy

Cerebra should be dependency-conscious but not self-sabotaging.

Suggested v0.1:

```text
SQLite
local file artifact store
one local vector backend
one lexical/full-text strategy
```

Possible vector backends:

```text
Qdrant local
LanceDB local
SQLite vector extension later
custom flat index for tiny MVP
```

The storage layer should hide backend details behind interfaces.

---

## 6. Dependency Strategy

Use Rust where speed and safety matter most:

- file walking
- hashing
- type detection
- chunk indexing
- graph export
- hot retrieval paths later

Use Python where ecosystem matters:

- parsing adapters
- embeddings orchestration
- summarization
- experimentation
- ML/RAG prototyping

Use TypeScript later where UI/API client work matters:

- local dashboard
- LumaWeave bridge
- context viewer

Do not prematurely split into too many services.

---

## 7. Backend-First Module Map

Suggested repo layout:

```text
cerebra/
  core/
    ids.py
    events.py
    errors.py
    config.py

  sources/
    registry.py
    detector.py
    watcher.py
    hashing.py

  ingest/
    router.py
    adapters/
      text.py
      markdown.py
      json.py
      yaml.py
      csv.py
      code.py
      pdf_text.py
    normalization.py
    chunking.py

  memory/
    records.py
    schemas.py
    lifecycle.py
    consolidation.py
    salience.py

  storage/
    sqlite_store.py
    artifact_store.py
    vector_store.py
    lexical_index.py
    graph_store.py

  retrieval/
    query_planner.py
    lexical.py
    vector.py
    graph_expand.py
    reranker.py
    context_packet.py
    trace.py

  graph/
    relationships.py
    export.py
    schemas.py

  cli/
    main.py
    init.py
    ingest.py
    search.py
    context.py
    consolidate.py
    export.py

  docs/
    ...
```

---

## 8. Policy Scout Boundary

Policy Scout appears only as an optional upstream event source.

Future Cerebra adapter:

```text
ingest_policy_scout_report
ingest_policy_scout_audit_summary
```

Cerebra should not depend on Policy Scout for core operation.

---

## 9. Architecture Doctrine

Cerebra should be built around memory truth, not UI sparkle.

The backend must answer:

```text
What did we ingest?
What did we extract?
What did we store?
How do we retrieve it?
Why did this context get selected?
What is stale, duplicated, contradicted, or archived?
How can LumaWeave visualize it?
```
