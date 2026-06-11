# Phase 5 Design — Working Memory and Truth Tower

**Type:** Design doc (implementation authority)
**Date:** 2026-06-11
**Status:** Approved — implementation may begin (Step 1)
**Scope:** Working memory with named slots, truth tower T1+T2, tower-to-packet, session management, inspector events, lockfile
**Author:** Claude Code

---

## §1. Current State at Phase 4 Completion

### What shipped (v0.2.0)

| Module | Status |
|--------|--------|
| `cerebra/retrieval/` | Complete — planner, traversal, scorer, trace, context_packet |
| `cerebra/storage/` | Complete — migrations 1–8, embeddings, graph_store, index_state, lexical |
| `cerebra/inspector/` | Complete — event, sqlite_log, ndjson_log; event vocabulary needs Phase 5 extension |
| `cerebra/cognition/` | Partial — `sku_classifier.py` only; working_memory.py and truth_tower.py do not exist |
| `cerebra/cli/main.py` | 8 commands — no session, memory, or tower commands |

### What does not exist (Phase 5 targets)

```
cerebra/cognition/working_memory.py       — does not exist
cerebra/cognition/truth_tower.py          — does not exist
cerebra/cognition/_constants.py           — does not exist
```

No sessions table, no working_memory_items table, no truth_tower_items table at any migration level. Next migration is Migration009.

### Test and coverage baseline

751 tests (639 unit + 112 integration), 88.51% coverage, 0 failures. Abstention fully covered. Phase 4 complete.

### Forward-compat concept docs

Three post-v0.1 concept docs are relevant only for D12 (forward-compat column naming):
- `docs/agent/concepts/interpretive_lattice.md` — multi-commit substrate; affects chunk classification, not Phase 5
- `docs/agent/concepts/archetypal_lenses.md` — lens-driven multi-commit signal; names the `interpretive_lens` attribution concept
- `docs/agent/concepts/evaluative_frame.md` — coherence layer over lens outputs; names the `frame_metadata` concept

Neither lens nor frame architecture is implemented in Phase 5. D12 reserves nullable columns so Migration009 does not block them later.

---

## §2. D1 — Persistence Model and Session Identity

**Decision:** Working memory is persistent, stored in the vault's SQLite database. One active session per vault at a time.

**Session lifecycle:**
- Session created automatically on first write-path command invocation if no active session exists for the vault (e.g., first `cerebra context` or `cerebra memory promote`)
- `session_id` format: `sess_<12 hex chars>` (same convention as other IDs)
- Subsequent commands reuse the active session; they load it by vault_path + status='active'
- `cerebra session reset` closes the current session (status → 'closed') and creates a new one; all working_memory_items and truth_tower_items associated with the old session_id are not deleted but become inaccessible to future commands
- `cerebra session show` prints the current session_id, started_at, item count, and vault_path
- No auto-close in Phase 5 (sessions accumulate until explicit reset)

**Rejected alternatives:**
- *In-process only* — `cerebra memory promote` followed by `cerebra context` would not see the promoted item; CLI commands cannot share in-process state between invocations without a daemon
- *One session per invocation* — destroys cross-command continuity; working memory would reset on every command

**Multi-vault note:** One-active-session-per-vault is a Phase 5 simplifying assumption. Sessions are keyed by `vault_path`; two vault paths each get their own independent session with no cross-vault state. When multi-vault deployment becomes a target (Phase 6+ or v0.3), the session identity model needs revisiting — e.g., a global session registry or vault-agnostic session IDs.

**Resolves C1** (session identity: session_id generated on first invocation, reused after) and **C2** (persistent vs in-process: persistent).

---

## §3. D2 — Goal Slot Semantics and Synthetic Items

**Decision:** `record_id` is nullable on `working_memory_items`. Synthetic items (no vault record FK) are fully supported.

**Content model:**
- If `record_id` IS NOT NULL: `content_summary` holds the record's excerpt (populated from the retrieval result at promotion time, truncated to 400 chars matching `EXCERPT_MAX_CHARS`)
- If `record_id` IS NULL: `content_summary` holds free text provided by the user (e.g., `cerebra memory promote --slot goal --text "debug the retrieval pipeline"`)

**Salience for synthetic items:** defaults to 0.8 when no retrieval score is available (user-set goals are treated as high-priority). Explicit `--salience` override allowed on `cerebra memory promote`.

**Interrupt slot scope:** Phase 5 supports the `interrupt` slot (capacity=3 per `_constants.py`) and allows manual promotion into it via `cerebra memory promote --slot interrupt`. Auto-promotion — where a salience monitor surfaces high-salience contradiction candidates without an explicit user command — is deferred to v0.3+ per `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md §9` MVP scope. The slot is available; the trigger machinery is not.

**Rejected alternatives:**
- *Require record_id* — users cannot set a working goal that isn't in the vault; contradicts D5's `cerebra memory promote --text` CLI surface

**Resolves C5** (synthetic items without memory_records FK).

---

## §4. D3 — T1 Auto-Population

**Decision:** When `cerebra context` runs, its `selected_memory` items automatically promote into the current session's T1 evidence slot of the truth tower. If no active session exists, one is created.

