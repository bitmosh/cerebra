# Cerebra — Documentation Index

## 1. Purpose

This index explains the Cerebra documentation set and recommended reading order.

Cerebra is a **local-first cognitive runtime** that uses memory as one major subsystem. It is not Policy Scout. It is not LumaWeave. Bons.ai will eventually be expressible as one cycle configuration that Cerebra runs.

Cerebra runs configurable cognitive cycles, maintains durable state and memory, manages working context, evaluates signals, consolidates experience, learns from prediction error, and emits graph-native records.

---

## 2. Current Status

The Cerebra documentation set is **architecture-complete for v0.1**. Every primitive has a specification. Integration points are named. The MVP scope is bounded. The prototype gate is concretely defined.

Doc set version: **v8.1**
Document count: 26 Cerebra docs + 1 Lattica-suite doc

Next step: build the prototype gate and update docs from real implementation evidence. Do not keep planning indefinitely before proving the spine.

---

## 3. Recommended Reading Order

For a fresh reader (human or implementing agent), read in this order:

### 3.1 Foundation (start here)

```text
1. CEREBRA_PROJECT_SCOPE.md          what Cerebra is and what it owns
2. CEREBRA_ARCHITECTURE.md           the system spine and major components
3. CEREBRA_DOC_INDEX.md              this document
```

### 3.2 The Cognitive Runtime Layer (the differentiators)

```text
4. CEREBRA_COGNITIVE_RUNTIME.md      cycle definitions and runtime execution
5. CEREBRA_WORKING_MEMORY_AND_ATTENTION.md   contested working memory + slots
6. CEREBRA_TRUTH_TOWER.md            five-tier structured cognitive workspace
7. CEREBRA_CATALYST.md               multi-factor strategy selector
8. CEREBRA_REINJECTION_LOOP.md       cognitive continuity across context limits
9. CEREBRA_SIGNAL_EPISTEMOLOGY.md    the six perennial threads and core signals
10. CEREBRA_PREDICTION_AND_EVALUATION.md  predictions, outcomes, error learning
```

### 3.3 The Memory Substrate

```text
11. CEREBRA_MEMORY_LAYERS.md         M0-M10 layered memory model
12. CEREBRA_SKU_ADDRESSING.md        multi-pointer cognitive-shape addressing
13. CEREBRA_INGESTION_ARCHITECTURE.md   source-to-memory pipeline
14. CEREBRA_RETRIEVAL_ARCHITECTURE.md   layered hybrid retrieval
15. CEREBRA_CONTEXT_PACKET_PROTOCOL.md  agent-facing memory bundles
16. CEREBRA_SALIENCE_SCORING.md      component-based salience
17. CEREBRA_ORTHOGONAL_ABLATION.md   memory aspect attribution
18. CEREBRA_CONSOLIDATION_ENGINE.md  memory maintenance and synthesis
19. CEREBRA_MEMORY_LIFECYCLE.md      state transitions and tombstones
20. CEREBRA_GRAPH_MODEL.md           graph-ready memory structures
```

### 3.4 Governance and Safety

```text
21. CEREBRA_STATE_GOVERNANCE.md      state schema, events, versioning
22. CEREBRA_LEEWAY_NETWORK.md        permissions-shaped safety architecture
23. CEREBRA_INSPECTOR.md             observability surface and event log
```

### 3.5 Build

```text
24. CEREBRA_MVP_SPEC.md              v0.1 scope and definition of done
25. CEREBRA_IMPLEMENTATION_PLAN.md   build order with milestones
26. CEREBRA_PROTOTYPE_CHECKLIST.md   the prototype gate before MVP
27. CEREBRA_TESTING_STRATEGY.md      testing requirements
```

### 3.6 Cross-Suite

```text
28. LATTICA_PRIMITIVES.md            shared primitives across Lattica projects
```

### 3.7 Housekeeping

