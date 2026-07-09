# Contributing to Cerebra

Cerebra is an active alpha-stage local-first cognitive runtime. Contributions
of any size are welcome, but please understand that responses may be slow as
this is a single-maintainer project.

## License

By submitting a pull request, you agree that your contribution will be
licensed under the [Apache License, Version 2.0][apache-2.0] — the same
license as this project.

You do not lose the rights to your contribution by submitting it; the
Apache-2.0 license grants the project (and downstream users) the same
rights as everyone else has to use, modify, and distribute your work.

## Developer Certificate of Origin (DCO)

All commits must be signed off, attesting to the [Developer Certificate of
Origin][dco]:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use `git commit -s` (or `git commit --signoff`) to add this line
automatically. This is a lightweight alternative to a full Contributor
License Agreement and serves the same provenance function.

If you forget to sign off, `git commit --amend --signoff` (or, for many
commits, `git rebase --signoff HEAD~N`) can fix it before pushing.

## Dev environment

Cerebra runs standalone against SQLite alone. To exercise the cognitive
cycle runtime, HTTP daemon, and event-stream inspector, install with the
`fossic` extra:

```bash
uv sync --extra dev --extra fossic
make test-quick       # fast tests; skips integration
make verify-docs      # confirms doc index entries exist
```

For the full test suite (including integration tests that load ~1.5 GB of
ML models): `make test`.

## How to contribute

1. Fork the repository.
2. Create a branch from `main`.
3. Make your change. Add or update tests for changed behavior.
4. Run the local checks before pushing:
   ```bash
   ruff check cerebra tests
   black --check cerebra tests
   mypy cerebra
   pytest -m "not integration"
   ```
5. Sign off your commits (`git commit -s`).
6. Open a pull request. Describe *why* the change is needed, not just what
   it does.

Small, focused changes are easier to review. If you're planning a large
change, please open an issue first to discuss the approach.

## Coding standards

- Type hints are required; `mypy --strict` runs in CI.
- Tooling versions are pinned exactly (`ruff==0.4.8`, `black==24.4.2`,
  `mypy==1.10.0`) — do not use different versions locally. See
  `docs/TECH_DEBT.md` TD-DEP-001 for the tool bump cadence.
- Inspector events are load-bearing — every cognitive action should emit
  a matching event when fossic is available.
- Provenance is non-negotiable for memory records. Every record needs a
  valid content-addressed source lineage.
- Keep pull requests focused on a single concern. Break larger changes
  into a sequence of commits or PRs.

## Status

Active development. Cerebra is functional end-to-end and tested against
real Ollama, but this is alpha software with known limitations. APIs may
change without notice between minor versions. See
[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) and
[`docs/TECH_DEBT.md`](docs/TECH_DEBT.md) for what's tracked.

[apache-2.0]: https://www.apache.org/licenses/LICENSE-2.0
[dco]: https://developercertificate.org/