**Mechanics:**
- After `build_context_packet()` completes, `context` command calls `promote_to_t1(session, packet.selected_memory)`
- Each selected MemoryItem becomes a `truth_tower_items` row at tier=1
- Existing T1 items from the same retrieval trace are not duplicated (idempotent by trace_id)
- If T1 is at capacity (10 items), lowest-salience existing T1 items are evicted to make room; the N items from the current context call are all inserted (N ≤ packet limit, default 10)
- A `TowerInitialized` event is emitted on first T1 population for the session; `TowerItemPromoted` events are emitted per item

**T1 accumulation vs replacement:** T1 **accumulates** across context calls within a session. Each `cerebra context` call adds new evidence; it does not wipe prior T1. Eviction enforces the capacity cap. To clear and start fresh, use `cerebra session reset`.

**Manual override:** `cerebra memory promote <record_id> --tier 1` bypasses the context command and promotes directly to T1.

**`cerebra search` does NOT modify working memory** — separation of concerns. Search is read-only relative to working memory state.

**Resolves C4** (T1 population trigger).

---

## §5. D4 — access_frequency Deferred

**Decision:** `access_frequency` salience component is deferred to Phase 6 or 7. Phase 5 working memory eviction uses the Phase 4 five-component composite score (`semantic`, `lexical`, `sku_match`, `recency`, `lifecycle`) as the salience score for items with a `record_id`.

No `access_log` table, no `last_accessed_at` or `access_count` columns on `memory_records`. No schema changes to the existing table structure.

**Rationale:** Adding `access_frequency` requires schema migration, a recording hook on every retrieval, and recalibration of the composite. Phase 5 has enough moving parts. The five-component score is sufficient for eviction ordering in the dev vault at current scale.

---

## §6. D5 — CLI Surface Scope

**Decision:** Phase 5 implements a minimal session and memory management surface. The full `cerebra inspect` family waits for Phase 6 (when the cycle runtime provides cycle_id context to make inspect queries meaningful).

**Phase 5 CLI surface (exact command list in §14):**
- `cerebra session show` — display current session
- `cerebra session reset` — close current session, create new
- `cerebra memory status` — display current slot contents (text and JSON)
- `cerebra memory promote` — manual promotion to slot or tower tier
- `cerebra memory evict` — manual eviction by item_id

**Explicitly deferred to Phase 6+:** `cerebra inspect session`, `cerebra inspect cycle`, `cerebra inspect cycle --tower`.

---

## §7. D6 — ContextPacket Schema

**Decision:** `packet_version` stays at 1. `truth_tower` is an **optional** field added to ContextPacket — present only when the current session has a populated tower, absent (key not present in JSON) when no active session exists or the tower is empty.

**Rationale:** Optional field is additive and non-breaking. Existing consumers (tests, downstream callers) that don't check for `truth_tower` continue to work. A `packet_version` bump to 2 would require every consumer to handle version branching — premature for a field that is absent in the common case.

**Test impact:** `test_abstention_against_vault.py::test_weather_context_abstained_packet_shape` asserts on a list of required fields — `truth_tower` is not in that list. No existing test changes required for D6.

**Resolves C3** (ContextPacket version strategy).

---

## §8. D7 — Migration009 Schema

### Sessions table

```sql
CREATE TABLE sessions (
    session_id       TEXT    PRIMARY KEY,
    vault_path       TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'closed')),
    started_at       INTEGER NOT NULL,
    last_active_at   INTEGER NOT NULL,
    schema_version   INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_sessions_vault_status
    ON sessions(vault_path, status);
```

One active session per vault enforced at the application layer: before creating a new session, the code closes any existing active session for the vault. No DB-level UNIQUE constraint on `(vault_path, status)` — this would complicate `session reset` atomicity.

**Delete discipline:** Cleanup is lifecycle-state-driven (`evicted_at`, `status='closed'`), never hard-delete. Closed sessions retain their items indefinitely for audit. All FK constraints across Migration009 use `ON DELETE RESTRICT` — a row in a parent table cannot be deleted while child rows reference it. This enforces the "never hard-delete" discipline at the DB layer.

### working_memory_items table

```sql
CREATE TABLE working_memory_items (
    item_id             TEXT    PRIMARY KEY,
    session_id          TEXT    NOT NULL
                                REFERENCES sessions(session_id)
                                    ON DELETE RESTRICT,
    slot_type           TEXT    NOT NULL
                                CHECK (slot_type IN (
                                    'goal', 'constraint', 'context', 'hypothesis',
                                    'evidence', 'contradiction', 'recent_output',
                                    'question', 'procedure', 'interrupt'
                                )),
    record_id           TEXT    REFERENCES memory_records(record_id)
                                    ON DELETE RESTRICT,
    content_summary     TEXT    NOT NULL,
    salience_score      REAL    NOT NULL DEFAULT 0.0,
    is_pinned           INTEGER NOT NULL DEFAULT 0,
    promoted_at         INTEGER NOT NULL,
    evicted_at          INTEGER,
    schema_version      INTEGER NOT NULL DEFAULT 1,
    interpretive_lens   TEXT,
    frame_metadata_json TEXT
);

CREATE INDEX idx_wmi_session_slot
    ON working_memory_items(session_id, slot_type)
    WHERE evicted_at IS NULL;

CREATE INDEX idx_wmi_session_active
    ON working_memory_items(session_id)
    WHERE evicted_at IS NULL;
```

