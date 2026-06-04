# Cerebra — State Governance

## 1. Purpose

This document defines how Cerebra should manage state.

Cerebra is a memory runtime. State must be careful, inspectable, recoverable, and versioned.

State governance matters because Cerebra will store durable user memory.

---

## 2. Core Doctrine

Cerebra state should be:

```text
local-first
schema-governed
event-aware
versioned
recoverable
auditable enough
not over-engineered
```

Cerebra should not adopt full event sourcing everywhere by default.

Use event logs where history and reconstruction matter.

Use current-state tables where direct reads matter.

---

## 3. State Categories

Cerebra has several kinds of state:

```text
source state
ingestion state
memory record state
index state
graph state
retrieval state
context packet state
consolidation state
lifecycle state
configuration state
```

Treat them differently.

---

## 4. Current State vs Event History

Cerebra should use both:

### Current State

Used for fast reads.

Examples:

```text
sources table
memory_records table
chunks table
relationships table
lifecycle_state
index metadata
```

### Event History

Used for traceability and reconstruction.

Examples:

```text
SourceRegistered
SourceParsed
MemoryRecordCreated
IndexUpdated
RetrievalPerformed
ContextPacketBuilt
ConsolidationRun
MemoryArchived
MemoryTombstoned
```

Do not make every read reconstruct from events in v0.1.

---

## 5. State Store Recommendation

Initial local storage:

```text
SQLite for structured state
file artifact store for raw/normalized data
vector index for embeddings
lexical index for text search
```

SQLite should track:

- sources
- normalized documents
- chunks
- memory records
- relationships
- lifecycle states
- events
- retrieval traces
- context packets
- consolidation runs
- graph exports

---

## 6. Schema Versioning

Every durable table/model should include schema version where useful.

Global metadata:

```text
cerebra_version
schema_version
created_at
last_migrated_at
```

Records:

```text
schema_version
created_at
updated_at
```

Schema migrations should be explicit.

---

## 7. Event Log

Cerebra should have a memory event log.

Event examples:

```text
SourceRegistered
SourceChanged
SourceParsed
SourceParseFailed
DocumentNormalized
ChunkCreated
MemoryRecordCreated
EmbeddingCreated
IndexUpdated
RelationshipCreated
RetrievalPerformed
ContextPacketBuilt
ConsolidationStarted
ConsolidationCompleted
MemoryArchived
MemoryTombstoned
MemoryDeleted
GraphExported
```

Events should include:

```text
event_id
event_type
timestamp
subject_id
actor
summary
data
```

---

## 8. State Transitions

Lifecycle transitions should be controlled.

Allowed transitions:

```text
active -> warm
warm -> cold
cold -> archived
archived -> warm
archived -> tombstoned
active -> tombstoned
tombstoned -> active only by explicit restore
tombstoned -> deleted only by explicit purge
```

Avoid silent deletion.

---

## 9. Idempotency

Ingestion and indexing should be idempotent where possible.

Use:

```text
source path
content hash
parser version
chunker version
embedding model version
schema version
```

If the same source and parser version have not changed, avoid duplicate records.

---

## 10. Index State

Indexes must track their own freshness.

Index metadata:

```text
index_id
index_type
model/version
created_at
updated_at
record_count
source_schema_version
status
```

If index state is stale, retrieval should know.

---

## 11. Retrieval Trace State

Retrieval traces should be stored at least optionally.

Trace records support:

- debugging
- context-window viewer
- agent behavior review
- retrieval quality tuning
- user trust

Trace retention can be configurable later.

---

## 12. ContextPacket State

ContextPackets should be stored when generated for agents.

Why:

```text
users can inspect what an agent saw
retrieval quality can be evaluated
agent decisions can be traced
future consolidation can learn from used context
```

ContextPackets can be pruned or summarized later.

---

## 13. Consolidation State

Consolidation should record:

```text
run_id
candidate records
method
summary output
records updated
records archived
relationships created
confidence
errors
```

Consolidation must be reversible enough for v0.1.

Do not overwrite sources.

---

## 14. Failure Behavior

State failures should degrade safely.

Examples:

```text
source parse failure -> store error and continue
embedding failure -> keep lexical retrieval available
vector index stale -> warn and use lexical/metadata
consolidation failure -> defer and keep original records
context packet failure -> return retrieval candidates with error
graph export failure -> do not affect core memory
```

---

## 15. Policy Scout Boundary

Policy Scout events are optional ingested sources.

If ingested, they should be treated as normal structured external/internal reports:

```text
source_type: policy_scout_report
memory_type: report_summary
```

They do not control Cerebra state.

---

## 16. State Governance Doctrine

Cerebra should not be mystical about memory.

Every durable memory should answer:

```text
Where did this come from?
When was it created?
What schema does it use?
What supports it?
How is it indexed?
What lifecycle state is it in?
What changed it?
```
