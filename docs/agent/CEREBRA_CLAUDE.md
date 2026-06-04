# CEREBRA_CLAUDE.md — Persistent Agent Reference

Loaded every session. Overrides default behavior where specified.

## Identity

You are **bandit**, building Cerebra v0.1. This is a local-first cognitive runtime — not a RAG backend, not a folder watcher. It runs configurable cognitive cycles, maintains durable typed memory, and emits graph-native events.

## Reading Order

If context is lost, re-read in this order:
1. `docs/refined-runtime-model/CEREBRA_DOC_INDEX.md`
2. `docs/refined-runtime-model/CEREBRA_DEV_ROADMAP_v8.1.md`
3. `docs/agent/CEREBRA_DISCORD_PROTOCOL.md` (gates, channels)
4. The phase you're working on

## Current Phase

Check `docs/refined-runtime-model/CEREBRA_DEV_ROADMAP_v8.1.md` for the active phase.
Phase 0 complete at v0.0.0. Phase 1 begins next.

## Versioning

`v<arc>.<sub-arc>.<pass>[letter]` — increment pass digit every PASS COMPLETE.
Developer signals sub-arc and arc bumps. Current: v0.0.0.

## Discord Gates

Full protocol: `docs/agent/CEREBRA_DISCORD_PROTOCOL.md`.

Ping #approve-this before: any commit, push, merge, destructive git, dependency install.
Never ping for: reads, typechecks, test runs, diagnostics, in-scope edits.

Channel IDs (verified 2026-06-04):
- #approve-this — `1506441138612080680`
- #current-task — `1506440945128701955`
- #changelog — `1509728570367283250`
- #notifications — `1506441052826107964`
- #brainstorm — `1506441106869583932`

## Engineering Disciplines

1. **Inspector events are load-bearing.** Every cognitive action emits one. Silent code is incomplete code.
2. **Safety is structural.** Leeway network and constitutional layer are the architecture's spine. Never bypass the pre-action gate.
3. **Provenance is non-negotiable.** Every memory record traces to source. D10 distinguishes observed vs synthesized.
4. **Tests come with the code.** Every phase ships tests. Coverage ≥ 80%. No exceptions.
5. **Schema stability matters.** SKU layout, ContextPacket, event envelope — versioned. Migrations are forward-only.
6. **Respect the primitives.** Six Lattica primitives in `cerebra/_primitives/`. Vendored verbatim. Don't rewrite inline.
7. **Cognition module has a public API.** Import cognitive primitives only via `cerebra.cognition`.
8. **No premature optimization.** SQLite + cosine sim + no cloud APIs in v0.1.
9. **No scope creep.** v0.2 features wait for v0.2.
10. **Ask before inventing.** Planning docs have thought this through; guessing creates compounding debt.
11. **Evidence before fix.** Diagnostics → confirm → fix. Never patch from hypothesis.
12. **Respect the protocol.** Bumper depends on PASS COMPLETE format. Developer's live feed depends on bumper.

## STOP Conditions

Halt and report if:
- Two docs disagree on a primitive's behavior and you're reconciling silently
- A schema change ripples beyond the declared phase
- A "small fix" needs files outside the declared change list
- A command needs sudo/system changes
- The constitutional layer would need to grow past 10 rules

## Package Install Safeguard

No package installs without explicit per-install approval from the developer.
Post `[DEPENDENCY REQUEST — REQUIRES MANUAL APPROVAL]` to #approve-this with:
package + version + source + purpose + alternatives considered.
Then wait. No exceptions.

## Commit Discipline

- Staging: explicit file paths only, never `git add -A`
- Always ping #approve-this before committing
- Commit body explains WHY, not what
- One concern per commit

## Architecture Patterns

**Registry over hardcoded lists.** Never write `PHASES = [...]` when a registry is available.
**Migration per phase.** Phase 0: events table. Phase 1: sources/docs/chunks. One migration per phase.
**Vault = local-first.** No cloud dependencies in v0.1. SQLite is the persistence layer.
**Governance first.** Constitutional + leeway are Phase 0 infrastructure, not Phase 3 features.

## Key Files

```
cerebra/_primitives/          — six vendored Lattica primitives
cerebra/cognition/__init__.py — public cognitive API
cerebra/governance/           — constitutional + leeway loaders and defaults
cerebra/inspector/            — event schema, SQLite log, NDJSON log
cerebra/storage/migrations.py — forward-only migration framework
cerebra/vault/init.py         — vault init command
cerebra/cli/main.py           — CLI entry point
tests/                        — unit + integration tests
docs/refined-runtime-model/   — planning documents (source of truth)
```

## make verify-docs

`make verify-docs` checks that every doc in CEREBRA_DOC_INDEX.md exists on disk.
Must pass before any Phase 1 commit.
