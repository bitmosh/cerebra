# Cerebra

A local-first cognitive runtime. Memory is one subsystem; the runtime is the project.

Part of the [Lattica](https://github.com/bitmosh) suite. Each project is standalone — connection happens through data contracts and graph-native event emission, not runtime dependencies.

## Status

**v0.4.4** — All 14 build phases complete. Full spine tested against real Ollama. See [`docs/CEREBRA_CLASSIC.md`](docs/CEREBRA_CLASSIC.md) for the full development arc and current state.

## What Cerebra is

A configurable cognitive cycle runtime that:
- Maintains durable memory across sessions
- Manages working context with bounded contested slots
- Evaluates outputs across six epistemological signals (coherence, groundedness, relevance, precision, generativity, epistemic humility)
- Learns from prediction error via a bandit selector
- Operates within structural safety bounds (capability + leeway + constitutional layers)
- Emits inspectable graph-native events for downstream visualization


## What Cerebra is not

- Not a RAG system (memory is a substrate, not the product)
- Not a visualization layer (LumaWeave does that)
- Not a safety harness for arbitrary agent commands (Policy Scout will do that)
- Not cloud-dependent (local-first by default, Ollama required)

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai) running locally (default `http://127.0.0.1:11434`)
- A model pulled in Ollama, e.g. `ollama pull granite3.2:3b`

## Setup

```bash
uv sync --extra dev   # not plain `uv sync` — pytest/numpy land outside the venv otherwise
```

## Quickstart

```bash
# 1. Initialize a vault
cerebra init ~/my-vault

# 2. Ingest a directory of Markdown documents
cerebra ingest ~/my-vault/docs --vault ~/my-vault

# 3. Search memory
cerebra search "event sourcing trade-offs" --vault ~/my-vault

# 4. Run a cognitive cycle
cerebra run-cycle simple.planning.v0 \
  --goal "Summarize the key trade-offs of event sourcing" \
  --vault ~/my-vault

# 5. Inspect what happened
cerebra inspect session list --vault ~/my-vault
cerebra inspect cycle show <cycle_id> --signals --vault ~/my-vault
cerebra inspect query --event-type CycleCompleted --vault ~/my-vault

# 6. Export the knowledge graph
cerebra export graph --vault ~/my-vault
```

## Example vault

The `examples/` directory contains a ready-to-run demo:

```bash
cerebra init examples/demo-vault --force
cerebra ingest examples/docs --vault examples/demo-vault
cerebra run-cycle simple.planning.v0 \
  --goal "What are the key patterns in knowledge-intensive systems?" \
  --vault examples/demo-vault
```

## Cycle configs

Built-in configs live in `cycles/`:

- `simple.planning.v0` — five-step planning cycle (understand → draft → critique → refine → finalize)
- `planning.adaptive.v0` — adaptive variant with bandit-driven strategy selection

Custom configs go in `<vault>/cycles/<name>.yaml`.

## Inspecting the runtime

```bash
# List sessions
cerebra inspect session list

# Show cycle detail with signals
cerebra inspect cycle show <cycle_id> --signals

# Stream live events
cerebra inspect query --tail

# Find low-scoring signals
cerebra inspect query --signal-low COHERENCE --threshold 0.5

# Show active leeway grants
cerebra inspect leeway active
```

## Running tests

```bash
# Unit tests only (no model loading)
.venv/bin/python -m pytest -m "not integration"

# Full suite including E2E spine (requires Ollama)
.venv/bin/python -m pytest tests/integration/test_e2e_spine.py -m integration -v
```

## Architecture

```
vault/
  data/cerebra.db      — SQLite: memory records, retrieval traces, events
  .fossic/store.db     — FossicStore: cycle events, session streams
  .cerebra/graph.json  — exported knowledge graph
  cycles/              — custom cycle config YAML files
```

Core pipeline: `ingest_path` → `query_plan` → `run_traversal` → `score_candidates` → `CycleRuntime` → `FossicStore` events

For documentation: [`docs/CEREBRA_CLASSIC.md`](docs/CEREBRA_CLASSIC.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## License

MIT (see LICENSE)
