# Phase 6+ Cognitive Extensions

*Concept document — drafted 2026-06-12. Companion to the cognitive_extension_overview.md navigational entry point. Captures architectural directions that emerged in conversation but are not yet ready for full concept documents. Each section names a direction, locates it in the architecture, and identifies what would need to be true before it moves from concept to implementation.*

---

## What this document is

The concept document series describes a layered cognitive architecture extension. The lattice, lenses, frame, methodology, and dark matter substrate documents each capture a substantive architectural commitment at depth. They are full design directions, ready to inform implementation when their phases arrive.

This document is different. It captures architectural ideas that have surfaced during design conversations but are not yet at the level of detail where a full concept document is warranted. Some of these are extensions to existing concept documents that would clutter their parent docs. Some are independent directions that need more empirical context before they can be designed in detail. Some are bookmarks for explorations that the work has not yet earned but should not lose.

The structure for each section is consistent. What the direction is. Where it sits in the architecture. What it depends on or enables. What would need to be true before moving from concept to implementation. The treatment is shorter than the main concept documents because the ideas have not yet reached the level of articulation that would justify longer treatment.

A reader of this document should not expect implementation-ready architecture. The expectation is "here are directions worth knowing about, here is what they would do if pursued, here is the rough shape of the work each would require."

---

## The minor arcana relational overlay

The archetypal lenses concept document describes twenty-two cognitive postures derived from the structural pattern of the Major Arcana. The full tarot system includes fifty-six additional cards organized into four suits (Cups, Pentacles, Swords, Wands) plus four court cards per suit. The lenses doc deliberately restricted itself to the twenty-two postures and did not address whether the suits contribute additional architectural value.

The Minor Arcana, if treated structurally rather than as occult content, captures cognitive *operations* rather than postures. The four suits map to four dimensions of cognitive activity that are orthogonal to the postures the lenses already provide:

Cups represent the affective dimension. The valence of cognition. Whether a thing matters emotionally and how. The dimension currently absent from Cerebra's architecture is the user's emotional relationship to content; nothing in the existing schema captures that a record matters more than another because of what it represents to the user.

Pentacles represent the embodied dimension. The concreteness and groundedness of an interpretation. The distance between abstract principle and observed particular. Cerebra has SKU categories (abstract types) and records (concrete instances) but no explicit dimension orthogonal to category that captures grounding scale.

Swords represent the discrimination dimension. The work of distinguishing one thing from another. Cerebra has classification (assigning categories) but does not have explicit not-this-but-that reasoning as a first-class operation. The lattice multi-commit handles both-this-and-that; discrimination handles the inverse.

Wands represent the generative dimension. Synthesis, creative pattern formation, the production of new structure from accumulated material. Cerebra retrieves and classifies; it does not yet generate new patterns from what it has accumulated. Phase 6's cycle runtime begins to address this but does not name it as a distinct operation type.

A minor arcana overlay would add multi-axial attribution to memory records. The existing SKU axis says what kind of content a record is. The overlay axis says what cognitive operation the record currently serves. A single record can have multiple suit affinities at different strengths; over time, the affinities shift based on how the record gets used.

The overlay creates parallel retrieval paths through the same substrate. When the cycle runtime is reasoning about emotional weight in past decisions, it queries the Cups dimension and gets different relevant records than the SKU axis would surface. The aliasing produces different cognitive views of the same accumulated memory.

This direction depends on the cycle runtime existing (Phase 6) and on the lens system being implemented (post-Phase-5 cognitive extension). Without either, the overlay has nothing to do — there are no cognitive operations actively querying it. Implementation would be most valuable once the cycle runtime is producing queries that need to distinguish between operation types.

Implementation would add a `record_suit_affinities` table linked to memory_records, with columns for suit (Cups, Pentacles, Swords, Wands), affinity_strength (real), and the operation that produced the affinity. Population happens over time as the cycle runtime uses records for different operations; initial affinities can be seeded from the SKU classification.

The four-suit committee described in the next section is a related but distinct architectural direction. The overlay is metadata on existing records; the committee is parallel inference at classification time. Both use the suit structure but for different purposes.

## The four-suit committee with fifth-element mediator

A specialized version of the existing classifier where, instead of a single Granite 4.1 3B Instruct producing a single classification, four suit-specialized adapters produce four parallel evaluations and a mediator function integrates them into a committee decision.

The four adapters are LoRA fine-tunes of the same Granite base, each trained on a different cognitive operation:

The Cups adapter evaluates affective weight. Does this content carry emotional significance? Is the user's relationship to it weighted? Does ignoring it produce more loss than ignoring an equivalent neutral chunk would?

The Pentacles adapter evaluates grounding. Is this content abstract principle or concrete observation? How close is it to direct experience? Could it be tested against observation?

The Swords adapter evaluates discrimination. What is this content not? What distinctions does it draw? Where are the meaningful boundaries between its category and adjacent categories?

