# Cognitive Nature as Perceptual Lens

*Drafted 2026-06-05. Status: long-term vision document. v0.5+ destination.*

## The destination

We eventually want the 16-category classification to be an inherent part of the model's cognitive nature. Then the model uses that perceptual lens to continue to retrain and adjust itself through that.

The categories aren't labels the model applies. They're the structure through which the model perceives. The shift is from "model that labels things as MECHANISM" to "model that sees mechanisms" — where MECHANISM is a way of seeing, not a verdict applied to seen things.

This is the v0.5+ direction. It's worth being explicit about now because it shapes intermediate design choices.

## How humans acquire conceptual frameworks

The analogy that makes this concrete: how humans acquire conceptual structures.

When a child first learns about cats, they label individual cats. "That is a cat. That is a cat. That is also a cat." The category CAT is something the child applies to perceptions.

After enough exposure, the category disappears as a separate cognitive step. The child doesn't think "I see something. Let me determine if it's a cat. Yes, it's a cat." They just see cats. The category became part of perception itself.

Same with adults learning new domains. A novice radiologist examines an X-ray and consciously runs through a checklist: "Are there opacities? Is the heart enlarged? Are the lungs symmetric?" An experienced radiologist looks at the same X-ray and sees pneumonia, or sees a normal chest, or sees something concerning. The diagnostic categories became perceptual.

The trajectory is the same in both cases: explicit labeling → implicit seeing. The category moves from output of perception to mode of perception.

## What this means architecturally

For Cerebra, the v0.5+ vision is a classifier whose internal representations are organized around the 16-category taxonomy. Not as a fine-tuned output layer over generic representations, but as the underlying structure the model uses to encode information.

Concretely, this means:

**v0.1 (now):** Generic instruction-tuned model + prompt that explains the 16 categories + classifier that picks one. The taxonomy is external to the model.

**v0.2:** LoRA-tuned model that has the taxonomy embedded in its outputs. The model has been trained on examples, but the underlying representations are still mostly generic. The taxonomy is overlaid on the model.

**v0.3-0.4:** Iterative fine-tuning with structured feedback. The model learns not just to output categories, but to use them in intermediate reasoning. The taxonomy is becoming part of how the model processes input.

**v0.5+:** Deeper training (potentially continued pretraining, not just LoRA) that restructures the model's internal representations around the cognitive categories. The model doesn't label things as MECHANISM — its representations have a MECHANISM-direction in latent space. The category is part of how the model encodes the world.

This is closer to "domain-specific foundation model" than "instruction-tuned classifier." It's a bigger commitment than v0.2's LoRA, but it's the destination that the v0.2 work is moving toward.

## The self-modifying loop

The really interesting consequence: once the categories are part of perception, the model can refine the categories themselves.

A model that just labels things as MECHANISM has no leverage on what MECHANISM means. The definition is in the prompt; the model applies the definition.

A model whose representations are organized around MECHANISM has implicit access to its own conceptual structure. It can notice "this example doesn't fit cleanly — maybe MECHANISM has subcategories" or "these two examples both fit MECHANISM but feel different — maybe there's a distinction my current concept doesn't capture."

This is the self-modifying loop:
1. Model perceives the world through current taxonomy
2. Model produces classifications that include uncertainty/edge-case markers
3. System collects edge cases, looks for patterns
4. Patterns suggest taxonomy refinements (new categories, subcategories, redrawn boundaries)
5. Refinements become new training signal
6. Model retrained with updated taxonomy
7. Loop continues

The model is participating in its own conceptual evolution, not just executing fixed concepts.

This is also closer to how humans actually work. We don't have static categories handed to us. We refine our categories through use, noticing when they fail, adjusting them, sometimes inventing new ones. A mature thinker has a vocabulary that's been shaped by their experience using earlier versions of it.

## Why this is different from "more training data"

This is the part where the destination differs from incremental ML.

Standard ML pattern: get more labeled data, train longer, model gets better at the task. The task is fixed; the model's accuracy on it improves.

Cognitive-lens pattern: the model's improving accuracy on the task changes what the task can be. As the model develops cleaner internal representations, the system can ask harder questions — questions that depend on the underlying representations being meaningful.

For example: at v0.1, asking "are these two chunks describing the same phenomenon at different scales?" is barely meaningful. The model doesn't have stable enough representations to compare across abstractions. At v0.5+, this kind of question becomes tractable because the categories that anchor "same phenomenon" are part of how the model sees.

The destination isn't "v0.1 with higher accuracy." It's a qualitatively different system whose capabilities couldn't exist without the perceptual restructuring.

## Connection to the triangle

This connects to the philosophy doc directly.

