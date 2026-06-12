# Cerebra Phase 6 Block — Needs Assessment

*Locked decisions and design constraints for the Phase 6 block (Phases 6 through 11 of the roadmap, collectively the cycle runtime). Produced from a five-layer assessment conversation on 2026-06-12, incorporating the event-sourced cognitive substrate architectural insight, fossic v1 ground truth from the fossic interview, and Lattica Claude's coordination responses. Input document for the Phase 6 block design doc.*

---

## 0. One-sentence thesis

Phase 6 (block) gives Cerebra an execution loop — the structure that turns accumulated memory and working context into goal-directed, evaluable, governable action. Phases 0–5 built a system that knows things; this block builds the system that does something with what it knows.

## 1. Block scope

The Phase 6 block comprises six sub-phases that are architecturally inseparable but build sequentially:

| Sub-phase | Name | Scope | Version | Wall-clock estimate at established pace |
|-----------|------|-------|---------|----------------------------------------|
| Phase 6 | Signal pipeline + prediction records | Six-signal evaluator with single-prompt evaluation, EvaluationPacket schema, PredictionRecord/OutcomeRecord schemas | v0.3.0 | ~few hours |
| Phase 7 | Leeway pre-action gate | Wire existing leeway substrate into action proposal path, composition-by-union semantics, LeewayGrantApplied events | v0.3.1 | ~few hours |
| Phase 8 | Cycle runtime skeletal | End-to-end cycle execution with real Ollama, ContinuationBundle schema, re-injection trigger | v0.3.2 | ~half day |
| Phase 9 | Clutch + Catalyst | Wire Clutch decisions, naive count-based Catalyst arm learning, accept/refine/branch/stop actions | v0.3.3 | ~few hours |
| Phase 10 | Consolidation | Session summary + calibration audit, summary becomes retrievable memory | v0.3.4 | ~few hours |
| Phase 11 | Graph export | JSON serialization of Cerebra state (full structure minus temporal layer) for LumaWeave consumption | v0.3.5 | ~few hours |

v0.1 of the broader Cerebra MVP is v0.3.5 — the Phase 6 block completion is the v0.1 milestone.

## 2. Block-level success criterion

The block ships successfully when this command works end-to-end:

```bash
cerebra run-cycle simple.planning.v0 --goal "Draft a prototype plan"
```

The command must:
1. Open a session
2. Build a ContextPacket from the goal
3. Execute one cognitive step with real Ollama
4. Score the output with all six signals (single-prompt each)
5. Make a Clutch decision (accept/refine/branch/stop)
6. Loop or stop based on the decision
7. On stop, consolidate the session
8. Optionally export graph state

If that command produces a session with a consolidated summary, the block succeeded.

## 3. Per-sub-phase success criteria

Each sub-phase closes when its specific demonstration works:

**Phase 6 (v0.3.0):** Six signals callable from Python with single-prompt evaluation, EvaluationPacket and PredictionRecord/OutcomeRecord schemas working in isolation. No cycle runs yet — evaluation infrastructure standing alone with tests.

**Phase 7 (v0.3.1):** LeewayRule loading from `governance/`, rule evaluation against proposed actions, LeewayGrantApplied events emitted, composition-by-union semantics tested. Still no cycle running.

**Phase 8 (v0.3.2):** `cerebra run-cycle` works end-to-end with real Ollama, single cycle executes, ContinuationBundle schema in place. ContextPacket → step → evaluation → memory write loop closes.

**Phase 9 (v0.3.3):** Clutch decisions wired to cycle, Catalyst arm selection working, accept/refine/branch/stop actions functional, naive count-based arm learning updates after each decision.

**Phase 10 (v0.3.4):** `cerebra consolidate --session <id>` produces summary plus calibration audit, summary becomes retrievable memory record, calibration delta logged for signal scoring formulas.

**Phase 11 (v0.3.5):** `cerebra export graph --out cerebra_graph.json` produces JSON LumaWeave can consume, includes nodes plus structural plus semantic plus lattice edges. No temporal graph layer.

## 4. Foundational architectural commitments

Three commitments shape every sub-phase. These must be honored throughout implementation:

### 4.1 Event-sourced cognitive substrate

Lattice nodes (and eventually other memory records) become event-sourced aggregates with reducers folding events into continuous state. The architecture follows three-way write decomposition:

- Pre-Phase-6 cognitive events (ingest, classification, retrieval, working memory, tower) continue writing to Cerebra's `inspector_events` via SQLiteEventLog. Adapter surfaces these into fossic streams read-only when adapter ships (v0.2 work).
- Phase 6 cycle runtime events write directly to fossic via `store.append()` into `cerebra/agent-trace/<cycle_id>` streams.
- Lattice node aggregate events write directly to fossic into `cerebra/lattice/<lineage_id>` streams. Reducers registered against `cerebra/lattice/*` via pattern-based registration per fossic's DynReducer pattern.

