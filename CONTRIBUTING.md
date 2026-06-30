# Contributing to cerebra-classic

**This fork is an archival snapshot.** It is not the venue for new feature
work. Active development of Cerebra continues at
[bitmosh/cerebra](https://github.com/bitmosh/cerebra) — please direct new
contributions there.

## What this fork accepts

The full maintenance policy is in [README.md](README.md). In short, this fork
accepts:

- Critical security patches that affect the runnable baseline
- Documentation corrections that improve accuracy of the snapshot
- Dependency version pin updates if a pinned dependency becomes permanently
  unavailable

This fork rejects: new features, architectural changes, performance
improvements, and cosmetic refactors.

## How to propose a change

1. Open an issue first describing the change and its rationale.
2. If maintainers agree the change is in scope, open a PR.
3. Match the conventions already in the codebase. Tooling pins are exact
   (`ruff==0.4.8`, `black==24.4.2`, `mypy==1.10.0`); use those versions.
4. CI must pass: lint, type-check, and the non-integration test suite all
   stay green. See `.github/workflows/test.yml`.

## Dev environment

```bash
uv sync --extra dev   # plain `uv sync` does not install dev deps
make test-quick       # fast tests; skips integration
make verify-docs      # confirms doc index entries exist
```

For the full test suite (including integration tests that load ~1.5 GB of
ML models): `make test`.

## Coding standards

- Type hints are required (`mypy --strict` runs in CI).
- Single-purpose, descriptive commit messages. One concern per commit.
- Inspector events are load-bearing — every cognitive action should emit one.
- Provenance is non-negotiable for memory records.

For the full design context, read
[`docs/CEREBRA_CLASSIC.md`](docs/CEREBRA_CLASSIC.md) and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
