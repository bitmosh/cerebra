# Phase 5 Needs Assessment — Working Memory and Attention

**Type:** Needs assessment (not a design doc)  
**Date:** 2026-06-10  
**Scope:** Investigation and inventory only. No design decisions, no implementation, no architectural commitments. "What exists, what's needed, what's unclear."  
**Author:** Claude Code  

---

## §1. Current State at Phase 4 Completion

### Schema (applied migrations 1–8)

| Migration | Tables created |
|-----------|---------------|
| 001 | `inspector_events`, `applied_migrations` |
| 002 | `sources`, `documents`, `chunks`, `memory_records` |
| 003 | rename `parse_warnings_json` → `parse_warnings` |
| 004 | `sku_assignments` |
| 005 | add `pass_count` to `sku_assignments` |
| 006 | `embeddings`, `pending_embeddings`, `index_state`, `graph_nodes`, `graph_edges` |
| 007 | seed `index_state`, queue active records into `pending_embeddings` |
| 008 | `retrieval_traces`, `retrieval_steps`, `retrieval_candidates` |

No working memory, attention, or truth tower tables exist at any migration level.

### CLI commands (as of v0.1.6)

```
cerebra init
cerebra ingest
cerebra config set/get
cerebra status
cerebra classify
cerebra search
cerebra context
cerebra reindex
```

No working memory commands. No inspect commands. No promote/evict commands.

### Event types currently emitted

Phase 0 (registered in `PHASE_0_EVENT_TYPES`): SystemInitialized, VaultCreated, MigrationRun, ConfigLoaded, LeewayRuleLoaded, ConstitutionalBlock.

Phase 4 (added without extending PHASE_0_EVENT_TYPES): QueryReceived, QueryPlanned, TraversalStepCompleted, SalienceScored, ContextPacketBuilt, RetrievalAbstained, StalenessDetected.

Phase 5 target events (from `CEREBRA_INSPECTOR.md §5.3–5.4`): WorkingMemoryCreated, AttentionItemProposed, AttentionItemPromoted, AttentionItemEvicted, AttentionItemDeferred, InterruptCandidateCreated, WorkingMemoryRendered, WorkingMemoryCleared, TowerInitialized, TowerItemPromoted, TowerItemEvicted, TowerCrossReferenceAdded, TowerItemStaled, TowerTierRebuilt, TowerCollapsed, TowerRendered.

None of the Phase 5 target events are registered or emitted.

### Modules

```
cerebra/
  retrieval/     planner, traversal, scorer, context_packet, trace  ← complete
  storage/       migrations, embeddings, graph_store, index_state, lexical  ← complete
  inspector/     event, sqlite_log, ndjson_log  ← complete; event vocabulary needs extending
  cognition/     sku_classifier  ← not Phase 5 scope
  cli/           main.py  ← all commands live here
```

No `cerebra/cognition/working_memory.py` or `cerebra/cognition/truth_tower.py` modules exist. The `cerebra/cognition/` package already exists (`sku_classifier.py` lives there).

### Test baseline

751 tests collected (639 unit + 112 integration). Coverage 88.51%. Abstention path fully covered by Step 10. Phase 4 complete at v0.2.0.

---

## §2. Phase 5 Deliverables

Source: `CEREBRA_DEV_ROADMAP_v8.1.md` §Phase 5, cross-referenced against `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md §13` and `CEREBRA_TRUTH_TOWER.md §15`.

### Module deliverables

| Module | Description |
|--------|-------------|
| `cerebra/cognition/working_memory.py` | Named slots, slot capacity caps, promotion/eviction logic |
| `cerebra/cognition/truth_tower.py` | T1 + T2 only; PROMOTE, manual EVICT, chronological render |

The roadmap names these explicitly (Phase 5 tasks 1 and 5). `cerebra/cognition/` already exists — no new package setup needed.

### Functional deliverables

1. Working memory tracks active items in 10 named slot types (goal, constraint, context, hypothesis, evidence, contradiction, recent_output, question, procedure, interrupt)
2. Capacity caps enforced per slot type (total 34 items across all slots)
3. Eviction policy: user-pinned non-evictable → truth-tower-cited eviction-resistant → lowest-salience evicted → tie=oldest
4. T1 populated from retrieval results (ContextPacket `selected_memory` → T1 evidence items)
5. T2 promotes with salience threshold + T1 citation requirement
6. Tower renders to ContextPacket (chronological format, one format only)
7. Inspector events emit for all working memory and tower operations
8. Tests cover capacity enforcement, promotion logic, eviction, tower render

