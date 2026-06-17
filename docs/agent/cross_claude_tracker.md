# Cross-Claude Coordination Tracker

**Purpose:** Running list of items pending for OTHER Claudes (Lattica Claude / fossic, Claude Code, bandit). Updated at the close of each pass so nothing slips while processes run.
**Owner:** Ryan; updated by Cerebra Claude as items move
**Last updated:** 2026-06-13 (Phase 9 Step 3 MERGE GATE review)

---

## Items pending for bandit

### Immediate (this pass / next pass)

| ID | Item | Priority | Context |
|---|---|---|---|
| B-001 | Produce `docs/aseptic/cross-pollination/pass-9.3.md` | NEEDED before Step 4 | CatalystInvoked + CatalystArmSelected event payload schemas going to fossic AGENT_TRACE_VOCABULARY.md. Required Step 3 deliverable that was missed. Format follows pass-9.1.md. Source-of-truth: actual code in `cerebra/cognition/catalyst.py` event emission. |
| B-002 | Add TD-018 to TECH_DEBT.md | LOW | CliRunner(mix_stderr=False) Click version compat issue. 39 failures across `test_memory_cli.py` (29), `test_abstention.py` (3), `test_memory_cli_against_vault.py` (7). Shared fix: remove `mix_stderr=False` from CliRunner() calls. |
| B-003 | Add TD-019 to TECH_DEBT.md | LOW | `test_lattice_against_vault.py` single failure. Separate root cause (vault-against-disk, not Click-related). Needs investigation. |
| B-004 | Update research docs per Step 3 clarifications | LOW | `catalyst_v0_1_arm_vocabulary.md` YAML fix (Q2/Q3); `catalyst_integration_decisions.md` D11 addition for `role:` field (Q1). Fold into Step 4 commit. |

### Step 4 scope (next pass)

| ID | Item | Priority | Context |
|---|---|---|---|
| B-005 | Phase 9 Step 4 implementation | QUEUED | Re-injection trigger + child session spawn + Phase 9 close. Kickoff drafting after B-001 lands. |

---

## Items pending for Lattica Claude (fossic)

### Open

| ID | Item | Priority | Context |
|---|---|---|---|
| L-001 | AGENT_TRACE_VOCABULARY.md §7.5.1 update | BATCHED | ClutchDecisionMade payload extension (cascade_depth, escalate_to_catalyst). Acknowledged in last relay; batched with other post-rc.1 doc corrections. No action needed from us; just tracking. |

### Pending production on our side

| ID | Item | Priority | Context |
|---|---|---|---|
| L-002 | AGENT_TRACE_VOCABULARY.md §7 — CatalystInvoked + CatalystArmSelected | BLOCKED | Pending B-001 (bandit produces pass-9.3.md). Once pass-9.3.md lands, relay to Lattica Claude. |

---

## Items pending for Claude Code

### Open

| ID | Item | Priority | Context |
|---|---|---|---|
| C-001 | (none currently) | — | — |

---

## Items pending for Ryan (you)

| ID | Item | Priority | Context |
|---|---|---|---|
| R-001 | Decide on `current_state.md` content depth | MEDIUM | New living doc for fossic/lattica cross-project visibility into Cerebra's dev state. Initial version produced this session. Update cadence: end of each major arc (phase close, not per-step). |
| R-002 | Decide on PD-008 status (README.md fossic-framed) | LOW | Added per recommendation last pass. Can resolve at Phase 9 close or carry forward. |

---

## Recently completed (last 5 items)

| Completed | Item | Closed via |
|---|---|---|
| 2026-06-13 | Phase 9 Step 3 — CatalystEngine | bandit (commit 432b834) |
| 2026-06-13 | Aseptic cleanup (TECH_DEBT/POLISH_DEBT/FUTURE_DIRECTIONS swap) | Claude Code → bandit verify |
| 2026-06-13 | LATTICA_PRIMITIVES.md §11 Bandit Selector spec landing | bandit (with 4 cascading cleanup fixes) |
| 2026-06-13 | Phase 9 Step 2 — Bandit primitive | bandit (1667 passing) |
| 2026-06-13 | Phase 9 Step 1 — ClutchEngine | bandit (1644 passing) |

---

## Standing protocols (reference)

**Discord channels:**
- `#current-task` — work-in-progress END
- `#approve-this` — MERGE GATE + BUMP+PUSH GATE
- `#changelog` — PASS COMPLETE (bumper triggers on `── PASS COMPLETE · vX.Y.Z` delimiter)
- `#notifications` — bumper output
- `#brainstorm` — bandit asks when ambiguous

**Cross-pollination naming:** `docs/aseptic/cross-pollination/pass-N.M.md` (matches fossic convention)

**Sev tags for cross-pollination:**
- `BLOCKING` — receiving project should drop other work
- `NEEDS-AWARENESS` — receiving project should schedule (batch with other doc corrections fine)
- `INFO` — receiving project may want to know

---

## Maintenance

This file gets updated at:
- End of each pass (move completed items to "Recently completed")
- When new items surface (add to appropriate Claude's queue)
- Before Step 4 kickoff (verify nothing slipped)

Items don't expire — they get resolved or explicitly deferred with a new context line.
