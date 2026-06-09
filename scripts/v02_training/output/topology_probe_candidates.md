# Topology Probe Candidates — Phase 2 Draft

8 cells: 4 categories × 2 clarity levels.  
2–3 candidates per cell = 20 candidates total.  
Final 8 (one per cell) selected by user.

---

## Construction notes

- 80–200 words per probe, consistent length avoids length as confound
- Source style: planning-doc voice (not academic, not casual)
- Category name does NOT appear verbatim in probe text
- Category definition is NOT restated
- L2: clear fit, no other reasonable category read
- L4: 2–3 other categories could legitimately be picked

---

## DESIGN — L2 (strong fit)

> Target: a reviewer would confidently assign DESIGN, no hesitation.

---

**DESIGN-L2-A**

The classifier splits its work across two distinct passes rather than attempting a
single comprehensive evaluation. The first pass narrows the search space to a
quadrant; the second pass selects within that quadrant. Keeping the two stages
separate lets each prompt be tighter and more focused than a combined prompt would
allow. The boundary between passes is explicit: Pass 1 output is the only input to
Pass 2. There is no feedback path from Pass 2 back to Pass 1. This separation also
makes each stage independently replaceable — swapping the quadrant logic does not
require changing the within-quadrant logic, and vice versa.

*Claimed: L2 DESIGN.*
*Rationale: The text describes an architectural partitioning decision — two-stage
structure, explicit interface boundary, independent replaceability. No procedural or
normative framing. Other categories are clearly not relevant.*

---

**DESIGN-L2-B**

The registry is the authoritative source of truth for all active panel types. No
component discovers available panels by importing them directly; instead, each panel
registers itself at load time, and consumers query the registry at runtime. This
means adding a new panel type requires only a single registration — no consumer
needs to be updated. The registry's structure also serves as the contract: any object
satisfying the registration interface is a valid panel, regardless of its
implementation. Hardcoded panel lists are explicitly prohibited because they create
a parallel taxonomy that diverges from the registry over time.

*Claimed: L2 DESIGN.*
*Rationale: Registry-as-authoritative-source is a structural architecture decision.
The text describes a structural pattern (what connects to what, and why), not a
procedure for doing something or a normative rule about behavior. Clean L2 DESIGN.*

---

**DESIGN-L2-C**

The tile system separates layout responsibility from content responsibility. Tiles
own their position and size; panels own their rendered content. Neither knows
anything about the other's internals. A tile can be moved, resized, or replaced
without touching the panel it hosts. A panel can be swapped to a new tile without
carrying layout state with it. The layout manager only speaks to tiles; the panel
registry only speaks to panels. This clean separation of concerns is load-bearing:
it prevents layout bugs from showing up as content bugs and vice versa.

*Claimed: L2 DESIGN.*
*Rationale: Explicit separation-of-concerns architecture, two distinct responsibility
domains, and an explanation of why the boundary is important. No ambiguity with
MECHANISM (nothing about how it operates) or PRINCIPLE (not a normative rule).*

---

## DESIGN — L4 (weak fit)

> Target: reviewer leans DESIGN but 2–3 other categories defensible.

---

**DESIGN-L4-A**

When a component needs to communicate a state change to other parts of the system,
it emits a typed signal rather than calling a function directly. The signal carries
a payload; receivers subscribe independently. This decouples the emitter from
knowing which receivers exist, and allows receivers to be added or removed without
modifying the emitter. The same pattern applies at the graph layer: when the graph
topology changes, the layout engine receives a signal rather than being called
directly. In practice this means the emitter and the layout engine can evolve on
separate schedules.

*Claimed: L4 DESIGN.*
*Rationale: This is a structural choice (signal/subscription vs. direct call) which
reads as DESIGN. But it also describes a concrete communication pathway (MECHANISM)
and could be read as a TECHNIQUE (event-driven pattern) or even PRINCIPLE (decoupling
as a rule). At least 2–3 other categories defensible.*

---

**DESIGN-L4-B**

The graph stores nodes and edges as separate collections, each indexed by a stable
identifier. Lookups are O(1) by identifier. Iteration order is insertion order.
Neither collection holds references to the other's objects; edges carry only the
identifiers of their endpoints. This means the node collection and edge collection
can be updated independently, and validating graph consistency is a separate pass
that neither collection is responsible for performing.

*Claimed: L4 DESIGN.*
*Rationale: Primary read is DESIGN (how data is structured, why collections are
separate). But "O(1) by identifier" and "insertion order" read as MECHANISM (how it
works). "Validating consistency is a separate pass" could be PRINCIPLE (separation
of concerns as a rule). At least 2 other categories are defensible.*

