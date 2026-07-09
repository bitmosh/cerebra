# TECH_DEBT.md

Tracked technical debt and deferred work. New items landed at the bottom; resolved items removed. If you find something not on this list, either open an issue or add it here.

---

## Active items

### TD-DEP-001 — Development tool pin cadence

**Status:** open · **Priority:** medium · **Effort:** ~2-4 hours

The `[project.optional-dependencies]` `dev` extra pins exact versions of ruff, black, and mypy to preserve reproducibility across CI runs:

```
ruff==0.4.8
black==24.4.2
mypy==1.10.0
```

These were current when Cerebra shipped v0.4.5. Current stable is significantly newer (ruff 0.15+, black 26+, mypy 2.2+). The pins should be reviewed and bumped periodically (target: within 3 months of each major project cycle).

Bumping requires methodical work — the prior sweep against mypy 1.20 vs 1.10 surfaced 51 mypy errors that were pre-existing debt in older tools too but only fired at the newer patch level. Loose pins (`>=X`) don't preserve reproducibility across CI drift, so exact pins stay for now.

**Path to resolution:**
1. Update pins in `pyproject.toml` and `.pre-commit-config.yaml` in lockstep.
2. Run ruff, black, mypy against the full tree.
3. Fix categorized violation waves.
4. Land as a single "tool modernization" commit.

### TD-CODE-001 — Dead-code SKU sibling routing in `dedup_siblings`

**Status:** open · **Priority:** medium · **Effort:** ~2-4 hours · **Filed:** issue #2

In `cerebra/retrieval/lattice_dedup.py`, `sku_address.split("::")` uses `::` as the separator. But `SKUAddress.to_hex_string()` produces addresses separated by `.` — so the split never matches, and the SKU-based sibling matching in `dedup_siblings` has always been dead code regardless of type.

The fix is scoped but non-trivial: the split has to be corrected to `.`, AND we need a test that verifies SKU-based sibling matching works against realistic addresses. If nobody's noticed this being broken, downstream code paths may have adapted to its absence — the fix should verify the behavior is genuinely desired before shipping.

**Path to resolution:**
1. Read `cerebra/retrieval/lattice_dedup.py` and understand what dedup_siblings intends to do.
2. Determine the correct split (SKUAddress format is `SSSS.OODD.LC` per the phase-2 spec).
3. Add a unit test that would have caught the bug.
4. Ship the fix; close issue #2.

### TD-EVENT-001 — Purge workflow audit path

**Status:** open · **Priority:** low · **Trigger:** any purge workflow implementation

The `_fossic/system` stream is designed to hold system-level events including purge audit records. Currently no purge workflow exists, so the stream is unpopulated. When a purge workflow is implemented, its events go to this stream and downstream consumers (Lattica) can render them.

### TD-EVAL-001 — LoRA training for signal evaluators

**Status:** open · **Priority:** low · **Trigger:** corpus imbalance addressed + instruct distillation prepared

Six epistemic signal evaluators currently use prompt-only Granite 4.1 3B Instruct. LoRA-tuning against a curated corpus would likely improve signal precision but requires balanced training data (which we don't have yet) and an instruct distillation pipeline (which is not scoped).

### TD-PRIMITIVES-001 — Lattica primitives PyPI extraction

**Status:** open · **Priority:** low · **Trigger:** 2+ stable consumers + 90-day stability criterion

The `_primitives/` directory contains vendored shared primitives (Clutch, Triangulator, Trajectory, HysteresisModeRouter, ScoreComposer, TombstoneSet, BanditSelector). Currently duplicated across projects that use them. Consolidation to a separate PyPI package is deferred until at least 2 consumer projects are stable and 90 days of API stability has been demonstrated.

### TD-SAFETY-001 — Constitutional pre-action rule shape

**Status:** open · **Priority:** low · **Trigger:** first real pre-action safety case

`forbids()` on constitutional rules currently always returns False (v0.1 ships with no rules that actually forbid). The API surface is complete; specific rule content will be authored when a real safety case emerges. Until then, this is scaffolding.

### TD-HITL-001 — HITL review flow

**Status:** open · **Priority:** low · **Trigger:** v0.2 HITL design

The `requires_review` field on memory records is unpopulated. Human-in-the-loop review flow is scoped for v0.2 and requires design work on how review requests surface, how reviewers see them, and how decisions propagate back into the runtime.

### TD-TEST-001 — Click `mix_stderr=False` compat

**Status:** open · **Priority:** low · **Effort:** ~30 minutes · **Trigger:** next Click version upgrade

39 tests across 3 test files use `mix_stderr=False`, which was removed in newer Click versions. Tests pass on the currently-pinned Click, but any upgrade will surface these. Fix is mechanical: remove the deprecated argument.

### TD-TEST-002 — `test_lattice_against_vault.py` vault-disk failure

**Status:** open · **Priority:** low · **Trigger:** adjacent vault test infrastructure changes

A specific integration test fails against a vault-on-disk fixture; root cause is uninvestigated. The test is skipped in CI. Fix requires understanding whether the fixture is stale, the test is stale, or the code path exercised is genuinely broken.

### TD-FOSSIC-001 — Explicit error messages for fossic-requiring commands

**Status:** open · **Priority:** medium · **Effort:** ~1-2 hours

`cerebra run-cycle` and `cerebra serve` currently import `FossicStore` at CLI-command execution time. When fossic isn't installed, the user sees a bare `ModuleNotFoundError: No module named 'fossic'` rather than an actionable message.

**Path to resolution:** Add a try/except around each fossic-requiring command's setup that catches `ImportError` and prints a clear message ("This command requires fossic. Install with `pip install cerebra[fossic]`"). Small code change, real UX improvement.

---

## Cadence

This document is reviewed once per version release. Items resolved get removed; items whose triggers fire get promoted; new debt discovered during development lands here.
