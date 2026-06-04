# Cerebra — Replacement Manifest v8

## Purpose

This manifest prevents duplicate/conflicting Cerebra docs after the scope correction.

The correction: Cerebra should not be framed as only a folder watcher, RAG layer, or LumaWeave passthrough. Cerebra should be framed as a local-first cognitive runtime that uses memory as one major subsystem.

---

## Replace These Files

| File | Action | Why |
|---|---|---|
| `CEREBRA_PROJECT_SCOPE.md` | REPLACE | Re-centers Cerebra as cognitive runtime, not just memory storage/RAG. |
| `CEREBRA_ARCHITECTURE.md` | REPLACE | Adds cycle runtime, working memory, signal pipeline, clutch, prediction, and graph-native events. |
| `CEREBRA_MEMORY_LAYERS.md` | REPLACE | Expands memory layers into source, episodic, working, semantic, procedural, predictive, graph, archive, and tombstone layers. |
| `CEREBRA_MVP_SPEC.md` | REPLACE | Changes MVP from RAG-first to runtime-spine-first. |
| `CEREBRA_IMPLEMENTATION_PLAN.md` | REPLACE | Adds prototype gate and runtime-first build order. |
| `CEREBRA_DOC_INDEX.md` | REPLACE | Updates canonical reading order and marks v8 docs as current. |

---

## Add These New Files

| File | Action | Why |
|---|---|---|
| `CEREBRA_COGNITIVE_RUNTIME.md` | ADD | Defines cycle definitions, runtime sessions, step execution, signal pipeline, clutch, catalyst, and graph emission. |
| `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md` | ADD | Defines contested working memory, attention slots, promotion, eviction, and interrupts. |
| `CEREBRA_PREDICTION_AND_EVALUATION.md` | ADD | Defines predictions, outcomes, prediction error, evaluation packets, and learning signals. |

---

## Keep These Existing Files For Now

These remain useful but should be interpreted under the revised runtime framing:

```text
CEREBRA_INGESTION_ARCHITECTURE.md
CEREBRA_RETRIEVAL_ARCHITECTURE.md
CEREBRA_CONTEXT_PACKET_PROTOCOL.md
CEREBRA_STATE_GOVERNANCE.md
CEREBRA_MEMORY_LIFECYCLE.md
CEREBRA_CONSOLIDATION_ENGINE.md
CEREBRA_GRAPH_MODEL.md
CEREBRA_SALIENCE_SCORING.md
CEREBRA_TESTING_STRATEGY.md
CEREBRA_MATRICES.md
CEREBRA_SCENARIO_CARDS.md
CEREBRA_PROTOTYPE_CHECKLIST.md
CEREBRA_VISUAL_PRODUCTION_PLAN.md
CEREBRA_MERMAID_DIAGRAMS.md
```

---

## Deprecated Framing

Avoid describing Cerebra primarily as:

```text
a folder watcher
a RAG wrapper
a vector database layer
a graph export tool
a LumaWeave passthrough
a Policy Scout event sink
```

Those are possible subsystems or integrations, not the identity.

---

## Canonical Framing

Use this framing going forward:

```text
Cerebra is a local-first cognitive runtime that runs configurable cognitive cycles, maintains durable state and memory, manages working context, evaluates signals, consolidates experience, learns from prediction error, and emits graph-native records for LumaWeave.
```

Short version:

```text
Cerebra is the runtime that remembers, attends, evaluates, consolidates, and decides what cognitive process should happen next.
```

---

## Boundary Rules

```text
Bons.ai = one cognitive cycle configuration / reference lab.
Cerebra = cognitive runtime, state, memory, attention, synthesis.
LumaWeave = graph visualization and exploration.
Policy Scout = optional safety/event source.
```

---

## Migration Instructions

1. Replace the six docs listed in the replacement table.
2. Add the three new docs.
3. Keep the other docs for now.
4. Do not keep old copies in the active docs directory with names like `_old`, `_v1`, or `_backup`.
5. Archive old copies outside the active docs folder if you want history.