---

**DESIGN-L4-C**

The state management layer is split between local component state and global store
state. Ephemeral interaction state — hover, drag in progress, focus — lives in local
component state and is not persisted. Durable state — active panel configuration,
graph topology, layout parameters — lives in the global store and survives component
remounts. The line between the two categories is decided at design time, not at
runtime. When a new piece of state is introduced, the question "which layer owns
this?" must be answered before the state is implemented.

*Claimed: L4 DESIGN.*
*Rationale: This is an architectural decision about state ownership (DESIGN). But
"ephemeral vs. durable" could read as a categorization / OBSERVATION. "The line is
decided at design time" could read as PRINCIPLE (a rule about process). "Must be
answered before implementation" has a normative flavor. 2–3 categories defensible.*

---

## MECHANISM — L2 (strong fit)

> Target: clear how-it-works description, no normative or structural framing.

---

**MECHANISM-L2-A**

When the classifier receives a chunk, it first sends the full content to the quadrant
model with the Pass 1 prompt. The quadrant model returns a JSON object containing
scores for each of the four quadrants and a primary field naming the highest scorer.
The classifier reads the primary field and constructs the Pass 2 prompt using it,
embedding the quadrant name in the prompt template. The Pass 2 prompt is then sent
to the same model with the within-quadrant category list. The model returns a second
JSON object with scores and a primary D1 category name. That name is the final
output of the two-pass call.

*Claimed: L2 MECHANISM.*
*Rationale: Pure step-by-step description of how the two-pass call executes. No
structural intent discussed, no normative framing, no reference to why the passes
are separated. Entirely procedural — how it works, in sequence.*

---

**MECHANISM-L2-B**

The retry handler wraps each Ollama call. On a ClassificationError, it sleeps for
one second and retries. After two failed attempts, it returns None and logs the
failure. The outer consensus loop treats a None vote as a skip — it does not count
toward the agreement threshold and does not prevent writing the record. The record's
stage2_votes dictionary will contain a None entry for the failing model, which
surfaces in the final analysis as a gap rather than as an incorrect vote.

*Claimed: L2 MECHANISM.*
*Rationale: Describes the exact failure-handling sequence — error → sleep → retry →
give up → propagate None → record gap. Pure operational flow. No structural intent,
no "why" framing, no normative claims.*

---

**MECHANISM-L2-C**

The physics layout runs on each animation frame. At each frame, the engine reads the
current node positions and applies three force terms: a spring force pulling connected
nodes toward their preferred separation distance, a repulsion force pushing all nodes
apart, and a drag term reducing velocity proportional to current speed. After summing
the forces, the engine updates each node's position by multiplying velocity by the
frame delta. Nodes pinned by the user are exempt from force application but still
affect other nodes through the spring term.

*Claimed: L2 MECHANISM.*
*Rationale: Step-by-step physics simulation loop — read positions, compute forces,
integrate, update. No ambiguity. TECHNIQUE would require framing around "how to
use" rather than "how it operates."*

---

## MECHANISM — L4 (weak fit)

> Target: 2–3 categories defensible alongside MECHANISM.

---

**MECHANISM-L4-A**

Configuration changes propagate through the component tree without direct prop
drilling. A context provider at the root holds the current configuration object; any
component that needs a configuration value reads from the context directly. When the
configuration changes, only components that read the changed fields re-render.
Components that hold stale closures over configuration values are a known failure
mode — they capture the old value at render time and do not react to updates unless
they re-read from context at call time.

*Claimed: L4 MECHANISM.*
*Rationale: Describes how config propagates (MECHANISM). Also reads as DESIGN (context
architecture, component tree structure). The stale closure warning reads as OBSERVATION
or PRINCIPLE. At least DESIGN and OBSERVATION are defensible alternatives.*

---

**MECHANISM-L4-B**

When two nodes are merged, the system resolves their edges before removing the
source node. Any edges pointing to the source are redirected to the target. Any
edges pointing from the source are duplicated onto the target, except for edges that
would create a self-loop. After edge resolution, the source node is removed from the
node collection and its identifier is added to a tombstone list. Components holding
a reference to the old identifier will receive a null on lookup rather than an error.

*Claimed: L4 MECHANISM.*
*Rationale: Describes the merge operation steps (MECHANISM). But "adding to tombstone
list" and the null-vs-error contract read as DESIGN decisions. "Self-loop exception"
could be a CONSTRAINT. The overall description sits between MECHANISM and DESIGN, with
CONSTRAINT as a third option.*

---

**MECHANISM-L4-C**

