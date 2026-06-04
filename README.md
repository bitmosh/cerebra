# Cerebra

A local-first cognitive runtime. Memory is one subsystem; the runtime is the project.

Part of the [Lattica](https://github.com/bitmosh) suite alongside LumaWeave and Bons.ai. Each project is standalone — connection happens through data contracts and graph-native event emission, not runtime dependencies.

## Status

**v0.1 in development.** Architecture complete (28 planning docs in `docs/refined-runtime-model/`). Implementation in progress per `docs/refined-runtime-model/CEREBRA_DEV_ROADMAP_v8.1.md`.

## What Cerebra is

A configurable cognitive cycle runtime that:
- Maintains durable memory across sessions
- Manages working context with bounded contested slots
- Evaluates outputs across six epistemological signals
- Learns from prediction error
- Operates within structural safety bounds (capability + leeway + constitutional layers)
- Emits inspectable graph-native events for downstream visualization

Bons.ai will eventually be expressible as one cycle configuration that Cerebra runs.

## What Cerebra is not

- Not a RAG system (memory is a substrate, not the product)
- Not a visualization layer (LumaWeave does that)
- Not a safety harness for arbitrary agent commands (Policy Scout will do that)
- Not cloud-dependent (local-first by default)

## Getting started

This repo is in pre-v0.1 setup. The implementing agent reads from `docs/refined-runtime-model/CEREBRA_KICKOFF_PROMPT.md`. Phase 0 of the dev roadmap establishes the project scaffolding.

For documentation: `docs/refined-runtime-model/CEREBRA_DOC_INDEX.md`

## License

MIT (see LICENSE)
