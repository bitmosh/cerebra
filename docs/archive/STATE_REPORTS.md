# Cerebra Classic — Per-Subsystem State Reports

Authoritative technical state snapshots at v0.4.4-pre-dyson. Generated from implementation evidence, not from design docs.


---
<!-- source: state-reports/01_system_overview.md -->

# Cerebra — System Overview

**Version:** v0.4.4 | **Python:** ≥3.12 | **Entry point:** `cerebra.cli.main:cli`

---

## 1. What Cerebra Is

Cerebra is a local-first cognitive runtime that executes structured multi-step reasoning cycles against a personal vault of ingested knowledge. It is not a general-purpose RAG pipeline or a chatbot wrapper. It is a closed-loop cognitive engine: each step retrieves context from the vault, calls an LLM, evaluates the output across six epistemic signals, routes the next action through a rule engine (Clutch), optionally escalates to a bandit-driven strategy selector (Catalyst), writes the output as a dual-format episode, and decides whether to continue, recurse, or stop.

The system is designed to run locally with Ollama as its LLM backend and Fossic as its event store. All data — vault records, retrieval traces, session state, cognitive episodes, signal evaluations — lives on disk under a vault directory the user controls.

---

## 2. Repository Topology

```
/home/boop/Projects/cerebra/
├── pyproject.toml                      # build, deps, tool config
├── cerebra-relay.py                    # relay agent: vault → hub (not a package module)
├── cycles/
│   ├── simple.planning.v0.yaml         # 5-step planning cycle, no catalyst
│   └── planning.adaptive.v0.yaml       # 5-step planning, 5 catalyst arms, 1 reinjection trigger
├── cerebra/
│   ├── cli/
│   │   ├── main.py                     # 21-command Click group
│   │   ├── daemon.py                   # HTTP serve command + DaemonState
│   │   ├── inspect.py                  # inspect subcommand handlers
│   │   └── lockfile.py                 # vault_lock() context manager
│   ├── cognition/
│   │   ├── _constants.py               # compile-time constants
│   │   ├── cycle_runtime.py            # CycleRuntime — main step loop
│   │   ├── cycle_config.py             # CycleConfig loader
│   │   ├── clutch.py                   # ClutchEngine — rule-based action router
│   │   ├── catalyst.py                 # CatalystEngine — bandit strategy selector
│   │   ├── evaluation.py               # EvaluationComposer — weighted signal → packet
│   │   ├── signals.py                  # 6 signal evaluators
│   │   ├── llm_adapter.py              # OllamaDirectAdapter + ProxyLLMAdapter
│   │   ├── working_memory.py           # WorkingMemory — LRU attention store
│   │   ├── truth_tower.py              # TruthTower — T1/T2 promoted knowledge
│   │   ├── session.py                  # RuntimeSession + SessionManager
│   │   ├── predictions.py              # PredictionPipeline
│   │   ├── episode_writer.py           # EpisodeWriter — dual-write cycle output
│   │   ├── stop_conditions.py          # StopConditionEvaluator
│   │   ├── reinjection.py              # ReinjectionTriggerEvaluator
│   │   ├── continuation_bundle.py      # ContinuationBundle + BundleDistiller
│   │   ├── event_emitter.py            # EventEmitter — fossic stream writer
│   │   ├── sku.py                      # SKUAddress + SKUAssignment
│   │   ├── sku_categories.py           # D1Category enum (16 values)
│   │   ├── sku_classifier.py           # SKUClassifier — two-pass LLM classifier
│   │   ├── sku_relationships.py        # SKU relationship helpers
│   │   ├── lattice.py                  # evaluate_lattice() + LatticeDecision
│   │   └── signal_prompts/             # 6 prompt files (one per signal)
│   │       ├── coherence.txt
│   │       ├── groundedness.txt
│   │       ├── generativity.txt
│   │       ├── relevance.txt
│   │       ├── precision.txt
│   │       └── epistemic_humility.txt
│   ├── governance/
│   │   ├── defaults.py                 # 15 LR rules + 5 CONST rules at vault init
│   │   ├── models.py                   # LeewayRule + ConstitutionalRule dataclasses
│   │   ├── pre_action_gate.py          # LeewayPreActionGate
│   │   ├── types.py                    # ProposedAction + GateDecision
│   │   └── loader.py                   # Rule loader from vault YAML
│   ├── inspector/
│   │   ├── event.py                    # InspectorEvent dataclass + make_event()
│   │   ├── sqlite_log.py               # SQLiteEventLog (inspector_events table)
│   │   └── ndjson_log.py               # NDJSONEventLog (line-atomic append)
│   ├── storage/
│   │   ├── db.py                       # connect() factory (WAL, FK, Row factory)
│   │   ├── migrations.py               # 18 forward-only migrations
│   │   ├── fossic_store.py             # FossicStore wrapper
│   │   ├── sqlite_store.py             # SQLiteStore (documents, chunks, records)
│   │   ├── embeddings.py               # drain_pending, cosine_search
│   │   ├── lexical.py                  # FTS5 build_fts_index, search
│   │   ├── artifact_store.py           # write_artifact, write_text_artifact
│   │   ├── graph_store.py              # upsert_node, upsert_edge
│   │   └── index_state.py              # is_lexical_stale, update_index_state
│   ├── retrieval/
│   │   ├── planner.py                  # RetrievalPlanner — mode + QueryPlan
│   │   ├── traversal.py                # RetrievalTraversal — 6-step traversal
│   │   ├── scorer.py                   # CompositeScorer — salience formula
│   │   ├── context_packet.py           # build_context_packet, ContextPacket
│   │   ├── trace.py                    # retrieval trace write helpers
│   │   └── lattice_dedup.py            # dedup_siblings + D2 routing
│   ├── memory/
│   │   ├── lifecycle.py                # LifecycleManager — state machine
│   │   └── records.py                  # MemoryRecord + build_record()
│   ├── ingest/
│   │   ├── pipeline.py                 # ingest_path() — per-file pipeline
│   │   ├── chunking.py                 # chunk_document()
│   │   ├── normalization.py            # text normalization helpers
│   │   ├── models.py                   # IngestReport, Chunk, ParseResult
│   │   └── adapters/
│   │       ├── base.py                 # BaseAdapter ABC
│   │       ├── markdown.py             # MarkdownAdapter
│   │       └── text.py                 # TextAdapter
│   ├── sources/
│   │   ├── registry.py                 # SourceRecord + register_source()
│   │   ├── detector.py                 # detect_type() → DetectionResult
│   │   ├── discovery.py                # discover_files()
│   │   └── hashing.py                  # content_hash()
│   ├── graph/
│   │   ├── model.py                    # ExportStats dataclass
│   │   └── exporter.py                 # export_graph()
│   ├── vault/
│   │   └── init.py                     # init_vault()
│   └── config.py                       # resolve_vault(), set/get_config_vault()
├── tests/
│   ├── unit/                           # ~75 test files
│   ├── integration/                    # ~25 test files
│   ├── fixtures/                       # shared fixture data
│   └── conftest.py
└── docs/
    ├── state-reports/                  # this directory
    └── ...
```

---

## 3. Build & Package Configuration

### pyproject.toml — core fields

```toml
[project]
name = "cerebra"
version = "0.4.4"
requires-python = ">=3.12"

[project.scripts]
cerebra = "cerebra.cli.main:cli"

[project.dependencies]
pydantic = ">=2.7"
pyyaml = ">=6.0"
click = ">=8.1"
numpy = ">=2.0,<3.0"
sentence-transformers = ">=3.0"
fossic = {path = "/home/boop/Projects/fossic/fossic-py"}   # local editable dep
```

### Dev dependencies

```toml
[tool.uv.dev-dependencies]
pytest = ">=8.2"
pytest-cov = ">=5.0"
ruff = ">=0.4"
black = ">=24.4"
mypy = ">=1.10"
types-PyYAML = ">=6.0"
pre-commit = ">=3.7"
```

### Test configuration

```toml
[tool.pytest.ini_options]
markers = [
    "unit: fast, in-memory, no ML models",
    "integration: temp vault + real SQLite + Ollama + ML models (~1.5 GB)",
]
addopts = "--cov=cerebra --cov-fail-under=80"
```

Coverage omits: `__init__.py`, `_primitives_canonical/*`

### Mypy (strict)

```toml
[tool.mypy]
strict = true
warn_return_any = true
no_implicit_reexport = true
```

