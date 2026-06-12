# Cerebra Phase 6 Block — Design Doc

*Implementation contract for the Phase 6 block (cycle runtime), spanning roadmap phases 6 through 11. Produced 2026-06-12 following the needs assessment, the cycle runtime event vocabulary spec, the fossic aggregate volume benchmark resolution, and three rounds of cross-Claude coordination with Lattica Claude. This is the document bandit reads to begin Phase 6 Step 1.*

*Companion documents (must be read alongside):*
- `v01_phase6_needs.md` — locked decisions, scope, success criteria
- `cerebra_phase6_event_vocabulary.md` — event schemas, determinism, causation chains, indexed_tags
- `event_sourced_cognitive_substrate.md` — architectural foundation
- `CEREBRA_SIGNAL_EPISTEMOLOGY.md` — six-signal foundation
- `CEREBRA_PREDICTION_AND_EVALUATION.md` — prediction/outcome record schemas

---

## 0. Reader orientation

This document is the design contract for the Phase 6 block. It specifies what bandit implements, in what order, against which interfaces. It does not re-derive architectural decisions — those are in the needs assessment and concept docs. Bandit reads those first, then this, then begins implementation.

The block ships six sub-phases (Phase 6 through Phase 11) at versions v0.3.0 through v0.3.5. The cumulative deliverable is the v0.1 Cerebra MVP: a cognitive runtime that runs cycles, evaluates outputs, makes governed decisions, learns from outcomes, and consolidates sessions.

The implementing-agent assumptions are unchanged from prior phases: bandit operates per established methodology (START → work → END → MERGE GATE → commit → bump → PUSH GATE), maintains mandatory deviation logs at `docs/agent/deviations/<version>.md`, and operates against the existing Cerebra repo structure.

## 1. Block-level architectural commitments

These commitments hold across every sub-phase. They are NOT decisions to revisit during implementation. Violations require an explicit deviation log entry and a STOP gate.

### 1.1 Event-sourced cognitive substrate with three-way write model

Cerebra's event substrate has three write paths:

**Path A — `inspector_events` via SQLiteEventLog (unchanged from Phases 1-5).** All pre-Phase-6 cognitive events continue writing here. Phase 6 implementation does NOT modify this path. The existing `cerebra/inspector/sqlite_log.py` is the production-tested write path; Phase 6 code does not touch it except to *add* new event types where they fit existing semantics.

**Path B — `cerebra/agent-trace/<cycle_id>` via fossic's direct append.** All cycle runtime events emit through this path. New code only — no migration of existing events. Stream naming: `cycle_id` is a single-segment slug (UUID or short identifier), no embedded slashes, under 256 chars. The `<cycle_id>` segment matches fossic's `*/agent-trace/*` glob convention.

**Path C — `cerebra/lattice/<lineage_id>` via fossic's direct append with reducer registration.** Lattice node aggregate events emit here. Each lineage has a stream. A single `LatticeNodeReducer` registers against `cerebra/lattice/*` via pattern-based registration. Reducers fold events into continuous aggregate state.

Paths B and C use fossic v1.0-rc.1's PyO3 binding (`fossic-py`). Path A continues using Cerebra's existing SQLite-backed event log.

### 1.2 Reducer purity and snapshot discipline

All reducers registered with fossic are pure synchronous functions: `apply(state, event) -> new_state`. No I/O, no side effects, no async. The contract is enforced at fossic's type layer.

Every reducer sets `state_schema_version` explicitly from first implementation, even when value is `1`. This is required to prevent messy snapshot invalidation when state shape later evolves. Default values are forbidden.

Lattice node streams snapshot every 100 events using cycle-completion-tied triggers (detailed in §4 below). Snapshot writes are Cerebra-side responsibility via `store.take_snapshot(stream_id, branch)` calls; fossic provides the mechanism, Cerebra owns the policy.

### 1.3 Causation chain discipline

Events maintain explicit causation chains per the vocabulary spec (`cerebra_phase6_event_vocabulary.md` section "Causation chains summary"). Every event's `causation_id` references the specific upstream event that enabled it, not just "the previous event."

For safety-gated actions specifically: `LeewayGrantApplied` must be appended BEFORE the gated action event, with the action event's `causation_id` referencing the `LeewayGrantApplied`'s ID. Single-threaded sequential emission preserves this invariant. Defensive cross-reference (action event payload includes `leeway_grant_event_id: EventId`) is recommended for Phase 7 but not required.

### 1.4 Synchronous internal, async at consumption boundary

Cycle runtime is internally synchronous — within a single cycle, all operations happen sequentially. Async appears only at the consumption boundary (witness layer subscriptions, Lattica observability views) which is post-v0.1 in implementation scope.

This means Phase 6 implementation does not introduce async/await patterns inside cycle execution. CLI commands block until cycle completion. Daemon mode (`cerebra serve`) is deferred to post-block work.

## 2. Block scope and version map

Six sub-phases, version bumps per sub-phase, totaling v0.3.0 through v0.3.5:

