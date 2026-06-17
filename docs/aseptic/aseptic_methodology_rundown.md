# Aseptic Methodology — Formal Rundown

*For Cerebra's evaluation of adoption and adaptation. Based on the docs in PK (INTRODUCTION.md, LIVING_REPORTS.md, BLAST_RADIUS.md, CROSS_POLLINATION.md spec, AGENT_BRIEFING.md, SUPERVISOR_PROTOCOL.md, aseptic-notes.md, aseptic-artifacts.md, plus README and per-pass blast-radius files).*

---

## What Aseptic is, in one sentence

**A methodology for multi-agent code execution that treats coordination drift as a contamination problem — prevented through continuous discipline at the work boundary, not cleaned up retrospectively after damage accumulates.**

The "sterile field" metaphor is load-bearing: the shared understanding between agents of what the system currently is (its invariants, its debt, its divergences from spec) is treated like a clinical sterile field. Contamination is any work proceeding from a false model of that shared state. Aseptic's instruments keep the field clean between agent executions, not reconstruct it afterward.

## The problem Aseptic addresses

Six failure modes that surface specifically in multi-agent parallel execution:

1. **Convention drift** — Multiple agents independently invent multiple solutions to the same micro-problem. Each works in isolation; together they're inconsistent.

2. **Spec-as-aspiration** — Aspirational language in specs produces plausible-looking but wrong code. The agent invents syntactically-valid behavior that doesn't actually match what the spec required.

3. **Latent integration bugs** — A pass completes 100% green in its own scope while hiding issues that only surface in downstream work. Tests in one component pass while breaking adjacent components.

4. **Partial invariant implementation** — An agent discovers a load-bearing invariant during a pass and fixes the case it saw, but doesn't generalize. Future agents reintroduce the bug.

5. **ADR drift** — Two agents read the same ADR at different times after amendments and produce divergent code against what they each believed was the canonical spec.

6. **Silent shortcuts** — An agent encounters ambiguity, makes a plausible choice silently, and the choice is wrong. The wrongness is undetectable until much later.

Traditional retrospective surveys catch some of these but only after they've ossified. Aseptic's premise: catch them per-pass, structurally, through continuous instruments.

## The core conviction

**Constraints survive parallel execution. Intentions don't.**

A constraint is enforceable at the boundary of an agent's work. An intention requires alignment of judgment across agents. Two agents executing in isolation form different judgments and have no way to learn what the other decided.

ADRs in the multi-agent era stop being communication of intent and become the actual coordination mechanism. They have to be *specific*, *enforceable*, *testable*, and *boundary-aware* in ways traditional ADRs aren't. The document does more work than it used to.

This generalizes: any artifact intended to coordinate multiple agents needs to be enforceable at the boundary of each agent's work.

## The four moves that make the system work

1. **Specific, enforceable specifications.** ADRs use a parallel-execution-safe format. The agent-facing section is strictly enforceable (constraints, boundaries, invariants); the human-facing section remains conversational (context, consequences).

2. **Continuous instruments, not retrospective surveys.** Three living reports accumulate per-pass entries across the project's lifetime. Two per-pass artifacts capture what each pass touched.

3. **Supervisor passes between batches, not after the arc.** A supervisor pass reads living reports as first input, cross-checks against git diff, proposes targeted cleanup before the next parallel batch starts.

4. **Fail-loudly defaults.** When an agent encounters ambiguity, the correct behavior is to refuse and surface, not to make a plausible choice silently. Every "plausible choice silently made" is a landmine; every "agent refused and surfaced" is recoverable.

## The five artifacts

The operational core. Three accumulate across passes; two are produced per-pass.

### Living reports (accumulate)

**TECH_DEBT.md** — Functional but known-bad implementation choices.

Tracks deliberate deferrals, architectural shortcuts with known cost, implementations that bypass structural principles for pragmatic reasons. Each entry has a triggering condition for when it becomes worth addressing. Without a trigger, debt becomes wallpaper.

Entry structure: what it is, why it was necessary, known cost, trigger condition, evidence (file/line reference).

**POLISH_DEBT.md** — Correct but feels-wrong.

Tracks naming inconsistencies, doc gaps, stale README sections, test helper duplication, file organization that grew organically. Mechanical to fix; no design discussion required. Separated from tech debt because cleanup cadence is different (and intentionally less structured — meant to be a burndown checklist).

Entry structure: what it is, where (file/section), fix (specific enough to execute without discussion).

**DEVIATION.md** — Where implementation diverged from spec or ADR.

