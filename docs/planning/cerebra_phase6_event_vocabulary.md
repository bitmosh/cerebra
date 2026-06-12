# Cerebra Phase 6 — Cycle Runtime Event Vocabulary

*Specification of all event types Cerebra's cycle runtime emits during Phase 6. Each event has required and optional payload fields, a determinism flag, named causation relationships, and indexed_tags recommendations for cross-stream queries. This document is the contract Cerebra's Phase 6 code emits against and Lattica Claude documents in AGENT_TRACE_VOCABULARY.md for cross-project visibility.*

---

## Scope and conventions

This document covers the cycle runtime extension event types. It does NOT cover:

- Pre-Phase-6 cognitive events (ingest, classification, retrieval, working memory, tower) — those continue using `inspector_events` schemas
- Lattice aggregate events — separate document forthcoming for the addendum-scoped events
- The five standard agent-trace types fossic ships (`llm_call`, `llm_response`, `tool_call`, `tool_result`, `reasoning_step`) — those are fossic-owned

The events specified here write to streams matching `cerebra/agent-trace/<cycle_id>` per the locked stream pattern.

### Naming convention

PascalCase event type names. Past-tense verbs (event reports something that happened, not something that will happen).

### Determinism flag

`deterministic: true` events have payloads that are functions of their causation chain — replaying the causation chain produces identical payload. `deterministic: false` events have payloads that depend on non-deterministic processes (LLM output, real-time data, stochastic decisions).

Most cycle runtime events are `deterministic: false` because they observe non-deterministic LLM behavior or stochastic Catalyst decisions. State-transition bookkeeping events (CycleStarted, CycleCompleted, SessionOpened) are `deterministic: true`.

### Causation

Each event names its causation parent — the event whose completion enabled this event. Causation chains anchor the cycle's execution graph for replay, OTel span construction, and counterfactual exploration.

### Indexed tags

`indexed_tags` recommendations identify fields that should be promoted to the events table's indexed_tags JSON column (per Lattica Claude's spec confirmation) for efficient cross-stream queries. Examples: querying all events for a session, all events for a cycle config type, all events where a specific signal scored low.

## Event types

### Session and cycle lifecycle

#### `SessionOpened`

Marks the start of a runtime session. Each session corresponds to one fossic stream.

**Required payload:**
- `session_id: str` — UUID, also the stream's `cycle_id` segment
- `goal: str` — the user-provided goal
- `cycle_config: str` — name of the cycle config used (e.g., `simple.planning.v0`)
- `vault_path: str` — vault root path
- `opened_at: int` — Unix epoch milliseconds

**Optional payload:**
- `parent_session_id: str | null` — for re-injection continuations; null for fresh sessions
- `recursion_depth: int` — 0 for fresh sessions; increments per re-injection
- `max_recursion_depth: int` — configurable cap, default 5

**Determinism:** `true` — pure bookkeeping

**Causation:** none (root event of session stream)

**Indexed tags:** `session_id`, `cycle_config`, `recursion_depth`, `parent_session_id`

---

#### `CycleStarted`

Marks the start of a cognitive cycle within a session. Bookend pair with `CycleCompleted`.

**Required payload:**
- `session_id: str`
- `cycle_id: str` — the matching `<cycle_id>` from the stream pattern
- `cycle_config: str`
- `started_at: int` — Unix epoch milliseconds

**Optional payload:**
- `step_index: int` — for cycles within a session; default 0

**Determinism:** `true` — pure bookkeeping

**Causation:** `SessionOpened` for the parent session

**Indexed tags:** `session_id`, `cycle_id`, `cycle_config`

---

#### `CycleCompleted`

Marks the end of a cognitive cycle. Bookend pair with `CycleStarted`.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `completed_at: int` — Unix epoch milliseconds
- `outcome: str` — one of `accept`, `stop`, `branched`, `continued`
- `total_steps: int` — number of steps executed in this cycle

**Optional payload:**
- `branched_to_cycle_id: str | null` — if outcome is `branched`
- `continued_to_session_id: str | null` — if outcome is `continued` (re-injection)