| Phase | Name | Scope | Version | Deliverable |
|-------|------|-------|---------|-------------|
| 6 | Signal pipeline + prediction records | Six-signal evaluator, EvaluationPacket, PredictionRecord/OutcomeRecord schemas | v0.3.0 | Standalone evaluation infrastructure with tests |
| 7 | Leeway pre-action gate | Wire existing leeway substrate, composition-by-union, LeewayGrantApplied events | v0.3.1 | Pre-action gate callable, no cycle yet |
| 8 | Cycle runtime skeletal | End-to-end cycle execution with real Ollama, ContinuationBundle, re-injection trigger | v0.3.2 | `cerebra run-cycle` works end-to-end |
| 9 | Clutch + Catalyst | Wire Clutch decisions, naive count-based Catalyst arm learning | v0.3.3 | Cycle decisions wired, accept/refine/branch/stop functional |
| 10 | Consolidation | Session summary + calibration audit, retrievable summary records | v0.3.4 | `cerebra consolidate` produces stable summary |
| 11 | Graph export | JSON serialization of Cerebra state (full structure minus temporal) | v0.3.5 | `cerebra export graph` produces LumaWeave-consumable JSON |

v0.3.5 is the v0.1 MVP milestone. Block close is MVP delivery.

## 3. Cross-cutting infrastructure (Phase 6 Step 0)

Before Phase 6 proper begins, three pieces of infrastructure must land. These are not their own sub-phase — they're foundational work for everything that follows.

### 3.1 `cerebra/storage/fossic_store.py`

Thin wrapper around `fossic-py` providing Cerebra-friendly access to fossic's Store. Surface:

```python
class FossicStore:
    def __init__(self, vault_path: Path):
        """Opens fossic store at <vault_path>/.fossic/store.db, creates if missing."""
        ...

    def append(
        self,
        stream_id: str,
        event_type: str,
        payload: dict,
        causation_id: Optional[bytes] = None,
        external_id: Optional[str] = None,
        indexed_tags: Optional[dict] = None,
    ) -> EventId:
        """Append event to stream, return content-addressed event ID."""
        ...

    def take_snapshot(self, stream_id: str, branch: str = "main") -> SnapshotInfo:
        """Take a snapshot of the current aggregate state for stream."""
        ...

    def read_state(self, stream_id: str, branch: str = "main") -> dict:
        """Read current aggregate state via registered reducer."""
        ...

    def register_reducer(self, stream_pattern: str, reducer: object) -> None:
        """Register a DynReducer against a glob stream pattern."""
        ...

    def current_version(self, stream_id: str, branch: str = "main") -> int:
        """Return current version (event count) for stream."""
        ...
```

The store is opened once at vault initialization and lives for the session's duration. Multiple `cerebra` CLI invocations create separate fossic-py Store instances — fossic handles WAL-based cross-process safety.

### 3.2 `cerebra/cognition/event_emitter.py`

Wrapper around `FossicStore.append()` that handles snapshot triggering for lattice streams and causation chain construction for safety-gated actions:

```python
class EventEmitter:
    def __init__(self, store: FossicStore, session_id: str, cycle_id: str):
        self.store = store
        self.session_id = session_id
        self.cycle_id = cycle_id
        self._last_event_id: Optional[bytes] = None

    def emit_cycle_event(
        self,
        event_type: str,
        payload: dict,
        causation_id: Optional[bytes] = None,
        indexed_tags: Optional[dict] = None,
    ) -> bytes:
        """Emit an event on the cerebra/agent-trace/<cycle_id> stream."""
        stream_id = f"cerebra/agent-trace/{self.cycle_id}"
        eid = self.store.append(
            stream_id=stream_id,
            event_type=event_type,
            payload=payload,
            causation_id=causation_id or self._last_event_id,
            indexed_tags=indexed_tags,
        )
        self._last_event_id = eid
        # CycleCompleted is the snapshot anchor for lattice streams (see emit_lattice_event)
        return eid

    def emit_lattice_event(
        self,
        lineage_id: str,
        event_type: str,
        payload: dict,
        causation_id: Optional[bytes] = None,
        indexed_tags: Optional[dict] = None,
    ) -> bytes:
        """Emit an event on the cerebra/lattice/<lineage_id> stream."""
        stream_id = f"cerebra/lattice/{lineage_id}"
        eid = self.store.append(
            stream_id=stream_id,
            event_type=event_type,
            payload=payload,
            causation_id=causation_id,
            indexed_tags=indexed_tags,
        )
        return eid

    def trigger_lattice_snapshots_at_cycle_boundary(self, touched_lineages: set[str]) -> None:
        """At CycleCompleted, snapshot any lattice stream that has accumulated >=100 events since last snapshot."""
        for lineage_id in touched_lineages:
            stream_id = f"cerebra/lattice/{lineage_id}"
            current = self.store.current_version(stream_id)
            last_snapshot = self.store.last_snapshot_version(stream_id)  # 0 if no snapshot
            if current - last_snapshot >= 100:
                self.store.take_snapshot(stream_id)
```

Snapshot triggering at cycle boundaries: the cycle runtime tracks which lattice lineages were touched (via emit_lattice_event calls) during a cycle. On CycleCompleted emission, `trigger_lattice_snapshots_at_cycle_boundary` examines each touched lineage and takes a snapshot if the lineage has accumulated ≥100 events since its last snapshot. This anchors snapshots to cognitively meaningful points rather than mod-arithmetic thresholds.

### 3.3 `cerebra/cognition/_constants.py` additions

Add Phase 6 block constants alongside existing Phase 5 constants:

