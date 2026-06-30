# Cerebra Classic — Architecture Reference

Current as of v0.4.4-pre-dyson. This is a technical reference for the implemented system. For the narrative of why this architecture exists and where it is going, see `CEREBRA_CLASSIC.md`.

---

## System Topology

```
vault/
  cerebra.db           — SQLite (WAL): memory, retrieval, WM, signals, sessions, episodes
  .fossic/store.db     — FossicStore: content-addressed causation-chained event streams
  .cerebra/graph.json  — exported knowledge graph (cerebra/v1 JSON)
  data/                — artifact files (parsed doc JSON, raw text)
  cycles/              — user-defined cycle configs (YAML)
```

**Core pipeline:**
```
ingest_path
  → SourceRegistry (change detection)
  → Parser (markdown/text)
  → Chunker
  → SQLiteStore (memory_records)
  → Embedder (pending queue → drain)
  → FTS5 index build

query
  → HybridRetrieval (lexical + vector + SKU + graph expansion)
  → SalienceScoring (composite: semantic + lexical + SKU + recency + lifecycle)
  → ContextPacket (records + WM state + cycle instructions + token budget)

run-cycle
  → CycleRuntime (step loop)
    → ContextPacket build
    → LLM call (Ollama)
    → SignalEvaluator (6 signals)
    → PredictionEngine (expected vs actual)
    → ClutchEngine (rule-based action router)
    → [CatalystEngine (bandit arm selector)]
    → [ReinjectionTriggerEvaluator → ContinuationBundle → child session]
    → EpisodeWriter (cycle_episode_records → memory_records)
    → FossicStore.append (agent-trace stream)
    → LeewayPreActionGate (pre-action permission check)
```

---

## CLI Surface

Entry point: `cerebra.cli.main:cli` — 21-command Click group.

| Command | What it does |
|---|---|
| `init <vault>` | Initialize vault directory + run migrations |
| `ingest <path>` | Register sources, parse, chunk, embed, index |
| `search <query>` | Lexical + vector search over memory records |
| `context <query>` | Build and print a ContextPacket |
| `run-cycle <config>` | Execute a cognitive cycle with a goal |
| `serve` | Start HTTP daemon (DaemonState, CORS headers) |
| `export graph` | Write `.cerebra/graph.json`; emit GraphSnapshotAvailable |
| `consolidate` | Promote cycle episodes to memory records |
| `inspect session list` | List runtime sessions |
| `inspect cycle show <id>` | Show cycle detail, optionally with signals |
| `inspect query` | Query inspector events (--event-type, --signal-low, --tail) |
| `inspect leeway active` | Show active leeway grants |

Vault locking: `cli/lockfile.py` provides `vault_lock(vault_path)` context manager (`.lock` file) to prevent concurrent vault access from multiple processes.

---

## Storage Layer

### SQLite (`cerebra/storage/db.py`)

All connections use `connect(db_path)` factory. Applied pragmas per connection:
- `journal_mode=WAL` — concurrent readers + one writer
- `foreign_keys=ON` — enforces FK constraints
- `synchronous=NORMAL` — durability / write speed balance
- `row_factory = sqlite3.Row` — rows accessible as dicts

**WAL discipline:** Inspector event writes must occur *after* `conn.close()` on any connection that modified related tables. Enforced by pattern in `TruthTower`, `LifecycleManager`, and other dual-write modules.

### Migration summary (M001–M018)

