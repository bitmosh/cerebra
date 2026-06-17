# Dark Matter Substrate

*Concept document — drafted 2026-06-12 following the iterative self-improvement methodology series. Captures architectural additions that emerged from working through the gap between sub-threshold interpretations and training corpus production. Status: open exploration, not implementation scope. Companion to the interpretive lattice, archetypal lenses, evaluative frame, and iterative self-improvement concept documents.*

---

## What this concept addresses

The interpretive lattice handles confidence-gated multi-commit at threshold and above. The methodology document specifies how committed records become training corpus. Between them sits a gap: sub-threshold interpretations are discarded, and the information they carry about the classifier's cognitive operation is lost with them.

This document addresses that gap. Sub-threshold interpretations are not noise to be filtered out. They are *dark matter* — invisible in the system's committed output but informationally rich about the system's operation, and especially valuable as raw material for training the model to be better at the cognitive operations it currently performs imperfectly. The document specifies how this dark matter gets captured, classified, and used.

The architectural commitment underneath the work in this document is that the system's *failures* and *near-misses* are training material rather than waste. That commitment is substantively different from the implicit stance most ML systems take, where training data is sourced externally and failures are diagnosed reactively rather than captured systematically. Cerebra's architecture, with the lattice and the inspector substrate already in place, is well-positioned to take a different stance: the system produces its own training corpus as a side effect of operating, and the corpus is richer when it includes what the system *almost* committed to alongside what it actually committed.

The implications reach further than they first appear. A system that systematically captures its dark matter and uses it for training is *self-supervised in a specific way* that most systems are not. The supervision signal is not external labels but the system's own confidence distributions, paired with corrective context that turns near-misses and wrong-but-instructive interpretations into structured training pairs. Over time, the system gets better at the cognitive operations it performs by training on the residue of those operations. The architecture builds in continuous-improvement substrate rather than treating improvement as something that happens between training runs.

## The three-class shadow structure

The classifier produces a confidence distribution over all SKU categories per chunk. The lattice handles entries above the commit threshold by writing them as sibling records. Everything else is currently discarded. The dark matter substrate captures *some* of what is currently discarded, classified by what it can tell the system about its own operation.

**Near-miss shadows** are sub-threshold interpretations whose confidence was close to the commit threshold. Specifically, interpretations whose confidence falls in the range from a configurable lower bound up to the commit threshold itself. The system considered these interpretations strongly enough that they almost committed. They are *adjacent* to the committed interpretations in the sense of being almost-committed alternatives, and they carry information about the cognitive neighborhood of the chosen interpretation. When the system retrieves a record, the adjacency of its near-misses informs how *singular* the committed interpretation actually was: a record whose nearest non-committed sibling scored 0.55 is interpreted with more confidence than a record whose nearest non-committed sibling scored 0.63.

Near-miss shadows are not retrieved by default. They sit alongside the committed records as context, queryable by lineage but not surfaced in normal retrieval results. They become visible to downstream cognition when meta-cognitive operations request them — for instance, when the system is reasoning about how confidently to hold a particular interpretation, or when a query needs to consider the adjacency of an interpretation rather than just the interpretation itself.

**Transmutation candidates** are sub-threshold interpretations that fall in a different range: confidence meaningful enough to indicate the classifier was *engaged* with the interpretation but not high enough to be a near-miss. These represent cases where the classifier produced a competing signal that wasn't quite a real alternative. The system was tempted by an interpretation that the threshold correctly rejected, but the rejection alone doesn't capture *why* the temptation existed.

These are the interpretations that benefit most from corrective training. The system was wrong in a particular way — wrong with structure, not wrong randomly. The transmutation candidate, paired with the right interpretation and a structured explanation of the difference, becomes a training example richer than any synthetic exemplar could be. The system learns not just "the right answer is X" but "here is what tempted you toward the wrong answer, here is the structural feature that distinguishes the right answer from the wrong one, here is how to recognize the distinction in future cases."

**Noise-filtered shadows** are the rest. Confidence too low to indicate the classifier was meaningfully engaged. Recording these would be expensive and would produce no usable signal. They are dropped at capture time. The threshold below which an interpretation is classified as noise rather than transmutation candidate is itself tunable.

The three classes correspond to three different downstream uses. Near-misses inform retrieval-side cognition about adjacency. Transmutation candidates feed the training pipeline. Noise-filtered shadows are discarded. The classification happens at capture time based on the confidence range. The thresholds bounding each class are tunable parameters that, like the commit threshold itself, should be evaluated across training cycles rather than fixed once.