```python
# Phase 6 — Signal pipeline
SIGNAL_NAMES = frozenset({
    "COHERENCE", "GROUNDEDNESS", "GENERATIVITY",
    "RELEVANCE", "PRECISION", "EPISTEMIC_HUMILITY"
})
SIGNAL_DEFAULT_WEIGHTS = {
    "COHERENCE": 0.18,
    "GROUNDEDNESS": 0.18,
    "GENERATIVITY": 0.12,
    "RELEVANCE": 0.22,
    "PRECISION": 0.12,
    "EPISTEMIC_HUMILITY": 0.18,
}
COMPOSITE_SCORE_FLOOR = 0.30  # below this, evaluation triggers refine action
PREDICTION_ERROR_CLASSIFIERS = {
    "noise": 0.10,
    "notable": 0.40,
    "severe": float("inf"),
}

# Phase 8 — Cycle runtime
CYCLE_MAX_STEPS = 20  # configurable per cycle config; this is the hard cap
RECURSION_DEPTH_DEFAULT = 5  # max continuation chains per session

# Phase 9 — Clutch + Catalyst
CLUTCH_ACTIONS = frozenset({
    "accept", "refine", "critique", "explore", "branch",
    "retrieve_more", "consolidate", "ask_user", "pause", "stop"
})

# Phase 6+ event types (defined in cerebra/inspector/event.py)
PHASE_6_EVENT_TYPES = frozenset({
    "SessionOpened", "CycleStarted", "CycleCompleted",
    "StepStarted", "ContextPacketBuilt", "StepExecuted",
    "PredictionMade", "SignalEvaluated", "EvaluationComposed",
    "OutcomeRecorded", "PredictionSevereMiss",
    "ClutchDecisionMade", "CatalystInvoked", "CatalystArmSelected",
    "LeewayGrantApplied",
    "ContinuationBundleCreated", "ReinjectionTriggered",
    "MemoryWriteFromCycle", "SessionFlushed",
    "ConsolidationStarted", "ConsolidationCompleted",
    "GraphExported",
})

LATTICE_SNAPSHOT_CADENCE = 100  # events between snapshots for lattice node streams
```

These constants are referenced throughout Phase 6 implementation. Changes require explicit migration consideration.

## 4. Phase 6 — Signal pipeline + prediction records (v0.3.0)

### 4.1 Scope

Phase 6 ships the evaluation infrastructure as a standalone subsystem. No cycle runs yet. The deliverable is:

1. Six-signal evaluator callable from Python
2. EvaluationPacket schema with composition logic
3. PredictionRecord and OutcomeRecord schemas
4. Migration adding required tables to the SQLite schema
5. Unit tests covering signal scoring, composition, prediction/outcome lifecycle

### 4.2 New code surfaces

**`cerebra/cognition/signals.py`** — The signal evaluator. Each signal has a checklist prompt template (versioned), an LLM-call invocation, and score extraction logic.

```python
class SignalEvaluator:
    def __init__(self, llm_adapter: LLMAdapter):
        self.llm_adapter = llm_adapter

    def evaluate(
        self,
        signal_name: str,
        output_text: str,
        context: dict,
    ) -> SignalScore:
        """Score one signal on the given output. Single-prompt evaluation."""
        prompt_template = self._load_template(signal_name)
        prompt = prompt_template.render(output=output_text, context=context)
        response = self.llm_adapter.complete(prompt)
        score, details = self._extract_score(response, signal_name)
        return SignalScore(
            signal_name=signal_name,
            score=score,
            evaluator_prompt_version=prompt_template.version,
            signal_strength=1.0,  # v0.1 default; v0.2 introduces strength scoring
            checklist_details=details,
        )
```

**`cerebra/cognition/evaluation.py`** — Evaluation composition logic:

```python
class EvaluationComposer:
    def __init__(self, weights: dict[str, float] = None):
        self.weights = weights or SIGNAL_DEFAULT_WEIGHTS
        self._validate_weights()

    def compose(self, signal_scores: list[SignalScore]) -> EvaluationPacket:
        composite = sum(
            score.score * self.weights[score.signal_name]
            for score in signal_scores
        )
        return EvaluationPacket(
            evaluation_id=generate_id(),
            composite_score=composite,
            per_signal_scores={s.signal_name: s.score for s in signal_scores},
            weights_used=dict(self.weights),
            composite_floor_violated=composite < COMPOSITE_SCORE_FLOOR,
            confidence=self._composite_confidence(signal_scores),
        )
```

**`cerebra/cognition/predictions.py`** — Prediction and outcome records:

```python
@dataclass
class PredictionRecord:
    prediction_id: str
    session_id: str
    cycle_id: str
    step_id: str
    expected_composite_score: float
    expected_per_signal: dict[str, float]
    prediction_basis: str  # prior_step_trajectory | cycle_config_default | static_baseline
    confidence: float
    made_at: int

class PredictionPipeline:
    def predict(
        self,
        session_state: SessionState,
        cycle_config: CycleConfig,
        step_context: StepContext,
    ) -> PredictionRecord:
        """Compute expected scores from prior trajectory + cycle config defaults."""
        ...

    def resolve(
        self,
        prediction: PredictionRecord,
        evaluation: EvaluationPacket,
    ) -> OutcomeRecord:
        """Compare actual to expected, classify error."""
        error = evaluation.composite_score - prediction.expected_composite_score
        classification = self._classify_error(error)
        return OutcomeRecord(
            outcome_id=generate_id(),
            prediction_id=prediction.prediction_id,
            actual_composite_score=evaluation.composite_score,
            prediction_error=error,
            error_classification=classification,
            per_signal_error=self._per_signal_error(prediction, evaluation),
        )
```

### 4.3 Schema migration

**Migration012** adds three tables:

