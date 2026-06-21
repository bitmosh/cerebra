# Cerebra — Cognition Layer: Core Runtime

---

## 1. Compile-Time Constants (`cerebra/cognition/_constants.py`)

All constants are module-level and evaluated at import time. Not configurable at runtime without code changes.

```python
# Signal names (6)
SIGNAL_NAMES = frozenset({
    "COHERENCE",
    "GROUNDEDNESS",
    "GENERATIVITY",
    "RELEVANCE",
    "PRECISION",
    "EPISTEMIC_HUMILITY",
})

# Signal weights (must sum to 1.0)
SIGNAL_WEIGHTS = {
    "COHERENCE":           0.20,
    "GROUNDEDNESS":        0.20,
    "GENERATIVITY":        0.15,
    "RELEVANCE":           0.15,
    "PRECISION":           0.15,
    "EPISTEMIC_HUMILITY":  0.15,
}

# Retrieval floor (composite score minimum for context packet)
_RETRIEVAL_FLOOR = 0.35

# Working memory / tower
ELEVATED_SALIENCE = 0.8           # salience applied to cited records promoted to WM
TOWER_CAPACITIES = {1: N, 2: N}   # T1 and T2 capacity limits (exact values in source)

# Lattice
LATTICE_COMMIT_THRESHOLD = 0.65
LATTICE_SNAPSHOT_CADENCE = N      # fossic events between lattice snapshots

# Prediction error classifiers (signed error thresholds)
PREDICTION_ERROR_CLASSIFIERS = {
    "noise":   0.05,   # |error| < 0.05 → "noise"
    "notable": 0.15,   # 0.05 ≤ |error| < 0.15 → "notable"
    # |error| ≥ 0.15 → "severe"
}

# Recursion
RECURSION_DEPTH_DEFAULT = 0

# Synthetic provenance FK anchors (M018)
SYNTHETIC_SOURCE_ID   = "src_synthetic"
SYNTHETIC_DOCUMENT_ID = "doc_synthetic"
SYNTHETIC_CHUNK_ID    = "chk_synthetic"

# Built-in reinjection predicate names
BUILTIN_REINJECTION_PREDICATE_NAMES: frozenset[str]  # see reinjection.py
```

---

## 2. LLM Adapters (`cerebra/cognition/llm_adapter.py`)

### OllamaDirectAdapter (preferred)

```python
class OllamaDirectAdapter:
    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.model    = os.environ.get("OLLAMA_MODEL", "...")
        self.timeout  = int(os.environ.get("TIMEOUT_SECONDS", "300"))
```

**IPv4 binding:** Uses `127.0.0.1` not `localhost` to avoid IPv6 connection hang with Docker on systems where `localhost` resolves to `::1`.

Methods:
```python
def chat(self, messages: list[dict]) -> str
def classify_quadrant(self, content: str) -> ClassificationResult
def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult
def complete_structured(self, prompt: str, schema: dict) -> dict
```

`complete_structured()` injects a JSON schema into the prompt and enforces structured output. Used by all signal evaluators except EPISTEMIC_HUMILITY.

### ProxyLLMAdapter (legacy LiteLLM)

```python
class ProxyLLMAdapter:
    def __init__(self):
        self.base_url = os.environ.get("LITELLM_BASE_URL")
        self.api_key  = os.environ.get("LITELLM_API_KEY")
        self.model    = os.environ.get("CEREBRA_LLM_MODEL")
```

Same interface as OllamaDirectAdapter. Used when LiteLLM proxy is preferred over direct Ollama.

### ClassificationResult

```python
@dataclass
class ClassificationResult:
    scores: dict[str, float]       # category/quadrant name → score
    confidence: float
    primary: str                   # highest-score category/quadrant
    reasoning: str
    model_string: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    raw_scores_json_override: str | None  # full JSON stored in sku_assignments
```

---

## 3. EventEmitter (`cerebra/cognition/event_emitter.py`)

The EventEmitter centralizes all Fossic stream writes for the cognition layer. Both cycle events and lattice events route through it.

```python
class EventEmitter:
    def __init__(
        self,
        store: FossicStore,
        session_id: str,
        cycle_id: str,
    )
```

