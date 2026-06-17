# simple.planning.v0 Cycle Config

*The v0.1 demonstration cycle. This is what `cerebra run-cycle simple.planning.v0 --goal "<text>"` executes against. Shipped as `cycles/simple.planning.v0.yaml` in Cerebra's built-in configs.*

---

## Overview

simple.planning.v0 is a **five-step planning cycle**. Given a goal, it:

1. **Understands** the goal — surfaces what's being asked, what context matters, what ambiguities exist
2. **Drafts** an initial plan — first pass at the structure
3. **Critiques** the plan — looks for gaps, contradictions, weak assumptions
4. **Refines** the plan — addresses critique findings
5. **Finalizes** — produces the polished output

The cycle progresses linearly when each step produces a reasonable score. Steps with low scores get repeated (Clutch refine action). Catastrophic failure on the first step (rare) stops the cycle.

This is intentionally **simple** — no branching, no parallel exploration, no catalyst-driven strategy selection. v0.2 adds those via more sophisticated cycle configs.

## YAML specification

```yaml
name: simple.planning.v0
version: 1
description: |
  A five-step planning cycle. Reads a goal, drafts a plan, critiques it,
  refines based on critique, and produces a finalized output. Demonstrates
  end-to-end cycle runtime for v0.1.

max_steps: 8

steps:
  - name: understand_goal
    description: Read the goal carefully and structure the understanding
    prompt_template:
      template: |
        # Goal
        {{ goal }}

        # Context from memory
        {{ retrieved_context }}

        # Task
        Read the goal carefully. Produce a structured understanding that covers:
        1. What is being asked (the core deliverable)
        2. What context from memory is relevant
        3. What ambiguities or open questions exist
        4. What success would look like

        Be specific. Avoid vague generalities. If something is unclear, say so explicitly.
      expected_output_format: free_form

  - name: draft_plan
    description: Generate an initial plan structure
    prompt_template:
      template: |
        # Goal
        {{ goal }}

        # Understanding (prior step)
        {{ prior_step_output }}

        # Context from memory
        {{ retrieved_context }}

        # Task
        Draft an initial plan that addresses the goal. Structure your plan with:
        1. Major phases or work-streams
        2. Key decisions that need to be made
        3. Dependencies and ordering
        4. Open questions that still need answering

        This is a draft — don't try to make it perfect. Get the structure on paper.
        Subsequent steps will critique and refine.
      expected_output_format: free_form

  - name: critique_plan
    description: Critically examine the plan for gaps and weaknesses
    prompt_template:
      template: |
        # Goal
        {{ goal }}

        # Plan to critique
        {{ prior_step_output }}

        # Task
        Critique the plan above. Be specific and direct. Identify:
        1. Hidden assumptions that should be made explicit
        2. Missing considerations or stakeholders
        3. Internal contradictions or tensions
        4. Steps that may be harder than they appear
        5. What success criteria are missing

        Don't be polite — your job is to find real problems. The plan will be revised
        based on this critique, so substantive criticism is more useful than mild
        suggestions.
      expected_output_format: free_form

  - name: refine_plan
    description: Address critique findings and produce a refined plan
    prompt_template:
      template: |
        # Goal
        {{ goal }}

        # Original plan
        {{ prior_steps[1] }}

        # Critique
        {{ prior_step_output }}

        # Task
        Revise the original plan to address the critique findings. For each major
        critique point, explicitly show how the revision addresses it. Keep the
        structure of the original plan but add, modify, or remove elements based on
        what the critique surfaced.

        Don't paper over critique points — if something genuinely can't be addressed,
        say so and explain why.
      expected_output_format: free_form

  - name: finalize
    description: Produce the polished final output
    prompt_template:
      template: |
        # Goal
        {{ goal }}

        # Refined plan
        {{ prior_step_output }}

        # Task
        Produce the final, polished output. This should be ready to share or act on.

        - Reorganize for clarity if needed
        - Acknowledge uncertainty where appropriate ("we estimate", "depends on", "if X then Y")
        - State key assumptions explicitly at the top
        - Make the structure scannable (headers, lists where appropriate)
        - End with concrete next steps

        This is the output the user will actually use. Make it useful.
      expected_output_format: free_form

stop_conditions:
  - name: max_steps_hit
    type: max_steps_reached
    parameters: {}

  - name: all_steps_done
    type: all_steps_completed
    parameters: {}

  - name: catastrophic_floor
    type: composite_floor_consecutive
    parameters:
      threshold: 0.30
      consecutive_count: 2

  - name: explicit_stop
    type: explicit_clutch_stop
    parameters: {}

  - name: user_interrupt
    type: user_interrupt
    parameters: {}

clutch_rules:
  # Catastrophic first-step failure — bail out
  - name: catastrophic_first_step
    description: First step scored below 0.3 — likely the goal is malformed or model is failing
    predicate_name: composite_below_threshold
    action: stop
    parameters:
      threshold: 0.30
      with_constraint: first_step

  # Refine low-scoring steps
  - name: refine_low_score
    description: Step composite below 0.5 — repeat the step
    predicate_name: composite_below_threshold
    action: refine
    parameters:
      threshold: 0.50

  # At final step with reasonable score — accept and end
  - name: accept_final_step
    description: At finalize step with composite >= 0.5 — accept (cycle terminates via all_steps_completed)
    predicate_name: at_terminal_step
    action: accept
    parameters:
      min_composite: 0.50

  # Default: accept the step and move on
  - name: default_accept
    description: Composite is reasonable — move to next step
    predicate_name: always
    action: accept
    parameters: {}
```