### Done-when criteria (from roadmap)

- Working memory tracks active goal/constraints/context/recent outputs
- Capacity caps enforced
- T1 from retrieval; T2 promotes with salience threshold + citation
- Tower renders to ContextPacket
- Events emit
- Tests cover capacity, promotion, eviction

---

## §3. Inventory by Area

### Area 1 — Working Memory Storage

**What exists:** Nothing. No table, no module, no schema.

**What Phase 5 needs:** A `working_memory_items` table (or equivalent). Minimum fields:
- `item_id` — primary key
- `session_id` — links to the cycle/session this working memory belongs to
- `slot_type` — one of the 10 named types
- `record_id` — FK to `memory_records` (or null for synthetic items like goals)
- `content_summary` — short text for render
- `salience_score` — float, used for eviction ordering
- `is_pinned` — boolean, non-evictable flag
- `is_tower_cited` — boolean, eviction-resistant flag
- `promoted_at` — epoch timestamp
- `evicted_at` — nullable epoch timestamp
- `schema_version`

**Gap:** Requires Migration009. No design decision exists yet about whether working memory persists to disk between cycles or exists only in-process. The MVP spec (`CEREBRA_WORKING_MEMORY_AND_ATTENTION.md §13`) says "working memory record" which implies some persistence, but the implementation detail is not resolved.

**Uncertainty:** The boundary between "session" and "cycle" isn't defined in the storage schema. `inspector_events` has `session_id` and `cycle_id` columns (currently always null). Working memory items need one of these to group correctly.

### Area 2 — Attention State

**What exists:** `inspector_events` has `session_id`, `cycle_id`, `step_id` columns — all currently null. `SQLiteEventLog.query_by_session()` is already implemented and indexed on `session_id` — once Phase 5 starts populating `session_id` on events, session-scoped queries work immediately with no new code. No `AttentionState` data structure exists in code.

**What Phase 5 needs:** An in-code `AttentionState` or `WorkingMemory` class that holds the current slot contents. At minimum: a dict mapping slot_type → list[AttentionItem], with capacity caps enforced.

**Gap:** The conceptual doc (`CEREBRA_WORKING_MEMORY_AND_ATTENTION.md`) defines an attention update cycle (read → score → promote/evict → render), but the trigger for this cycle — what causes it to run — is not resolved for Phase 5. The cycle runtime (`CEREBRA_COGNITIVE_RUNTIME.md`) is the intended caller, but Phase 5 does not implement the full cycle runtime.

**Uncertainty:** In the absence of a cycle runtime, how does working memory get populated in Phase 5? Options include: (a) manual `cerebra memory promote` CLI, (b) automatic population from `cerebra context` output, (c) test-only construction. The roadmap mentions "PROMOTE op" and "manual EVICT" — suggesting CLI-driven rather than automatic.

### Area 3 — Slot Dynamics

**What exists:** Slot capacity defaults are documented in `CEREBRA_DRIFT_FIXES_v8.1.md §1`:
- goal=1, constraint=4, context=7, hypothesis=3, evidence=5, contradiction=2, recent_output=2, question=3, procedure=4, interrupt=3 — TOTAL=34

These constants are not in code anywhere.

**Doc debt:** `DRIFT_FIXES_v8.1.md §1` is a patch document — it says "Target: `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md §4`, add this subsection after the slot enumeration." That patch was never applied. The live `§4` still only says "Slots can have capacity limits." Phase 5 should apply the patch (adding the `4.1 Default Slot Capacities` subsection) so the authoritative doc and the patch doc are in sync.

**What Phase 5 needs:**
- A constants file or config for slot capacities
- A slot management function that enforces caps and runs eviction when over capacity
- A salience comparator for eviction ordering (needs a salience score on each item)

**Gap:** What salience formula do working memory items use for eviction ordering? This is distinct from the retrieval salience (5-component composite). Working memory items may already have a composite score from when they were retrieved, but synthetic items (user-specified goals, constraints) have no retrieval-derived score.

