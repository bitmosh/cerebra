# Interpretive Lattice

*Concept document — drafted 2026-06-09 during Phase 3 review. Status: open exploration, post-v0.1 architectural direction. Not implementation scope; companion to forthcoming documents on archetypal lenses, the evaluative frame, and iterative self-improvement methodology.*

---

## The problem this concept addresses

Cerebra's current SKU classification commits each chunk to a single D1 category at ingest time. When the classifier's confidence is clear — a strong top-1 with everything else far below — this works well. The chunk lands in one position in the substrate, and downstream retrieval and reasoning proceed from a clean foundation.

The mode where this breaks is interpretive ambiguity. Some chunks legitimately occupy multiple categorical positions simultaneously. A description of an architectural decision that turns on a constraint is both DESIGN and CONSTRAINT — and the *relationship* between those interpretations is itself the meaning of the chunk. Forcing a single classification erases that relational content. The system commits to one label, discards the alternatives along with their reasoning, and the chunk's true interpretive shape is lost before it ever enters the substrate.

The interpretive lattice is a proposal to stop erasing that information. Instead of forcing single commitment under interpretive ambiguity, the system commits to *every* interpretation that meets a confidence threshold, with the commits linked as siblings. The chunk's place in the substrate becomes not a point but a small constellation — a footprint across the SKU category space rather than a single coordinate. This footprint is the chunk's interpretive shape, preserved rather than collapsed.

This is not a generalization of "top-k retrieval." Top-k operates at the answer layer: take multiple results, fuse them at the end. The lattice operates at the *substrate* layer: commit multiple interpretations of the same source content into memory, each one fully addressed, each one independently traversable. The downstream consequences differ substantially. Top-k fusion produces one answer that draws on several results; lattice multi-commit produces several memory entries that can each generate their own answers, retrievals, and downstream connections.

## The core mechanism: confidence-gated multi-commit

When the SKU classifier evaluates a chunk, it produces a confidence distribution across the sixteen D1 categories. In current Cerebra, the system reports the top-1 and discards the rest. The lattice proposal instead inspects the full distribution and writes a memory entry for *every category* whose confidence clears a defined threshold.

The threshold matters semantically. The proposal is a floor of 65%. Below that, the system isn't expressing belief in an interpretation; it's expressing a guess. Multi-committing to guesses pollutes the lattice with noise that future retrieval and training would have to work around. With the floor in place, "this chunk multi-committed" means something specific: the classifier believed *more than one interpretation* of this chunk was credible. That semantic precision is what makes the lattice useful as a structure rather than just a larger memory footprint.

A chunk that produces 78% DESIGN and 71% PRINCIPLE and 42% TOOL becomes two memory entries — one anchored in DESIGN, one in PRINCIPLE — with the TOOL interpretation discarded. A chunk that produces 88% MECHANISM and 31% spread across everything else becomes one memory entry. A chunk that produces 58% top-1 across the board becomes *no* memory entry and routes to the uncertain pool (discussed below). The threshold encodes a minimum standard for what the system is willing to commit to.

The implementation footprint is small. The memory record schema requires a sibling-lineage column connecting multi-commit entries to each other. The ingest pipeline requires modification to write multiple records per chunk when the threshold conditions are met. The retrieval pipeline requires lineage-aware deduplication (treated below). Nothing in current Cerebra storage prevents this — the substrate just hasn't been used this way yet.

## Two failure pools, two corrective treatments

The threshold creates a natural partitioning of chunks the classifier got *wrong*. The distinction matters because the two failure modes need fundamentally different corrective approaches.

**Above-threshold failures** are overconfident wrongs. The classifier committed to DESIGN at 78% confidence and the correct answer was PRINCIPLE. The model wasn't uncertain — it had a clear belief, and the belief was wrong. The corrective signal for these chunks isn't "here's a better answer." It's "your confidence was misplaced; here's why the surface signal you attended to misled you." The amendment names the attractor that pulled the model toward the wrong commit.

**Below-threshold failures** are calibrated uncertainties. The classifier produced no commit because no interpretation cleared the floor. Its calibration was honest — it didn't pretend to know. What it lacked was a path *to* an answer when the surface signal was ambiguous. The corrective signal for these chunks teaches resolution strategies: "here are the lens shifts, contextual lookups, or reasoning sequences that would have produced a confident answer." The amendment names the moves the model could have made to escape the ambiguity.

