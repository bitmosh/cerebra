# Cerebra — Re-injection Loop

## 1. Purpose

The re-injection loop is the primitive that lets Cerebra carry cognitive continuity across context-window boundaries.

Small LLMs (7B-13B class) fail not because they cannot think but because their attention degrades across long contexts. They lose the goal partway through, drift toward fluency over accuracy, lose the thread of their own reasoning. Giving them a *fresh* context with the *distilled prior state* as priming dramatically improves their performance on long-running tasks.

The re-injection loop is the architectural shape that does this. It terminates the current prompt, distills its results into a structured carry-forward bundle, and starts a fresh prompt with that bundle as priming. The agent continues thinking without continuing the same context.

This document defines the ContinuationBundle schema, the temporal and structural parallel modes, the budget discipline, the voice modes, and the integration with the truth tower and cycle runtime.

---

## 2. Core Doctrine

The re-injection loop should be:

```text
context-window-aware
state-carrying
budget-disciplined
voice-explicit
tower-projecting
graph-event-emitting
inspector-visible
recursion-bounded
```

The loop is not a clever prompt trick. It is an architectural primitive that treats prompt termination + fresh prompting as a *first-class cycle operation*, equal in standing to retrieval or evaluation.

---

## 3. The ContinuationBundle

The bundle is the structured carry-forward state. It is what survives across the prompt boundary.

```json
{
  "bundle_id": "cb_abc123",
  "parent_session_id": "sess_xyz",
  "parent_step_id": "step_42",
  "created_at": 1717459200,
  "voice_mode": "self",
  "injection_format": "top-down",
  "carry_forward": {
    "distilled_goal": "Plan the Cerebra prototype gate test scenarios",
    "summarized_prior_prompt": "...condensed prior prompt content...",
    "truth_tower_projection": {
      "format": "top-down",
      "tiers_included": ["T5", "T4", "T3"],
      "tiers_summarized": ["T2", "T1"]
    },
    "cognitive_insights": [
      {"insight_id": "ins_1", "content": "...", "confidence": 0.84},
      {"insight_id": "ins_2", "content": "...", "confidence": 0.71}
    ],
    "next_focus": "Generate three test scenarios that exercise the SKU classifier under ambiguous content",
    "open_questions": [
      "What's the right confidence threshold for ambiguous content?",
      "Should ambiguous classification trigger multi-prompt triangulation?"
    ],
    "constraints": [
      "Stay within v0.1 MVP scope",
      "No reliance on yet-unbuilt subsystems"
    ]
  },
  "budget": {
    "max_tokens": 8000,
    "target_response_tokens": 1500,
    "reserved_tokens": 500
  },
  "recursion_depth": 1,
  "max_recursion_depth": 5
}
```

Every field has a job. The bundle must be small enough to fit in the fresh context with room to think; it must be rich enough to preserve cognitive continuity.

---

## 4. Temporal Parallel Mode

Multiple continuation bundles fired sequentially within one user-facing cycle.

```text
User asks: "Help me design X"
  Step 1: agent thinks about X's requirements
    -> output: requirements doc + open questions
    -> distill into ContinuationBundle_1
  Step 2: agent thinks about X's design (fresh prompt, ContinuationBundle_1 as priming)
    -> output: design sketch + open questions
    -> distill into ContinuationBundle_2
  Step 3: agent thinks about X's test scenarios (fresh prompt, _2 as priming)
    -> output: test scenarios
  Return synthesized result to user
```

This is what beats single-prompt small-LLM context limits. The cycle is parallel to the user-facing operation but serial in time. The user sees one response; behind it, three (or more) prompt invocations happened, each with fresh attention.

**When to use:** any task that would exceed the LLM's reliable attention budget in a single prompt. The clutch can trigger this proactively based on task complexity estimates.

---

## 5. Structural Parallel Mode

Multiple continuation bundles fired with the *same parent* but *different injection formats*.

```text
Step N completes
  -> fork three ContinuationBundles from the same parent:
       bundle_A: render tower in adversarial format
       bundle_B: render tower in cross-validation format
       bundle_C: render tower in chronological format
  -> spawn three fresh prompts in parallel (literally parallel if infra supports)
  -> collect three independent perspectives
  -> truth tower absorbs all three with their disagreements visible
  -> next cycle step has richer T3 (cross-validated insights) from triangulation
```

