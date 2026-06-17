# Phase 6 Thesis — Cycle Runtime (v2)

**Written:** 2026-06-11  
**Author:** Claude Code (second pass, doc-grounded)  
**Supersedes/extends:** `phase6_cycle_runtime_thesis.md`  
**Status:** Pre-planning — for roadmap decisions, not implementation  

---

## Orientation: what "Phase 6" means in the roadmap

The roadmap (`CEREBRA_DEV_ROADMAP_v8.1.md`) does not have a single "Phase 6 — Cycle Runtime." It has four phases that collectively constitute the cycle runtime:

```
Phase 6  Signal Pipeline and Prediction Records   3-4 days
Phase 7  Leeway Network (Pre-Action Gate)         2-3 days
Phase 8  Cycle Runtime (Skeletal)                 3-4 days
Phase 9  Clutch and Catalyst (Minimal)            2-3 days
                                                  ---------
                                         total   10-14 days
```

These four are architecturally inseparable: Phase 8 consumes Phase 6's evaluation output; Phase 9's control logic reads Phase 6's signals; Phase 7's safety gate sits between Phase 6's evaluation and Phase 9's strategy selection. None of them makes sense alone. This document treats them as a single cognitive unit ("the cycle runtime block") but keeps the build-order distinctions visible because the phasing is the implementation order, not arbitrary clustering.

---

## 1. The one-sentence version

> Phase 6 gives Cerebra an execution loop — the structure that turns accumulated memory and working context into goal-directed, evaluable, governable action.

The longer version: Phases 0–5 built a system that can ingest documents, classify memory, retrieve context, maintain a truth tower, and track what it's attending to. Phase 6 builds the system that *runs a process using all of that* — executes a defined cognitive cycle, scores each output against an epistemically grounded set of signals, makes safety-checked control decisions, learns from the gap between expectation and outcome, and updates working memory based on what it found. Phase 6 is what transforms Cerebra from a well-organized retrieval system into a cognitive runtime.

---

## 2. What the current architecture cannot do

The current codebase (Phases 0–5, as of v0.2.7) has implemented the following modules:

```
cerebra/_primitives/          clutch.py, triangulator.py, score_composer.py,
                              trajectory.py, tombstone_set.py, mode_router.py
cerebra/cognition/            working_memory.py, truth_tower.py, sku*.py, lattice.py
cerebra/governance/           loader.py, models.py, defaults.py
cerebra/inspector/            event.py, ndjson_log.py, sqlite_log.py
cerebra/retrieval/            full pipeline through context_packet.py
cerebra/ingest/               full pipeline
cerebra/storage/              full stack
```

What is absent:

```
cerebra/cognition/signals.py         — signal evaluator
cerebra/cognition/predictions.py     — prediction / outcome records
cerebra/cognition/session.py         — runtime session
cerebra/cognition/cycle_config.py    — cycle definition schema
cerebra/cognition/catalyst.py        — strategy selector
```

None of the following capabilities exist:

### 2.1 No step execution

The system can retrieve context and load it into working memory. It cannot run a cognitive step *using* that context. There is no `run_step()`, no cycle definition schema, no mechanism to present a goal + ContextPacket to an LLM and capture structured output. The `llm_adapter.py` in `cerebra/cognition/` is a thin wrapper with no caller.

### 2.2 No signal evaluation

The six signals — COHERENCE, GROUNDEDNESS, GENERATIVITY, RELEVANCE, PRECISION, EPISTEMIC HUMILITY — are fully specified in `CEREBRA_SIGNAL_EPISTEMOLOGY.md` with checklist prompts and composition formulas. None of that exists in code. The `triangulator.py` primitive is on disk but has no consumer.

This is the gap that makes everything else consequential: without evaluation, there is nothing to learn from, no basis for control decisions, and no measure of whether the system is doing good work.

### 2.3 No prediction record

Before a step, nothing predicts expected quality. After a step, nothing measures the gap. `CEREBRA_PREDICTION_AND_EVALUATION.md` fully specifies PredictionRecord, OutcomeRecord, and prediction error computation. None are implemented. The bandit in the Catalyst has nothing to update against.

### 2.4 No control decision

`cerebra/_primitives/clutch.py` exists on disk. It is not wired to any caller. The Clutch takes signals, working memory state, trajectory, and prediction error as input; it returns a typed action (accept / refine / critique / explore / branch / retrieve_more / consolidate / ask_user / pause / stop). Since signals and prediction records don't exist yet, the Clutch's inputs don't exist, and it has never fired.

### 2.5 No runtime session

`session_id` has been a nullable field in `InspectorEvent` since Phase 0. It is `None` in every event Cerebra emits. There is no `RuntimeSession` — no object that binds a cycle run to a goal, a start time, a current step, and a completion status. There is no "run" in any meaningful sense; only individual queries and ingestion commands.

