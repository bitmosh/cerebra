# Cerebra — Working Memory and Attention

## 1. Purpose

Working memory is the active mental workspace of Cerebra.

It is not the same as long-term memory.

It is not the same as the LLM context window.

It is the bounded, contested state that determines what the runtime is currently attending to.

---

## 2. Core Doctrine

Working memory should be:

```text
bounded
contested
salience-driven
inspectable
task-aware
interrupt-capable
source-grounded
eviction-aware
```

A system with no working memory is just retrieval plus prompting.

---

## 3. Working Memory Contents

Working memory may contain:

```text
active goal
current task
selected source memories
current hypotheses
recent outputs
open contradictions
important constraints
pending questions
active entities
user directives
interrupt candidates
```

---

## 4. Working Memory Slots

Use slots to keep working memory structured.

Initial slots:

```text
goal_slot
constraint_slot
context_slot
hypothesis_slot
evidence_slot
contradiction_slot
recent_output_slot
question_slot
procedure_slot
interrupt_slot
```

Slots can have capacity limits.

### 4.1 Default Slot Capacities

Initial capacity defaults. These are arbitrary starting points; adjust based on real cycle behavior.

```text
Slot                  Capacity   Rationale
goal_slot             1          One active goal at a time. Multiple goals fragment focus.
constraint_slot       4          Active constraints rarely exceed four; more should be hierarchical.
context_slot          7          Miller's classic working-memory limit; tunable per cycle.
hypothesis_slot       3          Tracks multiple competing hypotheses without combinatorial blowup.
evidence_slot         5          Enough to triangulate, not enough to drown.
contradiction_slot    2          Surfaces real tensions without distracting from primary task.
recent_output_slot    2          Last two outputs for self-comparison and revision.
question_slot         3          Open questions the cycle is actively pursuing.
procedure_slot        4          Active procedural knowledge — how the work is being done.
interrupt_slot        3          Salience-monitor interrupt candidates pending review.

TOTAL: 34 maximum attention items
```

Per-cycle configs may override defaults. The Bons.ai ideation cycle might want hypothesis_slot=5 (more divergent ideas competing); a planning cycle might want constraint_slot=8 (more constraints to track).

**Eviction policy when capacity is reached:**

```text
1. user-pinned items: non-evictable
2. items cited by truth tower: eviction-resistant (penalty applied)
3. lowest-salience non-pinned item evicted first
4. tie: oldest item evicted
```

---

## 5. Attention Items

An attention item is a memory candidate competing for working memory.

Fields:

```text
attention_id
memory_id
item_type
content_summary
source_ref
salience
slot_target
reason
expires_at optional
```

---

## 6. Contention

New attention items compete with existing items.

Signals:

```text
salience
task relevance
source authority
recency
prediction surprise
user pin
contradiction relevance
graph centrality
token cost
```

Items can be:

```text
accepted
deferred
summarized
evicted
ignored
promoted
```

---

## 7. Promotion

Items may be promoted into working memory when:

```text
high task relevance
user explicitly references them
prediction error is high
contradiction detected
current cycle needs them
graph expansion finds important neighbor
```

Promotion should be logged.

---

## 8. Eviction

Items may be evicted when:

```text
low salience
goal changes
token pressure
duplicate content
contradiction resolved
stale output
better summary replaces detail
```

Eviction does not delete long-term memory.

It only removes from active attention.

---

## 9. Interrupts

An interrupt is a high-salience item surfaced without an explicit query.

Examples:

```text
this contradicts an earlier decision
this project already solved a similar problem
the goal has drifted
a stronger source supersedes this memory
a pending user constraint is being violated
```

Interrupts should be introduced cautiously.

MVP can store interrupt candidates without automatically interrupting.

---

## 10. Working Memory and Context Windows

The context window is a rendering of working memory plus selected retrieval.

Working memory decides what should be considered.

ContextPacket decides what fits.

---

## 11. Attention Update Cycle

```text
new candidate arrives
  -> score salience
  -> choose target slot
  -> compare against existing slot items
  -> accept/promote/defer/evict
  -> update working memory
  -> emit attention event
```

---

## 12. Working Memory Events

Events:

```text
WorkingMemoryCreated
AttentionItemProposed
AttentionItemPromoted
AttentionItemEvicted
AttentionItemDeferred
InterruptCandidateCreated
WorkingMemoryRendered
WorkingMemoryCleared
```

---

## 13. MVP Scope

Cerebra v0.1 should implement:

```text
working memory record
basic slots
manual/update-by-runtime promotion
simple salience-based eviction
ContextPacket rendering from working memory
attention events
```

Automatic interrupts can wait.

---

## 14. Working Memory Doctrine

Working memory is where Cerebra starts to feel like it has attention.

Long-term memory says what exists.

Working memory says what matters right now.