## What the dark matter table holds

The substrate is a single new table linked by lineage to the committed records. The schema is straightforward but the field choices matter.

```
lattice_shadows
  shadow_id           TEXT PRIMARY KEY
  chunk_id            TEXT NOT NULL  (FK to chunks)
  candidate_d1        INTEGER NOT NULL  (the category considered)
  candidate_confidence REAL NOT NULL  (the score it received)
  commit_threshold_used REAL NOT NULL  (what it failed to clear)
  shadow_class        TEXT NOT NULL  (near_miss | transmutation_candidate)
  classifier_version  TEXT NOT NULL  (which classifier produced this)
  primary_record_id   TEXT  (the record that did commit for this chunk, nullable if abstained)
  sibling_record_ids  TEXT  (JSON list of any lattice siblings that also committed)
  shadow_metadata_json TEXT  (forward-compat for lens/frame metadata)
  created_at          INTEGER NOT NULL
  schema_version      INTEGER NOT NULL DEFAULT 1
```

Several design choices in this schema deserve explicit attention.

The shadow is linked to the chunk, not to the primary record. This is important. A chunk that abstained (no committed record because all interpretations were below threshold) still produces shadows — the abstention itself is a cognitive event worth examining, and the shadows record what the system was tempted by even though it declined to commit. The primary_record_id is nullable so abstained chunks can still have their shadows recorded.

The classifier_version field is mandatory. Shadows are produced by a particular model at a particular point in its training history. When the model changes, old shadows become evidence about the *old* model's behavior, not the current one. Distinguishing them matters for training corpus quality. Mixing shadows from multiple classifier versions without attribution would produce corpus pollution that would be invisible until the resulting training run produced surprising regressions.

The shadow_metadata_json field is reserved for future use. When the lens system lands, individual lens activations may produce their own confidence distributions; when the evaluative frame lands, deviation chains may need to be captured. Both are downstream of the lattice commit decision and could be associated with the shadow that resulted. The JSON column gives that future work somewhere to put its metadata without requiring a schema migration. The same forward-compat instinct that gave Phase 5's working_memory_items its interpretive_lens and frame_metadata_json columns applies here.

The sibling_record_ids field captures the multi-commit context. If the chunk produced two sibling records and three near-miss shadows, each shadow record contains the IDs of both siblings. Reconstructing the full cognitive operation around a single chunk is possible from any single shadow record, which matters when the shadow is selected for training but the surrounding context is needed to make the training example structured.

The table is forward-only, no updates after insert. Shadows are immutable records of cognitive events. If the classifier later improves and the same chunk would no longer produce the same shadow, the historical record remains intact. The historical record is the training corpus; rewriting history would destroy training data integrity.

## The capture pipeline

Shadow capture sits alongside lattice commit, not in place of it. When the classifier produces a confidence distribution, three things happen in sequence.

The committed interpretations are written as memory records — primary alone if only top-1 cleared threshold, primary plus siblings if multi-commit triggered. This is the existing lattice behavior, unchanged.

Then the confidence distribution is examined for shadows. Each non-committed interpretation has its confidence compared against the shadow class thresholds. Near-miss interpretations and transmutation candidates produce lattice_shadows rows. Noise-filtered interpretations are dropped.

Finally, a `LatticeShadowsRecorded` inspector event fires per chunk, listing the chunk_id, the shadow_ids produced, and the class distribution (how many of each class). This event is the audit trail for the dark matter substrate's operation, and it joins the existing `LatticeCommit` event as part of the cognitive operation's full inspector record.

The capture pipeline is lightweight in performance terms. The classifier's confidence distribution is already computed; capturing it differently is a write-path addition, not a computation addition. The storage cost is bounded — shadows have no embeddings (their primary record carries the embedding that retrieval will use), and the JSON metadata is small. A vault with a million chunks would have at most a few million shadows, with most chunks producing zero shadows, some producing one, and the long tail producing the rest.

## The transmutation training pattern

Transmutation candidates are the substrate's most valuable output for training. The pattern for using them takes structured form.

The transmutation pipeline reads transmutation_candidate shadows alongside the committed records they almost competed with. For each shadow, it constructs a training example with three parts. The chunk itself, which the model needs to recognize. The model's confidence distribution at classification time, including both the committed interpretation and the transmutation candidate's near-miss confidence. The corrective context that explains why the committed interpretation is right and the candidate is wrong, structured so that the model can learn the distinction rather than just memorize the answer.

The corrective context comes from multiple sources, ordered by training value.

