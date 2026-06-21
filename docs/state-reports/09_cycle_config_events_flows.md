# Cerebra — Cycle Config Schema, Event Reference & Data Flows

---

## 1. Cycle Config YAML Schema

Cycle config files live in `cycles/` or at any absolute/relative path. Loaded by `CycleConfig` from `cerebra/cognition/cycle_config.py`.

### Top-level fields

```yaml
name: "simple.planning.v0"       # string, human-readable name
version: 1                        # int, config schema version
description: "..."               # string

max_steps: 8                      # int — hard ceiling on step count
composite_floor: 0.3              # float — floor used by composite_floor_consecutive stop condition
max_recursion_depth: 0            # int — 0 = no reinjection; N = allow N child sessions

steps: [...]                      # list[StepConfig]
stop_conditions: [...]            # list[StopConditionConfig]
clutch_rules: [...]               # list[ClutchRuleConfig]
catalyst_arms: [...]              # list[CatalystArmConfig] — optional
reinjection_triggers: [...]       # list[ReinjectionTriggerConfig] — optional
```

### StepConfig fields

```yaml
steps:
  - name: "understand_goal"
    description: "Analyze the goal and identify key constraints"
    role: "comprehension"                  # optional; semantic tag, not enforced
    prompt_template:
      template: |
        Goal: {{ goal }}
        
        Retrieved context:
        {{ retrieved_context }}
        
        {% if strategy_hint %}
        Strategic guidance: {{ strategy_hint }}
        {% endif %}
        
        Understand and analyze the goal thoroughly.
      expected_output_format: "prose"      # optional hint for signal evaluators
```

**Available template variables:**

| Variable | Source | Type |
|---|---|---|
| `{{ goal }}` | RuntimeSession.goal | str |
| `{{ retrieved_context }}` | `render_text(context_packet)` | str |
| `{{ prior_step_output }}` | last step's LLM output | str |
| `{{ prior_steps[N] }}` | Nth step's output (0-indexed) | str |
| `{{ strategy_hint }}` | CatalystEngine selected arm | str or empty |
| `{{ truth_tower }}` | `tower.render_chronological()` | str |
| `{% if var %}...{% endif %}` | Jinja2-style conditional | block |

### StopConditionConfig fields

```yaml
stop_conditions:
  - name: "hit_max_steps"
    type: "max_steps_reached"
    parameters:
      max_steps: 8          # int

  - name: "all_done"
    type: "all_steps_completed"
    parameters: {}          # no parameters

  - name: "floor_3_consecutive"
    type: "composite_floor_consecutive"
    parameters:
      floor: 0.35           # float
      n: 3                  # int — consecutive steps below floor

  - name: "clutch_said_stop"
    type: "explicit_clutch_stop"
    parameters: {}

  - name: "interrupted"
    type: "user_interrupt"
    parameters: {}
```

### ClutchRuleConfig fields

```yaml
clutch_rules:
  - name: "accept_high_quality"
    description: "Accept when composite exceeds threshold"
    predicate_name: "composite_above_threshold"
    action: "accept"
    parameters:
      threshold: 0.75       # predicate-specific

  - name: "stop_if_degrading"
    predicate_name: "consecutive_steps_below_floor"
    action: "stop"
    parameters:
      floor: 0.35
      n: 3
```

Rules are evaluated in config order. First match wins. If no rule matches, `escalate_to_catalyst=True`.

### CatalystArmConfig fields

```yaml
catalyst_arms:
  - arm_id: "constraint_check"
    type: "verification"               # semantic type (used by type_penalty)
    mapped_action: "critique"          # maps to a clutch action
    strategy_prompt: |
      Review the constraints on this problem carefully.
      Identify which constraints are hard (non-negotiable) vs. soft (negotiable).
      Make sure your plan respects all hard constraints.
```

### ReinjectionTriggerConfig fields