The most important of the three. Not a failure log — an information log. A deviation is when the agent decided that following the spec literally would be wrong, and made a different choice with justification. The entry records the divergence factually so future agents don't re-discover it.

Entry structure: what spec said, what implementation did, why the divergence was necessary, status (`OPEN — spec should be updated` / `OPEN — implementation should catch up` / `RESOLVED — spec updated` / `RESOLVED — implementation corrected`), adjacent impact.

**Resolution convention for all three:** Don't delete resolved entries. Strike through the heading, add a "> Resolved in vX.Y.Z" block with commit reference and resolution pass, collapse original body inside `<details>`. The history of "we knew, we fixed" is preserved.

### Per-pass artifacts

**BLAST_RADIUS/pass-NN.md** — One file per pass, structured.

Describes what *this specific pass* touched. Sections: Files (modified/created/deleted), Public APIs (added/modified/removed), Schema changes, Configuration changes, Dependency changes, Behavior changes, Living report updates.

The blast-radius file is the input for the PASS COMPLETE message (Highlights are a curated summary). Also the input for cross-pollination derivation.

The "Living report updates" section is **required even when empty**. An agent that made no updates must explicitly write "No new entries this pass. No entries resolved." This is the structural safeguard against empty-report-by-omission — an agent that didn't notice anything looks identical to one that didn't check, unless absence is made explicit.

**CROSS_POLLINATION/pass-NN.md** — One file per pass when adjacent-project impact exists.

For each adjacent project potentially affected: what changed that affects them, severity (BLOCKING / NEEDS-AWARENESS / FYI), suggested user action — pre-drafted message text the user can copy-paste to brief that project's advocate agent, or a verification command, or "no action needed."

Cross-pollination is separated from blast-radius because audiences differ: blast-radius is "what this project did," cross-pollination is "what adjacent projects should do about it."

## Supervisor passes

Runs between parallel batches, not after the arc closes. Cheap relative to retrospective surveys because living reports already surface most issues.

Process:
1. Read living reports — identify open entries accumulated since last supervisor pass
2. Run the integrity loop — fetch git diffs, cross-check against blast-radius files, flag any change not represented in a blast-radius (catches the "no new entries by omission" failure mode)
3. Verify spec coherence — cross-check DEVIATION entries against current spec docs and current code
4. Cross-check living reports against actual code state — find code patterns that should be logged but weren't
5. Identify findings per-pass agents missed — convention drift across agents, latent integration issues
6. Produce SUPERVISOR_REPORT.md — severity-classified findings with proposed cleanup tasks
7. **Halt before executing any fix** — non-negotiable. The supervisor pass is a diagnostic instrument; output goes to human review

The halt discipline exists because supervisor findings sometimes reveal that an assumption the whole system was built on is wrong. Executing fixes without review can propagate the wrong assumption.

Trigger conditions: living reports exceed 600 lines, batch of N parallel passes completed (recommended after every 3-5 parallel passes), explicit human request.

## Version convention

Work passes increment normally: `v0.9.0`, `v0.10.0`, `v0.11.0`.

Cleanup passes for non-load-bearing debt count down from `z`: `v0.11.z`, `v0.11.y`, `v0.11.x`.

The load-bearing test: if you'd describe the fix to a user as "we made X better," it's load-bearing and uses forward versioning. If you'd describe it as "we cleaned up internally," it's non-load-bearing and uses descending letters.

Three to five descending letters between forward versions is normal. Consuming more is a soft signal that upstream cadence is wrong (debt accumulating faster than addressed).

The version stream becomes legible at a glance: forward versions = features and load-bearing fixes; descending letters = internal hygiene.

## ADR format

Parallel-execution-safe template:

```
# ADR-N: <Title>

## Decision
One sentence.

## Constraints (enforceable)
- Specific, testable. "Type X must implement trait Y."

## Boundaries (parallel-execution-safe)
- Files this decision permits modification of: <explicit list>
- Files this decision PROHIBITS modification of: <explicit list>
- Other ADRs this decision depends on: <list with version refs>

## Invariants (testable)
- Property tests or assertions that must hold after this decision

## Failure-mode preference
- When implementation hits ambiguity, prefer: <"loud failure" / "explicit refusal" / "well-defined fallback">

## Context (for humans)
Why this decision. Tradeoffs considered. What this replaces.

## Consequences
What downstream work this enables or constrains.
```

The top sections (Decision through Failure-mode preference) are what parallel agents read. The bottom sections are conversational context for humans. The discipline is making the agent-facing section strictly enforceable while the human-facing section remains conversational.