Read adapter is NOT Phase 6 critical path. It's v0.2 cleanup work.

### 4.2 Cognitive dithering

Events are discrete by necessity (audit substrate). Aggregate state derived from events is continuous in appearance (cognitive substrate). The reducer is the integration step that turns discrete events into continuous-feeling state.

This resolves the discrete-vs-continuous tension explicitly. Phase 6 design operates against aggregate state where it needs continuity (signal trajectories, working memory dynamics, cycle progress) and against raw events where it needs discreteness (audit, replay, observability).

### 4.3 Synchronous at substrate, async at consumption boundary

fossic's append path is synchronous (reducers are pure synchronous functions per ADR-002). Cerebra's cycle runtime within a single cycle is synchronous. The consumption boundary is async — subscribers to event streams (witness layer, time-travel viewer, Lattica's observability) operate asynchronously without coordinating.

For Phase 6 specifically: cycles are synchronous internally. The daemon mode (cerebra serve, deferred to post-block) introduces async at the IPC boundary, but each cycle still runs synchronously.

## 5. Locked architectural decisions

Eight decisions locked from v2 thesis section 17 plus subsequent coordination:

1. **ES adoption timing:** fossic is ready (v1.0-rc.1, 158 tests passing). Phase 6 uses fossic natively from day one. No EventLog seam wrapping fossic — Cerebra's SQLiteEventLog stays for its existing purposes; cycle runtime calls `store.append()` directly.

2. **Stream granularity:** Per-session streams for cycle events (`cerebra/agent-trace/<cycle_id>`); per-lineage streams for lattice aggregates (`cerebra/lattice/<lineage_id>`).

3. **ContinuationBundle model:** ES branch via fossic's branching support, with `parent_session_id` causation pointer.

4. **Event ID format:** Content-addressed via blake3 per fossic's CCE schema. `evt_<uuid>` preserved as `external_id` on the events table. Full backfill of existing inspector_events on first adapter run (when adapter eventually ships) — single-second cost, preserves complete lineage history for reducers.

5. **LLM adapter test strategy:** Local Ollama for integration tests, mock adapter for unit tests.

6. **Signal prompt calibration:** Budget one calibration iteration after first cycle run. v0.1 ships single-prompt evaluation per signal.

7. **Clutch rules:** Pre-written for v0.1 with revision budget after calibration.

8. **Session_id enforcement:** Required in cycle runtime path, nullable elsewhere for backward compatibility.

Plus four operational decisions from coordination:

9. **Agent-trace stream pattern:** `cerebra/agent-trace/<cycle_id>` with single-segment `<cycle_id>` (UUIDs or short slugs), under 256-char stream ID limit. Forward-compatible extension `cerebra/agent-trace/<cycle_id>/<sub_id>` available via `**` glob subscription when sub-cycles needed.

10. **Reducer schema_version discipline:** Every reducer sets `state_schema_version` explicitly from first implementation, even when value is 1. Required to prevent messy snapshot invalidation when state shape later evolves.

11. **Real Ollama from Phase 8 onward:** Mock LLM only for unit tests. Phase 8 introduces real LLM calls; Phase 9 builds on real signal data.

12. **Re-injection across phases 8/9/10:** Phase 8 ships ContinuationBundle schema and re-injection trigger mechanics. Phase 9 ships the Clutch decision that spawns continuations. Phase 10 handles consolidation across continuation chains.

## 6. v0.1 vs deferred scope

Within the Phase 6 block, what ships in v0.1 vs defers to v0.2+:

**Signal evaluation depth:** v0.1 ships single-prompt evaluation per signal. v0.2 adds multi-prompt triangulation for high-stakes evaluations.

**EPISTEMIC HUMILITY sophistication:** v0.1 ships marker-based detection (presence of uncertainty markers boosts score; absence in confident claims penalizes). v0.1 medium adds checklist depth. v0.2 adds calibration against ground truth.

**ContinuationBundle voice modes:** v0.1 ships `system` voice only (task-brief style). v0.2 adds `self` voice (first-person, requires consistent persona across continuations).

**Catalyst arm learning:** v0.1 ships naive count-based updates (good outcome → increment arm weight). v0.2 adds proper bandit algorithm (Thompson sampling or epsilon-greedy with calibration).

**Consolidation depth:** v0.1 ships session summary plus calibration audit. v0.2 adds cross-session consolidation and pattern detection across sessions.

**Graph export richness:** v0.1 ships full structural plus semantic plus lattice edges. v0.2 adds temporal graph layer (state at time T).

**Explicitly deferred to v0.2+:**
- Full event-sourced aggregate architecture (Phase 6 sets foundation; full migration is v0.2)
- Dark matter substrate (shadows captured but not training-consumed in v0.1)
- Witness layer projections (Phase 6 events are witness-substrate-ready; witness consumer is v0.2)
- Counterfactual cognition via branching (Phase 8 ships branching mechanism; cognitive use is v0.2)
- Cognitive extensions (lenses, frame, methodology — all v0.2 or later)
- Crypto-shredding session deletion (fossic v1.1 deliverable; `purge_event` is the v0.1 interim)
- OTel GenAI export (fossic v1.1 deliverable; v0.1 emits to fossic streams natively, OTel export adds retroactively)
- Daemon mode (cerebra serve — block-relative future work)

## 7. Phase 6 block prerequisites

Four items must clear before Phase 6 implementation begins. Three are fossic-side (Lattica Claude has scheduled them); one is Cerebra-side.

### Fossic-side (in-flight, ETA today)

**Aggregate volume benchmark.** Validates that fossic's snapshot caching delivers sub-millisecond `read_state` latency at Cerebra's expected aggregate scale (thousands of streams, each potentially accumulating hundreds of events). Headline metric: `read_state` on 1000-event stream with snapshot at version 900 should be sub-millisecond. If passing, aggregate-runtime architecture validated. If failing, fossic optimization needed before Cerebra integrates. Spec at `fossic_aggregate_volume_benchmark_spec.md`.

**CCE Python test vector harness.** `fossic-py/tests/test_cce_vectors.py` loading shared `cce-test-vectors.json` and asserting Python CCE implementation produces byte-identical output to Rust. Unblocks Cerebra's CI gate on reducer correctness.

**Agent-trace pattern documentation.** AGENT_TRACE_VOCABULARY.md updated to document `cerebra/agent-trace/<cycle_id>` as the canonical Cerebra namespace.

### Cerebra-side

**Cycle runtime event vocabulary finalization.** Companion document `cerebra_phase6_event_vocabulary.md` specifying every Phase 6 event type with payload schema, determinism flag, causation chain, and indexed_tags recommendations. Drafted alongside this needs assessment.

## 8. Prototype gate

Bandit-mediated gate at the start of Phase 8 (cycle runtime skeletal). Before building Phase 8 in full, bandit reads the Phase 8 design doc with all prerequisites locked and either:

a) Confirms full implementation is the proof and proceeds directly to Phase 8 Step 1, or