```yaml
reinjection_triggers:
  - name: "retry_if_no_acceptance"
    predicate: "max_steps_without_acceptance"   # must be in BUILTIN_REINJECTION_PREDICATE_NAMES
    parameters: {}
```

---

## 2. Built-in Cycle: `simple.planning.v0`

File: `cycles/simple.planning.v0.yaml`

**Purpose:** Basic linear planning cycle. No catalyst arms, no reinjection.

```
max_steps: 8
composite_floor: 0.35 (implicit via stop conditions)
max_recursion_depth: 0
```

### Steps (5)

| # | name | role | description |
|---|---|---|---|
| 1 | `understand_goal` | — | Analyze goal, identify constraints |
| 2 | `draft_plan` | — | Produce initial plan |
| 3 | `critique_plan` | — | Identify weaknesses in plan |
| 4 | `refine_plan` | — | Apply critique, improve plan |
| 5 | `finalize` | — | Produce final, polished output |

### Stop conditions (5)

1. `max_steps_reached` (max_steps=8)
2. `all_steps_completed`
3. `composite_floor_consecutive` (floor=0.35, n=3)
4. `explicit_clutch_stop`
5. `user_interrupt`

### Clutch rules (4)

| Rule | Predicate | Action |
|---|---|---|
| `accept_high_quality` | `composite_above_threshold(0.75)` | `accept` |
| `refine_if_low` | `composite_below_threshold(0.45)` | `refine` |
| `critique_if_medium` | `composite_in_range(0.45, 0.65)` | `critique` |
| `stop_if_degrading` | `consecutive_steps_below_floor(0.35, 3)` | `stop` |

No catalyst arms. No reinjection triggers.

---

## 3. Built-in Cycle: `planning.adaptive.v0`

File: `cycles/planning.adaptive.v0.yaml`

**Purpose:** Adaptive planning with catalyst arm selection and optional reinjection.

```
max_steps: 12
composite_floor: 0.3
max_recursion_depth: 3
```

### Steps (5, with roles)

| # | name | role | description |
|---|---|---|---|
| 1 | `understand_goal` | `comprehension` | Deep goal analysis |
| 2 | `draft_plan` | `generation` | Initial plan generation |
| 3 | `critique_plan` | `critique` | Critical analysis of plan |
| 4 | `refine_plan` | `refinement` | Integrate critique |
| 5 | `finalize` | `synthesis` | Synthesize final output |

### Stop conditions (5)

Same set as `simple.planning.v0`, with adjusted parameters:
1. `max_steps_reached` (max_steps=12)
2. `all_steps_completed`
3. `composite_floor_consecutive` (floor=0.3, n=4) — more lenient (lower floor, more consecutive)
4. `explicit_clutch_stop`
5. `user_interrupt`

### Clutch rules (6)

| Rule | Predicate | Action |
|---|---|---|
| `accept_high_quality` | `composite_above_threshold(0.78)` | `accept` |
| `refine_if_low` | `composite_below_threshold(0.40)` | `refine` |
| `critique_if_medium` | `composite_in_range(0.40, 0.65)` | `critique` |
| `epistemic_check` | `epistemic_humility_low(0.35)` | `retrieve_more` |
| `groundedness_boost` | `groundedness_low(0.40)` | `retrieve_more` |
| `stop_if_degrading` | `consecutive_steps_below_floor(0.30, 4)` | `stop` |

### Catalyst arms (5)

| arm_id | type | mapped_action | purpose |
|---|---|---|---|
| `constraint_check` | `verification` | `critique` | Identify hard vs. soft constraints |
| `decomposition` | `structuring` | `explore` | Break problem into sub-problems |
| `risk_assessment` | `verification` | `critique` | Identify risks and failure modes |
| `prerequisite_id` | `structuring` | `explore` | Identify what must be resolved first |
| `resource_estimate` | `estimation` | `refine` | Estimate resources needed |

### Reinjection triggers (1)

`max_steps_without_acceptance` — fires when cycle hits `cap_reached` and no step was accepted. With `max_recursion_depth=3`, allows up to 3 child sessions.

