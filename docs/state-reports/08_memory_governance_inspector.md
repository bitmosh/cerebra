# Cerebra — Memory, Governance, Inspector & Primitives

---

## 1. MemoryRecord (`cerebra/memory/records.py`)

### MemoryRecord dataclass

```python
@dataclass
class MemoryRecord:
    record_id: str              # "rec_" + sha256(chunk_id)[:12]  OR  "ep_" + uuid[:12]
    record_type: str            # "source_chunk" | "cycle_episode"
    source_id: str              # real source OR "src_synthetic" (episodes)
    document_id: str            # real doc OR "doc_synthetic" (episodes)
    chunk_id: str               # real chunk OR "chk_synthetic" (episodes)
    content: str
    content_hash: str           # sha256 hex of content
    token_estimate: int         # character_count // 4
    sku_address: str | None     # None until classified
    sku_assigned_at: int | None
    lifecycle_state: str        # "active" | "archived" | "tombstoned"
    created_at: int
    schema_version: int
    # M015-M017 additions:
    is_lattice_member: bool     # True if this record is a lattice sibling
    lattice_lineage_id: str | None
    lattice_confidence: float | None
```

**Record ID derivation:**
- Ingested records: `"rec_" + sha256(chunk_id)[:12]` — stable, content-addressed by chunk
- Episode records: `"ep_" + uuid[:12]` — random per episode
- Lattice sibling records: `"rec_" + sha256(f"{primary_record_id}:{category}")[:12]` — deterministic

### `build_record(chunk: Chunk, source: SourceRecord) → MemoryRecord`

Derives `record_id` from `chunk.chunk_id`, sets `record_type="source_chunk"`, lifecycle_state="active".

### `build_records_for_document(chunks: list[Chunk], source: SourceRecord) → list[MemoryRecord]`

Calls `build_record()` for each chunk. No DB writes — returns list for batch insert by caller.

---

## 2. Lifecycle Manager (`cerebra/memory/lifecycle.py`)

### State Machine

```
   ┌─────────────────────────────────┐
   │                                  ▼
active ──archive──▶ archived ──tombstone──▶ tombstoned (terminal)
   │                    │
   │◀──restore──────────┘
   │
   └──tombstone──▶ tombstoned (terminal)
```

Four valid transitions:
1. `active → archived` (archive)
2. `active → tombstoned` (tombstone)
3. `archived → active` (restore)
4. `archived → tombstoned` (tombstone)

`tombstoned` is a terminal state. No transitions out of tombstoned. Attempting `tombstone → *` raises `InvalidTransitionError`.

### `LifecycleManager(db_path: Path, event_log: SQLiteEventLog | None = None)`

### `transition(record_id, target_state, *, actor="cli", reason=None) → str`

Returns previous state (for callers that need to know what changed).

**Steps:**
1. Read current state; raise `RecordNotFoundError` if absent
2. Validate transition is in the valid set; raise `InvalidTransitionError` if not
3. `UPDATE memory_records SET lifecycle_state = target_state WHERE record_id = ?`
4. FTS5 sync:
   - `active → archived`: delete from `memory_records_fts`
   - `active → tombstoned`: delete from `memory_records_fts`
   - `archived → active`: re-insert into `memory_records_fts`
   - `archived → tombstoned`: no-op (already absent from FTS5)
5. Emit appropriate inspector event (after `conn.close()`)

**Inspector events emitted:**
- `active → archived` → `MemoryRecordArchived`
- `* → tombstoned` → `MemoryRecordTombstoned`
- `archived → active` → `MemoryRecordRestored`

### `batch_transition(record_ids, target_state, *, actor, reason) → dict[str, str]`

Returns `{record_id: previous_state}` for all successfully transitioned records.

### Convenience methods

```python
def archive(record_id, *, actor="cli", reason=None) -> str
def tombstone(record_id, *, actor="cli", reason=None) -> str
def restore(record_id, *, actor="cli", reason=None) -> str
def get_state(record_id) -> str | None   # None if record not found
```

### Exceptions

```python
class LifecycleError(Exception): ...
class RecordNotFoundError(LifecycleError): ...
class InvalidTransitionError(LifecycleError): ...
```

---

## 3. Governance Models (`cerebra/governance/models.py`)

### SignalCondition

```python
@dataclass
class SignalCondition:
    signal_name: str    # one of SIGNAL_NAMES, or a virtual signal
    op: ConditionOp
    value: float | list

class ConditionOp(str, Enum):
    GTE = ">="
    LTE = "<="
    GT  = ">"
    LT  = "<"
    EQ  = "=="
    NEQ = "!="
    IN  = "in"

def evaluate(self, signals: dict[str, float]) -> bool
```

### LeewayRule

