# Cerebra — Drift Fix Patches v8.1

## Purpose

This document consolidates small additions and corrections to existing Cerebra docs. These are surgical fixes — patches to apply, not full rewrites. Each section identifies the target doc, the section to update, and the specific text or specification to add.

The fixes here are >= 92% confidence. Lower-confidence items are flagged in `CEREBRA_OPEN_QUESTIONS.md` and need user input before landing.

---

## 1. Working Memory Slot Capacity Defaults

**Target:** `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md` §4

**Add this subsection after the slot enumeration:**

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

## 2. Cycle Definition Schema Pin

**Target:** `CEREBRA_COGNITIVE_RUNTIME.md` §3 (Cycle Definition)

**Replace the current prose with this formal schema:**

### 3. Cycle Definition Schema

Cycle definitions are YAML files with the following schema:

```yaml
# Required fields
cycle_id: string             # globally unique, dotted-path convention (e.g. "bonsai.ideation.v1")
name: string                 # human-readable name
purpose: string              # short purpose statement
schema_version: integer      # cycle schema version (currently 1)

# Required structural fields
agent_roles:                 # list of agent roles this cycle uses
  - role_id: string
    role_name: string
    description: string

step_order:                  # ordered list of step types
  - step_type: string
    optional: boolean        # default false
    repeatable: boolean      # default false

allowed_actions:             # vocabulary for the catalyst
  - action_id: string
    action_name: string
    group: enum [terminal, iterative, structural, social]

# Required signal fields
metrics:                     # which signals this cycle evaluates
  - signal_id: string
    weight: float            # contribution to composite (sum should ≈ 1.0)

clutch_rules:                # priority-ordered rule cascade
  - rule_id: string
    priority: integer
    guard_expression: string
    action: object
    explanation_template: string

# Required output fields
output_schema:               # what this cycle emits to memory
  memory_record_types: [string]
  graph_event_types: [string]

stop_conditions:             # when the cycle ends
  - condition_id: string
    expression: string

# Optional fields
memory_scopes:               # which memory layers this cycle reads/writes
  reads: [string]            # default: all active layers
  writes: [string]            # default: episodic + working

catalyst_options:            # catalyst configuration
  vocabulary: [string]       # action ids from allowed_actions
  scoring_overrides: object  # optional weight adjustments

max_continuations: integer   # cap for re-injection loops, default 5
max_recursion_depth: integer # cap for nested continuations, default 5
```

### 3.1 Schema Validation

Cycle definitions must validate before loading. Validation checks:

```text
all required fields present
metric weights sum to between 0.95 and 1.05
clutch rules have unique rule_ids
clutch rule priorities are unique
action groups are valid enum values
referenced step_types exist
referenced signal_ids exist
stop_conditions cover at least one terminal case
```

Cycle definitions fail-loud at load time. Invalid configs do not partially load.

---

## 3. Clutch Action Grouping

**Target:** `CEREBRA_COGNITIVE_RUNTIME.md` §9 (Clutch Controller)

**Add this subsection:**

### 9.1 Action Groups

The 10 clutch actions are grouped by what they do to the cycle. Rules declare which group they fire in to prevent overlap and interference.

**Terminal group** (ends or pauses the cycle):

```text
accept    cycle complete, output is final
stop      cycle aborted, no useful output
pause     cycle suspended, may resume
```

**Iterative group** (continues the cycle with adjustment):

```text
refine    improve current output, same approach
critique  challenge current output, may change approach
explore   diverge from current approach
retrieve_more  expand the working memory context
```

