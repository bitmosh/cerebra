# Multi-Model SKU Classifier Calibration — v0.1.0 Two-Pass

Compares Cerebra's v0.1.0 two-pass classifier across available local models.
Settings held constant: temperature 0.0, think: false, v0.1.0 prompts (PROMPT_VERSION 2.0.0),
30 fixtures (13 clear / 2 ambiguous / 15 hard), 0.5-credit scoring on ambiguous_with matches.
Runs per model: 3

## 1. Summary Table

| Model | Size | Mean Partial | Std Dev | Mean Strict | Pass1 Acc | Mean Latency | VRAM |
|-------|------|:------------:|:-------:|:-----------:|:---------:|:------------:|:----:|
| qwen3.5-9b _baseline_ | 9.7B | **58%** | ±0.0% | 53% | 67% | 3.3s | 8932MB |
| qwen3.5-4b | 4B | **55%** | ±0.0% | 53% | 60% | 2.0s | 6474MB |
| granite4-micro | 3B | **53%** | ±0.0% | 47% | 70% | 2.5s | 8348MB |
| olmo3-7b _LoRA candidate_ | 7B | **45%** | ±0.0% | 40% | 57% | 65.5s | 7489MB |
| mistral-nemo _bonus_ | 12B | **43%** | ±0.0% | 40% | 57% | 4.9s | 8539MB |
| hermes3 | 8B | **37%** | ±0.0% | 33% | 53% | 3.6s | 6211MB |
| smollm3-3b | 3B | **35%** | ±0.0% | 33% | 43% | 2.6s | 6349MB |
| llama3.1-8b | 8B | **32%** | ±0.0% | 30% | 43% | 4.0s | 6391MB |
| granite4-tiny-h | ~7B MoE | **32%** | ±0.0% | 30% | 40% | 2.6s | 5624MB |
| qwen3.5-2b _bonus_ | 2B | **27%** | ±0.0% | 27% | 40% | 2.1s | 8239MB |
| qwen3.5-0.8b _bonus_ | 0.8B | **17%** | ±0.0% | 17% | 40% | 1.6s | 6699MB |

## 2. Per-Model Detail

### qwen3.5-9b (9.7B) — baseline

**Run 1:** strict=53%  partial=58%  pass1=67%  failures=0  elapsed=197s
**Run 2:** strict=53%  partial=58%  pass1=67%  failures=0  elapsed=126s
**Run 3:** strict=53%  partial=58%  pass1=67%  failures=0  elapsed=111s

**4-Quadrant table (run 1):**
- High-conf correct: 16
- High-conf WRONG:   14 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    9.0/13 = 69% partial
- Ambiguous (2): 1.5/2 = 75% partial
- Hard (15):     7.0/15 = 47% partial

**Per-D1-category accuracy (run 1):**
- AGENT        1/1  █
- CONSTRAINT   2/3  ██░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       1/5  █░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    3/6  ███░░░
- OBSERVATION  2/3  ██░
- PHENOMENON   1/1  █
- PRINCIPLE    3/4  ███░
- RELATION     1/1  █
- TECHNIQUE    1/1  █
- TOOL         0/1  ░

**Wrong predictions (run 1):** 14 fixture(s)
- `clear_07` expected=DESIGN got=PHENOMENON
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=OBSERVATION
- `clear_13` expected=TOOL got=MECHANISM (0.5 credit)
- `hard_01` expected=PRINCIPLE got=RELATION (0.5 credit)
- `hard_02` expected=MECHANISM got=CONSTRAINT
- `hard_03` expected=OBSERVATION got=MECHANISM
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=MECHANISM
- `hard_09` expected=DESIGN got=MECHANISM
- `hard_11` expected=CONSTRAINT got=PRINCIPLE (0.5 credit)
- `hard_12` expected=DESIGN got=MECHANISM

**Latency (run 1):** min=2991ms  max=5264ms  mean=3431ms  p95=3801

**Run-to-run variance:** 58% / 58% / 58% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### qwen3.5-4b (4B)

