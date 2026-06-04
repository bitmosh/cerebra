# Cerebra — Inspector

## 1. Purpose

The Inspector is Cerebra's observability surface.

Every cycle, every retrieval, every salience computation, every clutch decision, every leeway consultation produces structured events. The Inspector turns those events into something a user can examine.

The Inspector exists because *a system that thinks must be inspectable*. If the user cannot see why the system attended to one memory rather than another, why it chose to refine rather than accept, what hypotheses it was testing — the system's behavior is opaque, and opacity erodes trust.

This document defines the structured event schema, the CLI inspection commands, the rendering boundary between Cerebra and LumaWeave, the eventual frontend roadmap, and the integration with the rest of the runtime.

---

## 2. Core Doctrine

The Inspector should be:

```text
structured-first (events are data, then renderings)
locally-renderable (CLI in v0.1, no external dependency)
queryable
inspector-trace-complete (every cognitive action emits trace)
LumaWeave-handoff-ready (events are the integration shape)
budget-aware (event storage is bounded)
schema-versioned
non-intrusive (event emission cannot block cycle execution)
```

The Inspector is *not* a UI. The CLI rendering is one consumer of the event stream. LumaWeave is another. The eventual frontend is a third. The underlying truth is the structured event log; renderings derive from it.

---

## 3. Rendering Boundary

Cerebra ships the structured event log plus a minimal CLI inspector. LumaWeave handles rich visual rendering and cross-session graph exploration. The eventual standalone frontend (development beginning ~4 days post-v0.1) is the long-term command-center surface.

```text
Cerebra ships:
  Event emission infrastructure
  Structured event log on disk
  Query API over events
  CLI commands rendering text/JSON to terminal

LumaWeave handles:
  Visual graph rendering of events as nodes and edges
  Cross-session exploration
  Time-scrubber views (see Archive Refinery preset)
  Interactive graph navigation

Future Frontend (separate project):
  Command center / dashboard
  Agent selection
  Transformer options
  Weighting controls
  Live cognitive process rendering
```

The architectural rule: **Cerebra is independently inspectable.** A user with only Cerebra installed can debug a cycle, examine a tower, trace a retrieval, audit a leeway decision. Without LumaWeave. Without the frontend. The CLI inspector is the floor that ensures Cerebra never depends on its siblings for usability.

---

## 4. Event Schema

Every inspectable action emits an event with a common envelope.

```json
{
  "event_id": "evt_abc123",
  "event_type": "RetrievalPerformed",
  "schema_version": 1,
  "timestamp": 1717459200,
  "session_id": "sess_xyz",
  "cycle_id": "cyc_42",
  "step_id": "step_5",
  "subject_id": "ret_id_99",
  "actor": "cycle_runtime",
  "summary": "Retrieved 7 candidates via hybrid SKU + vector",
  "data": {
    "...event-specific payload..."
  }
}
```

### Envelope fields

```text
event_id        globally unique
event_type      from controlled vocabulary (see §5)
schema_version  for forward compatibility
timestamp       unix epoch seconds
session_id      cycle session this event belongs to
cycle_id        cycle within the session
step_id         step within the cycle
subject_id      the entity this event is about (memory, packet, decision, etc.)
actor           which subsystem produced the event
summary         short human-readable description
data            event-type-specific payload
```

Events are append-only. Once written, they are not modified. Corrections happen via subsequent events that supersede or annotate prior ones.

---

## 5. Event Type Vocabulary

The vocabulary is structured by subsystem.

### 5.1 Source and Ingestion

```text
SourceRegistered
SourceChanged
SourceParsed
SourceParseFailed
DocumentNormalized
ChunkCreated
MemoryRecordCreated
EmbeddingCreated
IndexUpdated
SKUAssigned
```

### 5.2 Retrieval and Context

```text
QueryReceived
RetrievalPerformed
RetrievalStepCompleted     (one for each of the 6 SKU traversal steps)
RetrievalCandidateScored
RetrievalCandidateExcluded
ContextPacketBuilt
ContextPacketRendered
ContinuationBundleDistilled
ContinuationSpawned
PromptReinjected
```

### 5.3 Working Memory and Attention