**Structural group** (changes the cycle's shape):

```text
branch    fork into multiple parallel cycle paths
consolidate  trigger consolidation on accumulated memory
```

**Social group** (involves the user or another agent):

```text
ask_user  pause for user input
```

### 9.2 Group Discipline

Rules in the clutch's priority cascade declare their target group. Two rules in the same group can compete on priority. Two rules in different groups *cannot directly compete* — group choice is the higher-level decision.

This means the clutch's rule cascade is implicitly two-pass:

```text
Pass 1: which group should this decision come from?
  Driven by overall cycle state — failure_streak, progress_delta, mode_duration
Pass 2: which action within that group?
  Driven by specific signals — coherence, novelty, confidence
```

Rules can be written to either pass. Most rules will be pass-2 (action within group). A small number of pass-1 rules establish which group dominates given the current cycle phase.

This structure prevents the rules-interfering-with-rules problem. Adding a refinement rule cannot interfere with a termination rule because they're in different groups.

---

## 4. Signal Composition Formula

> **⚠ SUPERSEDED:** This section is superseded by `CEREBRA_SIGNAL_EPISTEMOLOGY.md`.
> The 11-signal model below was an intermediate iteration. The canonical model is
> the six-signal epistemological architecture (COHERENCE, GROUNDEDNESS, GENERATIVITY,
> RELEVANCE, PRECISION, EPISTEMIC HUMILITY) grounded in the six perennial threads.
> Implementing agents should read `CEREBRA_SIGNAL_EPISTEMOLOGY.md` instead of this
> section. The composition formula structure (weighted mean × confidence × signal_strength)
> is preserved; only the signal vocabulary and weights differ.
>
> This section is retained for historical traceability but is **not** the spec.

**Target:** `CEREBRA_PREDICTION_AND_EVALUATION.md` §8 (Signal Pipeline)

**Add this subsection:**

### 8.1 Composite Formula

The composite score combines per-signal scores via weighted mean, then triangulates against confidence and signal strength.

```text
composite = Σ (signal_score_i × signal_weight_i) for i in signals
                where Σ signal_weight_i = 1.0

reward = composite × confidence × signal_strength
             range: [0, 1.0] (occasional overshoot to ~1.2 with positive shaping)
```

### 8.2 Default Signal Weights

Signals and their default weights for a general-purpose cycle. Per-cycle configs override:

```text
coherence            0.18
novelty              0.12
usefulness           0.20
specificity          0.10
contradiction        0.05   (penalty signal — negative contribution)
goal_alignment       0.20
confidence           (used as multiplier, not weighted-mean factor)
surprise             0.05
progress_delta       0.05
retrieval_quality    0.03
context_fit          0.02
                     ----
total                1.00
```

Two signals are excluded from the weighted mean and act as multipliers instead:

```text
confidence:        used in reward triangulation (composite × confidence × signal_strength)
signal_strength:   used in reward triangulation; derived from input data quality
```

### 8.3 Confidence and Signal Strength Bands

```text
confidence:        0.0 - 0.4   low (treat output as tentative)
                   0.4 - 0.7   moderate (proceed with care)
                   0.7 - 1.0   high (treat as reliable)

signal_strength:   0.0 - 0.5   weak (limited input data)
                   0.5 - 0.8   moderate (typical input)
                   0.8 - 1.0   strong (rich, validated input)
```

### 8.4 Calibration Audit

Signals are calibrated over time. The consolidation engine periodically reviews:

```text
predicted signal score vs actual signal score (when measurable)
per-signal systematic bias
per-signal variance vs claimed confidence
```

Calibration deltas adjust per-signal scoring formulas. This is the prediction-error feedback loop applied to the signal pipeline itself.

---

## 5. Prediction-Error Control Thresholds

**Target:** `CEREBRA_PREDICTION_AND_EVALUATION.md` §10 (Control Use)

**Replace §10 with this concrete specification:**

### 10. Control Use of Prediction Error

Prediction error feeds the clutch and catalyst as concrete signals with thresholds.

### 10.1 Thresholds

```text
absolute_error < 0.10:   noise band, no control adjustment
absolute_error 0.10-0.25: notable miss, soft adjustment
absolute_error 0.25-0.40: significant miss, moderate adjustment
absolute_error > 0.40:    severe miss, strong adjustment + flag for review
```

### 10.2 Adjustment Rules

When prediction error exceeds threshold, control feedback fires:

**Retrieval prediction error:**

```text
predicted retrieval_quality = 0.8, actual = 0.3 (large negative error)
  -> broaden retrieval next cycle (higher attention budget)
  -> lower salience for sources in this prediction's evidence chain
  -> log calibration delta for retrieval predictor
```

**Coherence prediction error:**

```text
predicted coherence = 0.7, actual = 0.4 (notable miss)
  -> next cycle's clutch favors `refine` over `accept`
  -> if pattern persists 3+ cycles, recommend mode change to refinement-heavy cycle
```

**Goal-alignment prediction error:**

```text
predicted alignment = 0.9, actual = 0.5 (severe miss)
  -> spawn continuation with explicit goal re-anchoring
  -> flag for user review (possible goal drift)
  -> calibration delta against goal-alignment predictor
```

**Novelty prediction error (over-prediction):**

```text
predicted novelty = 0.7, actual = 0.3
  -> catalyst type_pressure increased temporarily
  -> next selection favors actions in unexplored vocabulary regions
```

### 10.3 Worked Example

Cycle 14 of a planning session. Predictions and outcomes:

```text
predicted output_quality: 0.78
actual output_quality:    0.54
absolute_error:           0.24  (in the notable-miss band)
interpretation:           "overestimated planning step quality"

Adjustments:
  clutch: shift toward `refine` for next step
  catalyst: increase confidence_ramp threshold for current strategy
  calibration: log -0.24 delta against output_quality predictor
```

### 10.4 Severe Miss Handling

Errors above 0.40 trigger additional behavior:

```text
log to inspector with severity flag
emit graph event PREDICTION_SEVERE_MISS
if 3+ severe misses in last 10 cycles: pause cycle and request user review
do not auto-adjust scoring weights from a single severe miss
   (require pattern across multiple cycles to change scoring)
```

The pattern requirement is the discipline that prevents single-event overcorrection.

---

## 6. Multi-Prompt Triangulation Pattern

**Target:** `CEREBRA_PREDICTION_AND_EVALUATION.md` (new section after §8)

**Add this subsection:**

### 8.5 Multi-Prompt Triangulation

For high-stakes evaluation (high-salience memories, decisions with downstream impact, user-pinned content), the signal pipeline runs multiple narrower prompts instead of one wide prompt, then triangulates.

### Pattern

```text
Instead of one prompt asking for all 11 signal scores in one call:
  Run 3-4 prompts, each asking for a related signal group
  Compare scores across prompts for the same signal
  Signals where all prompts agree: high confidence
  Signals where prompts diverge: low confidence
```

### Signal Groups

```text
Quality group:       coherence + specificity + usefulness
Novelty group:       novelty + surprise + retrieval_quality
Alignment group:     goal_alignment + context_fit + contradiction
Progress group:      progress_delta + signal_strength
```

Each group is one prompt. Confidence emerges from cross-prompt agreement.

### When to Triangulate

```text
Always:    user-pinned content evaluation
Always:    memories being promoted to semantic memory
Always:    high-stakes clutch decisions (terminal group actions)
Optional:  routine cycle steps (cost vs benefit tradeoff)
```

Triangulation triples evaluation cost. Apply it where it earns its keep.

---

## 7. Prompt-Formula Awareness

**Target:** `CEREBRA_COGNITIVE_RUNTIME.md` (new section)

**Add this subsection:**

### 8.6 Prompt-Formula Mutual Awareness

Evaluation prompts and the formulas that consume their outputs should be mutually aware. This is a discipline that improves calibration.

### Prompt-Side Awareness

LLM prompts that produce metric scores should know:

```text
the scale they're scoring on (0-10 or 0-1)
the weight their score will receive in the composite
whether confidence will multiply their score
what "high" and "low" mean operationally for this metric
```

Example prompt fragment:

```text
Score coherence on a 0-10 scale.
Your coherence score contributes 18% of the composite.
A 7+ here suggests refinement is unnecessary.
A 4 or below triggers a critique cycle.
Be specific: cite which sentences cohere and which don't.
```

This calibrates the LLM's judgment toward the consumer's needs. Without this, prompts produce miscalibrated scores that the formula then weighs as if they were calibrated.

### Formula-Side Awareness

Formulas should preserve metadata about which prompt produced which input:

```text
metric_input: {
  signal: "coherence",
  score: 7.2,
  source_prompt_id: "coherence_eval_v3",
  source_prompt_version: 3,
  confidence_self_reported: 0.74
}
```

This makes calibration audits possible. If prompt v2 consistently underscores compared to prompt v3, the consolidation engine can detect and flag it.

---

## 8. SKU Cross-References in Existing Docs

The following existing docs should add cross-references to `CEREBRA_SKU_ADDRESSING.md`:

**`CEREBRA_RETRIEVAL_ARCHITECTURE.md`:** Add to §2 (Core Doctrine):

```text
All retrieval modes operate over the SKU-addressed substrate.
SKU is the precondition for efficient retrieval, not a fifth retrieval mode.
See CEREBRA_SKU_ADDRESSING.md for address shape and traversal.
```

**`CEREBRA_MEMORY_LAYERS.md`:** Add to §2 (Core Memory Doctrine):

```text
Every memory record at M2 and above carries a SKU at write time.
Memory addressing is uniform across layers; subcategory schemas vary by layer.
```

**`CEREBRA_CONSOLIDATION_ENGINE.md`:** Add to §5 (Consolidation Flow):

```text
Consolidation rewrites SKU pointers when summaries are produced.
Consolidation runs calibration audits on the classifier.
Consolidation triggers orthogonal ablation for promoted memories.
See CEREBRA_SKU_ADDRESSING.md §10 (pointer staleness) and
CEREBRA_ORTHOGONAL_ABLATION.md §6 (ablation scheduling).
```

**`CEREBRA_SALIENCE_SCORING.md`:** Add two new components to §4 (Salience Components):

```text
sku_sibling_distance:        closer in SKU space = higher salience for related queries
attribution_aligned_match:   query's match position aligned with memory's high-attribution position
```

---

## 9. Internal Cognition Module Boundary

**Target:** `CEREBRA_ARCHITECTURE.md` (new section)

**Add this subsection:**

### 19. Internal Cognition Module

Cerebra's cognitive primitives — clutch, catalyst, signal pipeline, truth tower, re-injection loop, salience scoring, prediction layer — are organized as an internal module with a clearly bounded public API:

```text
cerebra/
  cognition/
    __init__.py       # public API surface
    clutch.py
    catalyst.py
    signals.py
    truth_tower.py
    reinjection.py
    salience.py
    predictions.py
    _internal/        # implementation details, not part of public API
```

### 19.1 API Boundary Discipline

Other parts of Cerebra access cognitive primitives *only* through `cerebra.cognition`'s public API. The internal layer can be refactored freely without affecting other Cerebra modules.

### 19.2 Future Extraction

When the cognitive primitives stabilize (estimated 6-12 months of use), the `cerebra.cognition` module will be extracted into its own package: `lattica-cognition`. The eventual dependency graph:

```text
lattica-primitives    (small, stable, ubiquitous: clutch, triangulator, etc.)
       ↑
lattica-cognition     (cognitive harness: truth tower, re-injection, leeway, etc.)
       ↑
cerebra               (memory runtime built on lattica-cognition)
       ↑
bonsai (config)       (cycle config that Cerebra runs)
```

Until extraction, the internal module discipline approximates the eventual package boundary. This means the eventual extraction is mechanical, not a refactor.

### 19.3 What's In vs Out of cerebra.cognition

**In:**

```text
clutch, catalyst (the control primitives)
signal pipeline + composite formula
truth tower (tier structure, derivation, render formats)
re-injection loop (continuation bundles, voice modes)
salience scoring (component-based)
prediction layer (predictions, outcomes, calibration)
```

**Out (Cerebra-internal, not cognition):**

```text
ingestion adapters
storage (SQLite, vector index)
retrieval engine
ContextPacket builder
consolidation engine
memory lifecycle
graph export
```

The split is *primitives* (in cognition) vs *infrastructure* (in Cerebra). Cognition uses infrastructure through the public API.

---

## 10. Self-Improving Retrieval Reference

**Target:** `CEREBRA_COGNITIVE_RUNTIME.md` (add to §10 Catalyst section)

**Add this paragraph:**

### 10.1 Retrieval Strategies as Bandit Arms

Retrieval strategies (defined in `CEREBRA_SKU_ADDRESSING.md` §12) are catalyst-selectable actions. The cycle's clutch can issue an "adjust retrieval strategy" decision; the catalyst selects among the available retrieval strategy arms based on past performance for similar queries.

This means Cerebra learns to retrieve better over time. The same machinery that learns which cognitive strategies work (catalyst) also learns which retrieval strategies work. The pitch property: **a memory system with built-in self-improvement on the retrieval side.**

See `CEREBRA_SKU_ADDRESSING.md` §12 for the strategy space and `CEREBRA_CATALYST.md` for the selection mechanics.

---

## 11. Drift Fix Doctrine

These are surgical patches. The intent is to land small additions and corrections without rewriting working docs.

Each patch is independent. They can be applied in any order, though some have implicit dependencies (the clutch action grouping helps the cycle definition schema; the signal composition formula helps the prompt-formula awareness).

After these patches land, the planned-doc backlog drops to the lower-confidence items: Leeway Network, Inspector, Lattica Primitives package spec. Those need user input before writing.
