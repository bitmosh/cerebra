# Catalyst v0.1 Arm Vocabulary — planning.adaptive.v0

**Status:** Research doc, pre-kickoff
**Audience:** Cerebra Claude (kickoff drafter), bandit (implementing agent)
**Purpose:** Specify the v0.1 catalyst arm vocabulary for the planning.adaptive.v0 cycle config
**Sources:** catalyst_integration_decisions.md (companion doc), CEREBRA_CATALYST.md §5 (action vocabulary), Phase 8 simple.planning.v0 (reference structure)

---

## Context

Phase 9 Step 3 ships CatalystEngine plus a new cycle config (planning.adaptive.v0) that exercises catalyst escalation. Per the catalyst_integration_decisions.md companion doc:
- D2: New cycle config, not modification of simple.planning.v0
- D3: Arms are strategies mapped to CLUTCH_ACTIONS via `mapped_action` field
- D4: Each arm has explicit `type` field; K=5 window for type_penalty

This doc specifies what's actually in planning.adaptive.v0: the 5 arms, their types, their strategy prompts, and the Clutch rules that ensure catalyst escalation actually fires.

---

## The 5 v0.1 arms

### Arm 1: `constraint_check`

**Type:** `verification`
**Mapped action:** `refine`
**Strategy prompt:**

```
Apply constraint_check strategy to the current plan:

- Identify explicit constraints stated in the goal or prior step outputs
- Identify implicit constraints likely to apply (regulatory, resource, time, etc.)
- For each constraint, evaluate whether the current plan satisfies it
- Surface any constraints that need explicit verification with the user

Focus on surfacing hidden constraints. Do not propose new plan elements yet —
the refinement step downstream will use this constraint surface.
```

**When useful:** Plans that look feasible at first read but might violate constraints in execution (regulatory, budget, dependency).

### Arm 2: `decomposition`

**Type:** `structuring`
**Mapped action:** `refine`
**Strategy prompt:**

```
Apply decomposition strategy to the current plan:

- Identify sub-goals that are still too abstract or coarse-grained
- Break them down into more concrete, actionable sub-steps
- Identify dependencies between sub-goals (which must complete before others)
- Flag any sub-goals that still need further decomposition after this pass

Focus on increasing concreteness. Do not add new dimensions to the plan —
this is about resolving existing abstraction levels.
```

**When useful:** Plans that have high-level structure but lack concrete actionable detail.

### Arm 3: `risk_assessment`

**Type:** `verification`
**Mapped action:** `refine`
**Strategy prompt:**

```
Apply risk_assessment strategy to the current plan:

- Identify failure modes for each major plan element
- For each failure mode, estimate likelihood (low/medium/high)
- For each failure mode, estimate impact (low/medium/high)
- Highlight high-likelihood + high-impact items as priorities

Focus on what could go wrong, not what should go right. Do not propose
mitigations — that's a downstream refinement step.
```

**When useful:** Plans involving uncertainty, novel approaches, or external dependencies.

### Arm 4: `prerequisite_id`

**Type:** `structuring`
**Mapped action:** `refine`
**Strategy prompt:**

```
Apply prerequisite_id strategy to the current plan:

- For each plan step, identify what must be true or in place before that step
  can execute
- Distinguish hard prerequisites (blocking) from soft prerequisites (preferable)
- Identify any prerequisites not addressed in the current plan
- Surface ordering implications of these prerequisites

Focus on identifying gaps in the plan's prerequisite chain. Do not reorder steps —
just surface the missing pieces.
```

**When useful:** Plans where execution order matters or where setup work is implicit.

### Arm 5: `resource_estimate`

**Type:** `estimation`
**Mapped action:** `refine`
**Strategy prompt:**

```
Apply resource_estimate strategy to the current plan:

- For each plan step, estimate time required (rough order of magnitude)
- Estimate any tools, skills, or external resources needed
- Identify resource conflicts (steps competing for same resources)
- Flag any estimates that have high uncertainty

Focus on resource visibility, not resource optimization. Quantify where possible;
qualitatively flag where quantification is too uncertain to be useful.
```

**When useful:** Plans involving multi-week or multi-person execution where resource planning matters.

---

## Type distribution

| Type | Arms | Count |
|------|------|-------|
| verification | constraint_check, risk_assessment | 2 |
| structuring | decomposition, prerequisite_id | 2 |
| estimation | resource_estimate | 1 |

With K=5 type_penalty window and type_pressure=0.15:
- After 1 verification selection: next verification arm scores at 0.85 (gentle penalty)
- After 2 verification selections: next verification arm scores at 0.70
- Verification floor (3+ recent selections): 0.55, then 0.5 (floor)

This means catalyst diversity pressure kicks in after 2 same-type selections. With 2 arms per most types, this naturally pushes the catalyst to vary across both type and arm.

---

## YAML structure for planning.adaptive.v0