```text
WorkingMemoryCreated
AttentionItemProposed
AttentionItemPromoted
AttentionItemEvicted
AttentionItemDeferred
InterruptCandidateCreated
WorkingMemoryRendered
WorkingMemoryCleared
```

### 5.4 Truth Tower

```text
TowerInitialized
TowerItemPromoted
TowerItemEvicted
TowerCrossReferenceAdded
TowerItemStaled
TowerTierRebuilt
TowerCollapsed
TowerRendered
```

### 5.5 Cycle Runtime and Signals

```text
CycleStarted
StepStarted
StepCompleted
StepFailed
SignalEvaluated
EvaluationPacketCreated
ClutchDecisionIssued
CatalystSelectionMade
CycleCompleted
CyclePaused
CycleResumed
```

### 5.6 Predictions

```text
PredictionMade
PredictionResolved
PredictionErrorRecorded
PredictionSevereMiss
CalibrationDeltaApplied
```

### 5.7 Memory Lifecycle and Consolidation

```text
MemoryActivated
MemoryWarmed
MemoryCooled
MemoryArchived
MemoryTombstoned
MemoryRestored
MemoryDeleted
MemoryQuarantined
ConsolidationStarted
ConsolidationCompleted
SummaryCreated
DuplicateLinked
ContradictionDetected
StaleMarked
AblationPerformed
ContributionProfileUpdated
```

### 5.8 Leeway and Constitutional

```text
LeewayGrantApplied
LeewayGrantDenied
LeewayRevocationFired
ConstitutionalBlock
LeewaySetEmpty
LeewayRuleLoaded
LeewayRuleExpired
```

### 5.9 Graph Export

```text
GraphNodeCreated
GraphEdgeCreated
GraphNodeArchived
GraphNodeTombstoned
GraphExported
```

Each event type has a specific data schema. Schemas are versioned. Backward-incompatible changes require schema version bumps.

---

## 6. Event Storage

Events are stored in two places.

### 6.1 SQLite Event Table

```sql
CREATE TABLE inspector_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  timestamp INTEGER NOT NULL,
  session_id TEXT,
  cycle_id TEXT,
  step_id TEXT,
  subject_id TEXT,
  actor TEXT NOT NULL,
  summary TEXT NOT NULL,
  data_json TEXT NOT NULL
);

CREATE INDEX idx_events_session ON inspector_events(session_id);
CREATE INDEX idx_events_cycle ON inspector_events(cycle_id);
CREATE INDEX idx_events_type_time ON inspector_events(event_type, timestamp);
CREATE INDEX idx_events_subject ON inspector_events(subject_id);
```

### 6.2 NDJSON Append-Only Log

Each session also writes a flat NDJSON file at `<vault>/events/<session_id>.ndjson`. One event per line. Append-only. The NDJSON file is the authoritative log; the SQLite table is the queryable index.

```text
Why both:
  SQLite gives fast queries for the CLI inspector
  NDJSON gives durable, grep-able, replayable history
  If the SQLite index is lost, it can be rebuilt from NDJSON
  LumaWeave can consume NDJSON files directly
```

### 6.3 Retention

```text
Default: keep all events for 30 days, then compact
Compaction: detail events older than 30 days are summarized; SKU/cycle-level
            events are preserved indefinitely
Configurable per vault
Tombstones and deletions are preserved indefinitely (audit requirement)
```

---

## 7. CLI Inspector Commands

All commands operate on the local vault.

### 7.1 Session-Level

```bash
cerebra inspect session list                    # list all sessions
cerebra inspect session <session_id>            # session summary
cerebra inspect session <session_id> --events   # full event list
cerebra inspect session <session_id> --json     # JSON output for piping
```

### 7.2 Cycle-Level

```bash
cerebra inspect cycle <cycle_id>                # cycle summary
cerebra inspect cycle <cycle_id> --steps        # step-by-step trace
cerebra inspect cycle <cycle_id> --signals      # signal evaluations
cerebra inspect cycle <cycle_id> --clutch       # clutch decisions
cerebra inspect cycle <cycle_id> --tower        # truth tower snapshot
```

### 7.3 Memory-Level