The export pipeline reads the graph state snapshot, converts each node into a JSON
object using the node's type's serialization method, writes the objects into an array,
then writes the edge array using source/target identifier pairs. The resulting file is
valid JSON with two top-level keys: nodes and edges. On import, the pipeline reverses
the process: it reads the node array first, constructs node objects, then reads the
edge array and reconstructs edge objects by looking up their endpoints in the freshly
built node collection.

*Claimed: L4 MECHANISM.*
*Rationale: Procedural export/import flow (MECHANISM). The "two top-level keys" is a
structural contract (DESIGN). The "read nodes first, then edges" ordering could be a
TECHNIQUE (serialization pattern) or even PRINCIPLE (dependency ordering). 2–3
alternatives defensible.*

---

## PRINCIPLE — L2 (strong fit)

> Target: normative rule, stated as a rule, no ambiguity with other categories.

---

**PRINCIPLE-L2-A**

Production classifiers must never be retrained on their own outputs. If the
classifier's outputs are used as labels for a new training run, any systematic
errors in the classifier become encoded in the new training data. The new model
learns to reproduce the old model's mistakes rather than learning from ground truth.
This applies regardless of how many times the cycle is repeated — iterating
self-training does not reduce the error; it amplifies it. Ground truth labels must
come from human review or from a source that is independent of the classifier's
prior outputs.

*Claimed: L2 PRINCIPLE.*
*Rationale: A normative prohibition stated explicitly ("must never"), with a causal
explanation of the rule's basis. No description of a system structure (DESIGN), no
procedure (MECHANISM), no observed finding (OBSERVATION). Clean normative rule.*

---

**PRINCIPLE-L2-B**

A fix must never be committed before the failure has been confirmed. Diagnosing from
a hypothesis and patching from that diagnosis without verifying the diagnosis first
is how fixes that "should work" create new failures. The cost of a false-positive
diagnosis — time spent on a wrong fix — is always higher than the cost of running
the diagnostic steps that would have ruled it out. Confirm the failure is real.
Confirm the mechanism that causes it. Then write the fix.

*Claimed: L2 PRINCIPLE.*
*Rationale: A normative rule about process ("must never"), causal reasoning behind
the rule, and an explicit prescription ("Confirm... then write"). No ambiguity with
MECHANISM (no operational steps described), DESIGN (no structure described), or
OBSERVATION (no finding reported).*

---

**PRINCIPLE-L2-C**

Any state that is shared across components must have a single owner. If two
components can both write to the same state, the system will eventually produce
inconsistent updates — one write will overwrite another, or reads will see
intermediate states. Ownership of shared state is not a style preference; it is a
correctness requirement. The owner writes; everyone else reads. If two components
both need to write, the state belongs in a layer above both of them, and both
components write through that layer.

*Claimed: L2 PRINCIPLE.*
*Rationale: Normative rule ("must have a single owner"), explained as a correctness
requirement, not a preference. While it touches on architecture, it's stated as a
rule to follow, not a structural description — the normative framing distinguishes
it from DESIGN.*

---

## PRINCIPLE — L4 (weak fit)

> Target: 2–3 categories defensible alongside PRINCIPLE.

---

**PRINCIPLE-L4-A**

When it is not clear whether a new piece of state belongs in local component state
or in the global store, the default should be local. Moving state from local to
global is easy. Moving state from global to local is harder — it requires identifying
all consumers, verifying none of them need the state to survive remounts, and
removing the global store entry without breaking any consumers. The asymmetry means
the cost of choosing global when local would have sufficed is higher than the cost
of choosing local when global turns out to be needed.

*Claimed: L4 PRINCIPLE.*
*Rationale: Normative default ("should be local") with cost-asymmetry reasoning. But
the description of state migration reads like MECHANISM (steps for moving state). The
"cost of choosing" framing could read as JUDGMENT. The distinction between local and
global state also has DESIGN flavor. 2–3 alternatives defensible.*

---

**PRINCIPLE-L4-B**

Probe texts should not contain the name of their target category. When the category
name appears in the probe, the model has a surface-level cue that leads directly to
the right answer — and a model following that cue is demonstrating pattern matching,
not category understanding. The goal of the probe corpus is to test whether the model
has internalized the conceptual distinction, not whether it can recognize a keyword.
Category names should appear only in the classification prompt where the model must
choose among them, not in the content it is classifying.

*Claimed: L4 PRINCIPLE.*
*Rationale: Normative construction rule ("should not contain"). But it also reads as
a methodological TECHNIQUE (how to build a good probe corpus) and as OBSERVATION
(noting that surface-level cues produce pattern matching not understanding). The line
between PRINCIPLE (normative rule) and TECHNIQUE (construction method) is the main
ambiguity.*