```yaml
name: planning.adaptive.v0
version: v0
description: |
  Adaptive planning cycle. Exercises catalyst escalation when Clutch's
  rule cascade does not match.

max_steps: 8
composite_floor: 0.3

steps:
  - name: understand_goal
    role: comprehension
    prompt_template: |
      Goal: {{ goal }}
      
      Read the goal carefully. Identify the core objective and any constraints
      that are explicitly stated.
      
      Return a 2-3 sentence summary of what's being asked, followed by a
      bullet list of any explicit constraints you identified.

  - name: draft_plan
    role: generation
    prompt_template: |
      Goal: {{ goal }}
      Understanding: {{ prior_step_output }}
      
      Draft an initial plan for this goal. Aim for 5-8 high-level steps.
      Each step should describe what happens, not how.

  - name: critique_plan
    role: critique
    prompt_template: |
      Goal: {{ goal }}
      Current plan: {{ prior_step_output }}
      
      {% if strategy_arm %}
      {{ strategy_arm.strategy_prompt }}
      {% else %}
      Critically evaluate this plan. Identify weaknesses, gaps, and assumptions.
      {% endif %}

  - name: refine_plan
    role: refinement
    prompt_template: |
      Goal: {{ goal }}
      Critique of the current plan: {{ prior_step_output }}
      
      Produce a refined plan that addresses the critique. The current draft plan
      is in your working memory context.

  - name: finalize
    role: synthesis
    prompt_template: |
      Goal: {{ goal }}
      Refined plan: {{ prior_step_output }}
      
      Produce the final plan in a clean, actionable format.

clutch_rules:
  # First rule that matches wins. Designed to escalate to catalyst
  # in the critique_plan step when no clear acceptance/refinement signal.
  
  - name: stop_at_final_step_accept
    predicate: at_terminal_step
    parameters: {}
    action: accept
  
  - name: refine_on_severe_miss
    predicate: prediction_severe_miss
    parameters: {}
    action: refine
  
  - name: stop_on_persistent_floor
    predicate: consecutive_steps_below_floor
    parameters: {count: 2}
    action: stop
  
  - name: accept_on_high_composite
    predicate: composite_above_threshold
    parameters: {threshold: 0.75}
    action: accept
  
  # Note: NO default_accept rule. Mid-cycle steps with moderate composite
  # (0.3 to 0.75) and no severe miss trigger escalate_to_catalyst.

stop_conditions:
  - name: max_steps_reached
    type: max_step_count
    parameters: {max_steps: 8}
  
  - name: persistent_low_composite
    type: composite_floor_consecutive
    parameters: {threshold: 0.3, count: 3}

catalyst_arms:
  - arm_id: constraint_check
    type: verification
    mapped_action: refine
    strategy_prompt: |
      [see Arm 1 specification above]
  
  - arm_id: decomposition
    type: structuring
    mapped_action: refine
    strategy_prompt: |
      [see Arm 2 specification above]
  
  - arm_id: risk_assessment
    type: verification
    mapped_action: refine
    strategy_prompt: |
      [see Arm 3 specification above]
  
  - arm_id: prerequisite_id
    type: structuring
    mapped_action: refine
    strategy_prompt: |
      [see Arm 4 specification above]
  
  - arm_id: resource_estimate
    type: estimation
    mapped_action: refine
    strategy_prompt: |
      [see Arm 5 specification above]
```

---

## Key difference from simple.planning.v0

The critical behavioral difference: **no `default_accept` rule in planning.adaptive.v0's clutch_rules.**

simple.planning.v0's last rule (per Phase 8) is something like:
```yaml
- name: default_accept
  predicate: always
  parameters: {}
  action: accept
```

This rule ensures Clutch ALWAYS matches some rule, so `escalate_to_catalyst` never fires. That's correct for the deterministic baseline.

planning.adaptive.v0 removes this catch-all. When the four explicit rules don't match (mid-cycle, moderate composite, no severe miss), Clutch sets `escalate_to_catalyst=True`. Catalyst fires, selects an arm based on its 3-factor scoring, and the next step's prompt template uses that arm's strategy_prompt.

This means: planning.adaptive.v0 should produce 0-3 catalyst invocations per typical cycle, depending on signal quality. Each invocation produces a CatalystArmSelected event and updates the bandit arm stats.

---

## Expected runtime behavior

A typical planning.adaptive.v0 run looks like this:

**Step 1 (understand_goal):**
- predicate `first_step` doesn't match anything explicitly in this rule set
- composite typically 0.6-0.8 (well-formed understanding)
- Clutch rules: `prediction_severe_miss` (no), `consecutive_steps_below_floor` (no), `composite_above_threshold` (maybe yes), `at_terminal_step` (no)
- If composite > 0.75: action=accept via accept_on_high_composite
- Else: escalate_to_catalyst=True, catalyst fires, selects an arm (first selection: forced_exploration of first arm in declared order = constraint_check)