**Run 1:** strict=53%  partial=55%  pass1=60%  failures=0  elapsed=61s
**Run 2:** strict=53%  partial=55%  pass1=60%  failures=0  elapsed=60s
**Run 3:** strict=53%  partial=55%  pass1=60%  failures=0  elapsed=58s

**4-Quadrant table (run 1):**
- High-conf correct: 16
- High-conf WRONG:   14 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    7.0/13 = 54% partial
- Ambiguous (2): 2.0/2 = 100% partial
- Hard (15):     7.5/15 = 50% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   2/3  ██░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       1/5  █░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    4/6  ████░░
- OBSERVATION  2/3  ██░
- PHENOMENON   1/1  █
- PRINCIPLE    3/4  ███░
- RELATION     0/1  ░
- TECHNIQUE    1/1  █
- TOOL         1/1  █

**Wrong predictions (run 1):** 14 fixture(s)
- `clear_06` expected=AGENT got=PHENOMENON
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=RELATION
- `clear_15` expected=RELATION got=CREATION
- `hard_01` expected=PRINCIPLE got=RELATION (0.5 credit)
- `hard_02` expected=MECHANISM got=JUDGMENT
- `hard_03` expected=OBSERVATION got=PHENOMENON
- `hard_07` expected=DESIGN got=GOAL
- `hard_09` expected=DESIGN got=GOAL
- `hard_10` expected=MECHANISM got=RELATION
- `hard_11` expected=CONSTRAINT got=JUDGMENT
- `hard_14` expected=DESIGN got=PRINCIPLE

**Latency (run 1):** min=1828ms  max=2174ms  mean=2032ms  p95=2161

**Run-to-run variance:** 55% / 55% / 55% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### qwen3.5-2b (2B) — bonus

**Run 1:** strict=27%  partial=27%  pass1=40%  failures=0  elapsed=67s
**Run 2:** strict=27%  partial=27%  pass1=40%  failures=0  elapsed=124s
**Run 3:** strict=27%  partial=27%  pass1=40%  failures=0  elapsed=93s

**4-Quadrant table (run 1):**
- High-conf correct: 8
- High-conf WRONG:   10 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    12

**Difficulty breakdown (run 1):**
- Clear (13):    4.0/13 = 31% partial
- Ambiguous (2): 0.0/2 = 0% partial
- Hard (15):     4.0/15 = 27% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       0/5  ░░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    1/6  █░░░░░
- OBSERVATION  3/3  ███
- PHENOMENON   0/1  ░
- PRINCIPLE    2/4  ██░░
- RELATION     0/1  ░
- TECHNIQUE    0/1  ░
- TOOL         0/1  ░

