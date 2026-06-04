SUPERSEDED — see cerebra-refined/CEREBRA_DEV_ROADMAP_v8.1.md

# Cerebra — Implementation Plan

## 1. Purpose

This document defines the revised implementation plan for Cerebra.

The plan is prototype-first and cognitive-runtime-first.

It replaces the previous plan that was too close to a conventional RAG backend.

---

## 2. Senior Dev Rule

Do not build broad architecture before proving the runtime spine.

The first implementation should be small, testable, and disposable if it reveals a flaw.

Target:

```text
~500-1000 lines prototype before more major docs
```

---

## 3. Phase 0 — Prototype Gate

### Goal

Prove the cognition-shaped spine.

### Build

```text
vault init
markdown ingestion
chunking
basic retrieval
ContextPacket
working memory record
cycle definition
mock cycle step
signal evaluation
clutch decision
graph event export
```

### Done When

```text
one command can run a tiny cycle from source memory to graph export
```

Example:

```bash
cerebra run-demo --docs ./docs --goal "Plan Cerebra prototype"
```

---

## 4. Phase 1 — Vault and Source Memory

### Goal

Create reliable local storage and source ingestion.

Deliverables:

```text
vault paths
SQLite schema
source registry
hashing
Markdown parser
chunker
source_chunk records
events
```

Tests:

```text
init
ingest
dedupe
re-ingest unchanged
provenance chain
```

---

## 5. Phase 2 — Retrieval and ContextPacket

### Goal

Build traceable context.

Deliverables:

```text
lexical retrieval
simple vector abstraction
hybrid fusion
salience components v0
retrieval trace
ContextPacket JSON
plain text rendering
```

Tests:

```text
exact match
semantic-ish match
project filter
trace creation
source provenance
```

---

## 6. Phase 3 — Working Memory v0

### Goal

Track active context separately from long-term memory.

Deliverables:

```text
working_memory table/model
slots
attention items
promotion
eviction
ContextPacket integration
events
```

Tests:

```text
item promoted
capacity enforced
low salience evicted
working memory rendered into ContextPacket
```

---

## 7. Phase 4 — Cycle Runtime v0

### Goal

Run one simple cycle.

Deliverables:

```text
cycle definition schema
runtime session
step record
mock step executor
signal evaluation
clutch decision v0
runtime events
```

Tests:

```text
cycle loads
session starts
step runs
signals generated
clutch decision emitted
session completes
```

---

## 8. Phase 5 — Signal Pipeline and Clutch v0

### Goal

Make control decisions explainable.

Deliverables:

```text
signal components
composite summary
confidence
rule-based clutch
mode persistence
hysteresis metadata
```

Initial clutch actions:

```text
accept
refine
retrieve_more
consolidate
stop
ask_user
```

Tests:

```text
low context fit -> retrieve_more
high score -> accept
low coherence -> refine
summary needed -> consolidate
```

---

## 9. Phase 6 — Graph Event Writer

### Goal

Emit graph-native runtime state.

Deliverables:

```text
graph node model
graph edge model
event outbox
JSON export
LumaWeave-compatible shape
```

Runtime nodes:

```text
RuntimeSession
CycleStep
ContextPacket
EvaluationPacket
ClutchDecision
MemoryRecord
Summary
```

Tests:

```text
nodes exported
edges exported
provenance exists
event outbox survives failure
```

---

## 10. Phase 7 — Consolidation v0

### Goal

Turn a session into durable summary memory.

Deliverables:

```text
session summary
summary support links
semantic memory candidate
consolidation record
graph edges
```

Tests:

```text
summary links to steps/memory
sources preserved
no deletion
consolidation event emitted
```

---

## 11. Phase 8 — Prediction v0

### Goal

Record expected vs actual signals.

Deliverables:

```text
prediction record
outcome record
prediction error
graph events
clutch input hook
```

Tests:

```text
prediction created
outcome measured
error calculated
large error influences next action
```

This phase can be skipped until v0.2 if runtime spine needs stabilizing.

---

## 12. Phase 9 — Bons.ai Cycle Compatibility

### Goal

Express Bons.ai-like cycle as a Cerebra config.

Deliverables:

```text
bonsai.ideation.v0 cycle config
agent role mapping
signal mapping
catalyst strategy mapping
clutch mapping
event mapping
```

Do not port code wholesale.

Extract patterns.

---

## 13. Revised Build Order

```text
1. prototype gate
2. vault/source/chunk memory
3. retrieval/ContextPacket
4. working memory
5. cycle runtime
6. signal/clutch
7. graph events
8. consolidation
9. prediction
10. Bons.ai config compatibility
11. async monitors
```

---

## 14. Implementation Doctrine

Build the smallest loop that proves Cerebra is not just search:

```text
memory -> attention -> cycle -> evaluation -> control -> memory -> graph
```

That loop is the product seed.
