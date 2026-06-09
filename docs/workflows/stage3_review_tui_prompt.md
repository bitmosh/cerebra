# Stage 3 Review TUI — Build Specification

Build a terminal user interface for the user to manually review 583 records produced by Stage 2 of the v0.2 LoRA curation pipeline. Each record needs a verdict (KEEP / RELABEL / MARK_AMBIGUOUS / DROP) with optional notes.

The interface is the bottleneck for getting through 583 records efficiently. Build it for speed and zero-loss save state.

## Reference materials

Read first for context:
- `docs/projects/v0.2_lora_classifier/PLANNING.md` — overall plan
- `scripts/v02_training/output/stage2_consensus.jsonl` — input file format (each line is a record with v0.1.0 label, 3 model votes, consensus tag)
- `scripts/v02_training/output/stage1_analysis.json` — distribution stats for context

## What to build

A single Python file: `scripts/v02_training/stage3_review.py`

Uses the `textual` framework for TUI rendering. Add `textual` to `requirements.txt` or install in working environment.

The interface displays one record at a time with all relevant context, captures a verdict via keyboard shortcuts, optionally captures notes, and writes the verdict to the output file immediately before advancing to the next record.

## Input format

Each line of `stage2_consensus.jsonl` is a JSON object like:

```json
{
  "record_id": "abc123",
  "chunk_content": "The leeway network inverts prohibition models...",
  "v01_label": "MECHANISM",
  "v01_confidence": 0.78,
  "stage2_votes": {
    "qwen3.5:latest": "DESIGN",
    "llama3.1:8b": "MECHANISM",
    "ibm/granite4:micro": "DESIGN"
  },
  "agreement_count": 1,
  "consensus_tag": "contested"
}
```

(Verify the actual field names by reading the file. If the script that wrote it used different names, match those.)

## Output format

Each verdict written to `scripts/v02_training/output/stage3_curated.jsonl` as a new line:

```json
{
  "record_id": "abc123",
  "verdict": "KEEP" | "RELABEL" | "MARK_AMBIGUOUS" | "DROP",
  "final_label": "MECHANISM",
  "ambiguous_with": null,
  "notes": "",
  "reviewed_at": "2026-06-08T22:15:00Z",
  "v01_label_was": "MECHANISM",
  "stage2_votes_were": {...}
}
```

Field semantics:
- `verdict` — one of the four verdicts
- `final_label` — the category that should be used for training (= v01_label if KEEP, the new label if RELABEL, the v01_label if MARK_AMBIGUOUS, null if DROP)
- `ambiguous_with` — list of categories also considered defensible, only populated for MARK_AMBIGUOUS verdicts
- `notes` — user free text, optional
- `reviewed_at` — ISO timestamp when verdict was recorded
- `v01_label_was` / `stage2_votes_were` — preserved for audit trail

Write per-record immediately. No batch save. Crash or quit = zero work lost.

## Display layout

Single-screen layout, no scrolling. All info visible at once:

```
┌──────────────────────────────────────────────────────────────────┐
│ Stage 3 Review · Record 127/583 (21.8%) · Session: 47 reviewed   │
│ Filter: all  Sort: original  Avg time/record: 18s                │
├──────────────────────────────────────────────────────────────────┤
│ Chunk content:                                                   │
│                                                                  │
│ The leeway network inverts prohibition models. Instead of        │
│ specifying what is forbidden, it specifies what is permitted     │
│ under what conditions. Everything outside the network is         │
│ implicitly disallowed.                                           │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│ v0.1.0 label:    MECHANISM       (confidence: 0.78)              │
│                                                                  │
│ Stage 2 votes:                                                   │
│   [1] Qwen 3.5 9B          → DESIGN                              │
│   [2] Llama 3.1 8B         → MECHANISM                           │
│   [3] Granite 4.0 Micro    → DESIGN                              │
│                                                                  │
│ Consensus:       contested (1/3 agree with v0.1.0)               │
├──────────────────────────────────────────────────────────────────┤
│ Verdict:                                                         │
│   [K]eep    [R]elabel    [A]mbiguous    [D]rop                   │
│                                                                  │
│ Navigation:                                                      │
│   [←/→] Prev/Next   [J]ump   [F]ilter   [S]ort   [N]otes         │
│   [Q]uit (saves and exits)                                       │
└──────────────────────────────────────────────────────────────────┘
```

Use color/highlight for:
- Consensus tag (green = consensus, yellow = contested)
- Stage 2 votes that match v0.1.0 label (highlighted)
- Stage 2 votes that disagree (different highlight)
- v0.1.0 confidence (color-coded: green ≥0.8, yellow 0.6-0.8, red <0.6)