The Wands adapter evaluates generative potential. What new patterns does this content enable? What synthesis does it make possible? What other content does it productively combine with?

The fifth element is a mediator function — not a fifth model but logic in the runtime that integrates the four evaluations. The mediator's responsibilities:

Conflict resolution when the suit-experts disagree. If Cups says emotionally important, Swords says imprecise, Wands says generative, Pentacles says ungrounded, what does the committee output? The mediator's job is *deciding what the disagreement means* rather than letting it resolve by majority vote.

Frame selection. Not every chunk needs all four evaluations. A technical specification probably engages Swords and Wands meaningfully; Cups is irrelevant. A personal reflection probably engages Cups and Pentacles; Wands less so. The mediator decides which suits engage for which content, similar to the suit-rotation pattern in efficient ensemble methods.

Confidence normalization. Cups confidence in "this matters affectively" is not directly comparable to Swords confidence in "this distinction is sharp." The mediator normalizes across heterogeneous confidence signals before composing them.

Meta-cognitive flagging. When all four suits return low confidence, the mediator flags "the committee cannot characterize this content well." When three suits agree and one strongly disagrees, the mediator preserves the disagreement for downstream reasoning rather than collapsing it.

The mediator is implemented as a Python function, not a fifth model. Its behavior is inspectable and tunable. The four model adapters produce evaluations; the mediator produces a decision.

This direction depends on the LoRA training pipeline being resumed and on the dark matter substrate being populated enough to provide training corpus for the four specialized adapters. The methodology for training each suit-adapter is a downstream design question once those prerequisites are in place.

Resource-wise, four LoRA adapters on a single Granite base is feasible on a 12GB VRAM card with adapter swapping. Inference latency is higher than single-classification but bounded; the committee runs in single-digit seconds for a chunk rather than sub-second. Production deployment would need to decide whether to run the committee on every chunk or only on chunks where the lattice indicates ambiguity that the committee could help resolve.

## The Advaita epistemic gradient as clutch-engaged mode

The Advaita Vedanta epistemic registers (vyāvahārika, prātibhāsika, pāramārthika) map to three modes a cognitive system can operate in:

Transactional mode treats working models as reliable for ordinary purposes while acknowledging their provisional character. This is the default mode and where most cognitive activity happens.

Provisional mode treats the system's own assumptions as known-operational-fictions. The system flags to itself that current working models may not hold; this changes how strongly the system commits and how readily it revises.

Invariant mode operates only with structure that holds across all framings. Logical relations, mathematical truths, the bare fact that something is happening rather than what is happening. Rarely active; engaged for questions where surface-level reasoning would just reproduce the question.

The architectural commitment is that these are not static properties of memory records but *operational modes the system shifts between based on cognitive context*. A chunk that lives in transactional register most of the time is the same chunk; what changes is how the system relates to it during specific cognitive operations.

The clutch primitive from the Lattica primitives is the natural mechanism for engaging mode shifts. The clutch handles event-driven mode changes; epistemic gradient becomes one of the modes the clutch can engage. When the cognitive context warrants it — encountering paradox, needing to reason across radically different frames, recognizing the system's own miscalibration — the clutch shifts the active mode.

In transactional mode, retrieval operates normally, commits are confident, the system treats its own outputs as actionable.

In provisional mode, retrieval is annotated with uncertainty markers, commits include hedging metadata, the system surfaces its assumptions for explicit examination rather than treating them as given.

In invariant mode, the system filters out framing-dependent content, focuses on structural relationships, treats specific contents as instances of patterns rather than as facts to be reasoned about directly.

The mode is queryable as system state. The cycle runtime can ask "what mode am I in?" and adjust its behavior accordingly. Inspector events capture mode transitions so the audit trail shows when and why the system shifted register.

This direction depends on the cycle runtime existing (Phase 6) and on the clutch primitive being available for new use cases. The integration with the existing clutch is mostly additive — adding a new mode-engagement condition rather than restructuring the clutch itself.

The training implications are substantial. If the model has been trained primarily in transactional mode, it may not engage provisional or invariant modes well even when the architectural triggers fire. This is an open question that empirical work would need to answer: do the modes actually produce different cognitive operations when engaged, or does the underlying model collapse them back to a single behavioral pattern?

## The witness layer as architectural primitive

The Advaita doctrine that awareness (sākṣī, the witness) is distinct from the contents it observes points at an architectural separation that meta-cognition requires. A system that observes itself needs the observing function to be distinct from the observed content.

Cerebra's current architecture has inspector events as the substrate for self-observation. Events accumulate; they are queryable; nothing currently *consumes them for cognition*. They are audit, not witness.

The witness layer as architectural primitive would be a substrate that systematically reads the inspector event stream and produces structured self-observation as queryable data. The witness sees what the system did, when, why; over time the witness accumulates patterns of operation that the system can examine.

This is distinct from the truth tower. The tower holds *what the system thinks* (curated cognitive contents). The witness holds *what the system has observed itself thinking* (self-observation as structured data). They are similar in shape and persistent in nature but different in role. The tower is for cognition; the witness is for meta-cognition.

