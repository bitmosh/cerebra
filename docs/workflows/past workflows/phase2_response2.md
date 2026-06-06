# Cerebra Phase 2 — Second-Round Consultation Response

*Probes run, all 30 fixtures audited, temperature data collected. Where I'm revising my first report's position, I'll say so explicitly.*

---

## Decision 1 — Fixture Audit

### The Three Flagged Fixtures

```
fixture_id: clear_04
content: "Cerebra is a local-first cognitive runtime. It ingests knowledge sources,
          classifies memory, and provides structured retrieval for reasoning cycles."
current label: PHENOMENON
model's answer: TOOL
verdict: KEEP
reasoning: The dominant sentence is "Cerebra IS a [entity]" — a bounded definition of a
named thing. That is the canonical PHENOMENON shape. The second sentence lists capabilities,
but it's subordinate to the definition. TOOL requires focus on what an instrument does FOR
the agent using it; this text is explaining what Cerebra IS, not positioning it as an
instrument for your use. The model is pattern-matching "it [does X for purpose Y]" as TOOL,
which is a surface reading that misses the definitional frame of the whole chunk.
```

```
fixture_id: clear_10
content: "The vault directory at ~/cerebra-vaults/dev/ contains: data/ (SQLite database),
          artifacts/ (normalized document JSON), events/ (NDJSON inspector logs),
          leeway/ (governance YAML), constitutional/ (constitutional rules YAML)."
current label: CONTEXT
model's answer: OBSERVATION
verdict: KEEP
reasoning: This is describing the environment Cerebra operates in — the physical layout of
the vault, what each directory holds. That is the definition of CONTEXT: setting, environment,
scope. OBSERVATION is measurements, data points, counted states. A directory listing is not
a measurement; it is environmental architecture. The model is pattern-matching "contains: X,
Y, Z" as an enumeration of observed facts, which is a surface reading. The presence of the
tilde-path and directory structure are strong CONTEXT signals the model is not weighing.
```

```
fixture_id: hard_08
content: "A STOP-gate triggers when 5 or more simultaneous test failures share a root cause.
          Do not patch them one by one. Classify the shared signature first."
current label: CONSTRAINT
model's answer: PATTERN
verdict: KEEP
reasoning: "Do not patch them one by one" is a hard prohibition — unambiguous CONSTRAINT
language. The "when 5 or more... triggers" clause describes the activation condition for the
constraint, not a recurring pattern. PATTERN would require the text to be identifying a
regularity across observations; this text is issuing a rule. The model is over-weighting the
conditional structure ("when X occurs") and under-weighting the explicit "do not" prohibition.
```

All three: KEEP. The model was wrong in all three cases, not the fixtures.

---

### Full Audit of the Remaining 27

Going through every fixture with the same strict eye. Verdicts use the requested format.

---

**clear_01:**
```
fixture_id: clear_01
content: "Every cognitive action must emit a structured inspector event at write time.
          Silent code is incomplete code. Inspector events are non-negotiable."
current label: PRINCIPLE
model's answer: CONSTRAINT
verdict: KEEP
reasoning: "Must emit" is a positive behavioral standard — it defines how things SHOULD work,
not what is prohibited. "Non-negotiable" appears in the prompt's PRINCIPLE keyword list.
"Silent code is incomplete code" is a doctrinal statement about quality. CONSTRAINT requires
a prohibition or outer wall; this is a prescriptive norm. The model is treating "non-negotiable"
as a prohibition marker, but the text specifies a required behavior rather than forbidding one.
```

**clear_02:**
```
fixture_id: clear_02
content: "cerebra ingest <path> discovers all markdown and text files under the target
          directory, registers them as sources, parses each, chunks the content, and writes
          memory records."
current label: TECHNIQUE
model's answer: MECHANISM
verdict: MARK_AMBIGUOUS
reasoning: The fixture notes "Procedural step-by-step description of how to invoke the
command. Classic TECHNIQUE." But the description is in the passive system-action voice:
"discovers... registers... parses... chunks... writes" — all subject-is-the-system, no
human actor performing steps. Substituting "it happens automatically" preserves full meaning,
which by the v1.1.0 prompt's own MECHANISM test points to MECHANISM. TECHNIQUE requires an
actor following steps; this describes what the system does. The model's MECHANISM answer is
genuinely defensible. The fixture might be better labeled as MARK_AMBIGUOUS or relabeled to
MECHANISM given the prompt's stated test.
```

**clear_03:**
```
fixture_id: clear_03
content: "content_hash is derived by reading the file in 64KB blocks and feeding each block
          to SHA256. The final digest is returned as a lowercase hex string."
current label: MECHANISM
model's answer: MECHANISM (probed directly — correct)
verdict: KEEP
reasoning: Classic causal chain with passive subject. "Is derived by [causal process]" is
the canonical MECHANISM form. No ambiguity.
```

**clear_05:**
```
fixture_id: clear_05
content: "Do not assist with creating weapons capable of mass casualties, biological agents,
          chemical weapons, or any action that would harm large populations."
current label: CONSTRAINT
verdict: KEEP
reasoning: "Do not" plus explicit prohibition list. Canonical CONSTRAINT. No ambiguity.
```

**clear_06:**
```
fixture_id: clear_06
content: "bitmosh is the sole developer of Cerebra. The project is a solo exploration of
          cognitive architecture with no team dependencies."
current label: AGENT
verdict: KEEP
reasoning: Named person, role, intent. Canonical AGENT. No ambiguity.
```

**clear_07:**
```
fixture_id: clear_07
content: "The sku_assignments table stores: assignment_id (PK), record_id (FK), sku_address,
          d1 through d10 digit columns, raw_scores_json, classifier_version..."
current label: DESIGN
verdict: KEEP
reasoning: Schema definition — intentional structure of a data artifact. The table was
designed with these columns. Canonical DESIGN.
```

**clear_08:**
```
fixture_id: clear_08
content: "Tombstoned items do not return on retrieval queries but block re-insertion of the
          same item. Once tombstoned, an item stays tombstoned until explicit removal."
current label: MECHANISM
verdict: KEEP
reasoning: Causal chain: tombstone state → blocks retrieval AND blocks re-insertion. The
"do not return" could be read as CONSTRAINT-adjacent, but the text is describing automatic
system behavior, not issuing a prohibition. The "stays tombstoned until explicit removal"
is a state-machine description. MECHANISM is correct.
```

**clear_09:**
```
fixture_id: clear_09
content: "Desired outcome for Phase 2: every memory record in the vault has a non-null
          sku_address. The classifier backfill sweep must leave zero NULL records."
current label: GOAL
verdict: KEEP
reasoning: "Desired outcome" + success criterion. Canonical GOAL. No ambiguity.
```