The first and most valuable source is *direct precedent*. The retrieval substrate is queried for cases where the same classifier successfully committed to the same SKU category for chunks structurally similar to the current case. These are *self-referential* training examples: the model is shown its own correct past behavior in adjacent cases, paired with the current case where it failed. The differential between the successful cases and the failed case becomes the lesson. "Here is what you got right in cases A, B, and C. Here is what you got wrong in case D. Here is the structural feature that distinguishes case D from the others, which you should have attended to."

When direct precedent is unavailable — when the classifier has no record of getting this category right on similar chunks — the pipeline falls back to *adjacent precedent*. Cases where the classifier got related but not identical categories right. The training value is lower because the transfer is less direct, but the structure is still self-referential and still preserves the model's own representational quirks.

When neither direct nor adjacent precedent is available, the pipeline falls back to *synthetic exemplars*. Cases crafted by the corrective system to demonstrate what the right interpretation looks like. These have the lowest training value because they introduce content that doesn't share the model's representational quirks, but they are the only fallback when the model has no past success to point to.

The hierarchy is honest about what produces good transmutation training. The model learns most from being shown its own successes paired with its current failures. The model learns less from synthetic counter-examples that may or may not transfer cleanly. The pipeline tries the highest-value source first and falls back only when necessary.

## The scribe as shadow curator

The scribe pattern described in the iterative self-improvement document gets a concrete role here. The scribe is the agent that captures shadows, triages them, and curates them into training pairs.

The scribe's responsibilities, articulated as specific cognitive operations:

Reading the lattice's confidence distributions as they are produced, classifying each non-committed interpretation by its shadow class, writing the appropriate lattice_shadows rows.

For transmutation_candidate shadows, running the retrieval queries needed to construct the corrective context. The scribe queries the substrate for direct precedent, falls back to adjacent precedent, and falls back further to synthetic exemplars when needed. The fallback hierarchy is the scribe's logic; the corpus it operates against is the system's own memory.

Assembling the structured training example with chunk, confidence distribution, committed interpretation, and corrective context. The scribe's output is a training-pair record ready for the LoRA training pipeline to consume.

Capturing meta-information about each curation decision — which precedent type was used, why the fallback happened if it did, what the structural feature of the corrective context is. This meta-information becomes the audit trail for the training corpus and is itself training data for future scribe iterations.

The scribe is informed of its role and purpose. The witness pattern from the iterative methodology document applies: the scribe knows what it is, what it is doing, and why. The training data it produces will train future model iterations, which is useful context for the scribe to operate well rather than information to withhold. The scribe's specific operations are named (capture, classify, query precedent, assemble training pair) rather than left as abstractions like "be a good scribe."

## Connection to the existing architecture

The dark matter substrate slots into the existing architecture without disturbing what is already shipped.

The lattice produces confidence distributions; shadow capture is a write-path addition that reads those distributions. Existing lattice behavior is unchanged.

The inspector substrate's events table already captures LatticeCommit events; LatticeShadowsRecorded joins it as a sibling event type. No schema changes to inspector_events are needed.

The retrieval substrate operates against memory_records; shadows are not in that table and do not surface in normal retrieval. The retrieval substrate is unchanged.

The working memory and truth tower substrates from Phase 5 operate against committed memory records; they have no interaction with shadows. Phase 5 is unchanged.

The lattica observability layer reads inspector events; LatticeShadowsRecorded events become visible to it automatically. The shadows table itself becomes queryable for the dark-matter view that observability layer might want to expose. Lattica gains new capability without architectural friction.

When the LoRA training pipeline is resumed, the corpus it trains against gains the transmutation pairs the scribe has been curating. This is the substantive change: the LoRA bench was about corpus inadequacy, and the dark matter substrate is what addresses that inadequacy structurally. The training corpus is no longer limited to manually-curated calibration sets; it grows as the system operates, with the scribe converting operational experience into structured corrective training material.

## What the dark matter substrate is and is not

The substrate is *captured cognitive operation*. It records what the classifier almost committed to, paired with what it actually committed to, structured for downstream use. The substrate is *operational* in the sense that it is produced as a side effect of the system running, not as a manually-curated artifact.

The substrate is not *memory* in the Cerebra sense. Memory records are committed interpretations the system stands behind. Shadows are non-committed interpretations the system considered. Conflating them would lose the architectural distinction that gives the substrate its training value. Shadows are *evidence about the system's cognitive operation*, not evidence about the world the system is reasoning about.