This is the depth mode. Same situation, multiple takes. The disagreements between the takes become T3 contradictions or T4 working hypotheses with explicit counter-evidence.

**When to use:** decisions with high stakes, creative work where divergent perspectives compound, debugging where the bug might have multiple plausible explanations.

---

## 6. Voice Modes

The fresh prompt can be framed in two voices.

**voice_mode: "self"**

```text
The fresh prompt reads as the agent talking to itself.
"You were working on planning the Cerebra prototype gate. Here's where you left off..."
The agent's response continues in its own voice as if uninterrupted.
```

Best for tasks where cognitive continuity matters more than role boundaries — long-running creative work, sustained analysis, exploration.

**voice_mode: "system"**

```text
The fresh prompt reads as system priming.
"Context: prior cycle was planning the Cerebra prototype gate. Distilled state: {bundle}.
 Task: continue from this state by addressing {next_focus}."
The agent's response is shaped as if responding to an external task brief.
```

Best for tasks with clear structure — code generation, factual research, structured outputs.

The voice mode is set in the bundle and the renderer respects it. Both modes use the same bundle data; only the framing differs.

---

## 7. Budget Discipline

Re-injection loops can run up LLM call counts dramatically. Discipline matters.

```text
per_cycle_continuation_cap:    5 continuations maximum per user-facing cycle
recursion_depth_cap:           5 levels of nested continuation maximum
token_budget_per_continuation: configurable, default 8000
total_token_budget_per_cycle:  cap = continuation_cap × per_continuation_budget
```

The clutch enforces these caps. New clutch rule:

```text
if continuation_count >= per_cycle_continuation_cap - 1:
  next continuation action requires confidence ≥ 0.7
  otherwise force accept current state and return to user
```

This is the "we're at 4 of 5 continuations, accept current draft" rule we discussed earlier. The clutch knows about continuation budget and adjusts its threshold for accept vs continue accordingly.

**Cost mitigation:** at small model sizes (7B-13B running locally), inference is cheap and the budget can be generous. At larger models (40B+ hosted), the per-token cost compounds quickly. The bundle's `budget` field should reflect actual cost reality.

---

## 8. Recursion vs Cycles

A continuation is not the same as a new cycle.

```text
Cycle:        new session_id, new goal, new working memory, new tower
Continuation: same session_id, same goal, working memory rebuilt from bundle,
              tower rebuilt from bundle.truth_tower_projection
```

Continuations preserve identity. Cycles establish it. A continuation that exceeds the recursion cap should trigger a *cycle break* — the system decides whether to finalize and return, or to spawn a genuinely new cycle with the bundle as context.

This is the architectural shape that prevents runaway recursion. The system can recurse, but only within a bounded depth. Beyond that, it must commit to either ending or starting fresh.

---

## 9. Truth Tower Projection

The carry-forward includes a tower projection. Not the full tower — a projection.

```text
T5 goal:            always included verbatim
T4 hypotheses:      always included if voice_mode is "self"; summarized if "system"
T3 insights:        always included if confidence ≥ continuation_threshold
T2 memories:        summarized to citations only, full content only if essential
T1 evidence:        cite-only references, no full content
```

The projection's job is to give the fresh prompt enough structure to think *as a continuation* without dragging the full tower into a context window that needs room to work.

Projection quality is itself a learning signal. If the system frequently has to invoke retrieval in continuations because the projection didn't carry forward what was needed, projection rules adjust over time.

---

## 10. Graph Event Emission

Every continuation emits graph events. This makes the loop visible to the inspector and to LumaWeave.

```text
CONTINUATION_SPAWNED         parent_step -> bundle
BUNDLE_DISTILLED             step output -> bundle content
PROMPT_REINJECTED            bundle -> new prompt
CONTINUATION_RESPONDED       new prompt -> new step output
CONTINUATION_BUDGET_HIT      cap reached event (terminal)
RECURSION_DEPTH_HIT          depth cap event (terminal)
```

The graph edge `CONTINUATION_OF` links a new step back to its parent step. LumaWeave can render continuation chains as visible thinking paths.

---

## 11. Integration With Existing Components