```python
@dataclass
class LeewayRule:
    rule_id: str            # "LR-001" through "LR-015"
    capability: str         # maps to ProposedAction.action_name
    conditions: list[SignalCondition]
    condition_join: str     # "AND" | "OR"
    scope: LeewayScope      # current_step | current_cycle | current_session | persistent
    phase: LeewayPhase      # pre_action | post_action | both
    revocation_conditions: list[SignalCondition]
    description: str

def is_granted(self, signals: dict[str, float]) -> bool
    # AND: all conditions True
    # OR: any condition True

def is_revoked(self, signals: dict[str, float]) -> bool
    # any revocation condition True → revoked

def grants(self, action: str) -> bool
    # capability matches action AND phase includes pre_action
```

### ConstitutionalRule

```python
@dataclass
class ConstitutionalRule:
    rule_id: str    # "CONST-001" through "CONST-005"
    description: str
    trigger_keywords: list[str]
    ...

def forbids(self) -> bool:
    return False    # always False in v0.1 (DEV-009: constitutional enforcement deferred)
```

---

## 4. Governance Defaults (`cerebra/governance/defaults.py`)

Written to vault at init by `write_defaults_to_vault()`. 15 LR rules + 5 CONST rules.

### Selected Leeway Rules

| Rule ID | Capability | Conditions | Notes |
|---|---|---|---|
| LR-001 | retrieve_context | GROUNDEDNESS ≥ 0.3 | Baseline retrieval gate |
| LR-002 | expand_retrieval | GROUNDEDNESS < 0.5 AND RELEVANCE < 0.5 | Trigger wider search |
| LR-003 | refine_step | COHERENCE < 0.6 | Allow step refinement |
| LR-004 | critique_pass | PRECISION < 0.5 OR GROUNDEDNESS < 0.4 | Allow critique step |
| LR-005 | spawn_continuation_bundle | composite < 0.6 AND continuation_count < 5 AND has_clear_next_focus | Revoked if token_budget_exhausted |
| LR-006 | apply_strategy_arm | COHERENCE ≥ 0.3 | Catalyst arm application gate |
| LR-007 | explore_alternative | GENERATIVITY < 0.4 | Allow exploration |
| LR-008 | consolidate_outputs | steps_run ≥ 3 | Allow consolidation |
| LR-009 | ask_clarifying_question | EPISTEMIC_HUMILITY ≥ 0.5 | Ask user gate |
| LR-010 | write_to_episodic_memory | (unconditional) | **Always permitted** in v0.1; no conditions |
| LR-011 | write_to_semantic_memory | GROUNDEDNESS ≥ 0.7 AND EPISTEMIC_HUMILITY ≥ 0.6 | Revoked if contradiction_against_existing_semantic |
| LR-012 | tombstone_memory | user_requested == True | User must explicitly request |
| LR-013 | promote_to_truth_tower | COHERENCE ≥ 0.5 AND GROUNDEDNESS ≥ 0.5 | Tower promotion gate |
| LR-014 | apply_clutch_stop | composite < 0.3 AND consecutive_below >= 2 | Clutch stop gate |
| LR-015 | branch_execution | GENERATIVITY ≥ 0.6 AND steps_run <= max_steps/2 | Branching gate |

**LR-010 note:** `write_to_episodic_memory` has no conditions and is unconditionally "permitted". This is the rule that gates `EpisodeWriter.write()`. The result: every step always writes an episode (subject to governance, but governance always grants it in v0.1).

### Constitutional Rules

| Rule ID | Prohibition |
|---|---|
| CONST-001 | CBRN / mass violence content |
| CONST-002 | Sentience or consciousness claims |
| CONST-003 | Targeted harm to specific individuals |
| CONST-004 | System deception (pretending to be human, hiding AI nature) |
| CONST-005 | Safety-pinned tombstone bypass |

All CONST rules return `forbids() = False` in v0.1 (DEV-009: enforcement deferred to future phase). The rules are loaded and inspected but not yet enforced at runtime.

---

## 5. Pre-Action Gate (`cerebra/governance/pre_action_gate.py`)

### ProposedAction

```python
@dataclass(frozen=True)
class ProposedAction:
    action_name: str    # e.g. "write_to_episodic_memory"
    session_id: str
    cycle_id: str
    step_id: str
    payload: dict       # context for condition evaluation
```

### GateDecision

```python
@dataclass(frozen=True)
class GateDecision:
    final_decision: str         # "permitted" | "forbidden"
    proposed_action: ProposedAction
    grants_applied: list[str]   # rule_ids that granted
    forbidden_by: list[str]     # rule_ids that forbade
    review_required_by: list[str]   # deferred to v0.2 (always empty in v0.1)
```

### `LeewayPreActionGate.evaluate(proposed_action) → GateDecision`