---

**PRINCIPLE-L4-C**

A migration that cannot be rolled back safely should not be run in production without
a tested rollback path. Irreversible schema changes are the highest-risk category of
database migration. Even when a forward migration is correct, the inability to undo
it means any downstream error forces a full restore rather than a targeted fix. The
test is not "will this migration succeed" — it is "if this migration succeeds and
something breaks downstream, can we recover cleanly without a restore?" If the answer
is no, the rollback path must be built before the migration runs.

*Claimed: L4 PRINCIPLE.*
*Rationale: Normative rule about migration safety, with risk framing. But also reads
as DESIGN (rollback as architectural requirement), CONSTRAINT (the "if no rollback,
must build it first" condition), or even TECHNIQUE (how to think about migration
risk). The normative framing is primary but the other reads are all defensible.*

---

## OBSERVATION — L2 (strong fit)

> Target: empirical finding or observed state, no normative or structural framing.

---

**OBSERVATION-L2-A**

In Round 2 calibration, both Granite 4.1 models returned high-confidence scores even
on fixtures where the prediction was wrong. Of the 14 wrong predictions by the 3B
model, all 14 were high-confidence. None were low-confidence wrong. This means the
model's confidence score does not distinguish between cases where it is right and
cases where it is wrong. A downstream consumer using confidence as a signal for
escalation would escalate nothing — because nothing registers as low-confidence —
while the actual error rate remained at 42%.

*Claimed: L2 OBSERVATION.*
*Rationale: Describes an empirical finding from calibration runs — the confidence
score's failure to track accuracy. Purely descriptive, citing specific numbers. No
normative prescription, no structural design, no mechanism described.*

---

**OBSERVATION-L2-B**

Across 13 models and 30 fixtures in Round 1, five fixtures received no correct
predictions. Every model, regardless of architecture or size, assigned an incorrect
D1 category to these five fixtures. The pattern of wrong predictions on these fixtures
was not random — most models converged on the same incorrect category for each one,
suggesting the fixtures were ambiguous or the ground truth labels were debatable
rather than the models failing independently.

*Claimed: L2 OBSERVATION.*
*Rationale: Reports empirical finding (5 fixtures with 0/13 correct predictions),
describes a pattern (convergence on same wrong category). No prescription, no
structure description, no mechanism. Pure empirical observation with hedged
interpretation.*

---

**OBSERVATION-L2-C**

During Stage 2 consensus scoring, the three-model panel showed substantially different
failure profiles. Two models frequently agreed when they were wrong, giving a false
majority signal. One model dissented from the majority on approximately 20% of
contested records, and in roughly half of those cases the dissenter's answer matched
the v0.1.0 label. The dissent was not noise — it was disproportionately predictive
of label correctness. This suggests the dissenting model had developed a different
and sometimes more accurate category lens on the same content.

*Claimed: L2 OBSERVATION.*
*Rationale: Empirical finding from Stage 2 data — the dissenting model's behavior.
Descriptive and specific. No normative claims about what should happen, no structural
choices described. The "suggests" phrasing is consistent with observation, not design
or principle.*

---

## OBSERVATION — L4 (weak fit)

> Target: 2–3 categories defensible alongside OBSERVATION.

---

**OBSERVATION-L4-A**

The v2.0.0 two-pass prompt structure produces different accuracy profiles at different
clarity levels. On clear fixtures (labeled L2), both models correctly classify 60-70%
of the time. On hard fixtures (labeled L4), accuracy drops to 50-57%. The accuracy
gap between L2 and L4 is smaller than expected — only 5-10 percentage points —
suggesting that the distinction between "strong fit" and "weak fit" probes matters
less to the models than it matters to human reviewers constructing the corpus.

*Claimed: L4 OBSERVATION.*
*Rationale: Reports empirical finding (accuracy gap between clarity levels). But this
is also a methodological insight that reads as PRINCIPLE (what the finding implies
about probe construction) or TECHNIQUE (how to interpret calibration results). The
"smaller than expected" framing introduces normative comparison. 2–3 categories
defensible.*

---

**OBSERVATION-L4-B**

Models trained primarily on instruction-following data tend to report higher
confidence on ambiguous inputs than models trained on reasoning-heavy data. In the
calibration runs, instruction-tuned models averaged 0.85-0.90 confidence on
hard fixtures regardless of whether they were right or wrong. Reasoning-trained
models averaged 0.65-0.75 on the same fixtures, with a more pronounced gap between
correct (higher confidence) and incorrect (lower confidence) predictions. The
reasoning-trained models' confidence was better calibrated even though their overall
accuracy was similar.