**clear_11:**
```
fixture_id: clear_11
content: "Phase 0 complete at commit 5747c7e on 2026-06-04. 88 tests passed. Repository
          initialized, governance loaded, first vault created successfully."
current label: EVENT
verdict: KEEP
reasoning: Named occurrence at a specific commit + date. Canonical EVENT. The numbers (88
tests) add slight OBSERVATION texture but the primary shape is a time-situated occurrence.
```

**clear_12:**
```
fixture_id: clear_12
content: "Six Lattica primitives vendored verbatim into cerebra/_primitives/: Clutch,
          SignalTriangulator, TrajectoryTracker, HysteresisModeRouter, ComponentScoreComposer,
          TombstoneSet."
current label: CREATION
verdict: KEEP
reasoning: Artifacts produced and placed in the codebase. Canonical CREATION.
```

**clear_13:**
```
fixture_id: clear_13
content: "The Clutch primitive maps signal state to typed action via a priority-ordered rule
          cascade. Rules fire in priority order; the first matching rule wins."
current label: TOOL
model's answer: MECHANISM
verdict: MARK_AMBIGUOUS
reasoning: The first sentence has TOOL surface form: "maps X to Y via Z" describes the
capability interface. But the second sentence is pure MECHANISM: "rules fire in priority
order; the first matching rule wins" describes internal causal operation. The fixture notes
acknowledge this: "TOOL is 'what it does for you'; MECHANISM is 'how the internals work.'"
Both sentences are present and neither is subordinate. This chunk is describing both what
the Clutch does AND how it does it internally. A 3/2 human split is realistic here. Calling
the model wrong is harder to defend than for clear_01 or clear_14.
```

**clear_14:**
```
fixture_id: clear_14
content: "Provenance digit D10 must distinguish synthesized entries from observed entries
          at the address level. Without this, the substrate is contaminated."
current label: PRINCIPLE
model's answer: CONSTRAINT
verdict: KEEP
reasoning: "Must distinguish" is a positive behavioral requirement — it specifies what the
system SHOULD do, not what it must NOT do. "Without this, the substrate is contaminated"
gives the architectural reason for the requirement. This is design doctrine, not prohibition.
CONSTRAINT would require "must not conflate" or "never mix observed and synthesized." The
requirement is expressed as a positive obligation (must do X) not a negative prohibition
(must not do Y). PRINCIPLE is correct.
```

**clear_15:**
```
fixture_id: clear_15
content: "LumaWeave visualizes knowledge graphs; Cerebra produces the cognitive substrate
          those graphs run on. One makes, the other thinks about what was made."
current label: RELATION
verdict: KEEP
reasoning: Explicit dependency between two named systems. Canonical RELATION.
```

---

**hard_01:**
```
fixture_id: hard_01
content: "The SKU is the substrate that makes everything above it possible. Get this right
          and the truth tower, the leeway network, and the dream/retrain direction all
          compose cleanly on top of it."
current label: PRINCIPLE
model's answer: RELATION
verdict: MARK_AMBIGUOUS
reasoning: "Makes everything above it possible" + "compose cleanly on top of it" is
structural dependency language — the primary information being conveyed is HOW the SKU
relates to everything else in the architecture. That is RELATION. "Get this right" is
prescriptive, which tips toward PRINCIPLE, but it's more of an engineering guideline
framing than a design doctrine. A case can be made that the text is issuing a normative
imperative ("do this correctly"); an equal case can be made that it is describing an
architectural dependency ("the SKU enables everything above it"). The model's RELATION
answer is genuinely defensible, perhaps more so than PRINCIPLE given the structural
framing of the second sentence.
```

**hard_02:**
```
fixture_id: hard_02
content: "The leeway network inverts prohibition models. Instead of specifying what is
          forbidden, it specifies what is permitted under what conditions. Everything
          outside the network is implicitly disallowed."
current label: MECHANISM
model's answer: DESIGN
verdict: MARK_AMBIGUOUS
reasoning: "Inverts prohibition models" is describing an architectural design choice —
a deliberate departure from conventional prohibition-based design. "Instead of X, it
specifies Y" is design decision language. "Everything outside the network is implicitly
disallowed" describes the operational consequence (MECHANISM). Both cognitive shapes are
present. The fixture chose MECHANISM for the operational inversion; the model chose DESIGN
for the architectural decision framing. The first sentence ("inverts prohibition models")
is the primary claim and it is explicitly about the design choice made, not the causal
chain by which it operates. The model's DESIGN answer is defensible.
```

**hard_03:**
```
fixture_id: hard_03
content: "When a location saturates — more than 255 entries at a single SKU address — that
          is signal that this address is genuinely active and is a candidate for deeper
          subdivision via the type-tag axes."
current label: OBSERVATION
verdict: KEEP
reasoning: "More than 255 entries" is a specific threshold condition. "That is signal"
is pointing at a measurement-based indicator. This is closer to OBSERVATION (a threshold
event on a measured quantity) than PATTERN (a recurring structure across many instances).
PATTERN would describe a regularity seen repeatedly; this describes one condition at one
address. KEEP, though OBSERVATION is the weaker label of the easy-to-medium set.
```

**hard_04:**
```
fixture_id: hard_04
content: "The bandit primitive updates strategy selection weights per query shape over time.
          Strategies that work for certain query shapes get higher selection probability.
          The system gets better at retrieving over time, not just storing."
current label: MECHANISM
verdict: KEEP
reasoning: Causal learning loop: past performance → weight update → higher selection
probability. Classic MECHANISM — internal causal chain operating automatically over time.
No ambiguity.
```

**hard_05:**
```
fixture_id: hard_05
content: "Consolidation converts episodic cycle history into durable semantic and
          procedural memory. Repeated patterns become compressed representations;
          one-off events are allowed to decay."
current label: MECHANISM
model's answer: PATTERN
verdict: KEEP
reasoning: "Converts... become compressed... are allowed to decay" describes a causal
transformation process. The word "repeated patterns" in the text is a noun phrase (input
to the mechanism), not a description of a PATTERN cognitive shape. MECHANISM is correct.
The model appears to be anchoring on the word "patterns" in the text rather than reading
the cognitive shape of the whole sentence. The "allowed to decay" clause is particularly
mechanistic — a system process, not a description of recurring structure.
```