**Uncertainty:** The eviction policy mentions "items currently cited by higher tiers are eviction-resistant" — this requires a runtime cross-reference between T2 and working memory slot contents. In Phase 5, only T1 and T2 exist; the check is whether the item appears in T2. This implies T2 must be queryable during working memory eviction.

### Area 4 — Access Tracking

**What exists:** `memory_records` has no access tracking columns. `retrieval_candidates.selected` (boolean) records that a record appeared in a ContextPacket, but there's no access count, last-access timestamp, or task-type tracking.

**What Phase 5 needs (if `access_frequency` is added as a salience component):**
- `last_accessed_at INTEGER` on `memory_records` (or a separate `memory_access_log` table)
- `access_count INTEGER` on `memory_records`

**Gap:** Phase 4 explicitly deferred `access_frequency` as a salience component. Whether Phase 5 needs it depends on whether working memory eviction uses full retrieval salience (which would require access_frequency) or a simplified score (composite from last retrieval). The roadmap says Phase 5 uses "salience threshold" for T2 promotion but doesn't specify which salience model.

**Uncertainty:** If access tracking requires schema changes (Migration009 columns on `memory_records`), this affects every existing test that asserts on `memory_records` row structure. The blast radius is non-trivial.

### Area 5 — Salience Dynamics

**What exists:** Five-component retrieval salience model (semantic, lexical, sku_match, recency, lifecycle). `score_composer.compose()` in `cerebra/_primitives/score_composer.py`. Lifecycle component is effectively constant at 1.0 in Phase 4 (no archived/warm records in the dev vault).

**What Phase 5 needs:**
- A salience score attached to each working memory item, used for eviction ordering
- Possibly: `user_pin` boost for pinned items (currently not in the scorer)
- Possibly: `access_frequency` component (deferred from Phase 4)

**Gap:** The working memory salience score needs to be defined. Options: (a) reuse the retrieval composite score as-is, (b) add a `user_pin` boost on top of the retrieval composite, (c) define a separate simpler formula for working memory items. None of these are in design docs.

**Uncertainty:** `CEREBRA_SALIENCE_SCORING.md §15 MVP` lists `user_pin` as an MVP component — it's documented as v0.1 scope but was not implemented in Phase 4. Phase 5 may be where it first appears in code.

### Area 6 — ContextPacket Integration

**What exists:** `ContextPacket` dataclass and `build_context_packet()` in `cerebra/retrieval/context_packet.py`. The packet has: `selected_memory`, `is_abstained`, `token_estimate`, `uncertainties`, `selected_count`, `candidate_count`, `excluded_candidate_count`, `best_score_seen` (abstained only). `packet_version=1`, `schema_version=1`.

**What Phase 5 needs:** The truth tower renders into the ContextPacket. The roadmap says "tower-to-packet." This likely means adding a `truth_tower` field or `tower_render` field to the packet.

**Gap:** Adding a field to `ContextPacket` is a schema change. It requires either:
- Bumping `packet_version` to 2, or
- Making the field optional (present only when a tower exists), which avoids a version bump

The test suite has tests that assert on specific required fields in the packet JSON (`test_abstention_against_vault.py::test_weather_context_abstained_packet_shape` checks for specific fields). Adding a new field is additive and non-breaking IF it's optional.

**Uncertainty:** Whether Phase 5 always renders a tower into the packet (every `cerebra context` call), or only when a working memory session exists. If the former, the tower field may be empty/null when no session is active, which adds complexity to the CLI.

### Area 7 — Event Surface