**Determinism:** `true` — pure bookkeeping derived from cycle execution

**Causation:** `CycleStarted` for the same cycle_id

**Indexed tags:** `session_id`, `cycle_id`, `outcome`

---

### Step execution

#### `StepStarted`

Marks the start of one cognitive step within a cycle. A cycle may execute many steps.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str` — UUID for this step
- `step_index: int` — 0-based ordinal within the cycle
- `started_at: int`

**Optional payload:**
- `step_type: str` — `generate`, `refine`, `critique`, `explore` (matches Clutch action vocabulary)

**Determinism:** `true` — bookkeeping

**Causation:** Most recent `ClutchDecisionMade` in the cycle that selected this step (or `CycleStarted` for first step)

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `step_type`

---

#### `ContextPacketBuilt`

The retrieval pipeline assembled the ContextPacket for this step. Note: ContextPacketBuilt also exists in pre-Phase-6 retrieval flow; the Phase 6 version is emitted in cycle context with cycle_id.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `packet_id: str`
- `selected_count: int` — number of memories selected
- `packet_version: int`

**Optional payload:**
- `abstained: bool` — true if retrieval abstained; selected_count would be 0
- `abstention_reason: str | null`

**Determinism:** `false` — retrieval involves embedding similarity which has model dependencies

**Causation:** `StepStarted`

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `abstained`

---

#### `StepExecuted`

The cognitive step ran (LLM produced output). Captures the step's input and output.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `executed_at: int`
- `llm_model: str` — e.g., `granite-4.1-3b-instruct`
- `prompt_tokens: int`
- `completion_tokens: int`
- `output_text: str` — the LLM's structured output

**Optional payload:**
- `latency_ms: int`
- `temperature: float`
- `top_p: float`

**Determinism:** `false` — LLM output is non-deterministic

**Causation:** `ContextPacketBuilt` for the same step

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `llm_model`

---

### Prediction and evaluation

#### `PredictionMade`

Before a step executes, a prediction is recorded about expected output quality.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `prediction_id: str`
- `expected_composite_score: float` — 0.0 to 1.0
- `expected_per_signal: dict[str, float]` — predicted score per signal
- `prediction_basis: str` — `prior_step_trajectory`, `cycle_config_default`, `static_baseline`

**Optional payload:**
- `confidence: float` — confidence in the prediction itself, 0.0 to 1.0

**Determinism:** `false` — depends on prior cycle state

**Causation:** `StepStarted` for the same step

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `prediction_basis`

---

#### `SignalEvaluated`

One signal scored the step's output. Six of these fire per step (one per signal in the six-signal epistemology).

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `signal_name: str` — one of `COHERENCE`, `GROUNDEDNESS`, `GENERATIVITY`, `RELEVANCE`, `PRECISION`, `EPISTEMIC_HUMILITY`
- `signal_score: float` — 0.0 to 1.0
- `evaluator_prompt_version: str` — versioned prompt template ID
- `evaluated_at: int`

**Optional payload:**
- `signal_strength: float` — confidence in the score itself; v0.1 may default to 1.0
- `checklist_details: dict | null` — per-checklist-item ratings if expanded evaluation
- `low_confidence: bool` — true if signal_strength below threshold

**Determinism:** `false` — LLM-based evaluation

**Causation:** `StepExecuted` for the same step

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `signal_name`, `low_confidence`

---

#### `EvaluationComposed`

The six signals were composed into a composite evaluation per the weighted formula.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `evaluation_id: str`
- `composite_score: float` — `Σ(signal_i × weight_i)`, 0.0 to 1.0
- `per_signal_scores: dict[str, float]` — final scores after composition
- `weights_used: dict[str, float]` — weights applied (may differ from defaults per cycle config)
- `composed_at: int`

**Optional payload:**
- `confidence: float` — system's claim about evaluation reliability
- `composite_floor_violated: bool` — true if composite fell below cycle config floor

**Determinism:** `true` — pure function of SignalEvaluated outputs and weights

**Causation:** Most recent `SignalEvaluated` for the step (chains back through all six)

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `composite_floor_violated`

---

#### `OutcomeRecorded`

Compares the prediction to the actual evaluation, computes prediction error.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `outcome_id: str`
- `prediction_id: str` — links to the matching PredictionMade
- `actual_composite_score: float`
- `prediction_error: float` — `actual - expected`
- `error_classification: str` — `noise` (|err| < 0.10), `notable` (0.10-0.40), `severe` (> 0.40)
- `recorded_at: int`

**Optional payload:**
- `per_signal_error: dict[str, float]` — error per signal

**Determinism:** `true` — pure subtraction of EvaluationComposed and PredictionMade

**Causation:** `EvaluationComposed` for the step

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `error_classification`

---

#### `PredictionSevereMiss`

Emitted alongside OutcomeRecorded when error_classification is `severe`. Allows specific subscriber attention to severe misses.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `outcome_id: str`
- `prediction_error: float`
- `expected: float`
- `actual: float`

**Determinism:** `true` — derived from OutcomeRecorded

**Causation:** `OutcomeRecorded` for the step

**Indexed tags:** `session_id`, `cycle_id`, `step_id`

---

### Control decisions

#### `ClutchDecisionMade`

The Clutch evaluated signals plus prediction error plus working memory state and produced a typed action decision.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `decision_id: str`
- `action: str` — one of `accept`, `refine`, `critique`, `explore`, `branch`, `retrieve_more`, `consolidate`, `ask_user`, `pause`, `stop`
- `rule_matched: str` — name of the Clutch rule that fired
- `decided_at: int`

**Optional payload:**
- `cascade_depth: int` — how many rules were evaluated before one fired
- `escalate_to_catalyst: bool` — true if action requires Catalyst arm selection
- `evaluation_id: str` — links to the EvaluationComposed that informed the decision

**Determinism:** `true` — Clutch is a deterministic cascade given identical inputs

**Causation:** `OutcomeRecorded` (or `EvaluationComposed` if no prediction was made)

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `action`, `escalate_to_catalyst`

---

#### `CatalystInvoked`

The Catalyst was called to select a strategy when Clutch escalated.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `invocation_id: str`
- `vocabulary_size: int` — number of arms in the catalyst vocabulary for this cycle config
- `invoked_at: int`

**Optional payload:**
- `triggering_clutch_decision_id: str` — links to the ClutchDecisionMade that escalated
- `leeway_filtered_vocabulary_size: int` — vocabulary size after leeway pre-filtering

**Determinism:** `true` — bookkeeping

**Causation:** `ClutchDecisionMade` with `escalate_to_catalyst: true`

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `invocation_id`

---

#### `CatalystArmSelected`

The Catalyst's bandit selected a strategy arm.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `invocation_id: str`
- `arm_name: str` — selected strategy
- `arm_score: float` — the multi-factor score that contributed to selection
- `selection_method: str` — `weighted_random` for v0.1 (proper bandit deferred to v0.2)
- `selected_at: int`

**Optional payload:**
- `arm_stats_pre: dict | null` — arm's stats before this selection (for replay)
- `tau: float` — temperature parameter if used
- `all_arm_scores: dict[str, float]` — full distribution for diagnostic purposes

**Determinism:** `false` — weighted_random sampling is stochastic

**Causation:** `CatalystInvoked` for the same invocation_id

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `arm_name`

---

### Safety gate

#### `LeewayGrantApplied`

The leeway pre-action gate evaluated the proposed action and applied grants from the loaded leeway rules.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `proposed_action: str` — the action being evaluated
- `grants_applied: list[str]` — names of leeway rules that granted permission
- `final_decision: str` — `permitted`, `requires_review`, `forbidden`
- `applied_at: int`

**Optional payload:**
- `forbidden_by: str | null` — rule that forbade if final_decision is `forbidden`
- `review_required_by: list[str]` — rules requiring HITL review if applicable

**Determinism:** `true` — leeway rules are deterministic composition-by-union

**Causation:** `ClutchDecisionMade` (or `CatalystArmSelected` if catalyst was invoked) — fires BEFORE the action executes per the causal ordering requirement

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `final_decision`

---

### Re-injection

#### `ContinuationBundleCreated`

A ContinuationBundle was distilled from the current cycle state for re-injection.

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `bundle_id: str`
- `distilled_goal: str`
- `summarized_prior_prompt: str`
- `truth_tower_projection: dict` — `{t5_goal, t4_hypotheses?, t3_insights, t2_citations, t1_citations}`
- `cognitive_insights: list[str]`
- `next_focus: str`
- `open_questions: list[str]`
- `constraints: list[str]`
- `recursion_depth: int`
- `bundle_size_bytes: int`
- `created_at: int`

**Optional payload:**
- `voice_mode: str` — `system` for v0.1 (`self` deferred)
- `truncation_applied: bool` — true if bundle hit size cap and was compressed

**Determinism:** `true` — bundle is a deterministic distillation of cycle state

**Causation:** Most recent `ClutchDecisionMade` (with action implying continuation) or context budget exhaustion trigger

**Indexed tags:** `session_id`, `cycle_id`, `bundle_id`, `recursion_depth`

---

#### `ReinjectionTriggered`

A new continuation session is being spawned from a ContinuationBundle.

**Required payload:**
- `session_id: str` — the parent session
- `cycle_id: str` — the parent cycle
- `bundle_id: str` — the ContinuationBundle being used
- `child_session_id: str` — the new session about to open
- `trigger_reason: str` — `context_budget`, `clutch_spawn`, `explicit_continuation`
- `triggered_at: int`

**Optional payload:**
- `recursion_cap_hit: bool` — true if this was the last allowed continuation

**Determinism:** `true` — bookkeeping

**Causation:** `ContinuationBundleCreated` for the same bundle_id

**Indexed tags:** `session_id`, `cycle_id`, `bundle_id`, `child_session_id`, `trigger_reason`

---

### Working memory and tower updates from cycle context

These events update working memory and tower state as a result of cycle actions. They emit alongside the existing Phase 5 working memory events but carry cycle_id for cycle traceability.

#### `MemoryWriteFromCycle`

The cycle wrote new content to memory (episodic memory of cycle output).

**Required payload:**
- `session_id: str`
- `cycle_id: str`
- `step_id: str`
- `record_id: str` — new memory record created
- `write_reason: str` — `accept`, `consolidate`, `branch_anchor`
- `content_summary: str`
- `written_at: int`

**Optional payload:**
- `source_lineage: list[str]` — record IDs whose content contributed to this write

**Determinism:** `false` — content depends on LLM output

**Causation:** `ClutchDecisionMade` with action `accept` or `consolidate`

**Indexed tags:** `session_id`, `cycle_id`, `step_id`, `record_id`, `write_reason`

---

#### `SessionFlushed`

Session ending event, written when Clutch action is `stop`. Signals that working memory was flushed and the session is being closed.

**Required payload:**
- `session_id: str`
- `cycle_id: str` — the cycle that issued the stop
- `total_cycles: int`
- `total_steps: int`
- `flushed_at: int`
- `final_outcome: str` — `accepted`, `cap_reached`, `user_requested`, `error`

**Optional payload:**
- `consolidation_pending: bool` — true if Phase 10 consolidation should run

**Determinism:** `true` — bookkeeping

**Causation:** `ClutchDecisionMade` with action `stop`

**Indexed tags:** `session_id`, `cycle_id`, `final_outcome`

---

### Consolidation (Phase 10)

#### `ConsolidationStarted`

`cerebra consolidate --session <id>` started a consolidation pass for a closed session.

**Required payload:**
- `session_id: str`
- `consolidation_id: str`
- `session_event_count: int` — number of events to consolidate
- `started_at: int`

**Determinism:** `true` — bookkeeping

**Causation:** External (CLI invocation) or automatic post-SessionFlushed if configured

**Indexed tags:** `session_id`, `consolidation_id`

---

#### `ConsolidationCompleted`

Consolidation produced a summary record.

**Required payload:**
- `session_id: str`
- `consolidation_id: str`
- `summary_record_id: str` — the new memory record holding the summary
- `calibration_audit: dict` — `{per_signal_calibration_delta, overall_calibration_status}`
- `completed_at: int`

**Optional payload:**
- `cited_record_ids: list[str]` — memory records cited in the summary
- `cited_lineage_ids: list[str]` — lattice lineages referenced

**Determinism:** `false` — summary content is LLM-derived

**Causation:** `ConsolidationStarted` for the same consolidation_id

**Indexed tags:** `session_id`, `consolidation_id`, `summary_record_id`

---

### Graph export (Phase 11)

#### `GraphExported`

`cerebra export graph --out <path>` produced a JSON file.

**Required payload:**
- `export_id: str`
- `output_path: str`
- `node_count: int`
- `edge_count: int`
- `exported_at: int`

**Optional payload:**
- `vault_path: str`
- `session_filter: str | null` — if export was scoped to a specific session
- `include_lattice_lineages: bool` — should match v0.1-full setting

**Determinism:** `true` — graph state at export time is deterministic

**Causation:** External (CLI invocation)

**Indexed tags:** `export_id`, `vault_path`

---

## Causation chains summary

Three causation chain families, each rooted at a specific event:

**Cycle execution chain** (per-step):
```
SessionOpened
  → CycleStarted
    → StepStarted
      → ContextPacketBuilt
        → StepExecuted
          → PredictionMade (from cycle config defaults if no prior step)
            → SignalEvaluated × 6
              → EvaluationComposed
                → OutcomeRecorded
                  → ClutchDecisionMade
                    → [CatalystInvoked → CatalystArmSelected]?
                      → LeewayGrantApplied
                        → [next StepStarted or CycleCompleted]