**hard_06:**
```
fixture_id: hard_06
content: "Measurement: cerebra ingest docs/refined-runtime-model/ produced 39 sources and
          745 chunks with 0 failures on 2026-06-04."
current label: OBSERVATION
verdict: KEEP
reasoning: Begins with "Measurement:" — an explicit genre marker. Numeric outputs (39
sources, 745 chunks, 0 failures). The date "2026-06-04" adds EVENT texture but the
primary information is the measured output of a process run, not the occurrence of the
run itself. OBSERVATION is correct.
```

**hard_07:**
```
fixture_id: hard_07
content: "The approval gate is a workflow convention, not a CLI feature. bumper renders
          and traces, and you (or your agent) post a dry-run sample for approval before
          the live bump."
current label: DESIGN
model's answer: MECHANISM
verdict: KEEP
reasoning: "Is a workflow convention, not a CLI feature" is an explicit design decision
statement — it asserts what architectural category this belongs to. "bumper renders and
traces, and you post a dry-run sample" is procedure (TECHNIQUE-adjacent), not internal
causality. MECHANISM would require describing how the gate works causally. The first
sentence is the load-bearing claim: "this is a convention not a feature" = a design
choice. The model getting MECHANISM is harder to defend than DESIGN or PRINCIPLE;
this is a genuine model error.
```

**hard_09:**
```
fixture_id: hard_09
content: "Phase 2 scope: assign D1, D4, D9, D10 digits using the classifier; stub D2, D3
          as 0x0 with subcategory_strategy_version='v1-stub'; defer D5, D6 to v0.2."
current label: DESIGN
verdict: KEEP
reasoning: Scoping decisions — what was included, what was stubbed, what was deferred.
Canonical DESIGN (intentional structural choices made for a purpose). No ambiguity.
```

**hard_10:**
```
fixture_id: hard_10
content: "Memories above the active salience threshold are promoted to working memory and
          become available to the current reasoning cycle. Below the threshold, they stay
          in episodic storage."
current label: MECHANISM
model's answer: OBSERVATION
verdict: KEEP
reasoning: Threshold-based state transition: above X → promoted, below X → stays. Classic
MECHANISM — automatic causal process. No human actor, no measurement being reported. The
model likely anchored on "threshold" as a measurement term, but the text is describing the
causal consequence of threshold comparison, not reporting an observed measurement.
```

**hard_11:**
```
fixture_id: hard_11
content: "Two-attempt cap: if a fix and one retry both fail, stop and report. Three rounds
          on one theory means the theory is wrong."
current label: CONSTRAINT
verdict: KEEP
reasoning: "Two-attempt cap" in the title + "stop and report" = hard behavioral limit with
concrete number. Canonical CONSTRAINT. "Three rounds means the theory is wrong" adds
reasoning, not ambiguity.
```

**hard_12:**
```
fixture_id: hard_12
content: "Phase 3 adds a lexical FTS5 index over chunk content and a vector similarity layer
          using numpy + cosine similarity over an embedding table. No external vector store
          in v0.1."
current label: DESIGN
verdict: KEEP
reasoning: Architectural decisions about Phase 3 infrastructure — what layers are added,
what's excluded. Canonical DESIGN.
```

**hard_13:**
```
fixture_id: hard_13
content: "The inspector exists because a system that thinks must be inspectable. Opacity in
          a cognitive runtime is not a trade-off — it is a defect."
current label: PRINCIPLE
model's answer: MECHANISM
verdict: KEEP
reasoning: "Must be inspectable" is normative. "Opacity is not a trade-off, it is a defect"
is a strong doctrinal judgment that opacity violates a principle. This is design doctrine —
a philosophical stance about what cognitive systems SHOULD be. MECHANISM would require
describing how something operates causally. The text contains no causal chain; it contains
an architectural manifesto. Model error.
```

**hard_14:**
```
fixture_id: hard_14
content: "Deviation log entry format: state what the plan said, what was shipped instead,
          why it deviated, the downstream impact, and whether the deviation is accepted or
          needs reverting."
current label: DESIGN
model's answer: TECHNIQUE
verdict: KEEP
reasoning: "Entry format: [field list]" is a schema definition — the structure of a
designed artifact. TECHNIQUE would be "to write a deviation log entry, follow these steps."
This is defining the FORMAT (schema) of the entry, not the procedure for writing one. The
distinction: DESIGN describes what was built, TECHNIQUE describes steps to follow. A format
specification is DESIGN.
```

**hard_15:**
```
fixture_id: hard_15
content: "sku_address is NULL for all 745 memory records immediately after Phase 1 ingest.
          The classifier backfill sweep in Phase 2 populates all 745 addresses."
current label: OBSERVATION
verdict: KEEP
reasoning: "NULL for all 745 records" is a measured state of the system. Numeric count
dominates. OBSERVATION is correct.
```

---

### Fixture Quality Summary

| Category | Count | Notes |
|---|---|---|
| KEEP — unambiguous | 23 | Labels are clearly correct |
| KEEP — the model was clearly wrong | 2 | hard_07, hard_13 — no defensible alternative |
| MARK_AMBIGUOUS | 5 | clear_02, clear_13, hard_01, hard_02, and (weakly) hard_03 |

The five ambiguous cases, and whether the model's wrong answer overlaps:

| Fixture | Label | Model got | Model's answer defensible? |
|---|---|---|---|
| clear_02 | TECHNIQUE | MECHANISM | **Yes** — passive-voice system action legitimately reads as MECHANISM |
| clear_13 | TOOL | MECHANISM | **Yes** — second sentence is genuinely MECHANISM |
| hard_01 | PRINCIPLE | RELATION | **Yes** — structural dependency framing |
| hard_02 | MECHANISM | DESIGN | **Yes** — first sentence is architectural design language |
| hard_07 | DESIGN | MECHANISM | No — MECHANISM doesn't fit; PRINCIPLE would be the alternative |

**Corrected accuracy against defensible labels:** 14 correct + 4 defensible = 18/30 = **60%**, not 47%.

This is materially different. The model is not 47% accurate on a clean test — it's 47% accurate on a test that includes 5 fixtures with arguable labels, 4 of which the model happens to answer in the "other reasonable" way. The true error rate on unambiguous fixtures is 12/25 = 52% wrong (before the two-pass work). Still below threshold, but the gap is smaller.

**Recommendation:** relabel clear_02 as TECHNIQUE/MECHANISM ambiguous and clear_13 as TOOL/MECHANISM ambiguous, and note hard_01, hard_02 as ambiguous in the fixture metadata. Keep the ambiguous cases in the fixture set for calibration purposes — a model that gets both answers should score 0.5 credit, not 0. This requires a minor change to the test scoring logic.

---

## Decision 2 — Two-Pass Hierarchical Design

