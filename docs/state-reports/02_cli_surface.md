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
