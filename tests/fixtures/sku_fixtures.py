"""
30-fixture calibration set for D1 SKU classification.

15 CLEAR cases: 5/5 humans would agree on D1.
15 HARD cases: humans would split 3/2; marked with ambiguous_with.

All content drawn from Cerebra planning docs (the actual corpus being classified).
Hard cases are marked in tests to track separately from clear-case accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass

from cerebra.cognition.sku_categories import D1Category


@dataclass
class SKUFixture:
    fixture_id: str
    content: str
    expected_d1: D1Category
    difficulty: str  # "clear" or "hard"
    ambiguous_with: D1Category | None  # the other reasonable D1 for hard cases
    notes: str


SKU_FIXTURES: list[SKUFixture] = [
    # ── Clear cases ───────────────────────────────────────────────────────────
    SKUFixture(
        fixture_id="clear_01",
        content=(
            "Every cognitive action must emit a structured inspector event at write time. "
            "Silent code is incomplete code. Inspector events are non-negotiable."
        ),
        expected_d1=D1Category.PRINCIPLE,
        difficulty="clear",
        ambiguous_with=None,
        notes="Strong normative 'must' + 'non-negotiable' language. PRINCIPLE is unambiguous.",
    ),
    SKUFixture(
        fixture_id="clear_02",
        content=(
            "cerebra ingest <path> discovers all markdown and text files under the target directory, "
            "registers them as sources, parses each, chunks the content, and writes memory records."
        ),
        expected_d1=D1Category.TECHNIQUE,
        difficulty="ambiguous",
        ambiguous_with=D1Category.MECHANISM,
        notes=(
            "Procedural description of cerebra ingest. TECHNIQUE-as-described, but the passive-voice "
            "system-action language ('discovers, registers, parses') legitimately reads as MECHANISM "
            "too. Marked ambiguous — both answers defensible."
        ),
    ),
    SKUFixture(
        fixture_id="clear_03",
        content=(
            "content_hash is derived by reading the file in 64KB blocks and feeding each block "
            "to SHA256. The final digest is returned as a lowercase hex string."
        ),
        expected_d1=D1Category.MECHANISM,
        difficulty="clear",
        ambiguous_with=None,
        notes="Causal chain: how the hash is computed. MECHANISM.",
    ),
    SKUFixture(
        fixture_id="clear_04",
        content=(
            "Cerebra is a local-first cognitive runtime. It ingests knowledge sources, "
            "classifies memory, and provides structured retrieval for reasoning cycles."
        ),
        expected_d1=D1Category.PHENOMENON,
        difficulty="clear",
        ambiguous_with=None,
        notes="Named entity with bounded definition. 'What Cerebra is.' PHENOMENON.",
    ),
    SKUFixture(
        fixture_id="clear_05",
        content=(
            "Do not assist with creating weapons capable of mass casualties, "
            "biological agents, chemical weapons, or any action that would harm large populations."
        ),
        expected_d1=D1Category.CONSTRAINT,
        difficulty="clear",
        ambiguous_with=None,
        notes="Hard prohibition. 'Do not' + list of banned actions. CONSTRAINT.",
    ),
    SKUFixture(
        fixture_id="clear_06",
        content=(
            "bitmosh is the sole developer of Cerebra. The project is a solo exploration "
            "of cognitive architecture with no team dependencies."
        ),
        expected_d1=D1Category.AGENT,
        difficulty="clear",
        ambiguous_with=None,
        notes="Person with role and intent. AGENT.",
    ),
    SKUFixture(
        fixture_id="clear_07",
        content=(
            "The sku_assignments table stores: assignment_id (PK), record_id (FK), "
            "sku_address, d1 through d10 digit columns, raw_scores_json, classifier_version, "
            "prompt_version, subcategory_strategy_version, model_string, latency_ms."
        ),
        expected_d1=D1Category.DESIGN,
        difficulty="ambiguous",
        ambiguous_with=D1Category.OBSERVATION,
        notes=(
            "DESIGN (schema definition — intentional structure of a data table) vs OBSERVATION "
            "('the table stores X, Y, Z' reads as a factual declaration of what exists). "
            "The 'stores:' + bare enumeration surface gives observational character to a design "
            "artifact. 0/13 models picked DESIGN; 10/13 picked OBSERVATION. Both defensible."
        ),
    ),
    SKUFixture(
        fixture_id="clear_08",
        content=(
            "Tombstoned items do not return on retrieval queries but block re-insertion "
            "of the same item. Once tombstoned, an item stays tombstoned until explicit removal."
        ),
        expected_d1=D1Category.MECHANISM,
        difficulty="clear",
        ambiguous_with=None,
        notes="How tombstoning works operationally — causal: tombstone → blocks retrieval. MECHANISM.",
    ),
    SKUFixture(
        fixture_id="clear_09",
        content=(
            "Desired outcome for Phase 2: every memory record in the vault has a non-null "
            "sku_address. The classifier backfill sweep must leave zero NULL records."
        ),
        expected_d1=D1Category.GOAL,
        difficulty="clear",
        ambiguous_with=None,
        notes="'Desired outcome' + specific success criterion. GOAL.",
    ),
    SKUFixture(
        fixture_id="clear_10",
        content=(
            "The vault directory at ~/cerebra-vaults/dev/ contains: data/ (SQLite database), "
            "artifacts/ (normalized document JSON), events/ (NDJSON inspector logs), "
            "leeway/ (governance YAML), constitutional/ (constitutional rules YAML)."
        ),
        expected_d1=D1Category.CONTEXT,
        difficulty="clear",
        ambiguous_with=None,
        notes="Directory structure — setting/environment in which Cerebra operates. CONTEXT.",
    ),
    SKUFixture(
        fixture_id="clear_11",
        content=(
            "Phase 0 complete at commit 5747c7e on 2026-06-04. "
            "88 tests passed. Repository initialized, governance loaded, "
            "first vault created successfully."
        ),
        expected_d1=D1Category.EVENT,
        difficulty="ambiguous",
        ambiguous_with=D1Category.OBSERVATION,
        notes=(
            "EVENT (time-anchored Phase 0 completion moment) vs OBSERVATION (measurement content: "
            "'88 tests passed' dominates the surface alongside status readouts). First sentence is "
            "unambiguous EVENT; sentences 2-3 are measurement data. 12/13 models picked OBSERVATION. "
            "Both defensible — reading as the event vs reading as the record of the event."
        ),
    ),
    SKUFixture(
        fixture_id="clear_12",
        content=(
            "Six Lattica primitives vendored verbatim into cerebra/_primitives/: "
            "Clutch, SignalTriangulator, TrajectoryTracker, HysteresisModeRouter, "
            "ComponentScoreComposer, TombstoneSet."
        ),
        expected_d1=D1Category.CREATION,
        difficulty="clear",
        ambiguous_with=None,
        notes="Artifacts produced and placed in the codebase. CREATION.",
    ),
    SKUFixture(
        fixture_id="clear_13",
        content=(
            "The Clutch primitive maps signal state to typed action via a "
            "priority-ordered rule cascade. Rules fire in priority order; "
            "the first matching rule wins."
        ),
        expected_d1=D1Category.TOOL,
        difficulty="ambiguous",
        ambiguous_with=D1Category.MECHANISM,
        notes="A capability/instrument used to do something. TOOL (vs MECHANISM which is 'how'). "
        "TOOL is 'what it does for you'; MECHANISM is 'how the internals work'.",
    ),
    SKUFixture(
        fixture_id="clear_14",
        content=(
            "Provenance digit D10 must distinguish synthesized entries from observed entries "
            "at the address level. Without this, the substrate is contaminated."
        ),
        expected_d1=D1Category.PRINCIPLE,
        difficulty="clear",
        ambiguous_with=None,
        notes="Strong normative 'must' + consequence of violation. PRINCIPLE.",
    ),
    SKUFixture(
        fixture_id="clear_15",
        content=(
            "LumaWeave visualizes knowledge graphs; Cerebra produces the cognitive substrate "
            "those graphs run on. One makes, the other thinks about what was made."
        ),
        expected_d1=D1Category.RELATION,
        difficulty="clear",
        ambiguous_with=None,
        notes="Connection between two systems. Dependency/complementarity. RELATION.",
    ),
    # ── Hard cases ────────────────────────────────────────────────────────────
    SKUFixture(
        fixture_id="hard_01",
        content=(
            "The SKU is the substrate that makes everything above it possible. "
            "Get this right and the truth tower, the leeway network, and the dream/retrain "
            "direction all compose cleanly on top of it."
        ),
        expected_d1=D1Category.PRINCIPLE,
        difficulty="hard",
        ambiguous_with=D1Category.RELATION,
        notes=(
            "PRINCIPLE (normative claim about SKU's load-bearing role: 'get this right and...') vs "
            "RELATION (structural dependency framing across components: SKU as substrate for truth "
            "tower, leeway network, dream/retrain). The causal framing tips toward PRINCIPLE but "
            "the dependency-mapping structure makes RELATION defensible."
        ),
    ),
    SKUFixture(
        fixture_id="hard_02",
        content=(
            "The leeway network inverts prohibition models. Instead of specifying what is "
            "forbidden, it specifies what is permitted under what conditions. "
            "Everything outside the network is implicitly disallowed."
        ),
        expected_d1=D1Category.DESIGN,
        difficulty="hard",
        ambiguous_with=D1Category.PRINCIPLE,
        notes=(
            "DESIGN (architectural inversion choice: 'inverts prohibition models' / 'instead of X, "
            "it does Y' is design-decision language) vs PRINCIPLE (normative framing: 'everything "
            "outside is implicitly disallowed' reads as a governance rule). 0/13 models picked old "
            "MECHANISM primary; 1/13 picked DESIGN, 7/13 picked PRINCIPLE. Primary swapped from "
            "MECHANISM to DESIGN (data-driven); ambiguous_with updated from DESIGN to PRINCIPLE."
        ),
    ),
    SKUFixture(
        fixture_id="hard_03",
        content=(
            "When a location saturates — more than 255 entries at a single SKU address — "
            "that is signal that this address is genuinely active and is a candidate for "
            "deeper subdivision via the type-tag axes."
        ),
        expected_d1=D1Category.OBSERVATION,
        difficulty="hard",
        ambiguous_with=D1Category.PATTERN,
        notes="OBSERVATION (a specific threshold event with a concrete trigger) vs PATTERN "
        "(recurrence across many addresses). The 'when X occurs, that is signal' is closer "
        "to observing a condition than identifying a repeating pattern.",
    ),
    SKUFixture(
        fixture_id="hard_04",
        content=(
            "The bandit primitive updates strategy selection weights per query shape over time. "
            "Strategies that work for certain query shapes get higher selection probability. "
            "The system gets better at retrieving over time, not just storing."
        ),
        expected_d1=D1Category.MECHANISM,
        difficulty="hard",
        ambiguous_with=D1Category.TOOL,
        notes="MECHANISM (how the bandit learning works — causal: past performance → weight update "
        "→ higher selection) vs TOOL (bandit as an instrument). The focus is on the learning "
        "process, not on what the bandit does for you.",
    ),
    SKUFixture(
        fixture_id="hard_05",
        content=(
            "Consolidation converts episodic cycle history into durable semantic and procedural "
            "memory. Repeated patterns become compressed representations; "
            "one-off events are allowed to decay."
        ),
        expected_d1=D1Category.MECHANISM,
        difficulty="hard",
        ambiguous_with=D1Category.TECHNIQUE,
        notes="MECHANISM (causal chain: repetition → compression; one-off → decay) vs TECHNIQUE "
        "(method for doing consolidation). The descriptive 'converts / become / are allowed' "
        "language is mechanistic, not procedural.",
    ),
    SKUFixture(
        fixture_id="hard_06",
        content=(
            "Measurement: cerebra ingest docs/refined-runtime-model/ produced "
            "39 sources and 745 chunks with 0 failures on 2026-06-04."
        ),
        expected_d1=D1Category.OBSERVATION,
        difficulty="hard",
        ambiguous_with=D1Category.EVENT,
        notes="OBSERVATION (measurement data with numbers) vs EVENT (something that happened at "
        "a point in time). Both apply; the numbers tip toward OBSERVATION over EVENT.",
    ),
    SKUFixture(
        fixture_id="hard_07",
        content=(
            "The approval gate is a workflow convention, not a CLI feature. "
            "bumper renders and traces, and you (or your agent) post a dry-run "
            "sample for approval before the live bump."
        ),
        expected_d1=D1Category.DESIGN,
        difficulty="hard",
        ambiguous_with=D1Category.TECHNIQUE,
        notes=(
            "DESIGN (intentional architectural choice: 'convention not feature' / 'is X, not Y' "
            "framing signals a design decision) vs TECHNIQUE (procedural second sentence: 'bumper "
            "renders and traces, and you post a dry-run sample' reads as how-to steps). 5/13 models "
            "picked TECHNIQUE (the stronger performers); only 1/13 picked old ambiguous_with=PRINCIPLE. "
            "ambiguous_with updated from PRINCIPLE to TECHNIQUE to reflect actual model behavior."
        ),
    ),
    SKUFixture(
        fixture_id="hard_08",
        content=(
            "A STOP-gate triggers when 5 or more simultaneous test failures share a root cause. "
            "Do not patch them one by one. Classify the shared signature first."
        ),
        expected_d1=D1Category.CONSTRAINT,
        difficulty="hard",
        ambiguous_with=D1Category.PRINCIPLE,
        notes="CONSTRAINT (hard limit: 5+ failures = stop, hard prohibition on individual patching) "
        "vs PRINCIPLE (behavioral rule). The 'do not' + concrete threshold tips to CONSTRAINT.",
    ),
    SKUFixture(
        fixture_id="hard_09",
        content=(
            "Phase 2 scope: assign D1, D4, D9, D10 digits using the classifier; "
            "stub D2, D3 as 0x0 with subcategory_strategy_version='v1-stub'; "
            "defer D5, D6 to v0.2."
        ),
        expected_d1=D1Category.DESIGN,
        difficulty="hard",
        ambiguous_with=D1Category.TECHNIQUE,
        notes="DESIGN (scoping decisions — what was intentionally included/excluded) vs TECHNIQUE "
        "(procedure for doing Phase 2). Scope decisions are architectural choices = DESIGN.",
    ),
    SKUFixture(
        fixture_id="hard_10",
        content=(
            "Memories above the active salience threshold are promoted to working memory "
            "and become available to the current reasoning cycle. "
            "Below the threshold, they stay in episodic storage."
        ),
        expected_d1=D1Category.MECHANISM,
        difficulty="hard",
        ambiguous_with=D1Category.PRINCIPLE,
        notes="MECHANISM (causal: above threshold → promoted; below → stays) vs PRINCIPLE "
        "(rule governing promotion). The directional causality is mechanistic.",
    ),
    SKUFixture(
        fixture_id="hard_11",
        content=(
            "Two-attempt cap: if a fix and one retry both fail, stop and report. "
            "Three rounds on one theory means the theory is wrong."
        ),
        expected_d1=D1Category.CONSTRAINT,
        difficulty="hard",
        ambiguous_with=D1Category.PRINCIPLE,
        notes="CONSTRAINT (hard cap: 2 attempts max) vs PRINCIPLE (behavioral rule for debugging). "
        "The concrete number cap ('two-attempt') is more CONSTRAINT than PRINCIPLE.",
    ),
    SKUFixture(
        fixture_id="hard_12",
        content=(
            "Phase 3 adds a lexical FTS5 index over chunk content and a vector similarity "
            "layer using numpy + cosine similarity over an embedding table. "
            "No external vector store in v0.1."
        ),
        expected_d1=D1Category.DESIGN,
        difficulty="hard",
        ambiguous_with=D1Category.TECHNIQUE,
        notes="DESIGN (architectural decisions about Phase 3 infrastructure) vs TECHNIQUE (how "
        "to implement it). 'Adds X, no Y in v0.1' is scoping/design language.",
    ),
    SKUFixture(
        fixture_id="hard_13",
        content=(
            "The inspector exists because a system that thinks must be inspectable. "
            "Opacity in a cognitive runtime is not a trade-off — it is a defect."
        ),
        expected_d1=D1Category.PRINCIPLE,
        difficulty="hard",
        ambiguous_with=D1Category.GOAL,
        notes="PRINCIPLE (normative 'must be' + 'opacity is a defect') vs GOAL (desired state). "
        "The framing is a design doctrine, not just a desired outcome.",
    ),
    SKUFixture(
        fixture_id="hard_14",
        content=(
            "Deviation log entry format: state what the plan said, what was shipped instead, "
            "why it deviated, the downstream impact, and whether the deviation is accepted "
            "or needs reverting."
        ),
        expected_d1=D1Category.DESIGN,
        difficulty="hard",
        ambiguous_with=D1Category.TECHNIQUE,
        notes="DESIGN (schema/format specification for a structured artifact) vs TECHNIQUE "
        "(procedure for writing a log entry). 'Format: field1, field2...' is schema = DESIGN.",
    ),
    SKUFixture(
        fixture_id="hard_15",
        content=(
            "sku_address is NULL for all 745 memory records immediately after Phase 1 ingest. "
            "The classifier backfill sweep in Phase 2 populates all 745 addresses."
        ),
        expected_d1=D1Category.OBSERVATION,
        difficulty="hard",
        ambiguous_with=D1Category.EVENT,
        notes="OBSERVATION (measured state of the system: 745 NULLs) vs EVENT (the backfill "
        "sweep as an occurrence). The dominant information is a measured count = OBSERVATION.",
    ),
]

# Quick lookup maps
FIXTURE_BY_ID: dict[str, SKUFixture] = {f.fixture_id: f for f in SKU_FIXTURES}
CLEAR_FIXTURES: list[SKUFixture] = [f for f in SKU_FIXTURES if f.difficulty == "clear"]
HARD_FIXTURES: list[SKUFixture] = [f for f in SKU_FIXTURES if f.difficulty == "hard"]
AMBIGUOUS_FIXTURES: list[SKUFixture] = [f for f in SKU_FIXTURES if f.difficulty == "ambiguous"]

assert len(SKU_FIXTURES) == 30, f"Expected 30 fixtures, got {len(SKU_FIXTURES)}"
assert len(CLEAR_FIXTURES) == 11, f"Expected 11 clear fixtures, got {len(CLEAR_FIXTURES)}"
assert len(AMBIGUOUS_FIXTURES) == 4, f"Expected 4 ambiguous fixtures, got {len(AMBIGUOUS_FIXTURES)}"
assert len(HARD_FIXTURES) == 15, f"Expected 15 hard fixtures, got {len(HARD_FIXTURES)}"