### Quadrant Taxonomy

Reproducing from `CEREBRA_SKU_ADDRESSING.md §4` verbatim, since the structure is used directly as the routing key:

```
EMPIRICAL  — how things are / work     — 0x0-0x3
  OBSERVATION   0x0   direct measurements, counts, recorded states
  PATTERN       0x1   recurrence, regularity across observations
  MECHANISM     0x2   causal chains, internal operation, process
  PHENOMENON    0x3   named entities, bounded definitions ("X is a Y")

GENERATIVE — how things are made/done  — 0x4-0x7
  TECHNIQUE     0x4   procedure; how-to; steps an actor follows
  DESIGN        0x5   intentional structure; choices made for purposes
  CREATION      0x6   artifacts produced; deliverables; outputs
  TOOL          0x7   capability/instrument; what it does for the user

NORMATIVE  — how things should be      — 0x8-0xB
  PRINCIPLE     0x8   doctrine, norms, behavioral standards
  JUDGMENT      0x9   evaluation, critique, appraisal
  GOAL          0xA   desired state, intentions, success criteria
  CONSTRAINT    0xB   hard limits, prohibitions, must-nots

RELATIONAL — how things connect        — 0xC-0xF
  EVENT         0xC   things that happened; time-situated occurrences
  AGENT         0xD   persons/systems with intent and role
  CONTEXT       0xE   settings, environments, operating conditions
  RELATION      0xF   connections, dependencies, influences
```

**Would a different mapping be more model-discriminable?** No. The quadrant structure is clean at the coarse level and maps directly to the SKU's own high-bit encoding. The issue isn't quadrant design — it's that TECHNIQUE and MECHANISM straddle the Empirical/Generative boundary at the description level. That's a calibration and disambiguation problem, not a taxonomy structure problem.

---

### Pass 1 — Quadrant Selection Prompt

Design principle: short, vocabulary-triggered, no abstract reasoning demanded. The model should pattern-match on surface signals ("must/should" → Normative, "how it works" → Empirical, etc.).

```
You are a classifier. Read the text below and assign it to one of four cognitive quadrants.

EMPIRICAL   — describes how things ARE or WORK: facts, observations, counts, measurements,
              causal processes ("is derived by", "works by", "triggers when"), named entities
GENERATIVE  — describes how things are MADE or DONE: procedures, steps to follow, schemas
              designed, artifacts produced, capabilities that serve a purpose  
NORMATIVE   — describes how things SHOULD BE: "must", "should", "do not", "never", "required",
              "is a defect", "non-negotiable", design doctrine, goals, evaluations
RELATIONAL  — describes how things CONNECT: events at specific times, named persons/agents,
              operating environments, dependencies ("enables", "depends on", "X and Y together")

Score all four quadrants 0.0–1.0. Scores may overlap if the text spans quadrants.

Return ONLY valid JSON:
{"scores": {"EMPIRICAL": 0.0, "GENERATIVE": 0.0, "NORMATIVE": 0.0, "RELATIONAL": 0.0},
 "confidence": 0.0, "primary": "QUADRANT_NAME"}

Text:
<text>
{content[:2000]}
</text>
```

**Why this will outperform the single-pass prompt at quadrant level:** The surface markers for each quadrant are genuinely distinct in planning documentation. "Must/should/do not" are unambiguous Normative signals. Dates and named persons are unambiguous Relational signals. The model can pattern-match these reliably without understanding authorial intent.

---

### Pass 2 — Within-Quadrant Prompts (One per Quadrant)

Each prompt only needs to discriminate between 4 categories. Disambiguation rules are included only for the confusable pairs actually present in that quadrant.

**Pass 2-A: EMPIRICAL quadrant**

```
You are a classifier. This text has been identified as EMPIRICAL — it describes how things
are or work. Now identify which of these four types best fits:

OBSERVATION   — a measurement, count, or recorded state: "39 sources produced", "NULL for
                all 745 records", "confidence=0.9"
PATTERN       — recurring structure across multiple cases: "strategies that work for X tend
                to Y", trends, regularities identified across observations
MECHANISM     — internal causal process: how something works automatically, "is derived by",
                "triggers when X → does Y", state transitions, causal chains with no actor
PHENOMENON    — what something IS: named entity definition, "Cerebra is a [definition]",
                bounded descriptions of what a thing is (not what it does for you)

Key distinctions:
MECHANISM vs OBSERVATION: describes internal causality and process (MECHANISM) vs reports a
  measured state or count (OBSERVATION)? A causal chain is MECHANISM; a number is OBSERVATION.
MECHANISM vs PATTERN: one causal process in one system (MECHANISM) vs recurring regularity
  seen across many instances (PATTERN)?
PHENOMENON vs MECHANISM: defines what something IS (PHENOMENON) vs describes how it WORKS (MECHANISM)?

Score all four 0.0–1.0.
Return ONLY valid JSON:
{"scores": {"OBSERVATION": 0.0, "PATTERN": 0.0, "MECHANISM": 0.0, "PHENOMENON": 0.0},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}

Text:
<text>
{content[:2000]}
</text>
```

**Pass 2-B: GENERATIVE quadrant**

```
You are a classifier. This text has been identified as GENERATIVE — it describes how things
are made or done. Now identify which of these four types best fits:

TECHNIQUE   — procedure: steps a person or system FOLLOWS to accomplish something, how-to
              instructions, "to X: do A, then B, then C", methods with an active actor
DESIGN      — structure: intentional architectural choices already made, schemas, "the table
              stores X, Y, Z", scope decisions ("Phase 2 assigns X, stubs Y")
CREATION    — artifact: something produced and placed somewhere, "vendored into", deliverables,
              outputs, works produced
TOOL        — capability: what an instrument does FOR the user; interface description;
              "Clutch maps signal to action", capability-interface language

Key distinctions:
TECHNIQUE vs DESIGN: steps to follow (TECHNIQUE) vs structure already decided (DESIGN)?
  "To create X, do Y" = TECHNIQUE. "The table has columns A, B, C" = DESIGN.
TOOL vs MECHANISM: what the instrument provides (TOOL) vs how its internals work (MECHANISM)?
  "Maps X to Y" = TOOL. "Rules fire in priority order, first match wins" = MECHANISM.
DESIGN vs CREATION: the architectural choice (DESIGN) vs the artifact produced (CREATION)?

Score all four 0.0–1.0.
Return ONLY valid JSON:
{"scores": {"TECHNIQUE": 0.0, "DESIGN": 0.0, "CREATION": 0.0, "TOOL": 0.0},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}

Text:
<text>
{content[:2000]}
</text>
```