```sql
CREATE TABLE evaluations (
    evaluation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    composite_score REAL NOT NULL,
    per_signal_scores TEXT NOT NULL,  -- JSON
    weights_used TEXT NOT NULL,        -- JSON
    composite_floor_violated INTEGER NOT NULL,
    confidence REAL,
    composed_at INTEGER NOT NULL
);
CREATE INDEX idx_evaluations_session ON evaluations(session_id);
CREATE INDEX idx_evaluations_cycle ON evaluations(cycle_id);

CREATE TABLE predictions (
    prediction_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    expected_composite_score REAL NOT NULL,
    expected_per_signal TEXT NOT NULL,  -- JSON
    prediction_basis TEXT NOT NULL,
    confidence REAL,
    made_at INTEGER NOT NULL
);
CREATE INDEX idx_predictions_session ON predictions(session_id);

CREATE TABLE outcomes (
    outcome_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    actual_composite_score REAL NOT NULL,
    prediction_error REAL NOT NULL,
    error_classification TEXT NOT NULL,
    per_signal_error TEXT,  -- JSON
    recorded_at INTEGER NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);
CREATE INDEX idx_outcomes_session ON outcomes(session_id);
CREATE INDEX idx_outcomes_classification ON outcomes(error_classification);
```

### 4.4 Tests

Test surfaces required for v0.3.0 close:

- Signal evaluator produces scores in [0.0, 1.0] for each of six signals
- Per-signal checklist prompts load correctly with versioning
- EPISTEMIC HUMILITY marker-based scoring (presence of "I think", "probably", "uncertain", etc. boosts; absence in confident claims penalizes)
- Composition formula validates weights sum to 1.0 ± 0.05
- Per-cycle weight overrides work
- Composite floor detection fires correctly
- PredictionRecord/OutcomeRecord round-trip correctly through SQLite
- Error classification handles all three thresholds (noise/notable/severe)
- Migration012 applies cleanly to existing v0.2.7 vaults

### 4.5 Phase 6 success criterion

Six signals callable from Python with single-prompt evaluation, EvaluationPacket and PredictionRecord/OutcomeRecord schemas working in isolation. No cycle runs yet — evaluation infrastructure standing alone with passing tests.

Demonstration:
```python
evaluator = SignalEvaluator(llm_adapter=ollama_adapter)
scores = [evaluator.evaluate(name, "test output", {}) for name in SIGNAL_NAMES]
composer = EvaluationComposer()
packet = composer.compose(scores)
assert 0.0 <= packet.composite_score <= 1.0
assert len(packet.per_signal_scores) == 6
```

## 5. Phase 7 — Leeway pre-action gate (v0.3.1)

### 5.1 Scope

Phase 7 wires the existing leeway substrate (`cerebra/governance/`) into the action proposal path. The substrate already loads rules from constitutional configs; what's missing is the runtime pre-action evaluation. Phase 7 delivers:

1. `LeewayPreActionGate` callable that evaluates proposed actions against loaded leeway rules
2. Composition-by-union semantics (multiple rules combine permissively, not restrictively)
3. `LeewayGrantApplied` event emission via the EventEmitter wrapper
4. Causation chain discipline enforced (LeewayGrantApplied before action event)
5. Unit tests covering rule composition, grant application, forbidden actions, review-required paths

No cycle runs yet — the gate is callable but Phase 8 introduces the cycle that calls it.

### 5.2 New code surfaces

**`cerebra/governance/pre_action_gate.py`** — The gate itself:

```python
class LeewayPreActionGate:
    def __init__(self, rules: list[LeewayRule], constitutional_rules: list[ConstitutionalRule]):
        self.rules = rules
        self.constitutional_rules = constitutional_rules

    def evaluate(self, proposed_action: ProposedAction) -> GateDecision:
        """
        Evaluate a proposed action against all loaded rules.

        Composition-by-union: an action is permitted if ANY leeway rule grants it,
        unless a constitutional rule forbids it. Constitutional forbids ALWAYS WIN.
        """
        # First check constitutional forbids (highest priority)
        for c_rule in self.constitutional_rules:
            if c_rule.forbids(proposed_action):
                return GateDecision(
                    final_decision="forbidden",
                    forbidden_by=c_rule.name,
                    grants_applied=[],
                )

        # Then collect grants from leeway rules
        grants = [r.name for r in self.rules if r.grants(proposed_action)]
        if not grants:
            return GateDecision(
                final_decision="forbidden",
                forbidden_by="no_grants",
                grants_applied=[],
            )

        # Check for review-required rules
        review_required = [r.name for r in self.rules if r.requires_review(proposed_action)]
        if review_required:
            return GateDecision(
                final_decision="requires_review",
                grants_applied=grants,
                review_required_by=review_required,
            )

        return GateDecision(
            final_decision="permitted",
            grants_applied=grants,
        )
```

### 5.3 Event emission discipline

When the cycle runtime (Phase 8+) proposes an action, the sequence is:

```python
# In the cycle's action proposal path
proposed = clutch_decision.to_proposed_action()
gate_decision = leeway_gate.evaluate(proposed)

# CRITICAL: LeewayGrantApplied is emitted BEFORE the action event
leeway_event_id = emitter.emit_cycle_event(
    event_type="LeewayGrantApplied",
    payload={
        "proposed_action": proposed.action_name,
        "grants_applied": gate_decision.grants_applied,
        "final_decision": gate_decision.final_decision,
        "forbidden_by": gate_decision.forbidden_by,
    },
    causation_id=clutch_decision_event_id,
)

if gate_decision.final_decision == "permitted":
    # The action event references the LeewayGrantApplied as causation
    action_event_id = emitter.emit_cycle_event(
        event_type="StepStarted",  # or whichever gated action
        payload={...},
        causation_id=leeway_event_id,  # explicit reference
    )
```

