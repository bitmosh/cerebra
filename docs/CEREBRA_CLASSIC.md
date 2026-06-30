# Cerebra Classic

Cerebra Classic is the pre-dyson-sphere baseline of Cerebra — a local-first cognitive runtime that executes structured multi-step reasoning cycles against a personal knowledge vault. This repository preserves the complete system at `v0.4.4-pre-dyson`, tagged 2026-06-21 immediately following the fossic v1.6.0 substrate release.

It is **runnable**, **inspectable**, and **citable** as a working reference implementation of an event-sourced federated cognitive architecture.

---

## What Cerebra Is

Cerebra is a configurable cognitive cycle runtime. It is not a RAG pipeline or a chatbot wrapper. The central idea is a closed-loop cognitive engine: each step retrieves context from a vault of ingested knowledge, calls a local LLM via Ollama, evaluates the output across six epistemic signals, routes the next action through a rule engine (Clutch), optionally escalates to a bandit-driven strategy selector (Catalyst), writes the result as a dual-format episode, and decides whether to continue, recurse, or stop.

Every cognitive action leaves behind structured state: input, context, output, signal scores, control decision, memory write, and graph event. Nothing happens without a trace.

### Core capabilities at v0.4.4

- **Vault management** — initialize and maintain a local vault with full content-addressed provenance
- **Source ingestion** — parse and chunk markdown and plain text; generate embeddings; build FTS5 index
- **Hybrid retrieval** — lexical (FTS5), vector (cosine), SKU-addressed, graph-expanded; component-scored composite
- **Cognitive cycle runtime** — configurable YAML-defined cycles with N steps, stop conditions, and clutch actions
- **Six epistemic signal evaluators** — coherence, groundedness, relevance, precision, generativity, epistemic humility
- **Clutch controller** — priority-rule action router with hysteresis, mode persistence, and cascade depth
- **Catalyst / strategy selector** — bandit-driven arm selection over five cognitive strategy arms
- **Working memory + TruthTower** — bounded contested attention slots; five-tier derived workspace (T1 Evidence → T5 Goal)
- **Re-injection loop** — continuation bundles enable cognitive continuity across context window limits
- **Dual-format episode persistence** — cycle outputs written to both SQLite (retrievable) and FossicStore (event-chained)
- **Lifecycle management** — archive, tombstone, restore on memory records with stale detection
- **Graph export** — cerebra/v1 JSON for downstream visualization
- **Inspector CLI** — forensic query surface for sessions, cycles, signals, leeway, and events
- **Leeway network** — three-tier safety architecture (constitutional, capability, conditional leeway grants)
- **HTTP daemon** — `cerebra serve` for tile-integrated usage

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
`cerebra export graph` produces cerebra/v1 JSON for downstream visualization. `GraphSnapshotAvailable` event emitted on `cerebra/graph/<lineage_id>` fossic stream. Hub-direct emission path for multi-process scenarios.

**Phase 13 (v0.4.3) — Inspector CLI**
`cerebra inspect` command group: `session list`, `cycle show <id> [--signals]`, `query [--event-type] [--signal-low] [--tail]`, `leeway active`. Forensic observability over both the SQLite inspector events table and the FossicStore event streams.

**Phase 14 (v0.4.4) — Integration testing and polish**
Full E2E spine test against real Ollama. CORS header added to daemon `_send_json` for Tauri webview integration. `cerebra-relay.py` relay agent for vault-to-hub emission. v0.1 ship gate passed.

---

## Current State

**Version:** v0.4.4 / tag `v0.4.4-pre-dyson`

**What is shipped and tested:**
- All 14 build phases complete
- 21-command CLI covering the full surface (init, ingest, search, context, run-cycle, consolidate, export, inspect subgroup, serve)
- Dual storage operational: SQLite (18 migrations) + FossicStore causation-chained event streams
- E2E integration tests pass against real Ollama
- Graph export producing visualization-compatible JSON
- Inspector CLI with full event, session, cycle, and leeway observability
- HTTP daemon with CORS for Tauri webview consumption

**Known open items (non-blocking for v0.1):**

| ID | Item | Trigger |
|---|---|---|
| TD-001 | Purge workflow audit path — `_fossic/system` stream not yet consumed | When any purge workflow is implemented |
| TD-002 | LoRA training for signal evaluators — using prompt-only Granite 4.1 3B Instruct | When corpus imbalance addressed + instruct distillation prepared |
| TD-003 | Lattica primitives PyPI extraction — currently vendored in `_primitives/` | When 2+ stable consumers + 90-day stability criterion cleared |
| TD-012 | Constitutional pre-action rule shape — `forbids()` always returns False | When a real pre-action safety case emerges |
| TD-013 | HITL review flow — `requires_review` field unpopulated | When v0.2 HITL design begins |
| TD-018 | Click `mix_stderr=False` compat — affects 39 tests in 3 files | On next Click version upgrade |
| TD-019 | `test_lattice_against_vault.py` vault-disk failure — root cause uninvestigated | When adjacent vault test infrastructure changes |

