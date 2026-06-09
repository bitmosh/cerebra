# Deferred Docs Backlog

*Logged 2026-06-05. Capture before they slip; write when time allows.*

Docs identified as worth writing but not part of the initial "core 5" capture. Listed roughly by priority within each category. The thinking from these threads is preserved in conversation transcripts; these notes mark what to write up.

## High priority — write soon

### `architecture/per_pair_disambiguation.md`

The insight that disambiguation logic is per-category-pair, not universal. Each conceptual boundary (MECHANISM/TECHNIQUE vs CONSTRAINT/PRINCIPLE etc.) has its own discerning factors. No universal logical filters transpose between pairs.

Key content:
- `boundary_diagnostics` dictionary structure: per-pair features, decision rules, common confusions
- Why humans use different diagnostics for different category boundaries
- Builds empirically from calibration data; expands as new confusions surface
- Connection to counsel/swarm: per-pair logic applied to each council vote
- Eventually obsoleted in v0.5+ as the model internalizes boundaries

Source: 2026-06-05 conversation about "each factor has its own set of discerning factors."

### `architecture/system1_system2_at_model_layer.md`

Could merge with counsel doc or stand alone. The insight that thinking-mode toggle isn't a config — it's a per-call cognitive-mode decision. Catalyst should choose when System 1 (fast pattern match, single model) vs. System 2 (deliberative, counsel) is appropriate.

Key content:
- Kahneman's System 1/2 mapped to model architecture
- Catalyst as the decision-maker for cognitive mode
- Connection to McGilchrist hemispheric integration
- Signal pipeline can inform mode selection
- The trap of two thinking systems competing (covered in `two_thinking_systems_disruption.md`)

Source: discussion around Qwen 3.5 thinking mode and catalyst design.

### `philosophy/cognitive_models_reference.md`

Reference list of thinkers to draw from when specific design questions arise. Not a thesis — a quick lookup.

Key content:
- **Kahneman** — System 1/2, cognitive biases as systematic patterns
- **Watts** — understanding vs. being, self-reference traps, wisdom of insecurity
- **Minsky** — Society of Mind, K-lines, frames, trans-frames
- **Hofstadter** — strange loops, productive vs. pathological self-reference
- **McGilchrist** — hemispheric integration, left/right attention modes
- **Clark** — predictive processing, active inference
- **Peirce** — deduction/induction/abduction, three modes of inference
- **Vygotsky** — zone of proximal development, scaffolding
- **Bourdieu** — habitus, dispositional formation
- **Stiegler** — technics and time, externalization ethics
- **Varela/Maturana** — autopoiesis, enactivism, neurophenomenology
- **Visuddhimagga** — Theravāda Abhidhamma typology of cognition
- **Tibetan Geluk** — lorig (mind and awareness), tarig (logic) traditions
- **Sufism** — ilm/marifa/dhauq distinctions, muraqaba practice

For each: paragraph on what they're for, when to reach for them, key vocabulary.

Source: 2026-06-05 thread on cognitive models worth pooling.

### `architecture/structured_epistemic_output.md`

The proposed JSON shape with primary, confidence, alternatives, ambiguity_sources, clarifying_questions, sources. The "don't ask model to introspect; ask for observable features and derive meta-cognitive output from rules" principle (Path Z approach).

Key content:
- Full JSON shape example with each field explained
- Why model introspection is unreliable (Right for Wrong Reasons paper)
- Feature extraction approach: model emits observable features, Cerebra derives meta-output
- Format Tax paper connection: decouple reasoning from formatting
- Per-pair disambiguation as the source of "what features to look for"
- Evolution path from v0.2 simple version to v0.4+ richer version

Source: 2026-06-05 discussion about clarifying questions output format.

## Medium priority — write when referenced

### `architecture/context_state_gradient.md`

Hot / warm / cool / cold / dormant context states. Maps onto memory tier lifecycle in Cerebra's existing design. We touched on this briefly but didn't go deep.

Source: brief mention in earlier conversation; worth fleshing out.

### `architecture/classifier_clarifying_questions.md`

The pattern of the model surfacing what confused it during classification rather than just producing a verdict. "I was thinking maybe X or Y, but Z confused me." Different from epistemic output — focuses on the dialogue shape.

Could be downstream of structured_epistemic_output.md or its own thing.

Source: 2026-06-05 discussion.

### `architecture/model_substrate_criteria.md`

What makes a good Cerebra substrate model. Why IBM Granite 4 explicitly targets this. Why Qwen 3.5's thinking mode is wrong for Cerebra. Hallucination rates as family signature. Empirical question answered through calibration, not benchmarks.

Could merge with `two_thinking_systems_disruption.md` or stand alone.

Source: model exploration discussions on 2026-06-05.

### `architecture/training_methodology_lineages.md`

The foundational documented training traditions:
- **AI2's OLMo** — full transparency, model flow, OlmoTrace
- **Tülu 3** — SFT + DPO + RLVR recipe
- **HuggingFace Smol** — engineering playbook with failure modes
- **Unsloth** — consumer-hardware execution layer
- **Pythia** — interpretability infrastructure

How they compose. What each is best for. When to reach for each.

Source: 2026-06-05 web search on open training methodologies.

### `agent/deferred/v02_lora_track.md` — LoRA track (written, benched 2026-06-09)

Full record of Phase 1/2/3 work, key learnings, resume conditions, and resume plan.
See `docs/agent/deferred/v02_lora_track.md` — do not rewrite, it exists.

### `infrastructure/training_knowledge_mcp_design.md`

Lives outside the brainstorm directory — its own project. The multi-source training-knowledge MCP server design:
- OLMo + Tülu 3 + Smol + Unsloth + Pythia
- Sourced knowledge with consensus/disagreement separation
- Indexed reference corpus with hybrid retrieval (FAISS + BM25)
- Phased build prioritizing retrieval first

Path: probably `docs/projects/training_knowledge_mcp/DESIGN.md` rather than brainstorm.

Source: 2026-06-05 discussion of expanding the Smol MCP draft.

## Lower priority — write if needed

### `research/format_tax_finding.md`

The UCSD Format Tax paper finding: JSON output requirements degrade reasoning before any decoder constraint. Fix: decouple reasoning from formatting. Citation, key claims, our interpretation.

### `research/right_for_wrong_reasons_finding.md`

50-69% of correct answers from 7-9B models have flawed reasoning. Self-critique HARMS small models. RAG improves reasoning integrity.

### `research/qwen35_family_signature.md`

Family-level hallucination rate (80-82% on AA-Omniscience), the 38/62 prompt-weight claim verification (likely fabricated), Strong-to-Weak Distillation mechanism for the 4B.

### `process/collaboration_shape.md`

Terminal Claude / planning Claude / bandit division of labor. When to use which. Model-evaluation harness concept.

## Notes on writing these

- Most can be written incrementally — capture the framing first, fill in detail when referenced
- The "high priority" ones are where the thinking is most original or most load-bearing for upcoming work
- Lower priority docs are mostly reference material; write them when you find yourself wanting to point to one
- Some may turn out to deserve merger; some may turn out to deserve splitting; let usage shape that

## When to revisit this list

After Phase 2 closes. Re-read the deferred docs list, decide what to elevate, what to drop, and what to write.