This is the discipline. Bandit implements the cycle runtime such that every safety-gated action follows this exact pattern. The single-threaded synchronous nature of the cycle preserves the ordering invariant.

### 5.4 Defensive cross-reference (recommended)

Per the Phase 7 design consideration banked from earlier coordination, action event payloads include `leeway_grant_event_id: EventId` as a defensive cross-reference:

```python
action_payload = {
    "step_id": step_id,
    "step_type": step_type,
    "leeway_grant_event_id": leeway_event_id,  # defensive
    # ... other fields
}
```

This makes the safety invariant structurally auditable. A query against the action event can verify that the cited LeewayGrantApplied exists, was emitted on the same stream, and has a lower version. Defense in depth.

### 5.5 Tests

- Composition-by-union: multiple grants combine permissively
- Constitutional forbids always override leeway grants
- Empty grant set produces `forbidden` decision
- Review-required actions produce `requires_review` decision
- LeewayGrantApplied event emits before action event in test sequences
- Defensive cross-reference field populates correctly
- Causation chain from clutch decision → leeway grant → action event verifies correctly

### 5.6 Phase 7 success criterion

`LeewayPreActionGate.evaluate()` returns correct decisions for permitted/forbidden/requires_review cases. `LeewayGrantApplied` event emission integrates cleanly with the EventEmitter. Causation chain discipline preserved in all test scenarios.

## 6. Phase 8 — Cycle runtime skeletal (v0.3.2)

### 6.1 Scope

Phase 8 is the structural center of the block. Everything before it built infrastructure; everything after it builds on cycles. The deliverable:

1. `cerebra run-cycle <config> --goal "<text>"` command works end-to-end with real Ollama
2. RuntimeSession state type with persistence
3. Cycle execution loop (init → context → predict → step → evaluate → outcome → memory write → loop-or-stop)
4. ContinuationBundle schema (re-injection trigger mechanics ship; full re-injection logic in Phase 9)
5. Tests covering cycle execution, session persistence, basic re-injection threshold detection

This is the phase where Cerebra crosses from "infrastructure" to "cognitive runtime." Prototype gate decision happens at this kickoff per the bandit-mediated gate.

### 6.2 Prototype gate

At Phase 8 kickoff, bandit reads the entire Phase 6 block design doc + needs assessment + vocabulary spec. Bandit then makes one of two calls:

**Option A — Proceed directly to Phase 8 Step 1.** Bandit confirms the design is concrete enough that direct implementation is the proof. No thin prototype needed.

**Option B — Thin prototype as Phase 8 Step 0.** Bandit identifies integration risks that warrant a minimal end-to-end proof before full implementation. The prototype is bounded:
- Three docs ingested
- One cycle config loaded
- One ContextPacket built
- One mock step run
- One signal evaluated (probably COHERENCE for simplicity)
- One accept-only Clutch decision (no decision tree yet)
- Graph events emitted
- Graph export tested

Option B takes ~2-4 hours and ships at v0.3.1a (sub-version letter for unforeseen squeeze-in per Cerebra's versioning convention). Then Phase 8 proper proceeds.

Bandit's decision is documented in the deviation log for Phase 8 Step 1. No restriction on which option — both are valid.

### 6.3 New code surfaces

**`cerebra/cognition/session.py`** — RuntimeSession state type:

```python
@dataclass
class RuntimeSession:
    session_id: str
    cycle_config: str
    goal: str
    vault_path: Path
    opened_at: int
    parent_session_id: Optional[str] = None
    recursion_depth: int = 0
    max_recursion_depth: int = RECURSION_DEPTH_DEFAULT
    cycles_run: int = 0
    steps_run: int = 0
    state: str = "active"  # active | flushed | continued

class SessionManager:
    def open_session(
        self,
        goal: str,
        cycle_config: str,
        vault_path: Path,
        parent_session_id: Optional[str] = None,
    ) -> RuntimeSession:
        """Create a new session, persist to sessions table, emit SessionOpened."""
        ...

    def flush_session(self, session_id: str, outcome: str) -> None:
        """Close session, emit SessionFlushed."""
        ...
```

**`cerebra/cognition/cycle_config.py`** — Cycle configuration schema:

```python
@dataclass
class CycleConfig:
    name: str  # e.g., "simple.planning.v0"
    version: int
    description: str
    steps: list[CycleStep]
    signal_weights_override: Optional[dict[str, float]] = None
    clutch_rules: list[ClutchRule]
    catalyst_vocabulary: list[CatalystArm]
    max_steps: int = CYCLE_MAX_STEPS
    stop_conditions: list[StopCondition]

class CycleConfigLoader:
    def load(self, name: str) -> CycleConfig:
        """Load cycle config from cycles/ directory."""
        ...
```

**`cerebra/cognition/cycle_runtime.py`** — The actual cycle loop:

```python
class CycleRuntime:
    def __init__(
        self,
        store: FossicStore,
        session: RuntimeSession,
        config: CycleConfig,
        signal_evaluator: SignalEvaluator,
        composer: EvaluationComposer,
        prediction_pipeline: PredictionPipeline,
        leeway_gate: LeewayPreActionGate,
        # Phase 9 additions: clutch, catalyst
        # Phase 10 additions: consolidation_engine
    ):
        ...

    def run(self) -> SessionFinalState:
        """Execute the cycle loop until stop or re-injection."""
        cycle_id = generate_id()
        emitter = EventEmitter(self.store, self.session.session_id, cycle_id)
        emitter.emit_cycle_event("CycleStarted", {...})

        try:
            while not self._should_stop():
                step_result = self._run_step(emitter)
                if self._should_reinject():
                    bundle = self._distill_continuation_bundle()
                    emitter.emit_cycle_event("ContinuationBundleCreated", {...})
                    emitter.emit_cycle_event("ReinjectionTriggered", {...})
                    self._spawn_continuation(bundle)
                    return SessionFinalState.continued
        finally:
            emitter.emit_cycle_event("CycleCompleted", {...})
            emitter.trigger_lattice_snapshots_at_cycle_boundary(
                touched_lineages=self._touched_lineages
            )

        return SessionFinalState.accepted_or_stopped
```

**`cerebra/cognition/continuation_bundle.py`** — ContinuationBundle schema:

```python
@dataclass
class ContinuationBundle:
    bundle_id: str
    session_id: str
    cycle_id: str
    distilled_goal: str
    summarized_prior_prompt: str
    truth_tower_projection: dict
    cognitive_insights: list[str]
    next_focus: str
    open_questions: list[str]
    constraints: list[str]
    recursion_depth: int
    voice_mode: str = "system"  # v0.1: system only; v0.2 adds self
    bundle_size_bytes: int = 0
    created_at: int = 0

    def to_priming_text(self) -> str:
        """Render the bundle as priming text for the continuation session."""
        ...
```

Phase 8 ships ContinuationBundle as schema + creation trigger. The actual continuation spawn (Phase 9) consumes the bundle.

### 6.4 Schema migration

**Migration013** adds sessions, continuation_bundles tables:

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    cycle_config TEXT NOT NULL,
    goal TEXT NOT NULL,
    vault_path TEXT NOT NULL,
    opened_at INTEGER NOT NULL,
    parent_session_id TEXT,
    recursion_depth INTEGER NOT NULL DEFAULT 0,
    max_recursion_depth INTEGER NOT NULL DEFAULT 5,
    cycles_run INTEGER NOT NULL DEFAULT 0,
    steps_run INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id)
);
CREATE INDEX idx_sessions_parent ON sessions(parent_session_id);