**Notes:**
- `record_id` nullable per D2
- `interpretive_lens` and `frame_metadata_json` are D12 forward-compat columns, always NULL in Phase 5
- `is_tower_cited` column removed (amendment 3): tower-citation status is computed on demand via JOIN to `truth_tower_items` — at Phase 5 scale (≤34 WM items, ≤15 tower items per session) the join is trivially cheap and eliminates the consistency question entirely
- Partial indexes on `WHERE evicted_at IS NULL` are the hot-path queries; evicted items are never in the active set

### truth_tower_items table

Two tiers (T1, T2) are stored in one table with a `tier` column. Separate tables would require UNION queries for cross-tier operations (especially T2→T1 citation checks); one table keeps joins simple.

```sql
CREATE TABLE truth_tower_items (
    tower_item_id       TEXT    PRIMARY KEY,
    session_id          TEXT    NOT NULL
                                REFERENCES sessions(session_id)
                                    ON DELETE RESTRICT,
    tier                INTEGER NOT NULL CHECK (tier IN (1, 2)),
    wm_item_id          TEXT    REFERENCES working_memory_items(item_id)
                                    ON DELETE RESTRICT,
    record_id           TEXT    REFERENCES memory_records(record_id)
                                    ON DELETE RESTRICT,
    retrieval_trace_id  TEXT    REFERENCES retrieval_traces(trace_id)
                                    ON DELETE RESTRICT,
    content_summary     TEXT    NOT NULL,
    salience_score      REAL    NOT NULL,
    sku_address         TEXT,
    t1_citation_id      TEXT    REFERENCES truth_tower_items(tower_item_id)
                                    ON DELETE RESTRICT,
    is_pinned           INTEGER NOT NULL DEFAULT 0,
    is_stale            INTEGER NOT NULL DEFAULT 0,
    promoted_at         INTEGER NOT NULL,
    evicted_at          INTEGER,
    schema_version      INTEGER NOT NULL DEFAULT 1,
    CHECK ((tier = 1 AND t1_citation_id IS NULL) OR (tier = 2 AND t1_citation_id IS NOT NULL))
);

CREATE INDEX idx_tti_session_tier
    ON truth_tower_items(session_id, tier)
    WHERE evicted_at IS NULL;

CREATE INDEX idx_tti_t1_citation
    ON truth_tower_items(t1_citation_id)
    WHERE evicted_at IS NULL;
```

**Notes:**
- T1 items: `wm_item_id` typically NULL (T1 populates directly from retrieval); `retrieval_trace_id` set to the trace that surfaced this item; `t1_citation_id` always NULL (enforced by table CHECK constraint)
- T2 items: `wm_item_id` set (T2 promotes from working memory); `t1_citation_id` NOT NULL (enforced by table CHECK constraint); `retrieval_trace_id` NULL
- Tower-citation status for a working memory item is computed on demand: `SELECT 1 FROM truth_tower_items WHERE wm_item_id = ? AND evicted_at IS NULL LIMIT 1` — no denormalized column
- The `idx_tti_t1_citation` index enables efficient staleness propagation: when a T1 item is evicted, find all T2 items that cite it in one query

### Capacity constants (enforced at application layer)

| Tier | Capacity |
|------|----------|
| T1   | 10       |
| T2   | 5        |

Slot capacity constants live in `cerebra/cognition/_constants.py` (see §9).

### Idempotency

All session creation uses `INSERT OR IGNORE` patterns. Working memory item promotion checks for duplicate `(session_id, record_id, slot_type)` with `evicted_at IS NULL` before inserting. Tower item promotion checks for duplicate `(session_id, record_id, tier)` with `evicted_at IS NULL`.

### Migration structure

Migration009 adds all three tables in a single migration. No other schema changes. Forward-only invariant: if the ContextPacket schema later needs a `packet_version=2` column, that is Migration010+.

---

## §9. D8 — Slot Capacity Constants

### Where they live

```python
# cerebra/cognition/_constants.py
SLOT_CAPACITIES: dict[str, int] = {
    "goal":           1,
    "constraint":     4,
    "context":        7,
    "hypothesis":     3,
    "evidence":       5,
    "contradiction":  2,
    "recent_output":  2,
    "question":       3,
    "procedure":      4,
    "interrupt":      3,
}
SLOT_CAPACITY_TOTAL = 34

TOWER_CAPACITIES: dict[int, int] = {
    1: 10,  # T1 source-grounded evidence
    2: 5,   # T2 high-salience memories
}

SYNTHETIC_ITEM_DEFAULT_SALIENCE = 0.8
```

**Compile-time only in Phase 5.** No runtime config override, no `cerebra config set slot.goal.capacity` in Phase 5. Per-cycle overrides (mentioned in `CEREBRA_DRIFT_FIXES_v8.1.md §1`) are a Phase 8+ concern when the cycle runtime is built. Keeping them compile-time constants simplifies the eviction logic considerably.

### Doc patch

The patch specified in `CEREBRA_DRIFT_FIXES_v8.1.md §1` must be applied to `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md §4` as a task in Phase 5 Step 1. The patch adds subsection `4.1 Default Slot Capacities` with the capacity table and eviction policy. This is a doc change, not a code change — applied alongside Migration009 in Step 1 so the authoritative doc matches the implementation from the start.

---

## §10. D9 — Eviction Policy and Salience

### Salience score per item