```bash
cerebra inspect memory <memory_id>              # memory summary with SKU
cerebra inspect memory <memory_id> --history    # all events touching this memory
cerebra inspect memory <memory_id> --attribution  # contribution profile if available
cerebra inspect memory <memory_id> --graph      # graph neighbors
```

### 7.4 Retrieval-Level

```bash
cerebra inspect retrieval <retrieval_id>        # what was queried, what came back
cerebra inspect retrieval <retrieval_id> --path # traversal path through SKU
cerebra inspect retrieval <retrieval_id> --scores  # all score components
```

### 7.5 Leeway-Level

```bash
cerebra inspect leeway active                   # currently active grants
cerebra inspect leeway history <session_id>     # consultation history
cerebra inspect leeway revocations              # revocations triggered recently
cerebra inspect constitutional                  # constitutional rules
```

### 7.6 Query

```bash
cerebra inspect query --event-type RetrievalPerformed --last 1h
cerebra inspect query --signal-low GROUNDEDNESS --threshold 0.4
cerebra inspect query --severe-misses --last 24h
cerebra inspect query --cycle <cycle_id> --filter "clutch_action=escalate"
```

---

## 8. Rendering Formats

CLI commands support three output formats.

### 8.1 Default — Pretty Text

Human-readable with color and structure. The default for terminal use.

```text
$ cerebra inspect cycle cyc_42

Cycle cyc_42                                            [completed: 12m ago]
  Session:        sess_xyz
  Goal:           Plan the Cerebra prototype gate
  Cycle config:   bonsai.ideation.v1
  Started:        2026-06-04 09:14:22
  Duration:       4m 18s
  Status:         accepted

Signal Composite: 0.78 (confidence 0.84, signal_strength 0.92)
  COHERENCE:           0.82
  GROUNDEDNESS:        0.71
  GENERATIVITY:        0.68
  RELEVANCE:           0.91
  PRECISION:           0.76
  EPISTEMIC HUMILITY:  0.79

Steps (7 total):
  step_1  build_context           ContextPacket 8.4k tokens
  step_2  generate                output: 1.2k tokens
  step_3  evaluate_signals        composite 0.62
  step_4  clutch                  REFINE (iterative group)
  step_5  generate                output: 1.5k tokens
  step_6  evaluate_signals        composite 0.78
  step_7  clutch                  ACCEPT (terminal group)

Use --steps for detail, --tower for truth tower snapshot
```

### 8.2 JSON

For piping to other tools or programmatic inspection.

```bash
cerebra inspect cycle cyc_42 --json | jq '.signals'
```

### 8.3 NDJSON Stream

For tailing live events.

```bash
cerebra inspect tail --session sess_xyz
cerebra inspect tail --event-type ClutchDecisionIssued
```

---

## 9. Why-Was-This-Retrieved Query

One of the Inspector's most important capabilities: explaining a single retrieval.

```bash
$ cerebra inspect retrieval ret_id_99 --explain

Retrieval ret_id_99                                     [cyc_42 step_1]
Query:  "Plan the Cerebra prototype gate test scenarios"
Time:   2026-06-04 09:14:25 (3.2s)
Strategy: medium_sibling_wide (selected by catalyst with score 0.78)

Steps performed:
  1. exact_match     -> 2 candidates
  2. partial_match   -> 5 candidates
  3. sibling_traverse -> 12 candidates
  4. vector_fallback -> 15 candidates (capped)

7 candidates selected for ContextPacket:

  [0.91] mem_abc — Cerebra MVP scope spec
         SKU: 0x5A.B1.4F.04.B2.04
         match: exact on D1+D2, sibling from query D3
         attribution: D1=0.42, D2=0.31, D3=0.18 (well-aligned with match)
         lifecycle: active, salience: 0.88

  [0.84] mem_def — Truth tower derivation operations
         SKU: 0x52.B3.4F.0C.B2.04
         match: partial on D1+D2, vector fallback for D3
         attribution: D2=0.55, D1=0.28 (partial alignment)
         lifecycle: active, salience: 0.76

  ...

Excluded candidates (12):
  4 archived
  3 below salience threshold
  2 duplicates linked to selected
  3 lower-scoring on attribution-aligned-match

LeewayGrants consulted: LR-001 (retrieve_from_memory) — applied
No revocations fired.
```