| # | Tables | Phase |
|---|---|---|
| M001 | `inspector_events`, `sources`, `documents`, `chunks`, `memory_records` | 1 |
| M002 | `sku_assignments` | 2 |
| M003 | `embeddings`, `pending_embeddings` | 3 |
| M004 | `index_state` | 3 |
| M005 | `graph_nodes`, `graph_edges` | 4 |
| M006 | `retrieval_traces`, `retrieval_steps`, `retrieval_candidates` | 5 |
| M007 | `sessions` | 5 |
| M008 | `working_memory_items` | 5 |
| M009 | `truth_tower_items` | 5 |
| M010 | `evaluations` | 6 |
| M011 | `predictions`, `outcomes` | 6 |
| M012 | `runtime_sessions` | 7 |
| M013 | `continuation_bundles` | 8 |
| M014 | `cycle_episode_records` | 8 |
| M015–M017 | ADD COLUMN `is_lattice_member`, `lattice_lineage_id`, `lattice_confidence` to `memory_records` | 10 |
| M018 | Synthetic provenance sentinels (`src_synthetic`, `doc_synthetic`, `chk_synthetic`) | 10 |

### FossicStore (`cerebra/storage/fossic_store.py`)

Wraps `fossic.Store` — content-addressed, causation-chained event store.

Key methods: `append(stream_id, event_type, payload, causation_id, indexed_tags)` → bytes (content-addressed event ID). `read_events(stream_id, stream_pattern, event_type, branch, from_version)`. `register_reducer(stream_pattern, reducer)` / `read_state(stream_id)`.

| Stream | Content |
|---|---|
| `cerebra/agent-trace/<session_id>` | Full per-session cycle event chain |
| `cerebra/control` | Daemon posture events |
| `cerebra/lattice/<lineage_id>` | Lattice classification events |
| `cerebra/graph/<lineage_id>` | `GraphSnapshotAvailable` (hub-direct) |

**DEV-005 — CCE dedup:** FossicStore deduplicates identical `(event_type + payload + causation_id)` tuples. `EventEmitter` varies causation_id automatically via chaining.

---

## Source Ingestion (`cerebra/sources/`, `cerebra/ingestion/`)

`register_source()` returns one of `NEW` / `SKIPPED_UNCHANGED` / `CHANGED`. On `CHANGED`: updates content hash, marks associated docs/chunks/records stale, emits `SourceChanged`. On `NEW`: inserts and emits `SourceRegistered`.

`source_id`: `"src_" + sha256(canonical_path)[:16]` — stable across re-ingests as long as path doesn't change.

Type detection (`detector.py`) returns `DetectionResult(detected_type, detection_confidence, parser_adapter)`. Supported: `"markdown"`, `"text/plain"`.

Chunking produces `Chunk(chunk_id, document_id, source_id, content, chunk_index, token_estimate)` records inserted in batch.

---

## SKU Addressing (`cerebra/cognition/sku_classifier.py`)

10-digit address encoding cognitive shape: `<location><entry><tags>`. Classified across 16 quadrant categories derived from 4 orientations × 4 cognitive dimensions. Classifier uses LLM prompt to assign quadrant + subcategory with a confidence score.

`sku_address` is NULL on records until `cerebra classify` runs the classifier pass. Assigned addresses enable shape-based retrieval fanout alongside lexical and vector paths.

---

## Retrieval (`cerebra/retrieval/`)

**Hybrid retrieval modes:** `lexical` (FTS5 MATCH), `vector` (cosine over mxbai-embed-large-v1 1024-dim blobs), `hybrid` (both + deduplication).

**Component scoring per candidate:**
- `semantic_score` — cosine similarity
- `lexical_score` — negated FTS5 rank
- `sku_match_score` — SKU address overlap
- `recency_score` — recency decay
- `lifecycle_score` — penalizes archived/tombstoned records
- `composite_score` — weighted sum

**Retrieval trace:** Every retrieval records `retrieval_traces` → `retrieval_steps` → `retrieval_candidates` with exclusion reasons for non-selected candidates.

**ContextPacket:** Assembled from selected records + working memory state + cycle instructions + token budget + retrieval trace reference.

---

## Cognition Runtime (`cerebra/cognition/`)

### CycleRuntime (`cycle_runtime.py`)