### Cycle events

```python
def emit_cycle_event(
    event_type: str,
    payload: dict,
    causation_id: bytes | None = None,
    indexed_tags: dict | None = None,
) -> bytes   # returns event ID bytes (used as causation_id for next event)
```

Stream: `cerebra/agent-trace/<session_id>`

**Implicit causation chain:** Each call without an explicit `causation_id` automatically uses the previous emit's returned event ID as causation. This builds a linear causal chain through the entire cycle's event stream.

### Lattice events

```python
def emit_lattice_event(
    lineage_id: str,
    event_type: str,
    payload: dict,
    causation_id: bytes | None = None,
    indexed_tags: dict | None = None,
) -> bytes
```

Stream: `cerebra/lattice/<lineage_id>` (separate stream per lineage, no auto-chain).

### Lattice snapshots

```python
def trigger_lattice_snapshots_at_cycle_boundary(
    touched_lineages: set[str],
) -> None
```

Called at the end of each cycle step. For each lineage in `touched_lineages`, calls `store.take_snapshot(stream_id)` if `LATTICE_SNAPSHOT_CADENCE` events have elapsed since the last snapshot.

---

## 4. RuntimeSession & SessionManager (`cerebra/cognition/session.py`)

### RuntimeSession

```python
@dataclass(frozen=True)
class RuntimeSession:
    session_id: str             # "sess_" + uuid[:12]
    cycle_config: str           # cycle config name (e.g. "simple.planning.v0")
    goal: str
    vault_path: Path
    opened_at: int              # ms timestamp
    parent_session_id: str | None   # set for reinjected child sessions
    recursion_depth: int        # 0 for top-level sessions
    max_recursion_depth: int    # from RECURSION_DEPTH_DEFAULT or cycle config
    cycles_run: int
    steps_run: int
    state: str                  # "active" | "flushed" | "continued"
    flushed_at: int | None
    final_outcome: str | None   # "accept" | "stop" | "cap_reached" | etc.
```

**DEV-012:** `session_id` IS the cycle_id segment embedded in the Fossic stream name: `cerebra/agent-trace/<session_id>`. Session ID and cycle ID are the same identifier.

### SessionManager

```python
class SessionManager:
    def __init__(self, db_path: Path, store: FossicStore)
```

**`open_session(goal, cycle_config, vault_path, parent_session_id=None) → (RuntimeSession, bytes)`**

Returns `(session, opened_event_id)`. The `opened_event_id` (bytes) is the Fossic event ID of the `SessionOpened` event, used as `causation_id` for the first `CycleStarted` event.

Steps:
1. Generate `session_id = "sess_" + uuid[:12]`
2. Insert into `runtime_sessions`
3. Emit `SessionOpened` to `cerebra/agent-trace/<session_id>`
4. Return `(session, event_id_bytes)`

**`flush_session(session_id, outcome, total_cycles, total_steps) → RuntimeSession`**

Updates `runtime_sessions` row: `state="flushed"`, `final_outcome`, `flushed_at`, `cycles_run`, `steps_run`.

Note: `SessionFlushed` is emitted by `CycleRuntime`, not by this method.

### Helper functions

```python
def write_session(db_path: Path, session: RuntimeSession) -> None
def read_session(db_path: Path, session_id: str) -> RuntimeSession | None
def update_session_state(db_path: Path, session_id: str, state: str, **kwargs) -> None
def list_sessions_for_vault(db_path: Path) -> list[RuntimeSession]      # DESC by opened_at
def list_continuation_chain(db_path: Path, root_session_id: str) -> list[RuntimeSession]
```

### SessionState (frozen, used internally by CycleRuntime)

```python
@dataclass(frozen=True)
class SessionState:
    session: RuntimeSession
    cycle_config_loaded: dict                       # parsed YAML as dict
    prior_step_composites: list[float]              # history of composite scores
    prior_step_per_signal: dict[str, list[float]] | None
```

---

## 5. Stop Condition Evaluator (`cerebra/cognition/stop_conditions.py`)

### CycleState