Witness state would be queryable in ways the inspector events alone are not. Inspector events are point-in-time records. Witness state is aggregated, classified, summarized into patterns the system can reason about. A query like "how often does my classifier abstain on queries that involve emotional content?" is a witness query, not an inspector query. The inspector has the raw events; the witness has the structure that makes them interrogable as patterns.

The dark matter substrate from the related concept document is one possible component of the witness — captured cognitive operations classified by their evidentiary status. Retrieval traces are another — captured cognitive operations classified by their query lineage. Working memory access patterns are a third. Each is a stream of self-observation that the witness layer would integrate.

The integration function is the substantive work. Inspector events produce a firehose; witness state requires the firehose to be classified, aggregated, and indexed for cognitive use. Projections over the event stream produce specific witness views; the witness layer is the collection of these projections plus the orchestration that keeps them current.

This direction depends on the inspector substrate having accumulated enough events to be worth aggregating (probably already the case), on the event sourcing toolkit providing projection infrastructure that the witness can build on (the revised toolkit architecture supports this), and on the cycle runtime existing to consume witness state for actual meta-cognition.

Implementation would start with a small set of witness projections that capture obvious patterns: abstention rates, lattice multi-commit frequencies, tower citation chains, working memory eviction patterns. These provide immediate value for human-readable observability (the Lattica dashboard) before they become substrate for the cycle runtime's meta-cognition.

The naming "witness" is loaded but accurate. The Quaker meaning (the part of awareness that observes without judging) maps cleanly onto the architectural function. The Advaita sākṣī meaning (the witness as distinct from observed contents) provides the structural argument for why the layer should be separate from the truth tower. Other traditions (Husserl's retention, certain contemplative pedagogies) provide additional vocabulary if needed. The architectural commitment is more important than the naming choice.

## What's not in this document

Several directions discussed in conversation are deliberately not captured here because they belong elsewhere.

The OpenTelemetry cross-project observability is infrastructure-flavored rather than cognitive-architecture-flavored. It belongs in the cross-project observability document, not here.

The event sourcing toolkit revision is its own design document and supersedes parts of an existing roadmap. It belongs in the toolkit revision document, not here.

The transmutational training methodology and the scribe pattern as shadow curator are captured in the dark matter substrate concept document. They are not duplicated here.

The lockfile mechanism implementation, the Phase 5 specific decisions, the lattice retrieval awareness — these are implementation work, not architectural direction. They live in design docs for their respective phases, not in concept docs.

The five-element framing that connects the four-suit committee to a fifth-element mediator is captured in that section; the fifth element is logic in code, not a fifth model. The temptation to expand the fifth element into a full architectural treatment is resisted because the mediator's substance is its functional behavior, not its conceptual framing.

## What unifies these directions

The directions in this document are not arbitrary additions. They cluster around three architectural themes that have emerged across multiple design conversations:

The system needs to know things about itself. The witness layer, the dark matter substrate, the meta-cognitive flagging in the four-suit committee — all of these are mechanisms for the system to observe and reason about its own operation. Meta-cognition is the major missing capability in the current architecture, and several of the directions in this document address different facets of it.

The system needs multi-axial attribution rather than single-axis classification. The minor arcana overlay, the four-suit committee, the lattice multi-commit (already shipped) — all of these add parallel paths through the same substrate. Single-axis classification collapses ambiguity; multi-axial attribution preserves it as structure.

The system needs continuous influence rather than discrete events. The Advaita epistemic gradient operating as clutch-engaged mode, the witness layer aggregating event streams into queryable patterns, the field-like dynamics gestured at in earlier conversations — all of these point at the limits of pure event-driven architecture. The current system reacts to events; the directions here move toward the system *operating within a continuously updated cognitive context*.

Together, the three themes describe what Phase 6 and beyond is likely to be: not just the cycle runtime, but a cycle runtime that operates with meta-cognition, multi-axial attribution, and field-like contextual dynamics. The directions in this document are the architectural surface area that Phase 6+ work will gradually fill in.

## What this document is and is not

This is a banking document, not a design specification. The directions are real architectural ideas worth preserving; they are not implementation-ready. A reader implementing Phase 6 or later should treat this document as input to design rather than as design itself.

The directions are not all expected to land. Some may be subsumed by more specific designs that emerge later. Some may turn out to be wrong on inspection once empirical data from earlier phases changes the framing. The document captures the directions at the moment they were clear enough to write down; revision is expected.

The treatment is shorter than the main concept documents intentionally. The ideas are not yet articulated at the level that would warrant longer treatment, and forcing more length would produce false confidence rather than clearer architecture. When any of these directions becomes a real implementation target, it will earn its own full concept document at that time.

---

*This document extends the cognitive_extension_overview.md navigational entry point. Future revisions may promote sections from this document to standalone concept documents as the directions mature and the implementation context becomes clearer.*
