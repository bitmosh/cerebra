# cerebra-classic — Agent Context

This is an **archive repository**. No active development phases. The system is at v0.4.4-pre-dyson (14 phases complete, v0.1 ship gate passed).

## What to read first

- `docs/CEREBRA_CLASSIC.md` — development arc, current state, architecture rationale
- `docs/ARCHITECTURE.md` — technical reference for all subsystems
- `docs/archive/STATE_REPORTS.md` — per-subsystem implementation detail

## What this repo accepts

- Critical security patches that affect the runnable baseline
- Documentation corrections
- Dependency version pin updates if a pinned dependency becomes unavailable

Reject: new features, architectural changes, performance improvements.

## Engineering disciplines

1. Inspector events are load-bearing. Every cognitive action emits one.
2. Safety is structural — leeway network and constitutional layer are spine, not afterthought.
3. Every memory record traces to source. Synthesized memories are distinguishable from observed.
4. Schema stability matters. Migrations are forward-only.
5. Evidence before fix. Diagnostics → confirm → fix. Never patch from hypothesis.

## Key entry points

```
cerebra/cli/main.py           — 21-command Click group
cerebra/cognition/            — CycleRuntime, ClutchEngine, CatalystEngine, signal evaluators
cerebra/storage/              — SQLiteStore, FossicStore, embeddings, FTS5, migrations
cerebra/_primitives/          — vendored shared primitives
cycles/                       — built-in YAML cycle configs
tests/                        — unit + integration test suite
```

## Dependency note

`fossic` ships as a pre-built wheel in `vendor/` — no Rust toolchain required. See `pyproject.toml` for the vendored dep path (`file:vendor/fossic-1.8.1-...whl`).