1. Load all leeway rules for this vault
2. Evaluate each rule:
   - `rule.grants(proposed_action.action_name)` — check capability + phase
   - If yes: `rule.is_granted(signals)` from `proposed_action.payload`
   - If granted and not revoked: add to `grants_applied`
3. `final_decision = "permitted"` if `len(grants_applied) > 0` else `"forbidden"`

**Special case:** `LR-010` (write_to_episodic_memory) has no conditions → always evaluates to `is_granted=True` when capability matches.

**`requires_review`:** Deferred to v0.2 (DEV-010). Always empty list in v0.1.

---

## 6. Inspector Layer (`cerebra/inspector/`)

### InspectorEvent (`cerebra/inspector/event.py`)

```python
@dataclass
class InspectorEvent:
    event_type: str
    actor: str              # e.g. "ingest", "classify", "cycle", "cli"
    summary: str            # one-line human-readable description
    data: dict              # full event payload
    event_id: str           # "evt_" + uuid[:12] (default_factory)
    schema_version: int     # 1
    timestamp: int          # unix seconds (default_factory)
    session_id: str | None
    cycle_id: str | None
    step_id: str | None
    subject_id: str | None  # primary ID of the affected object (record_id, source_id, etc.)
```

`ALL_KNOWN_EVENT_TYPES` set (~50 values) across phases:
- PHASE_0: SystemInitialized, VaultCreated, MigrationRun, ConfigLoaded, LeewayRuleLoaded, ConstitutionalBlock
- PHASE_1 (ingest): SourceRegistered, SourceChanged, SourceParsed, SourceParseFailed, DocumentNormalized, DocumentParseWarning, ChunkCreated, MemoryRecordCreated, LexicalIndexUpdated, ArtifactWritten
- PHASE_2 (SKU): SKUAssigned, SKUReclassified, ClassificationFailed, ClassificationLowConfidence, BackfillStarted, BackfillCompleted, LatticeCommit
- PHASE_4 (graph): GraphNodeCreated, GraphEdgeCreated, GraphExported, GraphSnapshotAvailable
- PHASE_4 (retrieval): QueryReceived, QueryPlanned, TraversalStepCompleted, ContextPacketBuilt, LatticeSiblingResolved
- PHASE_5 (WM/Tower): AttentionItemProposed, AttentionItemPromoted, AttentionItemEvicted, AttentionItemDeferred, TowerInitialized, TowerItemPromoted, TowerItemEvicted, TowerItemStaled, TowerCrossReferenceAdded, TowerRendered
- PHASE_5 (lifecycle): MemoryRecordArchived, MemoryRecordTombstoned, MemoryRecordRestored
- PHASE_6 (cognition): SignalEvaluated, EvaluationComposed, OutcomeRecorded, PredictionSevereMiss, ClutchDecisionMade, CatalystInvoked, CatalystArmSelected, LeewayGrantApplied, LeewayGrantDenied, LeewayRevocationFired, MemoryWriteFromCycle

### `make_event()` helper

```python
def make_event(
    event_type: str,
    actor: str,
    summary: str,
    data: dict,
    *,
    session_id: str | None = None,
    cycle_id: str | None = None,
    step_id: str | None = None,
    subject_id: str | None = None,
) -> InspectorEvent
```

### SQLiteEventLog (`cerebra/inspector/sqlite_log.py`)

Writes to `inspector_events` table.

```python
class SQLiteEventLog:
    def __init__(self, db_path: Path)
    
    def write(self, event: InspectorEvent) -> None
    def query_by_type(self, event_type: str, limit: int = 100) -> list[dict]
    def query_recent(self, limit: int = 50) -> list[dict]
    def query_by_session(self, session_id: str) -> list[dict]
    def query_by_subject(self, subject_id: str, event_type: str | None = None) -> list[dict]
```

### NDJSONEventLog (`cerebra/inspector/ndjson_log.py`)

Line-atomic append to NDJSON files. Each write is a single JSON line followed by `\n`.

```python
class NDJSONEventLog:
    def __init__(self, file_path: Path)
    
    def write(self, event: InspectorEvent) -> None    # atomic append
    def read_all(self) -> list[str]                   # all lines
```

Files used:
- `vault/events/ingest.ndjson` — ingest pipeline events
- `vault/events/system.ndjson` — vault init and system events
- `vault/events/classify.ndjson` — SKU classification events

---

## 7. Primitives (`cerebra/_primitives/`)

Seven vendored primitive modules. All are pure Python with no external dependencies. Fully covered by unit tests. Not imported by user code directly — consumed by cognition modules.

### `bandit.py` — UCB1 Bandit

```python
class Bandit:
    def __init__(self, exploration_weight: float = 1.4)
    
    def select(self, arm_ids: list[str], total_steps: int) -> BanditSelection
    # Forces unsampled arms first; then UCB1: mean + w * sqrt(log(total+1) / count)
    
    def to_state(self) -> dict       # serialize arm stats
    def from_state(cls, state: dict) # deserialize

@dataclass
class BanditSelection:
    arm_id: str
    score: float
    was_forced: bool   # True if arm was unsampled (exploration forced)
```