```python
@dataclass
class CycleState:
    steps_run: int
    all_steps_completed: bool       # all cycle config steps have executed
    recent_composites: list[float]  # sliding window for consecutive floor checks
    explicit_stop: bool             # set by ClutchEngine action="stop"
    user_interrupted: bool          # set by SIGINT handler
    consecutive_low_composites: list[float]  # rolling list below floor
```

### `StopConditionEvaluator.check(state) → (bool, str | None)`

Returns `(should_stop, reason)`. Checks conditions in config order; stops on FIRST match.

**Five condition types:**

| type | Parameters | Logic |
|---|---|---|
| `max_steps_reached` | `max_steps: int` | `state.steps_run >= max_steps` |
| `all_steps_completed` | (none) | `state.all_steps_completed == True` |
| `composite_floor_consecutive` | `floor: float, n: int` | last N composites all < floor |
| `explicit_clutch_stop` | (none) | `state.explicit_stop == True` |
| `user_interrupt` | (none) | `state.user_interrupted == True` |

---

## 6. Signal Evaluators (`cerebra/cognition/signals.py`)

### Evaluation order

```python
SIGNAL_EVAL_ORDER = [
    "COHERENCE",
    "GROUNDEDNESS",
    "GENERATIVITY",
    "RELEVANCE",
    "PRECISION",
    "EPISTEMIC_HUMILITY",
]
```

### Signal evaluation protocol (5 of 6 signals)

For COHERENCE, GROUNDEDNESS, GENERATIVITY, RELEVANCE, PRECISION:

1. Load prompt from `cerebra/cognition/signal_prompts/<signal_name_lower>.txt`
2. Inject: step output, goal, prior context
3. Call `llm.complete_structured(prompt, schema)` where schema enforces:
   ```json
   {
     "score": float,       // 0.0–1.0
     "strength": float,    // confidence in the score itself (0.0–1.0)
     "checks": [...],      // list of sub-checks evaluated
     "reasoning": string
   }
   ```
4. On missing `"checks"` or `"reasoning"` fields: mark `low_confidence=True`
5. On `ClassificationError`: fallback to `score=0.5, strength=0.5, low_confidence=True`

### EPISTEMIC_HUMILITY (special case)

**No LLM call.** Marker-based evaluation:
- Scans step output for positive markers: `"uncertain"`, `"perhaps"`, `"I don't know"`, `"unclear"`, `"might"`, `"possibly"`, etc.
- Scans for negative markers: overconfident language, absolute claims
- Score is derived from marker ratio
- Always has `low_confidence=False` (deterministic)

This makes EPISTEMIC_HUMILITY the fastest signal to evaluate and immune to LLM API failures.

---

## 7. Evaluation Composer (`cerebra/cognition/evaluation.py`)

### EvaluationComposer

```python
class EvaluationComposer:
    def __init__(self, weights: dict[str, float])
    # Validates: sum(weights.values()) ≈ 1.0 (tolerance 1e-6)
    # Validates: keys == SIGNAL_NAMES
```

### `compose(signals) → EvaluationPacket`

```
composite = sum(score_i × weight_i for each signal i)
composite = max(0.0, min(1.0, composite))   # clamp to [0, 1]
confidence = mean([signal.strength for signal in signals])
```

### EvaluationPacket

```python
@dataclass
class EvaluationPacket:
    evaluation_id: str              # "eval_" + uuid[:12]
    session_id: str
    cycle_id: str
    step_id: str
    composite_score: float          # 0.0–1.0
    confidence: float               # mean signal strength
    per_signal: dict[str, float]    # {signal_name: score}
    per_signal_strength: dict[str, float]
    low_confidence_signals: list[str]   # signals that flagged low_confidence
    evaluated_at: int
```

### Events emitted during evaluation

1. `SignalEvaluated` × 6 — one per signal, causation-chained sequentially
2. `EvaluationComposed` — composite result with all per-signal scores

---

## 8. Prediction Pipeline (`cerebra/cognition/predictions.py`)

### PredictionRecord

```python
@dataclass(frozen=True)
class PredictionRecord:
    prediction_id: str          # "pred_" + uuid[:12]
    session_id: str
    cycle_id: str
    step_id: str
    expected_composite_score: float
    expected_per_signal: dict[str, float]
    prediction_basis: str       # "prior_step_trajectory" | "cycle_config_default" | "static_baseline"
    confidence: float           # 0.8 | 0.6 | 0.7 | 0.5 (see below)
    made_at: int
```

