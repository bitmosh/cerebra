# Multi-Model SKU Classifier Calibration — Round 2 (Granite 4.1)

Round 2 follow-up: tests two newly-pulled Granite 4.1 base models against
Round 1 results. Settings held constant with Round 1: temperature 0.0,
think: false, v0.1.0 two-pass prompts (PROMPT_VERSION 2.0.0),
30 fixtures (13 clear / 2 ambiguous / 15 hard), 0.5-credit scoring.
Runs per model: 3

Note: Granite 4.1 models are **base** (non-instruct) — instruct pull failed
with HuggingFace 500. Base models are preferred for v0.2 LoRA training.

## 1. Results Table

Round 1 baselines shown at top for direct comparison.

| Model | Size | Mean Partial | Std Dev | Mean Strict | Pass1 Acc | Mean Latency | VRAM |
|-------|------|:------------:|:-------:|:-----------:|:---------:|:------------:|:----:|
| qwen3.5-9b _baseline_ | 9.7B | 58% | ±0.0% | 53% | 67% | 3.3s | 8932MB |
| granite4-micro _Round 1_ | 3B | 53% | ±0.0% | 47% | 70% | 2.5s | 8348MB |
| granite41-3b _base model_ | 3B | **58%** | ±0.0% | 53% | 73% | 2.4s | 3739MB |
| granite41-8b _base model_ | 8B | **57%** | ±0.0% | 50% | 67% | 3.4s | 8799MB |

## 2. Per-Model Detail

### granite41-3b (3B) — base model

**Run 1:** strict=53%  partial=58%  pass1=73%  failures=0  elapsed=73s
**Run 2:** strict=53%  partial=58%  pass1=73%  failures=0  elapsed=72s
**Run 3:** strict=53%  partial=58%  pass1=73%  failures=0  elapsed=72s

**4-Quadrant table (run 1):**
- High-conf correct: 16
- High-conf WRONG:   14 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    7.0/13 = 54% partial
- Ambiguous (2): 2.0/2 = 100% partial
- Hard (15):     8.5/15 = 57% partial

**Per-D1-category accuracy (run 1):**
- AGENT        1/1  █
- CONSTRAINT   2/3  ██░
- CONTEXT      0/1  ░
- CREATION     1/1  █
- DESIGN       2/5  ██░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    2/6  ██░░░░
- OBSERVATION  2/3  ██░
- PHENOMENON   0/1  ░
- PRINCIPLE    3/4  ███░
- RELATION     0/1  ░
- TECHNIQUE    1/1  █
- TOOL         1/1  █

**Wrong predictions (run 1):** 14 fixture(s)
- `clear_04` expected=PHENOMENON got=DESIGN
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=OBSERVATION
- `clear_10` expected=CONTEXT got=CREATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_15` expected=RELATION got=CREATION
- `hard_01` expected=PRINCIPLE got=RELATION (0.5 credit)
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_03` expected=OBSERVATION got=PATTERN (0.5 credit)
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=TECHNIQUE
- `hard_11` expected=CONSTRAINT got=PRINCIPLE (0.5 credit)
- `hard_14` expected=DESIGN got=RELATION

**Latency (run 1):** min=2224ms  max=2663ms  mean=2428ms  p95=2647

**Run-to-run variance:** 58% / 58% / 58% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### granite41-8b (8B) — base model

**Run 1:** strict=50%  partial=57%  pass1=67%  failures=0  elapsed=102s
**Run 2:** strict=50%  partial=57%  pass1=67%  failures=0  elapsed=101s
**Run 3:** strict=50%  partial=57%  pass1=67%  failures=0  elapsed=101s

**4-Quadrant table (run 1):**
- High-conf correct: 15
- High-conf WRONG:   15 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    8.0/13 = 62% partial
- Ambiguous (2): 1.5/2 = 75% partial
- Hard (15):     7.5/15 = 50% partial

**Per-D1-category accuracy (run 1):**
- AGENT        1/1  █
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       1/5  █░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    4/6  ████░░
- OBSERVATION  2/3  ██░
- PHENOMENON   0/1  ░
- PRINCIPLE    3/4  ███░
- RELATION     1/1  █
- TECHNIQUE    1/1  █
- TOOL         0/1  ░

