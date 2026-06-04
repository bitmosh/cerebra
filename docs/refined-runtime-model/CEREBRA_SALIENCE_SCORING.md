# Cerebra — Salience Scoring

## 1. Purpose

This document defines Cerebra's salience scoring model.

Salience determines how important or useful a memory is likely to be for a given task or over time.

Salience is not the same as vector similarity.

A memory can be semantically similar but low-salience.

A memory can be highly salient even if the query wording is different.

---

## 2. Core Doctrine

Salience should be:

```text
component-based
task-aware
project-aware
source-grounded
lifecycle-aware
confidence-aware
inspectable
tunable
```

Do not collapse too early into one opaque number.

---

## 3. Salience vs Similarity

Similarity answers:

```text
How close is this memory to the query?
```

Salience answers:

```text
How useful, important, reliable, current, and contextually appropriate is this memory right now?
```

Both matter.

---

## 4. Salience Components

Initial components:

```text
semantic_similarity
lexical_match
project_relevance
source_authority
recency
access_frequency
user_pin
relationship_centrality
confidence
lifecycle_state
task_relevance
summary_support
contradiction_penalty
staleness_penalty
sensitivity_penalty
```

---

## 5. Component Examples

### 5.1 Semantic Similarity

From vector search.

```text
Higher if meaning matches the query.
```

### 5.2 Lexical Match

From exact/keyword search.

```text
Higher for exact filenames, symbols, package names, IDs, and phrases.
```

### 5.3 Project Relevance

Higher when the memory belongs to the active project.

```text
query project: Cerebra
memory project: Cerebra
project_relevance: high
```

### 5.4 Source Authority

Higher for canonical docs, user-authored notes, and confirmed decisions.

Lower for speculative generated content.

### 5.5 Recency

Higher for recent records, but not blindly.

Old foundational decisions may remain high-salience.

### 5.6 Access Frequency

Higher for records frequently retrieved or used in ContextPackets.

### 5.7 User Pin

Pinned memory should receive a strong boost.

### 5.8 Relationship Centrality

Higher for memory connected to many important records or summaries.

### 5.9 Confidence

Higher for high-confidence extraction and source support.

### 5.10 Lifecycle State

Active/warm records rank higher than cold/archive records by default.

Tombstoned records are excluded.

### 5.11 Task Relevance

Higher when a memory is relevant to the current task type.

Example:

```text
implementation task -> code architecture records boosted
planning task -> roadmap/scope records boosted
debugging task -> error logs and recent traces boosted
```

### 5.12 Contradiction Penalty

Contradicted records should be lowered unless the task asks about conflicts.

### 5.13 Staleness Penalty

Stale or superseded records should be lowered.

### 5.14 Sensitivity Penalty

Sensitive records may require special handling or exclusion from agent context.

---

## 6. Salience Score Shape

Example:

```json
{
  "salience_score": 0.87,
  "components": {
    "semantic_similarity": 0.72,
    "lexical_match": 0.35,
    "project_relevance": 1.0,
    "source_authority": 0.9,
    "recency": 0.6,
    "access_frequency": 0.4,
    "user_pin": 0.0,
    "relationship_centrality": 0.7,
    "confidence": 0.92,
    "lifecycle_state": 1.0,
    "task_relevance": 0.85,
    "contradiction_penalty": 0.0,
    "staleness_penalty": 0.0,
    "sensitivity_penalty": 0.0
  }
}
```

---

## 7. Contextual Salience

Salience should depend on context.

The same memory may score differently for:

```text
coding task
planning task
debugging task
summarization task
project recap
security review
music/game brainstorm
```

The query planner should provide task hints.

---

## 8. Lifecycle Effects

Lifecycle state affects salience.

Suggested multipliers:

```text
active: 1.0
warm: 0.85
cold: 0.55
archived: retrieval card only by default
tombstoned: excluded
deleted: unavailable
quarantined: excluded unless review mode
```

---

## 9. Source Authority

Authority levels:

```text
user_directive
canonical_project_doc
user-authored_note
confirmed_report
source_chunk
generated_summary
speculative_inference
low-confidence_extraction
```

Generated summaries should not outrank canonical sources unless they are explicitly requested for compression.

---

## 10. Salience Decay

Decay should be careful.

Do not decay:

```text
pinned memory
canonical project boundaries
user preferences
high-authority decisions
```

Decay more readily:

```text
temporary working notes
old logs
intermediate agent outputs
low-confidence generated guesses
stale implementation details
```

Decay should reduce default ranking, not delete memory.

---

## 11. Access-Based Updates

When a memory is used in a successful ContextPacket, update access metadata.

Track:

```text
last_accessed_at
access_count
context_packet_count
task_types_used
user_feedback if available
```

Do not let access count alone dominate.

Frequently retrieved bad memory should not become trusted.

---

## 12. User Feedback

Future user feedback can adjust salience.

Feedback types:

```text
pin
unpin
mark useful
mark irrelevant
mark outdated
mark wrong
archive
tombstone
```

Feedback should create events.

---

## 13. Salience in ContextPacket Assembly

ContextPacket builder should use salience to decide:

```text
what to include directly
what to summarize
what to reference only
what to exclude
what to retrieve from archive
```

High-salience memory should still be balanced against token budget.

---

## 14. Salience in Consolidation

Consolidation can update salience.

Examples:

```text
summary created -> supporting records may cool
duplicate linked -> duplicate salience lowered
canonical record chosen -> canonical salience raised
contradiction found -> conflicted record salience adjusted
archive package created -> retrieval card salience raised
```

---

## 15. MVP Salience

Cerebra v0.1 should implement a simple component model:

```text
semantic_similarity
lexical_match
project_relevance
source_authority
recency
confidence
lifecycle_state
user_pin
```

Later:

```text
relationship_centrality
access_frequency
task_relevance
contradiction/staleness penalties
```

---

## 16. Testing Requirements

Salience tests should cover:

```text
same project boost
pinned memory boost
tombstone exclusion
archive lowering
source authority boost
low-confidence penalty
stale penalty
lexical exact match boost
semantic match boost
component visibility
```

---

## 17. Salience Doctrine

Salience is where Cerebra starts to feel less like search and more like memory.

But it must remain inspectable.

A user should be able to ask:

```text
Why did this memory get selected?
```

And Cerebra should have an answer.
