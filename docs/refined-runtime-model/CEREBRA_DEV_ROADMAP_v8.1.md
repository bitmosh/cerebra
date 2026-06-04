# Cerebra — Development Roadmap v8.1

## Purpose

This roadmap defines the build sequence for Cerebra v0.1.

It supersedes the phase ordering in `CEREBRA_IMPLEMENTATION_PLAN.md`, which was written before the SKU, truth tower, leeway, signal epistemology, and inspector primitives were specified. The build order here integrates those primitives at the right points and places governance scaffolding before feature code.

The principle: **build the things that make every other thing inspectable, governable, and structurally safe first**. Feature code on top of weak foundations creates technical debt that compounds; feature code on top of strong governance produces code that stays maintainable indefinitely.

---

## Build Discipline

Three rules govern every phase:

```text
1. Every phase has a "done when" gate. No phase is complete without passing
   its gate. No subsequent phase starts until the gate passes.

2. Every phase produces tests as part of its scope. Phases without tests
   are not complete even if they "work."

3. Every phase emits inspector events. Code that runs silently is not
   complete even if it works correctly.
```

These rules are non-negotiable. They are what turn the prototype from "code that runs" into "code that can grow into v1.0."

---

## Phase 0 — Project Scaffolding and Governance

**Goal:** establish the floor that everything else builds on.

**Why first:** if you defer governance, you write code that ignores it. Then governance becomes a refactor instead of a foundation. The order here is the lever that makes the rest of the project maintainable.

**Tasks:**

```text
1. Create repository structure per CEREBRA_ARCHITECTURE.md §7
2. Set up pyproject.toml with Python 3.12+, no unnecessary dependencies
3. Set up pytest + coverage tooling
4. Set up linting (ruff) and formatting (black) with pre-commit hooks
5. Set up type checking (mypy) with strict mode
6. Create cerebra/_primitives/ directory and vendor the six Lattica primitives
7. Create cerebra/cognition/ module skeleton with __init__.py exposing
   the public API surface (even if empty for now)
8. Create vault initialization (cerebra/vault/init.py) — the cerebra init
   command and its directory structure
9. Set up SQLite schema migration framework (cerebra/storage/migrations.py)
10. Create the constitutional layer file format and load the v0.1 defaults
    (5 constitutional rules from CEREBRA_LEEWAY_NETWORK.md §12)
11. Create the leeway rule file format and load the v0.1 defaults
    (15 leeway rules from CEREBRA_LEEWAY_NETWORK.md §12)
12. Create the inspector event schema and SQLite event table
13. Create the NDJSON append-only event log infrastructure
14. Create CI workflow that runs lint + types + tests on every push
```

**Done when:**

```text
[ ] Repository structure matches the spec
[ ] Pre-commit hooks block bad commits
[ ] CI runs on push and fails on lint/type/test errors
[ ] `cerebra init <path>` creates a vault with all required directories
[ ] Vault contains: config.yaml, data/cerebra.db, artifacts/, indexes/,
    exports/, events/, leeway/, constitutional/
[ ] Constitutional and leeway YAML files load and validate
[ ] Inspector event infrastructure can emit and store an event
[ ] All six Lattica primitives are importable and have passing tests
[ ] Coverage report exists; coverage stays >=80% from here on
```

**Time estimate:** 2-3 working days for a focused solo developer with AI assistance.

---

## Phase 1 — Source Memory Foundation

**Goal:** reliable source ingestion with provenance preservation.

**Tasks:**

```text
1. Source registry table and operations (cerebra/sources/registry.py)
2. Content hashing (cerebra/sources/hashing.py)
3. File discovery (cerebra/sources/discovery.py)
4. Type detection with confidence (cerebra/sources/detector.py)
5. Markdown parser adapter (cerebra/ingest/adapters/markdown.py)
6. Text parser adapter (cerebra/ingest/adapters/text.py)
7. Normalization layer (cerebra/ingest/normalization.py)
8. Heading-based chunker for markdown (cerebra/ingest/chunking.py)
9. Memory record builder for source_chunk type (cerebra/memory/records.py)
10. Storage layer for sources, documents, chunks, records (cerebra/storage/sqlite_store.py)
11. Inspector events for every ingestion action
12. Idempotency check using content hash + parser version
13. CLI command: cerebra ingest <path>
```