### 2.6 No strategy selection

`CEREBRA_CATALYST.md` fully specifies the five-factor scoring formula (`base_reward × chain_bonus × decay_factor × type_penalty × confidence_ramp`) and weighted-random sampling. There is no `catalyst.py`, no arm stats table, no action vocabulary loader.

### 2.7 Leeway loads but does not gate

`cerebra/governance/loader.py` reads constitutional and leeway YAML at vault init. The 15 default leeway rules (`LR-001` through `LR-015`) and 5 constitutional rules (`CONST-001` through `CONST-005`) load correctly. That is all they do. The pre-action gate — the consultation protocol that checks whether a capability is currently permitted before a step fires — does not exist.

### 2.8 No re-injection loop

`CEREBRA_REINJECTION_LOOP.md` fully specifies the ContinuationBundle, temporal parallel mode, voice modes, budget discipline, and recursion caps. Nothing on disk implements any of it. Long-running cognitive work across context-window boundaries is entirely unsupported.

### 2.9 The truth tower has no driver

Phase 5 built the tower structure (T1 + T2, PROMOTE operation, capacity caps, inspector events). The tower is built to be driven by a cycle runtime: each step reads from T1+T2, the Clutch's accept/refine/stop actions write back to it, the re-injection loop draws from its projection. Without the cycle runtime, the tower is a well-designed container with no process filling or consuming it.

---

## 3. The smallest proof of success

> If you can run `cerebra run-cycle simple.planning.v0 --goal "Design a test plan for the Phase Lattice"` and observe all of the following, the cycle runtime block succeeded.

1. A `RuntimeSession` record in the vault: `session_id`, `cycle_id`, `started_at`, `status: running`.
2. T1 in the truth tower was populated from retrieval — ContextPacket drove `TowerTierRebuilt`.
3. At least one step executed. A real or mock LLM received goal + T1+T2 tower projection and returned structured output.
4. An `EvaluationPacket` exists with scores for all six signals and a computed composite. The `triangulator.py` primitive was the computation path.
5. `PredictionMade` was emitted before the step; `PredictionResolved` was emitted after, with a computed error value.
6. At least one leeway grant was applied (`LeewayGrantApplied` event in the inspector).
7. A `ClutchDecisionMade` event was emitted with a typed action.
8. Working memory was updated based on the Clutch action.
9. All of the above are queryable: `cerebra inspect events --session <id>`.

The proof is structural, not qualitative. Fake LLM output is acceptable. No particular signal score threshold is required. The proof is that the loop ran, every step emitted events, and the session has a visible start and end.

---

## 4. The signal epistemology — why these six signals

Phase 6 (signals sub-phase) is the part of this block most likely to be underestimated. The signals are not implementation details. They are the cognitive epistemology of the system, and the choice of exactly these six is load-bearing.

The signals derive from six threads that converge across philosophical and contemplative traditions independently — analytic philosophy, phenomenology, Buddhist epistemology, Sufi tradition, scholastic precision, pragmatist philosophy. The convergence is not coincidence. These are the conditions under which thought can be reliable, regardless of cultural framing.

### The six threads and their LLM failure-mode mappings

| Signal | Philosophical thread | LLM failure mode | Default weight |
|--------|---------------------|------------------|----------------|
| COHERENCE | Aristotle's non-contradiction; Buddhist catuṣkoṭi avoidance | self-contradiction within output | 0.18 |
| GROUNDEDNESS | Empiricism; phenomenology's "return to the things themselves"; Sufi direct knowing vs hearsay | hallucination | 0.18 |
| GENERATIVITY | Hegel's dialectic; Zen koans; scientific paradigm shifts | sycophancy / mode collapse / repetition | 0.12 |
| RELEVANCE | Aristotle's phronesis; Buddhist upaya (skillful means); pragmatist "what difference does it make" | drift / tangent generation | 0.22 |
| PRECISION | Scholastic precision; logical positivism; Buddhist analytical meditation | mush / vague language | 0.12 |
| EPISTEMIC HUMILITY | Socratic "I know that I know nothing"; Gödel incompleteness; apophatic theology | overclaiming / false confidence | 0.18 |

The mapping is one-to-one: six signals, six failure modes. This is not coincidence — the perennial threads and LLM failure modes are independently describing the same underlying conditions for reliable thought.

**EPISTEMIC HUMILITY is the most consequential new signal.** It is not in any precursor system. An AI that scores its own outputs on whether they know what they don't know is qualitatively different from one that asserts without calibration. This is the signal that distinguishes a memory system that earns trust from one that claims it.

### Operationalization