**Step 2 (draft_plan):**
- composite typically 0.5-0.7 (initial draft)
- Similar Clutch evaluation
- If catalyst fired in step 1, the next step's template can include strategy_arm context

**Step 3 (critique_plan) — the catalyst-friendly step:**
- This is where strategy_arm makes most sense
- If catalyst fires, the critique focuses on the selected strategy (constraint_check, risk_assessment, etc.)
- If catalyst doesn't fire (rule matches), critique uses the default else-branch

**Steps 4-5 (refine_plan, finalize):**
- Refine uses critique from step 3 (which may have been strategy-focused)
- Finalize uses refine output
- Eventually action=accept via `stop_at_final_step_accept` rule

**Total catalyst invocations per cycle:** ~1-3 (depending on signal patterns).
**Arms exercised across a single cycle:** ~1-3 different arms (forced_exploration cycles through them on first invocations; UCB-based selection after).

---

## Test expectations

What Step 3's tests should demonstrate:

**1. Cycle config loads successfully:**
- YAML validator accepts planning.adaptive.v0
- catalyst_arms section validated (all required fields present, mapped_action is valid CLUTCH_ACTION, arm_ids unique, types are non-empty strings)
- No default_accept rule is acceptable (validator doesn't require one)

**2. Cycle runs end-to-end with catalyst:**
- CycleRuntime executes planning.adaptive.v0 against a real goal
- At least one step results in ClutchDecisionMade with escalate_to_catalyst=True
- For each such step, CatalystInvoked and CatalystArmSelected events emit
- Arm stats accumulate in catalyst_arm_stats table
- Cycle terminates cleanly (accept, stop, or cap_reached)

**3. Catalyst learning across a single session:**
- Run a multi-cycle test (3-5 cycles, all in the same session)
- Verify arm_stats accumulate across cycles
- Verify that arms with higher rewards get selected more often after enough samples
- Verify type_penalty kicks in: after 2 selections of same-type arms, next same-type arm gets penalized

**4. Cannot-select handling:**
- Construct a test cycle config with empty catalyst_arms
- Verify CatalystArmSelected emits with selected_arm_id=null and reason="cannot_select"
- Verify cycle falls back to Clutch's default action (the action set on ClutchDecision before escalation)

**5. Persistence round-trip:**
- Save arm_stats to SQLite via Bandit.to_state() + write to catalyst_arm_stats table
- Reload from catalyst_arm_stats table + Bandit.from_state()
- Verify all stats are preserved exactly

**6. Strategy prompt injection:**
- When CatalystArmSelected fires with arm_id=X, the next step's prompt template renders with the X's strategy_prompt content
- Test that the template variable `strategy_arm` is available when an arm was selected, None otherwise
- Test that the prompt rendering correctly substitutes strategy_arm.strategy_prompt

---

## What's NOT in v0.1 catalyst behavior

Per CEREBRA_CATALYST.md MVP scope, these are v0.2+:
- **chain_bonus factor** — v0.1 formula is `base_reward × type_penalty × confidence_ramp`, not the full 5-factor product
- **decay_factor** — recency decay across cycles deferred
- **Multiple cycle configs with distinct vocabularies** — v0.1 ships one (planning.adaptive.v0)
- **self_optimize action** — not in v0.1 arm vocabulary
- **Leeway-catalyst integration** — arms aren't pre-filtered by leeway in v0.1

These should NOT appear in planning.adaptive.v0's behavior. Implementation must explicitly skip them (or document why they're stubbed if any appear due to code structure reasons).

---

## Files involved

- **`cycles/planning.adaptive.v0.yaml`** — new cycle config (~150 lines including arm strategy prompts)
- **`cerebra/cognition/catalyst.py`** — new CatalystEngine class
- **`cerebra/cognition/catalyst_stats.py`** — persistence helpers for arm_stats (or fold into catalyst.py if small enough)
- **`cerebra/storage/migrations.py`** — Migration017 (two new tables)
- **`cerebra/cognition/cycle_runtime.py`** — modifications to invoke catalyst when escalate_to_catalyst=True, propagate strategy_arm into next step's prompt context
- **`tests/unit/test_catalyst.py`** — unit tests for CatalystEngine, scoring formula, arm selection
- **`tests/integration/test_catalyst_e2e.py`** — end-to-end test running planning.adaptive.v0
- **`docs/agent/deviations/v0.3.6.md`** — continue logging deviations

---

## Document corrections

- 2026-06-13: Q2 — removed redundant `floor:` parameter from `consecutive_steps_below_floor` predicate parameters (cycle-level `composite_floor` is source of truth; the predicate reads `ctx.cycle_state.consecutive_steps_below_floor`, not a parameter-supplied floor).
- 2026-06-13: Q3 — refine_plan template uses `prior_step_output` only; cross-step context via working memory rather than `prior_steps[]` indexed lookback (`prior_steps` contains strings not objects, so `.output` access would fail at render time).