| Item type | Salience source |
|-----------|-----------------|
| Record-backed (record_id NOT NULL) | Phase 4 composite score from the retrieval that surfaced it, stored in `salience_score` at promotion time |
| Synthetic (record_id IS NULL) | `SYNTHETIC_ITEM_DEFAULT_SALIENCE` (0.8) unless `--salience` override provided |
| Tower T1 item | Inherits from the retrieval composite score via the source `memory_records` row — same five-component score used for WM items |
| Tower T2 item | Inherits from the `working_memory_items.salience_score` of the `wm_item_id` it was promoted from |

Salience scores are **frozen at promotion time**. They do not update on subsequent retrievals. `access_frequency` would enable dynamic updates; that is deferred (D4).

### Eviction ordering

When a slot is at capacity and a new item arrives:

1. **User-pinned items (`is_pinned=1`):** non-evictable. Never displaced.
2. **Tower-cited items (active T2 row via JOIN):** eviction-resistant. For comparison purposes, treat their effective salience as `salience_score + 0.20`. This penalty is applied only during eviction candidate selection, not stored.
3. **Lowest effective-salience non-pinned item evicted first.**
4. **Tie-breaker:** oldest `promoted_at` evicts first.

### Tower-citation check at eviction time

Before completing eviction of a working memory item, check whether any active T2 tower item cites it:

```sql
SELECT 1 FROM truth_tower_items
WHERE wm_item_id = ? AND evicted_at IS NULL LIMIT 1
```

If found, apply the eviction-resistance penalty. Uses `idx_tti_t1_citation` and the session partial index — not expensive at Phase 5 scale.

### When eviction triggers

Eviction runs **at promotion time** when the slot is over capacity after insertion. Not on a separate background sweep. The sequence:

```
1. Insert new item into slot (optimistically)
2. Count active items in slot
3. If count > capacity: run eviction to remove lowest-effective-salience item
4. Emit AttentionItemEvicted for evicted item
5. Emit AttentionItemPromoted for new item
```

Tower eviction follows the same pattern when T1 or T2 is at capacity.

---

## §11. D10 — Truth Tower T1+T2 Implementation

### T1 population

Automatic via `cerebra context` (D3). `promote_to_t1(session_id, memory_items, trace_id)` is called in the `context` CLI command after `build_context_packet()` returns. Each `MemoryItem` in `selected_memory` becomes a `truth_tower_items` row at tier=1.

T1 accumulates across context calls. Eviction enforces the 10-item cap per the eviction policy in D9. Items from the same retrieval trace are idempotent (re-running `cerebra context` with the same query does not duplicate T1 items).

### T2 promotion

**Manual-only in Phase 5.** No automatic T2 promotion based on salience thresholds alone. The user explicitly issues `cerebra memory promote <record_id> --tier 2` or `cerebra memory promote --item-id <wm_item_id> --tier 2`.

**T2 citation requirement:** Every T2 item must cite a T1 item. The `--cite <tower_item_id>` flag is required when promoting to T2 unless `--pin` is set (user-pinned T2 items are exempt from the citation requirement in Phase 5). Validation at CLI layer; exits 2 if the cited item is not a T1 item in the current session. **Born-stale rejection:** if the cited T1 item has `evicted_at IS NOT NULL`, the promote is rejected with exit 2 and the message `"Cannot promote to T2: cited T1 item <id> was evicted at <timestamp>. Promote a current T1 first."` A `--allow-stale` flag may be added in a future pass if there is a valid use case.

**Salience threshold:** Not enforced programmatically in Phase 5 (manual-only means the user decides when something is T2-worthy). The threshold documented in `CEREBRA_TRUTH_TOWER.md §11` (`salience ≥ 0.5 AND cited ≥ 1 T1`) is design intent for auto-promotion, which is Phase 6 territory.

**Rejected alternative:** *Auto-promotion based on salience ≥ 0.5* — introduces complex trigger semantics (on every context call? on session reset?) without a clear cycle runtime to anchor it. Manual-only is safe and testable.

### Staleness in Phase 5

When a T1 item is evicted, all T2 items citing it (via `t1_citation_id`) are marked `is_stale=1` and `TowerItemStaled` events are emitted. **Staleness does not cascade further in Phase 5** (no T3/T4 exist). Stale T2 items remain visible in `cerebra memory status --tower` output, labeled `[stale]`. They are not automatically evicted or rebuilt. `REBUILD` and `COLLAPSE` operations (and their events `TowerTierRebuilt`, `TowerCollapsed`) are Phase 6 territory; the events are defined in the vocabulary but never emitted in Phase 5.

### Render format

One format in Phase 5: **chronological**. Items rendered T1-first (oldest to newest promoted_at within each tier), then T2 items each immediately following the T1 item they cite.

```
T1 [1] refined-runtime-model/CEREBRA_LEEWAY_NETWORK.md  | score: 0.47 | trace: trace_abc
       The leeway network is Cerebra's permissions-shaped safety…
T1 [2] refined-runtime-model/CEREBRA_DRIFT_FIXES_v8.1.md | score: 0.63 | trace: trace_def
       Working memory slot capacity defaults…
  T2 [1] ^T1[2]  refined-runtime-model/CEREBRA_DRIFT_FIXES_v8.1.md | score: 0.63
         Working memory slot capacity defaults…
```

---

## §12. D11 — Inspector Event Payloads

### Event type registration

