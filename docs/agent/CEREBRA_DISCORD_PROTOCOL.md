# CEREBRA_DISCORD_PROTOCOL.md — Full Discord Coordination Protocol

## 1. Channel IDs

Verified via MCP on 2026-06-04. Use IDs, not names.

| Name | ID |
|------|-----|
| #approve-this | `1506441138612080680` |
| #current-task | `1506440945128701955` |
| #changelog | `1509728570367283250` |
| #notifications | `1506441052826107964` |
| #brainstorm | `1506441106869583932` |

If any ID changes, update this file and ask the developer to confirm.

## 2. Channel Purposes

**#current-task** — lifecycle tracking only.
- Brief BEGIN at pass start (phase name, goal).
- Brief END at pass finish (key results, modified files).
- Once per major pass, start and end only. Do not use for approval requests.

**#changelog** — PASS COMPLETE reports only.
- The bumper parses this channel. The `── PASS COMPLETE ·` delimiter is the trigger.
- Post directly here, not forwarded from #current-task.
- Malformed = broken/missing blog post.

**#approve-this** — approval gates.
- Post before: commit, push, merge, destructive git action, dependency install.
- Format: describe action + provide relevant context (diff summary, commit message, etc.).
- Recognized responses: `approve` / `yes` / `lgtm` / `go` (proceed) | `reject` / `no` / `stop` (halt) | `corrections` (apply, then re-confirm).

**#notifications** — detailed run updates.
- Test pass/fail counts, regression alerts, diagnostic findings, long-task status.
- Verbatim output for failures.

**#brainstorm** — high-ROI improvements only.
- Format: problem / proposed solution / estimated ROI / cost.
- Don't spam; reserve for substantive architectural questions.

## 3. Per-Pass Flow (Load-Bearing)

Every pass follows this exact sequence:

```
1. Confirm Discord MCP is connected — else HALT.
2. Post brief START to #current-task.
3. Work + verify, foreground.
4. Post brief END to #current-task.
5. MERGE GATE: post to #approve-this with the draft PASS COMPLETE text
   as a code block. Run len() on it first — must be ≤1800 chars.
   Wait for approval. Commit with explicit paths on approval.
6. Post the PASS COMPLETE verbatim to #changelog (exactly the text
   approved in step 5 — no changes). Single message only.
7. BUMP+PUSH GATE: run `bumper bump --dry` (no --msg; buffer=1 picks
   the previous message, so step 6 must be the most recent #changelog
   entry before the dry run). Post dry-run output to #approve-this.
   Wait for approval → run `bumper bump` live.
```

Do not skip steps. Do not combine steps. Each gate is a real pause.

**Between step 6 and step 7: do not post anything else to #changelog.**
Buffer=1 means bumper takes the second-most-recent message. The PASS COMPLETE
from step 6 must stay as the latest entry until the bump completes.

## 4. PASS COMPLETE Format (Load-Bearing)

The bumper parses this format. Every field is required. Do not reword delimiters or labels.

```
── PASS COMPLETE · <version> · <YYYY-MM-DD> ──────────────────

Title: <one-line human title>
Summary: <1-2 sentences, what changed and why — becomes the post description>

Project: cerebra

Highlights:
  · <what-changed bullet>
  · <...>

Learnings:
  · <insight / gotcha bullet>
  · <...>

Commit: <sha7 of the merge commit>

Tests: <N passed · M failed · K skipped>
Branch: <clean | branch name>
```

The `── PASS COMPLETE ·` delimiter is the bump trigger. Messages without it are ignored by the bumper.

### 1800-character hard budget (CRITICAL)

The PASS COMPLETE **must land in a single Discord message**. Discord's limit is 2000 chars; the hard budget is **1800 chars** (200-char safety margin). A split message means bumper cannot find the Commit: field and parse fails.

**Before posting, run `len()` on the string. If over 1800, trim — do not split.**

Budget breakdown by field (approximate):

```
Delimiter line:   ~55 chars  (fixed)
Title:            ~85 chars  (label + max title)
Summary:         ~265 chars  (label + max 250 chars)
Project:          ~20 chars  (fixed)
Highlights:      ~660 chars  (6 bullets × ~100 chars + labels)
Learnings:       ~330 chars  (3 bullets × ~100 chars + labels)
Commit:           ~20 chars  (fixed)
Tests:            ~55 chars  (fixed)
Branch:           ~20 chars  (fixed)
Whitespace/newlines: ~90 chars
──────────────────────────────
Total cap:      ~1600 chars  (leaves ~200 chars headroom)
```

Per-field limits when trimming:
- Summary: max 250 chars (1–2 sentences)
- Highlights: max 6 bullets, max 100 chars each
- Learnings: max 3 bullets, max 100 chars each
- Title: max 80 chars

**Commit: is load-bearing. It must be in the same message as the delimiter. Trim everything else first.**

## 5. Approval Gate Discipline

**Always ping #approve-this before:**
- Any commit
- Any push
- Any merge
- Any destructive git action (force-push, reset --hard, delete branch)
- Any dependency installation

**Never ping for:**
- Reads, typechecks, test runs, diagnostics
- In-scope edits not yet being committed

**In-between / unsure:** post to #current-task and wait for direction.

## 6. Monitoring Approval Responses

After posting to #approve-this:
- Re-fetch the channel immediately to check if a response is already there.
- If no response, use `Bash sleep 15 run_in_background` and call
  `fetch_messages` when the notification fires. Repeat until a response lands.
- The Monitor tool cannot call MCP tools — do not use it for Discord polling.
- Do not proceed without an explicit approval response.

## 7. Merge Gate Self-Check

Before posting the merge gate to #approve-this, verify all five:

1. Does my code do exactly what the approved plan said? Where it doesn't, is it in the deviation log?
2. Are there schema columns the plan specified that aren't in my migration?
3. Are there events the plan said should emit that don't?
4. Are there tests for behaviors the plan listed?
5. **Does the draft PASS COMPLETE fit in a single Discord message under 1800 chars?**
   Run `len()` on the string. If over, trim before including it in the gate.

The merge gate post must include the PASS COMPLETE as a code block so the developer
can review the exact text before approving. The text approved here is posted verbatim
to #changelog — no regenerating, expanding, or contracting after approval.

## 8. Dependency Request Format

Post to #approve-this (NOT #current-task):

```
[DEPENDENCY REQUEST — REQUIRES MANUAL APPROVAL]

Package: <name> <version>
Source: <PyPI / GitHub / etc.>
Purpose: <what this solves — be specific>
Alternatives considered: <stdlib? existing dep? skip entirely?>

Waiting for developer to install + confirm after vetting.
```

Then wait. Do not proceed. The developer installs and confirms.

## 9. MCP Failure Protocol

If Discord MCP is down:
- HALT before any gate.
- Do not use raw HTTP or REST API.
- Report the MCP failure to the developer directly in chat.
- Wait for MCP to be restored before any gated action.

## 10. Version in PASS COMPLETE

Version format: `v<arc>.<sub-arc>.<pass>[letter]`

- First commit: v0.0.0
- Each PASS COMPLETE: increment pass digit
- Sub-arc and arc bumps: developer signals when to bump
- Letter appendages: for squeeze-ins that bypass normal sequence (e.g. v0.0.3a)

The bumper accepts all these formats. The version in the PASS COMPLETE delimiter is what the bumper publishes.