```text
- CEREBRA_DRIFT_FIXES_v8.1.md        surgical patches to existing docs
- CEREBRA_OPEN_QUESTIONS.md          resolved/remaining design questions
- CEREBRA_REPLACEMENT_MANIFEST.md    historical migration record
- CEREBRA_MATRICES.md                reference tables for implementation
- CEREBRA_SCENARIO_CARDS.md          example use cases
- CEREBRA_MERMAID_DIAGRAMS.md        diagrams catalog
- CEREBRA_DIAGRAM_MANIFEST.md        diagram metadata
- CEREBRA_VISUAL_PRODUCTION_PLAN.md  visual production guide
```

---

## 4. The Layered Architecture, At A Glance

```text
┌──────────────────────────────────────────────────────────────┐
│ Constitutional Layer (inviolable — see Leeway Network)       │
├──────────────────────────────────────────────────────────────┤
│ Capability Bounds (structural — what adapters exist)         │
├──────────────────────────────────────────────────────────────┤
│ Truth Tower Structural Rules (derivation discipline)         │
├──────────────────────────────────────────────────────────────┤
│ Leeway Network (conditional permissions)                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌────────────────────────────────────────────────────┐    │
│   │ Cycle Runtime                                      │    │
│   │   - Cycle Definitions (Bons.ai as one config)      │    │
│   │   - Clutch (priority-rule controller)              │    │
│   │   - Catalyst (multi-factor strategy selector)      │    │
│   │   - Signal Pipeline (6 perennial threads)          │    │
│   │   - Prediction Layer (expected vs actual)          │    │
│   │   - Re-injection Loop (cognitive continuity)       │    │
│   └────────────────────────────────────────────────────┘    │
│                          ↕                                   │
│   ┌────────────────────────────────────────────────────┐    │
│   │ Truth Tower (M4.5 - derived workspace)             │    │
│   │   T5 Goal / T4 Hypotheses / T3 Insights /          │    │
│   │   T2 Memories / T1 Evidence                        │    │
│   └────────────────────────────────────────────────────┘    │
│                          ↕                                   │
│   ┌────────────────────────────────────────────────────┐    │
│   │ Working Memory (M4 - contested slots)              │    │
│   └────────────────────────────────────────────────────┘    │
│                          ↕                                   │
│   ┌────────────────────────────────────────────────────┐    │
│   │ Memory Substrate                                   │    │
│   │   M0 Sources / M1 Docs / M2 Chunks /               │    │
│   │   M3 Episodic / M5 Semantic / M6 Procedural /      │    │
│   │   M7 Predictive / M8 Graph /                       │    │
│   │   M9 Consolidated / M10 Tombstones                 │    │
│   └────────────────────────────────────────────────────┘    │
│                          ↕                                   │
│   ┌────────────────────────────────────────────────────┐    │
│   │ SKU Addressing (across all memory layers)          │    │
│   │   - 10-digit address: location + entry + tags      │    │
│   │   - Multi-pointer fanout                           │    │
│   │   - Cognitive-shape categories (16 quadrants)      │    │
│   │   - Self-improving retrieval                       │    │
│   └────────────────────────────────────────────────────┘    │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Inspector (observability across all layers)                  │
├──────────────────────────────────────────────────────────────┤
│ Graph Event Emission (to LumaWeave)                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Project Laws

These laws guide every Cerebra implementation decision:

```text
1. Cerebra is a cognitive runtime, not just memory storage.
2. Cerebra owns memory, not visualization.
3. Cerebra is local-first by default.
4. Every memory needs provenance.
5. Retrieval must be layered, not vector-only.
6. Salience must be component-based.
7. Signals must derive from epistemological foundation, not arbitrary metrics.
8. Every cognitive action must be inspectable.
9. Consolidation must not erase source truth.
10. Synthesized memories must be distinguishable from observed memories.
11. Tombstones prevent accidental resurrection.
12. Safety is structural (capabilities + leeway), not procedural (rules-on-rules).
13. The constitutional layer is small (5-10 rules) and inviolable.
14. Graph export is derived from memory records.
15. Bons.ai is a cycle config, not the engine.
16. Policy Scout is optional source material, not Cerebra's core.
17. LumaWeave consumes Cerebra's events; Cerebra does not depend on LumaWeave.
```

---

## 6. Quick Reference — Which Doc Answers Which Question

**"How does Cerebra work overall?"** → ARCHITECTURE + PROJECT_SCOPE

**"What's a cycle and how does it run?"** → COGNITIVE_RUNTIME

**"How does the system decide what to do next?"** → COGNITIVE_RUNTIME §9 (Clutch) + CATALYST

**"How does the system pick strategies?"** → CATALYST

**"How does the system think for longer than a context window?"** → REINJECTION_LOOP

**"What does the system measure and why those things?"** → SIGNAL_EPISTEMOLOGY

**"How does the system learn from its own mistakes?"** → PREDICTION_AND_EVALUATION

**"How is memory addressed?"** → SKU_ADDRESSING

**"How does memory get categorized?"** → SKU_ADDRESSING §4 (16 cognitive categories)

**"How does retrieval work?"** → RETRIEVAL_ARCHITECTURE + SKU_ADDRESSING §11

**"How does the system score memory relevance?"** → SALIENCE_SCORING

**"How does the system know which aspects of a memory matter?"** → ORTHOGONAL_ABLATION

**"How does the system maintain memory over time?"** → CONSOLIDATION_ENGINE + MEMORY_LIFECYCLE

**"How does the system represent thinking-in-progress?"** → TRUTH_TOWER + WORKING_MEMORY_AND_ATTENTION

**"How is safety handled?"** → LEEWAY_NETWORK

**"How do I debug what the system did?"** → INSPECTOR

**"How does Cerebra connect to LumaWeave?"** → INSPECTOR §11 + GRAPH_MODEL §18

**"What do I build for v0.1?"** → MVP_SPEC + IMPLEMENTATION_PLAN

**"What's the first thing to build?"** → PROTOTYPE_CHECKLIST

**"What primitives are shared with other Lattica projects?"** → LATTICA_PRIMITIVES

---

## 7. Implementation Discipline

Before writing more docs, build the prototype gate.

The prototype is defined in `CEREBRA_PROTOTYPE_CHECKLIST.md`:

```text
ingest 3-5 markdown files
load one cycle definition
build one ContextPacket
run one mock cognitive step
score it with component signals
issue one clutch decision
write graph events
export tiny graph JSON
```

When this runs end to end, the spine is proven. Subsequent docs and architecture refinements should follow from what the prototype reveals.

---

## 8. Version History

```text
v1 - v7:    earlier ChatGPT iterations (deprecated; framing was RAG-shaped)
v8:         realignment to cognitive-runtime framing
            (PROJECT_SCOPE, ARCHITECTURE, MEMORY_LAYERS, MVP_SPEC, 
             IMPLEMENTATION_PLAN, DOC_INDEX replaced;
             COGNITIVE_RUNTIME, WORKING_MEMORY_AND_ATTENTION, 
             PREDICTION_AND_EVALUATION added)
v8.1:       cognitive primitives complete
            (SKU_ADDRESSING, ORTHOGONAL_ABLATION, TRUTH_TOWER,
             REINJECTION_LOOP, CATALYST, SIGNAL_EPISTEMOLOGY,
             LEEWAY_NETWORK, INSPECTOR added;
             DRIFT_FIXES patches; LATTICA_PRIMITIVES established;
             OPEN_QUESTIONS resolved)
v0.1:       (in progress) — prototype gate construction
```

---

## 9. Index Doctrine

This index is the navigation map. When new docs are added, this index is updated in the same commit. When the doc set drifts from this index, the index is wrong and must be updated.

Current entry point for any reader: read §3 in order. Diverge as needed for specific questions per §6.

Build the prototype.