Each signal becomes a checklist prompt. The COHERENCE checklist asks: do any claims contradict each other? Are any terms used equivocally? Do conclusions follow from premises? Are hidden premises present? Does the reasoning loop? Each checklist item is rated 0–3 per specific line; the aggregate becomes a 0–1 signal score.

The composition formula: `composite = Σ(signal_i × weight_i)`. Then: `reward = composite × confidence × signal_strength`. Confidence and signal_strength are triangulating multipliers, not signal inputs — they are the system's claim about how much to trust its own evaluation.

**Per-cycle weight overrides** make the signals task-aware: a code-review cycle down-weights GENERATIVITY (correctness matters, not novelty) and up-weights COHERENCE and PRECISION. A brainstorming cycle up-weights GENERATIVITY and temporarily loosens PRECISION. The same six signals serve any cognitive task; the weights encode the task's priorities.

### Why signal prompt design is the load-bearing work

A signal prompt that is too vague produces random scores (noise). One that is too specific overfits to a single domain. The signal prompts need calibration data before they can be trusted. The roadmap's 3–4 day estimate for Phase 6 (signals sub-phase) assumes the prompt design goes smoothly. Assume it doesn't on the first pass.

The six signal checklist prompts, with fixture content to validate them against, are the highest-risk deliverable in the entire Phase 6–9 block.

---

## 5. Cognitive operations in execution order

Within a single cycle step, in execution order:

```
 1.  LOAD CYCLE DEFINITION
       Read YAML cycle config. Validate schema.
       Extract: step_order, allowed_actions, stop_conditions,
       catalyst_options, signal_weight_overrides, clutch_rules.

 2.  CREATE RUNTIMESESSION
       session_id, cycle_id, goal, project, started_at, status.
       session_id populates all subsequent inspector events.
       This is the first time session_id is non-null in any event.

 3.  BUILD CONTEXTPACKET
       Delegate to Phase 4 retrieval.
       ContextPacket drives T1 rebuild: TowerTierRebuilt.
       The LLM prompt is built from T1+T2 tower projection,
       not from raw retrieval results.

 4.  PRE-ACTION GATE (leeway check)
       Before any step: consult leeway network.
       Emit LeewayGrantApplied / LeewayGrantDenied.
       Constitutional revocation → ConstitutionalBlock → halt.
       If leeway-filtered candidate set is empty → LeewaySetEmpty
       → clutch falls back to safe default.

 5.  MAKE PREDICTION
       Before step execution: predict expected signal scores.
       Write PredictionRecord: expected, confidence, basis.
       Emit PredictionMade.

 6.  EXECUTE STEP
       Present goal + tower projection + step spec to LLM.
       Capture structured output: step_id, duration, errors.
       Emit StepExecuted (or StepFailed).

 7.  EVALUATE SIGNALS
       Run six checklist prompts.
       Aggregate to EvaluationPacket:
         { coherence, groundedness, generativity, relevance,
           precision, epistemic_humility, composite,
           confidence, signal_strength, triangulated_reward }
       triangulator.py is the computation path.
       Emit SignalEvaluated.

 8.  RESOLVE PREDICTION
       Compare EvaluationPacket composite to PredictionRecord.expected.
       error = actual - expected.
       Classify: noise (|err| < 0.10) / notable / severe (|err| > 0.40).
       Write OutcomeRecord. Emit PredictionResolved, PredictionErrorRecorded.
       Severe miss → emit PredictionSevereMiss additionally.

 9.  ISSUE CLUTCH DECISION
       Inputs: signals, working_memory_state, trajectory, prediction_error,
               recent_action_history, cycle_phase, user_constraints.
       Clutch cascades its rule set (first-match-wins) → typed action:
         accept / refine / critique / explore / branch /
         retrieve_more / consolidate / ask_user / pause / stop
       Emit ClutchDecisionMade.

10.  INVOKE CATALYST (when Clutch action is ESCALATE)
       Catalyst loads action vocabulary from cycle config.
       Compute multi-factor scores:
         score(action) = base_reward × chain_bonus × decay_factor
                       × type_penalty × confidence_ramp
       Filter through leeway network (pre-action gate again on candidates).
       Weighted-random sample from filtered set (not argmax).
       Emit CatalystInvoked, CatalystSelected.
       If filtered set empty: cannot_select → Clutch safe default.

11.  UPDATE WORKING MEMORY
       Based on Clutch decision:
         accept      → evict lowest-salience items, write episodic memory
         refine      → pin current T2 items for next step
         retrieve_more → refresh T1 with updated salience weights
         branch      → fork session state (new session with parent pointer)
         stop        → flush session, mark complete, collapse tower
       Emit corresponding WorkingMemory / Tower events.

12.  CONTINUE OR STOP
       Check stop conditions from cycle config.
       If continuing → increment step, return to step 3.
       If re-injection threshold hit (context budget) → step 13.
       If stop condition met → finalize session.

13.  RE-INJECTION (when context budget exhausted)
       Distill truth tower projection (T5 goal verbatim + T4 hypotheses
       + T3 insights above threshold) into ContinuationBundle.
       Bundle includes: distilled_goal, summarized_prior_prompt,
       tower_projection, cognitive_insights, next_focus,
       open_questions, constraints, recursion_depth.
       Emit ReinjectionTriggered, ContinuationBundleCreated.
       Start fresh prompt with bundle as priming.
       Increment recursion_depth; enforce max_recursion_depth (default 5).
```

