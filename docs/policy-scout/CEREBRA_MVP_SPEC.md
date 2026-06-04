# Cerebra — MVP Specification

## 1. Purpose

This document defines Cerebra v0.1.

The MVP should prove that Cerebra can ingest local sources, create structured memory records, retrieve them through hybrid search, assemble ContextPackets, and export graph-ready data.

Do not build a polished UI first.

Do not build Policy Scout inside Cerebra.

Do not build a universal perfect parser.

Build the memory runtime spine.

---

## 2. MVP Product Statement

Cerebra v0.1 is a local-first backend/CLI memory runtime that can:

1. Initialize a local memory vault.
2. Ingest folders/files.
3. Register sources.
4. Parse common text-based file types.
5. Normalize and chunk content.
6. Create memory records with provenance.
7. Build lexical and vector indexes.
8. Retrieve through hybrid search.
9. Assemble ContextPackets.
10. Store retrieval traces.
11. Manage basic lifecycle states.
12. Export graph-ready JSON.

---

## 3. MVP CLI Commands

### 3.1 Initialize Vault

```bash
cerebra init ./cerebra-vault
```

Creates:

```text
config
storage
artifacts
indexes
events
exports
```

### 3.2 Ingest Source

```bash
cerebra ingest ./docs
cerebra ingest ./file.md
```

### 3.3 Search Memory

```bash
cerebra search "retrieval architecture"
```

### 3.4 Build ContextPacket

```bash
cerebra context "Plan Cerebra ingestion architecture" --project Cerebra
```

### 3.5 Consolidate

```bash
cerebra consolidate --project Cerebra
```

### 3.6 Lifecycle Actions

```bash
cerebra archive mem_123
cerebra tombstone mem_123
cerebra restore archive_123
```

### 3.7 Graph Export

```bash
cerebra export graph --project Cerebra --out cerebra_graph.json
```

---

## 4. MVP Ingestion Scope

Support:

```text
text
markdown
json
yaml
csv
code files
folder ingestion
source registry
hash-based dedupe
basic chunking
metadata extraction
```

Defer:

```text
PDF
docx
odt
email
audio
image OCR
zip/archive recursive ingestion
complex notebooks
```

unless easy local support is available.

---

## 5. MVP Storage Scope

Use:

```text
SQLite for metadata/state/events
local artifact store for normalized docs
simple lexical index
local vector index
graph tables in SQLite
```

Do not require a remote database.

Do not require a cloud vector DB.

---

## 6. MVP Retrieval Scope

Support:

```text
lexical search
vector search
metadata filtering
simple hybrid fusion
basic salience scoring
retrieval trace
```

Graph expansion can be simple one-hop expansion.

Community summaries and DRIFT-like retrieval can come later.

---

## 7. MVP ContextPacket Scope

A ContextPacket should include:

```text
context_packet_id
task/query
selected memory records
source references
score components
token estimate
retrieval trace ID
plain text rendering
JSON rendering
```

Optional:

```text
basic graph neighbors
excluded candidates
uncertainty notes
```

---

## 8. MVP Lifecycle Scope

Support:

```text
active
archived
tombstoned
deleted marker
```

Required behavior:

```text
active records retrieve normally
archived records retrieve through retrieval card/explicit search
tombstoned records excluded from normal retrieval
deleted markers prevent accidental stale references
```

---

## 9. MVP Consolidation Scope

Support:

```text
manual consolidation command
duplicate detection by hash/text similarity
document summary creation
project/topic summary creation
archive retrieval card creation
basic relationship creation
consolidation event log
```

Defer:

```text
advanced contradiction resolution
autonomous consolidation schedules
large-scale community graph summarization
learned salience updates
```

---

## 10. MVP Graph Scope

Support:

```text
Source -> Document -> Chunk -> MemoryRecord provenance graph
Project membership edges
Summary support edges
basic RELATED_TO edges
graph export JSON
```

Defer:

```text
advanced graph database
live visualization
community detection
graph layout
```

LumaWeave owns visualization.

---

## 11. MVP Non-Goals

Do not build in v0.1:

```text
full frontend
cloud sync
multi-user server
Policy Scout clone
agent shell execution
full web crawler
perfect universal file parsing
complex plugin marketplace
autonomous deletion
automatic sensitive personal memory inference
```

---

## 12. Definition of Done

Cerebra v0.1 is done when:

1. `cerebra init` creates a local vault.
2. `cerebra ingest ./docs` registers and parses supported files.
3. Cerebra creates source records.
4. Cerebra creates normalized documents.
5. Cerebra creates chunks with provenance.
6. Cerebra creates memory records.
7. Cerebra builds lexical and vector indexes.
8. `cerebra search` returns hybrid results with score components.
9. `cerebra context` creates a ContextPacket.
10. ContextPacket includes selected memory and source provenance.
11. Retrieval trace is stored.
12. `cerebra consolidate` creates at least one summary.
13. `cerebra archive` creates retrieval card/archived state.
14. `cerebra tombstone` excludes memory from normal retrieval.
15. `cerebra export graph` exports graph JSON.
16. Tests cover ingestion, retrieval, ContextPacket, lifecycle, consolidation, and graph export.

---

## 13. MVP Build Order

```text
1. project scaffold
2. config/vault init
3. source registry
4. file discovery
5. type detection
6. parser adapters
7. normalization
8. chunking
9. memory record schema
10. SQLite store
11. lexical index
12. vector index
13. hybrid retrieval
14. salience scoring v0
15. ContextPacket builder
16. retrieval trace
17. lifecycle manager
18. consolidation v0
19. graph store/export
20. tests and docs polish
```

---

## 14. Prototype Gate

Before writing more than a few more planning docs, build a thin prototype proving:

```text
ingest three markdown files
create chunks
search hybrid
build ContextPacket
show retrieval trace
export tiny graph JSON
```

This prevents planning from outrunning proof.

---

## 15. MVP Doctrine

Cerebra v0.1 succeeds if it proves the spine:

```text
source -> memory record -> retrieval -> ContextPacket -> graph export -> lifecycle event
```

Everything else can grow from there.
