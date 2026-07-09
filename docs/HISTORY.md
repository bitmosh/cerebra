# Cerebra — Development History

Cerebra is a local-first cognitive runtime that executes structured multi-step reasoning cycles against a personal knowledge vault. This document describes how it was built — the 14-phase development arc, the core architectural choices, and the tradeoffs behind the current design.

Cerebra is **actively maintained alpha software**. This history explains the shape of the system, not a frozen snapshot.

---

## What Cerebra Is

Cerebra is a configurable cognitive cycle runtime. It is not a RAG pipeline or a chatbot wrapper. The central idea is a closed-loop cognitive engine: each step retrieves context from a vault of ingested knowledge, calls a local LLM via Ollama, evaluates the output across six epistemic signals, routes the next action through a rule engine (Clutch), optionally escalates to a bandit-driven strategy selector (Catalyst), writes the result as a dual-format episode, and decides whether to continue, recurse, or stop.

Every cognitive action leaves behind structured state: input, context, output, signal scores, control decision, memory write, and graph event. Nothing happens without a trace.

### Core capabilities at v0.4.5

- **Vault management** — initialize and maintain a local vault with full content-addressed provenance
- **Source ingestion** — parse and chunk markdown and plain text; generate embeddings; build FTS5 index
- **Hybrid retrieval** — lexical (FTS5), vector (cosine), SKU-addressed, graph-expanded; component-scored composite
- **Cognitive cycle runtime** — configurable YAML-defined cycles with N steps, stop conditions, and clutch actions
- **Six epistemic signal evaluators** — coherence, groundedness, relevance, precision, generativity, epistemic humility
- **Clutch controller** — priority-rule action router with hysteresis, mode persistence, and cascade depth
- **Catalyst / strategy selector** — bandit-driven arm selection over five cognitive strategy arms
- **Working memory + TruthTower** — bounded contested attention slots; five-tier derived workspace (T1 Evidence → T5 Goal)
- **Re-injection loop** — continuation bundles enable cognitive continuity across context window limits
- **Dual-format episode persistence** — cycle outputs written to both SQLite (retrievable) and FossicStore (event-chained) when the `fossic` extra is installed
- **Lifecycle management** — archive, tombstone, restore on memory records with stale detection
- **Graph export** — cerebra/v1 JSON for downstream visualization
- **Inspector CLI** — forensic query surface for sessions, cycles, signals, leeway, and events
- **Leeway network** — three-tier safety architecture (constitutional, capability, conditional leeway grants)
- **HTTP daemon** — `cerebra serve` for tile-integrated usage with Lattica

---

## Development Progression

Cerebra was built in 14 discrete phases, each verified by tests before proceeding. The migration table in `cerebra/storage/migrations.py` (M001–M018) maps directly onto this arc.

### Phases 1–6: Foundation and Memory Substrate

**Phase 1 — Core vault and ingest pipeline**
Source registration with content-hash-based change detection (`SKIPPED_UNCHANGED` / `CHANGED` / `NEW` outcomes). Markdown and text parsing. Chunk pipeline. `SourceRecord` with stable content-addressed `source_id`. Inspector event emission from the first commit. SQLite connection factory with WAL mode, FK enforcement, and row-dict adapter applied uniformly.

**Phase 2 — SKU classification** (M002)
10-digit cognitive-shape addressing across 16 quadrant categories (4 orientations × 4 dimensions). An LLM-driven classifier assigns SKU addresses to memory records, enabling shape-based retrieval alongside lexical and vector paths.

**Phase 3 — Embeddings and vector search** (M003)
`mxbai-embed-large-v1` (1024-dim float32) stored per record. Cosine search over active records. `pending_embeddings` queue for batch drain processing. FTS5 index for lexical search with query sanitization guarding against FTS5 syntax errors from LLM-generated queries.

**Phase 4 — Graph model** (M004, M005)
`graph_nodes` + `graph_edges` tables. Bidirectional links between source nodes and memory records. FTS5 index staleness tracking. Graph export path established for downstream visualization.

**Phase 5 — Working memory and retrieval tracing** (M006–M009)
`WorkingMemorySession` with bounded attention slots. `TruthTower` (T1 Evidence → T5 Goal) as a five-tier derived workspace. `ContextPacket` builder assembling retrieval results and working memory state into agent-ready bundles. Full retrieval tracing (traces → steps → candidates) with component scores (semantic, lexical, SKU match, recency, lifecycle).