---

## 6. State Phase 6 operates against

| State | Direction | Owner | Phase built |
|-------|-----------|-------|-------------|
| Cycle definition YAML | read | cycle config file | Phase 6 (new) |
| RuntimeSession | read/write | sessions table | Phase 6 (new) |
| Leeway grants (loaded) | read | governance/ | Phase 0 — exists, not yet consulted |
| Constitutional rules (loaded) | read | governance/ | Phase 0 — exists, not yet consulted |
| ContextPacket | read | retrieval engine | Phase 4 — built |
| WorkingMemory session | read/write | working_memory table | Phase 5 — built |
| TruthTower T1/T2 | read/write | truth_tower_items table | Phase 5 — built |
| PredictionRecord | write | predictions table | Phase 6 (new) |
| OutcomeRecord | write | outcomes table | Phase 6 (new) |
| EvaluationPacket | write | evaluations table | Phase 6 (new) |
| CatalystArmStats | read/write | catalyst_stats table | Phase 9 (new) |
| ContinuationBundle | write | bundles table / vault file | Phase 8 (new) |
| Inspector events | write | inspector_events + NDJSON | Phase 0 — exists |

The critical new state types: `RuntimeSession`, `PredictionRecord`, `OutcomeRecord`, `EvaluationPacket`. None have any on-disk representation today.

---

## 7. Events Phase 6–9 produce

New event types, grouped by sub-phase:

**Session lifecycle (Phase 8):**
```
RuntimeSessionCreated
RuntimeSessionCompleted
RuntimeSessionFailed
CycleStarted
StepStarted
StepCompleted
StepFailed
CycleCompleted
```

**Leeway/safety (Phase 7):**
```
LeewayGrantApplied
LeewayGrantDenied
LeewayRevocationFired
LeewaySetEmpty
LeewayRuleLoaded
LeewayRuleExpired
ConstitutionalBlock       (schema exists; first real use here)
```

**Signal evaluation (Phase 6):**
```
SignalEvaluated           (EvaluationPacket as payload)
```

**Prediction/learning (Phase 6):**
```
PredictionMade
PredictionResolved
PredictionErrorRecorded
PredictionSevereMiss      (only when |error| > 0.40)
```

**Control (Phase 9):**
```
ClutchDecisionMade
CatalystInvoked
CatalystSelected
```

**Re-injection (Phase 8):**
```
ReinjectionTriggered
ContinuationBundleCreated
```

**Truth Tower (deferred from Phase 5, first used here):**
```
TowerTierRebuilt          (T1 rebuild at cycle start)
TowerCollapsed            (session end → tower flush)
```

Every event in this block carries `session_id` as a non-null field. Phase 6 is the first phase where `session_id` is a first-class populated field rather than an optional annotation.

---

## 8. Integration with Phase 5's working memory and truth tower

Phase 5 built the workspace. Phase 6 drives it.

### What Phase 5 delivered that Phase 6 directly depends on

**WorkingMemory (slots, salience, eviction policy):** the cycle runtime writes to working memory after every Clutch decision. `accept` evicts lowest-salience items and writes episodic memory. `refine` pins current T2 items so they persist through the next step. `retrieve_more` triggers a fresh ContextPacket with updated salience weights, which refreshes T1. The 10-slot working memory model with its capacity caps and eviction priority is the workspace the cycle runtime operates in.

**TruthTower T1/T2:** T1 is the grounding layer for every step. The ContextPacket's retrieval results auto-populate T1 at cycle start (`TowerTierRebuilt`). The LLM prompt is constructed from the tower's T1+T2 projection, not raw retrieval candidates. The cycle runtime does not call retrieval directly — it reads through the tower. The tower is the mediated view.

**Tower operations (PROMOTE, EVICT, STALE, REBUILD):** the Clutch's `stop` action triggers the tower collapse cascade: session marked complete → working memory flushed (`WorkingMemoryCleared`) → tower collapsed (`TowerCollapsed`). Phase 5 built the operations; Phase 6 is the first entity to invoke them as part of a cycle.

**session_id in working memory events:** Phase 5's `WorkingMemoryCreated` events have a `session_id` field. It has been `None` in every event since Phase 5 shipped. Phase 6 is what populates it — the `RuntimeSession` created at cycle start provides the session_id that flows into all subsequent events.