Executes YAML-defined cycle configs. A config specifies: `cycle_id`, `purpose`, step list (each with `name`, `prompt_template`, `max_steps`, `stop_conditions`), `clutch_rules`, `catalyst_arms` (optional), `reinjection_trigger` (optional), `max_recursion_depth`.

Step loop per step:
1. Build ContextPacket from retrieval + WM state
2. `LeewayPreActionGate.evaluate()` — permission check
3. LLM call (Ollama) with prompt + context
4. `SignalEvaluator.evaluate()` → 6 scores
5. `PredictionEngine` — record prediction + compute error
6. `ClutchEngine.decide()` → `ClutchDecision(action, confidence, mode, ...)`
7. If action == `escalate`: `CatalystEngine.select_arm()` → `CatalystDecision`
8. `EpisodeWriter.write()` → `cycle_episode_records` + `memory_records` (via synthetic FK sentinels)
9. `EventEmitter.emit(event_type, payload)` → FossicStore append on agent-trace stream
10. Check stop conditions / continue

### ClutchEngine (`clutch.py`)

Six predicate types evaluated in priority order:
- `signal_floor(signal, threshold)` — fire if signal drops below threshold
- `signal_ceiling(signal, threshold)` — fire if signal exceeds threshold
- `threshold_window(signals, window)` — fire on composite score in range
- `step_count(n)` — fire after N steps
- `mode_persistence(mode, min_steps)` — fire if current mode held for min_steps
- `truth_tower_occupation(tier, condition)` — fire on TruthTower tier state

Hysteresis: mode changes require confidence delta to prevent flapping. Cascade depth limits nested clutch escalations. `escalate` action hands control to Catalyst.

### CatalystEngine (`catalyst.py`)

Wraps `BanditSelector` (epsilon-greedy + UCB1 over `cerebra/agent-trace` stream history) across five arms: `explore`, `refine`, `disrupt`, `structure`, `memory_integration`. Arm selection informed by prior signal trajectory (Triangulator), recency (Trajectory), and score composition (ScoreComposer). Prediction error feeds arm reward updates.

### ReinjectionTriggerEvaluator (`reinjection.py`)

Evaluated when cycle reaches terminal condition (e.g., `cap_reached` with no accepted step). Predicate list from cycle config. On trigger: `BundleDistiller.distill()` builds `ContinuationBundle` (distilled goal, summarized prior, TruthTower projection, insights, next focus, open questions, constraints), written to `continuation_bundles` table and `.to_prompt_prefix()` primes child session. Child session spawned via `SessionManager.open_session(parent_session_id=...)` at `recursion_depth + 1`.

### Signal Evaluators (`cognition/signal_prompts/`)

Six evaluators, each in `cerebra/cognition/signal_prompts/<signal>_v1.py`:
- `coherence_v1` — logical consistency of the step output
- `groundedness_v1` — grounding in retrieved evidence
- `relevance_v1` — relevance to the current goal
- `precision_v1` — specificity and lack of vagueness
- `generativity_v1` — novelty and generative value
- `epistemic_humility_v1` — appropriate uncertainty acknowledgment

Each scores 0.0–1.0 via LLM call. Composite score is a weighted average. Scores persisted in `evaluations` table. Low scores on named signals are queryable via `cerebra inspect query --signal-low <SIGNAL> --threshold <t>`.

---

## Working Memory and TruthTower (`cognition/session.py`, `cognition/lattice.py`)

### WorkingMemorySession

Bounded contested attention slots per session. Items: active task, current goals, active hypotheses, selected memories, recent outputs, open contradictions, pending questions. Slot competition: lower-salience items evicted when slots fill. Items persisted to `working_memory_items` table.

### TruthTower

Five-tier derived cognitive workspace:
- **T1 Evidence** — retrieved records, source-grounded
- **T2 Memories** — selected working memory items
- **T3 Insights** — evaluated step outputs (signal-scored)
- **T4 Hypotheses** — active hypotheses under evaluation
- **T5 Goal** — current cycle goal