### OutcomeRecord

```python
@dataclass(frozen=True)
class OutcomeRecord:
    outcome_id: str
    prediction_id: str
    session_id: str; cycle_id: str; step_id: str
    actual_composite_score: float
    prediction_error: float         # signed: actual - expected
    error_classification: str       # "noise" | "notable" | "severe"
    per_signal_error: dict[str, float]
    recorded_at: int
```

**Error classification thresholds:**
- `|error| < 0.05` → `"noise"`
- `0.05 ≤ |error| < 0.15` → `"notable"`
- `|error| ≥ 0.15` → `"severe"` (also emits `PredictionSevereMiss` event)

### Prediction basis selection

```python
def predict(input: PredictionInput) -> PredictionRecord
```

Basis and confidence selected by priority:

| Basis | Condition | Confidence |
|---|---|---|
| `prior_step_trajectory` | ≥2 prior composites available | 0.8 (≥3 prior) or 0.6 (exactly 2) |
| `prior_step_trajectory` | exactly 1 prior composite | 0.6 |
| `cycle_config_default` | cycle config specifies `composite_floor` | 0.7 |
| `static_baseline` | no prior data | 0.5, all signals at 0.65 |

For `prior_step_trajectory`: expected composite = moving average of last N composites. Per-signal expectations = moving average of per-signal scores.

### `resolve(prediction, evaluation) → OutcomeRecord`

Computes error, classifies it, returns OutcomeRecord.

### Events emitted

- `PredictionMade` — after `predict()`, before LLM call
- `OutcomeRecorded` — after `resolve()`
- `PredictionSevereMiss` — additionally if `error_classification == "severe"`

---

## 9. CycleRuntime (`cerebra/cognition/cycle_runtime.py`)

The main orchestrator. Owns the step loop, signal evaluation, clutch decisions, episode writes, and reinjection.

```python
class CycleRuntime:
    def __init__(
        self,
        config: CycleConfig,
        session: RuntimeSession,
        db_path: Path,
        store: FossicStore,
        llm: LLMAdapter,
        opened_event_id: bytes,         # from SessionManager.open_session()
        episode_writer: EpisodeWriter | None = None,
        install_signal_handlers: bool = True,   # False in tests
    )
```

### `run() → CycleResult`

```python
@dataclass
class CycleResult:
    session_id: str
    outcome: str            # "accept" | "stop" | "cap_reached" | "runtime_failure"
    steps_run: int
    step_history: list[StepRecord]
    final_composite: float | None
```

### Step loop (pseudocode)

