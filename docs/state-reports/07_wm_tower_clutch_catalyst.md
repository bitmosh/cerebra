# Cerebra — Working Memory, Truth Tower, Clutch, Catalyst & Episode Systems

---

## 1. Working Memory (`cerebra/cognition/working_memory.py`)

WorkingMemory is the short-term attention store for a cognitive session. It holds a bounded set of `WorkingMemoryItem`s ranked by effective salience, with LRU eviction at capacity.

### Session management

```python
def new_session(vault_path: Path, session_id: str) -> WorkingMemorySession
```

- Closes any existing `active` session first (single-session invariant — only one WM session per vault at a time)
- Creates new row in `sessions` table
- Returns `WorkingMemorySession`

WM session IDs: `"sess_" + uuid[:12]` (same prefix as RuntimeSession — they are linked but distinct objects).

### WorkingMemoryItem IDs

`"wmi_" + uuid[:12]`

### Salience and effective salience

```python
effective_salience = actual_salience + 0.20   # if item is cited in truth tower
effective_salience = actual_salience           # otherwise
```

Tower-cited items get a +0.20 bonus to prevent them from being evicted even if their raw salience is low.

### `promote(record_id, salience) → WorkingMemoryItem | None`

1. Emit `AttentionItemProposed`
2. Check capacity: if at capacity, evict lowest-effective-salience non-pinned item → emit `AttentionItemEvicted`
3. Insert new item
4. If insertion would still overflow (shouldn't happen): emit `AttentionItemDeferred`
5. Emit `AttentionItemPromoted`
6. Return item (or None if deferred)

### Events

- `AttentionItemProposed` — a record has been proposed for WM
- `AttentionItemPromoted` — successfully added to WM
- `AttentionItemEvicted` — removed to make room
- `AttentionItemDeferred` — rejected (edge case, capacity guard)

---

## 2. Truth Tower (`cerebra/cognition/truth_tower.py`)

The truth tower is a two-tier promoted knowledge store. T1 is auto-promoted from retrieval (high-value retrieved records). T2 is explicitly promoted from working memory, must cite a T1 item.

### TowerItem

```python
@dataclass
class TowerItem:
    tower_item_id: str          # "tti_" + uuid[:12]
    session_id: str
    tier: int                   # 1 or 2
    wm_item_id: str | None      # T2 only: which WM item was promoted
    record_id: str | None       # underlying memory record (T1 always has this)
    retrieval_trace_id: str | None  # T1 only: which retrieval surfaced this
    content_summary: str        # first 400 chars of record content
    salience_score: float
    sku_address: str | None
    t1_citation_id: str | None  # T2 only: tower_item_id of cited T1 item
    is_pinned: bool
    is_stale: bool              # True if cited T1 was evicted
    promoted_at: int            # ms timestamp
    evicted_at: int | None
```

### `TruthTower(db_path, session_id)`

### `promote_to_t1(memory_items, trace_id, event_log=None) → list[TowerItem]`

Called by `build_context_packet()` when `--promote-t1` is set, and optionally by `CycleRuntime` after each retrieval.

**Steps:**
1. Filter: skip records already in active T1 for this session (idempotent)
2. Lattice sibling dedup via `dedup_memory_items()` (pre-filter before tower insertion)
3. Safety net dedup by `chunk_id` (catches non-tagged records that share a chunk)
4. For each surviving item:
   a. Check T1 capacity
   b. If at capacity: evict lowest-salience non-pinned T1 item → emit `TowerItemEvicted`
   c. After T1 eviction: stale all T2 items that cite the evicted T1 → emit `TowerItemStaled` per item
   d. Emit `TowerInitialized` (once per session, first time any T1 item is promoted)
   e. Insert T1 item
   f. Emit `TowerItemPromoted`

### `promote_to_t2(wm_item, t1_citation_id, is_pinned=False, event_log=None) → TowerItem`

Validates:
- Cited `t1_citation_id` must exist in `truth_tower_items` for this session
- Must be `tier=1`
- Must not be stale (`is_stale=False`) — **Amendment 4: born-stale rejection** — T2 items cannot cite an already-stale T1

If valid:
1. Check T2 capacity; evict lowest-salience non-pinned T2 if needed → `TowerItemEvicted`
2. Insert T2 item
3. Emit `TowerCrossReferenceAdded` (records the T1→T2 link)
4. Emit `TowerItemPromoted`

### `evict(tower_item_id, reason, event_log=None)`

Eviction of a T1 item propagates to all T2 items that cite it:
- Calls `mark_stale_from_t1_eviction(t1_item_id)` → sets `is_stale=True` on all citing T2s → emits `TowerItemStaled` per item (idempotent)
- Emits `TowerItemEvicted` for the T1 item itself

### `to_tower_field(event_log=None) → dict | None`

Returns the tower as a structured dict for inclusion in a `ContextPacket`:

```python
{
    "t1_items": [...],      # active T1 items
    "t2_items": [...],      # active T2 items
    "t1_count": N,
    "t2_count": N,
    "stale_count": N,       # stale T2 items
}
```

Returns `None` if tower is empty. Emits `TowerRendered` with `included_in_packet=True`.

### `render_chronological(event_log=None) → str`

Text render: T1 items first (sorted by `promoted_at`), then T2 items with their T1 citation. Stale T2 items marked with `[STALE]`. Emits `TowerRendered` with `included_in_packet=False`.

### WAL safety rule

In `TruthTower`, all `event_log.write()` calls happen *after* `conn.close()`. This is the WAL discipline mentioned in `03_storage_layer.md` — prevents "database is locked" when the inspector event write and the tower DB write would share the same WAL epoch.

---

## 3. ClutchEngine (`cerebra/cognition/clutch.py`)

The ClutchEngine evaluates a set of rules against the current cycle context and selects an action. It is the primary routing mechanism between cycle steps.

### ClutchDecision

```python
@dataclass(frozen=True)
class ClutchDecision:
    action: str                 # see action table below
    rule_matched: str | None    # name of the rule that fired
    escalate_to_catalyst: bool  # True when NO rule matched (default escalation)
    cascade_depth: int          # 0-indexed position of matched rule in config
```

**`escalate_to_catalyst=True`** when no rule matches. This is the default path — the Catalyst bandit selects a strategy.

### ClutchCycleState (mutable, passed per-step)

```python
@dataclass
class ClutchCycleState:
    consecutive_steps_below_floor: int
    prior_clutch_decisions: list[ClutchDecision]
    catalyst_invoked_this_step: bool
```

### Actions

| Action | Meaning |
|---|---|
| `accept` | Output is good; advance or complete |
| `refine` | Rerun current step with refinement prompt |
| `critique` | Apply critique pass before advancing |
| `explore` | Widen context or approach |
| `branch` | Fork into parallel sub-approaches |
| `retrieve_more` | Re-run retrieval with expanded query |
| `consolidate` | Merge/summarize accumulated outputs |
| `ask_user` | Pause and surface a question |
| `pause` | Halt cycle, await external input |
| `stop` | Terminate cycle (sets `explicit_stop=True` in CycleState) |

### 14 Built-in Predicates

**Phase 8 originals (6):**

| Predicate | Parameters | Logic |
|---|---|---|
| `composite_below_threshold` | `threshold: float` | `composite_score < threshold` |
| `composite_above_threshold` | `threshold: float` | `composite_score > threshold` |
| `always` | (none) | always True (catch-all rule) |
| `at_terminal_step` | (none) | `steps_run >= max_steps - 1` |
| `first_step_below_floor` | `floor: float` | `step_index == 0 AND composite < floor` |
| `composite_in_range` | `low: float, high: float` | `low ≤ composite ≤ high` |

**Phase 9 additions (8):**

| Predicate | Parameters | Logic |
|---|---|---|
| `consecutive_steps_below_floor` | `floor: float, n: int` | `consecutive_steps_below_floor >= n` |
| `prior_step_action_was` | `action: str` | previous ClutchDecision.action == action |
| `catalyst_not_invoked_recently` | `steps: int` | no catalyst in last N steps |
| `step_count_above` | `n: int` | `steps_run > n` |
| `composite_trajectory_degrading` | `window: int` | composite trend is falling over window steps |
| `epistemic_humility_low` | `threshold: float` | EPISTEMIC_HUMILITY signal score < threshold |
| `groundedness_low` | `threshold: float` | GROUNDEDNESS signal score < threshold |
| `cascade_depth_above` | `depth: int` | `cascade_depth > depth` (prevents infinite escalation) |

### Rule evaluation

Rules are evaluated in config order (the order they appear in `clutch_rules` in the cycle YAML). The first matching predicate wins. `cascade_depth` is the 0-indexed position of the matched rule.

---

## 4. CatalystEngine (`cerebra/cognition/catalyst.py`)

The CatalystEngine uses a UCB1 bandit to select the best strategy arm when ClutchEngine escalates.

### Tables

```sql
CREATE TABLE catalyst_arm_stats (
    session_id  TEXT NOT NULL,
    arm_id      TEXT NOT NULL,
    count       INT NOT NULL DEFAULT 0,
    total_reward REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (session_id, arm_id)
)

CREATE TABLE catalyst_recent_selections (
    session_id  TEXT NOT NULL,
    arm_id      TEXT NOT NULL,
    selected_at INT NOT NULL
)
```

`catalyst_recent_selections` maintains a rolling window of K=5 most recent arm selections per session.

### `select() → CatalystSelection | None`

**Selection algorithm:**

1. Load arm stats for current session (falls back to parent session stats per S4-D2 rule — see below)
2. Force unsampled arms first: if any arm has `count == 0`, select randomly from unsampled set
3. For sampled arms: compute UCB1 score per arm:
   ```
   ucb_score = mean_reward + exploration_weight × sqrt(log(total_steps + 1) / count)
   ```
   where `exploration_weight = 1.4` (from Bandit primitive default)
4. Apply penalties and ramps before final selection:
   ```
   final_score = ucb_score × type_penalty × confidence_ramp
   
   type_penalty = max(0.5, 1.0 - (count_same_arm_type_in_last_5 × 0.15))
   confidence_ramp = min(1.0, count / 5.0)
   ```
5. Select arm with highest `final_score`

**S4-D2 child session inheritance:** When a child (reinjected) session has no arm stats of its own, it inherits the parent session's arm stats. This prevents the bandit from starting cold after reinjection, preserving learned arm preferences.

### Reward update

After each cycle step, if a catalyst arm was selected:
```python
reward = packet_eval.composite_score × packet_eval.confidence
```

Upserted via `ON CONFLICT (session_id, arm_id) DO UPDATE SET count=count+1, total_reward=total_reward+?`.

### CatalystSelection

```python
@dataclass
class CatalystSelection:
    arm_id: str
    arm_type: str           # e.g. "constraint_check", "decomposition"
    strategy_prompt: str    # injected as {{ strategy_hint }} in step template
    mapped_action: str      # clutch action this arm maps to
    score: float            # final selection score
```

---

## 5. Reinjection (`cerebra/cognition/reinjection.py`)

### ReinjectionDecision

```python
@dataclass
class ReinjectionDecision:
    should_fire: bool
    trigger_name: str | None
    predicate: str | None
    blocked_reason: str | None  # "recursion_depth_exceeded" if blocked
```

### `ReinjectionTriggerEvaluator.evaluate(termination_reason, step_history, recursion_depth, max_recursion_depth) → ReinjectionDecision`

**Gate check first:** If `recursion_depth >= max_recursion_depth`: return blocked decision immediately.

**Built-in predicate (v0.1):**

`max_steps_without_acceptance` — fires when:
- `termination_reason == "cap_reached"` (cycle hit max_steps, not a natural stop)
- AND no step in `step_history` had `clutch_action == "accept"`

When fired: `CycleRuntime._try_reinject()` calls `SessionManager.open_session(parent_session_id=current_session_id)` and spawns a new child `CycleRuntime`. The child receives the parent's continuation bundle (if `BundleDistiller.distill()` was called) as a prompt prefix.

---

## 6. Continuation Bundle (`cerebra/cognition/continuation_bundle.py`)

### ContinuationBundle

```python
@dataclass(frozen=True)
class ContinuationBundle:
    bundle_id: str              # "bundle_" + uuid[:12]
    parent_session_id: str
    child_session_id: str | None    # set after child session starts
    distilled_goal: str
    summarized_prior_prompt: str
    truth_tower_projection: dict    # tower state at time of distillation
    cognitive_insights: list[str]
    next_focus: str
    open_questions: list[str]
    constraints: list[str]
    recursion_depth: int
    voice_mode: str
    bundle_size_bytes: int
    created_at: int
    triggered_at: int | None
```

### BundleDistiller

```python
class BundleDistiller:
    def distill(
        self,
        parent_session_id: str,
        goal: str,
        recursion_depth: int,
        voice_mode: str,
        step_outputs: list[str],
        tower_data: dict | None,
    ) -> ContinuationBundle
```

**v0.1 stubs:** Most summarization is shallow:
- `distilled_goal = goal` (passed through unchanged)
- `summarized_prior_prompt = goal + "\n\n" + truncated_step_outputs[:500]`
- `cognitive_insights = []`
- `open_questions = []`
- `constraints = []`
- `next_focus = ""` (empty)

Full LLM-based distillation is planned for a future phase.

### `to_prompt_prefix() → str`

Renders bundle as structured text injected at the start of the child session's first step prompt. Format: goal → prior summary → tower projection → next focus.

### Persistence helpers

```python
def write_bundle(db_path: Path, bundle: ContinuationBundle) -> None
def read_bundle(db_path: Path, bundle_id: str) -> ContinuationBundle | None
def list_bundles_for_session(db_path: Path, parent_session_id: str) -> list[ContinuationBundle]
def link_child_session(db_path: Path, bundle_id: str, child_session_id: str, triggered_at: int | None = None) -> None
```

---

## 7. Episode Writer (`cerebra/cognition/episode_writer.py`)

The EpisodeWriter persists the output of each cycle step as a durable cognitive episode.

### `write()` signature

```python
class EpisodeWriter:
    def write(
        self,
        content: str,
        runtime_session_id: str,
        cycle_id: str,
        step_id: str,
        step_name: str,
        working_memory_session_id: str | None = None,
        leeway_grant_event_id: str | None = None,
        cited_record_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str    # returns record_id = "ep_" + uuid[:12]
```

### EpisodeRecord

```python
@dataclass(frozen=True)
class EpisodeRecord:
    record_id: str                      # "ep_" + uuid[:12]
    runtime_session_id: str
    working_memory_session_id: str | None
    cycle_id: str
    step_id: str
    step_name: str
    content: str
    content_summary: str                # first 200 chars
    metadata: dict | None
    leeway_grant_event_id: str | None   # which LeewayGrant authorized this write
    cited_record_ids: list[str] | None  # rec_ IDs extracted from LLM output
    created_at: int
```

### Dual-write (Phase 10)

Each episode is written to TWO locations in the same transaction:

**Write 1:** `INSERT INTO cycle_episode_records (...)` — specialized episode table with full metadata.

**Write 2:** `INSERT OR IGNORE INTO memory_records (...)` — makes the episode visible to the retrieval pipeline. Uses synthetic provenance sentinels for FK compliance:
```python
source_id   = SYNTHETIC_SOURCE_ID    # "src_synthetic"
document_id = SYNTHETIC_DOCUMENT_ID  # "doc_synthetic"
chunk_id    = SYNTHETIC_CHUNK_ID     # "chk_synthetic"
record_type = "cycle_episode"
```

**Post-write (outside transaction):** `queue_for_embedding(db_path, [record_id])` — queues the episode for embedding. Best-effort, failure is non-fatal.

This means cycle episodes are immediately retrievable via semantic search after the next `cerebra embed` run, without any special-casing in the retrieval layer.