TruthTower items persisted to `truth_tower_items` table. Tower state is serialized into `ContinuationBundle.truth_tower_projection` for re-injection.

---

## Memory Lifecycle (`cerebra/storage/lifecycle.py`)

Three active lifecycle states on `memory_records.lifecycle_state`:
- `active` — default, included in retrieval
- `archived` — deprioritized, not in default retrieval
- `tombstoned` — excluded from all retrieval, marker preserved for provenance

Tombstones are never deleted — they prevent accidental resurrection without breaking the provenance chain. Lifecycle transitions cascade from sources → documents → chunks → records when a source is detected as `CHANGED`.

---

## Leeway Network (`cerebra/cognition/clutch.py` / `LeewayPreActionGate`)

Three-tier safety architecture:
1. **Constitutional layer** — `ConstitutionalRule.forbids()` evaluated pre-action. Always returns False in v0.1 (DEV-009 — no rules designed yet). Inviolable when populated.
2. **Capability bounds** — structural: does an adapter for this action type exist?
3. **Leeway grants** — conditional: current WM/TruthTower state permits this action?

`GateDecision.review_required_by` exists but is never populated in v0.1 (TD-013 — no HITL flow). All decisions are two-state: permitted / forbidden.

`LeewayGrantApplied` event emitted on the agent-trace stream for every gate decision.

---

## Graph Export (`cerebra/cli/main.py` → `GraphStore` + `FossicStore`)

`cerebra export graph` writes `.cerebra/graph.json` from `graph_nodes` and `graph_edges` tables (populated by ingest and episode writer). Also emits `GraphSnapshotAvailable` on `cerebra/graph/<lineage_id>` fossic stream.

Export format (cerebra/v1 JSON):
```json
{
  "version": "cerebra/v1",
  "nodes": [{"node_id": "...", "node_type": "...", "label": "...", "data": {...}}],
  "edges": [{"edge_id": "...", "source": "...", "target": "...", "edge_type": "...", "weight": 1.0}]
}
```

---

## Vendored Primitives (`cerebra/_primitives/`)

Seven shared primitives vendored from the Lattica primitive set. Planned extraction to `lattica-primitives` PyPI package post two-stable-consumer + 90-day stability criterion (TD-003).

| Primitive | Role |
|---|---|
| `Clutch` | Priority-rule controller base (ClutchEngine extends this) |
| `Triangulator` | Multi-dimensional score triangulation for Catalyst |
| `Trajectory` | Recency-weighted signal trajectory tracker |
| `HysteresisModeRouter` | Mode persistence with anti-flapping |
| `ScoreComposer` | Weighted composite score builder |
| `BanditSelector` | Epsilon-greedy + UCB1 bandit for arm selection |
| `TombstoneSet` | Deduplication-safe seen-set for lifecycle management |

---

## Inspector Events

All modules emit structured events to `inspector_events` (SQLite) AND as FossicStore appends on the agent-trace stream. Queryable via `cerebra inspect query`.

Key event types:

| Event type | Emitter |
|---|---|
| `SourceRegistered` / `SourceChanged` | SourceRegistry |
| `LexicalIndexUpdated` | `lexical.build_fts_index` |
| `CycleStarted` / `CycleCompleted` | CycleRuntime |
| `StepExecuted` | CycleRuntime (per step) |
| `ContextPacketBuilt` | ContextPacket builder |
| `SignalEvaluated` | SignalEvaluator |
| `ClutchDecisionIssued` | ClutchEngine |
| `PredictionMade` / `PredictionErrorRecorded` | PredictionEngine |
| `LeewayGrantApplied` | LeewayPreActionGate |
| `MemoryConsolidated` | EpisodeWriter (on promotion) |
| `GraphSnapshotAvailable` | export graph command |
| `PostureChanged` | Daemon |