### Ruff

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM"]
ignore = ["E501"]
line-length = 100
```

---

## 4. Vault Resolution

All CLI commands and the daemon resolve the vault path through the same priority chain:

```
1. --vault <path>         (CLI flag, highest priority)
2. CEREBRA_VAULT env var  (shell environment)
3. ~/.config/cerebra/config.toml  [defaults] vault  (user config)
4. VaultNotFoundError raised (no fallback)
```

Implementation: `cerebra/config.py:resolve_vault(flag_value=None) → (Path, str)`

The returned `str` is a source description for logging (e.g., `"--vault flag"`, `"CEREBRA_VAULT env"`, `"config file"`).

**CAUTION:** `CEREBRA_VAULT` persists across shell sessions once exported. An incorrect value silently redirects all operations to the wrong vault. Always `unset CEREBRA_VAULT` if vault behavior seems wrong.

---

## 5. Configuration Files

### User config: `~/.config/cerebra/config.toml`

Created by `cerebra config set vault <path>`. Read with stdlib `tomllib` (Python 3.11+, no extra dep).

```toml
[defaults]
vault = "/abs/path/to/vault"
```

The writer preserves any existing keys (does not clobber the whole file).

Config helpers:
- `get_config_vault() → str | None`
- `set_config_vault(path: str) → None`
- `get_all_config() → dict`

### Vault config: `<vault>/config.yaml`

Written at `cerebra init`. Presence of this file is the canonical indicator that a path is a valid vault.

```yaml
cerebra_version: "0.0.0"
schema_version: 1
created_at: <unix_timestamp_int>
vault_path: "/abs/path/to/vault"
```

### Hub store env var

```
CEREBRA_PLATFORM_STORE=<path>   # path to ~/.lattica/fossic/store.db (hub store)
```

Used by: `export_graph()` (hub-direct GraphSnapshotAvailable), the HTTP daemon checkpoint endpoint. When absent, hub-direct writes are silently skipped.

---

## 6. Vault Directory Structure

Created by `init_vault(path, *, force=False)` in `cerebra/vault/init.py`.

```
<vault>/
├── config.yaml                 # vault identity file
├── cerebra.db                  # main SQLite database (WAL mode)
├── .fossic/
│   └── store.db                # Fossic content-addressed event store
├── .cerebra/
│   └── graph.json              # last graph export (cerebra/v1 schema)
├── data/                       # (reserved for future structured data)
├── artifacts/                  # JSON structured artifacts per document
├── indexes/                    # (reserved for future index blobs)
├── exports/                    # (reserved for future export formats)
├── events/
│   ├── ingest.ndjson           # ingest inspector events (NDJSON)
│   ├── system.ndjson           # system inspector events
│   └── classify.ndjson         # classification inspector events
├── leeway/                     # 15 LR rule YAML files written at init
└── constitutional/             # 5 CONST rule YAML files written at init
```

`init_vault` raises `VaultAlreadyExistsError` if `config.yaml` already exists and `force=False`.

Init steps (in order):
1. `mkdir` all subdirectories
2. Write `config.yaml`
3. `run_migrations(db_path)` — creates all SQLite tables
4. `write_defaults_to_vault()` — writes 15 LR + 5 CONST YAML files
5. Write VaultCreated event to both SQLiteEventLog and NDJSONEventLog
6. Write MigrationRun event
7. Write ConfigLoaded event

---

## 7. Two Event Buses

Cerebra maintains two parallel event recording systems with distinct purposes:

### Inspector bus (SQLite + NDJSON)

- **Tables:** `inspector_events` in `cerebra.db`
- **Files:** `vault/events/*.ndjson`
- **Writers:** `SQLiteEventLog`, `NDJSONEventLog`
- **Purpose:** Per-operation observability — ingest, classify, retrieval, lifecycle, graph, governance
- **Event IDs:** `"evt_" + uuid[:12]`
- **Schema version:** 1 (all events)
- **Queried by:** `inspect query`, `inspect session show`, all `inspect` subcommands

### Fossic bus (content-addressed event store)

- **Store:** `<vault>/.fossic/store.db`
- **Writer:** `FossicStore.append()` via `EventEmitter`
- **Purpose:** Audit-grade cognitive trace — causation-chained, content-addressed, append-only
- **Streams:** `cerebra/agent-trace/<session_id>`, `cerebra/control`, `cerebra/lattice/<lineage_id>`, `cerebra/graph/<lineage_id>`
- **Event IDs:** content-addressed bytes (fossic internal)
- **Queried by:** `inspect session show --events`, `inspect cycle show`, relay agent, Lattica tiles

These two buses are written to independently. The same logical event (e.g., `ContextPacketBuilt`) may appear in both, with the inspector copy carrying richer query metadata and the fossic copy carrying the canonical causation chain.

---

## 8. External Dependencies

| Dependency | Role | Notes |
|---|---|---|
| `fossic` (local) | Content-addressed event store | `file:///home/boop/Projects/fossic/fossic-py`; must reinstall with `--reinstall` after fossic changes |
| `sentence-transformers ≥3.0` | Embedding model loader | Downloads `mxbai-embed-large-v1` (~1.5 GB) on first use |
| `pydantic ≥2.7` | Data validation | Used in cycle config, governance models |
| `pyyaml ≥6.0` | YAML cycle config loading | Cycle files in `cycles/` |
| `click ≥8.1` | CLI framework | `cli` group + all subcommands |
| `numpy ≥2.0,<3.0` | Embedding cosine math | Float32 blob arithmetic |
| `tomllib` (stdlib 3.11+) | Config file reading | No extra dep required |
| Ollama | LLM inference | `http://127.0.0.1:11434` (IPv4 to avoid Docker IPv6 hang) |

---

## 9. Fossic Relay (`cerebra-relay.py`)

Not a package module — a standalone script at the repo root.

**Purpose:** Subscribe to `cerebra/**` streams on the local vault Fossic store and relay selected events to the Lattica hub store (`~/.lattica/fossic/store.db`).

**Stream routing:**
- `cerebra/agent-trace/*` → relay ✓
- `cerebra/lattice/*` → relay ✓
- `cerebra/bot/*` → relay ✓ (post-fold-in, safe when stream exists)
- `cerebra/graph/*` → skip (hub-direct via `export_graph()`, would double-write)
- `cerebra/control` → skip (local-only posture stream)

**Env vars:**
- `CEREBRA_VAULT` → local vault path (falls back to `~/.config/cerebra/config.toml`)
- `CEREBRA_PLATFORM_STORE` → hub store path (falls back to `~/.lattica/fossic/store.db`)

**Run:** `uv run python cerebra-relay.py`

The relay uses Fossic's `RelayAgent` base class (Appendix C pattern). Filtering is entirely via `CerebraRelayAgent._should_relay(event) → bool` — `relay_filter=set()` (empty) so no prefix-based pre-filtering happens at the Fossic layer.

---

## 10. Test Suite Structure

```
tests/
├── unit/           # ~75 files; fast, in-memory, mock LLM where needed
├── integration/    # ~25 files; real vault + real SQLite; some need Ollama running
├── fixtures/       # shared YAML configs, sample markdown files
└── conftest.py     # shared pytest fixtures (temp vault, mock LLM, etc.)
```

**Run unit tests only:**
```bash
uv run pytest -m unit
```

**Run integration tests (requires Ollama + ML model):**
```bash
uv run pytest -m integration
```

**With coverage:**
```bash
uv run pytest --cov=cerebra --cov-report=html
```

Coverage threshold: 80%. Integration tests load the embedding model (~1.5 GB) on first run and cache it in the `sentence-transformers` cache directory.

---
<!-- source: state-reports/02_cli_surface.md -->

# Cerebra — CLI Surface & HTTP Daemon

All commands live under a single `cli` Click group defined in `cerebra/cli/main.py`. Vault resolution applies to every command: `--vault` flag → `CEREBRA_VAULT` env → `~/.config/cerebra/config.toml [defaults] vault` → `VaultNotFoundError`.

---

## 1. Top-Level Commands

### `cerebra init <path>`

Initialize a new vault at `<path>`.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--force` | bool flag | False | Overwrite existing vault (skips VaultAlreadyExistsError) |

Creates vault directory tree, runs 18 migrations, writes 15 LR + 5 CONST governance YAML files, emits VaultCreated/MigrationRun/ConfigLoaded inspector events.

---

### `cerebra ingest <target>`

Ingest files from `<target>` (file or directory) into the vault.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--dry-run` | bool flag | False | Discover + detect without writing anything |
| `--extensions EXT` | str (multi) | all | Restrict to specific extensions (e.g. `--extensions .md --extensions .txt`) |
| `--exclude PATTERN` | str (multi) | none | Glob patterns to exclude |
| `--embed` | bool flag | False | Immediately drain embedding queue after ingest (vs. deferred) |

Prints `IngestReport` fields on completion: sources found/new/changed/skipped/failed, chunks created, records created, errors list.

---

### `cerebra classify`

Run SKU classification backfill on all unclassified memory records (`sku_address IS NULL`).

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--batch-size N` | int | system default | Records to classify per batch |
| `--dry-run` | bool flag | False | Report what would be classified without writing |

Prints `BackfillReport`: records_found, classified, skipped, failed, low_confidence, elapsed_ms.

Each record triggers two LLM calls (quadrant → category). Requires Ollama running at `OLLAMA_BASE_URL`.

---

### `cerebra embed`

Drain the `pending_embeddings` queue (generate vector embeddings for queued records).

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--batch-size N` | int | system default | Records per batch |

Uses `mixedbread-ai/mxbai-embed-large-v1` (1024-dim, float32 LE blob). First run downloads ~1.5 GB model.

---

### `cerebra index`

Full rebuild of the FTS5 lexical index from all active memory records.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |

Drops and recreates `memory_records_fts` from scratch. Safe to run anytime; idempotent. Uses full rebuild even for incremental updates (SQLite 3.45 bug workaround — see doc 03).

---

### `cerebra search <query>`

Run a retrieval query and print ranked results.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--limit N` | int | 10 | Max results to return |
| `--mode MODE` | str | hybrid | `lexical`, `vector`, or `hybrid` |
| `--floor F` | float | 0.35 | Composite score floor for inclusion |
| `--json` | bool flag | False | Output as JSON array |

Does not write anything to the vault. Retrieval trace is not persisted in this mode.

---

### `cerebra context <query>`

Run the full retrieval pipeline and emit a formatted `ContextPacket`.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--limit N` | int | 10 | Max selected_memory items |
| `--floor F` | float | 0.35 | Composite score floor |
| `--promote-t1` | bool flag | False | Promote retrieved items into TruthTower T1 |
| `--session-id ID` | str | None | Required with `--promote-t1` |
| `--json` | bool flag | False | Output ContextPacket as JSON |

Persists a `retrieval_trace` row and associated `retrieval_steps` / `retrieval_candidates` rows even in non-`--json` mode.

---

### `cerebra run-cycle <config>`

Execute a full cognitive cycle.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--goal TEXT` | str | required | Natural language goal for this cycle |
| `--session-id ID` | str | auto-generated | Attach to existing session |

`<config>` is a cycle name (looked up in `cycles/` dir, e.g. `simple.planning.v0`) or a path to a YAML file.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | `accept` — cycle completed with accepted outcome |
| 1 | `stop` / `cap_reached` — stopped by stop condition |
| 2 | `setup_error` — vault init or config load failure |
| 3 | `runtime_failure` — unhandled exception during cycle |

Emits full fossic event stream to `cerebra/agent-trace/<session_id>`.

---

### `cerebra export-graph`

Export the vault knowledge graph to `<vault>/.cerebra/graph.json` (cerebra/v1 schema).

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--out PATH` | Path | `<vault>/.cerebra/graph.json` | Override output path |

If `CEREBRA_PLATFORM_STORE` is set, also emits `GraphSnapshotAvailable` hub-direct to `cerebra/graph/<lineage_id>`. Hub errors are swallowed silently (non-fatal).

---

### `cerebra config get vault`

Print the currently resolved vault path (no flags).

---

### `cerebra config set vault <path>`

Write vault path to `~/.config/cerebra/config.toml`. Preserves all existing TOML keys.

---

### `cerebra serve`

Start the HTTP daemon (see section 3).

| Flag | Type | Default | Description |
|---|---|---|---|
| `--vault PATH` | Path | resolved | Vault root |
| `--host HOST` | str | `127.0.0.1` | Bind address |
| `--port PORT` | int | 7432 | Bind port |

---

## 2. `memory` Subgroup

Eight commands under `cerebra memory`. All require `--vault`.

### `cerebra memory status`

Print current working memory slot-by-slot plus truth tower citation markers.

| Flag | Default | Description |
|---|---|---|
| `--session-id ID` | required | WM session to inspect |
| `--json` | False | JSON output |

---

### `cerebra memory add <text>`

Inject text directly into working memory.

| Flag | Default | Description |
|---|---|---|
| `--session-id ID` | required | Target WM session |
| `--salience F` | system default | Override salience score (0.0–1.0) |

Emits `AttentionItemProposed` → `AttentionItemPromoted` (or `AttentionItemDeferred` if evicted immediately).

---

### `cerebra memory promote <record_id>`

Promote a memory record into the truth tower.

| Flag | Default | Description |
|---|---|---|
| `--session-id ID` | required | Session context |
| `--tier [1\|2]` | 1 | Target tier |
| `--text TEXT` | None | Override content summary |
| `--cite TOWER_ITEM_ID` | None | Required for T2: cite an existing T1 item |
| `--pin` | False | Pin item (prevents capacity eviction) |
| `--salience F` | 0.7 | Salience score for tower placement |

T2 promotion requires `--tier 2 --cite <t1_item_id>`. The cited T1 must exist, be tier=1, and not be evicted (born-stale rejection enforced).

---

### `cerebra memory tombstone <record_id>`

Tombstone a memory record (terminal state — no restore possible).

| Flag | Default | Description |
|---|---|---|
| `--reason TEXT` | None | Reason for tombstoning (stored in DB) |

Emits `MemoryRecordTombstoned`. Removes from FTS5 index if previously active.

---

### `cerebra memory restore <record_id>`

Restore an archived record back to active state.

Only valid for `archived` records. `tombstoned` is terminal.

Emits `MemoryRecordRestored`. Re-inserts into FTS5 index.

---

### `cerebra memory archive <record_id>`

Archive a record (reversible — can be restored).

| Flag | Default | Description |
|---|---|---|
| `--reason TEXT` | None | Reason for archiving |

Emits `MemoryRecordArchived`. Removes from FTS5 index.

---

### `cerebra memory list`

List records by lifecycle state.

| Flag | Default | Description |
|---|---|---|
| `--lifecycle STATE` | `active` | `active`, `archived`, or `tombstoned` |

---

### `cerebra memory show <record_id>`

Show detail for a specific memory record.

| Flag | Default | Description |
|---|---|---|
| `--json` | False | JSON output including all fields |

---

## 3. `inspect` Subgroup

Nine commands under `cerebra inspect`. All require `--vault`. All support `--json` unless noted.

### `cerebra inspect session list`

List all runtime sessions for this vault, DESC by `opened_at`.

Output columns: session_id, cycle_config, goal (truncated), state, opened_at, cycles_run, steps_run.

---

### `cerebra inspect session show <SESSION_ID>`

Show detail for a specific session.

| Flag | Default | Description |
|---|---|---|
| `--events` | False | Also read and print the full Fossic event stream for this session (`cerebra/agent-trace/<session_id>`) |

When `--events` is used, reads from `<vault>/.fossic/store.db` (not the hub store).

---

### `cerebra inspect cycle show <CYCLE_ID>`

Show events from a specific cycle.

| Flag | Default | Description |
|---|---|---|
| `--steps` | False | Include StepStarted/StepExecuted events |
| `--signals` | False | Include SignalEvaluated events |
| `--clutch` | False | Include ClutchDecisionMade events |

Filters the Fossic event stream by `cycle_id` field in payload.

---

### `cerebra inspect memory show <MEMORY_ID>`

Show detail for a memory record from the inspector perspective.

| Flag | Default | Description |
|---|---|---|
| `--history` | False | Show full lifecycle transition history from inspector_events |
| `--graph` | False | Show graph node + edges for this record |

---

### `cerebra inspect retrieval show <RETRIEVAL_ID>`

Show a retrieval trace with optional step and score breakdown.

Queries: `retrieval_traces`, `retrieval_steps`, `retrieval_candidates`.

| Flag | Default | Description |
|---|---|---|
| `--path` | False | Show traversal step path (which of 6 steps contributed candidates) |
| `--scores` | False | Show per-component score breakdown (uses `CompositeScore.explain()`) |

---

### `cerebra inspect leeway active`

Read all `LeewayGrantApplied` events across all sessions in this vault.

---

### `cerebra inspect leeway history <SESSION_ID>`

Show leeway event types (GrantApplied, GrantDenied, RevocationFired) filtered to a specific session.

---

### `cerebra inspect leeway revocations`

Read all `LeewayRevocationFired` events across all sessions.

---

### `cerebra inspect query`

Flexible event query across the inspector_events table.

| Flag | Default | Description |
|---|---|---|
| `--event-type TYPE` | None | Filter to a specific event type string |
| `--signal-low` | False | Show only ClassificationLowConfidence events |
| `--severe-misses` | False | Show only PredictionSevereMiss events |
| `--last N` | 50 | Return last N events (DESC by timestamp) |
| `--cycle CYCLE_ID` | None | Filter by cycle_id |
| `--filter KEY=VALUE` | None (multi) | Filter by payload field (e.g. `--filter source_id=src_abc123`) |
| `--tail` | False | Poll SQLite at 0.5s intervals (live tail mode) |

`--tail` is the primary tool for watching a running cycle in real time.

---

## 4. HTTP Daemon

Defined in `cerebra/cli/daemon.py`. Started by `cerebra serve`.

### Server implementation

```python
class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
```

Handles SIGINT + SIGTERM for graceful shutdown. Binds to `127.0.0.1:7432` by default.

### DaemonState

Shared mutable state, protected by `threading.Lock`:

```python
@dataclass
class DaemonState:
    posture: str                    # "auto" | "hold"
    cycle_thread: Thread | None     # current background cycle thread
    active_session_id: str | None   # session_id of running cycle
    cycle_count: int                # total cycles run since daemon start
    last_outcome: str | None        # last cycle's termination reason
```

### Endpoints

#### `GET /status`

Returns current DaemonState snapshot as JSON. Never blocks.

```json
{
  "posture": "auto",
  "cycle_running": false,
  "active_session_id": null,
  "cycle_count": 3,
  "last_outcome": "accept"
}
```

---

#### `POST /posture`

Set daemon posture. Body: `{"state": "hold" | "auto"}`

- `hold` — refuse new cycle requests (return 409)
- `auto` — accept new cycle requests

Side effect: emits `PostureChanged` to `cerebra/control` Fossic stream with new posture value.

Response: 200 with updated state JSON, or 400 if `state` field invalid.

---

#### `POST /cycles`

Start a background cognitive cycle. Body:

```json
{
  "config_name": "simple.planning.v0",
  "goal": "Natural language goal text"
}
```

**Preconditions (returns 409 if either fails):**
- `posture != "hold"`
- No cycle currently running (`cycle_thread` is None or not alive)

**On accept (202):** Spawns a background thread that calls `CycleRuntime.run()`. Returns:

```json
{
  "session_id": "sess_abc123def456",
  "status": "started"
}
```

The cycle runs to completion in the background. Poll `/status` or `inspect query --tail` to monitor progress.

---

#### `POST /checkpoint`

Distill current session state into a `ContinuationBundle` and persist it.

Steps:
1. `BundleDistiller.distill(parent_session_id, ...)` — builds bundle from current tower + step history
2. `write_bundle(db_path, bundle)` — persists to `continuation_bundles` table
3. Emits `CheckpointSaved` to `cerebra/agent-trace/<session_id>`

Response: 200 with `{"bundle_id": "bundle_abc123", "session_id": "sess_..."}`, or 400 if no active session.

---

## 5. Lockfile

`cerebra/cli/lockfile.py` provides a `vault_lock(vault_path) → contextmanager` that prevents concurrent vault access from multiple processes. Uses a `.lock` file in the vault root. Not yet used everywhere — see `docs/state-reports/03_storage_layer.md` for WAL concurrency notes.

---
<!-- source: state-reports/03_storage_layer.md -->

# Cerebra — Storage Layer

All persistent state lives in `<vault>/cerebra.db` (SQLite, WAL mode) and `<vault>/.fossic/store.db` (Fossic content-addressed store). This document covers every table, the connection factory, all 18 migrations, and the storage module implementations.

---

## 1. Connection Factory (`cerebra/storage/db.py`)

```python
def connect(db_path: Path) -> sqlite3.Connection
```

Applied pragmas (every connection):
- `PRAGMA journal_mode=WAL` — enables concurrent readers + one writer
- `PRAGMA foreign_keys=ON` — enforces FK constraints
- `PRAGMA synchronous=NORMAL` — balances durability vs. write speed
- `row_factory = sqlite3.Row` — all rows accessible as dicts

**Rule:** Every SQLite connection in the codebase must use this factory. Direct `sqlite3.connect()` calls are forbidden — they bypass the WAL + FK setup.

**WAL discipline for inspector events:** All inspector event writes must happen *after* `conn.close()` on any connection that just modified related tables. This prevents "database is locked" under WAL concurrency. Enforced by pattern in `TruthTower`, `LifecycleManager`, and other modules that do a DB write then emit an inspector event.

---

## 2. Migrations (`cerebra/storage/migrations.py`)

```python
def run_migrations(db_path: Path) -> None
```

Idempotent. Tracks applied versions in `applied_migrations` table (created if absent). Runs all unapplied migrations in order. Safe to call on every startup.

### Migration table index

| Migration | Tables Created | Notes |
|---|---|---|
| M001 | `inspector_events`, `sources`, `documents`, `chunks`, `memory_records` | Core schema |
| M002 | `sku_assignments` | Phase 2 SKU classification |
| M003 | `embeddings`, `pending_embeddings` | Phase 3 vector search |
| M004 | `index_state` | FTS5 staleness tracking |
| M005 | `graph_nodes`, `graph_edges` | Phase 4 graph model |
| M006 | `retrieval_traces`, `retrieval_steps`, `retrieval_candidates` | Retrieval audit |
| M007 | `sessions` | Phase 5 WM sessions |
| M008 | `working_memory_items` | Phase 5 attention items |
| M009 | `truth_tower_items` | Phase 5 tower |
| M010 | `evaluations` | Phase 6 signal evaluation |
| M011 | `predictions`, `outcomes` | Phase 6 prediction pipeline |
| M012 | `runtime_sessions` | Phase 7 cycle sessions |
| M013 | `continuation_bundles` | Phase 7 checkpointing |
| M014 | `cycle_episode_records` | Phase 10 episode writer |
| M015 | ADD COLUMN `is_lattice_member` to `memory_records` | Lattice support |
| M016 | ADD COLUMN `lattice_lineage_id` to `memory_records` | |
| M017 | ADD COLUMN `lattice_confidence` to `memory_records` | |
| M018 | Synthetic provenance sentinels | FK anchor for cycle episodes |

### M018 — Synthetic provenance sentinels

Inserts three sentinel rows so cycle episodes can have valid FK references in `memory_records`:

```sql
INSERT OR IGNORE INTO sources (source_id, ...) VALUES ('src_synthetic', ...)
INSERT OR IGNORE INTO documents (document_id, ...) VALUES ('doc_synthetic', ...)
INSERT OR IGNORE INTO chunks (chunk_id, ...) VALUES ('chk_synthetic', ...)
```

These are referenced by `EpisodeWriter` when inserting cycle episodes into `memory_records`. Without them, the FK constraints would reject episode rows (which have no real source file).

Constants in `_constants.py`:
- `SYNTHETIC_SOURCE_ID = "src_synthetic"`
- `SYNTHETIC_DOCUMENT_ID = "doc_synthetic"`
- `SYNTHETIC_CHUNK_ID = "chk_synthetic"`

---

## 3. Table Schemas

### `inspector_events`

```sql
CREATE TABLE inspector_events (
    event_id        TEXT PRIMARY KEY,   -- "evt_" + uuid[:12]
    event_type      TEXT NOT NULL,
    actor           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    data            TEXT NOT NULL,      -- JSON blob
    schema_version  INT NOT NULL DEFAULT 1,
    timestamp       INT NOT NULL,       -- unix seconds
    session_id      TEXT,
    cycle_id        TEXT,
    step_id         TEXT,
    subject_id      TEXT
)
```

Indexed by: `event_type`, `session_id`, `subject_id`, `timestamp`.

---

### `sources`

```sql
CREATE TABLE sources (
    source_id           TEXT PRIMARY KEY,   -- "src_" + sha256(canonical_path)[:16]
    canonical_path      TEXT NOT NULL UNIQUE,
    content_hash        TEXT NOT NULL,
    size_bytes          INT NOT NULL,
    detected_type       TEXT NOT NULL,
    detection_confidence REAL NOT NULL,
    parser_adapter      TEXT,
    parser_version      TEXT,
    chunker_version     TEXT,
    parser_status       TEXT NOT NULL DEFAULT 'pending',  -- "pending" | "parsed"
    lifecycle_state     TEXT NOT NULL DEFAULT 'active',
    created_at          INT NOT NULL,
    modified_at         INT,
    ingested_at         INT,
    schema_version      INT NOT NULL DEFAULT 1
)
```

---

### `documents`

```sql
CREATE TABLE documents (
    document_id     TEXT PRIMARY KEY,   -- "doc_" + uuid[:12]
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    title           TEXT,
    doc_type        TEXT,
    word_count      INT,
    schema_version  INT NOT NULL DEFAULT 1,
    created_at      INT NOT NULL
)
```

---

### `chunks`

```sql
CREATE TABLE chunks (
    chunk_id        TEXT PRIMARY KEY,   -- "chk_" + uuid[:12]
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    content         TEXT NOT NULL,
    chunk_index     INT NOT NULL,       -- position within document
    token_estimate  INT NOT NULL,
    schema_version  INT NOT NULL DEFAULT 1,
    created_at      INT NOT NULL
)
```

---

### `memory_records`

```sql
CREATE TABLE memory_records (
    record_id           TEXT PRIMARY KEY,   -- "rec_" + sha256(chunk_id)[:12]
    record_type         TEXT NOT NULL DEFAULT 'source_chunk',  -- "source_chunk" | "cycle_episode"
    source_id           TEXT NOT NULL REFERENCES sources(source_id),
    document_id         TEXT NOT NULL REFERENCES documents(document_id),
    chunk_id            TEXT NOT NULL REFERENCES chunks(chunk_id),
    content             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    token_estimate      INT NOT NULL,
    sku_address         TEXT,               -- NULL until classified
    sku_assigned_at     INT,
    lifecycle_state     TEXT NOT NULL DEFAULT 'active',  -- "active"|"archived"|"tombstoned"
    created_at          INT NOT NULL,
    schema_version      INT NOT NULL DEFAULT 1,
    -- M015-M017 additions:
    is_lattice_member   INT NOT NULL DEFAULT 0,   -- bool
    lattice_lineage_id  TEXT,
    lattice_confidence  REAL
)
```

---

### `sku_assignments`

```sql
CREATE TABLE sku_assignments (
    assignment_id               TEXT PRIMARY KEY,
    record_id                   TEXT NOT NULL REFERENCES memory_records(record_id),
    sku_address                 TEXT NOT NULL,
    d1_category                 TEXT NOT NULL,
    classifier_version          TEXT NOT NULL,
    prompt_version              TEXT NOT NULL,
    subcategory_strategy_version TEXT NOT NULL,
    confidence                  REAL NOT NULL,
    raw_scores_json             TEXT,       -- full quadrant+category scores JSON
    assigned_at                 INT NOT NULL
)
```

---

### `embeddings`

```sql
CREATE TABLE embeddings (
    embedding_id    TEXT PRIMARY KEY,   -- "emb_" + sha256(record_id:model:version)[:12]
    record_id       TEXT NOT NULL REFERENCES memory_records(record_id),
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    vector_blob     BLOB NOT NULL,      -- float32 LE, 1024 dims
    created_at      INT NOT NULL
)
```

---

### `pending_embeddings`

```sql
CREATE TABLE pending_embeddings (
    record_id   TEXT PRIMARY KEY REFERENCES memory_records(record_id),
    queued_at   INT NOT NULL
)
```

---

### `index_state`

```sql
CREATE TABLE index_state (
    key             TEXT PRIMARY KEY,   -- "fts5_last_updated"
    last_updated_at INT NOT NULL
)
```

Used by `is_lexical_stale()` to compare against `MAX(created_at)` from `memory_records`.

---

### `graph_nodes`

```sql
CREATE TABLE graph_nodes (
    node_id     TEXT PRIMARY KEY,   -- "source:<source_id>" | "record:<record_id>"
    node_type   TEXT NOT NULL,
    label       TEXT,
    data        TEXT,               -- JSON blob
    created_at  INT NOT NULL
)
```

---

### `graph_edges`

```sql
CREATE TABLE graph_edges (
    edge_id     TEXT PRIMARY KEY,   -- "edge_" + uuid[:12]
    source      TEXT NOT NULL REFERENCES graph_nodes(node_id),
    target      TEXT NOT NULL REFERENCES graph_nodes(node_id),
    edge_type   TEXT NOT NULL,
    weight      REAL,
    data        TEXT,               -- JSON blob
    created_at  INT NOT NULL
)
```

---

### `retrieval_traces`

```sql
CREATE TABLE retrieval_traces (
    trace_id            TEXT PRIMARY KEY,   -- "trace_" + uuid[:12]
    query               TEXT NOT NULL,
    mode                TEXT NOT NULL,      -- "lexical" | "vector" | "hybrid"
    context_packet_id   TEXT,               -- filled after build_context_packet()
    created_at          INT NOT NULL
)
```

---

### `retrieval_steps`

```sql
CREATE TABLE retrieval_steps (
    step_id     TEXT PRIMARY KEY,
    trace_id    TEXT NOT NULL REFERENCES retrieval_traces(trace_id),
    step_name   TEXT NOT NULL,      -- "exact_sku" | "lexical_search" | etc.
    candidate_count INT NOT NULL,
    created_at  INT NOT NULL
)
```

---

### `retrieval_candidates`

```sql
CREATE TABLE retrieval_candidates (
    candidate_id        TEXT PRIMARY KEY,
    trace_id            TEXT NOT NULL REFERENCES retrieval_traces(trace_id),
    record_id           TEXT NOT NULL,
    semantic_score      REAL,
    lexical_score       REAL,
    sku_match_score     REAL,
    recency_score       REAL,
    lifecycle_score     REAL,
    composite_score     REAL NOT NULL,
    retrieval_path      TEXT,
    exclusion_reason    TEXT,   -- NULL if selected; "composite_floor" | "lattice_sibling" | etc.
    rank                INT,
    created_at          INT NOT NULL
)
```

---

### `runtime_sessions` (M012)

```sql
CREATE TABLE runtime_sessions (
    session_id          TEXT PRIMARY KEY,   -- "sess_" + uuid[:12]
    cycle_config        TEXT NOT NULL,
    goal                TEXT NOT NULL,
    vault_path          TEXT NOT NULL,
    opened_at           INT NOT NULL,       -- ms
    parent_session_id   TEXT,
    recursion_depth     INT NOT NULL DEFAULT 0,
    max_recursion_depth INT NOT NULL,
    cycles_run          INT NOT NULL DEFAULT 0,
    steps_run           INT NOT NULL DEFAULT 0,
    state               TEXT NOT NULL DEFAULT 'active',  -- "active"|"flushed"|"continued"
    flushed_at          INT,
    final_outcome       TEXT
)
```

---

### `continuation_bundles` (M013)

```sql
CREATE TABLE continuation_bundles (
    bundle_id               TEXT PRIMARY KEY,   -- "bundle_" + uuid[:12]
    parent_session_id       TEXT NOT NULL,
    child_session_id        TEXT,
    distilled_goal          TEXT NOT NULL,
    summarized_prior_prompt TEXT NOT NULL,
    truth_tower_projection  TEXT NOT NULL,  -- JSON
    cognitive_insights      TEXT NOT NULL,  -- JSON array
    next_focus              TEXT NOT NULL,
    open_questions          TEXT NOT NULL,  -- JSON array
    constraints             TEXT NOT NULL,  -- JSON array
    recursion_depth         INT NOT NULL,
    voice_mode              TEXT NOT NULL,
    bundle_size_bytes       INT NOT NULL,
    created_at              INT NOT NULL,
    triggered_at            INT
)
```

---

### `cycle_episode_records` (M014)

```sql
CREATE TABLE cycle_episode_records (
    record_id                   TEXT PRIMARY KEY,   -- "ep_" + uuid[:12]
    runtime_session_id          TEXT NOT NULL,
    working_memory_session_id   TEXT,
    cycle_id                    TEXT NOT NULL,
    step_id                     TEXT NOT NULL,
    step_name                   TEXT NOT NULL,
    content                     TEXT NOT NULL,
    content_summary             TEXT NOT NULL,  -- first 200 chars
    metadata                    TEXT,           -- JSON
    leeway_grant_event_id       TEXT,
    cited_record_ids            TEXT,           -- JSON array
    created_at                  INT NOT NULL
)
```

---

### `predictions` / `outcomes` (M011)

```sql
CREATE TABLE predictions (
    prediction_id       TEXT PRIMARY KEY,   -- "pred_" + uuid[:12]
    session_id          TEXT NOT NULL,
    cycle_id            TEXT NOT NULL,
    step_id             TEXT NOT NULL,
    expected_composite  REAL NOT NULL,
    expected_per_signal TEXT NOT NULL,  -- JSON dict
    prediction_basis    TEXT NOT NULL,  -- "prior_step_trajectory"|"cycle_config_default"|"static_baseline"
    confidence          REAL NOT NULL,
    made_at             INT NOT NULL
)

CREATE TABLE outcomes (
    outcome_id              TEXT PRIMARY KEY,
    prediction_id           TEXT NOT NULL REFERENCES predictions(prediction_id),
    session_id              TEXT NOT NULL,
    cycle_id                TEXT NOT NULL,
    step_id                 TEXT NOT NULL,
    actual_composite        REAL NOT NULL,
    prediction_error        REAL NOT NULL,  -- signed: actual - expected
    error_classification    TEXT NOT NULL,  -- "noise" | "notable" | "severe"
    per_signal_error        TEXT NOT NULL,  -- JSON dict
    recorded_at             INT NOT NULL
)
```

---

## 4. FossicStore (`cerebra/storage/fossic_store.py`)

Wraps `fossic.Store` — a content-addressed, causation-chained event store.

```python
class FossicStore:
    def __init__(self, vault_path: Path)        # opens <vault>/.fossic/store.db
    
    @classmethod
    def at_platform_path(cls, db_path: Path)    # opens explicit path (hub store)
```

### Key methods

```python
def append(
    stream_id: str,
    event_type: str,
    payload: dict,
    causation_id: bytes | None = None,
    external_id: str | None = None,
    indexed_tags: dict | None = None,
) -> bytes
```

Returns content-addressed event ID bytes. The returned bytes become the `causation_id` for the next event in a chain.

```python
def read_events(
    *,
    stream_id: str | None = None,
    stream_pattern: str | None = None,   # glob, e.g. "cerebra/agent-trace/**"
    event_type: str | None = None,
    branch: str = "main",
    from_version: int | None = None,
) -> list[dict]
```

Each dict: `{event_type, payload, version, stream_id}`

```python
def register_reducer(stream_pattern: str, reducer: Callable) -> None
def read_state(stream_id: str) -> Any
def take_snapshot(stream_id: str) -> SnapshotInfo | None
def current_version(stream_id: str) -> int
def last_snapshot_version(stream_id: str) -> int
```

### Fossic streams (Cerebra)

| Stream pattern | Content |
|---|---|
| `cerebra/agent-trace/<session_id>` | Full per-session cycle event chain |
| `cerebra/control` | Daemon posture events (PostureChanged) |
| `cerebra/lattice/<lineage_id>` | Lattice classification events per lineage |
| `cerebra/graph/<lineage_id>` | GraphSnapshotAvailable (hub-direct only) |

### DEV-005 — CCE dedup

Fossic's content-addressed event engine deduplicates identical `(event_type + payload + causation_id)` tuples. Two events with the same type, payload, and causation_id collapse to one. Cerebra emission paths must vary causation_id to avoid unintended dedup (EventEmitter handles this automatically via chaining).

---

## 5. Embeddings (`cerebra/storage/embeddings.py`)

**Model:** `mixedbread-ai/mxbai-embed-large-v1`
- Dimensions: 1024
- Storage format: float32 little-endian blob
- Embedding ID: `"emb_" + sha256(f"{record_id}:{model_name}:{model_version}")[:12]`

### Functions

```python
def queue_for_embedding(db_path: Path, record_ids: list[str]) -> None
```
Inserts into `pending_embeddings`. Idempotent (INSERT OR IGNORE).

```python
def drain_pending(db_path: Path, batch_size: int = 32) -> int
```
Reads from `pending_embeddings`, generates embeddings in batches, inserts to `embeddings`, removes from queue. Returns count processed.

```python
def cosine_search(
    db_path: Path,
    query_text: str,
    limit: int = 20,
) -> list[tuple[str, float]]
```

Loads all active record embeddings into memory, computes cosine similarity via numpy, returns `[(record_id, score)]` sorted DESC. Safe up to ~50k records. For larger vaults, an ANN index would be needed (not yet implemented).

---

## 6. FTS5 / Lexical (`cerebra/storage/lexical.py`)

### Constants

```python
FTS_TABLE = "memory_records_fts"
```

### Functions

```python
def build_fts_index(db_path: Path, *, event_log=None) -> int
```

Full DROP + recreate of `memory_records_fts` from all active records. Returns record count indexed. Emits `LexicalIndexUpdated` inspector event.

```python
def update_fts_index(db_path: Path, record_ids: list[str], *, event_log=None) -> int
```

**Also does a full rebuild** (not incremental). This is intentional: SQLite 3.45 has a bug where incremental FTS5 delete on empty shadow tables raises "database disk image is malformed". The full rebuild avoids this.

```python
def search(db_path: Path, query: str, *, limit: int = 20) -> list[tuple[str, float]]
```

FTS5 MATCH query. Returns `[(record_id, rank)]` where rank is negative (more negative = better match). Callers negate the rank for scoring.

```python
def _sanitize_fts_query(query: str) -> str
```

Strips all non-alphanumeric characters so LLM-generated queries are safe for FTS5 MATCH (prevents syntax errors from special characters).

```python
def is_lexical_stale(db_path: Path) -> bool
```

Compares `MAX(memory_records.created_at)` vs `index_state.last_updated_at`. True means the index is behind the current record set.

---

## 7. ArtifactStore (`cerebra/storage/artifact_store.py`)

Persists structured and plain-text representations of parsed documents to disk.

```python
def write_artifact(doc: ParseResult, artifacts_dir: Path) -> Path
```
Writes `<artifacts_dir>/<doc_id>.json` — full structured JSON of the parsed document (title, sections, metadata).

```python
def write_text_artifact(vault_path: Path, doc_id: str, raw_content: str) -> Path
```
Writes `<vault>/data/<doc_id>.txt` — raw plain-text version. Used for reference and future re-processing.

---

## 8. GraphStore (`cerebra/storage/graph_store.py`)

Wraps the `graph_nodes` + `graph_edges` tables.

```python
def upsert_node(db, node_id: str, node_type: str, label: str, data: dict) -> None
```
INSERT OR REPLACE into `graph_nodes`.

```python
def upsert_edge(
    db,
    source: str,
    target: str,
    edge_type: str,
    weight: float | None = None,
    data: dict | None = None,
) -> str  # returns edge_id
```
INSERT OR IGNORE by `(source, target, edge_type)` uniqueness. Returns existing edge_id if already present.

These tables back the in-vault graph model (not to be confused with the exported `graph.json` — they're the same data in different formats).

---

## 9. IndexState (`cerebra/storage/index_state.py`)

```python
def get_index_state(db_path: Path, key: str) -> int | None
def update_index_state(db_path: Path, key: str, value: int) -> None
```

Currently used for one key: `"fts5_last_updated"` — unix timestamp of last FTS5 rebuild.

---

## 10. SQLiteStore (`cerebra/storage/sqlite_store.py`)

Higher-level store object used by the ingest pipeline and retrieval layer.

Key methods (non-exhaustive):

```python
def insert_document(doc: Document) -> None
def insert_chunks_batch(chunks: list[Chunk]) -> None
def insert_records_batch(records: list[MemoryRecord]) -> None
def get_record(record_id: str) -> MemoryRecord | None
def get_records_for_document(document_id: str) -> list[MemoryRecord]
def get_unclassified_records(limit: int) -> list[MemoryRecord]
def insert_sku_assignment(assignment: SKUAssignment) -> None
def update_record_sku(record_id: str, sku_address: str, assigned_at: int) -> None
def insert_session(session: WorkingMemorySession) -> None
def get_active_session() -> WorkingMemorySession | None
```

All methods use the `connect()` factory — they open and close their own connections per call (no persistent connection state on the object).

---
<!-- source: state-reports/04_sources_ingest_graph.md -->

# Cerebra — Sources, Ingest Pipeline & Graph Export

---

## 1. Sources (`cerebra/sources/`)

### SourceRecord (`cerebra/sources/registry.py`)

```python
@dataclass
class SourceRecord:
    source_id: str              # "src_" + sha256(canonical_path)[:16]
    canonical_path: str         # absolute path, normalized
    content_hash: str           # sha256 of file contents (hex)
    size_bytes: int
    detected_type: str          # e.g. "markdown", "text/plain"
    detection_confidence: float # 0.0–1.0
    parser_adapter: str | None  # "markdown" | "text" | None
    parser_version: str | None
    chunker_version: str | None
    parser_status: str          # "pending" → "parsed"
    lifecycle_state: str        # "active" (default)
    created_at: int             # unix ms
    modified_at: int | None
    ingested_at: int | None
    schema_version: int
```

Source ID is stable across re-ingests as long as the canonical path doesn't change.

---

### `register_source()` (`cerebra/sources/registry.py`)

```python
def register_source(
    store: SQLiteStore,
    event_log: SQLiteEventLog,
    path: Path,
    detection: DetectionResult,
    parser_version: str,
    chunker_version: str,
) -> tuple[SourceRecord, RegistrationOutcome]
```

**RegistrationOutcome** (enum):
- `NEW` — first time this path has been seen
- `SKIPPED_UNCHANGED` — `(canonical_path, content_hash, parser_version, chunker_version)` matches existing record; caller should skip all downstream work
- `CHANGED` — content_hash or version changed; marks source + all its documents + chunks + memory records as stale

**On CHANGED:**
- Updates source row with new content_hash, modified_at
- Marks associated documents/chunks/records stale (lifecycle_state = "stale", or triggers re-parse)
- Emits `SourceChanged` inspector event

**On NEW:**
- Inserts source row
- Emits `SourceRegistered` inspector event

---

### Type Detection (`cerebra/sources/detector.py`)

```python
def detect_type(path: Path) -> DetectionResult

@dataclass
class DetectionResult:
    detected_type: str
    confidence: float
    adapter_hint: str | None    # "markdown" | "text" | None
```

Detection is heuristic (extension + content sniff). No ML. Confidence is rule-derived:
- `.md`, `.mdx` → `"markdown"`, confidence=0.95
- `.txt` → `"text/plain"`, confidence=0.90
- Unknown → `"text/plain"`, confidence=0.50

---

### Discovery (`cerebra/sources/discovery.py`)

```python
def discover_files(
    target: Path,
    *,
    extensions: frozenset[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[Path]
```

Walks `target` recursively. If `extensions` is provided, only returns files matching those extensions. `exclude_patterns` are glob patterns matched against the relative path from `target`.

---

### Hashing (`cerebra/sources/hashing.py`)

```python
def content_hash(path: Path) -> str    # sha256 hex digest of file bytes
```

---

## 2. Ingest Pipeline (`cerebra/ingest/pipeline.py`)

### IngestReport

```python
@dataclass
class IngestReport:
    sources_found: int
    sources_new: int
    sources_changed: int
    sources_skipped: int
    sources_failed: int
    chunks_created: int
    records_created: int
    errors: list[str]
```

---

### `ingest_path()` — entry point

```python
def ingest_path(
    vault_path: Path,
    target: Path,
    *,
    dry_run: bool = False,
    exclude_patterns: list[str] | None = None,
    extensions: frozenset[str] | None = None,
    chunk_options: ChunkOptions | None = None,
) -> IngestReport
```

**Event log:** Dual-writes to both `SQLiteEventLog` (inspector_events table) and `NDJSONEventLog` (`vault/events/ingest.ndjson`).

---

### Per-file pipeline: `_ingest_file()` — 17 steps

Each file discovered by `discover_files()` passes through all 17 steps:

1. `detect_type(file_path)` → `DetectionResult`
2. `register_source(store, event_log, path, detection, parser_version, chunker_version)` → `(SourceRecord, outcome)`
3. **If `SKIPPED_UNCHANGED`:** return immediately (no further processing)
4. Upsert Source graph node (`upsert_node(db, "source:<source_id>", "spine", ...)`)
   - Emits `GraphNodeCreated` inspector event
5. Select adapter based on `detection.adapter_hint`:
   - `"markdown"` → `MarkdownAdapter`
   - `"text"` or None → `TextAdapter`
6. `adapter.parse(path, source_record)` → `ParseResult`
   - On failure: emit `SourceParseFailed`, add to `report.errors`, return
7. `write_artifact(doc, artifacts_dir)` → writes `<artifacts_dir>/<doc_id>.json`
8. `write_text_artifact(vault_path, doc_id, raw_content)` → writes `<vault>/data/<doc_id>.txt`
9. Emit `DocumentNormalized` inspector event
10. `store.insert_document(doc)` → inserts to `documents` table
11. Upsert Document graph node + Source→Document CONTAINS edge (`upsert_node`, `upsert_edge`)
12. `chunk_document(doc, opts)` → `list[Chunk]`; `store.insert_chunks_batch(chunks)`
13. For each chunk: upsert Chunk graph node + Document→Chunk CONTAINS edge + Chunk→Document PART_OF edge
14. `build_records_for_document(chunks, source)` → `list[MemoryRecord]`; `store.insert_records_batch(records)`
15. For each record: upsert MemoryRecord graph node + MemoryRecord→Chunk DERIVED_FROM edge
16. `update_fts_index(db_path, record_ids)` — full rebuild (adds new records)
17. `queue_for_embedding(db_path, record_ids)` — inserts to `pending_embeddings`
18. Update source `parser_status = "parsed"`, `ingested_at = now`
19. Emit `SourceParsed` inspector event

---

### Chunking (`cerebra/ingest/chunking.py`)

```python
def chunk_document(doc: ParseResult, opts: ChunkOptions | None = None) -> list[Chunk]

@dataclass
class ChunkOptions:
    max_tokens: int = 512
    overlap_tokens: int = 64
    min_tokens: int = 32
```

Token estimation: character count / 4 (heuristic). Chunks are non-overlapping in text but may overlap in token count (sliding window).

Chunk IDs: `"chk_" + uuid[:12]` (random, not content-addressed — chunk_index is the stable key within a document).

---

### Adapters

**MarkdownAdapter (`cerebra/ingest/adapters/markdown.py`):**

```python
class MarkdownAdapter(BaseAdapter):
    PARSER_VERSION = "1.0.0"
    
    def parse(self, path: Path, source: SourceRecord) -> ParseResult
```

Extracts: title (first H1), sections (H2/H3 boundaries), metadata (frontmatter if present). Joins section text for chunking.

**TextAdapter (`cerebra/ingest/adapters/text.py`):**

```python
class TextAdapter(BaseAdapter):
    PARSER_VERSION = "1.0.0"
    
    def parse(self, path: Path, source: SourceRecord) -> ParseResult
```

Reads raw text, uses filename as title, no section structure. Passes full content to chunker.

**ParseResult (shared, `cerebra/ingest/models.py`):**

```python
@dataclass
class ParseResult:
    document_id: str       # "doc_" + uuid[:12]
    source_id: str
    title: str
    doc_type: str
    sections: list[Section]
    raw_content: str
    word_count: int
    metadata: dict
```

---

## 3. Graph Model (`cerebra/graph/model.py`)

### ExportStats

```python
@dataclass
class ExportStats:
    node_count: int
    edge_count: int
    spine_count: int          # source nodes
    record_count: int         # memory_record nodes
    classified_count: int     # records with sku_address
    unclassified_count: int   # records without sku_address
    edges_by_type: dict[str, int]
    out_path: Path
    elapsed_ms: int
```

---

## 4. Graph Exporter (`cerebra/graph/exporter.py`)

```python
def export_graph(
    vault_path: Path,
    *,
    out_path: Path | None = None,       # default: <vault>/.cerebra/graph.json
    event_log: SQLiteEventLog | None = None,
    hub_store: Any = None,              # FossicStore for hub-direct emission
    triggered_by: str | None = None,   # event_id that triggered this export
) -> ExportStats
```

### Schema version

`"cerebra/v1"` — the schema identifier embedded in the output JSON.

### Node types

**Spine nodes** (one per active, non-`cerebra://` source):
```json
{
  "id": "source:<source_id>",
  "type": "spine",
  "label": "<filename>",
  "cluster": "<detected_type_cluster>",
  "data": {
    "source_id": "...",
    "canonical_path": "...",
    "detected_type": "...",
    "record_count": N
  }
}
```

Cluster colors by `detected_type`:
- `markdown` → `"azure"`
- `text/plain` → `"slate"`
- unknown → `"gray"`
- code types → `"teal"`

**Memory record nodes** (one per active record with an `sku_assignment`):
```json
{
  "id": "record:<record_id>",
  "type": "memory_record",
  "label": "<first 60 chars of content>",
  "cluster": "<d1_quadrant_cluster>",
  "data": {
    "record_id": "...",
    "sku_address": "...",
    "d1_category": "...",
    "lifecycle_state": "active",
    "is_lattice_member": false
  }
}
```

D1 quadrant cluster colors:
- Empirical (D1 `0x0`–`0x3`) → `"azure"`
- Generative (D1 `0x4`–`0x7`) → `"gold"`
- Normative (D1 `0x8`–`0xB`) → `"purple"`
- Relational (D1 `0xC`–`0xF`) → `"teal"`

Unclassified records (no sku_assignment) are **excluded** from the export.

### Edge types

| Type | Weight | Source → Target | Cap |
|---|---|---|---|
| `contains` | 0.4 | source node → record node | none |
| `describes` | 0.65 | record[N] → record[N+1] | chunk_index adjacency within same doc |
| `sku-proximity` | `min(0.5, group_size/20)` | record → record (shared D1) | `_SKU_PROXIMITY_CAP = 5` per node |
| `sku-exact` | 0.9 | record → record (identical sku_address) | none |

`sku-proximity` edges are capped at 5 per node to prevent hub-and-spoke topology when many records share the same D1 category.

### Node cap

`_MAX_NODES = 2000` total nodes. If the vault has more, sources are selected alphabetically (by canonical_path), then records selected in chunk_index order within those sources.

### Output JSON structure

```json
{
  "schemaVersion": "cerebra/v1",
  "metadata": {
    "schemaVersion": "cerebra/v1",
    "generatedAt": 1750000000,
    "generator": "cerebra",
    "vaultPath": "/abs/path/to/vault",
    "cerebraVersion": "0.4.4",
    "stats": {
      "nodeCount": 142,
      "edgeCount": 389,
      "nodesByType": {"spine": 12, "memory_record": 130},
      "edgesByType": {"contains": 130, "describes": 128, "sku-proximity": 87, "sku-exact": 44},
      "activeSourceCount": 12,
      "activeRecordCount": 180,
      "classifiedRecordCount": 130,
      "unclassifiedRecordCount": 50
    }
  },
  "nodes": [...],
  "edges": [...]
}
```

Written to `<vault>/.cerebra/graph.json` (creates `.cerebra/` dir if absent).

### Hub-direct emission

If `hub_store` is provided (or `CEREBRA_PLATFORM_STORE` is set when called from the daemon):

```python
hub_store.append(
    stream_id=f"cerebra/graph/{lineage_id}",
    event_type="GraphSnapshotAvailable",
    payload={
        "graph_path": str(out_path),
        "node_count": stats.node_count,
        "edge_count": stats.edge_count,
        "vault_path": str(vault_path),
        "triggered_by": triggered_by,
    }
)
```

Hub errors are caught and swallowed (non-fatal). The local export always completes regardless of hub status.

### Inspector events emitted

- `GraphExported` — after successful write, includes ExportStats in payload
- `GraphNodeCreated` — during ingest pipeline (not during export_graph; nodes are pre-existing in graph_nodes table)
- `GraphEdgeCreated` — same as above
- `GraphSnapshotAvailable` — only if hub-direct write succeeded

---

## 5. Data Flow: Ingest

```
CLI: cerebra ingest <target>
  └─ discover_files(target, extensions, exclude_patterns)
       └─ for each file:
            detect_type(file) → DetectionResult
            register_source(...) → (SourceRecord, RegistrationOutcome)
            if SKIPPED_UNCHANGED: continue
            MarkdownAdapter | TextAdapter .parse() → ParseResult
            write_artifact() + write_text_artifact()
            store.insert_document()
            upsert_node("source:<id>") + upsert_node("doc:<id>")
            upsert_edge(source→doc, "contains")
            chunk_document() → list[Chunk]
            store.insert_chunks_batch()
            for chunk: upsert_node + edges
            build_records_for_document() → list[MemoryRecord]
            store.insert_records_batch()
            for record: upsert_node + DERIVED_FROM edge
            update_fts_index(record_ids)     ← full FTS5 rebuild
            queue_for_embedding(record_ids)  ← deferred unless --embed
            source.parser_status = "parsed"
            emit SourceParsed
  └─ return IngestReport
```

---

## 6. Data Flow: Graph Export

```
CLI: cerebra export-graph
  └─ export_graph(vault_path)
       └─ SQL: SELECT active sources (canonical_path NOT LIKE 'cerebra://%')
            → spine nodes (up to _MAX_NODES)
          SQL: SELECT active records JOIN sku_assignments
            → memory_record nodes (classified only)
          Build edges:
            contains: source → each of its records
            describes: chunk_index-adjacent record pairs within same doc
            sku-proximity: records sharing D1 category (cap 5/node)
            sku-exact: records with identical sku_address
          Write graph.json (cerebra/v1)
          [If hub_store]: append GraphSnapshotAvailable to cerebra/graph/<lineage_id>
          emit GraphExported inspector event
          return ExportStats
```

---
<!-- source: state-reports/05_sku_retrieval.md -->

# Cerebra — SKU Addressing System & Retrieval Layer

---

## 1. SKU Address Format (`cerebra/cognition/sku.py`)

The SKU (Stock-Keeping Unit) address is a 12-character string with two dots that encodes the cognitive position of a memory record.

```
D1D2D3D4D5D6.D7D8.D9D10
│             │     │
│             │     └─ Tag byte: D9 (modality) + D10 (provenance)
│             └─ Entry byte: D7D8 (0x00–0xFF, up to 256 entries per location)
└─ Location: 6 hex nibbles (D1=category, D2-D6=subcategory stubs)
```

**Examples:**
- `"040000.01.00"` = D1=TECHNIQUE(0x4), D2-D6 stubs, entry=0x01, TEXT+OBSERVED
- `"8c0000.00.10"` = D1=PRINCIPLE(0x8), JUDGMENT sub-area (0xC?), entry=0x00, CODE+OBSERVED

**Phase 2 stubs:** D2=D3=D4=D5=D6=0x0 for all records. Subcategory expansion is future work.

### SKUAddress dataclass

```python
@dataclass(frozen=True)
class SKUAddress:
    d1: int          # 0x0–0xF (D1Category value)
    d2: int = 0      # stub
    d3: int = 0      # stub
    d4: int = 0      # stub
    d5: int = 0      # stub
    d6: int = 0      # stub
    d7: int          # entry high nibble
    d8: int          # entry low nibble
    d9: int          # D9Modality value
    d10: int         # D10Provenance value
    
    def to_hex_string(self) -> str
    
    @classmethod
    def from_hex_string(cls, s: str) -> "SKUAddress"
```

### SKUAssignment dataclass

```python
@dataclass
class SKUAssignment:
    assignment_id: str                  # uuid
    record_id: str
    sku_address: str                    # hex string
    d1_category: str                    # D1Category name
    classifier_version: str
    prompt_version: str
    subcategory_strategy_version: str
    confidence: float
    raw_scores_json: str | None         # full quadrant+category score JSON
    assigned_at: int
    
    def as_dict(self) -> dict           # for DB insert
```

---

## 2. D1 Category System (`cerebra/cognition/sku_categories.py`)

### D1Category enum (16 values)

```python
class D1Category(IntEnum):
    # Quadrant I — Empirical (0x0–0x3): facts, data, mechanisms
    OBSERVATION  = 0x0   # raw data, measurements, recorded events
    PATTERN      = 0x1   # regularities, correlations, trends
    MECHANISM    = 0x2   # causal processes, how things work
    PHENOMENON   = 0x3   # observable occurrences, discoveries

    # Quadrant II — Generative (0x4–0x7): techniques, designs, creations
    TECHNIQUE    = 0x4   # methods, procedures, algorithms
    DESIGN       = 0x5   # architectures, plans, blueprints
    CREATION     = 0x6   # artifacts, products, implementations
    TOOL         = 0x7   # instruments, frameworks, software

    # Quadrant III — Normative (0x8–0xB): principles, judgments, goals
    PRINCIPLE    = 0x8   # rules, laws, axioms, norms
    JUDGMENT     = 0x9   # evaluations, critiques, assessments
    GOAL         = 0xA   # objectives, intentions, desired states
    CONSTRAINT   = 0xB   # limits, restrictions, requirements

    # Quadrant IV — Relational (0xC–0xF): events, agents, contexts
    EVENT        = 0xC   # occurrences, milestones, incidents
    AGENT        = 0xD   # people, systems, entities that act
    CONTEXT      = 0xE   # settings, environments, situations
    RELATION     = 0xF   # connections, dependencies, associations
```

Quadrant extraction: `quadrant = (d1_value >> 2) & 0x3`
- 0 = Empirical, 1 = Generative, 2 = Normative, 3 = Relational

`CATEGORY_DESCRIPTIONS: dict[D1Category, str]` maps each value to a one-line description used verbatim in classification prompts.

---

## 3. D9 Modality & D10 Provenance (`cerebra/cognition/sku.py`)

### D9Modality

```python
class D9Modality(IntEnum):
    TEXT         = 0x0
    CODE         = 0x1
    GRAPH        = 0x2
    CONVERSATION = 0x3
    OBSERVATION  = 0x4
    DECISION     = 0x5
    SYNTHESIS    = 0x6
    UNKNOWN      = 0x7
```

For ingested records: `d9_from_detected_type(detected_type) → D9Modality` (heuristic, no LLM).
- `.md`, `.txt` → TEXT
- `.py`, `.ts`, `.rs`, etc. → CODE
- default → TEXT

### D10Provenance

```python
class D10Provenance(IntEnum):
    OBSERVED     = 0x0   # ingested from external source (default for ingest)
    CONSOLIDATED = 0x1   # merged/consolidated from multiple records
    SYNTHESIZED  = 0x2   # LLM-generated synthesis
    USER_PIN     = 0x3   # manually added by user
    EXTERNAL     = 0x4   # from external system (not directly ingested)
    SYSTEM       = 0x5   # system-generated (e.g. governance defaults)
    UNKNOWN      = 0x6
```

D10 is always `OBSERVED (0x0)` for records ingested via `cerebra ingest`. Cycle episodes get `SYNTHESIZED (0x2)`.

---

## 4. SKU Classifier (`cerebra/cognition/sku_classifier.py`)

### Version constants

```python
CLASSIFIER_VERSION           = "1.0.0"
PROMPT_VERSION               = "2.0.0"
SUBCATEGORY_STRATEGY_VERSION = "v1-stub"
HIGH_CONF_THRESHOLD          = 0.5
D1_ANCHOR_THRESHOLD          = 0.4
```

### Two-pass classification

**Pass 1 — classify_quadrant(content):**
- Prompt: asks LLM to score content against 4 quadrant descriptions
- Response: JSON `{scores: {Empirical: F, Generative: F, Normative: F, Relational: F}, primary: "...", reasoning: "..."}`
- Primary quadrant = highest score; confidence = primary_score
- Retried once on parse failure

**Pass 2 — classify_within_quadrant(content, quadrant):**
- Prompt: asks LLM to score content against the 4 categories in the winning quadrant
- Response: JSON `{scores: {CATEGORY_A: F, ...}, primary: "...", confidence: F, reasoning: "..."}`
- D1 answer = primary category in winning quadrant
- Retried once on parse failure

Response parsing in `_parse_classification_response()` handles three formats:
1. Canonical nested JSON (expected)
2. Flat JSON (LLM sometimes flattens)
3. Malformed — regex fallback to extract numeric scores

### `classify_record(record_id, content, detected_type) → SKUAssignment | None`

- Idempotency: skips if existing assignment has matching `classifier_version + prompt_version`
- On reclassification: deletes old `sku_assignments` row, re-inserts
- On success: calls `store.insert_sku_assignment()` + `store.update_record_sku()`
- Emits: `SKUAssigned` (new) or `SKUReclassified` (update)
- If `confidence < HIGH_CONF_THRESHOLD (0.5)`: also emits `ClassificationLowConfidence`
- On unrecoverable error: emits `ClassificationFailed`, returns None

### `classify_record_lattice(record_id, content, detected_type, threshold=None) → list[str]`

Runs the same two-pass classification, then passes all category scores to `evaluate_lattice()`.

If `LatticeDecision.should_multi_commit` (≥2 categories ≥ threshold):
- Builds sibling records in `memory_records` for each secondary category
- Sibling `record_id = "rec_" + sha256(f"{primary_record_id}:{category}")[:12]` (deterministic)
- Siblings share the same chunk_id/document_id/source_id as the primary
- Sets `is_lattice_member=True`, `lattice_lineage_id`, `lattice_confidence` on all involved records
- Emits ONE `LatticeCommit` event per chunk (not per sibling) to avoid over-emission
- Returns `[primary_record_id, sibling1_record_id, ...]` (primary always first)

### BackfillReport

```python
@dataclass
class BackfillReport:
    records_found: int
    classified: int
    skipped: int          # already classified with matching version
    failed: int           # ClassificationFailed events
    low_confidence: int   # ClassificationLowConfidence events
    elapsed_ms: int
```

---

## 5. Lattice Evaluation (`cerebra/cognition/lattice.py`)

```python
LATTICE_COMMIT_THRESHOLD = 0.65
```

### LatticeDecision

```python
@dataclass
class LatticeDecision:
    all_scores: dict[str, float]        # category name → score (all 16)
    candidates: list[str]               # categories ≥ threshold
    primary: str                        # highest score category
    should_multi_commit: bool           # True if ≥ 2 candidates

def evaluate_lattice(
    scores: dict[str, float],
    threshold: float | None = None,     # default: LATTICE_COMMIT_THRESHOLD
) -> LatticeDecision
```

`should_multi_commit` is True when `len(candidates) >= 2` (at least two categories scored ≥ threshold). This drives sibling record creation.

### Helpers

```python
def new_lineage_id() -> str                              # "lat_" + uuid[:12]
def build_sibling_record_id(primary_id, category) -> str # deterministic sha256
```

Sibling IDs are deterministic so re-running classification produces the same IDs (idempotent).

---

## 6. Retrieval Planner (`cerebra/retrieval/planner.py`)

### QueryPlan

```python
@dataclass
class QueryPlan:
    trace_id: str           # "trace_" + uuid[:12]
    query: str
    mode: str               # "lexical" | "vector" | "hybrid"
    max_candidates: int     # cap passed to traversal
    d1_hint: str | None     # detected D1 category for SKU traversal
    created_at: int
```

### Mode detection rules

Mode is auto-detected from query characteristics:

| Condition | Mode |
|---|---|
| Query contains code identifiers (`_IDENTIFIER_RE` matches) | `lexical_only` |
| Query length ≤ 2 words AND no D1 keyword hit | `vector_only` |
| Default (all other cases) | `hybrid` |

`_IDENTIFIER_RE` matches: `snake_case_words`, `camelCaseWords`, `.file.extensions`, `"quoted strings"`, `` `backtick wrapped` ``, `ALL_CAPS_CONSTANTS`.

D1 keyword detection uses `d1_keywords.toml` — a TOML file with hex keys (e.g., `"0x5"` for DESIGN) mapping to keyword vocabulary lists. A D1 match sets `d1_hint` in the QueryPlan.

### `RetrievalPlanner.plan(query) → QueryPlan`

1. Detect mode
2. Assign trace_id
3. Emit `QueryReceived` inspector event
4. Emit `QueryPlanned` inspector event (includes mode + d1_hint)
5. Return QueryPlan

---

## 7. Retrieval Traversal (`cerebra/retrieval/traversal.py`)

```python
def traverse(
    db_path: Path,
    plan: QueryPlan,
    event_log: SQLiteEventLog | None = None,
) -> list[CandidateRecord]
```

Six steps execute sequentially. Empty results from a step fall through silently (no abort). Each step annotates candidates with which step found them (for `retrieval_path` field).

### Step 1: `exact_sku`

SQL: `WHERE sku_address = plan.d1_hint` (exact SKU address match, if `d1_hint` set).

Emits `TraversalStepCompleted` with `step_name="exact_sku"`, `candidate_count=N`.

### Step 2: `partial_sku`

SQL: `WHERE sku_address LIKE 'd1_prefix%'` — D1 prefix match (first hex nibble matches `d1_hint`).

Only runs if `d1_hint` is set and `exact_sku` returned < `plan.max_candidates`.

### Step 3: `sibling_traversal`

v0.1 stub — returns input candidates unchanged (no-op). Reserved for future lattice sibling expansion.

### Step 4: `lexical_search`

Calls `lexical.search(db_path, plan.query, limit=plan.max_candidates)`.

Only runs if `plan.mode` is `lexical_only` or `hybrid`.

Returns `[(record_id, rank)]` where rank is negative (FTS5 convention).

### Step 5: `vector_fallback`

Calls `embeddings.cosine_search(db_path, plan.query, limit=plan.max_candidates)`.

Only runs if `plan.mode` is `vector_only` or `hybrid`.

### Step 6: `trace_annotation`

Not a search step — annotates each accumulated candidate with its `retrieval_path` (which steps surfaced it) and deduplicates by record_id (keeping best score seen across steps).

Final sort: `semantic_score DESC`, then `abs(lexical_score) DESC` (tiebreak). Cap at `plan.max_candidates`.

---

## 8. Composite Scorer (`cerebra/retrieval/scorer.py`)

### Salience formula

```
composite = (semantic   × 0.40)
          + (lexical    × 0.25)
          + (sku_match  × 0.15)
          + (recency    × 0.10)
          + (lifecycle  × 0.10)
```

### Component derivations

**Semantic score:** raw cosine similarity from `embeddings.cosine_search()` (already 0–1).

**Lexical score:** FTS5 rank negated and normalized. FTS5 returns negative ranks; the negation gives a positive "goodness" score. Normalized to [0, 1] across the candidate set.

**SKU match score:**
- `1.0` — sku_address matches `plan.d1_hint` exactly
- `0.5` — sku_address D1 nibble matches `plan.d1_hint` D1 nibble (partial)
- `0.0` — no match or no d1_hint

**Recency score:** `math.exp(-age_days / 365)` — exponential decay. A record created today scores 1.0; a 1-year-old record scores ~0.37.

**Lifecycle score:** Always `1.0` in Phase 4. Tombstoned records are pre-filtered before scoring, so lifecycle scoring isn't needed in practice. Reserved for future partial-lifecycle scoring.

### ScoredCandidate

```python
@dataclass
class ScoredCandidate:
    record_id: str
    semantic_score: float
    lexical_score: float
    sku_match_score: float
    recency_score: float
    lifecycle_score: float
    composite_score: float
    content_excerpt: str        # first 300 chars
    retrieval_path: str         # "exact_sku+lexical" etc.
    exclusion_reason: str | None  # set by dedup_siblings or floor filter
    # lattice fields (set by dedup_siblings):
    lattice_sibling_count: int | None
    lattice_winner_record_id: str | None
    lattice_routing_basis: str | None

def explain(self) -> list[dict]:
    # Returns: [{component, value, weight, contribution}, ...]
```

---

## 9. Lattice Deduplication (`cerebra/retrieval/lattice_dedup.py`)

When multiple records share the same `lattice_lineage_id` (siblings), at most one reaches the context packet. Dedup runs after scoring, before floor filtering.

### `dedup_siblings(scored, query_d1, db_path, trace_id, event_log=None) → list[ScoredCandidate]`

Groups candidates by `lattice_lineage_id`. For each group, selects one winner via D2 routing:

**D2 routing rules (applied in priority order):**

1. `sku_match` — exactly one sibling's sku_address D1 matches `query_d1` → that sibling wins
2. `sku_match_multi` — multiple siblings' D1 matches `query_d1` → highest composite wins (tiebreak: earliest `created_at`)
3. `composite_score` — no D1 match → highest composite wins (tiebreak: earliest `created_at`)

Losers receive `exclusion_reason = "lattice_sibling"`.

All group members (winner + losers) receive:
- `lattice_sibling_count` — total group size
- `lattice_winner_record_id` — record_id of the winner
- `lattice_routing_basis` — which rule applied (`"sku_match"`, `"sku_match_multi"`, or `"composite_score"`)

Emits `LatticeSiblingResolved` inspector event per group.

### `dedup_memory_items(items, db_path) → list[MemoryItem]`

Used by `TruthTower.promote_to_t1()` for dedup before tower insertion. No DB updates, no events (pure in-memory filter).

---

## 10. ContextPacket (`cerebra/retrieval/context_packet.py`)

### MemoryItem

```python
@dataclass
class MemoryItem:
    record_id: str
    source_id: str
    chunk_id: str
    content_excerpt: str    # max 400 chars (truncated from content)
    source_path: str        # vault-relative path
    sku_address: str | None
    score: float            # composite score
    score_components: dict[str, float]  # {"semantic": F, "lexical": F, ...}
    retrieval_path: str     # which traversal steps surfaced this
    rank: int               # 1-indexed position in selected_memory
```

### ContextPacket

```python
@dataclass
class ContextPacket:
    context_packet_id: str          # "ctxpkt_" + uuid[:12]
    packet_version: int
    schema_version: int
    created_at: int
    query: str
    mode: str
    is_abstained: bool              # True if floor not met by any candidate
    abstention_rationale: str | None
    retrieval_trace_id: str
    origin_event_ids: list[str]     # event IDs of upstream events
    selected_memory: list[MemoryItem]   # top N after floor filter
    token_estimate: int
    selected_count: int
    candidate_count: int            # total before floor filter
    uncertainties: list[str]
    excluded_candidate_count: int
    best_score_seen: float | None   # populated on abstained packets only
    truth_tower: dict | None        # set by to_tower_field() if called
```

### `build_context_packet(trace_data, scored_candidates, db_path, *, limit=10, event_log=None) → ContextPacket`

Called when at least one candidate clears the floor (`_RETRIEVAL_FLOOR = 0.35`). Selects top `limit` candidates, truncates content to 400 chars per item, sets `truth_tower` field if `TruthTower.to_tower_field()` returns data.

Side effects:
- `UPDATE retrieval_traces SET context_packet_id = ...`
- Emit `ContextPacketBuilt` inspector event

### `build_abstained_packet(trace_data, best_score_seen, *, event_log=None) → ContextPacket`

Called when no candidates clear the floor. Returns packet with `is_abstained=True`, `selected_memory=[]`. Does NOT update `retrieval_traces.context_packet_id`.

### `render_text(packet, limit=10) → str`

Renders packet as structured text for injection into LLM prompt. §12 format (numbered sections with source attribution).

---

## 11. Retrieval Data Flow

```
query (str)
  └─ RetrievalPlanner.plan(query)
       → QueryPlan (mode, trace_id, d1_hint)
  └─ RetrievalTraversal.traverse(db_path, plan)
       Step 1: exact_sku (if d1_hint)
       Step 2: partial_sku (if d1_hint, needs more)
       Step 3: sibling_traversal (stub, no-op)
       Step 4: lexical_search (if lexical|hybrid)
       Step 5: vector_fallback (if vector|hybrid)
       Step 6: trace_annotation (dedup + annotate)
       → list[CandidateRecord]
  └─ score_candidates(candidates, plan)
       → list[ScoredCandidate] (composite = 0.40s+0.25l+0.15k+0.10r+0.10c)
  └─ dedup_siblings(scored, query_d1, ...)
       D2 routing: sku_match > sku_match_multi > composite_score
       → list[ScoredCandidate] (losers have exclusion_reason="lattice_sibling")
  └─ filter_by_floor(candidates, floor=_RETRIEVAL_FLOOR)
       → selected (composite ≥ 0.35) + excluded
  └─ if selected:
       build_context_packet(trace, selected, limit=10)
       → ContextPacket (is_abstained=False)
     else:
       build_abstained_packet(trace, best_score_seen)
       → ContextPacket (is_abstained=True, selected_memory=[])
```

---
<!-- source: state-reports/06_cognition_runtime.md -->

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

---
<!-- source: state-reports/07_wm_tower_clutch_catalyst.md -->

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

---
<!-- source: state-reports/08_memory_governance_inspector.md -->

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

---
<!-- source: state-reports/09_cycle_config_events_flows.md -->

# Cerebra — Cycle Config Schema, Event Reference & Data Flows

---

## 1. Cycle Config YAML Schema

Cycle config files live in `cycles/` or at any absolute/relative path. Loaded by `CycleConfig` from `cerebra/cognition/cycle_config.py`.

### Top-level fields

```yaml
name: "simple.planning.v0"       # string, human-readable name
version: 1                        # int, config schema version
description: "..."               # string

max_steps: 8                      # int — hard ceiling on step count
composite_floor: 0.3              # float — floor used by composite_floor_consecutive stop condition
max_recursion_depth: 0            # int — 0 = no reinjection; N = allow N child sessions

steps: [...]                      # list[StepConfig]
stop_conditions: [...]            # list[StopConditionConfig]
clutch_rules: [...]               # list[ClutchRuleConfig]
catalyst_arms: [...]              # list[CatalystArmConfig] — optional
reinjection_triggers: [...]       # list[ReinjectionTriggerConfig] — optional
```

### StepConfig fields

```yaml
steps:
  - name: "understand_goal"
    description: "Analyze the goal and identify key constraints"
    role: "comprehension"                  # optional; semantic tag, not enforced
    prompt_template:
      template: |
        Goal: {{ goal }}
        
        Retrieved context:
        {{ retrieved_context }}
        
        {% if strategy_hint %}
        Strategic guidance: {{ strategy_hint }}
        {% endif %}
        
        Understand and analyze the goal thoroughly.
      expected_output_format: "prose"      # optional hint for signal evaluators
```

**Available template variables:**

| Variable | Source | Type |
|---|---|---|
| `{{ goal }}` | RuntimeSession.goal | str |
| `{{ retrieved_context }}` | `render_text(context_packet)` | str |
| `{{ prior_step_output }}` | last step's LLM output | str |
| `{{ prior_steps[N] }}` | Nth step's output (0-indexed) | str |
| `{{ strategy_hint }}` | CatalystEngine selected arm | str or empty |
| `{{ truth_tower }}` | `tower.render_chronological()` | str |
| `{% if var %}...{% endif %}` | Jinja2-style conditional | block |

### StopConditionConfig fields

```yaml
stop_conditions:
  - name: "hit_max_steps"
    type: "max_steps_reached"
    parameters:
      max_steps: 8          # int

  - name: "all_done"
    type: "all_steps_completed"
    parameters: {}          # no parameters

  - name: "floor_3_consecutive"
    type: "composite_floor_consecutive"
    parameters:
      floor: 0.35           # float
      n: 3                  # int — consecutive steps below floor

  - name: "clutch_said_stop"
    type: "explicit_clutch_stop"
    parameters: {}

  - name: "interrupted"
    type: "user_interrupt"
    parameters: {}
```

### ClutchRuleConfig fields

```yaml
clutch_rules:
  - name: "accept_high_quality"
    description: "Accept when composite exceeds threshold"
    predicate_name: "composite_above_threshold"
    action: "accept"
    parameters:
      threshold: 0.75       # predicate-specific

  - name: "stop_if_degrading"
    predicate_name: "consecutive_steps_below_floor"
    action: "stop"
    parameters:
      floor: 0.35
      n: 3
```

Rules are evaluated in config order. First match wins. If no rule matches, `escalate_to_catalyst=True`.

### CatalystArmConfig fields

```yaml
catalyst_arms:
  - arm_id: "constraint_check"
    type: "verification"               # semantic type (used by type_penalty)
    mapped_action: "critique"          # maps to a clutch action
    strategy_prompt: |
      Review the constraints on this problem carefully.
      Identify which constraints are hard (non-negotiable) vs. soft (negotiable).
      Make sure your plan respects all hard constraints.
```

### ReinjectionTriggerConfig fields

```yaml
reinjection_triggers:
  - name: "retry_if_no_acceptance"
    predicate: "max_steps_without_acceptance"   # must be in BUILTIN_REINJECTION_PREDICATE_NAMES
    parameters: {}
```

---

## 2. Built-in Cycle: `simple.planning.v0`

File: `cycles/simple.planning.v0.yaml`

**Purpose:** Basic linear planning cycle. No catalyst arms, no reinjection.

```
max_steps: 8
composite_floor: 0.35 (implicit via stop conditions)
max_recursion_depth: 0
```

### Steps (5)

| # | name | role | description |
|---|---|---|---|
| 1 | `understand_goal` | — | Analyze goal, identify constraints |
| 2 | `draft_plan` | — | Produce initial plan |
| 3 | `critique_plan` | — | Identify weaknesses in plan |
| 4 | `refine_plan` | — | Apply critique, improve plan |
| 5 | `finalize` | — | Produce final, polished output |

### Stop conditions (5)

1. `max_steps_reached` (max_steps=8)
2. `all_steps_completed`
3. `composite_floor_consecutive` (floor=0.35, n=3)
4. `explicit_clutch_stop`
5. `user_interrupt`

### Clutch rules (4)

| Rule | Predicate | Action |
|---|---|---|
| `accept_high_quality` | `composite_above_threshold(0.75)` | `accept` |
| `refine_if_low` | `composite_below_threshold(0.45)` | `refine` |
| `critique_if_medium` | `composite_in_range(0.45, 0.65)` | `critique` |
| `stop_if_degrading` | `consecutive_steps_below_floor(0.35, 3)` | `stop` |

No catalyst arms. No reinjection triggers.

---

## 3. Built-in Cycle: `planning.adaptive.v0`

File: `cycles/planning.adaptive.v0.yaml`

**Purpose:** Adaptive planning with catalyst arm selection and optional reinjection.

```
max_steps: 12
composite_floor: 0.3
max_recursion_depth: 3
```

### Steps (5, with roles)

| # | name | role | description |
|---|---|---|---|
| 1 | `understand_goal` | `comprehension` | Deep goal analysis |
| 2 | `draft_plan` | `generation` | Initial plan generation |
| 3 | `critique_plan` | `critique` | Critical analysis of plan |
| 4 | `refine_plan` | `refinement` | Integrate critique |
| 5 | `finalize` | `synthesis` | Synthesize final output |

### Stop conditions (5)

Same set as `simple.planning.v0`, with adjusted parameters:
1. `max_steps_reached` (max_steps=12)
2. `all_steps_completed`
3. `composite_floor_consecutive` (floor=0.3, n=4) — more lenient (lower floor, more consecutive)
4. `explicit_clutch_stop`
5. `user_interrupt`

### Clutch rules (6)

| Rule | Predicate | Action |
|---|---|---|
| `accept_high_quality` | `composite_above_threshold(0.78)` | `accept` |
| `refine_if_low` | `composite_below_threshold(0.40)` | `refine` |
| `critique_if_medium` | `composite_in_range(0.40, 0.65)` | `critique` |
| `epistemic_check` | `epistemic_humility_low(0.35)` | `retrieve_more` |
| `groundedness_boost` | `groundedness_low(0.40)` | `retrieve_more` |
| `stop_if_degrading` | `consecutive_steps_below_floor(0.30, 4)` | `stop` |

### Catalyst arms (5)

| arm_id | type | mapped_action | purpose |
|---|---|---|---|
| `constraint_check` | `verification` | `critique` | Identify hard vs. soft constraints |
| `decomposition` | `structuring` | `explore` | Break problem into sub-problems |
| `risk_assessment` | `verification` | `critique` | Identify risks and failure modes |
| `prerequisite_id` | `structuring` | `explore` | Identify what must be resolved first |
| `resource_estimate` | `estimation` | `refine` | Estimate resources needed |

### Reinjection triggers (1)

`max_steps_without_acceptance` — fires when cycle hits `cap_reached` and no step was accepted. With `max_recursion_depth=3`, allows up to 3 child sessions.

---

## 4. Fossic Event Reference

All Fossic events are appended to streams via `FossicStore.append()`. Every event has a `causation_id` (bytes) linking it to its predecessor in the chain.

### Stream: `cerebra/agent-trace/<session_id>`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `SessionOpened` | SessionManager | session_id, goal, cycle_config, opened_at, parent_session_id, recursion_depth |
| `CycleStarted` | CycleRuntime | session_id, cycle_id (= session_id), cycle_config, goal |
| `StepStarted` | CycleRuntime | step_index, step_name, cycle_id |
| `ContextPacketBuilt` | build_context_packet | context_packet_id, selected_count, is_abstained, mode |
| `PredictionMade` | PredictionPipeline | prediction_id, expected_composite, basis, confidence |
| `StepExecuted` | CycleRuntime | step_id, step_name, output (truncated), cited_record_ids |
| `StepExecutionFailed` | CycleRuntime | step_id, step_name, error, attempt_count |
| `SignalEvaluated` | EvaluationComposer | signal_name, score, strength, low_confidence |
| `EvaluationComposed` | EvaluationComposer | composite_score, confidence, per_signal, low_confidence_signals |
| `OutcomeRecorded` | PredictionPipeline | outcome_id, prediction_error, error_classification, actual_composite |
| `PredictionSevereMiss` | PredictionPipeline | outcome_id, prediction_error, step_name (error ≥ 0.15) |
| `ClutchDecisionMade` | ClutchEngine | action, rule_matched, escalate_to_catalyst, cascade_depth |
| `CatalystInvoked` | CatalystEngine | session_id, step_name, arm_count |
| `CatalystArmSelected` | CatalystEngine | arm_id, arm_type, strategy_prompt, score |
| `LeewayGrantApplied` | LeewayPreActionGate | rule_id, capability, grants_applied |
| `LeewayGrantDenied` | LeewayPreActionGate | rule_id, capability, forbidden_by |
| `LeewayRevocationFired` | LeewayPreActionGate | rule_id, capability, revocation_reason |
| `MemoryWriteFromCycle` | CycleRuntime | record_id, step_id, cited_record_ids |
| `CycleCompleted` | CycleRuntime | outcome, steps_run, final_composite |
| `SessionFlushed` | CycleRuntime | session_id, outcome, total_cycles, total_steps, flushed_at |
| `ReinjectionTriggered` | CycleRuntime | trigger_name, child_session_id, recursion_depth |
| `CheckpointSaved` | HTTP daemon | bundle_id, session_id |

### Stream: `cerebra/control`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `PostureChanged` | HTTP daemon | new_state ("auto"\|"hold"), previous_state |

### Stream: `cerebra/lattice/<lineage_id>`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `LatticeCommit` | SKUClassifier | primary_record_id, sibling_record_ids, lineage_id, categories, threshold |

### Stream: `cerebra/graph/<lineage_id>`

| Event type | Emitter | Key payload fields |
|---|---|---|
| `GraphSnapshotAvailable` | export_graph | graph_path, node_count, edge_count, vault_path, triggered_by |

---

## 5. Inspector Event Reference

Inspector events use the `InspectorEvent` dataclass (see doc 08). Key event types by subsystem:

### Vault / System

| Event type | actor | subject_id | Notes |
|---|---|---|---|
| `SystemInitialized` | system | vault_id | On any startup |
| `VaultCreated` | vault | vault_id | After init_vault() |
| `MigrationRun` | migrations | vault_id | Per migration applied |
| `ConfigLoaded` | config | vault_id | |
| `LeewayRuleLoaded` | governance | rule_id | Per rule loaded at startup |
| `ConstitutionalBlock` | governance | rule_id | When CONST rule would have forbidden (currently no-op) |

### Ingest

| Event type | subject_id | Notes |
|---|---|---|
| `SourceRegistered` | source_id | New source |
| `SourceChanged` | source_id | Content changed |
| `SourceParsed` | source_id | Successfully parsed |
| `SourceParseFailed` | source_id | Adapter raised exception |
| `DocumentNormalized` | document_id | |
| `DocumentParseWarning` | document_id | Partial parse success |
| `ChunkCreated` | chunk_id | Per chunk (may be high volume) |
| `MemoryRecordCreated` | record_id | Per record |
| `LexicalIndexUpdated` | — | After FTS5 rebuild |
| `ArtifactWritten` | document_id | After write_artifact() |

### SKU / Lattice

| Event type | subject_id | Notes |
|---|---|---|
| `SKUAssigned` | record_id | First classification |
| `SKUReclassified` | record_id | Version upgrade |
| `ClassificationFailed` | record_id | Unrecoverable error |
| `ClassificationLowConfidence` | record_id | confidence < 0.5 |
| `BackfillStarted` | — | |
| `BackfillCompleted` | — | Includes BackfillReport stats |
| `LatticeCommit` | lineage_id | Multi-category commit |

### Graph

| Event type | subject_id | Notes |
|---|---|---|
| `GraphNodeCreated` | node_id | During ingest (not export) |
| `GraphEdgeCreated` | edge_id | During ingest |
| `GraphExported` | out_path | After export_graph() |
| `GraphSnapshotAvailable` | lineage_id | Hub-direct write succeeded |

### Retrieval

| Event type | subject_id | Notes |
|---|---|---|
| `QueryReceived` | trace_id | |
| `QueryPlanned` | trace_id | Includes mode, d1_hint |
| `TraversalStepCompleted` | trace_id | Per step (6 events per retrieval) |
| `ContextPacketBuilt` | context_packet_id | |
| `LatticeSiblingResolved` | lineage_id | Per lattice group resolved |

### Memory / Tower

| Event type | subject_id | Notes |
|---|---|---|
| `AttentionItemProposed` | record_id | WM proposed |
| `AttentionItemPromoted` | wm_item_id | WM inserted |
| `AttentionItemEvicted` | wm_item_id | LRU evicted |
| `AttentionItemDeferred` | record_id | Capacity guard |
| `TowerInitialized` | session_id | First T1 promotion |
| `TowerItemPromoted` | tower_item_id | T1 or T2 |
| `TowerItemEvicted` | tower_item_id | Capacity eviction |
| `TowerItemStaled` | tower_item_id | T2 staled by T1 eviction |
| `TowerCrossReferenceAdded` | tower_item_id | T2 cites T1 |
| `TowerRendered` | session_id | `included_in_packet` flag |
| `MemoryRecordArchived` | record_id | |
| `MemoryRecordTombstoned` | record_id | |
| `MemoryRecordRestored` | record_id | |

---

## 6. Data Flows

### Ingest flow

```
cerebra ingest <target>
  ↓
discover_files(target, extensions, exclude_patterns)
  ↓ for each file:
  detect_type(file) → DetectionResult
  register_source(store, event_log, path, detection, versions)
    → RegistrationOutcome
  
  [SKIPPED_UNCHANGED] → skip file
  [NEW | CHANGED] → continue:
  
  adapter.parse(path, source) → ParseResult
  write_artifact() → <vault>/artifacts/<doc_id>.json
  write_text_artifact() → <vault>/data/<doc_id>.txt
  store.insert_document()
  upsert_node("source:<id>", "spine")
  upsert_node("document:<id>", "document")
  upsert_edge(source → document, "contains")
  chunk_document() → list[Chunk]
  store.insert_chunks_batch()
  for chunk: upsert_node + edges (CONTAINS, PART_OF)
  build_records_for_document() → list[MemoryRecord]
  store.insert_records_batch()
  for record: upsert_node + DERIVED_FROM edge
  update_fts_index(record_ids)       ← full FTS5 rebuild
  queue_for_embedding(record_ids)    ← deferred unless --embed
  source.parser_status = "parsed"
  emit SourceParsed
  ↓
IngestReport
```

### SKU Classify flow

```
cerebra classify
  ↓
query: memory_records WHERE sku_address IS NULL
  ↓ for each record (batch_size at a time):
  SKUClassifier.classify_record_lattice(record_id, content, detected_type)
    ↓
    LLM: classify_quadrant(content)          ← LLM call 1
      → 4 quadrant scores + primary quadrant
    LLM: classify_within_quadrant(content, q) ← LLM call 2
      → 4 category scores within quadrant + D1 answer
    evaluate_lattice(scores, threshold=0.65)
      → LatticeDecision (should_multi_commit?)
    
    [should_multi_commit=False]:
      store.insert_sku_assignment()
      store.update_record_sku()
      emit SKUAssigned
    
    [should_multi_commit=True]:
      insert primary sku_assignment
      for each secondary category:
        build_sibling_record_id(primary_id, category)  ← deterministic
        INSERT sibling into memory_records (is_lattice_member=True)
        INSERT sibling sku_assignment
      emit LatticeCommit (one event total, not per-sibling)
    
    if confidence < 0.5: emit ClassificationLowConfidence
    queue_for_embedding([primary_id, ...sibling_ids])
  ↓
BackfillReport
```

### Retrieval / Context flow

```
cerebra context <query>   OR   CycleRuntime._retrieve_for_step()
  ↓
RetrievalPlanner.plan(query)
  → QueryPlan {mode, trace_id, d1_hint, max_candidates}
  emit QueryReceived + QueryPlanned
  ↓
RetrievalTraversal.traverse(db_path, plan)
  Step 1: exact_sku      → candidates (if d1_hint)
  Step 2: partial_sku    → candidates (if d1_hint + need more)
  Step 3: sibling_traversal → pass-through (stub)
  Step 4: lexical_search → FTS5 MATCH (if lexical|hybrid)
  Step 5: vector_fallback → cosine similarity (if vector|hybrid)
  Step 6: trace_annotation → dedup + annotate retrieval_path
  emit TraversalStepCompleted ×6
  ↓
score_candidates(candidates, plan)
  composite = 0.40×semantic + 0.25×lexical + 0.15×sku + 0.10×recency + 0.10×lifecycle
  ↓
dedup_siblings(scored, query_d1, db_path, trace_id)
  D2 routing: sku_match → sku_match_multi → composite_score
  emit LatticeSiblingResolved per lattice group
  ↓
filter_by_floor(deduped, floor=0.35)
  → selected (≥ floor) + excluded
  ↓
  [selected is non-empty]:
    build_context_packet(trace, selected, limit=10)
      SELECT content, source info for top-10 records
      UPDATE retrieval_traces.context_packet_id
      TruthTower.to_tower_field() → tower dict
      emit ContextPacketBuilt
      → ContextPacket {is_abstained=False, selected_memory=[...]}
  
  [selected is empty]:
    build_abstained_packet(trace, best_score_seen)
      → ContextPacket {is_abstained=True, selected_memory=[]}
```

### Cycle Runtime flow

```
cerebra run-cycle <config> --goal "..."
  ↓
SessionManager.open_session(goal, config, vault_path)
  INSERT runtime_sessions
  fossic append SessionOpened → cerebra/agent-trace/<session_id>
  → (RuntimeSession, opened_event_id: bytes)
  ↓
CycleRuntime(config, session, db_path, store, llm, opened_event_id)
  fossic: CycleStarted (causation=opened_event_id)
  ↓
  LOOP while not stopped:
    StopConditionEvaluator.check(cycle_state) → (stop?, reason)
    if stop: break
    
    resolve step from config (round-robin if past last step)
    
    [RETRIEVAL]:
    RetrievalPlanner.plan(goal) → QueryPlan
    traverse → score → dedup_siblings → filter → packet
    fossic: ContextPacketBuilt
    
    [PREDICTION]:
    PredictionPipeline.predict(prior_composites) → PredictionRecord
    INSERT predictions
    fossic: PredictionMade
    
    [LLM]:
    render_template(step, {goal, retrieved_context, tower, strategy_hint})
    llm.chat(rendered_prompt) → output        [5s retry, 1 retry max]
    fossic: StepExecuted (or StepExecutionFailed)
    
    [EVALUATE]:
    for signal in SIGNAL_EVAL_ORDER:
      if signal == EPISTEMIC_HUMILITY: marker_based_eval()
      else: llm.complete_structured(signal_prompt, schema)
      fossic: SignalEvaluated (causation-chained)
    EvaluationComposer.compose(signals) → EvaluationPacket
    fossic: EvaluationComposed
    
    [OUTCOME]:
    PredictionPipeline.resolve(prediction, eval) → OutcomeRecord
    INSERT outcomes
    fossic: OutcomeRecorded
    if severe: fossic: PredictionSevereMiss
    
    [CITATIONS]:
    cited = re.findall(r'\brec_[0-9a-f]{12}\b', output)
    wm.promote(rec_id, salience=0.8) for each cited
    
    [CLUTCH]:
    ClutchEngine.decide(context) → ClutchDecision
    fossic: ClutchDecisionMade
    if clutch.escalate_to_catalyst:
      CatalystEngine.select() → CatalystSelection | None
      if selected: fossic: CatalystInvoked + CatalystArmSelected
    
    [GOVERNANCE]:
    LeewayPreActionGate.evaluate(ProposedAction("write_to_episodic_memory"))
    if permitted:
      fossic: LeewayGrantApplied
      EpisodeWriter.write(output, ...) → record_id
        INSERT cycle_episode_records
        INSERT memory_records (record_type="cycle_episode", synthetic FKs)
        queue_for_embedding([record_id])
      fossic: MemoryWriteFromCycle
    
    cycle_state.steps_run += 1
    prior_composites.append(eval.composite_score)
    if clutch.action == "stop": cycle_state.explicit_stop = True
  ↓
fossic: CycleCompleted {outcome, steps_run, final_composite}
SessionManager.flush_session(session_id, outcome, ...)
fossic: SessionFlushed
  ↓
[REINJECTION]:
ReinjectionTriggerEvaluator.evaluate(reason, step_history, depth, max_depth)
if should_fire AND not blocked:
  BundleDistiller.distill(...) → ContinuationBundle
  write_bundle(db_path, bundle)
  SessionManager.open_session(parent_session_id=session_id)  ← recursive
  CycleRuntime(child_session).run()
  fossic: ReinjectionTriggered
  ↓
return CycleResult
```

### Graph Export flow

```
cerebra export-graph [--out PATH]
  ↓
export_graph(vault_path, out_path, event_log, hub_store, triggered_by)
  ↓
  SQL: SELECT active sources WHERE canonical_path NOT LIKE 'cerebra://%'
    ORDER BY canonical_path LIMIT 2000
  SQL: SELECT active records JOIN sku_assignments ON record_id
    (only classified records get nodes)
  
  BUILD nodes:
    spine node per source:
      id="source:<source_id>", type="spine"
      cluster: detected_type → azure|slate|gray|teal
    memory_record node per classified record:
      id="record:<record_id>", type="memory_record"
      cluster: d1_quadrant → azure|gold|purple|teal
  
  BUILD edges:
    contains: source→record (weight=0.4) for each record's source
    describes: record[N]→record[N+1] (weight=0.65) for adjacent chunk_index pairs in same doc
    sku-proximity: record→record (weight=min(0.5, group_size/20)) for shared D1
      → capped at _SKU_PROXIMITY_CAP=5 per node
    sku-exact: record→record (weight=0.9) for identical sku_address
  
  WRITE: <vault>/.cerebra/graph.json (cerebra/v1 schema)
  
  [if hub_store]:
    hub_store.append(
      "cerebra/graph/<lineage_id>",
      "GraphSnapshotAvailable",
      {graph_path, node_count, edge_count, ...}
    )
    ← errors swallowed (non-fatal)
  
  emit GraphExported inspector event
  return ExportStats
```
