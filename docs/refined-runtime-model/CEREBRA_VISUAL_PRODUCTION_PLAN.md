# Cerebra — Visual Production Plan

## 1. Purpose

This document defines the first visual set for Cerebra.

Cerebra is a local-first memory and cognition runtime. Its visuals should explain how sources become structured memory, how memory is retrieved, how ContextPackets are assembled, how memory lifecycle works, and how graph-ready exports flow to LumaWeave.

---

## 2. Visual Doctrine

Cerebra visuals should be:

```text
memory-centered
source-grounded
backend-first
graph-ready
retrieval-aware
lifecycle-aware
clean and readable
```

Avoid making Cerebra look like:

```text
a graph viewer
a security harness
a generic vector database
a chatbot wrapper
```

Cerebra is the memory runtime.

---

## 3. First Diagram Set

Recommended first diagrams:

```text
1. Cerebra System Architecture
2. Source Ingestion Pipeline
3. Memory Layer Stack
4. Hybrid Retrieval Flow
5. ContextPacket Assembly Flow
6. Memory Lifecycle State Machine
7. Consolidation Engine Flow
8. Graph Export / LumaWeave Bridge
9. State Governance Map
10. Salience Scoring Components
```

---

## 4. Diagram 1 — Cerebra System Architecture

### Purpose

Show the full backend spine.

### Key Message

Cerebra converts sources into structured memory, retrieval, ContextPackets, consolidation, lifecycle management, and graph export.

---

## 5. Diagram 2 — Source Ingestion Pipeline

### Purpose

Show how raw sources become memory records.

### Key Message

Ingestion is adapter-based, confidence-aware, and provenance-preserving.

---

## 6. Diagram 3 — Memory Layer Stack

### Purpose

Show memory is layered, not one flat vector database.

### Key Message

Sources, documents, chunks, memory records, summaries, graph relationships, ContextPackets, consolidated memory, and archive/tombstone layers each have different jobs.

---

## 7. Diagram 4 — Hybrid Retrieval Flow

### Purpose

Show retrieval order.

### Key Message

Cerebra uses lexical, vector, metadata, graph, summaries, salience, reranking, and budget allocation.

---

## 8. Diagram 5 — ContextPacket Assembly Flow

### Purpose

Show how retrieved memory becomes agent-ready context.

### Key Message

ContextPackets include selected memory, provenance, graph hints, uncertainties, token budget, and retrieval trace.

---

## 9. Diagram 6 — Memory Lifecycle State Machine

### Purpose

Show allowed memory state transitions.

### Key Message

Cerebra does not forget by accident. Archive, tombstone, restore, and delete behavior is explicit.

---

## 10. Diagram 7 — Consolidation Engine Flow

### Purpose

Show how raw accumulated memory becomes cleaner durable memory.

### Key Message

Consolidation summarizes, links, de-duplicates, detects contradictions, updates salience, and recommends lifecycle changes without deleting source truth.

---

## 11. Diagram 8 — Graph Export / LumaWeave Bridge

### Purpose

Show responsibility separation.

### Key Message

Cerebra owns graph-ready memory data. LumaWeave visualizes it.

---

## 12. Diagram 9 — State Governance Map

### Purpose

Show current state tables, event log, indexes, artifacts, and traces.

### Key Message

Cerebra uses current state for fast reads and events for traceability.

---

## 13. Diagram 10 — Salience Scoring Components

### Purpose

Show salience is component-based, not a single opaque number.

### Key Message

Similarity is only one signal. Project relevance, source authority, lifecycle state, confidence, recency, pins, graph centrality, and task relevance matter.

---

## 14. Recommended Creation Order

```text
1. Cerebra System Architecture
2. Source Ingestion Pipeline
3. Hybrid Retrieval Flow
4. ContextPacket Assembly Flow
5. Memory Lifecycle State Machine
6. Consolidation Engine Flow
7. Memory Layer Stack
8. Graph Export / LumaWeave Bridge
9. State Governance Map
10. Salience Scoring Components
```

---

## 15. Visual Doctrine

Every Cerebra diagram should answer:

```text
What source did this come from?
What memory layer does this affect?
How can it be retrieved?
How can it be inspected?
How can it evolve over time?
```