## Agent briefing

A copy-pasteable system-prompt fragment for participating agents. Specifies:
- Read TECH_DEBT, POLISH_DEBT, DEVIATION before writing code
- At pass completion: update living reports, write blast-radius file, write cross-pollination if warranted, write pass report
- Fail-loudly defaults
- Deviation surfacing convention (don't silently align code to spec or spec to code; surface as DEVIATION entry)
- Version convention (load-bearing → forward, cleanup → descending letter)

The briefing makes Aseptic discipline portable — drop it into any agent's task prompt and that agent participates correctly.

## What Aseptic explicitly is NOT

- **Not process-heavy.** Each living-report entry should be 1-3 sentences. Each blast-radius file is a structured snapshot. The discipline is lightweight per-pass; the value comes from continuity, not depth.

- **Not a replacement for spec discipline.** Aseptic assumes specs already exist and are well-written. It addresses the gap between "spec is good" and "multi-agent execution against the spec stays clean."

- **Not automation.** No CI hooks, no enforcement scripts, no linters. It's a practice discipline. Instruments work because agents find them useful, not because a system enforces compliance.

- **Not universally applicable.** Solo sequential work doesn't benefit much. Works well for projects with clean module boundaries, well-understood domains, and ADR-friendly decision structure. Struggles with projects where "taste" is primary input (UI, subjective business logic).

---

# Adaptation analysis for Cerebra

## What Cerebra already does (partial Aseptic)

Cerebra has organic versions of several Aseptic patterns:

**Deviation logs per version.** `docs/agent/deviations/v0.3.0.md`, `v0.3.2.md`, `v0.3.3.md` exist with DEV-NNN entries. Each captures what was deviated, why, impact, approval. This is functionally identical to Aseptic's DEVIATION.md — except Cerebra splits by version while Aseptic accumulates in one file.

**MERGE GATE + PASS COMPLETE pattern.** The bandit methodology already requires structured pass reporting via the PASS COMPLETE format (Title, Summary, Highlights, Learnings, Commit, Tests, Branch). This is partial BLAST_RADIUS — but less detailed about API surface, schema changes, configuration changes.

**Per-pass `phase_N_step_M_kickoff_prompt.md` documents.** These are partially ADR-like — they specify what's in scope, what's deferred, references to read, success criteria. The "specific risks" section captures invariants. But they're not formal ADRs and don't have the parallel-execution-safe boundary definitions.

**The "ASK rather than deviate silently" discipline in bandit's prompts.** This is Aseptic's "fail-loudly defaults" + "deviation surfacing convention" applied informally.

**Cross-Claude relays.** Manual cross-pollination work via Lattica Claude relays. Functionally similar to what CROSS_POLLINATION files would capture, but reconstructed during each relay rather than produced as a structural artifact.

## What Cerebra would gain by formalizing

**TECH_DEBT.md and POLISH_DEBT.md don't exist.** Cerebra has tech debt tracked in conversation (LoRA training resume conditions, primitives extraction 90-day criterion, dark matter substrate implementation, witness layer projections, cognitive extensions, etc.). All of it lives in my memory entries or scattered in design docs. A living TECH_DEBT.md would make these legible at a glance to bandit and future Claudes, with explicit trigger conditions.

**No supervisor passes.** Cerebra's implicit "supervisor work" happens when I (Cerebra Claude) review bandit's MERGE GATE submissions, but it's not formalized as a separate periodic pass. We have no explicit integrity loop, no spec coherence verification across multiple phases, no cross-pass pattern detection.

**No formal ADRs.** Cerebra has design docs (`v01_phase6_design.md`, `v01_phase5_design.md`, etc.) and concept docs, but no parallel-execution-safe ADR format. As Cerebra scales to multi-agent implementation (if we add parallelism per the earlier discussion), this gap becomes meaningful.

**No version convention for cleanup work.** Cerebra uses informal letter suffixes (v0.3.1a, v0.3.2a) for "squeeze-in" passes, but doesn't have the systematic load-bearing/cleanup distinction. The forward-vs-descending pattern would make version streams legible.

**No structured blast-radius per pass.** The PASS COMPLETE format captures highlights but not the full structured inventory Aseptic's BLAST_RADIUS provides. Adjacent projects (Lattica, LumaWeave, fossic eventually as consumer of Cerebra output) currently learn about Cerebra changes through ad-hoc relays rather than structured cross-pollination files.

## What needs scrubbing for Cerebra orientation

Direct fossic-isms in the doc set that need replacement:

**Adjacent project list.** Aseptic's docs reference fossic's adjacent projects: cerebra, policy-scout, lumaweave, bo, ai-stack, rhyzome (benched), bons.ai (benched). For Cerebra-oriented Aseptic, adjacent projects become: fossic, lumaweave, bons.ai, policy-scout, rhyzome (if active), bo (if active). The list is inverted — fossic becomes an adjacent project where it was the host before.

**File path references.** `docs/aseptic/...` could stay or could move to `docs/agent/aseptic/...` to fit Cerebra's existing `docs/agent/` convention. Bandit reads from `docs/agent/` for deviation logs already; consistency favors integration into that namespace.

**Example references.** Aseptic's docs use fossic examples throughout: "Pass 8.5 Symbol-binding bug," "napi-rs limitation," "purge_event semantics," "tilde expansion drift." These would need replacement with Cerebra examples (which we have plenty of from the day's work: PyO3 bridge cost surfacing in benchmark, governance/ structure mismatch in Phase 7 audit, sessions table name collision in Phase 8 Step 1, etc.).

