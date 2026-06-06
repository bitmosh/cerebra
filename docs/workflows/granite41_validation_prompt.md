# Small-Scale Validation — Granite 4.1 3B Production Substrate

Before committing to a full 745-record backfill with Granite 4.1 3B as the new production model, validate end-to-end that the model works cleanly through the full Cerebra pipeline on real planning-doc chunks (not just calibration fixtures).

This is a 30-minute spot-check, not a full validation. Goal: catch any edge cases the calibration test didn't surface.

## Context

Round 2 calibration showed Granite 4.1 3B base (`huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M`) ties Qwen 3.5 9B at 58% partial accuracy, with better Pass 1 quadrant accuracy (73% vs 67%), faster inference (2.4s vs 3.3s), and smaller VRAM footprint (3.7GB vs 8.9GB).

Decision made: switch production substrate to Granite 4.1 3B for both v0.1.0 ship and v0.2 LoRA target.

But the calibration test used 30 specific fixtures. Real planning docs may contain edge cases (very long chunks, chunks with code blocks, chunks with unusual formatting) that the fixtures don't represent. Validate before backfill commitment.

## Pre-conditions

- Phase 2 close-out prompt has NOT yet run. The current production model is still Qwen 3.5 9B in the LLMAdapter config.
- The Round 1 / Round 2 calibration scripts and data are in place.
- The `huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M` model is pulled in Ollama.

## Task

### 1. Sample 50 chunks from the actual ingest corpus

Query the SQLite vault (`~/cerebra-vaults/dev/data/cerebra.db`) for 50 chunks from the `memory_records` table where `sku_address IS NULL` (i.e., chunks ingested in Phase 1 that haven't been classified yet).

Stratify the sample to be representative:

- 10 chunks from very short content (under 200 chars)
- 10 chunks from medium content (200-1000 chars)
- 10 chunks from long content (1000+ chars)
- 10 chunks that contain code blocks or technical syntax
- 10 chunks selected randomly

If any of these strata don't have 10 candidates, fill from random.

Capture the chunk IDs for reproducibility — write `validation_sample_chunks.json` with the IDs and source document references.

### 2. Run the two-pass classifier on each chunk

Use the current v0.1.0 two-pass classifier (PROMPT_VERSION 2.0.0) with the Granite 4.1 3B model:

- Temperature 0.0
- think: false
- v2.0.0 two-pass prompts (Pass 1 quadrant, Pass 2 within-quadrant)
- Same OllamaDirectAdapter path used by the calibration script

For each chunk, capture:
- Pass 1 result (quadrant, confidence, raw scores)
- Pass 2 result (primary, confidence, raw scores)
- Total latency (pass 1 + pass 2)
- JSON parse success/failure
- Any anomalies (refused to commit, malformed output, timeouts, etc.)

### 3. Spot-check the outputs

You don't need to ground-truth-label all 50 chunks. Instead, check for:

**Mechanical issues:**
- Did any classifications fail to parse JSON? How many? Which patterns?
- Did any chunks produce unexpected output formats?
- Did any chunks take dramatically longer than calibration fixtures (>10s)?
- Did any chunks produce NULL or empty results?
- Did the model ever refuse to commit ("I can't determine this")?

**Quality issues (sample-level, not exhaustive):**
- Pick 10 of the 50 chunks at random
- For each, read the chunk content and judge: does the model's classification seem reasonable? Not "is it the right answer" but "is it in the right neighborhood?"
- A classification can be wrong but reasonable. Look for classifications that are obviously wrong (e.g., a clear procedural how-to classified as OBSERVATION).

**Distribution issues:**
- What's the spread of predicted D1 categories across the 50 chunks? Is it heavily skewed to a few categories?
- What's the spread of Pass 1 quadrants? Are all 4 quadrants represented?
- If there's an obvious bias (e.g., 40 of 50 chunks classified as OBSERVATION), that's signal something's off.

### 4. Latency and resource validation

Capture:
- Mean latency per chunk
- Distribution: are there outliers?
- VRAM usage during the run
- Any thermal/throttling issues
- Estimated full-backfill duration if pattern holds (745 chunks × mean latency)

### 5. Write the validation report

Create `docs/agent/granite41_3b_validation.md` with:

**Section 1: Sample**
- How chunks were selected
- Distribution by content type
- Sample IDs reference

**Section 2: Mechanical reliability**
- Parse failure rate (0 expected; any non-zero is concerning)
- Refusal rate
- Output format consistency
- Anomalies

**Section 3: Quality spot-check**
- 10 randomly-selected classifications with chunk content and verdict (reasonable / questionable / obviously wrong)
- Note any patterns in the questionable/wrong cases

**Section 4: Distribution**
- D1 category histogram across 50 chunks
- Pass 1 quadrant histogram
- Any concerning bias

**Section 5: Performance**
- Latency distribution
- VRAM peak
- Estimated backfill duration: 745 chunks × mean latency

**Section 6: Verdict**
One of three:

**a) Cleared for backfill** — no mechanical issues, reasonable quality, performance projects to acceptable backfill time. Recommend proceeding to Phase 2 close-out with Granite 4.1 3B.

**b) Cleared with observations** — minor issues observed but not blocking. Recommend proceeding with documented mitigations.

**c) Blocked** — significant issues. Report findings; user decides whether to address issues, switch to alternate model, or proceed anyway.

## Don't list

- Do NOT run a full 745-record backfill
- Do NOT modify production code or configs
- Do NOT update the LLMAdapter default model yet (the actual switch happens in the Phase 2 close-out pass)
- Do NOT change the prompts or fixtures
- Do NOT touch the database except read-only queries

This is a validation pass, not an implementation pass.

## Estimated time

- Sample selection: 5 minutes
- Run classifier on 50 chunks: ~50 × 2.4s = 2 minutes
- Spot-check analysis: 20-30 minutes
- Writeup: 15 minutes

Total: ~45-60 minutes
