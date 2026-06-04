# Cerebra — Architecture

## 1. Purpose

This document defines Cerebra as a local-first cognitive runtime.

The previous memory-backend framing was useful but too narrow. This architecture keeps ingestion, retrieval, lifecycle, and graph export, but places them inside a broader runtime that can run configurable cognitive cycles.

---

## 2. System Spine

```text
Cycle Definition
  -> Runtime Planner
  -> Working Memory
  -> Retrieval / ContextPacket
  -> Cognitive Step Execution
  -> Signal Evaluation
  -> Clutch / Control Decision
  -> Memory Write
  -> Consolidation
  -> Prediction Update
  -> Graph Event Emission
```

---

## 3. High-Level Components

```text
Cycle Definition Registry
Cognitive Runtime
State Store
Working Memory Manager
Retrieval Engine
ContextPacket Builder
Capability Router
Signal Pipeline
Clutch Controller
Catalyst / Action Selector
Prediction Engine
Consolidation Engine
Memory Lifecycle Manager
Graph Event Writer
Source Ingestion System
LumaWeave Exporter
```

---

## 4. Cycle Definition Registry

Cerebra should run configurable cognitive cycles.

A cycle definition describes:

```text
cycle_id
purpose
agent roles
step order
allowed actions
input schema
output schema
metrics
memory scopes
tool/capability requirements
stop conditions
graph emission contract
```

Example cycle definitions:

```text
bonsai.ideation.v1
research_synthesis.v1
code_review.v1
planning_review.v1
decision_analysis.v1
```

Bons.ai becomes one cycle definition.

---

## 5. Cognitive Runtime

The runtime executes cycle definitions.

Responsibilities:

```text
load cycle config
initialize state
build ContextPackets
dispatch steps
collect outputs
evaluate metrics
update state
call clutch/controller
write memory events
emit graph-native events
stop or continue
```

The runtime is not hardcoded to one agent loop.

---

## 6. State Store

The state store owns durable runtime state.

State categories:

```text
cycle state
session state
working memory state
memory record state
retrieval trace state
evaluation state
prediction state
consolidation state
graph emission state
```

Use current-state tables for fast reads and event history for traceability.

---

## 7. Working Memory Manager

Working memory is a bounded contested space.

It tracks:

```text
active task
current goals
active hypotheses
selected memories
recent outputs
open contradictions
pending questions
interrupt candidates
```

Working memory is not just the LLM context window.

The context window is one rendering of working memory.

---

## 8. Retrieval Engine

The retrieval engine supports:

```text
lexical search
vector search
metadata filtering
graph expansion
summary retrieval
salience scoring
reranking
archive-aware retrieval
```

Retrieval returns candidate memory records with score components and trace.

---

## 9. ContextPacket Builder

The ContextPacket builder turns memory candidates into agent-ready context.

It includes:

```text
selected records
source provenance
working memory state
cycle instructions
procedural memory
uncertainties
token budget
retrieval trace
```

ContextPackets should be stored or summarized so users can inspect what agents saw.

---

## 10. Capability Router

The capability router chooses which cognitive capability or cycle step to invoke.

Examples:

```text
retrieve
summarize
critique
generate
compare
score
consolidate
branch
ask_question
write_graph_event
```

This is not a shell permission system.

Command safety belongs to Policy Scout if command execution becomes relevant.

---

## 11. Signal Pipeline

The signal pipeline converts outputs into structured metrics.

Signals may include:

```text
coherence
novelty
usefulness
specificity
contradiction
goal_alignment
confidence
surprise
progress_delta
retrieval_quality
context_fit
```

Signals should remain componentized.

Do not collapse early into one vague score.

---

## 12. Clutch Controller

The clutch is a reusable control primitive.

It reads state and signals, then returns an explainable control action.

Examples:

```text
accept
refine
critique
branch
explore
consolidate
pause
ask_user
retrieve_more
stop
```

The clutch should use:

```text
priority rules
multi-signal input
hysteresis
mode persistence
no-flapping behavior
```

---

## 13. Catalyst / Action Selector

The catalyst chooses cognitive transformation strategies under uncertainty.

Examples:

```text
exploration
refinement
disruption
analogy
structure
optimization
memory_integration
```

It can use bandit-style learning for non-critical strategy selection.

It should not override safety or user intent.

---

## 14. Prediction Engine

Cerebra should record predictions about its own outputs.

Prediction examples:

```text
expected coherence
expected improvement
expected user usefulness
expected retrieval relevance
expected need for consolidation
expected risk of goal drift
```

After a step, Cerebra records prediction error.

Prediction error becomes a learning signal.

---

## 15. Consolidation Engine

Consolidation converts episodic cycle history into durable semantic/procedural memory.

It creates:

```text
session summaries
project summaries
pattern notes
contradiction records
updated procedures
archive summaries
graph relationships
```

Consolidation may run after cycles or during quiescent periods.

---

## 16. Graph Event Writer

Cerebra emits graph-native records.

Events:

```text
CycleStarted
StepExecuted
ContextPacketBuilt
MemoryRetrieved
SignalEvaluated
ClutchDecisionIssued
PredictionMade
PredictionErrorRecorded
MemoryConsolidated
RelationshipCreated
CycleCompleted
```

LumaWeave consumes/visualizes these.

---

## 17. Async Runtime Boundary

Async behavior should be introduced in phases.

Initial v0.1:

```text
foreground cycle only
manual consolidation
manual retrieval
```

Later:

```text
background salience monitor
quiescent consolidation
interrupt candidates
stale memory detection
goal drift monitor
```

Avoid async complexity before the deterministic spine works.

---

## 18. Architecture Doctrine

Cerebra should be built around one senior-dev rule:

```text
Every cognitive action must leave behind structured state: input, context, output, signal, control decision, memory write, and graph event.
```

If a step cannot be inspected later, it is not mature enough for Cerebra.
