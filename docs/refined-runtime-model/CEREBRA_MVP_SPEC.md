# Cerebra — MVP Specification

## 1. Purpose

This document defines the revised Cerebra v0.1 MVP.

The MVP must prove Cerebra as a cognitive runtime, not just a RAG backend.

The goal is a small but real spine:

```text
cycle definition -> runtime session -> working memory -> retrieval -> ContextPacket -> step output -> signal evaluation -> clutch decision -> memory write -> graph event
```

---

## 2. MVP Product Statement

Cerebra v0.1 is a local-first cognitive runtime prototype that can:

1. Initialize a local vault.
2. Ingest a small set of local project docs.
3. Create source-grounded memory records.
4. Load a simple cognitive cycle definition.
5. Build a ContextPacket from retrieval + working memory.
6. Execute a simple cycle step.
7. Evaluate the output with component signals.
8. Issue a clutch/control decision.
9. Write episodic memory and graph-native events.
10. Create a basic consolidation summary.
11. Export graph JSON for LumaWeave.

---

## 3. Prototype Gate Comes First

Before building the full MVP, build a thin prototype.

Prototype goal:

```text
ingest three markdown files
load one cycle definition
build one ContextPacket
run one mock cognitive step
score it
issue one clutch decision
write graph events
export graph JSON
```

This prevents planning from outrunning implementation proof.

---

## 4. MVP CLI Commands

```bash
cerebra init ./demo-vault
cerebra ingest ./docs
cerebra search "ContextPacket retrieval trace"
cerebra context "Plan Cerebra runtime implementation" --project Cerebra
cerebra run-cycle simple.planning.v0 --goal "Draft a prototype plan"
cerebra consolidate --session sess_123
cerebra export graph --out cerebra_graph.json
```

---

## 5. MVP Cycle Scope

Support one simple built-in cycle.

Example:

```text
simple.planning.v0
```

Steps:

```text
build_context
generate_response_or_mock_step
evaluate_signals
clutch_decision
memory_write
graph_emit
```

The first implementation can mock the LLM call if needed.

The runtime spine matters more than model quality.

---

## 6. MVP Memory Scope

Support:

```text
source memory
normalized documents
chunks
episodic runtime events
basic working memory
basic semantic summaries
relationship graph
tombstone markers
```

Procedural and predictive memory can begin as simple records.

---

## 7. MVP Working Memory Scope

Support:

```text
working memory record
active goal
selected memory items
constraint items
recent output item
basic salience ordering
ContextPacket rendering
```

No automatic interrupt system in v0.1.

---

## 8. MVP Prediction/Evaluation Scope

Support:

```text
prediction record optional
evaluation packet required
signal components
composite score summary
clutch decision input
graph event emission
```

Prediction can be deterministic/simple.

---

## 9. MVP Graph Scope

Export graph nodes:

```text
Source
Document
Chunk
MemoryRecord
RuntimeSession
CycleStep
EvaluationPacket
ClutchDecision
ContextPacket
Summary
```

Export graph edges:

```text
CONTAINS
DERIVED_FROM
USED_IN_CONTEXT
PRODUCED
EVALUATED_BY
DECIDED_BY
SUMMARIZES
BELONGS_TO
```

---

## 10. MVP Non-Goals

Do not build:

```text
full polished UI
async background cognition
advanced prediction models
automatic interrupts
multi-cycle marketplace
full Bons.ai migration
Policy Scout integration
full LumaWeave integration
universal file parsing
cloud sync
```

---

## 11. Definition of Done

Cerebra v0.1 is done when:

1. `cerebra init` creates a vault.
2. `cerebra ingest` registers and chunks Markdown docs.
3. Source provenance is preserved.
4. `cerebra search` returns traceable results.
5. `cerebra context` creates a ContextPacket.
6. A working memory record is created and updated.
7. `cerebra run-cycle` executes one simple cycle.
8. The cycle produces a step output.
9. The signal pipeline creates component metrics.
10. The clutch returns an explainable decision.
11. Runtime events are written.
12. Consolidation creates a source-linked summary.
13. Graph export includes runtime + memory nodes.
14. Tests cover the full spine.

---

## 12. Build Order

```text
1. vault init
2. source registry
3. markdown ingestion
4. chunking
5. memory records
6. lexical retrieval
7. ContextPacket builder
8. working memory record
9. cycle definition schema
10. runtime session
11. mock step execution
12. signal evaluation
13. clutch decision v0
14. runtime memory writes
15. graph event writer
16. consolidation summary
17. graph export
18. tests
```

---

## 13. MVP Doctrine

Cerebra v0.1 should prove the smallest cognition-shaped loop:

```text
know something
hold something in mind
do a step
evaluate it
decide what next
remember what happened
emit a graph-native trace
```