**What exists:** `cerebra/inspector/event.py` has `PHASE_0_EVENT_TYPES` frozenset. Phase 4 events were added without extending this frozenset (the `make_event()` function does not validate against `PHASE_0_EVENT_TYPES` — it's informational only). `SQLiteEventLog` writes to `inspector_events`; `query_by_subject()` and `query_by_type()` exist for retrieval.

**What Phase 5 needs:**
- 8 Working Memory events: WorkingMemoryCreated, AttentionItemProposed, AttentionItemPromoted, AttentionItemEvicted, AttentionItemDeferred, InterruptCandidateCreated, WorkingMemoryRendered, WorkingMemoryCleared
- 8 Truth Tower events: TowerInitialized, TowerItemPromoted, TowerItemEvicted, TowerCrossReferenceAdded, TowerItemStaled, TowerTierRebuilt, TowerCollapsed, TowerRendered

Total: 16 new event types. Data payloads for each are not specified in any design doc.

**Gap:** No Phase 5 event data schemas exist. The Phase 4 design doc (§11) specified exact data fields for each retrieval event. Phase 5 needs the equivalent — either in this assessment or in the Phase 5 design doc. Without field specs, tests for event payloads cannot be written.

**Uncertainty:** Phase 4 events were added ad-hoc without extending the event type vocabulary in `event.py`. Should Phase 5 formalize a `PHASE_5_EVENT_TYPES` frozenset, or introduce a single `ALL_EVENT_TYPES` that's extended each phase? This is a housekeeping question without a current answer.

### Area 8 — CLI Surface

**What exists:** `cerebra/cli/main.py` with 8 commands. No inspect commands. No memory management commands.

**What Phase 5 needs:**
- `cerebra memory promote <record_id> --slot <slot_type>` — add an item to working memory
- `cerebra memory evict <item_id>` — manual eviction
- Possibly: `cerebra memory status` — show current slot contents

The roadmap explicitly mentions "PROMOTE op" and "manual EVICT" as Phase 5 deliverables. It implies CLI commands (not just internal API).

**Gap:** No CLI design exists for working memory commands. The `cerebra inspect` command family (from `CEREBRA_INSPECTOR.md §7`) would also provide `cerebra inspect cycle ... --tower`, but that requires the cycle runtime which is out of Phase 5 scope. The minimum viable surface is working memory management, not full inspect.

**Uncertainty:** Should working memory CLI commands live under `cerebra memory ...` or `cerebra wm ...` or `cerebra attention ...`? The roadmap uses the term "working memory" but doesn't specify the CLI prefix.

### Area 9 — Carried-Forward Issues

**Phase 3 Q7 — Dual staleness semantics:** Resolved in Phase 4 `§7 D6`. `is_stale()` was extended with `check_drift=True` and a per-index drift detector registry (`lexical` and `vector` registered; `graph` deferred — no drift detector, Phase 4 explicitly noted). No open action for Phase 5.

**Phase 4 cold-load latency (~10s first query):** Observed during Step 6 verification: mxbai-embed-large-v1 loads fresh each `cerebra` invocation (no process-level cache). First query ~10s; subsequent queries in the same process are fast. Flagged in the Step 6 STOP gate as "a warm-cache invocation strategy or model pre-warming is a Phase 5 concern." No fix exists yet. If Phase 5 adds working memory CLI commands that also trigger retrieval, they'll hit the same cold-load.

**Lexical component 0.0 for most queries:** FTS5 AND semantics mean every term must appear in a document — colloquial queries ("how memories age", "weather forecast") produce 0.0 lexical scores even when the index is healthy. Confirmed during the reindex sidequest: `cerebra reindex --lexical` built 745 rows correctly, but scores stayed 0.0 for natural-language queries. The fix (OR/prefix FTS operators or query rewriting) is Phase 5+ calibration territory, not Phase 4.

**From Phase 4 §13 (Open Questions and Risks):**

| Issue | Status | Phase 5 relevance |
|-------|--------|-------------------|
| Q1 — D1 keyword classifier calibration | Open | Empirical validation still needed; not Phase 5 scope |
| Q3 — `cerebra search` vs full traversal | Resolved (run full traversal in both) | No action |
| Q4 — Token budget for `cerebra context` | Open | Phase 5 adds token-budget-aware pruning (ContextPacket budget field per §13) |
| Q5 — Graph staleness | Open | Phase 5 could add meaningful drift detector; low priority |
| Q6 — Sorting tie-breaking | Open | Low priority; add `created_at DESC` secondary sort if ties observed |
| Q7 — Excerpt length | Resolved (`EXCERPT_MAX_CHARS = 400` constant) | No action |

**From Phase 4 §14 (Deferred within Phase 4):**

| Deferred item | Phase 5 relevance |
|---------------|-------------------|
| `--explain` flag on `cerebra search` | Could land in Phase 5 if time allows; not core |
| Trace pruning (`cerebra prune traces`) | Low priority; Phase 5 scope per roadmap note |
| Lexical staleness warning in ContextPacket | Low priority |
| Graph neighborhood in ContextPacket | Deferred to Phase 5 explicitly |

**Lifecycle component:** `lifecycle` salience component is currently constant 1.0 (all dev vault records are `active`). Phase 5 working memory may be the first context where `warm` or `cold` records appear in retrieval, making this component non-trivial. No action required now but worth noting.

### Area 10 — Roadmap Alignment

**Phase 5 scope (from `CEREBRA_DEV_ROADMAP_v8.1.md`):**
- working_memory.py with named slots and slot capacity from DRIFT_FIXES §1 ✓ (documented)
- Promotion/eviction logic ✓ (policy documented)
- ContextPacket integration ✓ (tower-to-packet)
- truth_tower.py T1+T2 ✓ (T1 from retrieval, T2 manual promote)
- PROMOTE op ✓ (CLI surface needed)
- Manual EVICT ✓ (CLI surface needed)
- Chronological render ✓ (one render format)
- Tower-to-packet ✓ (ContextPacket field addition)
- Inspector events ✓ (16 new event types)
- Tests covering capacity, promotion, eviction ✓

**Explicitly out of Phase 5 scope:**
- T3, T4, T5 tiers (v0.2)
- Staleness propagation (v0.2)
- Auto-interrupts (deferred per WORKING_MEMORY_AND_ATTENTION §13)
- Multi-render formats beyond chronological (v0.2)
- Query expansion (Phase 6+)
- Sibling pointer traversal (v0.2)
- Multi-vault operations

**Alignment gaps:**
- The "graph neighborhood in ContextPacket" was deferred from Phase 4 to Phase 5 in §14 — it's not in the roadmap's Phase 5 task list. Low priority but worth clarifying.
- `access_frequency` salience component: in scope per `CEREBRA_SALIENCE_SCORING.md §15 MVP` but not in the Phase 5 task list. Needs a decision.

---

## §4. Carried-Forward Concerns

These are open issues from prior phases that Phase 5 must not silently close or that may complicate Phase 5 implementation.

**C1 — Session/cycle identity.** `inspector_events` has `session_id` and `cycle_id` columns, always null. `SQLiteEventLog.query_by_session()` already exists in code and is indexed — if Phase 5 starts populating `session_id` on events, this query method works immediately with no new code. The open question is what generates the session_id and when: `CEREBRA_COGNITIVE_RUNTIME.md §6` defines a `RuntimeSession` schema with a `working_memory_id` field, confirming working memory needs a stable referenceable ID. Phase 5 needs either (a) a session concept (session_id generated at `cerebra memory` command invocation) or (b) session-less singleton working memory (always null session_id — design inconsistency with the runtime spec).

**C2 — In-process vs persistent working memory.** The MVP scope says "working memory record" (implies persistence) but working memory is also described as a cycle-duration construct (implies in-process). `CEREBRA_COGNITIVE_RUNTIME.md §5` execution flow shows `initialize working memory` as step 2 of every cycle — the runtime expects to initialize it at cycle start, not find it already populated. This implies in-process initialization is the intended model, but the CLI command path (`cerebra memory promote`) has no running cycle to initialize. If it's in-process only, the working memory is always empty at CLI invocation. This needs a decision.

**C3 — ContextPacket version.** Adding a `truth_tower` field to ContextPacket changes the schema. Integration tests assert on specific required fields. If the new field is optional and absent from abstained packets, existing tests pass without change. If it's always present (empty or null when no tower), that's a different contract. Current `packet_version=1` — bump or not?

**C4 — PROMOTE op for T1 population.** T1 is populated from retrieval results. In Phase 5 without a cycle runtime, the only way to populate T1 is via `cerebra context` output. The roadmap says "T1 from retrieval" — this may mean T1 is automatically populated when `cerebra context` runs, without a separate CLI command. If so, every `cerebra context` call updates working memory T1 — which means working memory must persist between commands (C2 above).

**C5 — Synthetic working memory items.** The `goal` slot holds "active goal" — but in Phase 5 without a cycle runtime, who specifies the goal? If `cerebra memory promote` is the only path, the user would need to explicitly promote a record to the goal slot. But goals may not correspond to existing memory_records. A user might want to set a goal like "debug the retrieval pipeline" that isn't in the vault. This may require working memory items that have no `record_id` FK.

---

## §5. Conceptual Doc Map

Documents that define Phase 5 scope, in order of authority for implementation decisions:

| Document | Role |
|----------|------|
| `CEREBRA_DEV_ROADMAP_v8.1.md` | Task list and done-when criteria — primary scope definition |
| `CEREBRA_DRIFT_FIXES_v8.1.md §1` | Slot capacity defaults — authoritative constants |
| `CEREBRA_WORKING_MEMORY_AND_ATTENTION.md` | Working memory semantics, MVP scope, event types |
| `CEREBRA_TRUTH_TOWER.md` | Truth tower tiers, operations, MVP scope (T1+T2) |
| `CEREBRA_INSPECTOR.md §5.3–5.4` | Event type vocabulary for working memory + tower |
| `CEREBRA_SALIENCE_SCORING.md §15` | Salience component MVP list (includes user_pin) |
| `CEREBRA_MEMORY_LAYERS.md` | M4 (working memory) position in layer hierarchy |

Documents that are context but not Phase 5 implementation sources:
- `CEREBRA_COGNITIVE_RUNTIME.md` — cycle runtime; Phase 5 doesn't build this, but working memory must be compatible with it. Key findings from this doc: (1) `RuntimeSession` schema includes `working_memory_id` field — working memory needs a stable ID; (2) execution flow shows `initialize working memory` as step 2 — working memory API must be initializable by a future cycle runner; (3) MVP runtime scope includes "runtime session records" and "ContextPacket use" but not full working memory management.
- `CEREBRA_CONTEXT_PACKET_PROTOCOL.md` — original protocol spec; Phase 4 design doc overrides this for implemented fields

---

## §6. Recommended Next Step

Write a Phase 5 design doc (`v01_phase5_design.md`) that resolves the five open questions before any implementation begins. The carried-forward concerns in §4 are architectural decisions, not implementation details — they determine the module interface, the migration scope, and the CLI surface. Starting implementation before these are resolved will produce the same "fix during implementation" problems that Phase 3's Q7 (dual staleness semantics) produced.

Minimum questions to resolve in the design doc before coding:

1. **Persistent or in-process?** Is working memory persisted to disk (Migration009 required) or in-process per command invocation (no migration, but no cross-command persistence)?
2. **Session identity?** Does Phase 5 introduce a session_id concept, or does working memory operate session-less?
3. **T1 population trigger?** Is T1 automatically populated when `cerebra context` runs, or manually via `cerebra memory promote`?
4. **Synthetic items?** Can working memory slots hold items without a `memory_records` FK (e.g., user-specified goals)?
5. **ContextPacket schema change?** Is `truth_tower` field optional or required? What's the packet_version strategy?

These five decisions shape everything else in Phase 5. Get them locked first.

---

## §7. Open Questions for Ryan

**Q1 — Persistence model.** Do you want working memory to persist between `cerebra` command invocations (i.e., I run `cerebra memory promote X` and then `cerebra context Y` and the promoted item is still in working memory)? Or is working memory rebuilt each time? If persistent, what's the isolation model — one working memory per vault, or per session, or per explicit "start session" command?

**Q2 — Goal slot.** The goal slot (capacity 1) holds "active goal." Can a user directly set a goal that isn't a memory_records entry (free text), or should it always reference a vault record? The truth tower doc says "T5 goal: user intent or cycle config" — does Phase 5 support user-specified intent as a string, or only as a reference to an ingested record?

**Q3 — auto-populate T1 from context.** When `cerebra context "task"` runs, should it automatically populate working memory T1 with the selected memory results? Or does T1 population require explicit `cerebra memory promote`? Auto-populate is simpler to demo but couples the context command to working memory state.

**Q4 — access_frequency salience component.** This was an MVP component in the salience doc but was deferred from Phase 4. Does Phase 5 add it? It requires access tracking columns in the schema (migration change) and a scoring change. If no, the working memory eviction salience will use Phase 4's 5-component composite — which doesn't include access_frequency and has lifecycle constant at 1.0.

**Q5 — `cerebra inspect` commands.** `CEREBRA_INSPECTOR.md §7` defines `cerebra inspect cycle ... --tower` and related commands. Does Phase 5 need to implement any of these, or does it only need `cerebra memory promote/evict/status`? Inspect commands require the cycle identity concept (C1 above).

**Q6 — packet_version bump.** When the tower field is added to ContextPacket, do you want `packet_version` bumped to 2, or should the new field be silently optional (no version bump)? A bump is more honest but breaks any consumer that hard-checks `packet_version == 1`.