**Phase 6 — Signal evaluation and prediction** (M010, M011)
Six epistemic signal evaluators scored per cycle step. Prediction layer: expected vs. actual composite scores, signed prediction error, error classification (noise / notable / severe). Prediction error accumulates into the Catalyst bandit's learning signal.

### Phases 7–9: Cognitive Runtime Spine

**Phase 7 — Leeway network + FossicStore integration** (M012)
Three-tier safety architecture: constitutional rules (inviolable — always evaluated, v0.1 has no rules that forbid), capability bounds (structural — which adapters exist), conditional leeway grants (runtime permission decisions). `LeewayPreActionGate` evaluates proposed actions before execution and records `LeewayGrantApplied` events. FossicStore integration: all cycle events emit to `cerebra/agent-trace/<session_id>` streams with content-addressed, causation-chained event IDs. `cerebra serve` HTTP daemon ships in this phase.

**Phase 8 — Full cycle runtime** (M013, M014)
`CycleRuntime` main step loop executing configurable YAML cycle definitions. `ContinuationBundle` + `BundleDistiller`: when a cycle hits `max_steps_without_acceptance`, the runtime distills a continuation prompt containing the TruthTower projection, open questions, constraints, and next focus, then opens a child session and primes it with the bundle. Cycle episodes persist to `cycle_episode_records` (pre-Phase 10 retrieval bridge).

**Phase 9 — ClutchEngine, CatalystEngine, re-injection**
Full `ClutchEngine`: priority rules, multi-signal input, hysteresis, cascade depth, escalate hook. Six predicate types: signal floor, signal ceiling, threshold window, step count, mode persistence, truth tower occupation. `CatalystEngine` wraps six vendored primitives (Triangulator, Trajectory, HysteresisModeRouter, ScoreComposer, TombstoneSet, BanditSelector) for bandit-driven arm selection over five cognitive strategy arms: explore, refine, disrupt, structure, memory_integration. `ReinjectionTriggerEvaluator` predicate evaluation produces continuation bundles and spawns child sessions at recursion depth < `max_recursion_depth`.

### Phases 10–14: Loop Closure and Ship Gate

**Phase 10 (v0.4.0) — Cognitive loop closure** (M015–M018)
Cycle episodes promoted into the main `memory_records` table via `EpisodeWriter`, closing the feedback loop: outputs from prior cycles become retrievable context for future cycles. Synthetic provenance sentinels (M018) anchor FK constraints for episodes with no real source file. Lattice membership columns added (M015–M017).

**Phase 11 (v0.4.1) — Lifecycle manager**
Full archive/tombstone/restore on memory records. Lifecycle state transitions: `active → archived → tombstoned`. Tombstones prevent accidental resurrection without breaking provenance chains. Stale lifecycle states propagate from changed sources through documents, chunks, and records.

**Phase 12 (v0.4.2) — Graph export**
`cerebra export graph` produces cerebra/v1 JSON for downstream visualization. `GraphSnapshotAvailable` event emitted on `cerebra/graph/<lineage_id>` fossic stream when fossic is available (hub emission wrapped in try/except so unavailability never fails the export). Hub-direct emission path for multi-process scenarios.

**Phase 13 (v0.4.3) — Inspector CLI**
`cerebra inspect` command group: `session list`, `cycle show <id> [--signals]`, `query [--event-type] [--signal-low] [--tail]`, `leeway active`. Forensic observability over both the SQLite inspector events table and the FossicStore event streams.

**Phase 14 (v0.4.4) — Integration testing and polish**
Full E2E spine test against real Ollama. CORS header added to daemon `_send_json` for Tauri webview integration. `cerebra-relay.py` relay agent for vault-to-hub emission. Full 14-phase system shipped.

### v0.4.5 and beyond

Ongoing work post-v0.4.4 focuses on public release readiness: dependency hygiene (fossic promoted from vendored wheel to PyPI-installed optional dep), CI reproducibility (exact tool pins reviewed periodically per TECH_DEBT.md), and defect resolution (tracked open items in KNOWN_ISSUES.md).

---

## Architectural Choices and Their Tradeoffs

Two design decisions are worth surfacing explicitly because they shape everything downstream.

### Dual persistence strategy

Cerebra uses two storage systems with different semantics:

1. **`cerebra.db` (SQLite)** — a mutable relational store holding memory records, retrieval traces, working memory state, signal evaluations, sessions, predictions, and cycle episodes. Schema evolves through explicit `ALTER TABLE` DDL across 18 sequential migrations.