## Behavioral walkthrough

**Normal happy path:**
1. `understand_goal` runs → output scored at ~0.7 → Clutch evaluates rules in order
   - `catastrophic_first_step`? No (composite >= 0.3) → skip
   - `refine_low_score`? No (composite >= 0.5) → skip
   - `accept_final_step`? No (not at terminal step) → skip
   - `default_accept`? Yes (always) → action: accept
2. `draft_plan` runs → similar pattern → accept
3. `critique_plan` runs → accept
4. `refine_plan` runs → accept
5. `finalize` runs → output scored at ~0.7 → Clutch evaluates
   - `catastrophic_first_step`? No → skip
   - `refine_low_score`? No → skip
   - `accept_final_step`? Yes (at terminal step, composite >= 0.5) → action: accept
6. Stop condition `all_steps_completed` fires → cycle terminates with outcome "accept"

Total: 5 step executions, 5 cycle event chains, 1 MemoryWriteFromCycle per accepted step.

**Refinement path (one step scored low):**
1. `understand_goal` → 0.7 → accept
2. `draft_plan` → 0.4 (vague, missing structure) → Clutch evaluates
   - `refine_low_score`? Yes (composite < 0.5) → action: refine
3. `draft_plan` repeats → 0.65 → accept (default)
4. `critique_plan` → ... continues

Total step executions: 6 (because draft_plan was repeated once).

**Catastrophic failure path (first step scored very low):**
1. `understand_goal` → 0.25 (model refused or produced gibberish) → Clutch evaluates
   - `catastrophic_first_step`? Yes (composite < 0.3, first_step) → action: stop
2. Stop condition `explicit_clutch_stop` fires → cycle terminates with outcome "stop"

Total step executions: 1.

**Max steps path (lots of refinement):**
1. `understand_goal` → 0.6 → accept
2. `draft_plan` → 0.45 → refine
3. `draft_plan` → 0.45 → refine
4. `draft_plan` → 0.45 → refine
5. `draft_plan` → 0.45 → refine
6. `draft_plan` → 0.45 → refine
7. `draft_plan` → 0.45 → refine
8. `draft_plan` → 0.45 → refine
9. Stop condition `max_steps_hit` fires (8 step executions hit max_steps=8) → outcome "cap_reached"

The cycle ran but didn't complete. Useful test of the stop conditions actually firing.

## Signal weight overrides

v0.1 uses **default signal weights** for all steps. No per-step overrides.

For v0.2, planned overrides (NOT shipping in v0.1):
- `understand_goal`: COHERENCE and RELEVANCE weighted higher
- `draft_plan`: GENERATIVITY weighted higher (creativity rewarded)
- `critique_plan`: PRECISION and GROUNDEDNESS weighted higher
- `refine_plan`: balanced (no override)
- `finalize`: EPISTEMIC_HUMILITY weighted higher (final output should acknowledge uncertainty)

## What's intentionally NOT in this config

For clarity about v0.1 scope:

- **No catalyst arms.** simple.planning.v0 uses sequential progression, no strategy selection from a vocabulary. Phase 9 introduces real catalyst.
- **No branching.** No `branch` Clutch actions. Counterfactual exploration is post-v0.1.
- **No JSON output schemas.** All steps are free-form. Structured outputs come in v0.2 cycle configs.
- **No per-step signal weight overrides.** Default weights throughout.
- **No external tool calls.** All steps are pure LLM calls. Tool integration is v0.2+.
- **No HITL review.** `requires_review` Clutch decisions deferred per Phase 7 deviation.

## Testing simple.planning.v0

Step 2's success criterion includes:

```bash
cerebra run-cycle simple.planning.v0 --goal "Draft a prototype plan for a weekend hiking trip in October"
```

Should produce:
- A session opened
- 5 cycle events emitted to `cerebra/agent-trace/<cycle_id>`
- Step executions visible (5 steps in the happy path)
- 5 evaluations composed with 6 signals each
- 5 prediction/outcome pairs recorded
- LeewayGrantApplied events emitted before each MemoryWriteFromCycle
- Final session state = "flushed" with outcome = "accepted"
- A consolidation pending (Phase 10 will produce summary; Phase 8 just marks consolidation_pending=True)

The actual plan output quality isn't the primary validation. The validation is that **the cycle ran end-to-end with all components composing correctly**.

If the cycle outputs garbage but the event chain is correct, Phase 8 Step 2 succeeded. The plan quality improves with cycle config sophistication, calibration data, and v0.2 features — but the v0.1 milestone is "the runtime works."

---

*This is the v0.1 demonstration cycle. Bandit ships this YAML in `cycles/simple.planning.v0.yaml` plus the Python loader code to parse it. Step 2 implements the loader against the schema (see `cycle_config_schema.md`).*
