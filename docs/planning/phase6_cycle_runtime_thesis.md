# Phase 6 Thesis — Cycle Runtime

**Written:** 2026-06-11
**Status:** Pre-planning — for roadmap decisions, not implementation yet
**Scope:** Addresses Phases 6–9 of the current roadmap as a unified capability block

---

## A note on roadmap numbering

The current roadmap (`CEREBRA_DEV_ROADMAP_v8.1.md`) names the phases as follows:

```
Phase 6:  Signal Pipeline and Prediction Records
Phase 7:  Leeway Network (Pre-Action Gate)
Phase 8:  Cycle Runtime
Phase 9:  Clutch / Catalyst
```

These four phases are architecturally inseparable — each one is load-bearing for the next, and none of them is useful without the others. This document treats them as one logical phase: **the Cycle Runtime**. Refer to the roadmap for granular build-order within that block. The user is calling this block "Phase 6" conversationally; this document does the same, meaning the full 6–9 block unless a sub-phase is called out.

---

## 1. The one-sentence version

> Phase 6 gives Cerebra a brain stem: the execution loop that turns stored memory and working context into goal-directed action.

Longer version: where Phases 1–5 built a system that *knows things*, Phase 6 builds the system that *does something with what it knows* — runs a defined process, evaluates each step against principled quality signals, makes control decisions, learns from errors, and updates working memory based on what it found.

---

## 2. What the current architecture cannot do

Phases 0–5 are complete. Here is a precise account of what they cannot do, and why those gaps matter.

### 2.1 There is no step execution

The system can retrieve context and load it into working memory. It cannot run a cognitive step *using* that context. There is no `run_step()`, no cycle definition, no mechanism for the system to present a goal + context + ContextPacket to an LLM and capture structured output.

The result: everything built so far is infrastructure for a process that has no way to start.

### 2.2 There is no evaluation

After a step produces output, nothing can score it. The six signals (coherence, groundedness, generativity, relevance, precision, epistemic humility) exist as a fully specified epistemology in `CEREBRA_SIGNAL_EPISTEMOLOGY.md` but there is no `EvaluationPacket`, no signal evaluator, no composition formula in code. The system cannot distinguish a good output from a bad one.

The result: the system cannot learn, because there is nothing to learn *from*.

### 2.3 There is no control decision