CREATE TABLE continuation_bundles (
    bundle_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    distilled_goal TEXT NOT NULL,
    summarized_prior_prompt TEXT NOT NULL,
    truth_tower_projection TEXT NOT NULL,  -- JSON
    cognitive_insights TEXT NOT NULL,      -- JSON array
    next_focus TEXT NOT NULL,
    open_questions TEXT NOT NULL,           -- JSON array
    constraints TEXT NOT NULL,              -- JSON array
    recursion_depth INTEGER NOT NULL,
    voice_mode TEXT NOT NULL DEFAULT 'system',
    bundle_size_bytes INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
CREATE INDEX idx_bundles_session ON continuation_bundles(session_id);
```

### 6.5 CLI surface

```bash
cerebra run-cycle <cycle_config> --goal "<goal text>" [--vault <path>] [--continue <session_id>]
```

Behavior:
- `--continue <session_id>` resumes a session via continuation bundle
- Default vault from CEREBRA_VAULT env var or config
- Streams cycle progress to stdout (event types and step indices)
- Returns 0 on `accept` outcome, 1 on `stop`, 2 on `cap_reached`

### 6.6 Phase 8 success criterion

`cerebra run-cycle simple.planning.v0 --goal "Draft a prototype plan"` produces a session that runs at least one cycle through at least one step with real Ollama, emits all expected events, and either stops or marks for continuation. ContinuationBundle schema validates correctly even if not yet consumed.

This is the moment Cerebra becomes a cognitive runtime.

## 7. Phase 9 — Clutch + Catalyst (v0.3.3)

### 7.1 Scope

Phase 9 wires control. Phase 8 ran cycles but Clutch decisions were stub-accepted. Phase 9 ships:

1. Clutch decision wired to cycle, with rule cascade producing typed actions
2. Catalyst arm selection (naive count-based learning)
3. All action types functional: accept/refine/critique/explore/branch/retrieve_more/consolidate/ask_user/pause/stop
4. ContinuationBundle consumption (the continuation actually spawns when Clutch decides to)
5. Re-injection threshold detection (context budget exceeded triggers ContinuationBundle creation)

### 7.2 New code surfaces

**`cerebra/cognition/clutch_rules.py`** — Cycle-aware Clutch rules:

```python
@dataclass
class ClutchRule:
    name: str
    condition: Callable[[ClutchContext], bool]
    action: str  # one of CLUTCH_ACTIONS
    escalate_to_catalyst: bool = False

class ClutchEngine:
    def __init__(self, rules: list[ClutchRule]):
        self.rules = rules

    def decide(self, context: ClutchContext) -> ClutchDecision:
        """Evaluate rules in order, return first matching decision."""
        for rule in self.rules:
            if rule.condition(context):
                return ClutchDecision(
                    action=rule.action,
                    rule_matched=rule.name,
                    escalate_to_catalyst=rule.escalate_to_catalyst,
                )
        # Default to accept if no rule matches
        return ClutchDecision(action="accept", rule_matched="default")
```

**`cerebra/cognition/catalyst.py`** — Naive count-based arm learning:

```python
@dataclass
class CatalystArmStats:
    arm_name: str
    total_invocations: int = 0
    total_reward: float = 0.0
    last_invoked_at: int = 0

    @property
    def average_reward(self) -> float:
        return self.total_reward / self.total_invocations if self.total_invocations else 0.5

class CatalystEngine:
    def __init__(self, vocabulary: list[CatalystArm], stats: dict[str, CatalystArmStats]):
        self.vocabulary = vocabulary
        self.stats = stats

    def select_arm(self, context: CatalystContext) -> CatalystArm:
        """Weighted random selection based on arm average rewards."""
        weights = [self.stats[arm.name].average_reward for arm in self.vocabulary]
        return random.choices(self.vocabulary, weights=weights)[0]

    def update_arm_stats(self, arm_name: str, reward: float) -> None:
        """Naive count-based update."""
        stats = self.stats[arm_name]
        stats.total_invocations += 1
        stats.total_reward += reward
        stats.last_invoked_at = now_ms()
```

### 7.3 Re-injection trigger logic

When the cycle runtime detects context budget exhaustion (or Clutch decision is `continue`):

```python
def _should_reinject(self) -> bool:
    """Determines if context budget is exhausted or Clutch requested continuation."""
    if self._context_budget_exceeded():
        return True
    if self._clutch_decision_was_continue():
        return True
    return False

def _distill_continuation_bundle(self) -> ContinuationBundle:
    """Distill current cycle state into a bundle for fresh-prompt priming."""
    tower_projection = self._render_truth_tower_for_bundle()
    return ContinuationBundle(
        bundle_id=generate_id(),
        session_id=self.session.session_id,
        cycle_id=self.cycle_id,
        distilled_goal=self.session.goal,
        summarized_prior_prompt=self._summarize_prompt(),
        truth_tower_projection=tower_projection,
        cognitive_insights=self._extract_insights(),
        next_focus=self._derive_next_focus(),
        open_questions=self._extract_open_questions(),
        constraints=self._extract_constraints(),
        recursion_depth=self.session.recursion_depth + 1,
        voice_mode="system",
    )

def _spawn_continuation(self, bundle: ContinuationBundle) -> None:
    """Open new session from bundle, increment recursion depth."""
    if bundle.recursion_depth >= self.session.max_recursion_depth:
        # Hit the cap, force accept
        return
    child_session = self.session_manager.open_session(
        goal=bundle.distilled_goal,
        cycle_config=self.session.cycle_config,
        vault_path=self.session.vault_path,
        parent_session_id=self.session.session_id,
    )
    # Continuation runs as a new cycle in the child session
    # bundle.to_priming_text() becomes the initial prompt
```

### 7.4 Schema migration

**Migration014** adds catalyst_arm_stats table:

```sql
CREATE TABLE catalyst_arm_stats (
    arm_name TEXT NOT NULL,
    cycle_config TEXT NOT NULL,
    total_invocations INTEGER NOT NULL DEFAULT 0,
    total_reward REAL NOT NULL DEFAULT 0.0,
    last_invoked_at INTEGER,
    PRIMARY KEY (arm_name, cycle_config)
);
```

### 7.5 Phase 9 success criterion

Cycle decisions wired to Clutch outputs, accept/refine/branch/stop actions all functional, naive arm learning updates after each Catalyst invocation. Continuation chains work — a session that hits context budget produces a child session with the bundle as priming.

## 8. Phase 10 — Consolidation (v0.3.4)

### 8.1 Scope

Phase 10 ships session consolidation:

1. `cerebra consolidate --session <id>` command
2. Session events reduced to a stable summary memory record
3. Calibration audit comparing predictions to outcomes across the session
4. Summary record becomes retrievable memory (consumed by future cycles)
5. Calibration delta logged for signal scoring formula evolution

### 8.2 New code surfaces

**`cerebra/cognition/consolidation.py`**:

```python
class ConsolidationEngine:
    def __init__(self, store: FossicStore, llm_adapter: LLMAdapter):
        self.store = store
        self.llm_adapter = llm_adapter

    def consolidate(self, session_id: str) -> ConsolidationResult:
        """Reduce session events to summary + calibration audit."""
        emitter = self._make_emitter(session_id)
        emitter.emit_cycle_event("ConsolidationStarted", {...})

        session_events = self._fetch_session_events(session_id)
        predictions = self._fetch_predictions(session_id)
        outcomes = self._fetch_outcomes(session_id)

        summary = self._generate_summary(session_events)
        summary_record_id = self._write_summary_to_memory(summary)
        calibration = self._calibration_audit(predictions, outcomes)

        emitter.emit_cycle_event("ConsolidationCompleted", {
            "summary_record_id": summary_record_id,
            "calibration_audit": calibration,
        })
        return ConsolidationResult(
            summary_record_id=summary_record_id,
            calibration_audit=calibration,
        )

    def _calibration_audit(
        self,
        predictions: list[PredictionRecord],
        outcomes: list[OutcomeRecord],
    ) -> dict:
        """Per-signal calibration delta computation."""
        per_signal = {}
        for signal_name in SIGNAL_NAMES:
            expected_avg = mean(p.expected_per_signal[signal_name] for p in predictions)
            actual_avg = mean(o.per_signal_error.get(signal_name, 0) for o in outcomes)
            per_signal[signal_name] = actual_avg - expected_avg
        overall_status = self._classify_calibration(per_signal)
        return {
            "per_signal_calibration_delta": per_signal,
            "overall_calibration_status": overall_status,
        }
```

### 8.3 Phase 10 success criterion

`cerebra consolidate --session <id>` produces summary plus calibration audit, summary becomes retrievable memory record (queryable via `cerebra search`), calibration delta logged for signal scoring formula evolution.

## 9. Phase 11 — Graph export (v0.3.5)

### 9.1 Scope

Phase 11 ships graph export for LumaWeave consumption:

1. `cerebra export graph --out <path>` command
2. JSON serialization of nodes plus structural plus semantic plus lattice edges
3. No temporal graph layer (v0.2)
4. Format documented for LumaWeave consumption contract

### 9.2 New code surfaces

**`cerebra/export/graph_export.py`**:

```python
class GraphExporter:
    def __init__(self, store: FossicStore, db_path: Path):
        self.store = store
        self.db_path = db_path

    def export(
        self,
        output_path: Path,
        session_filter: Optional[str] = None,
        include_lattice_lineages: bool = True,
    ) -> ExportResult:
        """Serialize Cerebra graph state to JSON."""
        nodes = self._collect_nodes(session_filter)
        edges = self._collect_edges(session_filter, include_lattice_lineages)

        graph_data = {
            "schema_version": 1,
            "exported_at": now_ms(),
            "vault_path": str(self.db_path.parent),
            "session_filter": session_filter,
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "include_lattice": include_lattice_lineages,
            },
        }

        with open(output_path, "w") as f:
            json.dump(graph_data, f, indent=2)

        emitter = self._make_emitter()
        emitter.emit_cycle_event("GraphExported", {
            "output_path": str(output_path),
            "node_count": len(nodes),
            "edge_count": len(edges),
        })

        return ExportResult(
            output_path=output_path,
            node_count=len(nodes),
            edge_count=len(edges),
        )