This is the explainability surface that no pure-RAG system can produce. Every retrieved memory has a stated reason; every excluded candidate has a stated reason; the leeway decisions are visible.

---

## 10. Tower Inspection

```bash
$ cerebra inspect cycle cyc_42 --tower

Truth Tower [cyc_42 final state]

T5  Active Goal (1/1)
  goal: Plan the Cerebra prototype gate test scenarios

T4  Working Hypotheses (3/4)
  h_1: SKU-based ingestion will surface classification edge cases first
       supports: ins_3, ins_5
       counter:  obs_7
  h_2: Truth tower derivation will need real cycles to tune
       supports: ins_2, ins_4
  h_3: Clutch action grouping reduces rule interference at MVP scale
       supports: ins_1

T3  Cross-Validated Insights (5/7)
  ins_1: Two-pass clutch reduces overlap (cited by h_3)
  ins_2: T1 evidence churn forces tower rebuild (cited by h_2)
  ...

T2  High-Salience Memories (8/12)
  mem_abc  (cited by ins_1, ins_3)
  mem_def  (cited by ins_2)
  ...

T1  Source-Grounded Evidence (14/20)
  ...

Last rebuild: T3 rebuilt 2m ago after ins_4 went stale
Last eviction: mem_xyz from T2 at 1m ago (lower salience than newcomer)
```

---

## 11. LumaWeave Handoff

LumaWeave consumes the event stream directly. The integration is:

```text
Cerebra writes NDJSON events to <vault>/events/*.ndjson
LumaWeave watches the events directory (live tail)
LumaWeave renders events as graph nodes and edges:
  SourceRegistered    -> Source node
  ChunkCreated         -> Chunk node + DERIVED_FROM edge
  ClutchDecisionIssued -> Decision node + DECIDED_BY edge
  ...
LumaWeave's perspective presets filter events for specific views:
  "Cycle Trace"     shows one cycle's full event sequence
  "Tower Evolution" shows truth tower state over time
  "Retrieval Atlas" shows SKU navigation paths
  "Archive Refinery" (Bons.ai ↔ Cerebra dogfood view)
```

The handoff is one-way: Cerebra produces events, LumaWeave renders them. Cerebra does not consume LumaWeave state. This preserves the standalone property.

---

## 12. Frontend Roadmap (Separate Project)

The eventual frontend is its own project, starting development ~4 days after Cerebra v0.1 ships.

Approach decisions:

```text
Backend: connects to Cerebra's local API + event stream
Frontend: custom roll (per user preference)
   May incorporate winning patterns from open-webui
   Independent codebase, not bundled with Cerebra
Communication: HTTP/WebSocket against Cerebra's local service mode
```

Capabilities targeted for the frontend over time:

```text
v1: Command center dashboard
    Agent selection from registered agents
    Cycle config selection
    Live session view with event tail
    Truth tower visualization
    Retrieval inspector

v2: Configuration surfaces
    Signal weight tuning
    Catalyst strategy selection
    Leeway rule visualization
    Cycle config builder

v3: Live cognitive process rendering
    Tied into LumaWeave's graph view
    Real-time agent thought visualization
    "Dogfood" view of running cycles
```

The frontend is downstream of Cerebra. Cerebra's CLI inspector is the floor.

---

## 13. Integration Points

**All Cerebra subsystems** emit events. Every major action produces an event. There are no silent operations.

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** every step boundary, every clutch decision, every catalyst selection emits an event.

**Truth Tower (`CEREBRA_TRUTH_TOWER.md`):** every tower operation emits an event. The tower is reconstructable from its event history.

**Consolidation Engine (`CEREBRA_CONSOLIDATION_ENGINE.md`):** every consolidation run emits a start, completion, and per-output event.

**Leeway Network (`CEREBRA_LEEWAY_NETWORK.md`):** every consultation, every grant application, every revocation emits an event. Audit trail is complete.

**Signal Epistemology (`CEREBRA_SIGNAL_EPISTEMOLOGY.md`):** every signal evaluation emits an event with full component breakdown.