---

## 4. Fossic Event Reference

All Fossic events are appended to streams via `FossicStore.append()`. Every event has a `causation_id` (bytes) linking it to its predecessor in the chain.

### Stream: `cerebra/agent-trace/<session_id>`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `SessionOpened` | SessionManager | session_id, goal, cycle_config, opened_at, parent_session_id, recursion_depth |
| `CycleStarted` | CycleRuntime | session_id, cycle_id (= session_id), cycle_config, goal |
| `StepStarted` | CycleRuntime | step_index, step_name, cycle_id |
| `ContextPacketBuilt` | build_context_packet | context_packet_id, selected_count, is_abstained, mode |
| `PredictionMade` | PredictionPipeline | prediction_id, expected_composite, basis, confidence |
| `StepExecuted` | CycleRuntime | step_id, step_name, output (truncated), cited_record_ids |
| `StepExecutionFailed` | CycleRuntime | step_id, step_name, error, attempt_count |
| `SignalEvaluated` | EvaluationComposer | signal_name, score, strength, low_confidence |
| `EvaluationComposed` | EvaluationComposer | composite_score, confidence, per_signal, low_confidence_signals |
| `OutcomeRecorded` | PredictionPipeline | outcome_id, prediction_error, error_classification, actual_composite |
| `PredictionSevereMiss` | PredictionPipeline | outcome_id, prediction_error, step_name (error ≥ 0.15) |
| `ClutchDecisionMade` | ClutchEngine | action, rule_matched, escalate_to_catalyst, cascade_depth |
| `CatalystInvoked` | CatalystEngine | session_id, step_name, arm_count |
| `CatalystArmSelected` | CatalystEngine | arm_id, arm_type, strategy_prompt, score |
| `LeewayGrantApplied` | LeewayPreActionGate | rule_id, capability, grants_applied |
| `LeewayGrantDenied` | LeewayPreActionGate | rule_id, capability, forbidden_by |
| `LeewayRevocationFired` | LeewayPreActionGate | rule_id, capability, revocation_reason |
| `MemoryWriteFromCycle` | CycleRuntime | record_id, step_id, cited_record_ids |
| `CycleCompleted` | CycleRuntime | outcome, steps_run, final_composite |
| `SessionFlushed` | CycleRuntime | session_id, outcome, total_cycles, total_steps, flushed_at |
| `ReinjectionTriggered` | CycleRuntime | trigger_name, child_session_id, recursion_depth |
| `CheckpointSaved` | HTTP daemon | bundle_id, session_id |

### Stream: `cerebra/control`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `PostureChanged` | HTTP daemon | new_state ("auto"\|"hold"), previous_state |

### Stream: `cerebra/lattice/<lineage_id>`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `LatticeCommit` | SKUClassifier | primary_record_id, sibling_record_ids, lineage_id, categories, threshold |

### Stream: `cerebra/graph/<lineage_id>`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `GraphSnapshotAvailable` | export_graph | graph_path, node_count, edge_count, vault_path, triggered_by |

---

## 5. Inspector Event Reference

Inspector events use the `InspectorEvent` dataclass (see doc 08). Key event types by subsystem:

### Vault / System

| Event type | actor | subject_id | Notes |
|---|---|---|---|
| `SystemInitialized` | system | vault_id | On any startup |
| `VaultCreated` | vault | vault_id | After init_vault() |
| `MigrationRun` | migrations | vault_id | Per migration applied |
| `ConfigLoaded` | config | vault_id | |
| `LeewayRuleLoaded` | governance | rule_id | Per rule loaded at startup |
| `ConstitutionalBlock` | governance | rule_id | When CONST rule would have forbidden (currently no-op) |

### Ingest

