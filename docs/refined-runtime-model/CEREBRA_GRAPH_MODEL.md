# Cerebra — Graph Model

## 1. Purpose

This document defines Cerebra's graph-ready memory model.

Cerebra is not the graph viewer. LumaWeave owns graph visualization.

Cerebra owns the memory graph data:

```text
nodes
edges
relationship confidence
provenance
lifecycle state
retrieval relevance
```

The graph model should support retrieval, consolidation, inspection, and export.

---

## 2. Core Doctrine

The graph should be:

```text
source-grounded
confidence-aware
typed
queryable
exportable
lifecycle-aware
retrieval-useful
not visualization-specific
```

The graph exists to improve memory and make relationships inspectable.

It should not be designed only for pretty layouts.

---

## 3. Graph Responsibilities

Cerebra's graph model should support:

```text
entity relationships
source relationships
memory record relationships
topic clusters
project boundaries
summary support links
contradictions
duplicates
updates/supersession
retrieval expansion
LumaWeave export
```

---

## 4. Node Types

Initial node types:

```text
Source
Document
Chunk
MemoryRecord
Summary
Entity
Topic
Project
RelationshipClaim
ContextPacket
ArchivePackage
ScoutReport
```

Policy Scout appears only as an optional source type through `ScoutReport` or structured imported reports.

---

## 5. Edge Types

Initial edge types:

```text
CONTAINS
DERIVED_FROM
MENTIONS
SUPPORTS
CONTRADICTS
DUPLICATES
UPDATES
SUPERSEDES
BELONGS_TO
RELATED_TO
PART_OF
SUMMARIZES
USED_IN_CONTEXT
ARCHIVED_AS
RESTORED_FROM
```

Each edge should include:

```text
edge_id
source_node_id
target_node_id
edge_type
confidence
evidence
created_by
created_at
lifecycle_state
```

---

## 6. Source and Provenance Edges

Source provenance must be explicit.

Examples:

```text
Source CONTAINS Document
Document CONTAINS Chunk
MemoryRecord DERIVED_FROM Chunk
Summary SUMMARIZES MemoryRecord
```

No memory record should exist without a path back to source, unless it is explicitly marked as user-authored or system-generated.

---

## 7. Entity Nodes

Entities may include:

```text
person
project
tool
library
file
module
concept
organization
package
command
agent
system
```

Entity extraction should be confidence-aware.

Do not overtrust auto-extracted entities.

---

## 8. Topic Nodes

Topics represent thematic clusters.

Examples:

```text
hybrid retrieval
memory lifecycle
context windows
graph export
Policy Scout integration
LumaWeave bridge
```

Topic nodes can be created by:

```text
manual tagging
clustering
consolidation
summarization
user annotation
```

---

## 9. Project Nodes

Project nodes help scope memory.

Examples:

```text
Cerebra
LumaWeave
Policy Scout
Bons.ai
Echoes of the Glade
```

Project-scoped retrieval should prefer memories connected to the active project.

---

## 10. Summary Support Graph

Summaries should link to supporting records.

Example:

```text
ProjectSummary SUMMARIZES MemoryRecord A
ProjectSummary SUMMARIZES MemoryRecord B
ProjectSummary DERIVED_FROM Source C
```

This prevents summaries from becoming unsupported claims.

---

## 11. Contradiction Graph

Contradictions should be first-class.

Example:

```text
MemoryRecord A CONTRADICTS MemoryRecord B
```

Contradiction edge fields:

```text
confidence
reason
detected_by
review_status
preferred_record_id optional
```

Do not silently resolve major contradictions.

---

## 12. Duplicate Graph

Duplicates should be linked, not blindly deleted.

Example:

```text
MemoryRecord A DUPLICATES MemoryRecord B
```

Duplicate edge fields:

```text
similarity
method
confidence
canonical_record_id optional
```

Consolidation may recommend archiving duplicates.

---

## 13. Update / Supersession Graph

When newer memory updates older memory:

```text
MemoryRecord Newer UPDATES MemoryRecord Older
MemoryRecord Newer SUPERSEDES MemoryRecord Older
```

This helps retrieval prefer current records while preserving history.

---

## 14. Graph Confidence

Graph confidence should be explicit.

Confidence levels:

```text
low
moderate
high
confirmed
```

Numeric confidence can also be stored:

```text
0.0 to 1.0
```

Graph retrieval should prefer high-confidence edges unless the query asks for exploratory context.

---

## 15. Graph Lifecycle

Graph nodes and edges should respect lifecycle state.

States:

```text
active
warm
cold
archived
tombstoned
deleted
quarantined
```

Normal retrieval should exclude tombstoned/deleted/quarantined nodes.

Archived nodes may appear through retrieval cards or archive summaries.

---

## 16. Graph Expansion for Retrieval

Graph expansion should be bounded.

Parameters:

```text
max_depth
max_neighbors
edge_type_filter
min_edge_confidence
lifecycle_filter
project_scope
topic_scope
```

Default expansion should be conservative.

Example:

```text
Start from top 10 retrieved records.
Expand one hop through SUPPORTS, UPDATES, BELONGS_TO, RELATED_TO.
Exclude low-confidence and tombstoned edges.
```

---

## 17. Community / Cluster Graph

Cerebra can later create graph communities.

Community nodes may represent:

```text
topic clusters
project areas
source clusters
entity neighborhoods
archive packages
```

Community summaries can support global retrieval and DRIFT-like search.

---

## 18. LumaWeave Export

Graph export should include:

```text
nodes
edges
labels
types
weights
confidence
source references
lifecycle state
created_at
updated_at
```

Export format should be stable JSON.

Example:

```json
{
  "schema_version": 1,
  "nodes": [
    {
      "id": "mem_123",
      "type": "MemoryRecord",
      "label": "Cerebra owns memory runtime",
      "properties": {
        "project": "Cerebra",
        "lifecycle_state": "active",
        "salience": 0.92
      }
    }
  ],
  "edges": [
    {
      "id": "edge_123",
      "type": "SUPPORTS",
      "source": "mem_123",
      "target": "summary_456",
      "confidence": 0.88
    }
  ]
}
```

---

## 19. Graph Store

Initial graph storage can live in SQLite tables.

Tables:

```text
nodes
edges
node_properties
edge_properties
graph_exports
```

Do not require a graph database for v0.1.

A graph database can be evaluated later if needed.

---

## 20. Graph Events

Events:

```text
GraphNodeCreated
GraphEdgeCreated
GraphEdgeUpdated
GraphEdgeRejected
GraphCommunityCreated
GraphExported
GraphNodeArchived
GraphNodeTombstoned
```

---

## 21. MVP Graph Scope

Cerebra v0.1 should support:

```text
Source -> Document -> Chunk -> MemoryRecord provenance graph
Project membership edges
Summary support edges
basic related_to edges
basic graph export JSON
bounded graph expansion in retrieval
```

Contradiction and duplicate edges can be basic.

Community graph can come later.

---

## 22. Testing Requirements

Graph tests should cover:

```text
node creation
edge creation
provenance chain
lifecycle filtering
graph expansion bounds
summary support links
duplicate links
contradiction links
export JSON
tombstone exclusion
```

---

## 23. Graph Doctrine

Cerebra's graph is a memory structure first and a visualization source second.

If the graph helps retrieval, consolidation, and provenance, it belongs.

If it only makes a pretty picture, defer it to LumaWeave.