```

**Re-injection chain** (continuation):
```
ClutchDecisionMade (with continuation action)
  → ContinuationBundleCreated
    → ReinjectionTriggered
      → SessionOpened (child session)
        → [next cycle's execution chain]
```

**Consolidation chain** (post-session):
```
SessionFlushed
  → ConsolidationStarted (external trigger)
    → ConsolidationCompleted
      → [MemoryWriteFromCycle creating summary record]
```

## Indexed tags rationale

Common queries that motivate indexed_tags choices:

- **Per-session traces:** `session_id` indexed on every event. Lattica's time-travel viewer renders a single session's complete event stream.
- **Per-cycle analysis:** `cycle_id` indexed on every cycle event. Lets a single cycle be replayed independently.
- **Signal trajectory queries:** `signal_name` + `signal_score` indexed on SignalEvaluated. Lets the witness layer track per-signal trends over time.
- **Severe miss surfacing:** `error_classification` indexed on OutcomeRecorded. Cross-cycle queries for "show me all severe prediction misses this week."
- **Clutch action distribution:** `action` indexed on ClutchDecisionMade. Lets analysis identify drift in cycle behavior over time.
- **Re-injection chains:** `recursion_depth` and `parent_session_id` indexed on SessionOpened. Lets the relationship between parent and child sessions be queried efficiently.

## Versioning and forward compatibility

All event types are v1 (their `type_version` field is `1`). Future schema evolution will bump `type_version` and provide upcasters per fossic's upcaster pattern.

Forward compatibility commitments:
- Field additions are non-breaking (new optional fields can be added at v1; required field additions bump version)
- Field removals require version bump
- Field renames require version bump and upcaster
- Determinism flag changes require version bump (rare, would indicate substantive semantic shift)

---

*This vocabulary is the contract for Cerebra's Phase 6 cycle runtime emissions. Lattica Claude documents this in AGENT_TRACE_VOCABULARY.md for cross-project visibility. Cerebra's Phase 6 implementation emits events matching these schemas exactly. Schema changes go through both projects' coordination before implementation.*
