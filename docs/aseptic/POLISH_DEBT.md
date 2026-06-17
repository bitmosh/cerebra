---
title: Cerebra Polish Debt — Living Report
last_reviewed: v0.3.5a (Phase 8 close)
---

# Cerebra Polish Debt — Living Report

Correct but feels-wrong. Mechanical to fix; no design discussion required. Naming inconsistencies, doc gaps, test helper duplication, file organization that grew organically.

The key test: *"is this correct, and is it also slightly wrong in a way that will confuse someone?"*

See `docs/aseptic/LIVING_REPORTS.md` (when scrubbed for Cerebra) for entry format conventions.

---

## Open entries

### PD-001 — `render_template` uses regex variable substitution

**What it is:** CycleRuntime's `render_template` helper uses simple regex-based variable substitution rather than Jinja2 (Phase 8 Step 2 D2 deviation).

**Where:** `cerebra/cognition/cycle_runtime.py` (or wherever render_template lives), CycleRuntime._render_prompt_template.

**Fix:** Migrate to Jinja2. ~30 minutes of code change + 1 dependency added (`jinja2 = "^3.1"`). Tests updated to verify template rendering with conditionals/loops if cycle configs need them.

**Trigger:** When cycle configs need conditionals, loops, or filters (post-v0.1 sophisticated cycle configs).

---

### PD-002 — `ELEVATED_SALIENCE = 0.8` is a guess

**What it is:** Phase 8 v0.3.5a added `ELEVATED_SALIENCE = 0.8` constant for salience boosting cited records. The value is a guess relative to Phase 5's default salience (probably 0.5 but not verified).

**Where:** `cerebra/cognition/_constants.py`, ELEVATED_SALIENCE constant.

**Fix:** Verify Phase 5's default salience value. Adjust `ELEVATED_SALIENCE` so the boost is measurably elevated but not equivalent to pinning. Add a test that demonstrates the boost differential.

**Trigger:** Phase 9 work touches salience, OR observed cited-record behavior doesn't match expectations (citations don't surface in subsequent retrievals despite being cited).

---

### PD-003 — Methodology lessons not formally captured

**What it is:** Phase 8 surfaced three reusable methodology patterns: audit-before-implementing, vocabulary-spec-wins-over-kickoff, ship-unblocked-defer-blocked-with-letter-suffix. These are mentioned in Phase 8 close artifacts but not consolidated into a permanent methodology reference.

**Where:** Currently scattered in `docs/agent/phase8_close.md` and various deviation log entries.

**Fix:** Consolidate into a single `docs/agent/cerebra_methodology.md` (or extend an existing methodology doc) that captures patterns observed during v0.1 implementation. Becomes the seed for Cerebra-side Aseptic adoption when timing is right.

**Trigger:** Aseptic full adoption begins (post-v0.1), OR the patterns become numerous enough that scattered notes lose legibility.

---

### PD-004 — Per-version deviation logs scattered

**What it is:** Cerebra uses per-version deviation log files (`docs/agent/deviations/v0.3.0.md`, `v0.3.2.md`, `v0.3.3.md`, `v0.3.5.md`, `v0.3.5a.md`). Aseptic convention is a single accumulating DEVIATION.md. Cerebra's pattern preserves per-pass context but loses "all open deviations at a glance."

**Where:** `docs/agent/deviations/` directory.

**Fix:** Either (a) migrate to single accumulating DEVIATION.md with original entries preserved, or (b) add a `DEVIATION_OPEN.md` index that lists open deviations across all version files. Option (b) is cheaper.

**Trigger:** Open deviation count across versions exceeds ~20, OR bandit starts missing relevant deviations because they're in older version files.

---

### PD-005 — `runtime_sessions` vs `sessions` naming pattern not documented

**What it is:** Phase 8 Step 1 named the new sessions table `runtime_sessions` to avoid collision with Phase 5's existing `sessions` table (working memory sessions). Per DEV-013, this is correct but the naming distinction isn't documented anywhere outside the deviation log.

**Where:** No central doc explains the two-sessions-table architecture.

**Fix:** Add a brief subsection to `CEREBRA_ARCHITECTURE.md` or `CEREBRA_STATE_GOVERNANCE.md` explaining: `runtime_sessions` tracks cycle execution sessions; `sessions` tracks working memory sessions. Both are valid; they track different things.

**Trigger:** First time someone outside the immediate context (future bandit, new Claude, external contributor) gets confused about which sessions table to use.

---

### PD-006 — Citation parsing format not documented in cycle configs

**What it is:** simple.planning.v0 prompt templates don't tell the LLM what citation format to use. The regex parser (PD-001's regex) looks for a specific pattern. If the LLM doesn't happen to use that pattern, citations don't extract.

**Where:** `cycles/simple.planning.v0.yaml` prompt templates.

**Fix:** Add a small "Citation format" note to relevant prompt templates: "When referencing prior context records, use the format [#record_id]. Citations in this format will be tracked and reinforced."

**Trigger:** Observed citation extraction rate is low in real-world simple.planning.v0 runs.

---

### PD-008 — docs/aseptic/README.md is fossic-framed

**What it is:** `docs/aseptic/README.md` was seeded from the fossic-side Aseptic adoption docs and remains fossic-framed. It references fossic-specific conventions and workflow context that doesn't map cleanly to Cerebra. A Cerebra-specific version listing FUTURE_DIRECTIONS.md and Cerebra's own Aseptic discipline entry points would be clearer for future bandit sessions working from this repo.

**Where:** `docs/aseptic/README.md`

**Fix:** Write a Cerebra-specific `docs/aseptic/README.md` covering: what Aseptic is in the context of Cerebra, the TECH_DEBT.md / POLISH_DEBT.md living reports, cross-pollination convention (`docs/aseptic/cross-pollination/`), and links to FUTURE_DIRECTIONS.md if/when that doc exists.

**Trigger:** Next time a bandit session opens docs/aseptic/ and gets confused by fossic framing, OR Aseptic full adoption is formalized for Cerebra (PD-003 trigger).

---

### PD-007 — Phase 8 close doc has placeholder sections

**What it is:** `docs/agent/phase8_close.md` may have <list the DEV entries> or similar placeholder text that wasn't filled in during initial creation.

**Where:** `docs/agent/phase8_close.md`.

**Fix:** Read through the doc, fill in any placeholder sections with actual content (DEV entry list, test count progression numbers, etc.).

**Trigger:** Next time someone reads the doc and notices placeholders.

---

## Resolved entries

(none yet — Phase 8 close is the first formal review)

---

*Last reviewed at v0.3.5a (Phase 8 close). Next review: Phase 9 kickoff, or supervisor pass when triggered.*