### The key relationship

Phase 5 built a workspace that can hold things. Phase 6 builds the process that puts things in, takes things out, and decides what to do based on what it finds. The workspace is only meaningful in the presence of the process. Phase 6 is what gives Phase 5 its purpose.

---

## 9. Integration with the leeway network

The leeway architecture deserves careful attention because it is architecturally unusual and the design decisions here have downstream consequences.

### The permission-positive inversion

Standard safety frameworks define what's *forbidden*; everything else is permitted. Rules compose by negation: adding a rule can restrict previously-permitted actions. Rules interact in ways nobody predicted; the action space becomes fragile as rule density increases.

The leeway network inverts this. It defines what's *permitted under what conditions*. Rules compose by *union*: adding a permission cannot restrict other permissions. Inside the leeway-bounded region, the cycle runtime has full cognitive freedom. The Clutch doesn't check safety. The Catalyst doesn't check safety. Both can be aggressive about behavioral selection because the leeway-bounded action space is by construction safe.

The architectural stack (from `CEREBRA_LEEWAY_NETWORK.md §4`):

```
Constitutional Layer    (5-10 hard rules)           inviolable revocations
Capability Bounds       (what adapters exist)        structural impossibility
Truth Tower Rules       (tier derivation discipline) derivation discipline
Leeway Network          (conditional permissions)    ← the focus of Phase 7
Clutch Policy           (what's preferred)           behavioral
Catalyst Defaults       (what's tried under uncertainty) exploratory
```

The constitutional rules (5 of them: CONST-001 through CONST-005) do not prohibit actions — they *revoke leeway grants* under specified conditions. This is the ceiling. Leeway grants in the middle are the body. Capability bounds are the floor.

### Phase 7 specifically delivers

Phase 7 wires up the pre-action gate. Currently, `governance/loader.py` reads the rules; nothing consults them. Phase 7 builds the consultation protocol:

```
For each capability the step needs:
  filter against current leeway grants
  check revocation conditions
  check constitutional revocation conditions
  if empty: LeewaySetEmpty → clutch safe default
  else: LeewayGrantApplied → proceed
```

The post-action audit (the second phase of consultation, where the output is checked against content-shaped revocation conditions) is deferred to v0.2. Phase 7 implements pre-action gating only.

### Concrete leeway examples in the cycle runtime

- **`retrieve_from_memory`**: LR-001, baseline grant, always permitted.
- **`spawn_continuation_bundle`**: conditional — composite < 0.6, continuation_count < 5, has_clear_next_focus = true. Revocation: token_budget_exhausted.
- **`promote_to_truth_tower_T4`**: conditional — cross_validation_count >= 2, confidence >= 0.7. Revocation: contradiction_detected_among_supports.
- **`write_to_semantic_memory`**: conditional — groundedness >= 0.7 AND epistemic_humility >= 0.6. Phase: both (checked pre-action and post-action in v0.2).

---

## 10. Integration with the catalyst

The Clutch decides *whether* to mutate strategy. The Catalyst decides *which strategy* to mutate to.

The Catalyst's five-factor formula is:

```
score(action) = base_reward × chain_bonus × decay_factor × type_penalty × confidence_ramp
```

Each factor addresses a distinct failure mode of greedy selection:
- **base_reward**: what has worked (prevents ignoring history)
- **chain_bonus**: what has worked in *sequence* (learns combinations, not just individual actions)
- **decay_factor**: floor at 0.7 for stale actions (prevents convergence to early winners)
- **type_penalty**: diversity pressure after N same-type selections (prevents mono-strategy lock-in)
- **confidence_ramp**: discount new actions until N samples exist (prevents first-impression dominance)