The substrate is not *abstention*. Abstention is the substrate-level silence operator — the system refusing to commit to any interpretation. Shadows can be produced alongside abstention (every interpretation was sub-threshold, producing shadows but no committed record) or alongside commit (some interpretations cleared threshold, others did not). The two are independent: shadow capture happens regardless of whether abstention triggered for a given chunk.

The substrate is not a *training pipeline* in itself. It is the substrate that feeds training pipelines. The transmutation training described above happens *against* the substrate; the substrate stores the raw material. Building the training pipeline that consumes the substrate is its own work, downstream of having the substrate to consume.

## Open questions

The thresholds bounding each shadow class are calibration parameters that have not been pinned down. Initial proposal: near_miss is confidence in [0.50, commit_threshold); transmutation_candidate is [0.25, 0.50); below 0.25 is noise. These ranges are reasonable starting points but should be evaluated empirically against held-out test data once the substrate is populated.

The volume of transmutation candidates produced by routine operation is unknown until the substrate runs against the existing corpus. The estimated volume of one or two shadows per chunk on average could be off by an order of magnitude in either direction. Storage planning depends on this estimate; calibration of how aggressively the transmutation training pipeline samples depends on it too. Empirical question that gets answered once the substrate is operational.

The relationship between shadow capture and the LoRA training cadence is not specified. Options include: capture shadows continuously, batch-process them into training pairs on a scheduled cadence; capture shadows continuously, process them on-demand when a training run is triggered; capture shadows but flag them for human review before training pair construction. Each has tradeoffs. The first is most automated but produces training pairs that may not have been reviewed for quality. The third is most careful but adds human-bottleneck latency. The middle ground is probably right but the calibration is not settled.

The role of multi-model amendment in transmutation training is partially specified by the existing methodology document but not yet integrated with the dark matter substrate. The proposed within-iteration multi-teacher pipeline (Sonnet then ChatGPT then Opus, with an Anthropic model finishing) applies to transmutation pairs once they exist. The substrate produces the pairs; the multi-teacher pipeline refines them. The exact integration is design work for when the transmutation pipeline becomes real.

Whether shadows should also be produced by the lens system once it exists is a deeper architectural question. Lens activations produce their own confidence distributions; capturing sub-activation interpretations as lens-shadows is a natural extension of this pattern. But the lens system itself does not yet exist, and committing to lens-shadow capture now is premature. Worth noting that the shadow_metadata_json field is reserved for exactly this kind of future extension.

## What this document is and is not

This is a concept document, not an implementation specification. It articulates an architectural addition that fills a gap visible in the existing concept document series. The implementation depends on choices that will be made when the substrate is built, on capabilities that do not yet exist (the scribe, the multi-teacher amendment pipeline), and on calibration that has not been performed (the shadow class thresholds, the storage budget).

Implementation is post-v0.1 and follows the lattice, lens, and frame implementations. The substrate can begin in a limited form earlier — even without the lens or frame components, the lattice produces confidence distributions that can be captured. A minimal first pass might be: shadow table, capture pipeline, LatticeShadowsRecorded event. The scribe and transmutation pipeline come later, building on a populated shadow table.

Expected scope when full implementation begins:

- Migration adding the lattice_shadows table with the schema specified above
- Shadow capture in the classifier write path, alongside existing lattice commit logic
- LatticeShadowsRecorded inspector event with the appropriate payload
- Scribe interface for shadow curation, separate from the capture pipeline
- Transmutation training pipeline reading from the shadow table and producing training pairs
- Eval-core suite specifically targeting shadow-class threshold sensitivity across training iterations
- Documentation for what shadows can and cannot be used for

Estimated implementation scope: substantial, distributed across multiple Cerebra phases as the dependencies stabilize. The first three items in the list above could be implemented in a v0.3 or v0.4 release if prioritized; the scribe and transmutation pipeline are likely v0.5+ as they depend on a substantial corpus of accumulated shadows.

The document exists so the architectural commitment is captured while it is clear, in the same way the lattice and lens documents captured their respective architectural commitments before their implementations began. The substrate described here is the methodology gap that the LoRA bench surfaced but did not name. Naming it explicitly is what permits the next implementation cycle to address it deliberately rather than rediscovering it during yet another bench.

---

*This document extends the iterative self-improvement concept document. It depends on the interpretive lattice concept document for the multi-commit substrate it builds upon, and on the evaluative frame concept document for the inspector-event vocabulary it uses. A reader new to the concept series should start with the cognitive extension overview document and read the lattice, lens, frame, and methodology documents before this one.*
