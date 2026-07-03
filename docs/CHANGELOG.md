# Changelog — Cerebra Classic

All notable changes to this repository. Grouped by category; each entry cites
at least one commit SHA. Dates are ISO 8601.

---

## [v0.4.4-pre-dyson] — 2026-06-21 (baseline tag)

The state preserved as cerebra-classic. All 14 build phases complete and
spine-tested against real Ollama.

### Added

- **Phase 1 — Core vault and ingest pipeline:** source registration with
  content-hash change detection, markdown/text parsing, chunk pipeline,
  `SourceRecord` with stable content-addressed `source_id`, Inspector event
  emission, SQLite connection factory with WAL + FK enforcement.
- **Phase 2 — SKU classification** (M002): 10-digit cognitive-shape addressing
  across 16 quadrant categories; LLM-driven classifier.
- **Phase 3 — Embeddings and vector search** (M003): `mxbai-embed-large-v1`
  (1024-dim float32), cosine search, FTS5 lexical index.
- **Phase 4 — Graph model** (M004, M005): `graph_nodes` + `graph_edges` tables,
  bidirectional source/memory links, graph export path.
- **Phase 5 — Working memory and retrieval tracing** (M006–M009):
  `WorkingMemorySession`, `TruthTower` (T1–T5), `ContextPacket` builder,
  full retrieval tracing with component scores.
- **Phase 6 — Signal evaluation and prediction** (M010, M011): six epistemic
  signal evaluators; prediction error layer feeding Catalyst learning signal.
- **Phase 7 — Clutch controller** (M012): priority-rule action router with
  hysteresis, mode persistence, cascade depth, compound predicates.
- **Phase 8 — Cognitive session and cycle runtime** (M013, M014): `CycleRuntime`,
  structured cycle YAML config, multi-step execution with stop conditions.
- **Phase 9 — Catalyst / strategy selector** (M015): epsilon-greedy + UCB1
  bandit over five cognitive strategy arms.
- **Phase 10 — Cognitive loop closure** (M016): cycle episodes bridge into
  retrieval; dual-format episode persistence (SQLite + FossicStore). (`cdca7dc`)
- **Phase 11 — Lifecycle manager** (M017): archive, tombstone, restore on
  memory records with stale detection. (`c271d3b`)
- **Phase 12 — Graph export** (M018): `cerebra/v1` JSON for LumaWeave
  visualization; synthetic FK sentinel rows in M018. (`04c4022`)
- **Phase 13 — Inspector CLI**: `cerebra inspect` command group covering
  sessions, cycles, signals, leeway, fossic events. (`dbe81bd`)
- **Phase 14 — Integration testing and polish**: full spine E2E test suite;
  re-injection loop; leeway network (constitutional, capability, conditional
  grants); HTTP daemon. (`4efb2bb`)

### Fixed

- `cerebra --version` now reads from package metadata via `importlib.metadata`
  rather than a hardcoded string. (`9cd2e31`)
- HTTP daemon CORS header added to `_send_json`, unblocking Tauri webview
  access. (`140c12b`)

---

## [post-archive] — 2026-06-21 to 2026-07-02 (infrastructure only)

No changes to the cognitive architecture or CLI surface.

### Added

- Hub-direct `GraphSnapshotAvailable` emission in graph exporter when
  `CEREBRA_PLATFORM_STORE` env var is set. (`2089667`)
- `cerebra-relay.py`: relay agent subscribing `cerebra/**` on the local vault
  store and forwarding to the Lattica hub fossic store. (`e2b202e`)
- CI pipeline: lint (ruff + black), type-check (mypy), unit tests
  (`pytest -m "not integration"`). (`f39f10b`)
- Archive documentation: `docs/CEREBRA_CLASSIC.md`, `docs/ARCHITECTURE.md`,
  `docs/archive/` bundle (STATE_REPORTS, DEVELOPMENT_LOG, DESIGN_SPECS).
  (`e23a309`)
- Vendored fossic wheel: `vendor/fossic-1.8.1-cp312-cp312-manylinux_2_34_x86_64.whl`.
  CI is now fully self-contained with no external repo access required.
  (`2239061`)

### Changed

- README rewritten: capabilities-first structure, setup quickstart, archival
  rationale. (`f39f10b`)
- fossic dependency changed from hardcoded local path to vendored pre-built
  wheel; no Rust toolchain required for install. (`2239061`)

### Removed

- 21 LoRA training artifact files (`scripts/v02_training/output/`) removed from
  tracking; covered by `.gitignore`. Training scripts and corpus methodology
  remain.

### Fixed

- Hardcoded developer machine path in fossic dep
  (`file:///home/boop/...`) replaced with vendored wheel. (`2239061`)

---

## What's next

Cerebra Classic is a preserved baseline. Active development continues in
[Cerebra](https://github.com/bitmosh/cerebra) (post-dyson-sphere).

**Planned in the active repo:**
- Replace `cerebra.db` with Rust-native projections on fossic streams
  (dyson sphere migration)
- Remove SQLite dual-write burden and synthetic FK sentinel rows (M018)
- Native Rust event-sourced retrieval and session state

No timeline commitments. Track progress in the active repo's commit log.