These are different teachings, and they need to be kept separate in training corpus design. A corpus that conflates overconfidence-corrections with uncertainty-resolutions teaches contradictory lessons: "be less confident" and "find ways to commit when uncertain" pull in opposite directions. The lattice substrate makes the distinction structural — chunks land in one pool or the other based on where their original confidence fell — and downstream corrective work can target the appropriate failure mode rather than averaging across both.

The two pools also have different revisitation cadences. Overconfident failures, once corrected, are useful immediately as training data and as evidence of where the classifier needs recalibration. Uncertain-pool chunks need patience — they may resolve naturally as more context becomes available (related chunks arriving, lenses activating, the classifier itself improving), and forcing premature resolution defeats the purpose of having put them there. Both pools are part of the substrate's memory; neither is a discard pile.

## Branches as the natural data structure

The lattice is naturally expressed as a branched event log. A chunk arrives; the initial classification appends a base event. Each interpretation that clears the threshold appends a branch from that base, with its own commit event and its own subsequent retrievals, modifications, and relationships. The chunk's interpretive footprint is literally the set of active branches descending from its initial event.

This shape suggests an architectural direction that goes beyond the current Cerebra inspector events. The existing event log is linear and append-only — adequate for the events it currently captures, but not naturally extensible to the lattice's branching semantics. A separate planning document (currently described as a TypeScript-first event-sourcing toolkit, to be re-targeted as Rust core with Python and TypeScript bindings) describes a substrate that provides exactly what the lattice needs: content-addressed events, cheap branches sharing parent storage, replay determinism, time-travel queries.

The integration path is not immediate. Phase 3 of Cerebra shipped with the current inspector-events table, which can support an initial lattice implementation. Future versions can migrate to the event-sourcing substrate without losing existing data — the events are forward-compatible by design. What the lattice concept needs from Cerebra in the near term is awareness that this direction exists, so storage and retrieval interfaces don't accidentally close doors that future architectural work will want open.

The deeper point is that branches make the lattice's reasoning *replayable*. Every multi-commit decision, every lens evaluation that fed the commit, every retrieval that touched a particular interpretation — all of it becomes a queryable trace. The system can answer questions like "show me how this chunk's DESIGN interpretation evolved over the last month" or "branch from the moment this chunk was classified and replay with a corrected lens" or "find every chunk whose multi-commit was later resolved to a single interpretation, and show me what made the resolution clear." None of these queries are tractable in a flat event log; all of them become natural in a branched one.

## Training signal multiplication

This is the property worth being most attentive to.

A chunk multi-committed to several categorical paths has, by construction, several different positions in the substrate. Each position has its own SKU address, its own retrieval anchoring, its own set of relationships to surrounding memory. When the cognitive runtime interacts with the chunk through retrieval, consolidation, contradiction-detection, or prediction, it generates signal about *which interpretation was useful in which context*.

Over enough usage, this produces data of a particular shape: not "what category is this chunk?" but "for what kind of query did this chunk's DESIGN interpretation serve well, and for what kind of query did its PRINCIPLE interpretation serve well?" The lattice is *labeled by use*. The interpretations carry usage histories. The histories tell future training systems not just "here are the classifications" but "here are the classifications and how they actually performed against real queries."

Single-label classification can't produce this signal because it commits before observing how the commit gets used. The model picks an interpretation; that interpretation is either retrieved or not, queried against or not, but the *alternatives* never existed in the substrate, so there's no way to know whether they would have served better. The lattice preserves the alternatives long enough for usage to label them.

This is precisely the training signal the v0.2 LoRA work needs. The benched LoRA effort identified corpus imbalance as the blocking issue — the 214-record corpus had thin coverage of multiple categories because curation systematically filtered out ambiguous chunks. The lattice's multi-commit approach addresses this at the substrate level. Ambiguous chunks don't get filtered; they get multi-committed. Their interpretations get labeled by use. The resulting corpus has shape that single-label classification can't produce:

- Chunks with their full multi-interpretation footprints, not single labels
- Usage records linking each interpretation to query patterns
- Disagreement records where the lattice produced conflicting commits that consolidation eventually resolved
- Calibration records linking original confidence to eventual interpretation-correctness