Phase 5 formalizes `PHASE_5_EVENT_TYPES` as a frozenset in `cerebra/inspector/event.py`, following the existing `PHASE_0_EVENT_TYPES` pattern. An `ALL_KNOWN_EVENT_TYPES` union of both is exported for callers that want to validate.

```python
PHASE_5_EVENT_TYPES: frozenset[str] = frozenset({
    "WorkingMemoryCreated", "AttentionItemProposed", "AttentionItemPromoted",
    "AttentionItemEvicted", "AttentionItemDeferred", "InterruptCandidateCreated",
    "WorkingMemoryRendered", "WorkingMemoryCleared",
    "TowerInitialized", "TowerItemPromoted", "TowerItemEvicted",
    "TowerCrossReferenceAdded", "TowerItemStaled", "TowerTierRebuilt",
    "TowerCollapsed", "TowerRendered",
})

ALL_KNOWN_EVENT_TYPES = PHASE_0_EVENT_TYPES | PHASE_5_EVENT_TYPES
```

`make_event()` continues to accept any event_type string (no runtime validation against the frozenset). The frozensets are informational and for tooling.

### Working Memory event payloads

All working memory events use `subject_id = session_id` except item-level events which use `subject_id = item_id`.

**WorkingMemoryCreated**
```python
subject_id = session_id
data = {
    "session_id": str,
    "vault_path": str,
    "started_at": int,
}
```

**AttentionItemProposed** *(item arrived for consideration, not yet accepted)*
```python
subject_id = item_id
data = {
    "session_id": str,
    "item_id": str,
    "slot_type": str,
    "record_id": str | None,
    "content_summary": str,
    "salience_score": float,
    "source": str,  # "context_auto" | "manual_promote"
}
```

**AttentionItemPromoted** *(item accepted into a slot)*
```python
subject_id = item_id
data = {
    "session_id": str,
    "item_id": str,
    "slot_type": str,
    "salience_score": float,
    "record_id": str | None,
    "eviction_triggered": bool,  # True if promoting caused an eviction
    "evicted_item_id": str | None,
}
```

**AttentionItemEvicted**
```python
subject_id = item_id
data = {
    "session_id": str,
    "item_id": str,
    "slot_type": str,
    "salience_score": float,
    "eviction_reason": str,  # "capacity" | "explicit"
    "was_tower_cited": bool,  # computed at eviction time via JOIN; not a stored column
}
```

**AttentionItemDeferred** *(proposed but not accepted due to low salience or slot pressure)*
```python
subject_id = item_id
data = {
    "session_id": str,
    "item_id": str,
    "slot_type": str,
    "salience_score": float,
    "defer_reason": str,  # "below_threshold" | "slot_full_pinned"
}
```

**InterruptCandidateCreated**
```python
subject_id = item_id
data = {
    "session_id": str,
    "item_id": str,
    "record_id": str | None,
    "salience_score": float,
    "interrupt_reason": str,  # free text, e.g. "high salience contradiction"
}
```

**WorkingMemoryRendered**
```python
subject_id = session_id
data = {
    "session_id": str,
    "total_item_count": int,
    "slot_summary": dict[str, int],  # {slot_type: count, ...}
    "render_format": str,            # "text" | "json"
}
```

**WorkingMemoryCleared**
```python
subject_id = session_id
data = {
    "session_id": str,
    "items_cleared": int,
    "reason": str,  # "session_reset" | "explicit"
}
```

### Truth Tower event payloads

**TowerInitialized** *(first T1 item lands in a session)*
```python
subject_id = session_id
data = {
    "session_id": str,
    "tier": 1,
    "t1_capacity": int,   # 10
    "t2_capacity": int,   # 5
}
```

**TowerItemPromoted**
```python
subject_id = tower_item_id
data = {
    "session_id": str,
    "tower_item_id": str,
    "tier": int,              # 1 or 2
    "record_id": str | None,
    "salience_score": float,
    "t1_citation_id": str | None,  # set for T2 items
    "retrieval_trace_id": str | None,  # set for T1 items
    "source": str,            # "context_auto" | "manual_promote"
}
```

**TowerItemEvicted**
```python
subject_id = tower_item_id
data = {
    "session_id": str,
    "tower_item_id": str,
    "tier": int,
    "salience_score": float,
    "eviction_reason": str,   # "capacity" | "explicit"
    "stale_t2_count": int,    # T2 items marked stale as a result (T1 eviction only)
}
```

**TowerCrossReferenceAdded** *(T2 item cites a T1 item)*
```python
subject_id = higher_item_id  # the T2 item
data = {
    "session_id": str,
    "higher_item_id": str,    # T2
    "higher_tier": 2,
    "lower_item_id": str,     # T1
    "lower_tier": 1,
}
```

**TowerItemStaled** *(T1 evicted; T2 citing it marked stale)*
```python
subject_id = staled_item_id  # the T2 item being staled
data = {
    "session_id": str,
    "staled_item_id": str,
    "tier": 2,
    "stale_reason": str,  # "t1_evicted"
    "evicted_t1_id": str,
}
```

**TowerTierRebuilt** *(Phase 6+ — defined but never emitted in Phase 5)*
```python
subject_id = session_id
data = {
    "session_id": str,
    "tier": int,
    "items_retained": int,
    "items_purged": int,
}
```

**TowerCollapsed** *(Phase 6+ — defined but never emitted in Phase 5)*
```python
subject_id = session_id
data = {
    "session_id": str,
    "tiers_cleared": list[int],
    "items_cleared": int,
    "reason": str,
}
```

