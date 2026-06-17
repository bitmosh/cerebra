# Canonical PASS COMPLETE Template

**This is load-bearing for bumper parsing AND Aseptic discipline. Use verbatim.**
**Reference for inclusion in every Cerebra kickoff prompt.**

---

## The template

```
── PASS COMPLETE · vX.Y.Z · YYYY-MM-DD ──
Title: <Pass title — e.g., "Phase 9 Step 3 — CatalystEngine consumer">
Summary: <1-3 sentence summary of what shipped>
Project: cerebra
Highlights:
  · <bullet>
  · <bullet>
  · <bullet>
Files (added to repo):
  · <path>
  · <path>
Files (modified in repo):
  · <path>
  · <path>
Files (NOT added to repo, intentionally):
  · <path or "None">
Living report updates:
  · <new entry or "No new TECH_DEBT entries. No POLISH_DEBT. No FUTURE_DIRECTIONS. No entries resolved.">
Learnings:
  · <bullet>
  · <bullet>
Commit: <sha7>
Tests: <N passed · M failed · K skipped>
Branch: <clean|name>
```

---

## What MUST match exactly (load-bearing)

These elements are parsed by bumper or required by Aseptic. Deviation breaks tooling:

1. **Opening delimiter:** `── PASS COMPLETE · vX.Y.Z · YYYY-MM-DD ──`
   - The `── PASS COMPLETE ·` substring IS the bumper trigger
   - The em-dashes (`──`) are U+2500 (not double hyphens `--`)
   - The middle dots (`·`) are U+00B7 (not periods `.`)
   - Version format: `vX.Y.Z` (with leading `v`)
   - Date format: `YYYY-MM-DD` (ISO 8601)

2. **Field names:** `Title:`, `Summary:`, `Project: cerebra`, `Highlights:`, `Files (added to repo):`, `Files (modified in repo):`, `Files (NOT added to repo, intentionally):`, `Living report updates:`, `Learnings:`, `Commit:`, `Tests:`, `Branch:`
   - Exact capitalization
   - Trailing colon
   - No alternative phrasings (e.g., NOT "What shipped:", "New files:", "Changes:")

3. **Bullet prefix:** `  · ` (two spaces, then middle dot U+00B7, then one space)
   - Not `- ` (hyphen + space)
   - Not `* ` (asterisk + space)
   - Not `• ` (different bullet character)

4. **Commit line position:** Last field before Tests/Branch. The `Commit:` line is the load-bearing trim point — bumper trims excess from above the Commit line if message exceeds 1800 chars.

5. **Tests line format:** `Tests: <N> passed · <M> failed · <K> skipped`
   - Use the middle dot `·` between counts (not commas, not slashes)
   - Order: passed, failed, skipped

6. **Hard char limit:** ≤1800 chars total
   - Discord limit is 2000; we use 200-char safety margin
   - Splitting across multiple messages BREAKS bumper parsing
   - If content exceeds, trim Learnings or Highlights bullets — never trim field structure

---

## What's flexible (formatting)

These elements have format flexibility but should follow precedent for readability:

- Highlights bullet count: typically 3-6
- Learnings bullet count: typically 2-4
- Files lists: include all files; "None" is valid if empty
- Living report updates: "No new entries this pass" is valid for clean passes

---

## Example (Phase 9 Step 2, as actually shipped)

```
── PASS COMPLETE · v0.3.6 · 2026-06-13 ──
Title: Phase 9 Step 2 — Bandit primitive implementation
Summary: Bandit Selector at cerebra/_primitives/bandit.py per LATTICA_PRIMITIVES.md §11. UCB arm selection, per-arm reward tracking, deterministic-when-seeded, serialization helpers. Seventh vendored primitive; Step 3 CatalystEngine consumes via get_stats.
Project: cerebra
Highlights:
  · bandit.py — Bandit, ArmStats, BanditSelection per §11 spec verbatim
  · 21 tests (19 from §11 requirements + 2 edge cases), all passing
  · Re-exported through cerebra._primitives and cerebra.cognition
  · Injected RNG for determinism (stored; unused in v0.1 — first-wins ties are deterministic without it)
  · to_state / from_state for consumer-defined persistence
Files (added to repo):
  · cerebra/_primitives/bandit.py
  · tests/unit/test_bandit.py — 21 tests
Files (modified in repo):
  · cerebra/_primitives/__init__.py — re-export Bandit, ArmStats, BanditSelection
  · cerebra/cognition/__init__.py — add to primitives re-export block and __all__
  · cerebra/_primitives/VENDORED_FROM.md — seventh primitive noted
  · docs/agent/deviations/v0.3.6.md — DEV-031 (structure audit) + DEV-032 (RNG stored, unused in v0.1)
Files (NOT added to repo, intentionally):
  · None
Living report updates:
  · No new TECH_DEBT entries. No POLISH_DEBT entries. No entries resolved.
  · _primitives_canonical/ still empty — noted in DEV-032; out of scope for Step 2.
Commit: a596fd0
Tests: 1667 passed · 40 failed · 4 skipped
Branch: clean
```