2. **`.fossic/store.db` (FossicStore, optional)** — a content-addressed, causation-chained event store backed by Rust. Every state transition is an immutable event with a deterministic hash ID. State is derived by replaying event streams. This is the classical event-sourcing model.

SQLite is the current-state answer; FossicStore is the history-of-changes answer. Coexistence creates real friction:

**WAL discipline.** Inspector event writes must happen *after* `conn.close()` on any connection that just modified related tables. This prevents "database is locked" errors under SQLite's WAL concurrency model. This discipline is hand-enforced across `TruthTower`, `LifecycleManager`, and other modules — a distributed coordination protocol implemented by convention rather than by the storage engine.

**Synthetic provenance sentinels (M018).** Cycle episodes have no real source file — they are outputs of cognitive cycles, not ingested documents. SQLite's FK constraints on `memory_records` require valid `(source_id, document_id, chunk_id)` references for every row. The workaround: insert three sentinel rows at migration time so episode inserts satisfy the FK constraints. In a pure event-sourced system, episodes are events on a stream and there are no FK constraints to satisfy.

**Dual-write burden (when fossic is enabled).** Every meaningful state change requires both a SQLite write (current state) and a FossicStore append (event history). These two writes must remain consistent without a distributed transaction primitive. The system manages this through careful sequencing.

**Schema migration accumulation.** The 18 migrations reflect organic schema evolution as features were added phase by phase. Each is a DDL patch on a mutable schema. A fully event-sourced system would project the same information from its event log without DDL — new views of state are new reducers registered against existing streams.

Future work may explore replacing `cerebra.db` with Rust-native projections built on fossic streams (removing the dual-write burden, WAL discipline, M018-style FK workarounds, and migration debt) but this is not planned for v0.5.x.

### Fossic as optional dependency

Cerebra runs standalone against SQLite alone. FossicStore is optional and unlocked by installing the `fossic` extra:

```
pip install cerebra[fossic]
```

Commands that require fossic (`run-cycle`, `serve`) will fail at startup with a clear message if the extra isn't installed. Commands that work without fossic (`init`, `ingest`, `search`, `classify`, etc.) are unaffected.

This choice keeps the base install lightweight while enabling the full inspector event trail when needed.

---

## Repository Structure

```
cerebra/
├── cli/                      # 21-command Click group (main, daemon, inspect, lockfile)
├── cognition/                # CycleRuntime, ClutchEngine, CatalystEngine, signal evaluators,
│                             # TruthTower, re-injection, EpisodeWriter, WM session manager
├── sources/                  # SourceRegistry, type detector, content-hash change detection
├── ingestion/                # Parser dispatch, chunking pipeline
├── retrieval/                # Hybrid retrieval, ContextPacket builder, salience scoring
├── storage/                  # SQLiteStore, FossicStore, embeddings, FTS5, graph, artifacts
└── _primitives/              # Vendored shared primitives: Clutch, Triangulator, Trajectory,
                              # HysteresisModeRouter, ScoreComposer, BanditSelector, TombstoneSet
cycles/
├── simple.planning.v0.yaml       # 5-step planning cycle (no catalyst)
└── planning.adaptive.v0.yaml     # 5-step planning + 5 catalyst arms + re-injection trigger
docs/
├── HISTORY.md                # This document
├── ARCHITECTURE.md           # Architecture overview
├── ARCHITECTURE_STATE.md     # Per-subsystem technical state reports
├── SETUP.md                  # Setup instructions
├── KNOWN_ISSUES.md           # Tracked open issues
└── TECH_DEBT.md              # Tracked debt and deferred work
examples/
└── docs/                     # Demo vault documents
tests/                        # Unit + integration test suite
```

---

## Setup and Usage

See [`SETUP.md`](SETUP.md) for setup instructions and prerequisites.

**Quick start:**

```bash
uv sync --extra dev --extra fossic
cerebra init ~/my-vault
cerebra ingest ~/my-vault/docs --vault ~/my-vault
cerebra run-cycle simple.planning.v0 --goal "your goal" --vault ~/my-vault
cerebra inspect cycle show <cycle_id> --signals --vault ~/my-vault
```

**Prerequisites:** Python 3.12+, Ollama running locally (e.g. `ollama pull granite3.2:3b`).

---

## Related

- **[fossic](https://github.com/bitmosh/fossic)** — the content-addressed event store substrate (v1.8.3+)
- **[lattica](https://github.com/bitmosh/lattica)** — the observability hub Cerebra emits into
