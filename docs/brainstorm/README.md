# Brainstorm

This directory captures design intuitions, philosophical frameworks, and architectural ideas that aren't yet committed to the Cerebra roadmap.

## What lives here

- Concepts that may inform v0.2+ design but aren't load-bearing yet
- Philosophy that shapes architectural decisions
- Reframes that change how we think about problems
- Threads from design conversations worth preserving

## What doesn't live here

- Anything in the active roadmap (lives in `docs/refined-runtime-model/`)
- Anything bandit needs to read to implement current work
- Operating protocol (lives in `docs/agent/`)

## Rules

When a brainstorm doc graduates to dev-path work, it moves out of this directory into the appropriate canonical doc and is removed from here. **This is staging, not archive.**

A brainstorm doc is allowed to be wrong. The point is to preserve thinking-in-progress, not to be authoritative. Future me might disagree with some of what's here. That's fine — it's a record of how the design was evolving.

Date-stamp each doc at the top. Drift over time IS useful information about how the design matured.

## Structure

```
brainstorm/
├── philosophy/          # foundational frameworks, mental models
├── architecture/        # design concepts not yet on dev path
├── reframes/            # strategic shifts in how we think about problems
└── DEFERRED_DOCS.md     # backlog of docs to write when time allows
```

## Current contents (2026-06-05)

**Status:** v0.1.0 shipped on 2026-06-06. Several reframes here have transitioned from hypothesis to implemented architecture. Where docs reflect that transition, they note "What actually shipped" sections. Docs that remain hypothetical (counsel mode, cognitive nature as perceptual lens) describe future-state architecture.

### Philosophy
- `triangle_balance_perception_understanding.md` — the three-corner perceptual model with attentive gravity

### Architecture
- `counsel_swarm_cognition.md` — multi-model deliberation pattern for ambiguity

### Reframes
- `two_thinking_systems_disruption.md` — Cerebra as thinking architecture, models as substrate
- `v01_as_substrate_for_lora.md` — v0.1 produces training signal, not final accuracy
- `cognitive_nature_as_perceptual_lens.md` — long-term vision: taxonomy as perceptual structure

### Backlog
- See `DEFERRED_DOCS.md` for docs to write later

## Format guidance

These can be informal. Not every doc needs the rigor of `CEREBRA_ARCHITECTURE.md`. A philosophy doc can be 3 paragraphs and a useful framing diagram. An architecture sketch can be a 5-bullet outline of an idea. Lower the bar; raise the volume of capture. Polish the ones that prove useful by getting referenced or built on.