**TowerRendered**
```python
subject_id = session_id
data = {
    "session_id": str,
    "t1_count": int,
    "t2_count": int,
    "stale_count": int,
    "render_format": str,  # "chronological"
    "token_estimate": int,
    "included_in_packet": bool,
}
```

---

## §13. D12 — Forward-Compat Columns

Two nullable columns are reserved on `working_memory_items` at Migration009 time. Both are always NULL in Phase 5. They cost nothing now and avoid a schema migration later.

| Column | Type | Purpose |
|--------|------|---------|
| `interpretive_lens TEXT` | nullable | Future attribution of which archetypal lens produced or influenced this item; populated by the lens system in post-v0.1 work |
| `frame_metadata_json TEXT` | nullable | Future evaluative frame metadata as JSON; populated by the evaluative frame coherence layer in post-v0.1 work |

These columns are defined in the `working_memory_items` CREATE TABLE in §8. They are not referenced in any Phase 5 code path.

**Why not on `truth_tower_items`?** Tower items derive from working memory items or from retrieval; their lens/frame attribution propagates through the `wm_item_id` FK. No forward-compat columns needed on the tower table.

---

## §14. D13 — CLI Commands

### `cerebra session`

```
cerebra session show
  Print current session: session_id, vault_path, status, started_at,
  last_active_at, working_memory item count, tower item counts (T1, T2).
  Exit 0. If no active session: "No active session for this vault."

cerebra session reset
  Close current session (status → 'closed'). Create new session.
  Acquires lockfile (D15).
  Print: "Session <old_id> closed. New session: <new_id>"
  Exit 0.
```

### `cerebra memory`

```
cerebra memory status [--format text|json]
  Print current working memory: slot contents, item count per slot,
  pinned items marked, stale items marked.
  Tower summary appended (T1/T2 counts, stale count).
  Does NOT acquire lockfile (read-only).
  Exit 0. If no active session: "No active session."

cerebra memory promote <record_id>
  Promote a vault record to working memory.
  [--slot SLOT_TYPE]     required if record is ambiguous; prompted if omitted
  [--tier 1|2]           promote directly to tower tier (bypasses slot)
  [--cite TOWER_ITEM_ID] required when --tier 2
  [--pin]                mark item non-evictable
  [--salience FLOAT]     override salience (default: from retrieval score)
  [--text "free text"]   promote a synthetic item (no record_id); requires --slot
  Acquires lockfile. Exit 0 on success, exit 2 on error.

cerebra memory evict <item_id>
  Evict a specific item from working memory or tower by item_id.
  item_id can be a wm_item_id (wmi_*) or tower_item_id (tti_*).
  Acquires lockfile. Exit 0 on success, exit 2 on error.
```

### Integration with existing commands

`cerebra context` — modified to call `promote_to_t1()` after packet build. Auto-creates session if none exists. Acquires lockfile.

`cerebra search` — no change. Does not interact with working memory.

`cerebra init`, `cerebra ingest`, `cerebra classify`, `cerebra reindex`, `cerebra config` — no change. Do not interact with working memory or tower.

---

## §15. D14 — Tower Render in ContextPacket

### When the field appears

`truth_tower` is present in the `context` output JSON **only** when:
- An active session exists for the vault, AND
- The tower has at least one non-evicted, non-stale item (T1 or T2)

If either condition is false, the `truth_tower` key is absent from the packet JSON. It is never `null` — absent vs present is the contract.

### Field schema

```json
"truth_tower": {
  "session_id":     "sess_abc123def456",
  "rendered_at":    1750000000,
  "render_format":  "chronological",
  "t1_count":       3,
  "t2_count":       1,
  "stale_count":    0,
  "items": [
    {
      "tower_item_id":       "tti_aabbccdd0011",
      "tier":                1,
      "content_summary":     "The leeway network is Cerebra's…",
      "salience_score":      0.472585,
      "record_id":           "rec_2eeeb3be9f63",
      "sku_address":         "500000.2B.00",
      "retrieval_trace_id":  "trace_bd1cc3ab4b7a",
      "t1_citation_id":      null,
      "is_stale":            false,
      "is_pinned":           false
    },
    {
      "tower_item_id":       "tti_11223344aabb",
      "tier":                2,
      "content_summary":     "Working memory slot capacity defaults…",
      "salience_score":      0.631653,
      "record_id":           "rec_2abba7320d64",
      "sku_address":         "E00000.04.00",
      "retrieval_trace_id":  null,
      "t1_citation_id":      "tti_aabbccdd0011",
      "is_stale":            false,
      "is_pinned":           false
    }
  ]
}
```

### Token estimation

Tower token estimate = `sum(len(item["content_summary"]) for item in items) // 4 + 20` (20-token overhead for the envelope fields). This is added to the packet's `token_estimate` field so the total reflects the full render cost to a downstream LLM consumer.

### Abstained packets

Abstained ContextPackets never include a `truth_tower` field, even if a session exists. The tower is not relevant to an abstention response.

### `render_text()` update

The existing `render_text()` in `context_packet.py` gains a tower section appended after the selected memory block:

```
Truth Tower (T1: 3 items, T2: 1 item)
  T1 [1] refined-runtime-model/CEREBRA_LEEWAY_NETWORK.md  | score: 0.47
         The leeway network is Cerebra's permissions-shaped safety…
  T1 [2] refined-runtime-model/CEREBRA_DRIFT_FIXES_v8.1.md | score: 0.63
         Working memory slot capacity defaults…
    T2 [1] ^T1[2]  | score: 0.63
           Working memory slot capacity defaults…
  T1 [3] ...
```

Section is omitted entirely if `truth_tower` field is absent from the packet.

---

## §16. D15 — Lockfile Integration

### Background

Phase 3 §7 Q2 specified `.cerebra.lock`. Phase 4 never implemented it. `TestVaultLockfile` in `test_phase4_e2e.py` is explicitly skipped with a gap note. Phase 5 adds write-path session and working memory commands, making the lock worthwhile.

### Lock path

`{vault_root}/.cerebra.lock`

### Commands that acquire the lock

| Command | Acquires lock? | Reason |
|---------|---------------|--------|
| `cerebra context` | Yes | Writes to truth_tower_items |
| `cerebra session reset` | Yes | Writes to sessions, clears items |
| `cerebra memory promote` | Yes | Writes to working_memory_items or truth_tower_items |
| `cerebra memory evict` | Yes | Writes to working_memory_items or truth_tower_items |
| `cerebra search` | No | Read-only; no working memory writes |
| `cerebra memory status` | No | Read-only |
| `cerebra session show` | No | Read-only |
| `cerebra init`, `cerebra ingest`, etc. | No | Unchanged from Phase 4 |

### Lock behavior

```python
# Acquire: open exclusive, non-blocking
# On contention: exit 2 with message "Vault is locked by another process. Try again."
# Release: always in finally block, delete lockfile
```

Implementation via `fcntl.flock(LOCK_EX | LOCK_NB)` on Linux (same process locks are reentrant — not a problem since CLI commands are single-invocation). Timeout: immediate (non-blocking). Stale lock detection: check if the locking PID is alive; if not, remove stale lock and re-acquire.

### Phase 4 skipped test

`TestVaultLockfile` in `test_phase4_e2e.py` has `pytest.skip("lockfile not implemented")`. Phase 5 Step 11 unskips it and implements the test body: two sequential processes, second should get a contention message and exit 2.

---

## §17. Module Structure

```
cerebra/cognition/
    __init__.py               (existing — no changes)
    sku_classifier.py         (existing — no changes)
    _constants.py             (new)   — slot capacities, tower capacities, salience defaults
    working_memory.py         (new)   — WorkingMemoryItem, WorkingMemory class
    truth_tower.py            (new)   — TowerItem, TruthTower class

cerebra/storage/
    migrations.py             (extend) — Migration009

cerebra/inspector/
    event.py                  (extend) — PHASE_5_EVENT_TYPES, ALL_KNOWN_EVENT_TYPES

cerebra/cli/
    main.py                   (extend) — session, memory commands; hook context for T1 auto-pop
```

### `working_memory.py` public interface

```python
class WorkingMemoryItem:
    item_id: str
    session_id: str
    slot_type: str
    record_id: str | None
    content_summary: str
    salience_score: float
    is_pinned: bool
    promoted_at: int
    evicted_at: int | None

class WorkingMemory:
    def __init__(self, db_path: Path, session_id: str): ...
    def promote(self, slot_type, record_id, content_summary, salience_score,
                is_pinned, event_log) -> WorkingMemoryItem: ...
    def evict(self, item_id, reason, event_log) -> None: ...
    def load_slot(self, slot_type) -> list[WorkingMemoryItem]: ...
    def load_all_active(self) -> dict[str, list[WorkingMemoryItem]]: ...
    def render_text(self) -> str: ...
    def to_dict(self) -> dict: ...

def new_session(db_path: Path, vault_path: str, event_log) -> str: ...  # returns session_id
def get_active_session(db_path: Path, vault_path: str) -> str | None: ...
def close_session(db_path: Path, session_id: str, event_log) -> None: ...
```

### `truth_tower.py` public interface

```python
class TowerItem:
    tower_item_id: str
    session_id: str
    tier: int
    wm_item_id: str | None
    record_id: str | None
    retrieval_trace_id: str | None
    content_summary: str
    salience_score: float
    sku_address: str | None
    t1_citation_id: str | None
    is_pinned: bool
    is_stale: bool
    promoted_at: int
    evicted_at: int | None

class TruthTower:
    def __init__(self, db_path: Path, session_id: str): ...
    def promote_to_t1(self, memory_items, trace_id, event_log) -> list[TowerItem]: ...
    def promote_to_t2(self, wm_item, t1_citation_id, is_pinned, event_log) -> TowerItem: ...
    def evict(self, tower_item_id, reason, event_log) -> None: ...
    def load_tier(self, tier) -> list[TowerItem]: ...
    def mark_stale_from_t1_eviction(self, t1_item_id, event_log) -> int: ...  # returns count
    def render_chronological(self) -> str: ...
    def to_tower_field(self) -> dict | None: ...  # None if tower is empty
```

---

## §18. Open Questions and Risks

**R1 — T1 accumulation semantics across context calls.** D3 specifies T1 accumulates; eviction enforces the 10-item cap. If the user runs `cerebra context` with different queries in the same session, T1 fills with items from multiple retrieval traces. This may dilute the tower's coherence — T1 becomes "everything I've retrieved" rather than "what I'm currently working with." Mitigation for Phase 5: document this behavior in CLI help text. Phase 6 can add `cerebra context --replace-t1` to clear-and-repopulate.