A LoRA fine-tune on this corpus would be training on *interpreted experience* rather than on labeled examples. That's qualitatively different from what current SFT pipelines work with, and the difference is in the direction that the field's better methodologies have been moving. Process supervision, preference learning, and outcome-based reward modeling all share the property that the training signal comes from *what happened in the world* rather than from *what a labeler said*. The lattice produces this kind of signal natively, as a side effect of its normal operation.

## Costs and mitigations

This needs honest accounting because the proposal isn't free.

The storage cost is the most obvious. Multi-commit produces more memory records, SKU assignments, and graph nodes per chunk. At Cerebra's current vault size of 745 records, the cost is negligible. At 100,000 records it becomes noticeable. At 1,000,000 records it determines whether the system remains feasible on consumer hardware. The mitigation is structural rather than incidental: the 65% threshold ensures that most chunks commit to one category cleanly, and multi-commit only triggers when confidence is genuinely spread. Empirical estimate based on the existing 214-record classification corpus suggests perhaps 20–30% of chunks would multi-commit under this threshold, producing roughly 1.4–1.6× storage cost per chunk on average. This is survivable across the corpus sizes Cerebra is likely to reach in the next year or two, and the upgrade path to vector index alternatives like turbovec absorbs the additional load.

Retrieval ambiguity is the next concern. A query that semantically matches the DESIGN copy and the PRINCIPLE copy of the same source chunk could surface both, producing what appears to be a duplicate result. Two ways to handle this, and probably both apply contextually. Lineage-aware deduplication carries the multi-commit relationship in metadata, so the retrieval pipeline can show one entry and list the siblings as alternative interpretations. Alternatively, when the multi-commit structure is itself relevant to the query, the system can surface multiple sibling commits with explicit annotation that they share source content. The right default is probably deduplication for top-line results with the multi-commit structure exposed when downstream agents or human users ask for explanation of why a particular result was chosen.

Consolidation pressure is real but solvable. When the cognitive runtime eventually resolves which interpretation of a chunk was actually correct — through use, through contradiction detection, through explicit human correction — the wrong interpretations need to be retired without erasing the training signal they carry. Tombstoning the wrong commits but preserving them in the graph with full lineage handles this. They become invisible to normal retrieval but remain visible to audit, to consolidation traces, and to future training corpus extraction. The Phase 10 consolidation work will need to engage this directly, but the substrate accommodates the requirement without further design changes.

The most subtle cost is that the classifier becomes load-bearing in a new way. The 65% threshold is a parameter that affects storage, retrieval, training, and consolidation behavior simultaneously. Tuning it is non-trivial. Too generous and the lattice fills with weak commits that produce noise; too tight and the system collapses to single-commit behavior. The right long-term approach is to make the threshold *learnable* from system feedback — track which commits are retrieved, which are validated, which are eventually retired, and adjust the threshold to optimize for retrieval-utility per unit of storage. This is a long-running calibration concern rather than a v0.1 implementation task, but it's worth flagging now so future work doesn't treat the threshold as a fixed constant.

## Connections to related concepts

The interpretive lattice is the substrate of a larger architecture. Its concrete utility depends on what lives on top of it, and the companion concepts answer questions the lattice alone leaves open.

The archetypal lenses (forthcoming document) provide the mechanism by which multi-commit signal is actually generated. The lattice describes *what* to do when multiple interpretations clear the threshold; the lenses describe *how* multiple interpretations get produced in the first place. Rather than asking "what category does this fit?" the lens system asks "what does the Builder see in this? what does the Critic see? what does the Connector see?" Each lens produces an independent classification with its own confidence; the union of lens activations populates the lattice. Without the lens system, multi-commit is theoretically possible but practically rare, because most chunks have one obvious top-1 under a single classification view. With it, multi-commit becomes the natural shape of interpretation, because different lenses legitimately see different things in the same content.

The evaluative frame (forthcoming document) provides the mechanism by which lattice commits are checked for coherence. An eightfold-equivalent set of evaluative principles operates as a constitutional self-critique layer over commit decisions. Multi-commits that violate evaluative coherence — for example, commits to mutually-incompatible interpretations without acknowledgment of the tension — get flagged for human review or further reasoning. This keeps the lattice honest. It prevents multi-commit from degrading into "the system commits to everything and resolves nothing."