```

### 9.3 Phase 11 success criterion

`cerebra export graph --out cerebra_graph.json` produces JSON LumaWeave can consume. Includes nodes plus structural plus semantic plus lattice edges. No temporal graph layer.

## 10. Open implementation questions (deferred to step-level design)

Items not locked in this design doc, resolved during step implementation:

- **Snapshot cadence for non-lattice aggregates.** v0.1 only has lattice node aggregates; future aggregates need cadence determined by their access patterns.
- **Specific Clutch rule pre-writing.** The default Clutch rule set is drafted in Phase 9 design step.
- **Catalyst arm vocabulary per cycle config.** Each cycle config defines its own arms; specific vocabularies drafted in Phase 9.
- **Calibration audit specifics for consolidation.** Detailed scoring methodology drafted in Phase 10.
- **LumaWeave consumption contract details.** Joint design with LumaWeave when its wiring begins.

These are appropriately deferred — they need step-level detail, not block-level commitment.

## 11. Risks and mitigations

**PyO3 bridge cost on lattice reads.** Quantified at 47μs/event, snapshot-every-100 keeps replay windows small. Profile in Phase 6 Step 1 against the real LatticeNodeReducer. If apply cost pushes per-event time meaningfully above 47μs, tighten cadence (50 events). v2 Rust port available if witness layer profiling reveals lattice reads dominate latency budget AND user-facing slowness is measurable.

**Bandit deviation during multi-step implementation.** Mandatory deviation log discipline applies. Each pass produces `docs/agent/deviations/<version>.md`. Merge gate requires review before each version bump.

**Cycle config schema evolution.** v0.1 ships `simple.planning.v0` only. Multiple cycle configs deferred to v0.2. Schema is forward-compatible (CycleConfig dataclass with optional fields).

**LLM adapter test coverage.** Unit tests use mock adapter; integration tests use local Ollama. Mock-only testing risks missing real-prompt failures; Ollama-only testing risks slow test runs. Mixed strategy mitigates both.

**Re-injection drift across continuation chains.** Each continuation has slightly less context than parent. Per the re-injection doctrine, recursion cap (5 levels default) prevents unbounded drift. Periodic full-context anchor steps deferred to v0.2.

## 12. Multi-agent build coordination (if used)

If Phase 6 block implementation uses multiple Claude Code agents in parallel (per the discussion in needs assessment §10):

- Coordination doc names section boundaries, interface contracts, agent ownership, integration test surface, merge order
- Each agent owns its section's tests plus integration tests against adjacent sections' published interfaces
- Mandatory deviation log per agent per pass, aggregated in coordination doc
- Merge gate to `#approve-this` required before any agent's work lands

If single-agent (bandit owns all six sub-phases sequentially), the above doesn't apply.

## 13. Block close criteria

Block ships as v0.3.5 when:

1. All six sub-phases have closed PASS COMPLETE blocks documented in `#changelog`
2. The block-level demonstration works: `cerebra run-cycle simple.planning.v0 --goal "..."` produces a complete session with consolidation and graph export
3. Test count crosses an agreed threshold (rough estimate: 1200-1500 total tests at block close, from ~920 at v0.2.7)
4. No open architectural questions blocking subsequent v0.2 work
5. Documentation updated: SCHEMA_VERSIONS.md, CHANGELOG.md, and any affected architecture docs reflect Phase 6 block changes

When all five criteria clear, v0.3.5 ships and v0.1 Cerebra MVP is delivered.

---

*This design doc is the contract bandit implements against. Subsequent step-level prompts derive from this doc rather than re-deriving decisions. If implementation surfaces a need to revise something here, it's a deviation worth logging — the doc gets updated, the deviation log captures why, the design stays the source of truth.*

*Once bandit reads this doc and the companions, Phase 6 Step 1 begins. The prototype gate decision lands at Phase 8 kickoff.*