## Keyboard interactions

### Primary verdicts (single keypress, no confirmation)

`K` — verdict = KEEP, final_label = v01_label, write record, advance
`D` — verdict = DROP, final_label = null, write record, advance

### Relabel flow

`R` — opens relabel sub-prompt:

```
┌──────────────────────────────────────────────────────────────────┐
│ Relabel to:                                                      │
│   [1] DESIGN      (Qwen vote)                                    │
│   [2] MECHANISM   (Llama vote — same as v0.1.0)                  │
│   [3] DESIGN      (Granite vote)                                 │
│   [O] Other → opens full 16-category picker                      │
│   [ESC] Cancel                                                   │
└──────────────────────────────────────────────────────────────────┘
```

If user presses 1/2/3: relabel to that vote category.
If user presses O: open full picker.

Full picker shows all 16 categories with hotkey assignments:

```
┌──────────────────────────────────────────────────────────────────┐
│ Pick category (hotkey or arrow keys + Enter):                    │
│                                                                  │
│   D1: DESIGN          M1: MECHANISM      T1: TECHNIQUE           │
│   T2: TOOL            P1: PRINCIPLE      C1: CONSTRAINT          │
│   J1: JUDGMENT        G1: GOAL           O1: OBSERVATION         │
│   P2: PHENOMENON      P3: PATTERN        E1: EVENT               │
│   R1: RELATION        C2: CONTEXT        C3: CREATION            │
│   A1: AGENT                                                      │
│                                                                  │
│   [ESC] Cancel                                                   │
└──────────────────────────────────────────────────────────────────┘
```

If two-letter hotkeys feel clunky, use arrow-key navigation + Enter as fallback. Either works.

After category selected: verdict = RELABEL, final_label = picked category, write record, advance.

### Ambiguous flow

`A` — opens ambiguous sub-prompt. Two-step:

Step 1: confirm primary label (default = v01_label, allow change):

```
Primary label:
  [Enter] Keep MECHANISM as primary
  [C]hange primary → opens category picker
```

Step 2: select ambiguous_with (1-3 alternatives):

```
Also defensible (select 1-3, [Enter] when done):
  [1] DESIGN     (Qwen vote)        [✓] selected
  [2] MECHANISM  (Llama vote)
  [3] DESIGN     (Granite vote)     [✓] selected
  [O] Other → category picker
  [Enter] Done
```

If user picks 1 then Enter: ambiguous_with = ["DESIGN"]
If user picks 1 then 3 then Enter: ambiguous_with = ["DESIGN"] (deduplicated)
If user picks 2 then Enter: ambiguous_with = ["MECHANISM"]

After done: verdict = MARK_AMBIGUOUS, final_label = primary, ambiguous_with = list, write record, advance.

### Notes capture (optional)

`N` — opens notes input field. User types free text (1-3 lines typical). Enter to save, ESC to cancel. Notes attach to the CURRENT record's verdict when written.

If notes entered BEFORE a verdict is pressed: notes are held in buffer, attached when verdict is recorded.

If notes pressed AFTER a verdict already recorded: open the previously-written record, update its notes, save.

Important: notes are always optional. Most records will have empty notes. Don't prompt for notes per record — only when user explicitly presses N.

### Navigation

`→` or `Space` — advance to next record (skip without verdict)
`←` — return to previous record (allows revising verdict)
`J` — jump to specific record ID (input field for record_id)
`Q` — quit (saves and exits cleanly)

### Filter mode

`F` — opens filter menu:

```
Filter mode:
  [1] All records (default)
  [2] Consensus only (~205 records)
  [3] Contested only (~378 records)
  [4] By D1 category
  [5] By confidence range
  [6] Unanimous against v0.1.0 (strongest disagreement)
  [7] Unreviewed only
  [ESC] Cancel
```

Option 4 prompts for category. Option 5 prompts for confidence range. Other options apply immediately.

Filter state persists across records until changed. Show current filter in header.

### Sort mode

`S` — opens sort menu:

```
Sort mode:
  [A] Original order (default)
  [B] Confidence ascending (hardest first)
  [C] Confidence descending (easiest first)
  [D] By D1 category
  [ESC] Cancel
```

Sort applies to filtered records. Show current sort in header.

## Resume behavior

