# Cerebra — Memory Lifecycle

## 1. Purpose

This document defines how Cerebra manages memory over time.

Cerebra should not keep every memory equally hot forever.

It should cool, summarize, archive, tombstone, restore, or delete memory according to explicit lifecycle rules.

The goal is not accidental forgetting.

The goal is controlled memory maintenance.

---

## 2. Core Doctrine

Cerebra never forgets by accident.

Memory lifecycle should be:

```text
explicit
auditable
reversible where possible
source-grounded
retrieval-aware
user-respecting
tombstone-safe
archive-aware
```

Cold memory should become cheaper and quieter, not necessarily disappear.

---

## 3. Lifecycle States

Initial states:

```text
active
warm
cold
archived
tombstoned
deleted
quarantined
```

---

## 4. `active`

Active memory is fully available.

Behavior:

```text
normal retrieval
normal graph visibility
normal ContextPacket eligibility
normal consolidation eligibility
```

Use for:

```text
current projects
recent sources
high-salience facts
pinned user memories
frequently accessed records
```

---

## 5. `warm`

Warm memory is useful but less central.

Behavior:

```text
retrievable
slightly lower default salience
eligible for summaries
eligible for consolidation
visible in graph
```

Use for:

```text
older but useful project context
less frequently accessed notes
supporting details
```

---

## 6. `cold`

Cold memory is low-access or low-current-salience.

Behavior:

```text
retrievable through explicit or broad search
lower default ranking
candidate for archive summary
candidate for compression
```

Cold does not mean useless.

---

## 7. `archived`

Archived memory is compressed or moved out of hot retrieval.

Behavior:

```text
raw/source details preserved where configured
archive summary remains retrievable
retrieval card remains active/warm
graph stub remains visible
full restore possible if source still available
```

Archived memory should not be pulled into normal ContextPackets unless specifically relevant.

---

## 8. `tombstoned`

Tombstoned memory is intentionally suppressed.

Behavior:

```text
excluded from normal retrieval
excluded from ContextPackets
blocks accidental resurrection
keeps minimal marker
requires explicit restore to re-enable
```

Use for:

```text
user-deleted memory
known false memory
unsafe or poisoned source
superseded generated claims
privacy-sensitive suppressed memory
```

---

## 9. `deleted`

Deleted memory is physically removed where possible.

Behavior:

```text
raw record removed
indexes cleaned
relationships removed or invalidated
minimal deletion audit retained only if policy allows
```

Deletion should be explicit.

---

## 10. `quarantined`

Quarantined memory is isolated pending review.

Use for:

```text
malformed sources
possibly poisoned data
untrusted imports
security reports needing review
low-confidence automated extraction
```

Quarantined memory should not be used in normal agent context.

---

## 11. Lifecycle Scoring

Lifecycle decisions should use components.

Signals:

```text
access frequency
last accessed
source priority
project activity
user pin
salience
confidence
duplication
staleness
contradiction
sensitivity
replaceability
storage cost
retrieval noise
```

Do not archive or delete based only on last access.

---

## 12. Archive Packages

Archived clusters may produce archive packages.

Suggested structure:

```text
archive_package/
  manifest.cerebra.json
  source_bundle.zst or source_refs.json
  summary.md
  retrieval_card.md
  graph_stub.json
  provenance.json
  checksums.sha256
  restore_plan.json
```

For MVP, this can be represented logically rather than physically zipped.

---

## 13. Retrieval Cards

Every archive should have a retrieval card.

A retrieval card answers:

```text
What is in this archive?
Why was it archived?
What projects/topics/entities does it relate to?
When should Cerebra restore/search it?
What are the strongest keywords/entities?
What sources support it?
What warnings exist?
```

Retrieval cards remain searchable.

---

## 14. Graph Stubs

Archived memory should leave a graph stub.

Graph stub fields:

```text
archive_id
summary_id
source_count
record_count
related_entities
related_projects
lifecycle_state
restore_policy
```

This lets LumaWeave show that archived memory exists without loading all details.

---

## 15. Tombstone Records

Tombstones prevent accidental resurrection.

Tombstone fields:

```text
tombstone_id
target_ids
source_hashes
semantic_hashes
reason
created_at
created_by
scope
restore_policy
```

On re-ingestion, Cerebra should check tombstones.

If a new source matches tombstoned material, Cerebra should block or ask.

---

## 16. Restore Behavior

Restore should be explicit.

Restore paths:

```text
archive -> warm
archive -> active
tombstoned -> active only with explicit user action
quarantined -> active after review
```

Restores should log events.

---

## 17. Lifecycle Events

Events:

```text
MemoryActivated
MemoryWarmed
MemoryCooled
MemoryArchived
ArchiveSummaryCreated
RetrievalCardCreated
MemoryTombstoned
MemoryRestored
MemoryDeleted
MemoryQuarantined
```

Events should include reason and actor.

---

## 18. Consolidation Interaction

Consolidation may suggest lifecycle changes.

Examples:

```text
duplicate cluster -> archive duplicates
stale project notes -> cool or archive
contradicted records -> mark stale or contradicted
low-confidence extraction -> quarantine
```

Consolidation should recommend. Lifecycle manager should apply rules.

---

## 19. Retrieval Interaction

Retrieval should respect lifecycle state.

Default retrieval order:

```text
active
warm
cold
archived retrieval cards
```

Excluded by default:

```text
tombstoned
deleted
quarantined
```

Explicit search can include archived records.

Tombstoned records require special restore/admin path.

---

## 20. User Controls

Users should eventually be able to:

```text
pin memory
archive memory
restore archive
tombstone memory
delete memory
view lifecycle state
view why memory was archived
view retrieval cards
```

MVP can start with CLI commands.

---

## 21. MVP Lifecycle Scope

Cerebra v0.1 should support:

```text
active
archived
tombstoned
deleted marker
basic lifecycle events
manual archive
manual tombstone
manual restore from archive
retrieval exclusion for tombstones
```

Warm/cold automated transitions can come later.

---

## 22. Testing Requirements

Lifecycle tests should cover:

```text
active retrieval
archive summary retrieval
archive restore
tombstone exclusion
tombstone re-ingestion block
delete marker
lifecycle event creation
graph stub creation
retrieval card creation
```

---

## 23. Lifecycle Doctrine

Memory lifecycle is part of memory intelligence.

Cerebra should not just retrieve memory.

It should maintain memory.
