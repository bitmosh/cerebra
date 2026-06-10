# Cognitive Architecture Extension — Overview

*Concept document — drafted 2026-06-09 as the navigational entry point for a series of four concept documents describing a post-v0.1 cognitive architecture extension to Cerebra. Status: open exploration, not implementation scope.*

---

## What this collection is

This is a series of four concept documents, drafted together on the same day, describing an architectural direction for Cerebra that extends substantially beyond the v0.1 substrate currently being built. The documents are concept-level: they articulate what is being proposed, why it is being proposed, and how the components relate to each other. They do not specify implementation, do not commit to timelines, and do not block any work currently in progress.

The four documents emerged from a working session that started with a small question about classifier confidence handling and ended with a coherent extension to Cerebra's cognitive runtime. The session covered ground that, in retrospect, deserves to be preserved as a unit rather than fragmented across multiple later conversations. These documents are the preservation.

Two readers are anticipated. The first is future-Ryan, returning to this material in three to six months when v0.1 has shipped and Phase 4 or later phases bring the architectural questions back into active design. The second is any collaborator who eventually joins the project and needs to understand the architectural commitments that current code is being designed to leave room for. Both readers will benefit from understanding the four documents as a unit rather than reading them in arbitrary order.

## The four documents and how they relate

**The interpretive lattice** describes the substrate-level concept. When the classifier produces a confidence distribution where multiple categories clear a threshold, the chunk is committed to each qualifying category as a sibling memory entry. The chunk's position in the SKU substrate becomes a small constellation rather than a single coordinate. This preserves interpretive ambiguity as first-class structure rather than collapsing it at classification time. The lattice is the foundation that the other concepts build on; nothing else in the series makes sense without it.

**The archetypal lenses** describe the mechanism by which lattice positions actually get populated. Rather than a single classifier producing one classification per chunk, a structured set of distinct interpretive postures evaluates the same chunk in parallel. Each lens has its own characteristic way of attending to content; the union of lens activations produces the multi-interpretation footprint the lattice records. The lenses include a silence operator that activates when no productive interpretation is available — calibrated abstention as a first-class lens.

**The evaluative frame** describes the coherence layer that sits above the lattice and lenses. A structured set of evaluative principles checks the system's own outputs continuously, detecting deviations from proper functioning and triggering compensatory activity through the Clutch primitive. The frame keeps lens proliferation disciplined, catches commits that lens-disagreement would otherwise allow to enter the substrate without acknowledgment, and produces the deviation-compensation chains that become training signal.

**Iterative self-improvement** describes the methodology that ties everything together. The architecture produces specific kinds of structured data — multi-commit footprints, lens transformation artifacts, frame deviation chains, silence rationales — that ordinary supervised fine-tuning pipelines cannot generate from labeled examples. This data is extracted as training corpus, amended where necessary by a stronger reasoning agent, used to fine-tune the underlying model, and the cycle repeats. Each iteration internalizes some of the harness-mediated capability into the model itself; the harness can then be extended into territory the previous model could not handle.

The relationship among the four is hierarchical in a specific way. The lattice provides the substrate; the lenses provide the generation; the frame provides the coherence; the methodology provides the training trajectory. Each document depends on its predecessors and is depended upon by its successors. The reading order matches this dependency structure.

## Suggested reading order

For a reader encountering the material fresh, the order in which the documents were drafted is the right reading order: lattice, then lenses, then frame, then methodology. Each document forward-references concepts that the later documents develop, and reading earlier documents first means those forward-references land as anticipated rather than as unsupported claims.

A reader returning to refresh on a specific topic can read documents independently. The lattice doc stands alone reasonably well; the lenses doc requires the lattice context but not the others; the frame doc requires both lattice and lenses; the methodology doc draws on all three. None of the documents is so long that re-reading the prerequisites is prohibitive when a refresh is needed.

A reader using these documents to inform implementation work should expect to read all four. The architectural commitments are entangled in ways that make selective reading risky. Implementing the lattice without the lenses produces a substrate that stays empty; implementing the lenses without the frame produces fragmentation; implementing any architectural component without the methodology produces training signal that goes unextracted.

## The unifying insight worth carrying across documents

The architecture as a whole exists to produce a particular kind of training signal. Single-classifier systems generate labeled examples. Cerebra's cognitive extension generates *structured cognitive experience* — interpretations with provenance, transformations with lineage, deviations with compensation chains, abstentions with rationales. This is qualitatively different from what supervised fine-tuning corpora normally contain, and it is what makes the spiral methodology possible at all.