```
cycle_state = CycleState(steps_run=0, ...)
emitter = EventEmitter(store, session_id, cycle_id)
emitter.emit_cycle_event("CycleStarted", {...}, causation_id=opened_event_id)

while True:
    should_stop, reason = StopConditionEvaluator.check(cycle_state)
    if should_stop:
        break

    step = resolve_step(config, cycle_state.steps_run)

    # Retrieve context
    plan = RetrievalPlanner.plan(goal)
    candidates = RetrievalTraversal.traverse(db_path, plan)
    scored = score_candidates(candidates, plan)
    deduped = dedup_siblings(scored, ...)
    filtered = filter_by_floor(deduped, _RETRIEVAL_FLOOR)
    packet = build_context_packet(...) if filtered else build_abstained_packet(...)

    # Build context vars for template
    context_vars = {
        "goal": session.goal,
        "retrieved_context": render_text(packet),
        "prior_step_output": last_step_output,
        "prior_steps": [step.output for step in step_history],
        "strategy_hint": catalyst_strategy_hint,  # from CatalystEngine if invoked
        "truth_tower": tower.render_chronological(),
    }

    emitter.emit_cycle_event("StepStarted", {"step_name": step.name, ...})

    # Predict before LLM call
    prediction = PredictionPipeline.predict(input)
    emitter.emit_cycle_event("PredictionMade", prediction.as_dict())

    # LLM call (5s retry on transient failure)
    output = llm.chat(render_template(step, context_vars))
    emitter.emit_cycle_event("StepExecuted", {"output": output, ...})

    # Evaluate signals (6 LLM calls + 1 marker-based)
    signals = evaluate_all_signals(output, goal, packet)    # 6 SignalEvaluated events
    packet_eval = EvaluationComposer(SIGNAL_WEIGHTS).compose(signals)  # EvaluationComposed

    # Record outcome
    outcome = PredictionPipeline.resolve(prediction, packet_eval)
    # OutcomeRecorded event + optional PredictionSevereMiss

    # Citation extraction
    cited_ids = re.findall(r'\brec_[0-9a-f]{12}\b', output)
    for rec_id in cited_ids:
        wm.promote(rec_id, salience=ELEVATED_SALIENCE)

    # Clutch decision
    clutch_decision = ClutchEngine.decide(context)
    emitter.emit_cycle_event("ClutchDecisionMade", clutch_decision.as_dict())

    # Catalyst (if clutch escalates)
    if clutch_decision.escalate_to_catalyst:
        catalyst_result = CatalystEngine.select(session_id, step_name, ...)
        if catalyst_result:
            emitter.emit_cycle_event("CatalystInvoked", ...)
            emitter.emit_cycle_event("CatalystArmSelected", ...)
            catalyst_strategy_hint = catalyst_result.strategy_prompt

    # Governance gate
    proposed = ProposedAction("write_to_episodic_memory", session_id, ...)
    gate = LeewayPreActionGate.evaluate(proposed)
    if gate.final_decision == "permitted":
        emitter.emit_cycle_event("LeewayGrantApplied", ...)
        record_id = EpisodeWriter.write(output, session_id, ...)
        emitter.emit_cycle_event("MemoryWriteFromCycle", {"record_id": record_id, ...})

    cycle_state.steps_run += 1
    prior_composites.append(packet_eval.composite_score)
    if clutch_decision.action == "stop":
        cycle_state.explicit_stop = True

emitter.emit_cycle_event("CycleCompleted", {"outcome": reason, ...})
session_manager.flush_session(session_id, outcome, ...)
emitter.emit_cycle_event("SessionFlushed", {...})

# Post-cycle reinjection check
_try_reinject(reason, step_history, session)
```

### Retrieval floor

`_RETRIEVAL_FLOOR = 0.35` — minimum composite score for a candidate to enter the context packet. When no candidates clear this floor, the packet is abstained (`is_abstained=True`, `selected_memory=[]`). The LLM still receives the prompt but sees no retrieved context.

### Citation extraction

```python
cited_ids = re.findall(r'\brec_[0-9a-f]{12}\b', output)
```

Any `rec_<12hex>` patterns in LLM output are treated as memory record citations. Cited records are promoted into WorkingMemory at `ELEVATED_SALIENCE = 0.8`.

### LLM retry

The `llm.chat()` call is wrapped with a 5-second retry on transient failures (connection timeout, empty response). Maximum 1 retry (2 total attempts) before emitting `StepExecutionFailed` and aborting the step.

### `_try_reinject()`

Called after the cycle completes. Passes termination reason, step history, and session metadata to `ReinjectionTriggerEvaluator.evaluate()`. If the evaluator fires, spawns a child `CycleRuntime` via `SessionManager.open_session(parent_session_id=session_id)`. The child session runs recursively. Blocked when `session.recursion_depth >= session.max_recursion_depth`.

### Fossic events in emission order

1. `CycleStarted` (causation: `opened_event_id`)
2. Per step:
   - `StepStarted`
   - `ContextPacketBuilt`
   - `PredictionMade`
   - `StepExecuted` (or `StepExecutionFailed`)
   - `SignalEvaluated` × 6 (causation-chained)
   - `EvaluationComposed`
   - `OutcomeRecorded`
   - `PredictionSevereMiss` (if severe error)
   - `ClutchDecisionMade`
   - `CatalystInvoked` (if escalated)
   - `CatalystArmSelected` (if escalated + arm found)
   - `LeewayGrantApplied` (if permitted)
   - `MemoryWriteFromCycle`
3. `CycleCompleted`
4. `SessionFlushed`
5. `ReinjectionTriggered` (if reinjection fires)