**Discord channel references.** Aseptic doesn't reference fossic-specific Discord channels in the spec docs I read, but if any exist in the operational docs (channel IDs for #current-task, #approve-this, #changelog), those would need Cerebra's channel IDs substituted.

**Bandit-specific terminology.** Cerebra uses "bandit" as the implementing agent name; Aseptic doesn't have an implementing-agent name (uses "the agent"). Either substitute "bandit" specifically or keep "the agent" as generic.

**Methodology references.** Some Aseptic docs reference fossic's specific methodology elements (Blog Bumper integration for PASS COMPLETE, the supervisor protocol triggering between parallel batches). Cerebra uses blog.bumper too and could keep these references; or could generalize.

The scrub-and-convert task is mechanical but real. Estimate: ~2-3 hours of focused Claude Code work to read through all the spec docs and produce a Cerebra-oriented version. The doc set is maybe 12 files totaling several thousand words.

## Where Aseptic might need expansion for Cerebra

Cerebra's coordination patterns go beyond what Aseptic was designed for. Three specific expansions worth considering:

### 1. Multi-Claude role coordination (beyond parallel code execution)

Aseptic was designed for parallel code agents working on the same project (fossic Pass 6 might run two agents implementing different bindings simultaneously). Cerebra has a different pattern: multiple Claude instances with **distinct roles** — Cerebra Claude (architecture + coordination), bandit (implementing agent), Lattica Claude (cross-project coordinator for fossic), terminal Claude (operational pipeline work).

Each role produces different artifacts and has different coordination needs. Cerebra Claude produces design docs and kickoff prompts; bandit produces code and PASS COMPLETE; Lattica Claude produces cross-project relays; terminal Claude produces bumper bumps.

Aseptic's instruments are agent-symmetric — every agent reads and writes the same artifacts. Cerebra's role asymmetry might need role-specific Aseptic extensions:
- Cerebra Claude's deliverables: design docs, kickoff prompts, vocabulary specs — what's the BLAST_RADIUS equivalent for these?
- Cross-Claude coordination (Cerebra ↔ Lattica): the CROSS_POLLINATION pattern works in principle, but the relay format and the synthesis-from-relay format don't have explicit Aseptic instruments yet.

### 2. Knowledge work artifacts (beyond code)

Aseptic's five artifacts assume code is the primary output. Cerebra produces substantial knowledge work alongside code: concept docs, vocabulary specs, design docs, methodology observations, coordination relays. These have their own "drift" failure modes (concept doc rationale gets forgotten, vocabulary specs become inconsistent across consumers, design decisions get re-litigated).

Possible expansion: a sixth artifact category, KNOWLEDGE_DEBT.md or similar, capturing things like "this design rationale isn't in any concept doc yet" or "this concept doc references an obsolete pattern." Different cleanup cadence than TECH_DEBT or POLISH_DEBT.

Could also be handled by extending POLISH_DEBT to include doc/spec quality issues, with a clear distinction between code-polish-debt and doc-polish-debt. Avoiding artifact proliferation has methodology virtue.

### 3. Long-horizon arc coordination

Aseptic was developed during a one-day fossic build with eleven parallel passes. Cerebra operates on longer horizons: phases close over hours-to-days, blocks close over days-to-weeks, the broader v0.1 milestone is a multi-week arc with regular pauses and resumptions.