**Wrong predictions (run 1):** 22 fixture(s)
- `clear_02` expected=TECHNIQUE got=OBSERVATION
- `clear_04` expected=PHENOMENON got=OBSERVATION
- `clear_06` expected=AGENT got=OBSERVATION
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=PHENOMENON
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=OBSERVATION
- `clear_13` expected=TOOL got=PRINCIPLE
- `clear_14` expected=PRINCIPLE got=PHENOMENON
- `clear_15` expected=RELATION got=CREATION
- `hard_01` expected=PRINCIPLE got=OBSERVATION
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_04` expected=MECHANISM got=PHENOMENON
- `hard_05` expected=MECHANISM got=PRINCIPLE
- `hard_07` expected=DESIGN got=OBSERVATION
- `hard_08` expected=CONSTRAINT got=MECHANISM
- `hard_09` expected=DESIGN got=OBSERVATION
- `hard_10` expected=MECHANISM got=PHENOMENON
- `hard_11` expected=CONSTRAINT got=RELATION
- `hard_12` expected=DESIGN got=OBSERVATION
- `hard_14` expected=DESIGN got=OBSERVATION

**Latency (run 1):** min=1705ms  max=2466ms  mean=2108ms  p95=2445

**Run-to-run variance:** 27% / 27% / 27% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### qwen3.5-0.8b (0.8B) — bonus

**Run 1:** strict=17%  partial=17%  pass1=40%  failures=0  elapsed=77s
**Run 2:** strict=17%  partial=17%  pass1=40%  failures=0  elapsed=57s
**Run 3:** strict=17%  partial=17%  pass1=40%  failures=0  elapsed=54s

**4-Quadrant table (run 1):**
- High-conf correct: 4
- High-conf WRONG:   1 ← investigate
- Low-conf correct:  1
- Low-conf wrong:    24

**Difficulty breakdown (run 1):**
- Clear (13):    2.0/13 = 15% partial
- Ambiguous (2): 0.0/2 = 0% partial
- Hard (15):     3.0/15 = 20% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   0/3  ░░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       0/5  ░░░░░
- EVENT        0/1  ░
- GOAL         0/1  ░
- MECHANISM    0/6  ░░░░░░
- OBSERVATION  2/3  ██░
- PHENOMENON   1/1  █
- PRINCIPLE    2/4  ██░░
- RELATION     0/1  ░
- TECHNIQUE    0/1  ░
- TOOL         0/1  ░

**Wrong predictions (run 1):** 25 fixture(s)
- `clear_02` expected=TECHNIQUE got=PHENOMENON
- `clear_03` expected=MECHANISM got=PHENOMENON
- `clear_05` expected=CONSTRAINT got=PHENOMENON
- `clear_06` expected=AGENT got=PHENOMENON
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=PHENOMENON
- `clear_09` expected=GOAL got=OBSERVATION
- `clear_10` expected=CONTEXT got=PHENOMENON
- `clear_11` expected=EVENT got=PHENOMENON
- `clear_12` expected=CREATION got=PHENOMENON
- `clear_13` expected=TOOL got=PATTERN
- `clear_14` expected=PRINCIPLE got=OBSERVATION
- `clear_15` expected=RELATION got=CREATION
- `hard_01` expected=PRINCIPLE got=PHENOMENON
- `hard_02` expected=MECHANISM got=PHENOMENON
- `hard_03` expected=OBSERVATION got=PHENOMENON
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=PHENOMENON
- `hard_08` expected=CONSTRAINT got=PATTERN
- `hard_09` expected=DESIGN got=OBSERVATION
- `hard_10` expected=MECHANISM got=PHENOMENON
- `hard_11` expected=CONSTRAINT got=PATTERN
- `hard_12` expected=DESIGN got=PHENOMENON
- `hard_14` expected=DESIGN got=PRINCIPLE

**Latency (run 1):** min=1210ms  max=2120ms  mean=1643ms  p95=2108

**Run-to-run variance:** 17% / 17% / 17% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### llama3.1-8b (8B)

**Run 1:** strict=30%  partial=32%  pass1=43%  failures=0  elapsed=123s
**Run 2:** strict=30%  partial=32%  pass1=43%  failures=0  elapsed=122s
**Run 3:** strict=30%  partial=32%  pass1=43%  failures=0  elapsed=119s

**4-Quadrant table (run 1):**
- High-conf correct: 9
- High-conf WRONG:   21 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    5.0/13 = 38% partial
- Ambiguous (2): 0.5/2 = 25% partial
- Hard (15):     4.0/15 = 27% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       0/5  ░░░░░
- EVENT        0/1  ░
- GOAL         0/1  ░
- MECHANISM    1/6  █░░░░░
- OBSERVATION  3/3  ███
- PHENOMENON   1/1  █
- PRINCIPLE    3/4  ███░
- RELATION     0/1  ░
- TECHNIQUE    0/1  ░
- TOOL         0/1  ░

**Wrong predictions (run 1):** 21 fixture(s)
- `clear_02` expected=TECHNIQUE got=OBSERVATION
- `clear_06` expected=AGENT got=PHENOMENON
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=PRINCIPLE
- `clear_09` expected=GOAL got=PRINCIPLE
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=OBSERVATION
- `clear_13` expected=TOOL got=MECHANISM (0.5 credit)
- `clear_15` expected=RELATION got=CREATION
- `hard_01` expected=PRINCIPLE got=PHENOMENON
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=PHENOMENON
- `hard_08` expected=CONSTRAINT got=RELATION
- `hard_09` expected=DESIGN got=OBSERVATION
- `hard_10` expected=MECHANISM got=OBSERVATION
- `hard_11` expected=CONSTRAINT got=OBSERVATION
- `hard_12` expected=DESIGN got=OBSERVATION
- `hard_14` expected=DESIGN got=RELATION

**Latency (run 1):** min=3644ms  max=4425ms  mean=4109ms  p95=4410

**Run-to-run variance:** 32% / 32% / 32% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### olmo3-7b (7B) — LoRA candidate

**Run 1:** strict=40%  partial=45%  pass1=57%  failures=0  elapsed=1956s
**Run 2:** strict=40%  partial=45%  pass1=57%  failures=0  elapsed=1950s
**Run 3:** strict=40%  partial=45%  pass1=57%  failures=0  elapsed=1987s

**4-Quadrant table (run 1):**
- High-conf correct: 11
- High-conf WRONG:   2 ← investigate
- Low-conf correct:  1
- Low-conf wrong:    16

**Difficulty breakdown (run 1):**
- Clear (13):    7.0/13 = 54% partial
- Ambiguous (2): 1.0/2 = 50% partial
- Hard (15):     5.5/15 = 37% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      1/1  █
- CREATION     0/1  ░
- DESIGN       1/5  █░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    3/6  ███░░░
- OBSERVATION  1/3  █░░
- PHENOMENON   0/1  ░
- PRINCIPLE    2/4  ██░░
- RELATION     1/1  █
- TECHNIQUE    0/1  ░
- TOOL         1/1  █

**Wrong predictions (run 1):** 18 fixture(s)
- `clear_02` expected=TECHNIQUE got=TOOL
- `clear_04` expected=PHENOMENON got=GOAL
- `clear_06` expected=AGENT got=GOAL
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=GOAL
- `clear_14` expected=PRINCIPLE got=CONTEXT
- `hard_01` expected=PRINCIPLE got=GOAL
- `hard_02` expected=MECHANISM got=CONSTRAINT
- `hard_03` expected=OBSERVATION got=PATTERN (0.5 credit)
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=GOAL
- `hard_07` expected=DESIGN got=PRINCIPLE (0.5 credit)
- `hard_08` expected=CONSTRAINT got=RELATION
- `hard_09` expected=DESIGN got=CONTEXT
- `hard_11` expected=CONSTRAINT got=PRINCIPLE (0.5 credit)
- `hard_14` expected=DESIGN got=PRINCIPLE
- `hard_15` expected=OBSERVATION got=CONTEXT

**Latency (run 1):** min=16204ms  max=186635ms  mean=65193ms  p95=173860

**Run-to-run variance:** 45% / 45% / 45% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### granite4-tiny-h (~7B MoE)

**Run 1:** strict=30%  partial=32%  pass1=40%  failures=0  elapsed=78s
**Run 2:** strict=30%  partial=32%  pass1=40%  failures=0  elapsed=77s
**Run 3:** strict=30%  partial=32%  pass1=40%  failures=0  elapsed=77s

**4-Quadrant table (run 1):**
- High-conf correct: 9
- High-conf WRONG:   21 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    3.0/13 = 23% partial
- Ambiguous (2): 0.5/2 = 25% partial
- Hard (15):     6.0/15 = 40% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       0/5  ░░░░░
- EVENT        0/1  ░
- GOAL         0/1  ░
- MECHANISM    2/6  ██░░░░
- OBSERVATION  3/3  ███
- PHENOMENON   0/1  ░
- PRINCIPLE    3/4  ███░
- RELATION     0/1  ░
- TECHNIQUE    0/1  ░
- TOOL         0/1  ░

**Wrong predictions (run 1):** 21 fixture(s)
- `clear_02` expected=TECHNIQUE got=OBSERVATION
- `clear_04` expected=PHENOMENON got=AGENT
- `clear_06` expected=AGENT got=PHENOMENON
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=OBSERVATION
- `clear_09` expected=GOAL got=OBSERVATION
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=OBSERVATION
- `clear_13` expected=TOOL got=MECHANISM (0.5 credit)
- `clear_14` expected=PRINCIPLE got=OBSERVATION
- `clear_15` expected=RELATION got=CREATION
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=MECHANISM
- `hard_08` expected=CONSTRAINT got=OBSERVATION
- `hard_09` expected=DESIGN got=OBSERVATION
- `hard_11` expected=CONSTRAINT got=OBSERVATION
- `hard_12` expected=DESIGN got=MECHANISM
- `hard_14` expected=DESIGN got=MECHANISM

**Latency (run 1):** min=2286ms  max=3145ms  mean=2606ms  p95=3041

**Run-to-run variance:** 32% / 32% / 32% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### granite4-micro (3B)

**Run 1:** strict=47%  partial=53%  pass1=70%  failures=0  elapsed=75s
**Run 2:** strict=47%  partial=53%  pass1=70%  failures=0  elapsed=76s
**Run 3:** strict=47%  partial=53%  pass1=70%  failures=0  elapsed=75s

**4-Quadrant table (run 1):**
- High-conf correct: 14
- High-conf WRONG:   14 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    2

**Difficulty breakdown (run 1):**
- Clear (13):    6.0/13 = 46% partial
- Ambiguous (2): 2.0/2 = 100% partial
- Hard (15):     8.0/15 = 53% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
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

**Wrong predictions (run 1):** 16 fixture(s)
- `clear_04` expected=PHENOMENON got=MECHANISM
- `clear_06` expected=AGENT got=OBSERVATION
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=PRINCIPLE
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_15` expected=RELATION got=DESIGN
- `hard_01` expected=PRINCIPLE got=RELATION (0.5 credit)
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_04` expected=MECHANISM got=RELATION
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=TECHNIQUE
- `hard_08` expected=CONSTRAINT got=PRINCIPLE (0.5 credit)
- `hard_11` expected=CONSTRAINT got=PRINCIPLE (0.5 credit)
- `hard_14` expected=DESIGN got=TECHNIQUE (0.5 credit)
- `hard_15` expected=OBSERVATION got=MECHANISM

**Latency (run 1):** min=2151ms  max=2776ms  mean=2492ms  p95=2696

**Run-to-run variance:** 53% / 53% / 53% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### smollm3-3b (3B)

**Run 1:** strict=33%  partial=35%  pass1=43%  failures=0  elapsed=81s
**Run 2:** strict=33%  partial=35%  pass1=43%  failures=0  elapsed=79s
**Run 3:** strict=33%  partial=35%  pass1=43%  failures=0  elapsed=79s

**4-Quadrant table (run 1):**
- High-conf correct: 10
- High-conf WRONG:   20 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    4.0/13 = 31% partial
- Ambiguous (2): 1.0/2 = 50% partial
- Hard (15):     5.5/15 = 37% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       0/5  ░░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    3/6  ███░░░
- OBSERVATION  2/3  ██░
- PHENOMENON   0/1  ░
- PRINCIPLE    2/4  ██░░
- RELATION     0/1  ░
- TECHNIQUE    0/1  ░
- TOOL         1/1  █

**Wrong predictions (run 1):** 20 fixture(s)
- `clear_02` expected=TECHNIQUE got=TOOL
- `clear_04` expected=PHENOMENON got=AGENT
- `clear_06` expected=AGENT got=DESIGN
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=CONTEXT
- `clear_10` expected=CONTEXT got=PHENOMENON
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=DESIGN
- `clear_14` expected=PRINCIPLE got=OBSERVATION
- `clear_15` expected=RELATION got=DESIGN
- `hard_01` expected=PRINCIPLE got=PATTERN
- `hard_02` expected=MECHANISM got=DESIGN (0.5 credit)
- `hard_03` expected=OBSERVATION got=MECHANISM
- `hard_05` expected=MECHANISM got=CONTEXT
- `hard_07` expected=DESIGN got=AGENT
- `hard_08` expected=CONSTRAINT got=RELATION
- `hard_09` expected=DESIGN got=RELATION
- `hard_11` expected=CONSTRAINT got=AGENT
- `hard_12` expected=DESIGN got=PATTERN
- `hard_14` expected=DESIGN got=AGENT

**Latency (run 1):** min=2310ms  max=3273ms  mean=2685ms  p95=3136

**Run-to-run variance:** 35% / 35% / 35% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### hermes3 (8B)

**Run 1:** strict=33%  partial=37%  pass1=53%  failures=0  elapsed=107s
**Run 2:** strict=33%  partial=37%  pass1=53%  failures=0  elapsed=110s
**Run 3:** strict=33%  partial=37%  pass1=53%  failures=0  elapsed=108s

**4-Quadrant table (run 1):**
- High-conf correct: 10
- High-conf WRONG:   20 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    5.0/13 = 38% partial
- Ambiguous (2): 0.5/2 = 25% partial
- Hard (15):     5.5/15 = 37% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       0/5  ░░░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    2/6  ██░░░░
- OBSERVATION  3/3  ███
- PHENOMENON   0/1  ░
- PRINCIPLE    3/4  ███░
- RELATION     0/1  ░
- TECHNIQUE    0/1  ░
- TOOL         0/1  ░

**Wrong predictions (run 1):** 20 fixture(s)
- `clear_02` expected=TECHNIQUE got=OBSERVATION
- `clear_04` expected=PHENOMENON got=MECHANISM
- `clear_06` expected=AGENT got=MECHANISM
- `clear_07` expected=DESIGN got=OBSERVATION
- `clear_08` expected=MECHANISM got=PATTERN
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=OBSERVATION
- `clear_13` expected=TOOL got=MECHANISM (0.5 credit)
- `clear_15` expected=RELATION got=MECHANISM
- `hard_01` expected=PRINCIPLE got=TECHNIQUE
- `hard_02` expected=MECHANISM got=PRINCIPLE
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=TECHNIQUE
- `hard_08` expected=CONSTRAINT got=MECHANISM
- `hard_09` expected=DESIGN got=TECHNIQUE (0.5 credit)
- `hard_11` expected=CONSTRAINT got=PATTERN
- `hard_12` expected=DESIGN got=OBSERVATION
- `hard_14` expected=DESIGN got=PATTERN

**Latency (run 1):** min=3200ms  max=4223ms  mean=3579ms  p95=4068

**Run-to-run variance:** 37% / 37% / 37% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

### mistral-nemo (12B) — bonus

**Run 1:** strict=40%  partial=43%  pass1=57%  failures=0  elapsed=150s
**Run 2:** strict=40%  partial=43%  pass1=57%  failures=0  elapsed=147s
**Run 3:** strict=40%  partial=43%  pass1=57%  failures=0  elapsed=147s

**4-Quadrant table (run 1):**
- High-conf correct: 12
- High-conf WRONG:   18 ← investigate
- Low-conf correct:  0
- Low-conf wrong:    0

**Difficulty breakdown (run 1):**
- Clear (13):    5.0/13 = 38% partial
- Ambiguous (2): 1.5/2 = 75% partial
- Hard (15):     6.5/15 = 43% partial

**Per-D1-category accuracy (run 1):**
- AGENT        0/1  ░
- CONSTRAINT   1/3  █░░
- CONTEXT      0/1  ░
- CREATION     0/1  ░
- DESIGN       2/5  ██░░░
- EVENT        0/1  ░
- GOAL         1/1  █
- MECHANISM    2/6  ██░░░░
- OBSERVATION  2/3  ██░
- PHENOMENON   0/1  ░
- PRINCIPLE    3/4  ███░
- RELATION     0/1  ░
- TECHNIQUE    1/1  █
- TOOL         0/1  ░

**Wrong predictions (run 1):** 18 fixture(s)
- `clear_04` expected=PHENOMENON got=MECHANISM
- `clear_06` expected=AGENT got=PHENOMENON
- `clear_07` expected=DESIGN got=MECHANISM
- `clear_08` expected=MECHANISM got=CONSTRAINT
- `clear_10` expected=CONTEXT got=OBSERVATION
- `clear_11` expected=EVENT got=OBSERVATION
- `clear_12` expected=CREATION got=MECHANISM
- `clear_13` expected=TOOL got=MECHANISM (0.5 credit)
- `clear_15` expected=RELATION got=CREATION
- `hard_01` expected=PRINCIPLE got=DESIGN
- `hard_02` expected=MECHANISM got=CONSTRAINT
- `hard_03` expected=OBSERVATION got=PATTERN (0.5 credit)
- `hard_04` expected=MECHANISM got=PATTERN
- `hard_05` expected=MECHANISM got=PATTERN
- `hard_07` expected=DESIGN got=TECHNIQUE
- `hard_08` expected=CONSTRAINT got=MECHANISM
- `hard_11` expected=CONSTRAINT got=TECHNIQUE
- `hard_12` expected=DESIGN got=MECHANISM

**Latency (run 1):** min=4259ms  max=5526ms  mean=5001ms  p95=5484

**Run-to-run variance:** 43% / 43% / 43% — std dev ±0.0%
**Determinism:** ✓ all 3 runs produced identical predictions

---

## 3. Strict vs Partial Accuracy Gap

Gap = partial_acc − strict_acc. A larger gap means the model frequently predicts
the defensible-alternative answer on ambiguous fixtures — it's directionally correct
but picking the 'other' reasonable category.

| Model | Strict | Partial | Gap |
|-------|:------:|:-------:|:---:|
| qwen3.5-9b | 53% | 58% | +5.0% |
| qwen3.5-4b | 53% | 55% | +1.7% |
| granite4-micro | 47% | 53% | +6.7% |
| olmo3-7b | 40% | 45% | +5.0% |
| mistral-nemo | 40% | 43% | +3.3% |
| hermes3 | 33% | 37% | +3.3% |
| smollm3-3b | 33% | 35% | +1.7% |
| llama3.1-8b | 30% | 32% | +1.7% |
| granite4-tiny-h | 30% | 32% | +1.7% |
| qwen3.5-2b | 27% | 27% | +0.0% |
| qwen3.5-0.8b | 17% | 17% | +0.0% |

## 4. Cross-Model Agreement Analysis

Per fixture: how many models got it correct (strict) across all runs?

**Consensus correct** (3 fixtures — all 11 models got these right):
`clear_01`, `hard_06`, `hard_13`

**Consensus failure** (5 fixtures — no model got these right):
`clear_07`, `clear_11`, `hard_02`, `hard_07`, `hard_11`

**Split** (22 fixtures):
- `clear_06` (AGENT): 1/11 models correct
- `clear_10` (CONTEXT): 1/11 models correct
- `clear_12` (CREATION): 1/11 models correct
- `hard_01` (PRINCIPLE): 1/11 models correct
- `hard_05` (MECHANISM): 1/11 models correct
- `clear_15` (RELATION): 2/11 models correct
- `hard_04` (MECHANISM): 2/11 models correct
- `hard_08` (CONSTRAINT): 2/11 models correct
- `hard_09` (DESIGN): 2/11 models correct
- `hard_14` (DESIGN): 2/11 models correct
- `clear_08` (MECHANISM): 3/11 models correct
- `hard_12` (DESIGN): 3/11 models correct
- `clear_02` (TECHNIQUE): 4/11 models correct
- `clear_04` (PHENOMENON): 4/11 models correct
- `clear_13` (TOOL): 4/11 models correct
- `hard_03` (OBSERVATION): 5/11 models correct
- `clear_14` (PRINCIPLE): 6/11 models correct
- `hard_10` (MECHANISM): 7/11 models correct
- `clear_09` (GOAL): 8/11 models correct
- `hard_15` (OBSERVATION): 9/11 models correct
- `clear_03` (MECHANISM): 10/11 models correct
- `clear_05` (CONSTRAINT): 10/11 models correct

## 5. Recommendation

### Phase 2 Production Model

**Winner: qwen3.5-9b** — 58% mean partial-credit accuracy

### v0.2 LoRA Training Target

OLMo 3 7B is the recommended LoRA training target per the v0.1.0 consultation
(documented training methodology, fits comfortably in 12GB VRAM for QLoRA).
Calibration data for OLMo 3 and alternatives:

- **olmo3-7b**: 45% mean partial accuracy
- **smollm3-3b**: 35% mean partial accuracy
- **granite4-micro**: 53% mean partial accuracy
- **granite4-tiny-h**: 32% mean partial accuracy

If OLMo 3 scored ≥60%, it remains the recommended LoRA target.
If another model significantly outperformed OLMo 3, discuss before committing.

## 6. Raw Data

Full per-fixture predictions and metrics for all runs: `multi_model_comparison_raw.json`