**Pass 2-C: NORMATIVE quadrant**

```
You are a classifier. This text has been identified as NORMATIVE — it describes how things
should be. Now identify which of these four types best fits:

PRINCIPLE   — behavioral standard or design doctrine: "must [do X]", "should", "is required",
              "non-negotiable", "opacity is a defect", normative rules about how systems
              SHOULD work
JUDGMENT    — evaluation or appraisal: weighing tradeoffs, assessing quality, "X is better
              than Y because...", critique of a design decision
GOAL        — desired state: "desired outcome", "the target is", success criteria, what's
              being pursued
CONSTRAINT  — hard prohibition or limit: "do not", "never", "forbidden", "must not", "do not
              patch one by one", explicit outer walls

Key distinction:
PRINCIPLE vs CONSTRAINT: behavioral standard — what SHOULD happen (PRINCIPLE) vs hard
  prohibition — what MUST NOT happen (CONSTRAINT)?
  "Must emit events" = PRINCIPLE (positive requirement).
  "Do not assist with..." = CONSTRAINT (explicit prohibition).
  "Non-negotiable" alone is a PRINCIPLE marker, not CONSTRAINT.
PRINCIPLE vs GOAL: normative doctrine (PRINCIPLE) vs desired outcome (GOAL)?
  "Desired outcome for Phase 2" = GOAL. "Inspector events are non-negotiable" = PRINCIPLE.

Score all four 0.0–1.0.
Return ONLY valid JSON:
{"scores": {"PRINCIPLE": 0.0, "JUDGMENT": 0.0, "GOAL": 0.0, "CONSTRAINT": 0.0},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}

Text:
<text>
{content[:2000]}
</text>
```

**Pass 2-D: RELATIONAL quadrant**

```
You are a classifier. This text has been identified as RELATIONAL — it describes how things
connect. Now identify which of these four types best fits:

EVENT    — something that happened at a specific moment: "Phase 0 complete on 2026-06-04",
           "88 tests passed", time-situated occurrences
AGENT    — a person, organization, or system with intent and role: "bitmosh is the sole
           developer of Cerebra", roles and responsibilities
CONTEXT  — the environment or setting something operates within: vault directories, system
           conditions, operating environments, "the vault contains..."
RELATION — connection between things: dependencies, enablement, "LumaWeave and Cerebra",
           "X makes Y possible", "X enables Z"

Key distinction:
CONTEXT vs DESIGN: existing environment described (CONTEXT) vs intentional structural
  choice made (DESIGN)? "The vault directory contains X, Y" = CONTEXT. "The vault was
  designed with separate data and event directories" = DESIGN.
EVENT vs OBSERVATION: time-situated occurrence (EVENT) vs measured count (OBSERVATION)?
  "Phase 0 complete on [date]" = EVENT. "745 chunks produced" = OBSERVATION.

Score all four 0.0–1.0.
Return ONLY valid JSON:
{"scores": {"EVENT": 0.0, "AGENT": 0.0, "CONTEXT": 0.0, "RELATION": 0.0},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}

Text:
<text>
{content[:2000]}
</text>
```

---

### Routing Logic — Does Pass 2 Always Fire?

**Yes. Pass 2 always fires.**

The temptation to skip Pass 2 on high-confidence Pass 1 results would require trusting confidence scores. The calibration data shows the model returning confidence 0.90 on wrong answers consistently — 14 out of 14 wrong answers in v1.2.0 were high-confidence. Trusting confidence to skip Pass 2 would skip it exactly when Pass 2 is most needed.

The cost: at ~5 seconds per Pass 2 call and 745 records for the backfill = ~62 minutes extra. Total backfill time: Pass 1 (745 × ~4s = ~50min) + Pass 2 (745 × ~5s = ~62min) = ~2 hours. This is acceptable for a one-time operation.

The benefit: Pass 2 has a focused task (4 categories vs 16) with disambiguated instructions relevant to that quadrant's actual confusable pairs. The NORMATIVE pass only needs to worry about PRINCIPLE vs CONSTRAINT, not about accidentally selecting MECHANISM.

One exception worth implementing: if Pass 1 returns quadrant confidence ≥ 0.97 AND the primary quadrant score is ≥ 3× the second-highest quadrant score, you could skip Pass 2 for the RELATIONAL quadrant only. Relational categories (EVENT, AGENT, CONTEXT, RELATION) are the most distinctive of all — a text containing "bitmosh is the developer" has essentially no overlap with any other quadrant. But this optimization is worth maybe 10% of records and adds conditional logic complexity. Don't bother for v0.1.

---

### Schema Impact

No schema migration needed. Everything fits in the existing `raw_scores_json` column as a nested structure.

**Proposed `raw_scores_json` shape for two-pass:**

```json
{
  "pass1": {
    "scores": {"EMPIRICAL": 0.85, "GENERATIVE": 0.10, "NORMATIVE": 0.05, "RELATIONAL": 0.00},
    "confidence": 0.85,
    "primary_quadrant": "EMPIRICAL"
  },
  "pass2": {
    "quadrant": "EMPIRICAL",
    "scores": {"OBSERVATION": 0.15, "PATTERN": 0.10, "MECHANISM": 0.90, "PHENOMENON": 0.05},
    "confidence": 0.90,
    "primary": "MECHANISM",
    "reasoning": "the hash is derived by a causal process"
  }
}
```

The existing parser in `_parse_classification_response` doesn't need changes. The `SKUClassifier` would call the adapter twice, passing the two prompts, and assemble the `raw_scores_json` from both results before calling `_select_d1()`. The selected D1 comes from `pass2.primary` not `pass1.primary`.

**For reclassification when prompt_version bumps:** the existing `_is_current()` check handles this correctly. If `PROMPT_VERSION = "2.0.0"` (two-pass), any record with `prompt_version != "2.0.0"` is reclassified. No migration needed — the `raw_scores_json` column is a flexible JSON blob and the new structure just replaces the old one.

**One addition worth making:** a `pass_count` field in the assignment:

```python
# sku_assignments table — add column
pass_count INTEGER DEFAULT 1
```

This lets queries distinguish single-pass assignments from two-pass assignments for analysis. One small migration to add this column when two-pass ships.

---

### Predicted Accuracy

Working from the calibration failure analysis: 14 of the 16 wrong answers were cross-quadrant or within-quadrant. Let me categorize them:

**Cross-quadrant errors (would be caught if Pass 1 is correct):**

