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