*Claimed: L4 OBSERVATION.*
*Rationale: Empirical finding about confidence calibration across training types
(OBSERVATION). Also reads as MECHANISM (why instruction-tuned models behave this
way) or PATTERN (a recurring regularity across model types). Could also be PRINCIPLE
("prefer reasoning-trained models for confidence-gated escalation"). 3 categories
defensible.*

---

**OBSERVATION-L4-C**

After three rounds of manual review, the most commonly misclassified category pair
was MECHANISM and TECHNIQUE. Reviewers disagreed with each other on this boundary
at a rate roughly 3× higher than for any other adjacent pair. When the same fixture
was reviewed on separate days, the same reviewer sometimes changed their own
assignment. The instability was not in the fixture content — it was in the boundary
definition. The two categories share enough semantic overlap that neither reviewers
nor models have a stable, reproducible criterion for choosing between them.

*Claimed: L4 OBSERVATION.*
*Rationale: Reports empirical finding (MECHANISM/TECHNIQUE confusion rate, reviewer
disagreement). But reads as PRINCIPLE (the categories need clearer definitions) and
as DESIGN concern (the taxonomy boundary is not well-drawn). The "instability was
in the boundary definition" interpretation slides toward normative critique. 2–3
alternatives defensible.*

---

## Summary table — 20 candidates

| Cell | ID | Claimed | Notes |
|------|-----|---------|-------|
| DESIGN L2 | DESIGN-L2-A | L2 DESIGN | Two-pass separation decision |
| DESIGN L2 | DESIGN-L2-B | L2 DESIGN | Registry-as-authoritative-source |
| DESIGN L2 | DESIGN-L2-C | L2 DESIGN | Tile/panel separation of concerns |
| DESIGN L4 | DESIGN-L4-A | L4 DESIGN | Signal/subscription vs. direct call |
| DESIGN L4 | DESIGN-L4-B | L4 DESIGN | Graph node/edge separate collections |
| DESIGN L4 | DESIGN-L4-C | L4 DESIGN | Local vs. global state ownership |
| MECHANISM L2 | MECHANISM-L2-A | L2 MECHANISM | Two-pass call execution steps |
| MECHANISM L2 | MECHANISM-L2-B | L2 MECHANISM | Retry handler flow |
| MECHANISM L2 | MECHANISM-L2-C | L2 MECHANISM | Physics simulation frame loop |
| MECHANISM L4 | MECHANISM-L4-A | L4 MECHANISM | Config propagation via context |
| MECHANISM L4 | MECHANISM-L4-B | L4 MECHANISM | Node merge + tombstone |
| MECHANISM L4 | MECHANISM-L4-C | L4 MECHANISM | Export/import pipeline steps |
| PRINCIPLE L2 | PRINCIPLE-L2-A | L2 PRINCIPLE | No self-training on own outputs |
| PRINCIPLE L2 | PRINCIPLE-L2-B | L2 PRINCIPLE | Confirm before fixing |
| PRINCIPLE L2 | PRINCIPLE-L2-C | L2 PRINCIPLE | Single owner for shared state |
| PRINCIPLE L4 | PRINCIPLE-L4-A | L4 PRINCIPLE | Local-before-global default |
| PRINCIPLE L4 | PRINCIPLE-L4-B | L4 PRINCIPLE | No category name in probe text |
| PRINCIPLE L4 | PRINCIPLE-L4-C | L4 PRINCIPLE | Rollback path before migration |
| OBSERVATION L2 | OBSERVATION-L2-A | L2 OBSERVATION | Confidence doesn't track accuracy |
| OBSERVATION L2 | OBSERVATION-L2-B | L2 OBSERVATION | 5 fixtures no model got right |
| OBSERVATION L2 | OBSERVATION-L2-C | L2 OBSERVATION | Dissenting model predictive of label |
| OBSERVATION L4 | OBSERVATION-L4-A | L4 OBSERVATION | L2/L4 accuracy gap smaller than expected |
| OBSERVATION L4 | OBSERVATION-L4-B | L4 OBSERVATION | Instruction vs. reasoning-trained confidence |
| OBSERVATION L4 | OBSERVATION-L4-C | L4 OBSERVATION | MECHANISM/TECHNIQUE boundary instability |

---

*Instructions for user review:*
- *Select 1 winner per cell (8 total)*
- *Mark winners by ID (e.g. "DESIGN-L2-B")*
- *Optional: note any cells where you want revisions instead of a winner*
- *After selection, Phase 3 (harness build) begins*