| Event type | subject_id | Notes |
|---|---|---|
| `SourceRegistered` | source_id | New source |
| `SourceChanged` | source_id | Content changed |
| `SourceParsed` | source_id | Successfully parsed |
| `SourceParseFailed` | source_id | Adapter raised exception |
| `DocumentNormalized` | document_id | |
| `DocumentParseWarning` | document_id | Partial parse success |
| `ChunkCreated` | chunk_id | Per chunk (may be high volume) |
| `MemoryRecordCreated` | record_id | Per record |
| `LexicalIndexUpdated` | — | After FTS5 rebuild |
| `ArtifactWritten` | document_id | After write_artifact() |

### SKU / Lattice

| Event type | subject_id | Notes |
|---|---|---|
| `SKUAssigned` | record_id | First classification |
| `SKUReclassified` | record_id | Version upgrade |
| `ClassificationFailed` | record_id | Unrecoverable error |
| `ClassificationLowConfidence` | record_id | confidence < 0.5 |
| `BackfillStarted` | — | |
| `BackfillCompleted` | — | Includes BackfillReport stats |
| `LatticeCommit` | lineage_id | Multi-category commit |

### Graph

| Event type | subject_id | Notes |
|---|---|---|
| `GraphNodeCreated` | node_id | During ingest (not export) |
| `GraphEdgeCreated` | edge_id | During ingest |
| `GraphExported` | out_path | After export_graph() |
| `GraphSnapshotAvailable` | lineage_id | Hub-direct write succeeded |

### Retrieval

| Event type | subject_id | Notes |
|---|---|---|
| `QueryReceived` | trace_id | |
| `QueryPlanned` | trace_id | Includes mode, d1_hint |
| `TraversalStepCompleted` | trace_id | Per step (6 events per retrieval) |
| `ContextPacketBuilt` | context_packet_id | |
| `LatticeSiblingResolved` | lineage_id | Per lattice group resolved |

### Memory / Tower

| Event type | subject_id | Notes |
|---|---|---|
| `AttentionItemProposed` | record_id | WM proposed |
| `AttentionItemPromoted` | wm_item_id | WM inserted |
| `AttentionItemEvicted` | wm_item_id | LRU evicted |
| `AttentionItemDeferred` | record_id | Capacity guard |
| `TowerInitialized` | session_id | First T1 promotion |
| `TowerItemPromoted` | tower_item_id | T1 or T2 |
| `TowerItemEvicted` | tower_item_id | Capacity eviction |
| `TowerItemStaled` | tower_item_id | T2 staled by T1 eviction |
| `TowerCrossReferenceAdded` | tower_item_id | T2 cites T1 |
| `TowerRendered` | session_id | `included_in_packet` flag |
| `MemoryRecordArchived` | record_id | |
| `MemoryRecordTombstoned` | record_id | |
| `MemoryRecordRestored` | record_id | |

---

## 6. Data Flows

### Ingest flow

```
cerebra ingest <target>
  ↓
discover_files(target, extensions, exclude_patterns)
  ↓ for each file:
  detect_type(file) → DetectionResult
  register_source(store, event_log, path, detection, versions)
    → RegistrationOutcome
  
  [SKIPPED_UNCHANGED] → skip file
  [NEW | CHANGED] → continue:
  
  adapter.parse(path, source) → ParseResult
  write_artifact() → <vault>/artifacts/<doc_id>.json
  write_text_artifact() → <vault>/data/<doc_id>.txt
  store.insert_document()
  upsert_node("source:<id>", "spine")
  upsert_node("document:<id>", "document")
  upsert_edge(source → document, "contains")
  chunk_document() → list[Chunk]
  store.insert_chunks_batch()
  for chunk: upsert_node + edges (CONTAINS, PART_OF)
  build_records_for_document() → list[MemoryRecord]
  store.insert_records_batch()
  for record: upsert_node + DERIVED_FROM edge
  update_fts_index(record_ids)       ← full FTS5 rebuild
  queue_for_embedding(record_ids)    ← deferred unless --embed
  source.parser_status = "parsed"
  emit SourceParsed
  ↓
IngestReport
```

### SKU Classify flow

