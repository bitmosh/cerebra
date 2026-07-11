# cerebra
[![Release](https://img.shields.io/github/v/release/bitmosh/cerebra?include_prereleases)](https://github.com/bitmosh/cerebra/releases)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/bitmosh/cerebra/actions/workflows/test.yml/badge.svg)](https://github.com/bitmosh/cerebra/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/badge/Coverage-82%25-green.svg)](https://github.com/bitmosh/cerebra)

A local-first cognitive cycle runtime built in Python. Structured multi-step reasoning against a personal knowledge vault, with signal-based evaluation and rule-driven control.

**v0.4.5** · **Python 3.12+** · **Apache-2.0** · **Status: Active — alpha**

---

<!-- OPERATOR: capture a terminal screenshot or GIF showing a cycle run.
     Suggested command:
       cerebra run-cycle simple.planning.v0 \
         --goal "What are the key patterns in knowledge-intensive systems?" \
         --vault examples/demo-vault
     followed by: cerebra inspect cycle show --signals --vault examples/demo-vault
     Save to: docs/assets/demo.gif -->

## What this is

Cerebra is a configurable cognitive runtime — not a RAG pipeline, not a chatbot wrapper. Each cognitive cycle retrieves context from an ingested knowledge vault, calls a local LLM (Ollama), and evaluates the output across six epistemic signals. A rule engine (Clutch) routes the next action; a bandit-driven strategy selector (Catalyst) handles escalation. The cycle writes the result as a dual-format episode and decides whether to continue, recurse, or stop. Every action leaves an inspectable trace.

**What's shipped in v0.4.5:**
- 21-command CLI (init, ingest, search, run-cycle, inspect, export, serve)
- Hybrid retrieval — lexical (FTS5) + vector (mxbai-embed-large-v1) + SKU-shaped + graph-expanded
- ClutchEngine — priority-rule controller with hysteresis, mode persistence, cascade depth
- CatalystEngine — bandit-driven (epsilon-greedy + UCB1) arm selection over five cognitive strategy arms
- TruthTower — five-tier derived workspace (T1 Evidence → T5 Goal)
- Re-injection loop — continuation bundles span context window limits across child sessions
- Six epistemic signal evaluators — coherence, groundedness, relevance, precision, generativity, epistemic humility
- Leeway network — three-tier safety architecture (constitutional, capability, conditional grants)
- Inspector CLI — forensic query surface over events, sessions, cycles, signals, leeway
- Dual persistence — SQLite (18 migrations) + optional FossicStore causation-chained event streams
- Graph export to visualization-compatible JSON

## Status

Active development. The system is functional end-to-end and tested against real Ollama, but this is alpha software with known limitations. Use at your own risk; see [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) and [`docs/TECH_DEBT.md`](docs/TECH_DEBT.md) for what's tracked. Contributions welcome.

For historical context on how the system was built (14-phase development arc, architecture rationale) see [`docs/HISTORY.md`](docs/HISTORY.md). For per-subsystem technical detail see [`docs/ARCHITECTURE_STATE.md`](docs/ARCHITECTURE_STATE.md).

---

## Setup

**Prerequisites:** Python 3.12+, Ollama running locally.

Cerebra runs standalone. fossic provides the causation-chained event store used by the cycle runtime and daemon; install with the `fossic` extra when using `run-cycle` or `serve`.

```bash
git clone https://github.com/bitmosh/cerebra
cd cerebra

# Minimal install (search, ingest, inspect — no cycle runtime)
pip install -e ".[dev]"

# Full install (adds fossic for run-cycle, serve, graph export event emission)
pip install -e ".[dev,fossic]"
```

```bash
# Quick demo
cerebra init examples/demo-vault --force
cerebra ingest examples/docs --vault examples/demo-vault
cerebra run-cycle simple.planning.v0 \
  --goal "What are the key patterns in knowledge-intensive systems?" \
  --vault examples/demo-vault
cerebra inspect cycle show --signals --vault examples/demo-vault
```

Full setup instructions (prerequisites, Ollama, vault layout): [`docs/SETUP.md`](docs/SETUP.md)

---

## Which commands need fossic

| Command | Fossic required | What fossic adds |
|---|---|---|
| `init`, `ingest`, `search`, `classify`, `context`, `lifecycle`, `memory`, `reindex`, `session`, `status` | No | SQLite-only paths, no event emission |
| `run-cycle` | Yes | All cycle/step/signal events — the entire inspector trail |
| `serve` | Yes | PostureChanged, CheckpointSaved events over HTTP |
| `export graph` | No | Optional GraphSnapshotAvailable notification to hub |
| `inspect` (event streams) | Yes | Reads directly from FossicStore |

If a fossic-requiring command is invoked without the extra installed, it fails at startup with a clear message. Everything else runs.

---

## Repository

```
cerebra/           — runtime source (CLI, cognition, retrieval, storage, sources)
cerebra/_primitives/ — internal shared primitives (Clutch, Catalyst components, etc.)
cycles/            — built-in cycle configs (YAML)
docs/
  HISTORY.md            — development arc, 14 build phases, architectural rationale
  ARCHITECTURE.md       — architecture overview
  ARCHITECTURE_STATE.md — per-subsystem technical state reports
  SETUP.md              — full setup instructions
  KNOWN_ISSUES.md       — tracked open issues
  TECH_DEBT.md          — tracked debt and deferred work
examples/docs/     — demo vault documents
tests/             — unit + integration test suite
```

---

## Ecosystem

Cerebra is part of the [Lattica](https://github.com/bitmosh/lattica) ecosystem — a set of local-first tools that share the [fossic](https://github.com/bitmosh/fossic) event store as their persistence substrate. Related projects:

- **[fossic](https://github.com/bitmosh/fossic)** — content-addressed event store substrate
- **[lattica](https://github.com/bitmosh/lattica)** — observability hub for the ecosystem
- **[lumaweave](https://github.com/bitmosh/lumaweave)** — graph visualization
- **[policy-scout](https://github.com/bitmosh/policy-scout)** — safety harness

Cerebra can be used standalone (SQLite-only) or as part of the ecosystem (with fossic).

---

## License

Apache-2.0 — see [`LICENSE`](LICENSE) for the full text.