The architecture is not justified by elegance or by completeness of design. It is justified by what it produces. If the lattice multi-commit structure produced no training signal that single-label classification cannot produce, the storage cost would be unwarranted. If the lens system produced no frame-shift artifacts that flat classification cannot produce, the harness complexity would be unwarranted. If the frame produced no deviation-compensation chains that could not be derived from outputs alone, the inspector overhead would be unwarranted. The architecture earns its complexity by producing data structures that map onto meta-cognitive capabilities the model cannot otherwise be trained to acquire.

This reframing matters when reading the individual documents. Each document is, at one level, describing a mechanism. At another level, each is describing a *data source* — a stream of structured signal that the methodology can extract. The two readings are equally important and the documents try to hold both simultaneously.

## Notes on language

The documents are deliberate about terminology. A few choices worth flagging because they affect how the work should be discussed externally.

*Lenses* rather than *personas* or *roles*. A lens is a cognitive posture the system applies to content, not an identity the system adopts. The distinction matters because identity framing tends to drift and develop internal coherence that resists revision; posture framing stays light. The lens is a tool, not a self.

*Frame* rather than *guard rails* or *content filter*. The frame checks the system's own reasoning against principles, not the content being processed against categories. It catches process failures, not topic violations. The pattern is constitutional self-critique applied to cognitive coherence rather than to harm avoidance.

*Multi-commit* rather than *multi-classification*. Multi-commit is what the lattice does at the substrate level: writes multiple sibling memory entries for chunks whose interpretive shape warrants it. Multi-classification could be misread as "the classifier returns multiple labels" — which is true but trivial. The substrate-level commitment is what matters.

*Harness-internalization spiral* rather than *distillation*. The work involves using stronger models to produce training data for a smaller domain-specific model. The mechanism is structurally similar to distillation but categorically different from the use case Anthropic's Fable 5 distillation classifier targets. The terminology should reflect this. *Corpus enrichment via strong-model amendment* is a longer phrasing that works for the data-preparation portion specifically.

*Silence operator* rather than *abstention* alone. Abstention is what the silence operator does; silence is the cognitive posture from which abstention emerges. Treating silence as a first-class lens with its own activation conditions, rather than as a special non-output, gives the system a positive concept of "deciding not to" rather than a defective concept of "failed to."

## What's deliberately not in these documents

Implementation specifications are not here. Each document includes a brief note on expected implementation scope, but the actual specification work is for a planning cycle that has not yet started. The concept docs exist so that planning cycle has a coherent target to work toward.

Exact API designs are not here. The documents describe what components do, not how they expose interfaces. Interface design is downstream of implementation choices that will be made later.

Specific training parameters are not here. The methodology document names threshold ranges and weighting heuristics but treats them as calibration concerns that emerge from empirical work rather than from design decisions. Pretending to certainty about exact numbers would be over-claiming.

Immediate work scope is not here. None of these documents proposes anything that should be implemented in the current Cerebra phase or the next two or three phases. The extension is post-v0.1 work, distributed across whatever future phases bring it into active design.

## Notes on the methodology amendment

A refinement to the methodology document emerged after it was drafted and is worth recording here. The doc proposes a single strong tier (Opus 4.7 high-effort) for corrective amendments, with variation across iterations to avoid teacher bias. A complementary approach is *within-iteration multi-teacher pipelining*: run the corpus through Sonnet 4.6 first, then through a different vendor's model (ChatGPT 5.5 or similar), then finish with Opus 4.7. Each pass catches different kinds of errors the previous pass missed, and ending with a deliberately chosen final model controls the stylistic and reasoning conventions that ultimately shape the corpus.

This is not in the methodology document itself but is a notable extension. Within-iteration variation produces immediate diversity in the corrective signal; across-iteration variation produces long-run robustness against any single teacher's idiosyncratic biases. Both approaches are compatible and both should probably be used in practice. The methodology doc may be amended to reflect this when the next revision cycle reaches it.

## Status of the collection

These documents are working artifacts, not final designs. They will be revised as the architecture's empirical context develops. Several open questions in each document will only be answerable after the architectural components have been built and run for some time, and the answers will likely require updates to the conceptual framing.

The collection's value is not in being correct in every particular. It is in being *coherent across the four documents* — a unified architectural direction articulated clearly enough that future work can target it deliberately, even when the specifics evolve. The unity of the vision is what makes the documents worth keeping together; the openness of the individual claims is what makes the documents worth revising as understanding develops.

When you return to this material, expect to find things you would phrase differently now. That is the point. The documents are meant to record the moment the architecture became coherent enough to write down, not to fix that moment as final. Coherence at a moment is enough to build forward from; finality would be premature.

---

*This document is the fifth and navigational of five concept documents. It depends on no other document but rather provides the entry point for the other four. The series describes a cognitive architecture extension to Cerebra that emerged during a working session on Phase 3 design review.*