The Clutch primitive lives in `cerebra/_primitives/`. It is not wired to anything. After an evaluation (which doesn't exist yet), nothing can say `accept`, `refine`, `branch`, `retrieve_more`, `consolidate`, `ask_user`, or `stop`. The session has no termination condition and no ability to steer between iterations.

The result: even if a step ran and was evaluated, the system could not act on what it found.

### 2.4 There is no learning signal

Before a step, nothing predicts what quality to expect. After a step, nothing computes the gap between predicted and actual. Prediction records, outcome records, and prediction error exist only in `CEREBRA_PREDICTION_AND_EVALUATION.md`. The Catalyst's bandit arm stats have nothing to update against.

The result: cycle behavior cannot improve. Every run starts from the same priors regardless of what happened before.

### 2.5 There is no session

`session_id` has been a nullable field in `InspectorEvent` and `WorkingMemory` since Phase 0. It is `None` in every event Cerebra currently emits. There is no `RuntimeSession` — no object that ties a cycle run together with a goal, a start time, a current step, and a completion status.

The result: there is no "run." There are queries and ingestion commands but no concept of executing a cognitive process from start to finish.

### 2.6 There is no strategy selection

The Catalyst has a fully specified multi-factor scoring formula in `CEREBRA_CATALYST.md` but there are no cycle configs with action vocabularies. The Catalyst has nothing to select from.

### 2.7 The leeway network exists but is never consulted

`cerebra/governance/` loads constitutional and leeway YAML at vault init. That is all it does. The pre-action gate — the check that happens before any action executes — does not exist. The system can load its own safety rules and then proceed to ignore them.

### 2.8 There is no re-injection loop

ContinuationBundle and re-injection are specified in `CEREBRA_REINJECTION_LOOP.md`. Nothing on disk implements them. Long-running cognitive processes across context boundaries are entirely unsupported.

---

## 3. The smallest proof

> If you can run `cerebra run-cycle simple.planning.v0 --goal "Design a test plan for the Phase Lattice"` and observe the following, Phase 6 succeeded:

1. A `RuntimeSession` record exists in the vault with a `session_id`, `cycle_id`, `started_at`, and `status: running`.
2. Working memory was populated from retrieval — T1 items auto-loaded from the ContextPacket.
3. At least one step executed. A real or mock LLM received the goal + context and returned structured output.
4. An `EvaluationPacket` exists with scores for all six signals and a computed composite.
5. A `PredictionMade` event was emitted before the step and a `PredictionResolved` event after it, with a computed error.
6. A Clutch decision was emitted — `accept`, `refine`, or any other typed action.
7. Working memory was updated based on that decision (at minimum: session marked complete or another step begun).
8. All of the above are queryable via `cerebra inspect events --session <id>`.

No particular signal score threshold is required. Fake LLM output is fine. The proof is structural: the loop ran, every action was inspectable, the session has a clear start and end.

---

## 4. Cognitive operations Phase 6 must enable

In execution order within a single cycle step:

```
1.  Load cycle definition
      Read a YAML cycle config. Validate against schema.
      Extract: step_order, allowed_actions, stop_conditions,
      catalyst_options, signal_weight_overrides.

2.  Create RuntimeSession
      session_id, cycle_id, goal, project, started_at, status.
      Populate session_id in all subsequent inspector events.

3.  Build ContextPacket
      Delegate to Phase 4 retrieval. Auto-populate T1 in truth tower
      from retrieval results (the TowerTierRebuilt event deferred
      from Phase 5 fires here for the first time).

4.  Pre-action gate (leeway check)
      Before any step executes: consult leeway network.
      Emit LeewayGrantApplied / LeewayGrantDenied.
      Constitutional block → ConstitutionalBlock event → halt.

5.  Make a prediction
      Before step execution: predict expected signal scores.
      Write PredictionRecord with expected, confidence, basis.
      Emit PredictionMade.

6.  Execute step
      Present goal + ContextPacket + cycle step spec to LLM.
      Capture structured output with step_id, duration, errors.
      Emit StepExecuted (or StepFailed if the call fails).

7.  Evaluate step output
      Run six signal checklist prompts.
      Aggregate to EvaluationPacket:
        { coherence, groundedness, generativity, relevance,
          precision, epistemic_humility, composite,
          confidence, signal_strength, triangulated_reward }
      Emit SignalEvaluated.

8.  Resolve prediction
      Compare EvaluationPacket composite to PredictionRecord.expected.
      Compute error = actual - expected.
      Classify: noise (|err| < 0.10) / notable / severe (|err| > 0.40).
      Write OutcomeRecord. Emit PredictionResolved, PredictionErrorRecorded.
      Severe miss → emit PredictionSevereMiss additionally.

9.  Issue Clutch decision
      Feed signals + working memory state + trajectory +
      prediction error into Clutch.
      Clutch cascades its rule set → typed action:
        accept / refine / critique / explore / branch /
        retrieve_more / consolidate / ask_user / pause / stop
      Emit ClutchDecisionMade.

10. Invoke Catalyst (when Clutch action is "select strategy" / ESCALATE)
      Catalyst loads vocabulary from cycle config.
      Compute multi-factor scores. Weighted-random sample.
      Emit CatalystInvoked, CatalystSelected.
      Leeway pre-filters vocabulary before sampling.

11. Update working memory
      Based on Clutch decision:
        accept    → evict lowest-salience items, write episodic memory
        refine    → pin current T2 items, retrieve_more → refresh T1
        branch    → fork session state
        stop      → flush session, mark complete
      Emit corresponding WorkingMemory / Tower events.

12. Decide: loop or stop
      Check stop conditions from cycle config.
      If continuing: increment step, return to step 3.
      If re-injection threshold hit (context budget): step 13.
      If stop condition met: finalize session.

13. Re-injection (when context budget exhausted)
      Distill current truth tower into ContinuationBundle.
      Serialize: distilled_goal, summarized_prior_prompt,
      truth_tower_projection (T3-T5 full, T1-T2 summarized),
      cognitive_insights, next_focus, open_questions, constraints.
      Emit ReinjectionTriggered, ContinuationBundleCreated.
      Start fresh prompt with bundle as priming.
      Increment recursion_depth; enforce max_recursion_depth.
```

---

## 5. State Phase 6 operates against

What must exist in the vault before a cycle step can execute, and what gets written:

| State | Direction | Owner | Phase built |
|-------|-----------|-------|-------------|
| Cycle definition (YAML) | read | cycle config file | Phase 6 (new) |
| RuntimeSession record | read/write | sessions table | Phase 6 (new) |
| Leeway grants (loaded) | read | governance/ | Phase 0 (exists, not yet consulted) |
| Constitutional rules (loaded) | read | governance/ | Phase 0 (exists, not yet consulted) |
| ContextPacket | read | retrieval engine | Phase 4 (built) |
| WorkingMemory session | read/write | working_memory table | Phase 5 (built) |
| TruthTower T1 / T2 | read/write | truth_tower_items table | Phase 5 (built) |
| PredictionRecord | write | predictions table | Phase 6 (new) |
| OutcomeRecord | write | outcomes table | Phase 6 (new) |
| EvaluationPacket | write | evaluations table | Phase 6 (new) |
| CatalystArmStats | read/write | catalyst_stats table | Phase 6 (new) |
| ContinuationBundle | write | bundles table / vault file | Phase 6 (new) |
| Inspector events | write | inspector_events + NDJSON | Phase 0 (exists) |

The critical new state types are: `RuntimeSession`, `PredictionRecord`, `OutcomeRecord`, `EvaluationPacket`, and `CatalystArmStats`. None of these have any on-disk representation today.

---

## 6. Events Phase 6 produces

New event types the cycle runtime requires, grouped by sub-phase:

**Session lifecycle:**
```
RuntimeSessionCreated
RuntimeSessionCompleted
RuntimeSessionFailed
```

**Leeway / safety:**
```
LeewayGrantApplied
LeewayGrantDenied
LeewayRevocationFired
LeewaySetEmpty
ConstitutionalBlock       (schema exists; first real use here)
```

**Step execution:**
```
StepExecuted
StepFailed
```

**Signal evaluation:**
```
SignalEvaluated           (EvaluationPacket as payload)
```

**Prediction / learning:**
```
PredictionMade
PredictionResolved
PredictionErrorRecorded
PredictionSevereMiss      (only when |error| > 0.40)
```

**Control:**
```
ClutchDecisionMade
CatalystInvoked
CatalystSelected
```

**Re-injection:**
```
ReinjectionTriggered
ContinuationBundleCreated
```

**Truth Tower (deferred from Phase 5, first emitted here):**
```
TowerTierRebuilt          (when T1 is rebuilt from retrieval at step start)
TowerCollapsed            (when session ends and tower is flushed)
```

Every one of these carries `session_id` as a non-null field. This is the first phase where `session_id` is a first-class populated field rather than an optional annotation.

---

## 7. Integration with Phase 5

Phase 5 built the workspace. Phase 6 uses it.

**What Phase 5 delivered that Phase 6 depends on directly:**

`WorkingMemory` — the cycle runtime writes to working memory after every Clutch decision. `accept` evicts low-salience items and marks the session as converging. `refine` re-pins current T2 items so they persist through the next step. `retrieve_more` triggers a fresh ContextPacket build with updated salience weights, which refreshes T1.

`TruthTower` — T1 is the grounding layer for every step. The ContextPacket's retrieval results auto-populate T1 at cycle start (`TowerTierRebuilt`). The LLM's input is constructed from T1 + T2, not raw retrieval. This means the cycle runtime does not call retrieval directly — it reads the tower. The tower is the mediated view.

`AttentionItemEvicted` / `TowerItemEvicted` — the Clutch's `stop` action triggers a cascade: session marked complete → working memory flushed (`WorkingMemoryCleared`) → tower collapsed (`TowerCollapsed`). This was architecturally planned in Phase 5 but the trigger never existed. Phase 6 is the trigger.

`session_id` in working memory — Phase 5 created sessions (`WorkingMemoryCreated`) but nothing created them except the `cerebra memory` CLI commands. Phase 6 replaces this: the cycle runtime creates the session at step 2, and every working memory operation in the cycle carries that `session_id` forward.

**The key insight about Phase 5 and Phase 6 together:**

Phase 5 built a workspace that can hold things. Phase 6 builds the process that puts things in, takes things out, and decides what to do based on what it finds there. The workspace is only meaningful in the presence of the process. Phase 6 is what gives Phase 5 its purpose.

---

## 8. ES interplay

This is where the event sourcing question becomes concrete.

### 8.1 Session as stream

The most natural ES mapping: one `session_id` = one ES stream. Phase 6 is the first phase where sessions are first-class and systematic. Every event in a cycle run has a non-null `session_id`. This makes Phase 6 the correct insertion point for ES adoption — before this phase, sessions are mostly null; after this phase, sessions are the organizing unit of everything.

If ES is adopted before or during Phase 6, the stream-per-session architecture is free. If adopted after, migrating existing null-session events is awkward.

### 8.2 Branching becomes real

The Clutch can emit a `branch` action. ContinuationBundle creates a new session that is causally a child of the parent session. These are not metaphorical branches — they are exactly what ES's branchable history models. The re-injection loop fires at context boundary and starts a new prompt; that new prompt is a branch of the same cognitive process at the state where context ran out.

ES branches would let you ask: "what would this cycle have produced if the Clutch had said `accept` at step 3 instead of `refine`?" That question is unanswerable with the current flat log. With ES branches, it's a replay operation.

Phase 6 is where branching first matters. Designing the cycle runtime without considering ES branch semantics means retrofitting later.

### 8.3 Pre-action gate ordering

The leeway pre-action gate (Phase 7 in the roadmap, part of the Phase 6 block conceptually) must emit `LeewayGrantApplied` *before* `StepExecuted`. This is a causal ordering requirement. ES's append-only single-writer-per-stream model enforces this correctly. The flat NDJSON log also enforces this, but only because writes happen in process order — there's no structural guarantee.

If any future scenario introduces concurrent event writers (multiple agent processes sharing a vault), the ES single-writer-per-stream constraint is load-bearing for leeway audit correctness.

### 8.4 Post-action audit (Phase 7)

The leeway network's post-action audit is a replay-heavy operation: "for this session, show me all actions that were executed and verify that each one had a corresponding grant." This is a linear scan from version 0 of the session's stream — exactly ES's linear replay pattern. The current `query_by_session()` in SQLiteEventLog is a manual implementation of this; ES gives it for free.

### 8.5 EvaluationPacket as a structured ES payload

The `EvaluationPacket` is the largest and most structured event payload the system will produce: six signal scores, composite, confidence, signal_strength, triangulated reward, and per-signal failure mode flags. This is a natural candidate for a well-typed ES payload with its own `schema_version`. The current inspector envelope's `data_json` TEXT field is flexible but untyped. ES with schema-versioned payloads gives the EvaluationPacket forward-migration guarantees as the signal formula evolves.

### 8.6 Prediction error correlation

`PredictionResolved` events need to correlate with their `PredictionMade` events. Both carry a `prediction_id`. Querying "show me all predictions made in this session and their outcomes" is a cross-event join, currently requiring two SQLite queries. ES's stream model makes this a read of the session stream filtered by event type — simpler and indexable.

### 8.7 Practical accommodations ES needs from Phase 6

If ES adoption happens before or during Phase 6, these decisions need to be made:

1. **session_id as stream ID.** Decide: one stream per session, or one vault-wide stream with session_id as a correlation field. The former gives natural replay granularity; the latter simplifies stream management. Recommendation: per-session streams. The vault-level system events (`VaultCreated`, `MigrationRun`) live on a single `system` stream; everything else is per-session.

2. **event_id migration.** Current format is `evt_<12-hex-uuid>`. ES uses content-addressed IDs (blake3). ES must preserve a user-supplied `event_id` field alongside its content hash, or Phase 6 must adopt the ES ID scheme from the start (and migrate the few existing events from Phases 0–5). Phase 6 is the right migration window — the event log is small and well-defined.

3. **ContinuationBundle as branch.** When re-injection fires, the new session could be modeled as an ES branch from the parent session's stream at the re-injection event. This is architecturally clean but requires the cycle runtime's session model to be branch-aware from initialization. Alternatively, model it as a new independent session with a `parent_session_id` pointer — simpler but loses the replay-from-branch capability. The right call depends on how central counterfactual replay is to the near-term roadmap.

4. **Synchronous emit requirement.** The cycle runtime is fully synchronous. ES's PyO3 API must support synchronous `append(event)` with no async runtime. This was called out in the ES consumer profile (Q26); confirming here that it is non-negotiable.

---

## 9. What makes Phase 6 hard

The implementation risks, named honestly:

**Signal prompts are the load-bearing work.** The six signal checklist prompts (`CEREBRA_SIGNAL_EPISTEMOLOGY.md §8`) are the core of the evaluation sub-phase. Writing prompts that produce reliable 0–1 scores is not a mechanical task. Prompts that are too vague produce random scores; prompts that are too specific overfit to one domain. Each checklist prompt needs calibration data before it can be trusted. The roadmap's 3–4 day estimate for Phase 6 (signals only) may be optimistic.

**Clutch rule design is subtle.** The Clutch's rule cascade (`CEREBRA_COGNITIVE_RUNTIME.md §9`) must handle every combination of signal states correctly. The default rule set will almost certainly be wrong on first attempt. Planning for a calibration period where the Clutch rules are revised based on observed behavior is more honest than treating the first version as final.

**The LLM adapter is a real dependency.** `cerebra/cognition/llm_adapter.py` exists as an `OllamaDirectAdapter` and a `ProxyLLMAdapter`. Step execution requires calling an actual LLM. Phase 6 tests need either a mock adapter (fast but may not reveal real prompt problems) or a local Ollama instance (slower but catches prompt failures). The test strategy needs to commit to one or the other early.

**Session state + working memory + truth tower must stay consistent.** If the cycle runtime crashes mid-step, the session is in an inconsistent state: some events were emitted, working memory may have been updated, but the step has no StepExecuted event. The failure behavior specification in `CEREBRA_COGNITIVE_RUNTIME.md §12` must be implemented carefully. SQLite transactions are the tool here, but the event emission path sits outside the transaction (by design, per the WAL safety rule in `truth_tower.py`). Getting the failure model right without compromising the emit-after-commit discipline is fiddly.

---

## 10. Recommended build order within the block

The roadmap's four-phase ordering (6 → 7 → 8 → 9) is correct and should not be reordered. The dependency chain:

```
Signals + Predictions (Phase 6)
  → you have evaluation before you build control
  
Leeway Network (Phase 7)
  → you have the safety gate before you build the thing it gates
  
Cycle Runtime (Phase 8)
  → you can now wire everything together with confidence
  → prototype gate runs here (see CEREBRA_PROTOTYPE_CHECKLIST.md)
  
Clutch / Catalyst (Phase 9)
  → control and strategy selection on top of a working runtime
```

The prototype gate (ingest → context → step → evaluate → clutch → emit) should run at the end of Phase 8. If it passes, continue. If it doesn't, that's evidence something earlier is wrong; fix before Phase 9.

---

## 11. ES adoption window

The natural adoption window for ES is **between Phase 5 completion and Phase 6 start** — i.e., now. Reasons:

- The event log is small (only Phases 0–5 events, no session events yet). Migration cost is near zero.
- Phase 6 will create the first systematic `session_id` population. Getting the stream model right before the first session is created is easier than retrofitting it after.
- The dual NDJSON + SQLite layer was always intended as a placeholder. Replacing it cleanly requires a green phase boundary, not a mid-phase migration.
- If ES is deferred to Phase 10+ (post-prototype), the cycle runtime will have accumulated hundreds of sessions' worth of events in the old format, and the migration becomes a real project.

If ES is not ready yet: proceed with the current NDJSON + SQLite layer, but name the seam explicitly in Phase 6's implementation so migration is clean. Specifically: isolate all event emission behind an `EventLog` interface, not direct calls to `NDJSONEventLog` and `SQLiteEventLog`, so the implementation can be swapped without touching the cycle runtime.
