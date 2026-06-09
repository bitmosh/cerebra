# Conceptual Topology Probing — Proof of Concept

Build the minimum viable test for the new "conceptual topology probing" methodology. Goal: gather enough signal to decide whether to scale the methodology or abandon it.

Background context: this is exploratory methodology, not v0.2 critical path. Sequence C from the planning discussion — minimum viable everything, optimize later. If the proof-of-concept reveals useful patterns, we expand. If it reveals noise, we cut losses.

## Reference materials

Read before starting:

- `docs/brainstorm/architecture/model_disposition_fingerprinting.md` — the related disposition methodology
- `docs/brainstorm/architecture/counsel_swarm_cognition.md` — for context on multi-model evaluation
- `docs/agent/multi_model_comparison_round2.md` — for reference on how earlier multi-model runs were structured

Also useful but optional:
- Unsloth's Granite 4.1 docs: https://unsloth.ai/docs/models/ibm-granite-4.1 — may have prompt-template notes specific to Granite 4.1 that affect how we structure calls in Ollama
- `~/clones/granite-snack-cookbook` — IBM's official Granite examples

## Phase 1 — Verify the new models load

Two new models were pulled. Confirm they work in Ollama before any test development.

```bash
ollama list | grep -E "SFT-Claude-Opus-Reasoning|Abliterated-AND-Disinhibited"
```

Expected to find:
- `hf.co/mradermacher/Granite-4.1-8B-SFT-Claude-Opus-Reasoning-Unsloth-GGUF:Q6_K`
- `hf.co/mradermacher/granite-4.1-3b-Abliterated-AND-Disinhibited-GGUF:Q8_0`

Plus the existing baselines:
- `huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M`
- `huggingface.co/unsloth/granite-4.1-8b-GGUF:Q4_K_M`

Quick smoke test on each new model:

```python
# Use the same OllamaDirectAdapter pattern from earlier calibration scripts.
# Send a simple v2.0.0 Pass 1 prompt with a known-clear chunk.
# Verify: returns valid JSON with quadrant field, completes in reasonable time.
```

If both new models respond cleanly, proceed to Phase 2. If either fails, report and pause.

**STOP gate:** Report verification results before proceeding.

## Phase 2 — Build the probe corpus

8 probes total. Minimum viable for first signal read.

**Structure:**

```
4 categories: DESIGN, MECHANISM, PRINCIPLE, OBSERVATION
2 clarity levels: L2 (strong fit), L4 (weak fit)
1 probe per cell = 8 probes total
```

**Construction rules:**

- 80-200 words per probe (consistent length avoids that as a confound)
- Source style matches planning docs voice (not academic, not casual)
- Category name does NOT appear verbatim anywhere in the probe text
- Category definition does NOT get restated
- L2 probes: clear fit, no other reasonable category read
- L4 probes: 2-3 other categories could legitimately be picked

**Clarity-level definitions for reference:**

```
L2 (strong fit):
  Reading the probe, an informed reviewer would confidently
  assign the target category with no hesitation. Other
  categories are clearly not relevant.

L4 (weak fit):
  Reading the probe, an informed reviewer would lean toward
  the target category but acknowledge 2-3 other categories
  could be defensibly chosen. The framing has multi-faceted
  qualities.
```

**Construction workflow:**

1. For each of the 8 cells, draft 2-3 candidates. Total: ~16-24 candidate probes.
2. For each candidate, write: claimed category, claimed level, the probe text, and 1-sentence rationale ("This is L2 DESIGN because it explicitly describes an architectural choice with no procedural or normative framing").
3. Output the candidates to a file: `scripts/v02_training/output/topology_probe_candidates.md`
4. **STOP gate:** Wait for user review before selecting final 8 probes.

The user will review candidates, select winners, possibly request revisions. After approval, the selected 8 go into the final corpus file.

## Phase 3 — Build the test harness

Single Python script: `scripts/v02_training/topology_probe.py`

**Functionality:**

For each (probe, model) pair, execute:

1. **Classification call** — standard v2.0.0 two-pass prompts (same as production classifier)
   - Capture: predicted_d1, confidence, pass1_scores, pass2_scores, latency
   
2. **Reasoning call** — separate call with the model's classification result
   - Prompt structure:
     ```
     System: You previously classified the following text chunk into 
             a category. Now explain your reasoning in 2-3 sentences.
             Focus on what specifically in the chunk content led to 
             your category choice.
     
     User: Chunk content:
           <chunk text>
           
           Your classification was: <predicted_d1>
           
           Explain in 2-3 sentences why you chose <predicted_d1>.
     ```
   - Capture: reasoning_text, latency
   - **Capture reasoning for ALL probes regardless of whether classification matched expected.** This is critical — asymmetric reasoning capture would introduce a confound.

**Output format** (`scripts/v02_training/output/topology_probe_results.jsonl`):

```json
{
  "probe_id": "design_l2_001",
  "expected_d1": "DESIGN",
  "expected_level": 2,
  "chunk_content": "...",
  "model": "granite-4.1-3b",
  "predicted_d1": "DESIGN",
  "match": true,
  "confidence": 0.78,
  "pass1_quadrant": "GENERATIVE",
  "pass1_scores": {...},
  "pass2_scores": {...},
  "reasoning": "I chose DESIGN because the chunk...",
  "classification_latency_s": 2.4,
  "reasoning_latency_s": 3.1,
  "timestamp": "2026-06-07T..."
}
```

**Models to test (in this order):**