**Done when:**

```text
[ ] `cerebra ingest ./docs` registers every markdown file
[ ] Sources have stable IDs based on content hash
[ ] Re-running ingest on unchanged files is a no-op (idempotency)
[ ] Chunks preserve heading path and source position
[ ] No orphan chunks (every chunk traces back to a source)
[ ] Inspector events emit for SourceRegistered, ChunkCreated, etc.
[ ] Tests cover happy path, malformed input, duplicate detection,
    modification detection
```

**Defer to later phases:** PDF, docx, JSON/YAML/CSV adapters. Markdown + text only for v0.1.

**Time estimate:** 2-3 days.

---

## Phase 2 — SKU Classifier and Addressing

**Goal:** every memory gets a SKU address at write time.

**Why early:** SKU is the substrate for everything above the raw chunks. If you defer it, you write retrieval code that doesn't use SKU and then refactor later.

**Tasks:**

```text
1. SKU data model and serialization (cerebra/cognition/sku.py)
2. The 16 cognitive categories table (cerebra/cognition/sku_categories.py)
3. The 16 relationship types table (cerebra/cognition/sku_relationships.py)
4. Single-pass SKU classifier with prompt + formula pairing
   (cerebra/cognition/sku_classifier.py)
5. Classifier metadata preservation (forward compat for ablation)
6. SKU storage as adjacent metadata on memory records
7. Inspector events: SKUAssigned with full classifier output
8. SKU validation (digit ranges, null handling)
9. Tests with known-content fixtures for classifier behavior
```

**Done when:**

```text
[ ] Every new memory record receives a SKU at write time
[ ] Classifier outputs per-category scores for all 16 categories
   (not just the top 3)
[ ] Classifier confidence is preserved per anchor position
[ ] SKU includes location digits (D1-D4 minimum), entry index (D7-D8),
    and provenance digit (D10)
[ ] D10 distinguishes observed vs synthesized vs consolidated
[ ] SKUs round-trip through serialization without data loss
[ ] Tests validate stable classification on unchanged content
[ ] Tests validate D10 enforcement (synthesized memories never tagged observed)
```

**Defer to v0.2:** D5/D6 temporal/novelty bands, multi-pointer fanout,
multi-prompt triangulation, calibration audits.

**Time estimate:** 2-3 days. The classifier prompt design is the load-bearing
work here.

---

## Phase 3 — Storage and Index Layer

**Goal:** memory persists; retrieval has indexes to work with.

**Tasks:**

```text
1. Complete SQLite schemas: sources, documents, chunks, memory_records,
   sku_assignments, lifecycle_states, events, graph_nodes, graph_edges
2. Artifact store for normalized documents (cerebra/storage/artifact_store.py)
3. Lexical index using SQLite FTS5 (cerebra/storage/lexical.py)
4. Vector index using a simple local strategy
   - For MVP: numpy + cosine similarity over an embedding table
   - Defer: Qdrant/LanceDB until volume demands it
5. Embedding generation (use sentence-transformers locally;
   no cloud APIs in v0.1)
6. Graph store using SQLite (cerebra/storage/graph_store.py)
7. Index freshness tracking (cerebra/storage/index_state.py)
8. Schema migration tooling (forward-only migrations)
9. Inspector events for all storage operations
```

**Done when:**

```text
[ ] Source/document/chunk/record persistence works
[ ] Lexical index returns matches for known queries
[ ] Vector index returns matches for semantic queries
[ ] Index freshness is queryable
[ ] Schema migration runs idempotently on existing vaults
[ ] Tests cover persistence round-trips, index freshness, migration
```

**Time estimate:** 3-4 days.

---

## Phase 4 — Retrieval and ContextPacket

**Goal:** retrieval through the SKU substrate, producing inspectable ContextPackets.

**Tasks:**