**Truth Tower (`CEREBRA_TRUTH_TOWER.md`):** ContinuationBundles draw from tower projections, not raw memory. The tower survives across continuations because its SKU-pointer structure is preserved in the bundle.

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** continuation is a clutch action in the structural group. New clutch rule: `if step_output_incomplete AND budget_available -> spawn_continuation`.

**Working Memory (`CEREBRA_WORKING_MEMORY_AND_ATTENTION.md`):** working memory rebuilds from the bundle's carry-forward in the new prompt. The slot occupancy from the parent step is reconstructed, not preserved.

**SKU Addressing (`CEREBRA_SKU_ADDRESSING.md`):** the bundle's citations are SKU pointers. The new prompt can re-retrieve through SKU if it needs fuller context than the bundle carries.

**Signal Pipeline (`CEREBRA_PREDICTION_AND_EVALUATION.md`):** continuation success is a measurable signal. Compare predicted-completion-without-continuation vs actual-completion-with-continuation. This is prediction-error feedback on the clutch's continuation-spawning decisions.

---

## 12. MVP Scope

Cerebra v0.1 should implement:

```text
ContinuationBundle schema (full schema, even if not all fields populated)
Temporal parallel mode only (structural deferred to v0.2)
voice_mode: "system" only (voice_mode: "self" deferred to v0.2)
Manual continuation trigger via clutch action
Per-cycle continuation cap enforced
Recursion depth cap enforced
Tower projection: T5 + T3 (skip T4 since T4 isn't in v0.1)
Graph event emission for continuations
```

Cerebra v0.2 adds:

```text
Structural parallel mode
voice_mode: "self"
Automatic continuation-spawning by clutch (based on completion signals)
Tower projection includes T4 hypotheses
Bundle distillation is a learned skill (calibration over time)
```

Cerebra v0.3+:

```text
Cross-cycle continuation (a cycle's bundle can prime a different cycle)
Bundle persistence and replay (debugging tool)
Bundle-quality scoring as a salience component
```

---

## 13. Testing Requirements

Re-injection loop tests should cover:

```text
ContinuationBundle round-trips correctly (distill -> render -> re-distill matches)
temporal parallel produces continuous narrative across continuations
structural parallel produces divergent perspectives that triangulate correctly
voice_mode: self produces first-person continuation
voice_mode: system produces task-brief continuation
per-cycle cap enforced
recursion depth cap enforced
tower projection includes only specified tiers
graph events emit correctly
budget discipline prevents runaway
CONTINUATION_OF edges link correctly in graph
clutch can spawn and accept continuations
continuation that hits budget cap forces accept
```

---

## 14. Failure Modes To Watch

**Context bloat through bundles.** If bundles aren't disciplined about what they carry, they grow each continuation and the fresh-context benefit disappears. Mitigation: hard size cap per bundle, compression review on every spawn.

**Drift across continuations.** Each continuation has slightly less context than the parent. Drift accumulates. Mitigation: periodic full-context "anchor" steps that re-establish the goal explicitly, run every N continuations.

**Cost spiraling.** Multiple structural parallels with deep temporal chains can cost 20+ LLM calls per user-facing cycle. Mitigation: hard cap on total calls per user-cycle, configurable.

**Loss of voice.** Self-voice mode requires consistent persona across continuations. If the bundle doesn't preserve enough stylistic signal, voice fragments. Mitigation: voice_signature field in bundle (style markers + key phrasings) for v0.2.

---

## 15. Re-injection Doctrine

The re-injection loop is the architectural answer to a hard problem: how does an agent think for longer than its context window allows?

The wrong answer is "make the context window bigger." That works until it doesn't, and the failure mode is silent attention degradation rather than visible context overflow.

The right answer is *terminate, distill, prime fresh*. The agent's thinking continues; the context that carries the thinking is renewed. The bundle is the structured handoff.

This is what makes small local models capable of sustained cognitive work. It is also what makes large hosted models cost-efficient — you pay for the attention budget you actually need, not for keeping a long context warm.

Combined with the truth tower (which gives the bundle structure to draw from) and the SKU addressing (which lets the bundle reference memory cheaply), the re-injection loop turns "context window" from a hard constraint into a managed resource.

The agent doesn't think within a context window. The agent thinks across a sequence of context windows, with continuity preserved by the bundle.

That is the difference between conversation and cognition.
