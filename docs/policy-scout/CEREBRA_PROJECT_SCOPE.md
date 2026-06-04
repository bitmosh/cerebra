# Cerebra — Project Scope

## 1. Purpose

Cerebra is a local-first memory and cognition runtime for personal and project-scale knowledge.

It is designed to ingest many kinds of source material, interpret it, structure it into durable memory records, support high-quality retrieval, and expose graph-ready memory structures to external visualization systems such as LumaWeave.

Cerebra is not primarily a graph viewer.

Cerebra is not primarily a security harness.

Cerebra is the system that remembers, retrieves, consolidates, reasons over, and maintains user-controlled knowledge.

---

## 2. One-Liner

```text
Cerebra is a local-first memory runtime for ingesting, structuring, retrieving, and consolidating a user's knowledge into durable, graph-ready context.
```

---

## 3. Core Doctrine

Cerebra should be:

```text
local-first
source-grounded
retrieval-layered
schema-governed
graph-ready
context-aware
consolidation-capable
agent-compatible
dependency-conscious
inspectable
```

The central idea:

```text
Cerebra turns a user's data bank into structured, retrievable, maintainable memory.
```

---

## 4. What Cerebra Owns

Cerebra owns:

- source ingestion
- source normalization
- document parsing
- chunking
- metadata extraction
- embeddings
- hybrid retrieval
- graph-ready relationship extraction
- memory records
- salience scoring
- consolidation
- memory lifecycle
- tombstoning/archive behavior
- ContextPacket generation
- persistent context functions
- context-window visibility
- graph export for LumaWeave
- memory event logs
- memory schema governance

---

## 5. What Cerebra Does Not Own

Cerebra does not own:

- graph visualization UI
- command execution security
- package install sandboxing
- agent shell permissions
- endpoint security
- full antivirus scanning
- polished front-end experience in v0.1

Those are separate systems.

Policy Scout may provide safe command/audit events that Cerebra can ingest later, but Policy Scout is not the center of Cerebra.

LumaWeave may visualize Cerebra graphs, but LumaWeave is not the memory runtime.

---

## 6. Primary User Story

A user points Cerebra at a local data bank.

Cerebra should:

1. Detect file types.
2. Parse and normalize sources.
3. Preserve source provenance.
4. Extract text, metadata, entities, topics, and relationships.
5. Create chunks and memory records.
6. Build vector, lexical, metadata, and graph indexes.
7. Retrieve relevant memory through layered search.
8. Generate ContextPackets for agents.
9. Track what context was given to which agent.
10. Consolidate related memories over time.
11. Archive or tombstone stale material safely.
12. Export graph-ready structures to LumaWeave.

---

## 7. Product Shape

Cerebra should start as a backend-first system.

Initial interfaces:

```text
CLI
local library/API
local service later
```

Defer front-end design until the backend is stable.

The first goal is not a beautiful UI.

The first goal is a trustworthy memory engine.

---

## 8. Core Capabilities

### 8.1 Source Ingestion

Cerebra should ingest:

- plain text
- Markdown
- JSON
- YAML
- CSV
- code files
- PDFs
- office docs where practical
- audio transcripts where available
- exported chat logs
- project docs
- generated reports
- future Policy Scout reports/events

The ingestion system should be extensible through adapters.

### 8.2 Source Understanding

Cerebra should attempt to detect:

- file type
- source category
- project association
- timestamp
- author/source if available
- document structure
- headings
- code symbols
- entities
- topics
- relationships
- confidence of extraction

### 8.3 Memory Records

Cerebra should not store only raw chunks.

It should store structured memory records with:

- source provenance
- content
- summary
- embeddings
- tags
- entities
- relationships
- salience
- lifecycle state
- confidence
- graph references

### 8.4 Retrieval

Cerebra should support layered retrieval:

- exact/lexical search
- vector similarity
- metadata filters
- graph-neighborhood expansion
- recency/salience scoring
- source-priority weighting
- reranking
- ContextPacket assembly

### 8.5 Consolidation

Cerebra should merge, compress, summarize, and reconcile memory over time.

Consolidation should produce:

- summaries
- topic clusters
- relationship updates
- contradiction notes
- stale memory markers
- archive summaries
- graph updates

### 8.6 Context Window Management

Cerebra should help agents work within limited context windows.

It should produce ContextPackets that include:

- selected memory items
- source citations/provenance
- summaries
- known uncertainties
- excluded-but-relevant notes
- token budget metadata
- retrieval trace

It should eventually support a context-window viewer so users can see what the agent is working from.

---

## 9. Local-First Posture

Cerebra should keep durable user memory local by default.

Local durable data:

- raw source references
- normalized source artifacts
- chunks
- memory records
- embeddings
- lexical indexes
- graph edges
- consolidation summaries
- retrieval traces
- ContextPacket history
- lifecycle records

Cloud APIs should be optional adapters, not required infrastructure.

---

## 10. Backend-First Build Principle

Do not start with the front end.

Build:

```text
source registry
ingestion adapters
memory schema
storage layer
retrieval layer
ContextPacket builder
consolidation engine
graph export
```

Then design the UI around real backend behavior.

---

## 11. Relationship to LumaWeave

LumaWeave is the graph visualization system.

Cerebra should export graph-ready data:

```text
nodes
edges
clusters
memory records
source references
relationship confidence
timestamps
lifecycle state
```

LumaWeave should visualize.

Cerebra should remember and retrieve.

---

## 12. Relationship to Policy Scout

Policy Scout is a local-first safety harness for agent commands, package installs, and suspicious project activity.

Cerebra may ingest Policy Scout data later:

- Scout Reports
- audit summaries
- security findings
- project risk history

But Policy Scout is not required for Cerebra v0.1.

Policy Scout should be mentioned only where command safety, agent permissions, or security event ingestion is relevant.

---

## 13. Non-Goals for Cerebra v0.1

Do not build in v0.1:

- polished front-end
- full LumaWeave visualization
- Policy Scout clone
- full web crawler
- autonomous write-access agent
- enterprise sync
- multi-user cloud service
- complex plugin marketplace
- perfect universal file parsing
- full citation/legal compliance system
- automatic deletion of user data without review

---

## 14. MVP Definition

Cerebra v0.1 is done when:

1. A user can initialize a local Cerebra vault.
2. A user can ingest a folder of Markdown/text/code/JSON files.
3. Cerebra stores source records and normalized memory records.
4. Cerebra chunks content with provenance.
5. Cerebra creates lexical and vector indexes.
6. Cerebra can run hybrid retrieval.
7. Cerebra can assemble a ContextPacket.
8. Cerebra can show a retrieval trace.
9. Cerebra can export graph-ready JSON.
10. Cerebra can mark memory as active, archived, or tombstoned.
11. Tests cover ingestion, schema validation, retrieval, lifecycle, and ContextPacket assembly.

---

## 15. Core Question

Cerebra should answer:

```text
What should the agent know right now, where did that knowledge come from, how confident is it, how does it relate to the rest of the user's memory, and what should happen to it over time?
```