```text
1. Query planner (cerebra/retrieval/query_planner.py)
2. Query SKU construction (parse query, build partial SKU pattern)
3. The 6-step traversal:
   - Step 1: exact match
   - Step 2: partial match (D1+D2+D3, vary D4-D10)
   - Step 3: sibling pointer traversal (will be no-op until v0.2 fanout)
   - Step 4: 1-hop expansion (also requires fanout; placeholder for v0.1)
   - Step 5: bounded vector fallback
   - Step 6: trace annotation
4. Salience scoring with v0.1 component set
   (semantic, lexical, project, source authority, recency, confidence,
    lifecycle, user_pin per CEREBRA_SALIENCE_SCORING.md §15)
5. Reranker (deterministic, formula-based for v0.1)
6. ContextPacket builder (cerebra/retrieval/context_packet.py)
7. Plain text + JSON rendering of ContextPackets
8. Retrieval trace storage with full annotation
9. Inspector events for QueryReceived, RetrievalPerformed,
   each step completion, ContextPacketBuilt
10. CLI commands: cerebra search, cerebra context
```

**Done when:**

```text
[ ] `cerebra search "query"` returns scored candidates with paths
[ ] Every result includes retrieval_path annotation ("exact match on D1+D2")
[ ] `cerebra context "task"` produces a ContextPacket with provenance
[ ] ContextPackets render as both JSON and plain text
[ ] Retrieval traces persist and are queryable
[ ] Tombstoned/quarantined memory is excluded from default retrieval
[ ] Score components are visible per result
[ ] Tests cover exact match, partial match, vector fallback,
    tombstone exclusion, trace presence
```

**Time estimate:** 3-4 days.

---

## Phase 5 — Working Memory and Truth Tower (Skeletal)

**Goal:** the cognitive workspace exists with M4 working memory and minimal T1/T2 tower.

**Tasks:**

```text
1. Working memory data model with named slots
   (cerebra/cognition/working_memory.py)
2. Slot capacity defaults from CEREBRA_DRIFT_FIXES_v8.1.md §1
3. Attention item promotion/eviction logic
4. ContextPacket integration (working memory contributes to packet)
5. Truth tower data model with T1 and T2 only
   (cerebra/cognition/truth_tower.py)
6. PROMOTE operation (T1→T2 with salience threshold)
7. Manual EVICT operation (no auto-staleness propagation in v0.1)
8. One render format: chronological
9. Tower-to-ContextPacket projection
10. Inspector events for all attention and tower operations
```

**Done when:**

```text
[ ] Working memory tracks active goal, constraints, context, recent outputs
[ ] Capacity caps are enforced; user-pinned items non-evictable
[ ] T1 populates from retrieval results
[ ] T2 promotion respects salience threshold and citation requirement
[ ] Tower renders into ContextPackets via chronological format
[ ] Events emit for all working memory + tower operations
[ ] Tests cover capacity enforcement, promotion rules, eviction priority
```

**Defer to v0.2:** T3/T4/T5, staleness propagation, multi-render formats.

**Time estimate:** 2-3 days.

---

## Phase 6 — Signal Pipeline and Prediction Records

**Goal:** evaluate step outputs across the six perennial-thread signals; record predictions.

**Tasks:**

```text
1. Signal evaluation prompts (one per signal, per CEREBRA_SIGNAL_EPISTEMOLOGY.md §8)
   - COHERENCE checklist prompt
   - GROUNDEDNESS checklist prompt
   - GENERATIVITY checklist prompt
   - RELEVANCE checklist prompt
   - PRECISION checklist prompt
   - EPISTEMIC HUMILITY checklist prompt
2. Signal evaluator that runs prompts and aggregates scores
   (cerebra/cognition/signals.py)
3. Default weights table (from CEREBRA_SIGNAL_EPISTEMOLOGY.md §6)
4. Composition formula using the Lattica primitive triangulator
5. Per-cycle config weight overrides
6. Prediction record schema (cerebra/cognition/predictions.py)
7. Outcome record + prediction error computation
8. Prediction-error thresholds (noise/notable/severe per cycle config)
9. EvaluationPacket creation per step
10. Inspector events for SignalEvaluated, PredictionMade,
    PredictionResolved, PredictionErrorRecorded, PredictionSevereMiss
```