Used by `CatalystEngine`.

---

### `clutch.py` — Primitive Clutch

Simpler than the cognition-layer ClutchEngine. Used directly in tests and small configurations.

```python
@dataclass
class Rule:
    name: str
    guard: Callable[[dict, dict], bool]   # (signals, state) → bool
    action: str | Callable                # action name or callable

@dataclass
class Decision:
    action: str
    intensity: float
    reason: str
    confidence: float
    metadata: dict

class Clutch:
    def __init__(self, rules: list[Rule])
    def decide(self, signals: dict, state: dict) -> Decision
    # First matching rule wins
    def explain(self) -> list[dict]
    # Per-rule firing trace for debugging
```

---

### `score_composer.py` — Composite Score

```python
@dataclass
class CompositeScore:
    composite: float
    components: dict[str, float]    # {name: raw_value}
    weights: dict[str, float]       # {name: weight}
    
    def explain(self) -> list[dict]:
        # Returns: [{component, value, weight, contribution}, ...]

def compose(
    components: dict[str, float],
    weights: dict[str, float],
    validate_weights: bool = True,
) -> CompositeScore
```

`validate_weights=True` raises `ValueError` if `sum(weights.values())` is not approximately 1.0.

---

### `trajectory.py` — Trajectory Tracker

```python
class TrajectoryTracker:
    def __init__(
        self,
        maxlen: int = 20,
        trend_window: int = 3,
        improving_threshold: float = 0.05,
        degrading_threshold: float = -0.05,
    )
    
    def update(self, composite: float, delta: float) -> TrajectoryState

@dataclass
class TrajectoryState:
    trend: str          # "improving" | "flat" | "degrading"
    label: str          # human-readable label (same as trend)
    failure_streak: int # consecutive steps below threshold
    delta_history: list[float]
```

`trend` is computed over the last `trend_window` deltas:
- mean delta ≥ `improving_threshold` → `"improving"`
- mean delta ≤ `degrading_threshold` → `"degrading"`
- otherwise → `"flat"`

Used by the `composite_trajectory_degrading` clutch predicate.

---

### `tombstone_set.py` — TombstoneSet

```python
class ItemState(Enum):
    PRESENT    = "present"
    TOMBSTONED = "tombstoned"
    ABSENT     = "absent"

class TombstoneSet:
    def add(self, item_id: str) -> None
    # Raises if item_id is tombstoned (blocked re-insertion)
    
    def tombstone(self, item_id: str) -> None
    # Transitions present → tombstoned (or no-op if absent)
    
    def restore(self, item_id: str) -> None
    # Removes tombstone (tombstoned → absent, then can be re-added)
    
    def state(self, item_id: str) -> ItemState
    
    def get_with_tombstones(self) -> dict[str, ItemState]
    # For audit: all items including tombstoned ones
```

Per-item states: present / tombstoned / absent. A tombstoned item blocks re-insertion until `restore()` is called.

---

### `mode_router.py` — Hysteresis Mode Router

Prevents mode flapping when signals hover near a boundary. A mode must hold for `min_duration` steps before it can change.

```python
class HysteresisModeRouter:
    def __init__(
        self,
        min_duration: int = 3,
        override_conditions: dict | None = None,
    )
    
    def decide(
        self,
        signals: dict[str, float],
        candidate_mode: str,
    ) -> ModeDecision

@dataclass
class ModeDecision:
    mode: str           # current active mode (may differ from candidate_mode)
    changed: bool       # True if mode actually changed this step
    reason: str         # "hysteresis_hold" | "mode_changed" | "override"
    duration: int       # steps current mode has been active
```

`override_conditions` bypass `min_duration` when specific signal conditions are met (e.g., extreme signal value → immediate mode change regardless of duration).

---

### `triangulator.py` — Triangulate Score

Combines a raw score with confidence and signal strength into a shaped final value.

```python
def triangulate(
    score: float,
    confidence: float,
    signal_strength: float,
    clamp_lo: float = 0.0,
    clamp_hi: float = 1.2,   # allows >1.0 for positive shaping bonus
) -> float

def triangulate_with_components(
    score: float,
    confidence: float,
    signal_strength: float,
    clamp_lo: float = 0.0,
    clamp_hi: float = 1.2,
) -> tuple[float, dict]   # (result, component breakdown)
```

`clamp_hi = 1.2` is intentional — high confidence + high signal_strength can produce a shaped result > 1.0 as a bonus signal. Callers are responsible for re-clamping if they need a strict [0, 1] range.

Formula (approximate): `result = score × (confidence + signal_strength) / 2`, then clamped. The exact formula is in source.
