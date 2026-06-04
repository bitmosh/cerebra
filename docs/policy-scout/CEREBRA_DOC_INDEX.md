# Cerebra — Documentation Index

## 1. Purpose

This index explains the Cerebra documentation set and recommended reading order.

Cerebra is a local-first memory and cognition runtime.

It is not Policy Scout.

It is not LumaWeave.

Policy Scout may provide optional safety/event source material later.

LumaWeave may visualize Cerebra's graph exports later.

Cerebra owns memory.

---

## 2. Recommended Reading Order

Read in this order:

```text
1. CEREBRA_PROJECT_SCOPE.md
2. CEREBRA_ARCHITECTURE.md
3. CEREBRA_MEMORY_LAYERS.md
4. CEREBRA_INGESTION_ARCHITECTURE.md
5. CEREBRA_RETRIEVAL_ARCHITECTURE.md
6. CEREBRA_CONTEXT_PACKET_PROTOCOL.md
7. CEREBRA_STATE_GOVERNANCE.md
8. CEREBRA_MEMORY_LIFECYCLE.md
9. CEREBRA_CONSOLIDATION_ENGINE.md
10. CEREBRA_GRAPH_MODEL.md
11. CEREBRA_SALIENCE_SCORING.md
12. CEREBRA_MVP_SPEC.md
13. CEREBRA_IMPLEMENTATION_PLAN.md
14. CEREBRA_TESTING_STRATEGY.md
```

---

## 3. Core Scope Docs

### `CEREBRA_PROJECT_SCOPE.md`

Defines:

- what Cerebra is
- what Cerebra owns
- what Cerebra does not own
- relationship to Policy Scout
- relationship to LumaWeave
- MVP definition

This is the anchor doc.

### `CEREBRA_ARCHITECTURE.md`

Defines the backend architecture:

- source registry
- ingestion router
- parser adapters
- normalization
- chunking
- memory records
- storage
- retrieval
- ContextPackets
- consolidation
- lifecycle
- graph export

---

## 4. Memory Model Docs

### `CEREBRA_MEMORY_LAYERS.md`

Defines the layered memory model:

```text
source artifacts
normalized documents
chunks
memory records
summaries
relationship graph
ContextPackets
consolidated long memory
archive/tombstone layer
```

### `CEREBRA_MEMORY_LIFECYCLE.md`

Defines memory states:

```text
active
warm
cold
archived
tombstoned
deleted
quarantined
```

Also defines archive packages, retrieval cards, graph stubs, tombstones, and restore behavior.

### `CEREBRA_CONSOLIDATION_ENGINE.md`

Defines how Cerebra maintains memory:

- duplicate detection
- summaries
- fact promotion
- contradiction detection
- staleness
- salience updates
- lifecycle recommendations

---

## 5. Ingestion and Retrieval Docs

### `CEREBRA_INGESTION_ARCHITECTURE.md`

Defines how sources become memory:

- source discovery
- source registry
- type detection
- adapter selection
- parser contracts
- normalization
- chunking
- memory record creation
- idempotency
- error handling

### `CEREBRA_RETRIEVAL_ARCHITECTURE.md`

Defines layered retrieval:

- lexical search
- vector search
- metadata filtering
- graph expansion
- summary/community retrieval
- salience scoring
- reranking
- ContextPacket assembly
- retrieval traces

### `CEREBRA_SALIENCE_SCORING.md`

Defines salience components:

- semantic similarity
- lexical match
- project relevance
- source authority
- recency
- user pin
- confidence
- lifecycle state
- task relevance
- penalties

---

## 6. Agent Context Docs

### `CEREBRA_CONTEXT_PACKET_PROTOCOL.md`

Defines the agent-facing memory bundle.

A ContextPacket includes:

- selected memory
- source provenance
- summaries
- graph context
- uncertainties
- token budget
- retrieval trace

This is Cerebra's main output to agents.

---

## 7. Governance and State Docs

### `CEREBRA_STATE_GOVERNANCE.md`

Defines:

- current state vs event history
- state categories
- schema versioning
- memory event log
- state transitions
- index state
- failure behavior

---

## 8. Graph Docs

### `CEREBRA_GRAPH_MODEL.md`

Defines graph-ready memory:

- node types
- edge types
- provenance graph
- entity nodes
- topic nodes
- contradiction graph
- duplicate graph
- LumaWeave export

---

## 9. Build Docs

### `CEREBRA_MVP_SPEC.md`

Defines v0.1:

- CLI commands
- MVP ingestion scope
- MVP retrieval scope
- MVP ContextPacket scope
- MVP lifecycle scope
- definition of done
- build order
- prototype gate

### `CEREBRA_IMPLEMENTATION_PLAN.md`

Defines practical milestones from prototype to graph export.

### `CEREBRA_TESTING_STRATEGY.md`

Defines testing requirements.

---

## 10. Project Laws

These laws should guide every Cerebra implementation decision:

```text
1. Cerebra owns memory, not visualization.
2. Cerebra is local-first by default.
3. Every memory needs provenance.
4. Retrieval must be layered, not vector-only.
5. Salience must be component-based.
6. ContextPackets must be inspectable.
7. Consolidation must not erase source truth.
8. Tombstones prevent accidental resurrection.
9. Graph export is derived from memory records.
10. Policy Scout is optional source material, not Cerebra's core.
```

---

## 11. Current Planning Status

The Cerebra docs are now coherent enough to start a thin prototype.

Next best step:

```text
Build the prototype gate:
  ingest three markdown files
  create chunks
  search hybrid-ish
  build ContextPacket
  export tiny graph JSON
```

Do not keep planning indefinitely before proving the spine.