**Done when:**

```text
[ ] Every step produces an EvaluationPacket with all 6 signals scored
[ ] Composite computes via weighted mean
[ ] Triangulated reward computes via confidence × signal_strength
[ ] Per-cycle weight overrides work
[ ] Predictions persist with confidence and basis
[ ] Outcomes link to predictions and produce typed error records
[ ] Severe misses (|error| > 0.40) emit additional flag events
[ ] Tests cover formula correctness, weight override, threshold bands
```

**Time estimate:** 3-4 days. The signal prompts are the load-bearing work.

---

## Phase 7 — Leeway Network (Pre-Action Gate)

**Goal:** safety architecture in place before any cycle runs.

**Why now:** by Phase 7 you have all the things leeway needs to gate — retrieval, evaluation, working memory writes. Putting leeway in place now means every subsequent line of code already respects it. Putting it in later means refactoring everything.

**Tasks:**

```text
1. Leeway rule schema validation (cerebra/cognition/leeway.py)
2. Constitutional rule schema validation
3. Leeway rule loader (reads vault leeway/ directory at init)
4. Constitutional rule loader (reads vault constitutional/ directory at init)
5. Pre-action gate evaluation
   - Capability lookup
   - Condition evaluation
   - Revocation check (rule-level)
   - Constitutional revocation check
6. Candidate filtering for catalyst (defer until catalyst lands;
   build the API surface now)
7. cannot_select signal handling
8. Inspector events for LeewayGrantApplied, LeewayGrantDenied,
   LeewayRevocationFired, ConstitutionalBlock, LeewaySetEmpty
9. CLI commands: cerebra inspect leeway active, cerebra inspect constitutional
```

**Done when:**

```text
[ ] Default leeway set (15 rules) loads at vault init
[ ] Default constitutional set (5 rules) loads at vault init
[ ] Pre-action gate evaluates capabilities correctly
[ ] Constitutional rules override leeway grants when conditions match
[ ] LeewaySetEmpty signal raises when no candidates pass
[ ] Inspector renders active grants and recent decisions
[ ] Tests cover grant matching, revocation, constitutional override,
    empty-set handling
```

**Defer to v0.2:** post-action audit phase.

**Time estimate:** 2-3 days.

---

## Phase 8 — Cycle Runtime (Skeletal)

**Goal:** the runtime can load a cycle config and execute one step.

**Tasks:**

```text
1. Cycle definition schema (cerebra/cognition/cycle_config.py)
   per CEREBRA_DRIFT_FIXES_v8.1.md §2
2. Cycle config YAML loader with validation
3. Runtime session model (cerebra/cognition/session.py)
4. Step execution framework with mockable LLM calls for v0.1
5. The "simple.planning.v0" built-in cycle config
6. Step orchestration: build_context → execute → evaluate → record
7. Inspector events for CycleStarted, StepStarted, StepCompleted,
   StepFailed, CycleCompleted
8. CLI command: cerebra run-cycle <config> --goal <text>
```

**Done when:**

```text
[ ] Cycle config YAML loads and validates
[ ] `cerebra run-cycle simple.planning.v0 --goal "..."` executes one cycle
[ ] Cycle produces step outputs (mockable LLM is fine for now)
[ ] EvaluationPacket attaches to each step
[ ] Runtime session persists with full step history
[ ] Tests cover config loading, session lifecycle, step orchestration
```

**Time estimate:** 3-4 days.

---

## Phase 9 — Clutch and Catalyst (Minimal)

**Goal:** decisions flow through the proper primitives.

**Tasks:**

```text
1. Clutch primitive from cerebra/_primitives/clutch.py (already vendored)
2. Clutch rule definitions for simple.planning.v0 cycle config
3. Clutch action group enforcement (terminal/iterative/structural/social)
4. Catalyst skeleton with five scoring factors
   (cerebra/cognition/catalyst.py)
5. Bandit primitive integration for base_reward
6. Weighted-random sampling (not argmax)
7. Leeway filter integration before sampling
8. Catalyst vocabulary for simple.planning.v0
9. Inspector events for ClutchDecisionIssued, CatalystSelectionMade
```

