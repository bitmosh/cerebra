# Cerebra — ContextPacket Protocol

## 1. Purpose

The ContextPacket is Cerebra's main agent-facing output.

A ContextPacket is a structured bundle of memory selected for a specific task, query, agent, or context window.

It should answer:

```text
What should the agent know right now?
Where did this information come from?
Why was it selected?
How reliable is it?
What was omitted?
How much context budget remains?
```

---

## 2. Core Doctrine

ContextPackets should be:

```text
source-grounded
retrieval-traceable
budget-aware
agent-readable
human-inspectable
uncertainty-aware
graph-aware
persistent when useful
```

A ContextPacket is not just pasted text.

It is structured context with provenance and selection reasons.

---

## 3. ContextPacket Flow

```text
agent/task request
  -> retrieval plan
  -> candidate retrieval
  -> scoring/reranking
  -> context budget allocation
  -> packet assembly
  -> packet storage
  -> agent delivery
  -> optional user inspection
```

---

## 4. ContextPacket Schema

Example:

```json
{
  "context_packet_id": "ctxpkt_123",
  "schema_version": 1,
  "created_at": 1710000000,
  "task": {
    "task_id": "task_123",
    "query": "Plan the Cerebra retrieval architecture.",
    "agent": "local_planner",
    "project": "Cerebra"
  },
  "budget": {
    "max_tokens": 12000,
    "estimated_tokens": 8400,
    "reserved_tokens": 2000
  },
  "selected_memory": [],
  "summaries": [],
  "graph_context": [],
  "uncertainties": [],
  "excluded_candidates": [],
  "retrieval_trace_id": "trace_123"
}
```

---

## 5. Selected Memory Item

Each selected memory item should include:

```json
{
  "memory_id": "mem_123",
  "source_id": "src_123",
  "chunk_id": "chunk_123",
  "memory_type": "project_context",
  "title": "Cerebra is the memory runtime",
  "content": "Cerebra owns memory and retrieval; LumaWeave owns graph visualization.",
  "summary": "Project responsibility boundary.",
  "score": 0.91,
  "score_components": {
    "semantic": 0.74,
    "lexical": 0.3,
    "project": 1.0,
    "salience": 0.9
  },
  "why_selected": [
    "same project",
    "high semantic match",
    "high salience"
  ],
  "provenance": {
    "source_path": "docs/CEREBRA_PROJECT_SCOPE.md",
    "section": "Relationship to LumaWeave"
  }
}
```

---

## 6. Packet Sections

Recommended sections:

```text
task
budget
selected_memory
source_summaries
graph_context
procedural_notes
uncertainties
excluded_candidates
retrieval_trace
```

---

## 7. Source Summaries

Source summaries provide compact context.

Example:

```json
{
  "source_id": "src_123",
  "summary": "This document defines Cerebra's project scope and boundaries.",
  "supporting_memory_ids": ["mem_1", "mem_2"],
  "confidence": 0.92
}
```

---

## 8. Graph Context

Graph context includes nearby relationships.

Example:

```json
{
  "node_id": "mem_123",
  "neighbors": [
    {
      "target_id": "mem_456",
      "relationship": "supports",
      "confidence": 0.88
    }
  ]
}
```

Graph context should be bounded by token budget.

---

## 9. Procedural Notes

Procedural memory tells an agent how to work.

Examples:

```text
Do not treat Policy Scout as Cerebra's core.
Preserve source provenance in all memory records.
Use hybrid retrieval before graph expansion.
Do not overwrite source records during consolidation.
```

Procedural notes should be high-confidence and sparse.

---

## 10. Uncertainties

ContextPackets should include uncertainty notes.

Examples:

```text
Some source files failed parsing.
Vector index is stale.
Graph relationships are low-confidence.
Archive records were not searched.
```

This prevents false certainty.

---

## 11. Excluded Candidates

Sometimes it is useful to record what was not included.

Fields:

```text
memory_id
score
reason_excluded
token_cost
```

Reasons:

```text
low score
duplicate
outside project scope
archived
too large for budget
lower confidence than selected summary
```

---

## 12. Retrieval Trace Link

ContextPackets should reference the retrieval trace.

The trace records:

```text
query
retrieval modes used
candidate counts
scores
filters
reranking
budget decisions
```

This makes context-window viewing possible.

---

## 13. Agent-Facing Rendering

Cerebra may render ContextPackets into plain text for agents.

Suggested layout:

```text
# ContextPacket

## Task

## Critical Context

## Supporting Memory

## Source Summaries

## Procedural Notes

## Uncertainties

## Retrieval Trace Summary
```

The structured JSON should still be preserved.

---

## 14. Context Window Viewer

A future viewer should show:

```text
what memory was included
why it was included
what sources support it
what was omitted
token budget usage
retrieval path
graph neighbors
uncertainties
```

This is one of Cerebra's differentiating features.

---

## 15. Packet Lifecycle

ContextPackets may have lifecycle states:

```text
ephemeral
stored
summarized
archived
deleted
```

Not every packet needs permanent retention.

But packets that influenced major actions should be retained or summarized.

---

## 16. MVP ContextPacket

Cerebra v0.1 should support:

```text
task/query
selected records
source provenance
score components
token estimate
retrieval trace ID
plain text rendering
JSON rendering
```

Graph context and excluded candidates can be basic.

---

## 17. ContextPacket Doctrine

A good ContextPacket lets the user ask:

```text
Why did the agent know this?
Why did it not know that?
What memory did it rely on?
What source supports this?
```

That is the core of inspectable agent memory.