The triangle of Balance / Perception / Understanding says: as understanding matures, perception grows because there isn't a localized network of aspects that demand significant attentive gravity. The mind is more free.

The v0.5+ model is the architectural version of this. Early Cerebra spends a lot of attentive gravity on classifying things — every chunk requires explicit categorization work. Later Cerebra has the categorization integrated into perception, freeing attentive budget for higher-level work (comprehension, synthesis, cross-domain pattern detection).

The mature model isn't doing more cognitive work than the immature model. It's doing the same kinds of work with less effort per item, because the conceptual structure that organizes the work has been internalized.

## What this asks of us now

The destination shapes intermediate choices in several ways:

**1. Pick training methods that move toward representation change, not just output change.**

LoRA on attention layers shifts how the model attends to input but leaves the underlying representations mostly intact. LoRA on MLP layers (or higher rank, more layers) starts to change representations. Eventually, continued pretraining on Cerebra-specific data is the move that genuinely restructures representations.

We don't need to do all of this in v0.2. But we should know v0.2's LoRA is one rung of a longer ladder, not a destination.

**2. Capture training data that supports representation work, not just output work.**

A training corpus of "chunk text → category label" supports output-level fine-tuning. A training corpus of "chunk text → category label + reasoning trace + feature analysis + cross-reference to similar chunks" supports representation-level work.

Phase 2's inspector logs should be designed with the second use case in mind, even though only the first is needed immediately. The richer logs become the corpus for v0.3+ training that does more than label-mimicry.

**3. Pick models that LoRA-train into representation change, not just output change.**

OLMo 3 with full training transparency and checkpoint access supports representation-level work because we can see what's happening and intervene at the right layers. Closed models that only support LoRA on the last few layers can't support this trajectory.

**4. Build the per-pair disambiguation logic into something the model can eventually learn, not just look up.**

If MECHANISM/TECHNIQUE disambiguation lives forever as a Python `if/elif` chain, the model never learns to make that distinction natively. If we structure the per-pair logic as training examples (chunks that exemplify each side of the boundary), the model can eventually internalize the boundary.

The per-pair logic is v0.2 scaffolding. By v0.5+ it should be obsoleted because the model just *sees* the difference.

## What this doesn't mean

Worth being clear about what this vision isn't.

This isn't "make the model conscious." The cognitive-nature language is metaphorical-but-useful. We're describing a model whose representations are organized around domain concepts. That's a real architectural property, achievable with current techniques. It doesn't require sentience or self-awareness in any rich sense.

This also isn't "the model becomes Cerebra." Cerebra remains the architecture above the model. The model becomes a better-aligned substrate, but the cognitive work (signal evaluation, working memory management, consolidation) still lives in code. The model gets better at being the perceptual layer; it doesn't replace the cognitive layer.

And this isn't a guaranteed destination. It's a direction. We might find that v0.3 is good enough and stop. We might find that the representations don't restructure cleanly through fine-tuning and we need different techniques. The vision is something to aim at, knowing the path will surprise us.

## What this means for the brainstorm directory

The cognitive-nature reframe is the *why* behind a lot of the other docs:

- The counsel/swarm is interim infrastructure — useful while the model's solo capability is limited, less needed as the model's perception matures
- Per-pair disambiguation is interim scaffolding — explicit rules now, internalized boundaries later
- Structured epistemic output is interim instrumentation — exposing the model's uncertainty to the system because the model can't yet handle uncertainty internally

All of these are training data sources for the cognitive-nature destination. They're not just utilities; they're the rungs of the ladder.

## On the timeline

v0.5+ isn't soon. Realistic estimate:

- v0.2 LoRA classifier: 3-6 months from now (Phase 2 close-out → backfill → curate → train)
- v0.3 per-pair disambiguation + counsel: another 3-6 months after v0.2
- v0.4 structured epistemic refinement: another 3-6 months
- v0.5+ continued pretraining on Cerebra-shaped data: 12-18 months out at the earliest

We're talking about a multi-year trajectory. That's fine. The point of writing this down now is that the intermediate decisions get better when we know where we're going.

The trap is treating v0.2 as the destination. v0.2 is an early waypoint. The destination is the model whose cognitive nature includes the taxonomy as a perceptual structure, capable of refining its own conceptual framework through use.

That's the magnum opus framing you said about Cerebra. Not "the memory system" but "the system that learns to think more clearly over time through its own cognitive infrastructure."

---

*See also: `triangle_balance_perception_understanding.md` for the philosophical grounding. `v01_as_substrate_for_lora.md` for the bootstrap mechanism. `counsel_swarm_cognition.md` for the interim multi-perspective infrastructure.*