Deferred future directions (FD-001 through FD-006 in `docs/archive/DEVELOPMENT_LOG.md`) cover dark matter substrate, witness layer projections, counterfactual branching, cognitive extensions, and cross-stream causation anchoring — all post-v0.1 work with no blocking dependency on Classic.

---

## Why This Is Archived as Classic — The SQLite Mismatch

Cerebra Classic uses a dual persistence strategy:

1. **`cerebra.db` (SQLite)** — a mutable relational store holding memory records, retrieval traces, working memory state, signal evaluations, sessions, predictions, and cycle episodes. Schema evolution requires explicit `ALTER TABLE` DDL through 18 sequential migrations.

2. **`.fossic/store.db` (FossicStore)** — a content-addressed, causation-chained event store backed by Rust. Every state transition is an immutable event with a deterministic hash ID. State is derived by replaying event streams. This is the classical event-sourcing model.

**The fundamental tension:** SQLite and FossicStore approach state at opposite poles. SQLite is a mutable CRUD store — the current state *is* the table rows. FossicStore is append-only — the current state is a *projection* derived from event replay. Coexistence creates friction at multiple points:

**WAL discipline.** Inspector event writes must happen *after* `conn.close()` on any connection that just modified related tables. This prevents "database is locked" errors under SQLite's WAL concurrency model. This discipline is hand-enforced across `TruthTower`, `LifecycleManager`, and other modules — essentially a distributed coordination protocol implemented by convention rather than by the storage engine.

**Synthetic provenance sentinels (M018).** Cycle episodes have no real source file — they are outputs of cognitive cycles, not ingested documents. SQLite's FK constraints on `memory_records` require valid `(source_id, document_id, chunk_id)` references for every row. The workaround: insert three fake sentinel rows at migration time so episode inserts satisfy the FK constraints without violating them semantically. In a pure event-sourced system, episodes are just events on a stream. There are no FK constraints to satisfy because there is no relational schema.

**Dual-write burden.** Every meaningful state change requires both a SQLite write (current state) and a FossicStore append (event history). These two writes must remain consistent without a distributed transaction primitive. The system manages this through careful sequencing and the inspector-event-after-close pattern, but the coupling is real and every new subsystem must be designed around it.

**Schema migration accumulation.** The 18 migrations reflect organic schema evolution as features were added phase by phase. Each is a DDL patch on a mutable schema. A fully event-sourced system projects the same information from its event log without DDL — new views of state are new reducers registered against existing streams.

**The dyson sphere migration** replaces `cerebra.db` with Rust-native projections built on fossic streams. The memory substrate, retrieval traces, session state, and lifecycle state become projections of the event log rather than independent tables. This eliminates the dual-write burden, WAL discipline requirements, M018-style FK workarounds, and migration debt in one architectural move.

**Why Classic remains a working model:**

The SQLite layer doesn't make the system *incorrect* — it makes the architecture *less coherent*. Every cognitive primitive in Cerebra Classic (Clutch, Catalyst, ContinuationBundle, TruthTower, signal evaluators, leeway network) is fully implemented, tested against real Ollama, and inspectable. The system demonstrates that an event-sourced federated cognitive runtime is buildable with this component set, and it demonstrates the right component set to build.

Classic is preserved so the *before* state remains empirically inspectable. The same vault runs on both Classic and post-dyson Cerebra. The cognitive architecture is identical; only the persistence substrate differs. This makes it possible to compare the two states concretely rather than speculatively — and to understand precisely what the dyson sphere migration buys.

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
├── CEREBRA_CLASSIC.md        # This document
├── ARCHITECTURE.md           # Current architecture reference
└── archive/                  # Compressed historical docs
    ├── DESIGN_SPECS.md       # Pre-build design specs and architectural exploration
    ├── DEVELOPMENT_LOG.md    # Phase close docs, deviations, aseptic artifacts, workflows
    └── STATE_REPORTS.md      # Per-subsystem technical state reports (v0.4.4 snapshot)
examples/
└── docs/                     # Demo vault documents
```

---

## Setup and Usage

See `README_CEREBRA_ORIGINAL.md` for complete setup instructions.

**Quick start:**

```bash
uv sync --extra dev
cerebra init ~/my-vault
cerebra ingest ~/my-vault/docs --vault ~/my-vault
cerebra run-cycle simple.planning.v0 --goal "your goal" --vault ~/my-vault
cerebra inspect cycle show <cycle_id> --signals --vault ~/my-vault
```

**Prerequisites:** Python 3.12+, Ollama running locally (e.g. `ollama pull granite3.2:3b`).

---

## Related

- **[fossic](https://github.com/bitmosh/fossic)** — the content-addressed event store substrate (v1.6.0 shipped 2026-06-21, concurrent with this archive)
- **[Cerebra](https://github.com/bitmosh/cerebra)** — active development, post-dyson-sphere evolution