**Done when:**

```text
[ ] Clutch evaluates rules and returns explainable decisions
[ ] First-match-wins semantics work correctly
[ ] Action grouping respected; rules declare their group
[ ] Catalyst scores candidates with all five factors
[ ] Weighted-random sampling never returns the same answer
    100% of the time on diverse runs
[ ] Leeway filter removes prohibited candidates before sampling
[ ] cannot_select signal handling triggers safe defaults
[ ] Tests cover scoring formula, sampling distribution, leeway integration
```

**Defer to v0.2:** chain_bonus, decay_factor, self_optimize action.

**Time estimate:** 2-3 days.

---

## Phase 10 — Consolidation v0

**Goal:** memory maintenance happens automatically after cycles.

**Tasks:**

```text
1. Consolidation engine skeleton (cerebra/memory/consolidation.py)
2. Duplicate detection (hash + text similarity)
3. Document summary creation
4. Project/topic summary creation
5. Archive retrieval card creation
6. SKU pointer rewriting when consolidation produces summaries
7. Calibration audit hook (placeholder; full implementation in v0.2)
8. Lifecycle recommendation generation
9. Inspector events for ConsolidationStarted, ConsolidationCompleted,
   SummaryCreated, DuplicateLinked
10. CLI command: cerebra consolidate --session <id>
```

**Done when:**

```text
[ ] Consolidation runs on demand
[ ] Duplicates link without source deletion
[ ] Summaries cite supporting records
[ ] SKU pointer rewrites work for consolidated content
[ ] Tests cover duplicate detection, summary support links, no-deletion
```

**Time estimate:** 2-3 days.

---

## Phase 11 — Lifecycle Manager

**Goal:** memory states transition correctly.

**Tasks:**

```text
1. Lifecycle state machine (cerebra/memory/lifecycle.py)
2. Active/archived/tombstoned/deleted-marker states for v0.1
   (warm/cold/quarantined deferred)
3. Tombstone-aware set primitive integration
4. State transition validation
5. Restore from archive operation
6. Inspector events for all transitions
7. CLI commands: cerebra archive, cerebra tombstone, cerebra restore
```

**Done when:**

```text
[ ] Archived memory retrieves via retrieval card only
[ ] Tombstoned memory is excluded from normal retrieval
[ ] Re-ingestion of tombstoned content is blocked
[ ] Restore from archive works
[ ] Lifecycle events emit and persist
[ ] Tests cover transition validity, tombstone re-ingestion block,
    retrieval exclusion
```

**Time estimate:** 1-2 days.

---

## Phase 12 — Graph Event Writer and Export

**Goal:** Cerebra emits structured graph data that LumaWeave can consume.

**Tasks:**

```text
1. Graph node and edge models (cerebra/graph/model.py)
2. Graph event outbox pattern (decouple emission from cycle execution)
3. NDJSON event writer per session
4. JSON graph export (cerebra/graph/export.py)
5. LumaWeave-compatible schema with provenance edges
6. CLI command: cerebra export graph --out <path>
```

**Done when:**

```text
[ ] Every cycle emits graph events to NDJSON file
[ ] `cerebra export graph` produces stable JSON with nodes + edges
[ ] Export includes provenance chains
[ ] Export includes lifecycle states
[ ] NDJSON file is line-atomic (LumaWeave can tail safely)
[ ] Tests cover event ordering, NDJSON validity, export schema
```

**Time estimate:** 1-2 days.

---

## Phase 13 — Inspector CLI Polish

**Goal:** the observability surface is genuinely useful for development and debugging.

**Tasks:**

```text
1. Implement all v0.1 inspector commands per CEREBRA_INSPECTOR.md §7
2. Pretty-text rendering with color and structure
3. JSON output flag (--json) for piping
4. Tail mode for live event streams
5. The "why was this retrieved" rendering (--explain flag)
6. Session, cycle, memory, retrieval, leeway sub-commands
7. Query command with event-type and signal-threshold filters
```