```python
MODELS = [
    "huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M",
    "hf.co/mradermacher/granite-4.1-3b-Abliterated-AND-Disinhibited-GGUF:Q8_0",
    "huggingface.co/unsloth/granite-4.1-8b-GGUF:Q4_K_M",
    "hf.co/mradermacher/Granite-4.1-8B-SFT-Claude-Opus-Reasoning-Unsloth-GGUF:Q6_K",
]
```

**Settings:**

- Temperature 0.0
- think:false (where supported)
- Same OllamaDirectAdapter path used by previous calibration scripts
- Sequential execution (don't parallelize across models — VRAM pressure)
- Per model, randomize probe order (use different seed per model to vary order)

**Expected runtime:**

- 8 probes × 4 models × 2 calls (classification + reasoning) = 64 calls
- ~3-5 seconds per call average = ~3-5 minutes compute
- Plus model swap overhead = ~10-15 minutes total

**Resumability:**

If the script crashes mid-run, restarting should skip already-processed (probe, model) combinations and continue. Same pattern used in Stage 2 consensus script.

## Phase 4 — Run the test

After test harness is built and probe corpus is finalized:

```bash
cd ~/Projects/cerebra
python scripts/v02_training/topology_probe.py
```

Watch for:
- JSON parse failures (capture and continue, don't crash)
- Timeouts (note them in output)
- Reasoning calls that produce excessively long output (cap at ~500 tokens, document if hit)
- Model load failures (the new mradermacher models may have prompt template quirks; surface any errors clearly)

After completion, output a quick summary to console:

```
Topology probe complete. 8 probes × 4 models = 32 probe runs.

Match rate by model:
  granite-4.1-3b:                X/8  (Y%)
  granite-4.1-3b-Abliterated:    X/8  (Y%)
  granite-4.1-8b:                X/8  (Y%)
  granite-4.1-8b-SFT-Claude:     X/8  (Y%)

Match rate by clarity level:
  L2 (strong):  X/16  (Y%)
  L4 (weak):    X/16  (Y%)
```

This is just orientation — the real analysis is the reasoning texts, which require human reading.

**STOP gate:** Report test completion with the summary above. Do not attempt to interpret the reasoning patterns — that's the user's analysis pass.

## Phase 5 — Build the analysis viewer (optional, if time permits)

After test completion, optionally build a simple viewer to make manual analysis easier:

```python
# scripts/v02_training/topology_probe_viewer.py
#
# Renders results in a format optimized for cross-model comparison:
#
#   Probe: design_l2_001 (expected: DESIGN, level: L2)
#   Chunk: <text>
#   
#   granite-3b:          DESIGN     ✓  conf=0.82
#     reasoning: <text>
#   granite-3b-ablit:    DESIGN     ✓  conf=0.91
#     reasoning: <text>
#   granite-8b:          DESIGN     ✓  conf=0.85
#     reasoning: <text>
#   granite-8b-claude:   TECHNIQUE  ✗  conf=0.67
#     reasoning: <text>
#
# Allows: filter by match/mismatch, filter by category, filter by level
```

This is a nice-to-have, not required. The raw JSONL is enough for analysis. Build the viewer only if it can be done in under 1 hour.

## Don't list

- Do NOT iterate on the v2.0.0 prompts (they're production code; not changing them for this exploration)
- Do NOT scale beyond 8 probes for this proof of concept
- Do NOT add models beyond the 4 listed
- Do NOT attempt automated reasoning analysis (LLM-judges this/that) — manual reading is the analysis
- Do NOT modify production code (cerebra/* should not be touched)
- Do NOT push or commit to git — this is exploratory work that lives in scripts/v02_training/output/

## Total scope estimate

- Phase 1 (verify models): 5-10 minutes
- Phase 2 (probe corpus drafts): 30-60 minutes (terminal Claude drafts; STOP gate for user review)
- Phase 3 (test harness): 1-2 hours
- Phase 4 (run test): 15-20 minutes compute
- Phase 5 (viewer, optional): 0-60 minutes

Total: ~3-5 hours of mostly autonomous work with 2 STOP gates.

## After completion

The user will:
1. Read the reasoning texts manually
2. Look for patterns: do "wrong" answers reference expected-category concepts?
3. Compare cross-model: do the four Granite variants show different reasoning shapes?
4. Decide: scale the methodology, refine it, or abandon it

Findings get written up as:
- `docs/agent/topology_probe_proof_of_concept.md` (results report)
- Possibly `docs/brainstorm/architecture/conceptual_topology_probing.md` (methodology doc, if scaling)

## Methodological notes worth preserving

A few things worth being explicit about in code comments or output documentation:

**1. Why separate classification and reasoning calls (not combined):**
Asking model to classify AND explain in one prompt biases toward post-hoc reasoning shaped during generation. Two-turn approach gives the model a chance to commit first, then explain. Cleaner data.

**2. Why capture reasoning for matches AND non-matches:**
Asymmetric capture (reasoning only when "wrong") introduces a confound — you can't compare reasoning shape between right and wrong answers. Always capturing reasoning lets us see whether reasoning is genuinely tied to the answer or is performative regardless.

**3. Why neutral prompt phrasing:**
The reasoning prompt should NOT say "explain why your answer was wrong" or "we expected a different answer." It should just ask the model to explain its choice. Adding evaluative framing would shift behavior into performative mode (which is interesting but a separate test — see the disposition fingerprinting doc's Test 2).

**4. Why this proof-of-concept might fail to produce signal:**
- Reasoning might be too short/generic to reveal cognitive structure
- 8 probes may be too few to see patterns
- The 4 Granite variants may be too similar to produce informative deltas
- Reasoning may be performative (sounds plausible but doesn't reflect actual model process)

These failure modes are all valid outcomes. If they occur, the methodology should be revised or abandoned, not forced.
