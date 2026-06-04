# Cerebra — Project Scope

## 1. Purpose

Cerebra is a local-first cognitive runtime.

It runs configurable cognitive cycles, maintains durable state and memory, manages working context, evaluates signals, consolidates experience, learns from prediction error, and emits graph-native records that LumaWeave can visualize.

Cerebra is not merely a folder watcher.

Cerebra is not merely a RAG layer.

Cerebra is not merely a graph export tool.

Cerebra is the runtime that decides what memory matters, what cognitive process is active, what context should be held in mind, what should be consolidated, and what should be emitted as structured graph-native evidence.

---

## 2. One-Liner

```text
Cerebra is a local-first cognitive runtime for configurable agent cycles, durable memory, contested working context, salience-based retrieval, consolidation, prediction-error learning, and graph-native event emission.
```

Shorter:

```text
Cerebra is the runtime that remembers, attends, evaluates, consolidates, and decides what cognitive process should happen next.
```

---

## 3. Core Identity

Cerebra has five core responsibilities:

```text
1. Runtime
2. Memory
3. Attention
4. Synthesis
5. Graph-native state
```

### 3.1 Runtime

Cerebra runs cognitive process definitions.

Examples:

```text
three-agent ideation cycle
code-review cycle
research-synthesis cycle
decision-analysis cycle
planning cycle
debugging cycle
```

Bons.ai becomes one possible cycle configuration, not the whole engine.

### 3.2 Memory

Cerebra stores and retrieves source-grounded memory.

Memory includes:

```text
source documents
episodic cycle events
semantic summaries
procedural rules
project decisions
prediction records
evaluation signals
graph relationships
```

### 3.3 Attention

Cerebra manages what is currently "in mind."

This means contested working memory, token budgets, salience, promotion, eviction, and interrupt candidates.

### 3.4 Synthesis

Cerebra reads across cycles and sessions.

It can detect:

```text
patterns
contradictions
goal drift
rediscovered ideas
stale decisions
productive next questions
```

### 3.5 Graph-Native State

Cerebra writes structured state and event records that LumaWeave can visualize.

LumaWeave shows the graph.

Cerebra produces, reads, and interprets graph-native memory.

---

## 4. Product Boundary

### Bons.ai

Bons.ai is a reference cognitive cycle.

It contains useful patterns:

```text
clutch
router
catalyst
signal pipeline
bandit selection
reward dynamics
branching
```

Cerebra should extract these as runtime-level primitives.

Bons.ai should eventually be expressible as:

```text
Cerebra running the Bons.ai ideation cycle config.
```

### LumaWeave

LumaWeave is the graph visualization and exploration layer.

It does not own cognitive state.

It does not decide what memory means.

Cerebra emits graph-native data; LumaWeave visualizes it.

### Policy Scout

Policy Scout is a local-first safety harness.

Policy Scout reports/events may later be ingested as Cerebra source material.

Policy Scout is optional and not required for Cerebra's core.

---

## 5. What Cerebra Owns

Cerebra owns:

```text
cycle definition schema
cycle runtime execution
state schema and persistence
working memory management
salience scoring
retrieval and ContextPacket assembly
signal pipeline
clutch/controller primitives
catalyst/action-selection primitives
prediction and prediction-error records
consolidation
cross-session synthesis
graph-native event emission
memory lifecycle
source-grounded ingestion
```

---

## 6. What Cerebra Does Not Own

Cerebra does not own:

```text
graph visualization UI
package install sandboxing
command permission enforcement
full endpoint security
general-purpose chat UI
web crawling as a core feature
every possible parser format in v0.1
```

---

## 7. The Real Differentiator

A simple memory system can answer:

```text
What did I store that matches this query?
```

Cerebra should answer:

```text
What does this system currently know?
What is it paying attention to?
What cognitive process is active?
What has changed across cycles?
What predictions did it make?
What surprised it?
What should be consolidated?
What should be surfaced to the agent now?
What should LumaWeave visualize as meaningful structure?
```

---

## 8. MVP Principle

The MVP should prove Cerebra as a runtime, not only a retrieval store.

The first prototype should show:

```text
load a cycle definition
ingest a few docs
retrieve source-grounded memory
build a ContextPacket
run one small cognitive step
score outputs with signal components
update working memory
write graph-native cycle events
create one consolidation summary
export graph JSON
```

---

## 9. Language Discipline

Allowed:

```text
cognitive runtime
working memory
salience
attention
prediction error
consolidation
cycle definition
graph-native event
```

Avoid overclaiming:

```text
sentient
conscious
self-aware
alive
```

Cerebra can behave in cognition-shaped ways without making claims about subjective experience.

---

## 10. Project Doctrine

Cerebra should earn its name through behavior:

```text
it remembers
it retrieves
it attends
it evaluates
it predicts
it consolidates
it notices contradictions
it emits inspectable structure
```