```
cerebra classify
  ↓
query: memory_records WHERE sku_address IS NULL
  ↓ for each record (batch_size at a time):
  SKUClassifier.classify_record_lattice(record_id, content, detected_type)
    ↓
    LLM: classify_quadrant(content)          ← LLM call 1
      → 4 quadrant scores + primary quadrant
    LLM: classify_within_quadrant(content, q) ← LLM call 2
      → 4 category scores within quadrant + D1 answer
    evaluate_lattice(scores, threshold=0.65)
      → LatticeDecision (should_multi_commit?)
    
    [should_multi_commit=False]:
      store.insert_sku_assignment()
      store.update_record_sku()
      emit SKUAssigned
    
    [should_multi_commit=True]:
      insert primary sku_assignment
      for each secondary category:
        build_sibling_record_id(primary_id, category)  ← deterministic
        INSERT sibling into memory_records (is_lattice_member=True)
        INSERT sibling sku_assignment
      emit LatticeCommit (one event total, not per-sibling)
    
    if confidence < 0.5: emit ClassificationLowConfidence
    queue_for_embedding([primary_id, ...sibling_ids])
  ↓
BackfillReport
```

### Retrieval / Context flow

```
cerebra context <query>   OR   CycleRuntime._retrieve_for_step()
  ↓
RetrievalPlanner.plan(query)
  → QueryPlan {mode, trace_id, d1_hint, max_candidates}
  emit QueryReceived + QueryPlanned
  ↓
RetrievalTraversal.traverse(db_path, plan)
  Step 1: exact_sku      → candidates (if d1_hint)
  Step 2: partial_sku    → candidates (if d1_hint + need more)
  Step 3: sibling_traversal → pass-through (stub)
  Step 4: lexical_search → FTS5 MATCH (if lexical|hybrid)
  Step 5: vector_fallback → cosine similarity (if vector|hybrid)
  Step 6: trace_annotation → dedup + annotate retrieval_path
  emit TraversalStepCompleted ×6
  ↓
score_candidates(candidates, plan)
  composite = 0.40×semantic + 0.25×lexical + 0.15×sku + 0.10×recency + 0.10×lifecycle
  ↓
dedup_siblings(scored, query_d1, db_path, trace_id)
  D2 routing: sku_match → sku_match_multi → composite_score
  emit LatticeSiblingResolved per lattice group
  ↓
filter_by_floor(deduped, floor=0.35)
  → selected (≥ floor) + excluded
  ↓
  [selected is non-empty]:
    build_context_packet(trace, selected, limit=10)
      SELECT content, source info for top-10 records
      UPDATE retrieval_traces.context_packet_id
      TruthTower.to_tower_field() → tower dict
      emit ContextPacketBuilt
      → ContextPacket {is_abstained=False, selected_memory=[...]}
  
  [selected is empty]:
    build_abstained_packet(trace, best_score_seen)
      → ContextPacket {is_abstained=True, selected_memory=[]}
```

### Cycle Runtime flow

