# Cerebra — Retrieval Architecture

## 1. Purpose

This document defines Cerebra's retrieval architecture.

Cerebra should not rely on a single retrieval method.

A strong memory runtime needs layered retrieval because different questions require different access paths.

Examples:

```text
exact filename or symbol -> lexical search
conceptual similarity -> vector search
project/topic constraints -> metadata filtering
multi-hop relationship question -> graph expansion
large corpus overview -> community/global summaries
agent context need -> ContextPacket assembly
```

---

## 2. Core Doctrine

Retrieval should be:

```text
hybrid
layered
traceable
source-grounded
graph-aware
salience-sensitive
rerankable
context-budget-aware
```

Do not treat vector search as the whole memory system.

Vector search is one retrieval signal.

---

## 3. Retrieval Layers

Initial retrieval layers:

```text
L1 lexical retrieval
L2 vector retrieval
L3 metadata filtering
L4 graph-neighborhood expansion
L5 summary/community retrieval
L6 salience scoring
L7 reranking
L8 ContextPacket assembly
```

---

## 4. Retrieval Flow

```text
query / task
  -> query planner
  -> lexical retrieval
  -> vector retrieval
  -> metadata filtering
  -> graph expansion
  -> summary/community retrieval
  -> salience scoring
  -> reranking
  -> context budget allocation
  -> ContextPacket
  -> retrieval trace
```

The retrieval trace is mandatory for inspectability.

---

## 5. Query Planner

The query planner decides which retrieval routes to use.

Inputs:

```text
query text
task type
agent role
project scope
time constraints
source filters
required precision
context budget
```

Possible retrieval modes:

```text
exact_lookup
hybrid_search
graph_expand
global_summary
local_detail
drift_search_like
context_refresh
archive_search
```

---

## 6. Lexical Retrieval

Lexical search is important for:

- exact names
- filenames
- code symbols
- package names
- error messages
- command snippets
- numeric values
- dates
- identifiers

Examples:

```text
"policy_scout"
"run_cycle"
"package-lock.json"
"ERR_MODULE_NOT_FOUND"
```

Lexical search should not be considered obsolete.

---

## 7. Vector Retrieval

Vector search is useful for:

- semantic similarity
- paraphrases
- conceptual matches
- vague recollection
- related ideas
- summaries
- long-form notes

Vector retrieval should return candidates with:

```text
memory_id
chunk_id
source_id
similarity
embedding_model
index_version
```

---

## 8. Hybrid Fusion

Cerebra should combine lexical and vector retrieval.

Initial fusion strategy:

```text
reciprocal rank fusion
```

or a simple weighted rank merge for MVP.

Hybrid retrieval reduces blind spots:

```text
lexical wins exact matches
vector wins semantic matches
hybrid covers both
```

---

## 9. Metadata Filtering

Metadata filters should be applied before or after retrieval depending on use case.

Metadata fields:

```text
project
source_type
file_type
created_at
modified_at
ingested_at
lifecycle_state
memory_type
confidence
author/source
tags
```

Examples:

```text
project == "Cerebra"
source_type == "markdown"
lifecycle_state in ["active", "warm"]
modified_at after date
```

---

## 10. Graph Expansion

Graph expansion retrieves related memory through relationships.

Useful relationships:

```text
mentions
supports
contradicts
updates
duplicates
belongs_to
derived_from
related_to
part_of
```

Graph expansion should be bounded.

Parameters:

```text
max_depth
max_neighbors
edge_type_filter
min_confidence
salience_threshold
```

Do not expand the whole graph by default.

---

## 11. Summary / Community Retrieval

For large corpora, Cerebra should support summary-level retrieval.

Summary layers:

```text
document_summary
topic_summary
project_summary
community_summary
archive_summary
```

This helps answer broad questions without pulling hundreds of chunks.

---

## 12. DRIFT-Like Retrieval

Cerebra can later implement a DRIFT-like mode:

```text
start with local query focus
pull relevant community summaries
generate follow-up retrieval questions
expand into local supporting evidence
assemble answer/context from both global and local memory
```

This is not required for MVP, but the architecture should leave room for it.

---

## 13. Salience Scoring

Salience is not the same as similarity.

Signals:

```text
similarity score
lexical score
recency
source priority
user-pinned memory
project relevance
relationship centrality
access frequency
confidence
lifecycle state
task relevance
```

Salience should be component-based.

Do not collapse too early.

---

## 14. Reranking

Reranking should operate after candidate fusion.

Possible reranking inputs:

```text
query
candidate text
summary
metadata
source priority
graph distance
salience components
```

Initial MVP can use a deterministic reranker.

Later versions may use:

```text
cross-encoder reranker
LLM reranker
learned reranker
```

Reranking must preserve traceability.

---

## 15. Context Budget Allocation

ContextPacket assembly should budget tokens.

Budget buckets:

```text
task instructions
high-salience records
supporting chunks
summaries
graph neighborhood
uncertainty notes
source citations
```

If budget is tight, include summaries plus references.

If budget is large, include direct supporting chunks.

---

## 16. Retrieval Trace

Every retrieval should produce a trace.

Trace fields:

```text
query
retrieval_mode
lexical_candidates
vector_candidates
metadata_filters
graph_expansions
summary_candidates
salience_scores
rerank_scores
selected_items
excluded_items
token_budget
```

Users should eventually be able to inspect this in a context-window viewer.

---

## 17. Archive-Aware Retrieval

Archived records should not disappear completely.

Default behavior:

```text
active/warm records -> normal retrieval
cold/archived records -> lower priority
tombstoned records -> excluded unless explicit admin/debug mode
deleted records -> unavailable
```

Archive summaries can represent cold clusters.

---

## 18. Retrieval Output

Retrieval should return candidates, not just text.

Candidate shape:

```json
{
  "memory_id": "mem_123",
  "source_id": "src_123",
  "chunk_id": "chunk_123",
  "score": 0.84,
  "score_components": {
    "lexical": 0.3,
    "vector": 0.7,
    "recency": 0.2,
    "graph": 0.4,
    "salience": 0.8
  },
  "why_selected": [
    "semantic match",
    "same project",
    "connected to selected entity"
  ]
}
```

---

## 19. MVP Retrieval

Cerebra v0.1 retrieval should include:

```text
lexical search
vector search
metadata filtering
simple fusion
basic salience scoring
ContextPacket output
retrieval trace
```

Graph expansion can be basic.

Community/global retrieval can come later.

---

## 20. Retrieval Doctrine

Cerebra should retrieve memory the way a good assistant thinks:

```text
find exact anchors
find conceptual neighbors
filter by context
expand through relationships
prefer salient and trustworthy records
fit the result into the current context budget
show the trace
```