**Done when:**

```text
[ ] All v0.1 inspect commands work and produce useful output
[ ] --json flag produces parseable JSON
[ ] Tail mode streams new events as they emit
[ ] --explain on retrieval shows full path and reasoning
[ ] Tests cover command output structure
```

**Time estimate:** 2-3 days.

---

## Phase 14 — Integration Testing and Polish

**Goal:** the full spine works end-to-end with confidence.

**Tasks:**

```text
1. End-to-end test: ingest, run cycle, retrieve, export
2. Performance baseline measurements
3. Documentation pass on README and quickstart
4. Example vault with sample content
5. Bug fixes from integration testing
6. v0.1 release notes
```

**Done when:**

```text
[ ] End-to-end test passes from clean vault to graph export
[ ] Performance baseline documented (queries/sec, ingestion rate)
[ ] README walks a new user through their first 5 minutes
[ ] v0.1 git tag exists
[ ] All v0.1 success criteria from CEREBRA_MVP_SPEC.md §11 pass
```

**Time estimate:** 2-3 days.

---

## Total Time Estimate

```text
Phase 0 (Scaffolding):          2-3 days
Phase 1 (Source Memory):        2-3 days
Phase 2 (SKU Classifier):       2-3 days
Phase 3 (Storage/Index):        3-4 days
Phase 4 (Retrieval/Context):    3-4 days
Phase 5 (Working Memory+Tower): 2-3 days
Phase 6 (Signals/Predictions):  3-4 days
Phase 7 (Leeway):               2-3 days
Phase 8 (Cycle Runtime):        3-4 days
Phase 9 (Clutch/Catalyst):      2-3 days
Phase 10 (Consolidation):       2-3 days
Phase 11 (Lifecycle):           1-2 days
Phase 12 (Graph Export):        1-2 days
Phase 13 (Inspector Polish):    2-3 days
Phase 14 (Integration):         2-3 days
                                ----------
Total:                          32-47 days
```

For a focused solo developer with strong AI assistance: roughly 6-9 weeks of actual work, calendar-spread however life requires.

---

## What This Roadmap Deliberately Does Not Cover

**Frontend.** Separate project starting ~4 days post-v0.1 ship. Not in scope here.

**Advanced primitives (deferred to v0.2+):**
- Multi-pointer SKU fanout
- Truth tower T3/T4/T5
- Orthogonal ablation operations
- Re-injection loop temporal/structural parallel
- Leeway post-action audit
- Multi-prompt triangulation
- Catalyst chain-bonus and decay
- Calibration audits
- Self-improving retrieval bandit
- Synthesis at endpoint
- Continental modifier
- Dream/retrain integration

**Policy Scout integration.** Separate project; integrates via ingested events when both projects exist.

**LumaWeave integration depth.** Cerebra emits events; LumaWeave consumes. Cerebra does not embed LumaWeave logic.

---

## Roadmap Doctrine

The phases above are not arbitrary. They are ordered by *dependency* and *governance leverage*.

Phase 0 establishes the floor. Every subsequent phase respects that floor — events, tests, lint, governance scaffolding. Skipping Phase 0 doesn't speed things up; it slows everything down later because you refactor what should have been built right.

Phases 1-4 build the substrate: source memory, SKU, storage, retrieval. These are the layers everything else stands on.

Phases 5-9 build the cognitive runtime: working memory, signals, leeway, runtime, clutch/catalyst. This is where Cerebra earns its name.

Phases 10-14 close the loop: maintenance, lifecycle, export, observability, integration testing.

If a phase reveals a flaw in an earlier phase, fix the earlier phase first. Building forward on broken foundations compounds errors that take 10x longer to fix later than 1x to fix now.

**The prototype gate from `CEREBRA_PROTOTYPE_CHECKLIST.md` runs after Phase 8.**

Once Phase 8 completes, you have everything the prototype gate requires. Run it. If it passes, continue to Phase 9. If it doesn't, that's the signal something earlier was wrong; fix it before continuing.

Build the spine. Let it tell you what the plans got wrong. Update from evidence.