```
cerebra run-cycle <config> --goal "..."
  ↓
SessionManager.open_session(goal, config, vault_path)
  INSERT runtime_sessions
  fossic append SessionOpened → cerebra/agent-trace/<session_id>
  → (RuntimeSession, opened_event_id: bytes)
  ↓
CycleRuntime(config, session, db_path, store, llm, opened_event_id)
  fossic: CycleStarted (causation=opened_event_id)
  ↓
  LOOP while not stopped:
    StopConditionEvaluator.check(cycle_state) → (stop?, reason)
    if stop: break
    
    resolve step from config (round-robin if past last step)
    
    [RETRIEVAL]:
    RetrievalPlanner.plan(goal) → QueryPlan
    traverse → score → dedup_siblings → filter → packet
    fossic: ContextPacketBuilt
    
    [PREDICTION]:
    PredictionPipeline.predict(prior_composites) → PredictionRecord
    INSERT predictions
    fossic: PredictionMade
    
    [LLM]:
    render_template(step, {goal, retrieved_context, tower, strategy_hint})
    llm.chat(rendered_prompt) → output        [5s retry, 1 retry max]
    fossic: StepExecuted (or StepExecutionFailed)
    
    [EVALUATE]:
    for signal in SIGNAL_EVAL_ORDER:
      if signal == EPISTEMIC_HUMILITY: marker_based_eval()
      else: llm.complete_structured(signal_prompt, schema)
      fossic: SignalEvaluated (causation-chained)
    EvaluationComposer.compose(signals) → EvaluationPacket
    fossic: EvaluationComposed
    
    [OUTCOME]:
    PredictionPipeline.resolve(prediction, eval) → OutcomeRecord
    INSERT outcomes
    fossic: OutcomeRecorded
    if severe: fossic: PredictionSevereMiss
    
    [CITATIONS]:
    cited = re.findall(r'\brec_[0-9a-f]{12}\b', output)
    wm.promote(rec_id, salience=0.8) for each cited
    
    [CLUTCH]:
    ClutchEngine.decide(context) → ClutchDecision
    fossic: ClutchDecisionMade
    if clutch.escalate_to_catalyst:
      CatalystEngine.select() → CatalystSelection | None
      if selected: fossic: CatalystInvoked + CatalystArmSelected
    
    [GOVERNANCE]:
    LeewayPreActionGate.evaluate(ProposedAction("write_to_episodic_memory"))
    if permitted:
      fossic: LeewayGrantApplied
      EpisodeWriter.write(output, ...) → record_id
        INSERT cycle_episode_records
        INSERT memory_records (record_type="cycle_episode", synthetic FKs)
        queue_for_embedding([record_id])
      fossic: MemoryWriteFromCycle
    
    cycle_state.steps_run += 1
    prior_composites.append(eval.composite_score)
    if clutch.action == "stop": cycle_state.explicit_stop = True
  ↓
fossic: CycleCompleted {outcome, steps_run, final_composite}
SessionManager.flush_session(session_id, outcome, ...)
fossic: SessionFlushed
  ↓
[REINJECTION]:
ReinjectionTriggerEvaluator.evaluate(reason, step_history, depth, max_depth)
if should_fire AND not blocked:
  BundleDistiller.distill(...) → ContinuationBundle
  write_bundle(db_path, bundle)
  SessionManager.open_session(parent_session_id=session_id)  ← recursive
  CycleRuntime(child_session).run()
  fossic: ReinjectionTriggered
  ↓
return CycleResult
```

### Graph Export flow

```
cerebra export-graph [--out PATH]
  ↓
export_graph(vault_path, out_path, event_log, hub_store, triggered_by)
  ↓
  SQL: SELECT active sources WHERE canonical_path NOT LIKE 'cerebra://%'
    ORDER BY canonical_path LIMIT 2000
  SQL: SELECT active records JOIN sku_assignments ON record_id
    (only classified records get nodes)
  
  BUILD nodes:
    spine node per source:
      id="source:<source_id>", type="spine"
      cluster: detected_type → azure|slate|gray|teal
    memory_record node per classified record:
      id="record:<record_id>", type="memory_record"
      cluster: d1_quadrant → azure|gold|purple|teal
  
  BUILD edges:
    contains: source→record (weight=0.4) for each record's source
    describes: record[N]→record[N+1] (weight=0.65) for adjacent chunk_index pairs in same doc
    sku-proximity: record→record (weight=min(0.5, group_size/20)) for shared D1
      → capped at _SKU_PROXIMITY_CAP=5 per node
    sku-exact: record→record (weight=0.9) for identical sku_address
  
  WRITE: <vault>/.cerebra/graph.json (cerebra/v1 schema)
  
  [if hub_store]:
    hub_store.append(
      "cerebra/graph/<lineage_id>",
      "GraphSnapshotAvailable",
      {graph_path, node_count, edge_count, ...}
    )
    ← errors swallowed (non-fatal)
  
  emit GraphExported inspector event
  return ExportStats
```