**Wrong predictions (run 1):** 15 fixture(s)
- `clear_04` expected=PHENOMENON got=RELATION
- `clear_07` expected=DESIGN got=PHENOMENON
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=PHENOMENON
- `clear_13` expected=TOOL got=MECHANISM (0.5 credit)
- `hard_01` expected=PRINCIPLE got=RELATION (0.5 credit)
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_03` expected=OBSERVATION got=MECHANISM
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=TECHNIQUE
- `hard_08` expected=CONSTRAINT got=PRINCIPLE (0.5 credit)
- `hard_11` expected=CONSTRAINT got=PATTERN
- `hard_12` expected=DESIGN got=MECHANISM
- `hard_14` expected=DESIGN got=TECHNIQUE (0.5 credit)

**Latency (run 1):** min=2990ms  max=3720ms  mean=3382ms  p95=3687

**Run-to-run variance:** 57% / 57% / 57% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

## 3. Head-to-Head Comparisons

### Granite 4.1 3B (base) vs Granite 4.0 Micro (instruct)

Tests IBM's '4.1 beats 4.0 at same size' claim on Cerebra's task.

| Metric | Granite 4.1 3B (base) | Granite 4.0 Micro (instruct) | Delta |
|--------|:---------------------:|:----------------------------:|:-----:|
| Partial acc | 58% | 53% | +5% |
| Strict acc | 53% | 47% | +7% |
| Pass 1 quadrant acc | 73% | 70% | +3% |
| Mean latency | 2.4s | 2.5s | -0.1s |

**Outcome:** Granite 4.1 3B **outperforms** Granite 4.0 Micro by 5%. IBM's 4.1>4.0 claim holds on Cerebra's task.

### Granite 4.1 8B (base) vs Qwen 3.5 9B (instruct, current production)

Tests whether a Granite 4.1 dense model can match or exceed current production accuracy.

| Metric | Granite 4.1 8B (base) | Qwen 3.5 9B (instruct) | Delta |
|--------|:---------------------:|:----------------------:|:-----:|
| Partial acc | 57% | 58% | -2% |
| Strict acc | 50% | 53% | -3% |
| Pass 1 quadrant acc | 67% | 67% | -0% |
| Mean latency | 3.4s | 3.3s | +0.1s |

**Outcome:** Granite 4.1 8B is **competitive** with Qwen 3.5 9B (within ±3%). See recommendation section for tie-breaking criteria.

### Granite 4.1 8B vs Granite 4.0 32B MoE

IBM's claim: Granite 4.1 8B matches Granite 4.0 32B MoE at 4× fewer parameters.
Cannot test directly — `ibm/granite4:tiny-h` in ollama list is the ~7B MoE variant
(granite4-tiny-h in Round 1), not the 32B MoE. 32B does not fit in 12GB VRAM.

Round 1 data for granite4-tiny-h (~7B MoE): 32% partial accuracy, 40% pass1.
Granite 4.1 8B (this run): 57% partial, 67% pass1.
Granite 4.1 8B outperforms the 7B MoE variant by 25% — consistent with IBM's architectural improvements.

## 4. Consensus Failure Analysis

Round 1 identified 5 fixtures no model got right: `clear_07` (DESIGN), `clear_11` (EVENT),
`hard_02` (MECHANISM), `hard_07` (DESIGN), `hard_11` (CONSTRAINT).

Did either Round 2 model break any of these?

**granite41-3b:**
- ✓ `hard_11` (CONSTRAINT): correctly predicted `PRINCIPLE (0.5 credit)` — consensus broken!
- ✗ `clear_07` (DESIGN): got `OBSERVATION`
- ✗ `clear_11` (EVENT): got `OBSERVATION`
- ✗ `hard_02` (MECHANISM): got `PRINCIPLE`
- ✗ `hard_07` (DESIGN): got `TECHNIQUE`

**granite41-8b:**
- No consensus failures broken
- ✗ `clear_07` (DESIGN): got `PHENOMENON`
- ✗ `clear_11` (EVENT): got `OBSERVATION`
- ✗ `hard_02` (MECHANISM): got `PRINCIPLE`
- ✗ `hard_07` (DESIGN): got `TECHNIQUE`
- ✗ `hard_11` (CONSTRAINT): got `PATTERN`

## 5. Updated Recommendation

### Phase 2 Production Model

**Recommend keeping Qwen 3.5 9B for v0.1.0 ship, evaluating Granite 4.1 8B in v0.1.1.**
Granite 4.1 8B (57%) is competitive with Qwen 3.5 9B (58%)
but this is a base model (non-instruct). Instruct variant may perform better once available.
For v0.1.1: if instruct pull succeeds, re-run this calibration and decide then.

### v0.2 LoRA Training Target

OLMo 3 was disqualified in Round 1 by latency (65s/fixture). Granite 4.1 is the
strongest candidate for v0.2 LoRA:

- **Base model availability**: base weights are ideal for LoRA fine-tuning (instruct variants are already instruction-tuned, reducing LoRA leverage)
- **IBM training docs**: Granite 4.x has documented QLoRA methodology
- **VRAM fit**: both 3B (2.1GB) and 8B (5.3GB) fit comfortably in 12GB for QLoRA
- **Predictable inference**: no thinking mode means stable classification latency

**Recommend Granite 4.1 3B** as primary LoRA target (58% partial baseline).
The 3B model is competitive with 8B, faster to fine-tune, and cheaper to run post-LoRA.

---

## 6. Raw Data

Full per-fixture predictions and metrics for all Round 2 runs: `multi_model_comparison_raw_round2.json`