That's 1378 chars — well under 1800.

---

## Common deviations to AVOID

These are patterns implementing agents (bandit, Claude Code) sometimes drift into. Each breaks tooling or discipline:

### Drift 1: Replacing field structure with prose

WRONG:
```
── PASS COMPLETE · Phase 9 Step 3: CatalystEngine ──
What shipped: <prose>
New files: <list>
Modified: <list>
```

Why wrong: `What shipped:` isn't a canonical field. Missing `Title:`, `Summary:`, `Project:`. Missing `Living report updates:`. Bumper still parses the delimiter (catches `── PASS COMPLETE ·`) but downstream fields are scrambled.

RIGHT:
```
── PASS COMPLETE · v0.3.6 · 2026-06-13 ──
Title: Phase 9 Step 3 — CatalystEngine consumer
Summary: ...
Project: cerebra
Highlights: ...
Files (added to repo): ...
[etc per canonical template]
```

### Drift 2: Wrong bullet character

WRONG: `- bandit.py implementation`
WRONG: `* bandit.py implementation`
RIGHT: `  · bandit.py implementation`

Bullets must use the middle dot `·` (U+00B7).

### Drift 3: Skipping Aseptic sections

WRONG: PASS COMPLETE without `Living report updates:` section
Why: Aseptic discipline tracks what changed in TD/PD/FD via this section. Missing it = audit gap.

RIGHT: Always include `Living report updates:` — even if just "No new entries this pass."

### Drift 4: Version label format

WRONG: `── PASS COMPLETE · 0.3.6 · 2026-06-13 ──` (missing `v`)
WRONG: `── PASS COMPLETE · v0.3.6 ──` (missing date)
WRONG: `── PASS COMPLETE · Phase 9 Step 3 · 2026-06-13 ──` (phase name in place of version)
RIGHT: `── PASS COMPLETE · v0.3.6 · 2026-06-13 ──`

### Drift 5: Multi-message PASS COMPLETE

WRONG: Posting a long PASS COMPLETE across two Discord messages
Why: bumper buffer=1; only sees first message. Splitting breaks parsing.

RIGHT: Stay ≤1800 chars in one message. If approaching the limit, trim Learnings bullets first, then Highlights, never field structure.

---

## Self-check before posting

Before pasting to `#changelog`, verify:

```
[ ] Opening delimiter matches: `── PASS COMPLETE · vX.Y.Z · YYYY-MM-DD ──`
[ ] All 12 canonical field names present (Title, Summary, Project, Highlights, Files added, Files modified, Files NOT added, Living report updates, Learnings, Commit, Tests, Branch)
[ ] All bullets use `  · ` prefix (two spaces, middle dot, space)
[ ] Char count ≤1800 — verify with len() or similar
[ ] Single Discord message (no splitting)
[ ] Version label includes `v` prefix
[ ] Date in ISO 8601 (YYYY-MM-DD)
[ ] Tests line uses `·` separators
```

If ANY check fails, fix before posting. The format is a contract with bumper + Aseptic tooling.

---

## How this gets enforced

**In every Cerebra kickoff prompt going forward:** This template gets included verbatim in a "MANDATORY: PASS COMPLETE FORMAT" section. Cerebra Claude (kickoff drafter) puts it prominently — not buried in a "PASS COMPLETE template" subsection. The implementing agent sees the canonical format alongside their work specification.

**The implementing agent (bandit, Claude Code, etc.):** treats the template as a contract. Deviation requires explicit reason in deviation log (DEV-XXX entry explaining why canonical format couldn't be followed).