**R2 — Lockfile on Linux only.** `fcntl.flock` is POSIX; Windows support is deferred (Cerebra's target is the dev machine, Linux). If Tauri Windows compatibility is needed later, a cross-platform lock library is required. Flagged here to avoid surprise.

**R3 — Multiple vaults, one active session each.** Sessions are keyed by `vault_path`. Two different vault paths each get their own session. No ambiguity, but `session show` and `memory status` must always receive a `--vault` path (the existing `_get_vault()` function handles this — no new behavior needed).

**R4 — Stale T2 items in tower render.** Stale items appear in `cerebra memory status --tower` with `[stale]` label but are still included in the tower render for `cerebra context`. This is intentional (they retain informational value) but may produce confusing output. A `--skip-stale` flag on render is a Phase 6 option.

**R5 — T2 citation requirement enforcement.** When promoting to T2, the CLI validates that the cited `t1_citation_id` belongs to the current session, is a tier-1 item, and is **not evicted** (`evicted_at IS NULL`). If the cited T1 item was evicted, the promote is rejected with exit 2: `"Cannot promote to T2: cited T1 item <id> was evicted at <timestamp>. Promote a current T1 first."` Born-stale T2 items are not a valid state in Phase 5 — the validation ensures the T2 citation is always live at creation time. A `--allow-stale` flag is reserved for a future pass if a valid use case emerges.

---

## §19. Phase 5 Task Ordering

Demo-critical path: `cerebra context` auto-populates T1 → `cerebra memory status` shows it → `cerebra memory promote --tier 2` adds T2 → second `cerebra context` call includes tower in packet. All other features serve that path.

### Step 1 — Foundation (schema + constants + doc patch)
- Migration009: sessions, working_memory_items, truth_tower_items tables
- `cerebra/cognition/_constants.py`: slot and tower capacity constants
- Apply DRIFT_FIXES §1 patch to `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md §4`
- `PHASE_5_EVENT_TYPES` frozenset in `cerebra/inspector/event.py`
- Tests: migration idempotency, table structure, FK constraints, constants module

### Step 2 — Session management
- `new_session()`, `get_active_session()`, `close_session()` in `working_memory.py`
- `cerebra session show` and `cerebra session reset` CLI commands
- Lockfile implementation (`fcntl.flock`; stale lock detection)
- Tests: session creation, reset, show, lockfile contention (unskips `TestVaultLockfile`)

### Step 3 — Working memory core
- `WorkingMemoryItem` dataclass, `WorkingMemory` class
- `promote()` with eviction logic (capacity check → eviction ordering → insert)
- `evict()` (explicit), `load_slot()`, `load_all_active()`
- Inspector event emission: AttentionItemProposed, AttentionItemPromoted, AttentionItemEvicted
- `WorkingMemoryCreated` on new session creation
- Tests: capacity enforcement per slot, eviction ordering (pinned, tower-cited, salience, age), synthetic items, inspector events

### Step 4 — Working memory CLI
- `cerebra memory status` (text + JSON)
- `cerebra memory promote` (record-backed and synthetic `--text`)
- `cerebra memory evict`
- Tests: CLI smoke tests against dev vault, `WorkingMemoryRendered` event on status

### Step 5 — Truth tower core
- `TowerItem` dataclass, `TruthTower` class
- `promote_to_t1()` (batch, from context output), `promote_to_t2()` (manual, with citation)
- T1 eviction at capacity; T2 staleness on T1 eviction
- `mark_stale_from_t1_eviction()`, `load_tier()`, `to_tower_field()`
- Inspector events: TowerInitialized, TowerItemPromoted, TowerItemEvicted, TowerCrossReferenceAdded, TowerItemStaled
- Tests: T1 populates from MemoryItems, T2 requires T1 citation, capacity caps, staleness propagation, eviction policy, events

### Step 6 — `cerebra context` T1 auto-population
- Hook `promote_to_t1()` into the context CLI command after `build_context_packet()`
- Session auto-creation on first context invocation
- `truth_tower` field added to ContextPacket output (optional per D6)
- `render_text()` in context_packet.py gains tower section
- Tests: vault integration — context call populates T1, JSON output contains truth_tower, text output shows tower section, abstained packet has no truth_tower

### Step 7 — `cerebra memory promote --tier` for T2
- `--tier 1|2` flag on `cerebra memory promote`
- `--cite <tower_item_id>` required for T2
- `TowerCrossReferenceAdded` event
- Tests: T2 promotion via CLI, born-stale T2 (cited T1 already evicted), citation validation

### Step 8 — Integration and tower status in `cerebra memory status`
- `cerebra memory status --tower` shows T1/T2 contents with stale indicators
- End-to-end vault test: full workflow (context → T1 → promote T2 → second context → tower in packet)
- Update `test_phase4_e2e.py::TestVaultLockfile` (unskip)
- Coverage check (target: maintain ≥ 88%)

**Time estimate per roadmap:** 2–3 days.

---

*Design approved ____. §8 (Migration009 schema), §11 (Truth Tower T1+T2), §15 (tower render in ContextPacket), and §19 (task ordering) are the STOP gate review sections. No Phase 5 implementation begins before review is complete.*
