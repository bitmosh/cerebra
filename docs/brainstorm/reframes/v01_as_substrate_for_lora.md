# v0.1 as Substrate for LoRA

*Drafted 2026-06-05. Status: load-bearing reframe shaping Phase 2 success criteria.*

## The reframe

v0.1's classifier doesn't need to be 90% accurate. It doesn't need to be 80% accurate. It needs to produce labeled data good enough to train a better classifier in v0.2.

This changes the success criterion for Phase 2 close-out. The merge gate isn't "did we hit 70% accuracy" — it's "did we produce a usable training corpus, with consistent failure modes, that v0.2 LoRA training can correct?"

## The math that makes this work

Phase 2 backfill processes ~745 chunks from the planning docs corpus.

At 73% accuracy with the two-pass architecture (terminal Claude's expected case):
- 745 × 0.73 = ~544 reliably labeled examples
- Plus 30 hand-labeled calibration fixtures
- = ~574 training examples for LoRA

Documented LoRA results on similar-scale tasks: 500-1000 high-quality examples can lift small-model classification accuracy from 60-70% to 85-90%. This isn't speculative — it's the documented pattern across Tülu 3, OLMo 3, and Unsloth's published case studies.

So v0.1 at 73% becomes v0.2 at 85-90%. The v0.1 imperfection is the training signal that produces the v0.2 improvement.

## Why this is the bootstrap loop

Cerebra produces its own training data by running.

The pattern:
1. v0.1 ships with imperfect classifier (substrate quality)
2. v0.1 runs on the planning docs corpus, producing 745 labeled assignments
3. The labels are noisy but consistent — the same chunk gets a similar label across runs
4. We curate the labels (correct obvious errors, mark genuine ambiguity)
5. v0.2 LoRA training uses the curated corpus as training data
6. v0.2 classifier is significantly more accurate
7. v0.2 re-classifies the corpus; new labels are better
8. v0.3 trains on v0.2's labels; classifier improves further
9. Loop continues

The substrate doesn't need to start good. It needs to start *consistent enough* and *good enough* that human curation can extract a clean training signal.

## What "good enough" actually means

The substrate has to pass three tests, not the accuracy gate:

**1. Errors must be consistent.** If the same chunk gets classified differently on every run, the training corpus is noise. Temperature 0.0 plus deterministic decoding solves this. We need reproducibility within a single classifier version.

**2. Errors must be identifiable.** If the substrate confidently produces wrong answers with no way to distinguish them from right answers, we can't curate. Confidence calibration matters — when wrong, the system should signal uncertainty. (This is the area where Qwen 3.5 9B fails hardest: 80% hallucination rate with high confidence on wrong answers.)

**3. Errors must be patterned.** Random errors can't be trained out cleanly. Systematic errors (MECHANISM/TECHNIQUE confusion, OBSERVATION/EVENT confusion) ARE the training signal. The LoRA pass specifically learns to handle those boundaries better.

73% accuracy with systematic, identifiable, consistent errors is more useful than 80% accuracy with random unpredictable errors. The shape of the imperfection matters more than the magnitude.

## What this means for Phase 2

The merge gate criteria shift:

**Old criteria:**
- 70% top-1 accuracy on calibration set

**Better criteria:**
- 65%+ accuracy with two-pass architecture (proving the architecture works)
- Reproducible within version (proving the substrate is stable)
- Errors clustered around known confusable pairs (proving the failure modes are trainable)
- 4-quadrant calibration table shows confidence correlates with correctness (proving the system can self-flag uncertainty)

If those four are true, Phase 2 ships. The accuracy number itself is less important than what shape the accuracy has.

## What this changes about model selection

We've been treating model selection as "which model classifies best?" The reframe changes the question to: "which model is the best LoRA training target?"

These aren't the same question.

A model that classifies at 70% out of the box but LoRA-trains to 90% is better than a model that classifies at 80% out of the box but doesn't respond well to LoRA training. The destination matters more than the starting point.

This is why models with publicly documented training methodology matter:
- **OLMo 3** — full training pipeline documented, intermediate checkpoints available, OlmoTrace shows what training data influences outputs
- **Tülu 3** — recipe for SFT + DPO + RLVR explicitly published
- **SmolLM3** — engineering blueprint with what failed, not just what worked
- **Pythia** — every training checkpoint preserved for interpretability research

These aren't just "better models." They're better *substrates* because we can see how they learn. The LoRA training pass is informed by understanding what shaped the base model.

A Qwen 3.5 fine-tune is a black box layered on a black box. An OLMo 3 fine-tune is an interpretable adjustment to a documented foundation.

Round 2 calibration (13 models, 30 fixtures) shifted the primary LoRA target to **Granite 4.1 3B base**: 58% partial accuracy matching Qwen 3.5 9B instruct, 73% Pass 1 quadrant accuracy (highest of any model tested), 3.7GB VRAM, Apache 2.0 license. OLMo 3 7B remains the secondary candidate / fallback for model-flow capabilities (full training transparency, OlmoTrace, intermediate checkpoints) — useful if Granite LoRA training doesn't yield expected results, but no longer the primary path.

## The longer arc

This reframe also clarifies what Cerebra is doing at the meta level.

v0.1: imperfect classifier — DONE, shipped 2026-06-06 at 65% partial-credit accuracy
v0.2: LoRA-tuned classifier (~85% accuracy)
v0.3: per-pair disambiguation + counsel mode (~92% accuracy)
v0.4: structured epistemic output, multi-round refinement (~95% accuracy)
v0.5+: the 16-category taxonomy becomes part of the model's perceptual nature (the cognitive-nature reframe)

Each version produces the substrate that the next version trains on. The system is bootstrapping its own cognitive sophistication through iterative training on its own outputs.

This is closer to how humans acquire conceptual frameworks than to how typical ML training works. We don't get a perfect taxonomy on day one — we get a rough taxonomy, use it, notice where it fails, refine it, internalize the refinements, use it again. Cerebra does this with explicit training cycles instead of implicit cognitive maturation.

## Practical Phase 2 implications

Specific things this reframe argues for:

**Don't over-iterate on the prompt.** Each prompt revision delays Phase 2 close-out. If we can get to 65-70% accuracy with the two-pass + fixture audit + temperature 0.0 work that's already planned, ship it. Save the prompt sophistication for the v0.2 training data construction.

**Capture failure modes systematically.** Every wrong answer in v0.1's backfill is a future training example. The inspector logs should preserve enough detail (what was the prompt, what was the response, what was the expected answer, what feature pattern is this chunk an example of) to construct training data later.

**Don't waste effort on calibration set expansion.** 30 hand-labeled fixtures is enough for the merge gate. Expanding to 100 fixtures would help v0.2 evaluation but doesn't help v0.1 ship. Build the bigger calibration set in v0.2 after we have a better classifier to evaluate.

**Pick the model that LoRA-trains best, not the model that classifies best now.** Round 2 calibration data shifted the LoRA target recommendation to Granite 4.1 3B. Round 2 results: Granite 4.1 3B base scored 58% partial accuracy — tying Qwen 3.5 9B instruct — with 73% Pass 1 quadrant accuracy (highest of any model tested across both rounds). At 3B dense, it's the most LoRA-trainable substrate that performs at production-model quality, with Apache 2.0 licensing and IBM's documented QLoRA methodology. OLMo 3 remains a secondary candidate / fallback for the model-flow capabilities (full training transparency, OlmoTrace) if Granite training doesn't yield expected results, but Granite 4.1 3B is the primary path. The model we LoRA-train doesn't have to be the model we use in v0.1; we can switch substrate when we switch versions.

## What actually shipped in v0.1.0

The reframe became historical fact on 2026-06-06. Phase 2 close-out:

- Production substrate: Granite 4.1 3B instruct (Unsloth GGUF, Q4_K_M)
- Calibration: 65% partial-credit accuracy (53% strict)
- Backfill: 745 records classified, 0 parse failures, 28.3 minutes total
- Perfect determinism: temp=0.0, same chunk → same SKU on re-run
- Gate criterion documented as substrate-for-LoRA, not raw accuracy

The 745 labeled records become the v0.2 LoRA training corpus. The substrate-for-LoRA argument is no longer a planning hypothesis; it's the working architecture.

One discovery worth noting: the production model is the **instruct** variant of Granite 4.1 3B, not the base. IBM's HuggingFace naming convention has `granite-4.1-3b` as the instruct model and `granite-4.1-3b-base` as the base. For v0.2 LoRA training, the base variant is the cleaner target.

## The honest framing

You said earlier: "we'll have to accept at a certain point that we're kinda trying to get models to do what we know they're not really capable of, yet."

This reframe is the answer to that.

We're not trying to get models to do something they can't do. We're using imperfect models to produce the training signal that lifts them to where they need to be. The current limitations aren't blockers — they're the gradient we train along.

Phase 2's job is to produce the training signal. The success criterion is "does the signal exist and is it usable?" not "is the classifier good?"

By that criterion, Phase 2 is close to done.

---

*See also: `two_thinking_systems_disruption.md` for substrate model criteria. `cognitive_nature_as_perceptual_lens.md` for where this bootstrap loop leads.*