The iterative self-improvement methodology (forthcoming document) provides the training pattern by which lattice-extracted signal becomes model weights. Each iteration runs the model with the harness in place (lens system, evaluative frame, lattice substrate), captures the multi-commit data and usage labels, distills the captured data into a training corpus, fine-tunes the model on that corpus, and restarts with the improved model. Three iterations is a realistic horizon; gains diminish substantially after that as the easy patterns get internalized and what remains is harder. The lattice is what makes this methodology work — without preserved alternatives, there's no signal to extract; without usage labels, the signal isn't actionable; without iterative reapplication, the improvements don't compound.

These four concepts together describe a cognitive architecture extension that is post-v0.1 work but architecturally compatible with current Cerebra. Phase 3's storage layer, just shipped, is the substrate the lattice extends. Nothing in the lattice design requires changes to current storage code. The implementation path is incremental, additive, and reversible at every step.

## Open questions worth surfacing

These are uncertainties to resolve before implementation begins, and several of them are likely to remain open until empirical work clarifies them.

Threshold dynamics is the first. Is the 65% confidence threshold a system constant, or should it vary by category, by lens, by chunk characteristics? Some categories may have higher legitimate ambiguity than others; some lenses may be more confident on average than others; some chunk types may simply be more prone to multi-interpretation. The initial answer for v0.1 of the lattice is a constant threshold across the system, with the understanding that empirical data will eventually justify variation. The threshold's calibration becomes one of the system's tunable parameters once the lattice has been populated enough to study.

Pool revisitation cadence is the second. When do uncertain-pool chunks get revisited? Three reasonable strategies — opportunistically when related content arrives, on a scheduled batch cadence, or on-demand when retrieval explicitly requests them — and all three may have a role. The design question is how the pool interacts with the rest of the cognitive runtime, particularly with consolidation and with explicit human review workflows. This will be engaged when Phase 4 retrieval is designed.

Commit retirement semantics is the third. When consolidation decides that a multi-commit chunk should have committed to only one interpretation, what happens to the retired commits? Move them to a separate structure, tombstone them in place, archive them? Each option has tradeoffs for training-data extraction and for retrieval clarity. The lean is toward tombstoned-in-place for v0.1, with the option to migrate to a separate retired-commits structure if consolidation traces show this is needed. The training data extracted from retired commits is among the most valuable signal the system produces — it shows the model what *eventually* turned out to be wrong, which is more informative than what was wrong at the moment of commit.

The relationship between lattice lineage and existing SKU D4 semantic edges is the fourth question. The SKU substrate's D4 relationship axis already encodes inter-record relationships of sixteen types. The lattice produces additional relationships — the "this chunk also exists as X" pointers that connect sibling interpretations of the same source content. Are these the same kind of edge or different? The proposal here is different: SKU D4 edges connect *different chunks*; lattice lineage edges connect *interpretations of the same chunk*. These are distinct enough to warrant separate edge types in the graph schema, both for clarity of meaning and for retrieval performance when traversing one without the other.

Performance under load is the fifth. At what corpus size does multi-commit start degrading retrieval performance noticeably? This is an empirical question that can't be answered without testing. Phase 4 retrieval implementation should include benchmarks that vary multi-commit ratio and measure query latency under realistic load.

## What this document is and isn't

This is a concept document, not an implementation specification. It articulates the *what* and the *why* of the interpretive lattice. The *how* depends on the related concept documents (lenses, frame, methodology) and on the runtime substrate (current Cerebra inspector events, eventual event-sourcing toolkit integration).

Implementation is post-v0.1. The current Cerebra storage layer is compatible with eventual lattice implementation but does not pre-build the multi-commit machinery. When implementation begins, the expected scope is moderate: schema additions for sibling lineage, a classifier interface change to return confidence distributions rather than single labels, ingest pipeline modifications to write multiple records under threshold conditions, retrieval pipeline modifications for lineage-aware deduplication, and consolidation pipeline additions for commit retirement when interpretations are eventually resolved. Estimated implementation effort: one to two weeks once the related concept documents are in place and a planning cycle dedicates time to the work.

The document captures the concept at the moment it became coherent. Future amendments will refine it as the related concepts develop and as Phase 4 (retrieval) provides empirical context that the current substrate-only view can't supply. Treat this as a starting point that will evolve, not as a finished design.

---

*This document emerged during Phase 3 design review on 2026-06-09 following a conversation about the limits of single-label classification and the possibility of preserving interpretive ambiguity as a first-class memory property. It is the first of four planned concept documents describing a post-v0.1 cognitive architecture extension.*
