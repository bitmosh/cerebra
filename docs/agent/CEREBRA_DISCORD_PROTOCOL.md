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
5. MERGE GATE: post to #approve-this. Wait for approval. Commit with explicit paths.
6. Post PASS COMPLETE to #changelog with real SHA.
7. BUMP+PUSH GATE: `bumper bump --dry` → post to #approve-this → wait for approval → execute.
```

Do not skip steps. Do not combine steps. Each gate is a real pause.

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
- Re-fetch the channel immediately to check if a response was already there.
- If no response after posting, use Monitor tool with a flat 30–45s poll (fetch limit 15).
- Do not spin a fake background loop.
- Do not proceed without an explicit approval response.

## 7. Dependency Request Format

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

## 8. MCP Failure Protocol

If Discord MCP is down:
- HALT before any gate.
- Do not use raw HTTP or REST API.
- Report the MCP failure to the developer directly in chat.
- Wait for MCP to be restored before any gated action.

## 9. Version in PASS COMPLETE

Version format: `v<arc>.<sub-arc>.<pass>[letter]`

- First commit: v0.0.0
- Each PASS COMPLETE: increment pass digit
- Sub-arc and arc bumps: developer signals when to bump
- Letter appendages: for squeeze-ins that bypass normal sequence (e.g. v0.0.3a)

The bumper accepts all these formats. The version in the PASS COMPLETE delimiter is what the bumper publishes.
