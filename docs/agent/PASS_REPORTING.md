# PASS COMPLETE Template Update for Bandit

*Drop-in additions to bandit's existing PASS COMPLETE format. These are structural safeguards from Aseptic methodology — catches missing-from-git failure mode + produces living-report data.*

---

## Two additions to the existing PASS COMPLETE structure

### Addition 1 — Files inventory section

After the existing `Highlights:` section and before `Learnings:`, add:

```
Files (added to repo):
  · path/to/new_file.py — purpose (one clause)
  · path/to/another.py — purpose

Files (modified in repo):
  · path/to/changed.py — what changed

Files (NOT added to repo, intentionally):
  · path/to/scratch.py — reason (e.g., experimental, deferred to next pass)
```

If no files added/modified/intentionally-excluded: explicit "None" entries required for each subsection.

**Why this catches a real failure mode:** Phase 7 shipped tests that weren't committed to git. The PASS COMPLETE reported test counts, but the test artifacts were untracked. The failure was invisible until bandit's Phase 8 audit caught it. Explicit files inventory at PASS COMPLETE time surfaces this category of drift immediately — bandit must list what was added; missing entries surface as obvious gaps.

### Addition 2 — Living report updates section

After the `Files` sections and before `Commit:`, add:

```
Living report updates:
  · TECH_DEBT: TD-NNN (new) — short title
  · POLISH_DEBT: PD-NNN (new) — short title
  · FUTURE_DIRECTIONS: FD-NNN (new) — short title
  · [any]: [ID] resolved (commit reference)
  
  -- OR explicit empty confirmation:
  · No new TECH_DEBT entries this pass. No POLISH_DEBT entries. No FUTURE_DIRECTIONS. No entries resolved.
```

**Why the empty confirmation is mandatory:** An agent that didn't notice anything looks identical to one that didn't check, unless absence is made explicit. The "no new entries this pass" confirmation prevents empty-report-by-omission.

---

## Updated full PASS COMPLETE template

```
── PASS COMPLETE · v<version> · <YYYY-MM-DD> ──
Title: <title>
Summary: <summary>
Project: cerebra

Highlights:
  · <highlight 1>
  · <highlight 2>
  · <highlight 3>

Files (added to repo):
  · <new file path> — <purpose>
  -- OR "None"

Files (modified in repo):
  · <changed file path> — <what changed>
  -- OR "None"

Files (NOT added to repo, intentionally):
  · <intentionally-excluded path> — <reason>
  -- OR "None"

Living report updates:
  · <entry change> 
  -- OR "No new TECH_DEBT entries this pass. No POLISH_DEBT entries. No FUTURE_DIRECTIONS. No entries resolved."

Learnings:
  · <learning 1>
  · <learning 2>

Commit: <sha7>
Tests: <N passed · M failed · K skipped>
Branch: <clean|name>
```

---

## Char count consideration

The existing PASS COMPLETE format hits ~1400-1500 chars for typical passes (well under the 1800 limit). The two additions probably add 100-200 chars depending on entry counts. Should still fit under 1800.

If a pass has many living report updates or many file changes, the PASS COMPLETE may approach the limit. Bandit verifies `len() <= 1800` before posting (existing discipline).

For passes that produce a lot of changes (rare), bandit can compress by:
- Grouping related files ("multiple test files in tests/cognition/" rather than listing each)
- Summarizing living report updates ("3 new TD entries, see DEVIATION.md")

Compression should be the exception, not the default. Most passes have small enough change surface for explicit lists.

---

## How bandit uses this in practice

At MERGE GATE time, bandit:

1. Drafts the PASS COMPLETE with all sections filled in (including the new Files and Living report updates sections)
2. Runs `len(pass_complete_text) <= 1800` check
3. Posts to `#approve-this` for MERGE GATE approval
4. After approval, commits + posts verbatim to `#changelog` + `bumper bump --dry`

If bandit forgets one of the new sections, the PASS COMPLETE is incomplete. Reviewer (Cerebra Claude) catches it during MERGE GATE review and requests the missing section before approval.

---

## Living report seed files

Bandit reads (and may update) these files at pass start:

- `docs/aseptic/TECH_DEBT.md` — Open tech debt entries with trigger conditions
- `docs/aseptic/POLISH_DEBT.md` — Open polish debt entries
- `docs/aseptic/FUTURE_DIRECTIONS.md` — Concept-stage architectural directions (FD- prefix)

When bandit:
- Discovers new tech debt during a pass: add entry to TECH_DEBT.md, note in PASS COMPLETE Living report updates
- Discovers new polish debt: add entry to POLISH_DEBT.md, note in PASS COMPLETE
- Resolves an existing entry: mark resolved in the file (strikethrough + resolved block per LIVING_REPORTS.md convention), note in PASS COMPLETE

---

## What this is NOT

- Not a full Aseptic blast-radius file (those are separate per-pass artifacts, more detailed than this)
- Not a structured JSON output (markdown is the format for v0.1)
- Not enforced by tooling (discipline is human-and-agent-driven)

The additions are minimal-cost extensions to existing methodology. ~30 seconds of additional work per pass for bandit. Real value from structural safeguards.

---

## When to revisit

If this discipline is working at Phase 11 close (v0.1 milestone), consider:

- Expanding to full Aseptic blast-radius file per pass
- Formalizing supervisor pass between phases
- Adding DEVIATION.md as accumulating file (or DEVIATION_OPEN.md index)
- Producing CROSS_POLLINATION/pass-NN.md when Cerebra changes affect LumaWeave/fossic

If the discipline is producing friction (bandit forgetting sections, MERGE GATE reviews getting noisy), simplify back to the minimum that catches the highest-value failure mode (probably just the Files inventory).