b) Flags integration risks that warrant a thin prototype first, in which case the prototype becomes Phase 8 Step 0: three docs ingested, one cycle config loaded, one ContextPacket built, one mock step run, one signal evaluated, one accept-only Clutch decision, graph events emitted, graph export tested.

The decision happens at Phase 8 kickoff with full context, not before.

## 9. Cross-project coordination state

**fossic v1.0-rc.1 ships before Phase 6 starts.** 158 core tests passing. Pass 10 deliverables complete (DynReducer, Python wiring, Node wiring, Tauri plumbing, typed errors, SimilaritySearchProvider stub).

**Lattica Claude is the coordination point for fossic-side work.** Cross-Claude relay via Chrome side-panel Claude is functional for substantive back-and-forth.

**Read adapter (inspector_events → fossic streams) is off the Phase 6 critical path** per the three-way write model. It becomes v0.2 cleanup work that unifies historical events with native streams.

**LumaWeave wiring blocked on Phase 11 graph export.** No Phase 6 dependency on LumaWeave; LumaWeave consumes Phase 6 output.

**Policy Scout Track 2 runs in parallel** without Phase 6 dependency. Eventual eval-core extraction is separate post-v0.1 work.

## 10. Multi-agent build coordination

Phase 6 block implementation may use multiple Claude Code agents working in parallel on different sub-phases or sections within a sub-phase. If multi-agent build is used:

**Coordination doc is source of truth.** Single document specifies section boundaries, interface contracts at each boundary, which agent owns which section, integration test surface, merge order. All agents read this first.

**Each agent owns its section's tests plus integration tests against adjacent sections' published interfaces.** Forces interface stability through cross-agent test coverage.

**Mandatory deviation log per pass** at `docs/agent/deviations/<version>.md` regardless of how many agents participated. Each agent maintains its own deviation log; the coordination doc aggregates deviations.

**Merge gate to `#approve-this` required before any agent's work lands.** Existing methodology applies regardless of parallelism.

## 11. Open questions remaining for Phase 6 design

Items not locked in needs assessment, deferred to design doc:

- Snapshot cadence for lattice node aggregates (will be informed by aggregate volume benchmark results)
- Specific Clutch rule pre-writing (will be drafted in Phase 9 design)
- Catalyst arm vocabulary per cycle config (cycle-specific, not block-level)
- Calibration audit specifics for consolidation (will be drafted in Phase 10 design)
- LumaWeave consumption contract details (will be coordinated with LumaWeave when its wiring begins)

These are appropriately deferred — they need design-phase-level detail rather than needs-assessment-level scope.

---

*This needs assessment is the foundation for the Phase 6 block design doc. Implementation proceeds against locked decisions here. Open questions in section 11 get resolved during design, not deferred indefinitely.*

*The cycle runtime event vocabulary specification (`cerebra_phase6_event_vocabulary.md`) is the companion artifact. Together they constitute the input to design.*
