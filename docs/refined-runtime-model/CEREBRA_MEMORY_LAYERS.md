# Cerebra — Memory Layers

## 1. Purpose

Cerebra's memory is not only source chunks plus vector search. It supports cognitive runtime behavior: working memory, episodic memory, semantic memory, procedural memory, predictive memory, and graph-native memory.

---

## 2. Revised Memory Layer Overview

Canonical layers:

```text
M0 Source Memory
M1 Normalized Document Memory
M2 Chunk Memory
M3 Episodic Runtime Memory
M4 Working Memory
M5 Semantic Memory
M6 Procedural Memory
M7 Predictive Memory
M8 Relationship Graph Memory
M9 Consolidated / Archive Memory
M10 Tombstone / Suppression Memory
```

---

## 3. M0 — Source Memory

Raw or referenced source material.

Examples:

```text
files
docs
code
reports
chat exports
cycle logs
```

Purpose:

```text
Preserve origin and provenance.
```

---

## 4. M1 — Normalized Document Memory

Parser-normalized representations.

Purpose:

```text
Create stable input for chunking, extraction, and citation.
```

---

## 5. M2 — Chunk Memory

Retrievable units from normalized documents.

Purpose:

```text
Provide source-grounded retrieval candidates.
```

Chunk memory supports:

```text
lexical index
vector index
metadata filters
source citations
```

---

## 6. M3 — Episodic Runtime Memory

Time-indexed cycle/session events.

Examples:

```text
cycle started
agent output
critique generated
score computed
clutch decision issued
branch created
prediction made
user feedback received
```

Purpose:

```text
Remember what happened.
```

Episodic memory is the raw material for consolidation.

---

## 7. M4 — Working Memory

Current active cognitive context.

Contains:

```text
active goal
current task
selected memories
open hypotheses
active contradictions
recent outputs
pending questions
interrupt candidates
```

Working memory is bounded and contested.

---

## 8. M5 — Semantic Memory

Durable facts, summaries, and project knowledge.

Examples:

```text
Cerebra owns cognitive runtime behavior.
LumaWeave owns visualization.
Bons.ai is one cycle definition.
```

Semantic memory should be source-supported.

---

## 9. M6 — Procedural Memory

Durable process knowledge.

Examples:

```text
how to run a Bons.ai ideation cycle
how to assemble a ContextPacket
how to consolidate a session
how to score retrieval quality
how to emit graph events
```

Procedural memory may be encoded as prompts, policies, cycle configs, or executable adapters.

---

## 10. M7 — Predictive Memory

Predictions and prediction-error records.

Examples:

```text
expected coherence of next output
expected retrieval usefulness
expected risk of goal drift
predicted need for consolidation
actual outcome
prediction error
```

Purpose:

```text
Let Cerebra learn from expectation gaps.
```

---

## 11. M8 — Relationship Graph Memory

Typed relationships among memory items.

Examples:

```text
supports
contradicts
updates
duplicates
derived_from
belongs_to
used_in_context
caused_by
```

This layer supports graph expansion, synthesis, and LumaWeave export.

---

## 12. M9 — Consolidated / Archive Memory

Compressed long-term memory.

Includes:

```text
project summaries
topic summaries
session summaries
archive summaries
retrieval cards
graph stubs
```

Purpose:

```text
Reduce noise while preserving recoverability.
```

---

## 13. M10 — Tombstone / Suppression Memory

Markers that prevent accidental resurrection.

Includes:

```text
false memory tombstones
user-deleted memory markers
privacy suppressions
poisoned-source markers
```

Purpose:

```text
Remember what should not be retrieved.
```

---

## 14. Retrieval Order

Default retrieval should consider:

```text
1. Working memory
2. Active semantic/procedural memory
3. Relevant chunk/source memory
4. Recent episodic memory
5. Graph-expanded neighbors
6. Consolidated summaries
7. Archive retrieval cards
```

Tombstoned/quarantined memory is excluded by default.

---

## 15. Consolidation Path

Typical consolidation path:

```text
episodic runtime memory
  -> session summary
  -> semantic memory
  -> procedural update
  -> predictive error update
  -> graph relationships
  -> archive card if needed
```

---

## 16. MVP Memory Scope

Cerebra v0.1 should implement:

```text
M0 source memory
M1 normalized documents
M2 chunks
M3 episodic cycle events
M4 basic working memory
M5 basic semantic summaries
M8 basic relationship graph
M9 basic archive summaries/cards
M10 tombstones
```

M6 procedural and M7 predictive memory can begin as simple records in v0.1 and deepen in v0.2+.

---

## 17. Memory Doctrine

Cerebra earns its name when memory is not just stored, but actively shaped:

```text
retrieved
contested
evaluated
consolidated
predicted against
suppressed when wrong
exported as graph-native structure
```