Specific gaps:
- Resume discipline: when Ryan picks up after a break, what's the structured "where were we" artifact? Currently it's me reconstructing from memory + tracker. A formal CURRENT_STATE.md or similar might serve.
- Cross-phase pattern detection: Aseptic's supervisor pass runs between batches. Cerebra's "between batches" cadence is more like "every few phases." The trigger conditions might need adjustment for the longer horizon.
- Phase-vs-pass-vs-step terminology: Aseptic uses "pass" as the atomic unit. Cerebra uses pass within a step within a phase within a block. Aseptic's instruments need to be clear about which level they apply at.

These expansions aren't required for Cerebra to adopt Aseptic — the core methodology works as-is — but they're places where adoption surfaces real gaps that future Aseptic evolution should address.

## Adoption recommendation

If we adopt Aseptic on Cerebra, the cleanest path is:

**Phase 1 — Scrub and convert (one focused Claude Code session, ~2-3 hours).** A separate Claude Code agent reads the Aseptic doc set in PK, produces Cerebra-oriented versions with fossic references scrubbed, adjacent project list inverted, examples replaced with Cerebra equivalents. Output goes to `docs/agent/aseptic/` in the Cerebra repo.

**Phase 2 — Seed living reports.** Bandit produces initial TECH_DEBT.md, POLISH_DEBT.md, and DEVIATION.md by scraping existing deviation logs (v0.3.0.md, v0.3.2.md, v0.3.3.md) and conversation-tracked tech debt items. The Cerebra "banked / post-v0.1" list in our task tracker maps directly to TECH_DEBT entries with trigger conditions.

**Phase 3 — Bandit briefing update.** Update bandit's standard task-prompt format to include the Aseptic agent briefing fragment. Future kickoff prompts reference Aseptic-style artifacts as required outputs.

**Phase 4 — First supervisor pass.** After Phase 8 closes, run a supervisor pass against the accumulated living reports. Produces SUPERVISOR_REPORT.md, identifies cleanup batch for descending-letter version (v0.3.3z or similar).

**Phase 5 — Cross-pollination workflow with Lattica Claude.** When fossic ships its first CROSS_POLLINATION/pass-NN.md file affecting Cerebra (Lattica Claude's commitment from earlier coordination), Cerebra-side responder reads it and updates Cerebra's DEVIATION.md or TECH_DEBT.md with the implications. Reciprocally, Cerebra produces CROSS_POLLINATION/pass-NN.md files when Cerebra phases close with cross-project impact.

**Phase 6 (later) — Expansion work.** Address the three expansion areas (multi-Claude role coordination, knowledge work artifacts, long-horizon arc) as Cerebra's specific gaps surface. Document the expansions and contribute back to the canonical Aseptic project when it exists.

## Cost/benefit assessment

**Costs of adoption:**
- ~2-3 hours of focused Claude Code work to scrub and convert
- ~30 minutes per pass of additional discipline (living report updates, blast-radius write, cross-pollination when warranted)
- Initial overhead of seeding living reports from existing scattered records
- Cognitive overhead of remembering to consult living reports at pass start

**Benefits of adoption:**
- Cerebra's tech debt becomes legible at a glance (currently scattered)
- Cross-Claude coordination becomes structured (currently ad-hoc relays)
- Supervisor passes catch issues that per-pass methodology misses
- Version convention makes load-bearing vs cleanup work visually distinct
- Cerebra becomes a second reference implementation for Aseptic itself, which has methodology value
- Bandit's deviation discipline gets clearer structural support

**Honest read:** Adoption is worth it post-v0.1, not now. The core v0.1 work (Phase 8 cycle runtime, Phase 9-11) is the highest-value thing Cerebra can be doing today. Aseptic adoption work isn't bad, it's just lower-priority than shipping the cognitive runtime. The scrub-and-convert can run in parallel with bandit's Phase 8 Step 2 work if you want it done now, but the actual operational adoption (bandit reads living reports, produces blast-radius files) is better timed for after v0.1 milestone when there's natural pause to integrate methodology changes.

The most useful immediate move would be **producing TECH_DEBT.md and POLISH_DEBT.md from existing scattered records** — banking the debt we already know about in a legible format, even before adopting the full per-pass discipline. That's maybe 30 minutes of work and immediate value.

---

*End of formal rundown. Decisions for Ryan: (1) when to adopt Aseptic on Cerebra, (2) whether to do the scrub-and-convert now or defer, (3) whether to seed TECH_DEBT.md and POLISH_DEBT.md now as a low-overhead first step, (4) whether the three expansion areas (multi-role, knowledge work, long-horizon) need investment beyond core adoption.*