The catalyst uses weighted-random sampling, not argmax. This preserves exploration after preferences form. Combined with the Clutch (which decides when to act) and leeway (which decides what's permitted), the Catalyst is the "what to try" layer of a system that can reason about hard problems without rigid prescription.

The Catalyst learns from signal evaluations: `reward = composite × confidence × signal_strength`. The same triangulator primitive that computes the EvaluationPacket's reward updates the Catalyst's bandit arm stats.

---

## 11. The re-injection loop — cognition across context boundaries

The re-injection loop is the answer to the question Phase 6 must eventually solve: how does an agent think for longer than its context window allows?

The wrong answer is "make the context window bigger." Larger context windows produce silent attention degradation rather than clean overflow. The right answer is *terminate, distill, prime fresh*.

The ContinuationBundle carries forward:
```json
{
  "distilled_goal":             "...",
  "summarized_prior_prompt":    "...",
  "truth_tower_projection": {
    "T5 goal":           verbatim,
    "T4 hypotheses":     always if voice_mode=self,
    "T3 insights":       confidence >= threshold,
    "T2 memories":       citations only,
    "T1 evidence":       cite-only references
  },
  "cognitive_insights":  [...],
  "next_focus":          "...",
  "open_questions":      [...],
  "constraints":         [...],
  "recursion_depth":     1,
  "max_recursion_depth": 5
}
```

A continuation is not a new cycle. It preserves session_id and goal; it rebuilds working memory from the bundle projection; it rebuilds T1 from fresh retrieval with the next_focus as query. The recursion cap (5 levels, configurable) prevents unbounded continuation; hitting it forces an accept-or-start-fresh decision.

The truth tower is what makes re-injection work: ContinuationBundles draw from tower projections, not raw working memory. The tower's SKU-pointer structure (T3 insights citing T2 items, T2 items citing T1 evidence) gives the bundle structured handoff content that a fresh prompt can reason with.

---

## 12. ES interplay — the architectural decisions

The event sourcing question is sharpest at Phase 6 because Phase 6 is where sessions become first-class. The brainstorm document `event_sourced_cognitive_substrate.md` introduces a key insight that should shape Phase 6 design before implementation begins.

### 12.1 Cognitive dithering

The insight (from the 2026-06-12 design conversations): events are discrete by necessity (audit substrate requires clean boundaries for replay and observability), but aggregate state *appears* continuous to the cognitive substrate (gradients like "working memory is becoming saturated" or "retrieval is abstaining more often").

> *Cognitive dithering* — arranging discrete events densely enough that their integration produces the appearance of continuity at the consuming layer. The architecture is honest at both layers: discrete at the substrate, continuous at the projection.

This resolves an architectural tension that has appeared repeatedly in design conversations. Phase 6 does not need to choose between "discrete events for auditability" and "continuous state for cognition." The substrate is discrete; the projections over it are continuous. Both layers are honest about their character.

### 12.2 Session as stream

One `session_id` = one ES stream. Phase 6 is the natural insertion point for ES adoption because:
- Before Phase 6: sessions are mostly null, stream-per-session has nothing to organize
- During Phase 6: first systematic `session_id` population happens
- After Phase 6: migrating a vault full of session events to a new stream model is expensive

If ES is adopted before or at Phase 6, stream-per-session is free. If deferred, retrofitting is awkward.

The vault-level system events (`VaultCreated`, `MigrationRun`, etc.) belong on a single `system` stream. Everything else is per-session.

### 12.3 Branching becomes real at Phase 6

The Clutch's `branch` action produces a child session causally derived from the parent at the branch point. The re-injection loop produces a continuation session with a `parent_session_id` pointer. These are not metaphorical branches — they are exactly what ES branch semantics model.

ES branches would let you ask: "what would this cycle have produced if the Clutch had said `accept` at step 3 instead of `refine`?" This question is unanswerable with the flat log. With ES branches, it's a replay operation. This is the "counterfactual cognition becomes natural" insight from the substrate document.

### 12.4 Lattice nodes as aggregates — post-v0.1 but foundational

The event-sourced substrate document proposes that memory records (particularly lattice members) become event-sourced aggregates rather than static rows. A record's state evolves as it's used: each `AttentionItemPromoted`, `TowerItemPromoted`, `RetrievalSelected` event updates the record's accumulated usage statistics, learned utility score, and meta-cognitive context.

This is post-v0.1 in implementation scope but the architectural commitment should be made before Phase 6 design is finalized. A Phase 6 that treats memory records as static rows is harder to migrate to the aggregate model than one that already separates "record committed state" from "record accumulated usage state."

The migration is forward-compatible: existing records start at "the original LatticeCommit event, no subsequent events." As they're used, they accumulate events and their state diverges from initial state. No backfill required.

### 12.5 Pre-action gate ordering

The leeway pre-action gate must emit `LeewayGrantApplied` *before* `StepExecuted`. This is a causal ordering requirement. ES's append-only single-writer-per-stream model enforces this structurally. The flat NDJSON log also enforces it, but only by process order — there is no structural guarantee against a future concurrent-writer scenario violating this ordering.

### 12.6 EvaluationPacket as typed payload

The EvaluationPacket is the largest and most structured event payload the system will produce: six signal scores, composite, confidence, signal_strength, triangulated reward, per-signal failure mode flags. This is a natural candidate for an ES payload with its own `schema_version`. The current `data_json` TEXT column is flexible but untyped. ES with schema-versioned payloads gives the EvaluationPacket forward-migration guarantees as the signal formula evolves.

### 12.7 Practical accommodations if ES is adopted at Phase 6

If the ES toolkit is ready by Phase 6, these specific decisions need to be made:

1. **Session as stream or session as correlation field?** Recommendation: per-session streams. Vault-level system events on a single `system` stream; everything else per-session. This gives natural replay granularity.

2. **event_id migration.** Current format: `evt_<12-hex-uuid>`. ES uses content-addressed IDs (blake3). Migration window: Phase 6, before the first sessions are created. The event log is small; migration cost is near zero now.

3. **ContinuationBundle as ES branch or as new session with `parent_session_id`?** ES branch is architecturally clean and enables counterfactual replay. New session with pointer is simpler but loses replay capability. Recommendation: ES branch if the toolkit is ready; pointer fallback if not.

4. **Synchronous emit requirement.** The cycle runtime is fully synchronous. The ES PyO3 API must support synchronous `append(event)`. This is non-negotiable per the cognitive substrate document's "synchronous at the substrate, async at the consumption boundary" principle.

### 12.8 If ES is not ready at Phase 6

Isolate all event emission behind an `EventLog` interface. No direct calls to `NDJSONEventLog` and `SQLiteEventLog` from cycle runtime code. When the ES toolkit is ready, the implementation swaps without touching the runtime logic. Name the seam explicitly so migration is a swap, not a refactor.

---

## 13. The witness layer — Phase 6+ but foundational to Phase 6 design

The `phase6_cognitive_extensions.md` document describes the witness layer as a separate substrate that reads the inspector event stream and produces structured self-observation as queryable data.

The distinction (from that document): the **truth tower** holds what the system thinks (curated cognitive contents). The **witness layer** holds what the system has observed itself thinking (self-observation as structured data). They are similar in shape but different in role — tower for cognition, witness for meta-cognition.

Why this matters for Phase 6 design: the witness layer is not Phase 6 scope, but its eventual inputs are Phase 6's outputs. Session events, signal evaluation events, Clutch decision events, Catalyst selection events — all of these are the raw substrate the witness layer will aggregate into patterns.

Phase 6 should emit these events in a form the witness layer can consume without modification. The witness layer queries: "how often does retrieval abstain on queries involving emotional content?" "What signal regresses first when the Catalyst selects `exploration`?" "Which Clutch actions follow `PredictionSevereMiss` most often?" These are Phase 6 event streams + Phase 6+ aggregation.

Under the cognitive dithering architecture, the witness layer doesn't need to maintain its own projection infrastructure — it reads aggregate state from lattica-es aggregates. Designing Phase 6's events with that consumption in mind (rather than as pure audit records) produces better event schemas.

---

## 14. What makes Phase 6 hard

### 14.1 Signal prompts are the load-bearing work

The six checklist prompts are the core of the evaluation sub-phase. Writing prompts that produce reliable 0–1 scores is not mechanical: too vague → random scores, too specific → domain overfit. Each needs calibration data. The 3–4 day estimate for the signal sub-phase is optimistic if the first versions of the checklist prompts don't work.

Plan for a calibration iteration after the first complete cycle run. Accept that the initial signal weights (the defaults from `CEREBRA_SIGNAL_EPISTEMOLOGY.md §6`) will need adjustment based on observed behavior.

### 14.2 Clutch rule design is subtle

The Clutch's first-match-wins cascade must handle every combination of signal states correctly. The default rule set will almost certainly misfire on first attempt. Budget calibration time — multiple cycles observed before declaring the rule set stable.

### 14.3 LLM adapter is a real dependency

`cerebra/cognition/llm_adapter.py` has `OllamaDirectAdapter` and `ProxyLLMAdapter`. Step execution requires calling an actual LLM. The test strategy needs to commit early to either a mock adapter (fast, won't catch prompt failures) or a local Ollama instance (slower, catches failures). The right call depends on how much signal prompt calibration is needed.

### 14.4 Consistency under failure

If the cycle runtime crashes mid-step: some events were emitted, working memory may have been updated, but there's no `StepExecuted` event. The failure model from `CEREBRA_COGNITIVE_RUNTIME.md §12` must be implemented carefully. SQLite transactions are the tool, but the event emission path sits outside the transaction by design (the WAL safety rule in `truth_tower.py` is explicit about emit-after-commit). Getting failure recovery right without compromising the emit discipline is fiddly work.

### 14.5 Session_id propagation

Every event in a cycle run must carry `session_id`. The inspector's `InspectorEvent` dataclass has this field as nullable. Making it non-nullable (or at least enforced in the cycle runtime path) requires touching every emission site. This is a cross-cutting change.

---

## 15. Recommended build order

The roadmap's phasing (6 → 7 → 8 → 9) is correct and should not be reordered. The logic:

```
Phase 6 (Signals + Predictions)
  Build the evaluation vocabulary first.
  You have something to score before you build control.
  The signal prompts need calibration time; start them earliest.

Phase 7 (Leeway Pre-Action Gate)
  Safety gating before the runtime exists means
  every subsequent line of cycle code already respects it.
  Building leeway after the runtime produces a refactor.

Phase 8 (Cycle Runtime Skeletal)
  Wire together evaluation + safety + session + step execution.
  The simple.planning.v0 built-in cycle config runs here.
  Prototype gate from CEREBRA_PROTOTYPE_CHECKLIST.md fires here.

Phase 9 (Clutch + Catalyst Minimal)
  Control and strategy selection on top of a working runtime.
  The scoring formula and action vocabulary are testable
  only once the runtime is producing real EvaluationPackets.
```

The prototype gate runs after Phase 8: `ingest → context → step → evaluate → clutch → emit`. If it passes, continue to Phase 9. If it doesn't, something earlier is wrong; fix before continuing.

---

## 16. ES adoption window

The natural window for ES adoption is **between Phase 5 completion and Phase 6 start** — i.e., now.

- The event log is small (only Phases 0–5 events, no session events). Migration cost is near zero.
- Phase 6 creates the first systematic `session_id` population. Getting the stream model right before the first session is created is substantially easier than retrofitting after.
- The NDJSON + SQLite dual-layer was always a placeholder. Replacing it cleanly requires a green phase boundary.
- If ES is deferred to Phase 10+, the cycle runtime accumulates hundreds of sessions' worth of events in the old format, and migration becomes a real project.

The `event_sourcing_toolkit_revised.md` brainstorm specifies the Rust-core + PyO3 adapter architecture. The synchronous `append(event)` requirement from that document is non-negotiable for Cerebra's synchronous cycle runtime. Confirm this is in the ES toolkit spec before committing to the integration.

If the toolkit is not ready at Phase 6 start: use the `EventLog` interface seam. The cycle runtime calls `EventLog.append(event)`; the implementation is initially the current NDJSON+SQLite stack; it swaps to ES when the toolkit ships.

---

## 17. Summary of key decisions

Before writing Phase 6 code, these decisions should be locked:

| Decision | Options | Recommendation |
|----------|---------|----------------|
| ES adoption timing | Before Phase 6 / after Phase 9 / never | Before Phase 6 if toolkit is ready; seam-first if not |
| Stream granularity | Per-session streams / vault-wide stream | Per-session streams |
| ContinuationBundle model | ES branch / new session + parent pointer | ES branch if toolkit supports it |
| event_id format | Current `evt_<uuid>` / content-addressed | Migrate to content-addressed at Phase 6 start |
| LLM adapter test strategy | Mock adapter / local Ollama | Local Ollama (catches real prompt failures) |
| Signal prompt calibration | Single pass / dedicated calibration iteration | Budget one calibration iteration after first cycle run |
| Clutch rules | Pre-written / empirical first pass | Pre-write, budget revision after calibration |
| Session_id enforcement | Optional (nullable) / required in cycle path | Required in cycle runtime; nullable allowed elsewhere |

---

## Appendix: what the v1 thesis got right, and where v2 diverges

The v1 thesis (`phase6_cycle_runtime_thesis.md`) was produced without reading the source docs directly. Its overall analysis was accurate: the correct gaps were identified, the correct build order was described, the ES interplay section was solid. Where v2 adds substantially:

1. **The roadmap actually distinguishes phases 6–9** more precisely than v1's "phases 6–9 as a single block." The build order matters: signals before safety gate before runtime before control.

2. **Signal epistemology depth**: the six philosophical threads underlying the signals are more than implementation flavor — they're the reason the mapping to LLM failure modes is one-to-one. This is the architectural justification that makes EPISTEMIC HUMILITY non-optional.

3. **The cognitive dithering insight** from the ES substrate brainstorm: discrete events + continuous projections is the architectural resolution of the audit-vs-cognition tension. V1 discussed ES integration; v2 names the underlying pattern.

4. **Lattice nodes as aggregates**: the post-v0.1 architectural commitment that memory records accumulate usage-event state. Phase 6 design should be compatible with this direction even before it's implemented.

5. **Witness layer distinction**: truth tower (what the system thinks) vs witness layer (what the system has observed itself thinking). Phase 6's event stream is the witness layer's future substrate.

6. **Permission-positive architecture specifics**: the composition-by-union property of the leeway network (vs composition-by-negation in prohibition-model safety) is the architectural load-bearing principle for why the leeway architecture scales.

7. **Re-injection loop specifics**: the ContinuationBundle schema and the tower-projection-as-carry-forward mechanism were underspecified in v1.

8. **What actually exists in the codebase**: grounded in the Python file tree. `clutch.py` and `triangulator.py` are on disk. `signals.py`, `predictions.py`, `session.py`, `catalyst.py`, `cycle_config.py` are not. This grounds the "what the current architecture cannot do" section in facts rather than inference.
