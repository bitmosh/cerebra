# cerebra-classic

A local-first cognitive cycle runtime built in Python. Fourteen build phases, fully tested against real Ollama. Preserved here as the pre-dyson-sphere baseline — the state immediately before portions of the persistence layer migrate into a Rust-backed event-sourced substrate.

**v0.4.4** · **Python 3.12+** · **MIT**

---

## What this is

Cerebra is a configurable cognitive runtime — not a RAG pipeline, not a chatbot wrapper. Each cognitive cycle retrieves context from an ingested knowledge vault, calls a local LLM (Ollama), evaluates the output across six epistemic signals, routes the next action through a rule engine (Clutch), optionally escalates to a bandit-driven strategy selector (Catalyst), writes the result as a dual-format episode, and decides whether to continue, recurse, or stop. Every action leaves an inspectable trace.

**What's shipped at v0.4.4:**
- 21-command CLI (init, ingest, search, run-cycle, inspect, export, serve)
- Hybrid retrieval — lexical (FTS5) + vector (mxbai-embed-large-v1) + SKU-shaped + graph-expanded
- ClutchEngine — priority-rule controller with hysteresis, mode persistence, cascade depth
- CatalystEngine — bandit-driven (epsilon-greedy + UCB1) arm selection over five cognitive strategy arms
- TruthTower — five-tier derived workspace (T1 Evidence → T5 Goal)
- Re-injection loop — continuation bundles span context window limits across child sessions
- Six epistemic signal evaluators — coherence, groundedness, relevance, precision, generativity, epistemic humility
- Leeway network — three-tier safety architecture (constitutional, capability, conditional grants)
- Inspector CLI — forensic query surface over events, sessions, cycles, signals, leeway
- Dual persistence — SQLite (18 migrations) + FossicStore causation-chained event streams
- Graph export to visualization-compatible JSON

Full technical narrative: [`docs/CEREBRA_CLASSIC.md`](docs/CEREBRA_CLASSIC.md)  
Architecture reference: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Setup

**Prerequisites:** Python 3.12+, Rust toolchain (for fossic), Ollama running locally.

```bash
git clone https://github.com/bitmosh/cerebra-classic
cd cerebra-classic
pip install -e ".[dev]"
```

fossic is a Rust/PyO3 extension — pip will compile it from source automatically if Rust is installed. Install Rust via [rustup.rs](https://rustup.rs) if needed.

```bash
# Quick demo
cerebra init examples/demo-vault --force
cerebra ingest examples/docs --vault examples/demo-vault
cerebra run-cycle simple.planning.v0 \
  --goal "What are the key patterns in knowledge-intensive systems?" \
  --vault examples/demo-vault
cerebra inspect cycle show --signals --vault examples/demo-vault
```

Full setup instructions (prerequisites, Ollama, vault layout): [`README_CEREBRA_ORIGINAL.md`](README_CEREBRA_ORIGINAL.md)

---

## Why this fork exists

Cerebra's persistence layer uses a dual strategy: SQLite (18 schema migrations, mutable relational store) alongside FossicStore (Rust, content-addressed, causation-chained event streams). These two approaches to state — CRUD vs. event-sourced replay — coexist with real friction: WAL discipline hand-enforced across modules, synthetic FK sentinel rows to satisfy constraints that shouldn't exist, dual-write sequencing without a transaction primitive.

The dyson sphere migration replaces `cerebra.db` with Rust-native projections on fossic streams. This fork preserves the before state — inspectable, runnable, and citable — so the architectural delta is concrete rather than speculative.

The cognitive architecture (Clutch, Catalyst, re-injection loop, TruthTower, signal evaluators, leeway network) is identical in both versions. Only the persistence substrate changes.

Full writeup: [`docs/CEREBRA_CLASSIC.md` — Why This Is Archived as Classic](docs/CEREBRA_CLASSIC.md#why-this-is-archived-as-classic--the-sqlite-mismatch)

---

## Repository

```
cerebra/           — runtime source (CLI, cognition, retrieval, storage, sources)
cerebra/_primitives/ — vendored shared primitives (Clutch, Catalyst components, etc.)
cycles/            — built-in cycle configs (YAML)
docs/
  CEREBRA_CLASSIC.md   — development arc, current state, architecture rationale
  ARCHITECTURE.md      — technical reference (subsystems, migrations, event types)
  KNOWN_ISSUES.md      — tracked defects acknowledged in the archive
  archive/             — historical design docs and development logs
examples/docs/     — demo vault documents
tests/             — unit + integration test suite
```

---

## Maintenance policy

Accepts: critical security patches, documentation corrections, dependency pin updates.  
Rejects: new features, architectural changes, performance improvements (those go in the live Cerebra).

---

## Related

- **[fossic](https://github.com/bitmosh/fossic)** — content-addressed event store substrate (v1.6.0, 2026-06-21)
- **[Cerebra](https://github.com/bitmosh/cerebra)** — active development, post-dyson-sphere

## License

MIT — see `LICENSE`.
