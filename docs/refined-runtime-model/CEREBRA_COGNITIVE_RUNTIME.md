# Cerebra — Cognitive Runtime

## 1. Purpose

The runtime is what makes Cerebra more than a memory system.

It executes configurable cognitive cycles, manages state, builds context, evaluates outputs, controls iteration, writes memory, and emits graph-native events.

---

## 2. Core Doctrine

The runtime should be:

```text
configurable
stateful
inspectable
signal-driven
memory-aware
graph-native
bounded
testable
```

Do not hardcode Cerebra to one specific agent loop.

---

## 3. Cycle Definition

A cycle definition is a declarative or semi-declarative description of a cognitive process.

Fields:

```text
cycle_id
name
purpose
input_schema
output_schema
agent_roles
step_order
allowed_actions
memory_scopes
metrics
clutch_rules
catalyst_options
stop_conditions
graph_events
```

---

## 4. Example Cycle: Bons.ai Ideation

```yaml
cycle_id: bonsai.ideation.v1
purpose: Generate, critique, improve, and evaluate ideas.
roles:
  - generator
  - critic
  - improver
steps:
  - build_context
  - generate
  - critique
  - improve
  - evaluate
  - clutch_decision
  - memory_write
  - graph_emit
stop_conditions:
  - accepted
  - max_passes
  - user_stop
```

Bons.ai becomes a config loaded by Cerebra, not Cerebra itself.

---

## 5. Runtime Execution Flow

```text
load cycle definition
  -> create runtime session
  -> initialize working memory
  -> build ContextPacket
  -> execute step
  -> capture output
  -> evaluate signals
  -> record prediction/outcome
  -> issue clutch decision
  -> update working memory
  -> write memory/event records
  -> continue/branch/stop
```

---

## 6. Runtime Session

A runtime session tracks one execution of a cycle.

Session fields:

```text
session_id
cycle_id
user_goal
project
started_at
completed_at
status
current_step
working_memory_id
context_packet_ids
event_ids
graph_event_ids
```

---

## 7. Step Execution

Each step should have:

```text
step_id
step_type
input
ContextPacket
output
metrics
errors
duration
memory_writes
graph_events
```

No major step should be invisible.

---

## 8. Signal Pipeline

Signals convert outputs into structured metrics.

Signal categories:

```text
quality
coherence
novelty
specificity
goal_alignment
contradiction
confidence
retrieval_quality
context_fit
surprise
progress_delta
```

Signals are componentized.

---

## 9. Clutch Controller

The clutch decides what the runtime should do next.

Possible actions:

```text
accept
refine
critique
explore
branch
retrieve_more
consolidate
ask_user
pause
stop
```

Inputs:

```text
signals
working_memory_state
cycle_phase
recent trajectory
prediction error
user constraints
mode
```

Output:

```text
action
intensity
reason
confidence
cooldown/hysteresis metadata
```

---

## 10. Catalyst / Strategy Selector

The catalyst selects cognitive transformation strategies.

Examples:

```text
exploration
refinement
disruption
analogy
structure
optimization
memory_integration
self_optimize
```

Use bandit-style learning only for non-critical strategy optimization.

Do not let learned strategy selection override user intent or safety boundaries.

---

## 11. Branching

The runtime may branch when signals suggest divergent promising paths.

Branch controls:

```text
max_branches
branch_reason
branch_parent
branch_score
merge_policy
```

Branches are graph-native events.

---

## 12. Runtime Failure Behavior

Failures should preserve state.

Examples:

```text
agent step fails -> record StepFailed
retrieval fails -> continue with reduced context if safe
evaluation fails -> use default metrics and mark uncertainty
memory write fails -> buffer or stop depending on severity
graph export fails -> keep event in outbox
```

Do not silently drop failed steps.

---

## 13. MVP Runtime Scope

Cerebra v0.1 should implement:

```text
one cycle definition format
one simple built-in cycle
runtime session records
ContextPacket use
signal evaluation v0
clutch action v0
memory write events
graph event export
```

Bons.ai compatibility can be a v0.2 target unless it is easy to express as a config.

---

## 14. Runtime Doctrine

Cerebra's runtime should make cognition inspectable.

Every cycle should leave behind a trail:

```text
goal
context
action
output
signal
decision
memory
graph event
```