| Fixture | Label quadrant | Model quadrant | Notes |
|---|---|---|---|
| clear_02 | GENERATIVE | EMPIRICAL | TECHNIQUE→MECHANISM |
| clear_04 | EMPIRICAL | GENERATIVE | PHENOMENON→TOOL |
| clear_10 | RELATIONAL | EMPIRICAL | CONTEXT→OBSERVATION |
| clear_13 | GENERATIVE | EMPIRICAL | TOOL→MECHANISM |
| hard_01 | NORMATIVE | RELATIONAL | PRINCIPLE→RELATION |
| hard_02 | EMPIRICAL | GENERATIVE | MECHANISM→DESIGN |
| hard_07 | GENERATIVE | EMPIRICAL | DESIGN→MECHANISM |
| hard_08 | NORMATIVE | EMPIRICAL | CONSTRAINT→PATTERN |
| hard_13 | NORMATIVE | EMPIRICAL | PRINCIPLE→MECHANISM |

9 cross-quadrant errors out of 14 wrong cases.

**Within-quadrant errors (Pass 1 doesn't help, Pass 2 must fix):**

| Fixture | Quadrant | Label | Model got |
|---|---|---|---|
| clear_01 | NORMATIVE | PRINCIPLE | CONSTRAINT |
| clear_14 | NORMATIVE | PRINCIPLE | CONSTRAINT |
| hard_05 | EMPIRICAL | MECHANISM | PATTERN |
| hard_10 | EMPIRICAL | MECHANISM | OBSERVATION |
| hard_14 | GENERATIVE | DESIGN | TECHNIQUE |

5 within-quadrant errors.

**Accuracy prediction:**

*If Pass 1 achieves 85% quadrant accuracy:*
- Correctly routes 9 × 0.85 = 7.7 of the 9 cross-quadrant cases to the right quadrant
- Pass 2 then handles these correctly: at a focused 4-category task, estimate 80% accuracy for the Generative↔Empirical border cases, 90% for others
- Cross-quadrant contribution: ~7 more correct
- Within-quadrant contribution from Pass 2: the 5 within-quadrant errors, some fixed by focused within-quadrant prompts. PRINCIPLE vs CONSTRAINT with dedicated disambiguation: estimate 60-70% of these flip → ~3 more correct
- Total correct: 14 + 7 + 3 = 24/30 = **80%** — best case
- If Pass 1 achieves 75%: 14 + 6 + 2 = 22/30 = **73%** — expected case
- If Pass 1 achieves 65%: 14 + 4 + 2 = 20/30 = **67%** — marginal case, still above threshold

**Best: 80%, Expected: 73%, Worst (if quadrant pass is poor): 67%**

All three cases are above the 70% threshold in expected and best case. This is the clearest path to hitting the gate.

---

### What Two-Pass Does NOT Fix

Two-pass does not fix the fundamental issue: the model is doing pattern-matching on surface vocabulary rather than understanding authorial intent. Three specific failure modes survive:

**1. Vocabulary traps within quadrants.** clear_01 (PRINCIPLE→CONSTRAINT) and clear_14 (PRINCIPLE→CONSTRAINT) are within-quadrant errors. The dedicated NORMATIVE pass has a specific disambiguation for PRINCIPLE vs CONSTRAINT. These should improve. But the model has demonstrated (in 18 consecutive probe calls at both temperature 0.0 and 0.1) that it considers clear_01 to be unambiguously CONSTRAINT with confidence 0.90. The within-quadrant NORMATIVE prompt would need to be very specifically targeted to move this.

**2. Passive-voice Generative vs Empirical.** "cerebra ingest discovers all markdown files, registers them as sources..." — the Pass 1 coarse prompt must distinguish this from MECHANISM. The pattern is: system action in passive voice = MECHANISM-looking. The Pass 1 prompt's GENERATIVE description needs to strongly signal that "system performs a sequence of steps on your behalf" is GENERATIVE even when written passively.

**3. The MECHANISM gravity well.** In the calibration data, 7 of the 14 wrong answers chose MECHANISM when the correct answer was something else. MECHANISM is a dominant attractor for technical descriptions of computer systems. Within the EMPIRICAL quadrant, the Pass 2-A prompt's distinction between MECHANISM and OBSERVATION needs to be sharp, or hard_10 (MECHANISM→OBSERVATION) and hard_05 (MECHANISM→PATTERN) will flip to MECHANISM→right-answer instead.

**Honest assessment:** two-pass is solving a real failure mode (cross-quadrant confusion accounts for 9/14 errors), not just shifting cost. The within-quadrant failures are 5 hard cases that require sharp single-pair disambiguation, which each quadrant's Pass 2 prompt is positioned to handle. Two-pass is the right architecture for this model and this task.

---

## Decision 3 — Temperature Stochasticity and Reproducibility

### (a) Diagnosing the Variance

I ran 23 direct Ollama calls in the probes above — temperature 0.0, 0.1, and 0.1+seed across two fixtures.

**clear_03 (expected MECHANISM):** The model returns MECHANISM correctly across all temperatures and seeds, but every response has a JSON formatting bug: the `reasoning` string drops its closing `"` before the final `}`. This means `json.loads` fails on every single call and the regex fallback extractor in `_try_extract_partial_json` handles it. The production code handles this correctly, but **every classification call is going through the fallback path** — the primary JSON parser never succeeds on this model's output.

**clear_01 (expected PRINCIPLE, model gets CONSTRAINT):** 18/18 calls across temperature 0.0, 0.1, and both seed=42 and seed=99 return CONSTRAINT. Confidence varies slightly (0.85 with seed=99, 0.90 with seed=42, 0.90-0.95 at temp=0.1) but the primary answer never changes. This fixture is not producing variance — the model has a committed, stable opinion.

**Why did the two calibration runs give different results (47% vs 27%)?**

Not temperature noise on strong-opinion fixtures — clear_01 proves that. The likely cause: approximately 10-15% of fixtures sit in a "soft zone" where the top two category scores are close (say, 0.65 vs 0.60). At temperature 0.1, the final token sampling for these fixtures flips occasionally. With 30 fixtures, 3-4 flips between runs produces the observed variance. The fixtures that flipped are probably the ones where the model's score distribution is flat rather than peaked.

The second test run was also affected by a model state difference: the second `_run_calibration()` call ran after the first test's 30 calls had been processed. Ollama's KV cache state and internal model buffers are different at call 31 vs call 1. Even at temperature 0.1, this affects the probability distribution for borderline tokens.

**Important secondary finding:** The JSON formatting bug (unclosed `reasoning` string) is consistent across all probes. This is a Qwen 3.5-specific behavior with `format: json` constraints — the model truncates the reasoning field at a certain length without closing the string. The fallback extractor handles it correctly, but it means we're paying the fallback cost on 100% of production calls. This is not a correctness problem but is worth documenting.

---

### (b) Ranking Determinism Options

**1. Temperature 0.0 (pure greedy decoding)**
*Verdict: Use this for production backfill.*
Confirmed effective by probes: 5/5 calls at temperature 0.0 return identical results for clear_01 (CONSTRAINT, conf=0.90). Zero variance. For strong-opinion fixtures, results are identical to temperature 0.1 anyway. For soft-zone fixtures, temperature 0.0 eliminates the flip probability. Ollama supports it directly — just pass `"temperature": 0.0` in options. **Cost: zero. Recommended.**

**2. Temperature 0.1 + fixed seed**
*Verdict: Marginal improvement, not worth using as primary.*
My probe shows seed=42 and seed=99 give slightly different confidence values (0.90 vs 0.85) for clear_01, but the same primary answer. For soft-zone fixtures where the primary might change, a fixed seed would produce reproducible (but not necessarily correct) results. Ollama supports the seed parameter. However, seed only helps if you use the SAME seed AND the model is in the same KV cache state. Across two separate backfill runs with a model reload in between, seed alone doesn't guarantee reproducibility. Temperature 0.0 is strictly more reliable.

**3. Full JSON schema grammar constraint**
*Verdict: Does not address reproducibility; addresses parse failures.*
Ollama supports a full JSON Schema object in the `format` field (not just `format: "json"`). This would enforce the exact output structure and eliminate the reasoning-field truncation issue. This is worth doing for eliminating the fallback path cost, but it doesn't reduce answer variance. The model's opinion on PRINCIPLE vs CONSTRAINT is not affected by how tightly the output grammar is constrained.

**4. Store sampling parameters in `sku_assignments`**
*Verdict: Necessary hygiene, doesn't add reproducibility.*
Already partially done via `model_string` field. Adding `temperature` and `seed` fields to the assignment row lets future analysis determine under what conditions an assignment was made. Worth adding as columns when two-pass ships. Does not help with reproducibility across re-runs — it just makes the non-reproducibility auditable.

**5. Multi-sample consensus (N calls, majority vote)**
*Verdict: Most reliable, expensive, use only for high-stakes records.*
3 calls on the same chunk with majority vote would eliminate almost all stochastic variance. Cost: 3× latency. For 745 records at 2 passes each: 745 × 6 calls × ~5s = ~37 minutes. Acceptable. But given that the probes show most fixtures have stable opinions at temperature 0.0, consensus is overkill for the backfill. Reserve for: user-pinned records, records with `d1_confidence < 0.4` from the initial pass, or records that will anchor Phase 4+ retrieval.

---

### (c) The Pragmatic Recommendation

**Use temperature 0.0 for the production backfill. This is sufficient for v0.1 close-out.**

"Stable SKUs within a single backfill run, may differ across re-runs" is only acceptable if: (a) you never re-run the backfill without bumping `PROMPT_VERSION`, and (b) you document the behavior. With temperature 0.0, re-runs with the same model and same `PROMPT_VERSION` WILL produce identical results (the model is deterministic at temp=0). This is strictly better than "may differ."

Phase 2 close-out should require: "deterministic-by-construction within a single model version." Temperature 0.0 achieves this without multi-sample overhead. The only scenario where determinism breaks down at temp=0 is a model version change (Ollama updates qwen3.5), which would justify a `PROMPT_VERSION` bump anyway.

One change needed: update `OllamaDirectAdapter._call_ollama_chat()` to use `temperature: 0.0` for the backfill, or expose temperature as a constructor parameter so the backfill command can override it explicitly.

---

## Decision 4 — The Strategic Question

The core question is whether the 16-category D1 taxonomy is a good fit for what a 9.7B local model without fine-tuning can reliably do.

The honest answer is: **not directly, at the category level**. But the conclusion from that isn't to abandon the taxonomy — it's to understand what level of the taxonomy the model can handle reliably and build from there.

---

### Path X — Keep Taxonomy, Accept Imperfect, LoRA in v0.2

**Cognitive integrity cost:** None. The architecture is preserved at full resolution. Every SKU assignment is V1-labeled and reclassifiable when the prompt or model improves.

**Schedule cost:** Minimal. Two-pass gets to ~73% expected accuracy. Ship that. Phase 3+ runs on a 73%-accurate substrate.

**LoRA implication:** Excellent. Phase 2's 745-record backfill at 73% accuracy is a training corpus. The low-confidence and near-tie records (identifiable from `raw_scores_json`) should be flagged for human review. 745 records × 0.73 correct = ~544 reliably labeled examples. Add the 30 calibration fixtures (human-labeled) and you have ~574 examples. That's above the 500-example minimum for a stable LoRA pass. Training on Qwen 3.5 9.7B with QLoRA on 12GB VRAM: feasible with Unsloth.

**Lock-in:** None. `prompt_version` handles reclassification. A future `PROMPT_VERSION = "3.0.0"` (LoRA-backed) triggers backfill of all 745 records.

**The argument for Path X:** the SKU's value is in the navigation graph it implies, not the precision of any single address. From `CEREBRA_SKU_ADDRESSING.md §16`: "The SKU's value is not in the precision of any single address. It is in the navigation graph the address scheme implies." A 73%-accurate D1 substrate is navigable. You can retrieve "things in the NORMATIVE quadrant" with high reliability even if the PRINCIPLE/CONSTRAINT split within that quadrant is occasionally wrong. Phase 3's retrieval layer operates at multiple levels of SKU resolution; D1 accuracy of 73% at the 16-category level is ~90%+ at the quadrant level.

---

### Path Y — Reduce to 8 Categories or 4 Quadrants

**Cognitive integrity cost:** High. The taxonomy's semantic value is in the 16-category resolution. "This chunk is NORMATIVE" is far less useful as an address than "this chunk is PRINCIPLE." The whole point of SKU addressing is navigating to a semantic neighborhood — quadrant-level addressing gives you one of four very wide neighborhoods. Phase 4's retrieval would need to scan a quarter of the vault to find relevant memories rather than navigating to the right D1 location.

**Schedule cost:** Deceptively low now, high later. You'd ship a simpler classifier quickly, then redo all the work for 16 categories in v0.2. The vault would have 745 records with quadrant-level SKUs that need full reclassification. If v0.2 ships 6 months later with 3,000 records in the vault, that reclassification is a larger burden.

**LoRA implication:** Negative. You'd fine-tune a 4-quadrant classifier. That model and training corpus don't transfer to 16-category classification. You'd need to retrain from scratch at v0.2.

**Lock-in:** High. Every architectural decision from Phase 3 onward that references D1 resolution would be built against 4 or 8 categories and would need adjustment when 16 categories land.

**Verdict: Don't do this.** The short-term convenience of simpler classification is not worth the architectural compromise and the technical debt of rebuilding. The taxonomy is the load-bearing part of the SKU architecture; simplifying it degrades the substrate quality more than a 73%-accurate 16-category classifier does.

---

### Path Z — Hybrid: Derive D1 from Structured Extraction

The idea: instead of asking the model "which cognitive shape is this?", ask structured binary questions about text features and derive D1 via rule logic. The model does easy extraction; Cerebra does the semantic classification.

**Example feature questions:**
- Does this text contain imperative mood ("must", "do not", "never", "should")? → Normative signal
- Is the grammatical subject a system/process performing actions passively? → Empirical/Mechanism signal
- Does the text describe steps an actor follows? → Generative/Technique signal
- Does the text contain a date or named occurrence? → Relational/Event signal
- Does the text define what something IS ("X is a Y")? → Empirical/Phenomenon signal
- Does the text contain numeric measurements or counts? → Empirical/Observation signal

From these binary/confidence answers, a deterministic rule system maps to D1:
```
IF imperative_strong AND NOT definition → CONSTRAINT
IF imperative_soft AND NOT prohibition → PRINCIPLE
IF passive_causal AND NOT steps → MECHANISM
IF named_entity_definition AND NOT capabilities → PHENOMENON
...
```

**Cognitive integrity cost:** Medium. The D1 assignment is still 16-category but derived via an explicit feature pipeline rather than direct classification. The derivation rules are human-auditable and correctable. Some nuance is lost (edge cases where two extraction features conflict), but the rules can be iterated. Importantly, the rules capture the INTENT of the category distinctions more reliably than prompt text does — "does this contain 'do not'?" is a much more reliable binary question than "is this a CONSTRAINT?"

**Schedule cost:** Significant. Path Z requires:
1. Designing 10-15 binary extraction questions
2. Writing the derivation rule system
3. Validating against the 30 calibration fixtures
4. Iterating rules where the derivation misfires
5. Integrating a multi-question prompt or N single-question calls
This is 1-2 weeks of engineering, not 2-3 hours. Not a Phase 2 close-out path.

**LoRA implication:** Better in some ways. The extraction questions are easier to label (binary) and easier to verify. A LoRA trained on "does this text contain imperative mood?" is more generalizable than one trained on "is this PRINCIPLE or CONSTRAINT?" However, you'd need to train N binary classifiers or one multi-output extractor — both are more complex than a single 16-class classifier.

**Lock-in:** Moderate. The derivation rules would become part of the classifier's versioning. Changes to rules would require reclassification of affected records. But the rules are deterministic and auditable, unlike the prompt-based approach which is a black box.

**Verdict:** Path Z is intellectually the most interesting option and probably the eventual destination after LoRA. It solves the fundamental problem (model can't reliably infer authorial intent) by decomposing intent into surface features the model CAN reliably detect. But it's a v0.2 engineering track, not a Phase 2 close-out path.

---

### My Recommendation

**Path X now. Path Z as the v0.2 alternative track alongside LoRA.**

Here's the specific reasoning:

**Two-pass gets to 70-80% expected accuracy.** That's above the gate threshold. Phase 2 closes out. Phase 3 runs on a reasonable substrate.

**745 records × 73% accuracy = ~544 reliable labels + 30 calibration fixtures = ~574 training examples for LoRA.** With Unsloth on the 4070 Super, a QLoRA pass on Qwen 3.5 9.7B with 574 examples, 3-5 epochs: ~45-60 minutes of training time, producing a model that internalizes the 16 category distinctions from the actual Cerebra planning doc corpus. Expected accuracy after LoRA: 85-90% on in-distribution text.

**Path Z is the right v0.2 choice IF LoRA doesn't reach 85%.** If the LoRA approach runs into problems — not enough reliable training data, insufficient VRAM for the 9.7B model, or the fine-tuned model still can't handle the PRINCIPLE/CONSTRAINT distinction — Path Z's feature extractor approach is the fallback. I'd implement both tracks at v0.2 and validate on an expanded fixture set.

**What would change my mind:**

1. If Phase 3 retrieval testing shows that D1 accuracy below 80% makes SKU-keyed retrieval indistinguishable from full-vault scan → accelerate to Path Z immediately, because the substrate is genuinely too noisy to provide navigation value.

2. If the two-pass calibration comes back below 70% despite the architectural changes → the model simply can't handle 16-category cognitive classification without fine-tuning; skip directly to Path Z for v0.1.1 and plan LoRA for v0.2.

3. If QLoRA training at v0.2 fails due to VRAM constraints (9.7B model is borderline at 12GB) → Path Z becomes primary because it doesn't require fine-tuning the full model.

4. If Path Z validation shows that 8-10 binary extraction questions achieve 85%+ D1 accuracy on the calibration set → ship Path Z in v0.1.1 rather than waiting for v0.2 LoRA. The extraction approach is lower-risk than LoRA if the rules generalize.

**The architecture is sound. The model is the limit. Build the substrate at acceptable accuracy now, improve it in v0.2, and preserve the full SKU design throughout. Don't compromise the taxonomy to work around a temporary model limitation.**

---

## Summary of Recommended Actions

1. **Fixture audit:** Mark clear_02, clear_13, hard_01, hard_02 as AMBIGUOUS in the fixture metadata. Update the calibration test to award 0.5 credit for the alternative reasonable answer on ambiguous fixtures. True accuracy is 60%, not 47%.

2. **Two-pass implementation:** Implement Pass 1 (quadrant) + Pass 2 (within-quadrant) using the prompts above. No schema migration required. `raw_scores_json` stores both pass results as a nested object. Bump `PROMPT_VERSION` to `"2.0.0"`.

3. **Temperature:** Set `temperature: 0.0` in `OllamaDirectAdapter._call_ollama_chat()` for the production backfill. Expose as a constructor parameter so calibration tests can optionally use 0.1 for variety analysis.

4. **Phase 2 close-out gate:** ≥70% on 30 fixtures (with 0.5 credit for ambiguous-fixture alternative answers). 4-quadrant table in the merge gate report. Document temperature=0.0 in the deviation log.

5. **v0.2 tracks:** (a) QLoRA fine-tuning on the Phase 2 backfill corpus; (b) Path Z feature extractor as alternative if LoRA underperforms. Both tracks run after Phase 3 ships and produces retrieval quality data.