**Predictions (`CEREBRA_PREDICTION_AND_EVALUATION.md`):** prediction and outcome events emit. Severe misses emit additional flag events.

**Memory Lifecycle (`CEREBRA_MEMORY_LIFECYCLE.md`):** state transitions emit events.

**Catalyst (`CEREBRA_CATALYST.md`):** selections emit with full scoring breakdown.

**Re-injection Loop (`CEREBRA_REINJECTION_LOOP.md`):** continuation bundles emit creation, distillation, spawning events.

**SKU Addressing (`CEREBRA_SKU_ADDRESSING.md`):** SKU assignments and traversal events emit.

---

## 14. MVP Scope

Cerebra v0.1 ships:

```text
Event emission infrastructure (envelope + 30 most-used event types)
SQLite event table + NDJSON append log
Basic CLI commands:
  cerebra inspect session ...
  cerebra inspect cycle ...
  cerebra inspect memory ...
  cerebra inspect retrieval ...
  cerebra inspect query ...
Pretty text rendering (default)
JSON rendering (--json flag)
Tail mode for live event streams
Event retention default (30 days)
```

Cerebra v0.2 adds:

```text
Remaining event types (full vocabulary from §5)
NDJSON tail mode for LumaWeave consumption
Compaction for events older than retention
Event replay capability (rebuild SQLite from NDJSON)
--explain flag on retrieval (full retrieval explanation)
Tower inspection commands
Leeway inspection commands
```

Cerebra v0.3+:

```text
Local web inspector (HTML rendering, localhost only)
Frontend integration API
Cross-session correlation queries
Statistical summary commands
```

---

## 15. Testing Requirements

Inspector tests should cover:

```text
event emission for every major action type
event ordering preserved within a session
NDJSON file is valid JSON-per-line
SQLite index rebuilds correctly from NDJSON
session inspect command returns expected summary
cycle inspect command shows step sequence
retrieval inspect command includes traversal path
memory inspect command includes attribution if available
tower inspect command renders all tiers
leeway inspect command shows active grants
query command filters by event type
query command filters by signal threshold
tail mode streams events as they emit
JSON output is valid and parseable
retention policy compacts old events correctly
tombstones preserved through compaction
```

---

## 16. Failure Modes To Watch

**Event emission blocking cycle execution.** If the event log is slow to write, it could backpressure the cycle. Mitigation: event writes are async with bounded queue. If the queue overflows, events are dropped with a single overflow marker (better to lose some events than to block cycles).

**Storage growth.** High-frequency cycles can produce many events. Mitigation: compaction at 30 days; configurable retention; per-event-type retention policies (lifecycle events kept forever, retrieval events kept 7 days, etc.).

**Schema drift.** Event schemas evolve over time. Mitigation: schema_version on every event; consumers (CLI inspector, LumaWeave) handle multiple versions; old events readable forever.

**Sensitive data in events.** Events might contain user content that should be filtered. Mitigation: events store IDs and summaries by default, not full content. Full content retrievable through subject_id lookup, which can apply sensitivity filtering.

**LumaWeave consuming partial events.** If LumaWeave reads an NDJSON file that's actively being appended, it could see partial lines. Mitigation: NDJSON writes are line-atomic; LumaWeave's tail-reader skips partial final lines.

---

## 17. Inspector Doctrine

A memory system that thinks must be inspectable. Without inspection, the system's behavior is opaque, and opacity erodes trust faster than any clever architectural property can build it.

The Inspector is the architectural commitment that **no cognitive action happens silently**. Every retrieval has a stated reason. Every clutch decision has a stated rationale. Every leeway grant has a stated condition. Every truth tower promotion has a stated derivation. The user can ask "why?" of any action and receive a structured, traceable answer.

This is the property that distinguishes Cerebra from systems that produce outputs and hide their work. It is also the property that makes the system genuinely debuggable — a system whose internal state is fully observable is a system that can be improved with discipline rather than guesswork.

The CLI is the floor. LumaWeave is the rich visual ceiling. The eventual frontend is the polished command center. All three render the same underlying truth: the event log.

Inspectability is not a feature added on top. It is the architectural commitment that the system's reasoning is reviewable. Build it from the foundation.
