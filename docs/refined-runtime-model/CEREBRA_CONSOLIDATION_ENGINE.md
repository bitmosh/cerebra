# Cerebra — Consolidation Engine

## 1. Purpose

This document defines Cerebra's consolidation engine.

Consolidation is the process that turns accumulated records into useful, durable, lower-noise memory.

Without consolidation, Cerebra is just a searchable pile of chunks.

With consolidation, Cerebra can start to earn its name.

---

## 2. Core Doctrine

Consolidation should be:

```text
source-grounded
incremental
reversible where possible
confidence-aware
traceable
human-reviewable for high-impact changes
retrieval-improving
not destructive by default
```

Consolidation should never erase source truth.

---

## 3. What Consolidation Does

Consolidation may:

```text
detect duplicates
merge near-duplicates
summarize clusters
promote durable facts
detect contradictions
mark stale records
update salience
create relationship edges
create project summaries
create archive summaries
recommend lifecycle changes
```

---

## 4. What Consolidation Does Not Do

Consolidation should not:

```text
delete sources automatically
overwrite provenance
silently resolve contradictions
promote low-confidence claims as truth
tombstone user memory without policy/user action
hide uncertainty
```

---

## 5. Consolidation Flow

```text
trigger
  -> candidate selection
  -> grouping/clustering
  -> duplicate detection
  -> summary generation
  -> contradiction/staleness checks
  -> relationship updates
  -> salience updates
  -> lifecycle recommendations
  -> consolidation record
  -> optional human review
  -> write outputs
```

---

## 6. Consolidation Triggers

Triggers:

```text
after ingestion batch
after N new records
after project session
manual command
low retrieval quality signal
archive candidate detection
scheduled maintenance
before graph export
```

MVP should support manual and after-ingestion-batch consolidation.

---

## 7. Candidate Selection

Candidate selection should use:

```text
project
topic
entity
source
time window
high duplication
low salience
retrieval noise
user-selected group
```

Do not consolidate the whole vault by default.

---

## 8. Duplicate Detection

Duplicate signals:

```text
exact content hash
near text similarity
same source/section
same entity/topic
embedding similarity
same title/heading
same claim
```

Duplicate handling:

```text
keep best-supported record active
link duplicates
archive redundant copies
preserve provenance
```

---

## 9. Summary Generation

Summary types:

```text
document_summary
topic_summary
project_summary
session_summary
entity_summary
archive_summary
retrieval_card
```

Summaries should include:

```text
supporting_record_ids
source_ids
confidence
summary_method
created_at
```

A summary without supporting sources is not trusted memory.

---

## 10. Fact / Claim Promotion

Some memory can be promoted into durable statements.

Examples:

```text
Cerebra owns memory; LumaWeave owns visualization.
Policy Scout is optional safety/event source.
User prefers local-first systems.
```

Promotion requirements:

```text
multiple support signals or high-authority source
clear provenance
high confidence
not contradicted by newer source
```

Promoted claims should still link to support.

---

## 11. Contradiction Detection

Contradiction types:

```text
direct conflict
newer update supersedes older claim
different project boundary statements
conflicting user preference
conflicting implementation decision
```

Contradiction output:

```text
contradiction record
involved memory IDs
evidence
confidence
recommended resolution
```

Do not silently choose a winner unless policy says so.

---

## 12. Staleness Detection

Staleness signals:

```text
older than current project phase
contradicted by newer source
source marked deprecated
low recent access
outdated dependency/version reference
superseded decision
```

Stale memory can be:

```text
lower-ranked
marked stale
archived
summarized
linked to newer record
```

---

## 13. Salience Updates

Consolidation can update salience.

Signals:

```text
access frequency
recent retrieval use
user pin
source authority
project relevance
relationship centrality
summary inclusion
contradiction/staleness
```

Salience should remain component-based.

---

## 14. Relationship Updates

Consolidation can create/update graph edges.

Examples:

```text
supports
contradicts
duplicates
updates
derived_from
belongs_to
related_to
```

Edges should include:

```text
confidence
evidence
created_by
created_at
```

---

## 15. Lifecycle Recommendations

Consolidation may recommend:

```text
archive duplicate cluster
cool old project notes
tombstone false generated memory
restore archived memory due to renewed relevance
quarantine low-confidence import
```

Consolidation recommends. Lifecycle manager applies.

---

## 16. Consolidation Record

Each run should produce a record.

Example:

```json
{
  "consolidation_id": "con_123",
  "started_at": 1710000000,
  "completed_at": 1710000042,
  "trigger": "manual",
  "scope": {
    "project": "Cerebra",
    "records": 128
  },
  "outputs": {
    "summaries_created": 4,
    "relationships_created": 18,
    "duplicates_linked": 12,
    "lifecycle_recommendations": 6
  },
  "confidence": 0.84,
  "warnings": []
}
```

---

## 17. Human Review Boundaries

Human review should be required for:

```text
deletion
tombstoning high-salience memory
resolving major contradictions
promoting sensitive personal claims
large archive operations
source-of-truth changes
```

Automated consolidation can safely:

```text
suggest summaries
link duplicates
create low-risk relationships
recommend lifecycle changes
```

---

## 18. LLM Use in Consolidation

LLMs may help:

```text
summarize clusters
identify possible contradictions
draft retrieval cards
extract candidate claims
explain relationships
```

LLMs must not:

```text
delete source records
resolve high-impact contradictions alone
promote unsupported claims
hide uncertainty
```

LLM outputs should be marked as generated and linked to sources.

---

## 19. MVP Consolidation Scope

Cerebra v0.1 should support:

```text
manual consolidation command
duplicate detection by hash/text similarity
document summaries
project/topic summaries
archive retrieval cards
basic relationship creation
basic staleness marking
consolidation events
```

Contradiction detection can start simple.

---

## 20. Testing Requirements

Consolidation tests should cover:

```text
duplicate detection
summary source linking
archive retrieval card creation
relationship creation
stale marking
no source deletion
consolidation record creation
human-review boundary enforcement
```

---

## 21. Consolidation Doctrine

Consolidation is memory maintenance.

It should make retrieval better, context cleaner, and long-term memory more useful.

It should not pretend generated summaries are more authoritative than their sources.