On launch:
1. Read `stage3_curated.jsonl` if it exists
2. Build set of already-reviewed record_ids
3. Filter input records to exclude already-reviewed (unless user wants to revise)
4. Position cursor at first unreviewed record (or first record if filter changes that)
5. Session stats: start counting from launch

If user reviewed 200 records last session and quits, relaunching skips to record 201. The 200 reviewed records are visible only if user explicitly filters for "All" or uses `←` Prev navigation.

## Calibration mode flag

Optional CLI flag for the joint calibration session:

```bash
python scripts/v02_training/stage3_review.py --calibration
```

In calibration mode:
- Shows the first 20 records regardless of resume state
- Records verdicts to `stage3_calibration.jsonl` (separate file, not stage3_curated.jsonl)
- After 20 records, exits with summary
- Does not affect main review state

This lets user + reviewer go through 20 records together to calibrate verdict criteria before the solo review begins. The calibration verdicts don't pollute the real curation output.

## Session stats display

In the header bar:

```
Stage 3 Review · Record N/583 (X%) · Session: K reviewed
Filter: {filter_name}  Sort: {sort_name}  Avg time/record: {avg}s
```

Track per session:
- Number of records reviewed this session
- Time per record (running average, exclude calibration-mode time)
- Verdict distribution this session (K reviewed, breakdown by verdict type)

Display these on quit:

```
Session summary:
  Records reviewed: 47
  Time elapsed: 14m 32s
  Average per record: 18.5 seconds
  
  Verdict breakdown:
    KEEP:           28  (60%)
    RELABEL:         8  (17%)
    MARK_AMBIGUOUS:  9  (19%)
    DROP:            2   (4%)
  
  Records with notes: 6
  
  Total progress: 173/583 (29.7%) — 410 records remaining
```

## Error handling

- If input file missing: error message, exit cleanly
- If output file write fails: error message, do NOT advance, give user opportunity to retry
- If user interrupts mid-action: cleanly cancel, no partial write
- If record_id appears twice in output (shouldn't happen, but defensive): use the most recent entry as the active verdict

## Don't list

- Do NOT auto-advance after verdict without recording it
- Do NOT batch writes (must write per-record)
- Do NOT modify the input file
- Do NOT require notes for any verdict (always optional)
- Do NOT confirm verdicts (single keypress is the confirmation; user can press ← to revise)
- Do NOT use Tab navigation in the relabel picker (hotkeys only or arrow + Enter)
- Do NOT add reviewer attribution fields (single-reviewer system, doesn't need them)

## STOP gate

After basic structure works (display layout + KEEP/DROP verdicts + save state + resume), pause and report. The user will verify:
- Layout renders correctly
- KEEP and DROP work and write properly
- Resuming after quit picks up where it left off
- Counter increments correctly

Then proceed to RELABEL flow, AMBIGUOUS flow, filters/sort, notes, calibration mode.

## Total scope estimate

- Basic structure + display + KEEP/DROP + save/resume: ~1 hour
- RELABEL flow + category picker: ~30 minutes
- AMBIGUOUS flow + sub-prompts: ~30 minutes
- Filter and sort modes: ~30 minutes
- Notes capture: ~15 minutes
- Calibration mode flag: ~15 minutes
- Polish + testing: ~30 minutes

Total: ~3-4 hours autonomous work with 1 STOP gate.

## Design philosophy notes

A few principles worth preserving as you build:

**Speed over polish.** The user will spend 4-8 hours in this interface. Every unnecessary keystroke compounds. Prefer single-key verdicts over confirmation dialogs.

**Zero work lost.** Per-record writes, not batch. Crash recovery should always work. If implementing crash recovery feels complex, simplify the data model rather than skip the safety property.

**Defensive on ambiguity.** When the user's input is unclear (e.g., partial keystroke), don't guess — show what they pressed and wait for confirmation.

**Preserve audit trail.** The output JSONL records v01_label_was and stage2_votes_were even though they're redundant with the input. This lets the output stand alone as a complete audit record without requiring cross-reference to the input.

**Notes are observations, not justifications.** The notes field captures user observations about the chunk for v0.3 D2/D3 work. It's NOT a place to justify verdicts. Don't prompt for "why?" — just provide the field if user has an observation to record.

## After completion

The user will:
1. Run with `--calibration` flag, do 15-20 records together with reviewer
2. Adjust verdict criteria if needed based on calibration discussion
3. Run normal mode, work through 583 records across multiple sessions
4. When done, `stage3_curated.jsonl` becomes input to `build_training_corpus.py`

No further interface work is expected after this. The build_training_corpus.py script is already written; it expects the JSONL output format specified above.
