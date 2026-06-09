# v0.2 LoRA — Phase 2 Training Plan

**Status:** Complete — Phase 2 training run and eval finished 2026-06-09  
**Adapter under analysis:** `output/lora_adapters/run_1780979597/adapter`  
**Base model:** `ibm-granite/granite-4.1-3b-base`  
**Corpus:** 214 records, 169 train / 21 val / 24 held-out test

**Pre-implementation seed check (amendment 5):** Run 1's `training_summary.json` does not log `seed`. Source code has `seed=42` hardcoded in `TrainingArguments` (`train_lora.py:229`). Phase 2 uses `seed=42`. The summary dict is updated in this implementation to log `"seed"` explicitly going forward.

---

## 1. Failure-mode summary

Re-eval of run_1780979597 with `raw_output` capture (Task 1) against 30 calibration fixtures:

| Mode | Count | Description |
|------|-------|-------------|
| **B** | 16 | Pure document continuation — model emits XML/HTML/prose (`</summary>`, `<field>`, `<thoughts>`, etc.) instead of JSON |
| **B\*** | 6 | Pass-2 failure; pass-1 succeeded via brace-matcher finding embedded JSON in B-type output; pass-2 raw unobserved |
| **C** | 2 | Model started generating valid JSON late in output (char 607 / char 904) then hit `max_new_tokens=256` before closing `}` |
| **D** | 1 | Valid JSON, wrong schema — `{"start_byte":0,"end_byte":0,...}` byte-range metadata struct (likely memorised from prompt content, not from a completion target — corpus is clean, see §1 note) |
| **A** | 0 | — |
| **Total** | **25/30** | |

**Corpus cleanliness:** Checked `pass1_train.jsonl` — all 169 records have only `["scores","confidence","primary_quadrant"]` in the completion. No byte-range keys. Mode D is a memorisation artefact from document content seen in the prompt body, not a target-field leak.

**Dominant pattern:** 22 of 25 failures are B-family (document continuation). The base Granite 4.1 model without proper EOS training and without completion-only loss masking learned to continue its training documents rather than to emit a JSON response. This is the expected failure mode when the LM objective is applied over prompt tokens as well as completion tokens with no stop signal.

**C-mode implication:** Two fixtures DID start emitting valid JSON (after ~600–900 chars of prose), then ran out of tokens. This confirms EOS was never trained — the model had no signal to stop after `}`.

---

## 2. Methodology source-of-truth

### Issue 1 — No EOS after completion

| Source | How EOS is handled |
|--------|--------------------|
| **open-instruct** (`dataset_transformation.py:147–171`) | Chat template appends EOS via `{% if loop.last and not add_generation_prompt %}{{ eos_token }}{% endif %}`, triggered by calling `apply_chat_template(..., add_generation_prompt=False)` |
| **granite-snack-cookbook** (`FineTuning_with_Unsloth.ipynb`) | Belt-and-suspenders: `apply_chat_template(..., add_generation_prompt=False) + EOS_TOKEN` — explicit append even after template |
| **Our pipeline** | `_format_training_text = prompt + completion` — no EOS appended, tokenizer `add_eos_token=False` |

**Adopted convention (T3.A):** Granite cookbook pattern **without** chat template wrapping. Append `tokenizer.eos_token` to the completion string at corpus-build time inside `build_pass1_pair()` and `build_pass2_pair()`.

Rationale: our prompts are not conversational; the v0.1.0 instruct baseline was established without chat templating; introducing `apply_chat_template` now would add a confounder between Phase 1 and Phase 2.

**EOS verification (granite-4.1-3b-base):**
```python
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("ibm-granite/granite-4.1-3b-base")
tok.eos_token      # → '<|end_of_text|>'
tok.eos_token_id   # → 100257
tok.add_eos_token  # → False  (auto-append disabled; must be explicit)
tok.chat_template  # → absent
```
`tokenizer.eos_token` resolves to `'<|end_of_text|>'` at corpus-build time. The token is distinct (ID 100257); BOS shares the same surface form but EOS in generation context is unambiguous.

---

### Issue 2 — Loss computed over all tokens (no completion-only masking)

| Source | How prompt tokens are masked |
|--------|------------------------------|
| **open-instruct** (`dataset_transformation.py:1112–1174`) | `mask_labels()` computes per-message token boundaries via repeated `apply_chat_template` prefix calls; non-assistant positions set to `-100`; uses `DataCollatorForSeq2Seq` with pre-computed labels |
| **granite-snack-cookbook** | SFTTrainer default masking (Unsloth handles it); no explicit collator override in notebooks |
| **Our pipeline** | `dataset_text_field="text"` with no `response_template` — loss over all tokens, including the prompt |

**Adopted convention (T3.B):** `DataCollatorForCompletionOnlyLM` with a string-based `response_template`.

**Anchor identification — `</text>` boundary:**

Seam in `pass1_train.jsonl` (verbatim):
```
...budget remains?\n```\n\n---\n\n\n</text>{"scores": {"EMPIRICAL": 0.0, ...
```

Seam in `pass2_train.jsonl` (verbatim):
```
...budget remains?\n```\n\n---\n\n\n</text>{"scores": {"PRINCIPLE": 1.0, ...
```

Both passes end their prompt with `</text>` and begin their completion immediately with `{` — no separator.

**Anchor uniqueness check:**
- `pass1_train.jsonl` (169 records): `</text>` appears exactly **1** time per record, only in the prompt. ✓
- `pass2_train.jsonl` (169 records): `</text>` appears exactly **1** time per record, only in the prompt. ✓

**Proposed `response_template`:** `"</text>"`

The collator tokenizes `"</text>"`, finds the token sequence in the full training sequence, and masks all positions up to and including it as `-100`. Training signal covers only `{"scores":...}<|end_of_text|>`.

**Known risk:** Granite 4.1 tokenises context-dependently. If `</text>` tokenises differently in isolation vs. in-context (i.e., the token IDs for `</text>` as a standalone string differ from the IDs when it appears after `\n\n---\n\n\n`), `DataCollatorForCompletionOnlyLM` will silently fail to find the boundary and fall back to full-sequence loss — which is the current broken state. **Verification step required before training:** run a single-record tokenisation check confirming the template tokens are found.

---

### Issue 3 — Pass-1 key mismatch (`"primary_quadrant"` vs `"primary"`)

| Location | Key |
|----------|-----|
| Pass-1 training completion (`build_pass1_pair`, `build_training_corpus.py:169–173`) | `"primary_quadrant"` |
| Pass-1 in-context example in prompt (`_build_pass1_prompt`, `sku_classifier.py:403–407`) | `"primary"` |
| Pass-2 training completion (`build_pass2_pair`, `build_training_corpus.py:192–197`) | `"primary"` ✓ |
| Evaluator (`evaluate_lora.py:161`) | handles both via `.get("primary") or .get("primary_quadrant")` |

The mismatch is in pass-1 only. Fix: change `"primary_quadrant"` → `"primary"` in `build_pass1_pair`. This aligns the completion schema with what the prompt example shows the model.

---

## 3. Concrete code changes for Phase 2

### Change 1 — EOS appended to completions

**File:** `scripts/v02_training/build_training_corpus.py`  
**Functions:** `build_pass1_pair` (line 169), `build_pass2_pair` (line 192)

Requires tokenizer EOS string. Two implementation options:
- (a) Define a constant at module top: `EOS = "<|end_of_text|>"` (verified for granite-4.1-3b-base)
- (b) Load tokenizer in `main()` and pass `eos_token` down to the pair builders

Option (a) is simpler; option (b) is more portable. Proposed: option (a) with a comment citing the verification.

**`build_pass1_pair` — current (lines 169–175):**
```python
completion = json.dumps({
    "scores": scores,
    "confidence": pass1_data.get("confidence", record["d1_confidence"]),
    "primary_quadrant": quadrant,   # also changed in Change 3 below
})
return {"prompt": prompt, "completion": completion, ...}
```

**Proposed:**
```python
# EOS verified: granite-4.1-3b-base tokenizer.eos_token == '<|end_of_text|>'
_EOS = "<|end_of_text|>"

completion = json.dumps({
    "scores": scores,
    "confidence": pass1_data.get("confidence", record["d1_confidence"]),
    "primary": quadrant,            # Change 3: key aligned to prompt example
}) + _EOS
return {"prompt": prompt, "completion": completion, ...}
```

**`build_pass2_pair` — current (lines 192–198):**
```python
completion = json.dumps({
    "scores": scores,
    "confidence": record["d1_confidence"],
    "primary": d1_name,
    "reasoning": f"This excerpt is best classified as {d1_name} within the {quadrant} quadrant.",
})
return {"prompt": prompt, "completion": completion, ...}
```

**Proposed:**
```python
completion = json.dumps({
    "scores": scores,
    "confidence": record["d1_confidence"],
    "primary": d1_name,
    "reasoning": f"This excerpt is best classified as {d1_name} within the {quadrant} quadrant.",
}) + _EOS
return {"prompt": prompt, "completion": completion, ...}
```

---

### Change 2 — Completion-only loss masking

**File:** `scripts/v02_training/train_lora.py`  
**Location:** `WeightedSFTTrainer` construction (lines 235–245)

**Methodology citation:** open-instruct `dataset_transformation.py:1112–1174` (role-based masking); granite cookbook `FineTuning_with_Unsloth.ipynb` (SFTTrainer default with `apply_chat_template`). We use `DataCollatorForCompletionOnlyLM` as our non-chat-template equivalent.

**Current:**
```python
trainer = WeightedSFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    dataset_num_proc=1,
    args=training_args,
    packing=False,
)
```

**Proposed:**
```python
from trl import DataCollatorForCompletionOnlyLM

response_template = "</text>"
collator = DataCollatorForCompletionOnlyLM(
    response_template=response_template,
    tokenizer=tokenizer,
)

trainer = WeightedSFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    dataset_num_proc=1,
    args=training_args,
    packing=False,
    data_collator=collator,
)
```

**Smoke test — 4 checks, all must pass before full training (`--smoke` flag):**

Run with `python scripts/v02_training/train_lora.py --smoke` after corpus rebuild. Checks in order:

1. **Text-field EOS check** (data): verify all smoke records' `text` fields end with `<|end_of_text|>`. Hard gate.
2. **Template anchor check** (tokenizer): verify `</text>` token IDs appear as a contiguous subsequence in the tokenized sequence. Hard gate. If this fails, `DataCollatorForCompletionOnlyLM` silently falls back to full-sequence loss.
3. **Labels masking check** (collator): apply the collator manually to one tokenized record; verify some positions are `-100` (prompt masked) and the last position is `eos_token_id` (EOS is trained). Hard gate.
4. **Inference EOS termination check** (post-training, soft gate): after 1-epoch training on 5 records, generate one example; verify the generation stops at `<|end_of_text|>` before hitting `max_new_tokens`. 1 epoch on 5 records may not reliably achieve EOS termination — report the result but treat this as informational; if EOS does trigger it confirms the signal is learned; if not, the full 3-epoch run should correct it.

Only proceed to full training if checks 1–3 pass.

---

### Change 3 — Pass-1 key alignment

**File:** `scripts/v02_training/build_training_corpus.py`  
**Function:** `build_pass1_pair` (line 172)

Covered in Change 1 proposed code above: `"primary_quadrant"` → `"primary"`.

**Methodology citation:** pass-2 already uses `"primary"` (line 195). In-context prompt example uses `"primary"` (`sku_classifier.py:405`). Aligning pass-1 completion to match.

No evaluator change needed — `evaluate_lora.py:161` already handles both keys via `p1_data.get("primary") or p1_data.get("primary_quadrant")`.

---

### Change 4 — Pass-2 raw output capture (T3.C)

**File:** `scripts/v02_training/evaluate_lora.py`

Phase 2 cannot ship without this. The 6 B* failures in Phase 1 had unobserved pass-2 raw output; we need to be able to classify pass-2 failures in the Phase 2 eval.

**Step 4a — add field to `FixtureResult` (after `raw_output`):**
```python
raw_output_p2: str = ""
```

**Step 4b — change `classify()` return to 5-tuple:**
```python
# Current signature:
def classify(self, content: str) -> tuple[str | None, float, str | None, str]:
    ...
    p2_raw = self._generate(...)
    ...
    return d1, confidence, quadrant, p1_raw

# Proposed signature:
def classify(self, content: str) -> tuple[str | None, float, str | None, str, str]:
    ...
    p2_raw = self._generate(...)
    ...
    return d1, confidence, quadrant, p1_raw, p2_raw

# All early-return paths (before pass-2) return empty string for p2_raw:
    return None, 0.0, None, p1_raw, ""
    return None, 0.0, quadrant, p1_raw, p2_raw  # after pass-2 failure
```

**Step 4c — update `evaluate_calibration` and `evaluate_test_set`:**
```python
d1, conf, quad, p1_raw, p2_raw = clf.classify(f.content)
r = FixtureResult(..., raw_output=p1_raw, raw_output_p2=p2_raw)
```

**Step 4d — update JSON output dict (both calibration and test_set results lists):**
```python
"raw_output": r.raw_output,
"raw_output_p2": r.raw_output_p2,
```

---

### Change 5 — Corpus rebuild

After Changes 1, 2, 3: re-run `build_training_corpus.py` to produce new `pass1_train.jsonl` and `pass2_train.jsonl` with EOS-appended completions. The `text` field produced by `_format_training_text` will then be `prompt + completion + <|end_of_text|>`.

**`_format_training_text` is unchanged:** `return prompt + completion` — the EOS is already embedded in the completion string, so it flows through naturally.

---

## 4. Validation plan

**Corpus:** same 214 records, same train/val/test split.  
**Hyperparameters:** all held constant from run_1780979597 (rank, learning rate, epochs, batch size, seed — no changes).  
**Eval:** re-run `evaluate_lora.py` against Phase 2 adapter with `--calibration-only` for initial signal; then full run including held-out test set once calibration numbers are satisfactory.  
**Instrument:** `raw_output` and `raw_output_p2` both captured (Change 4).

**Comparison metrics (run_1780979597 → Phase 2):**

| Metric | Run 1 baseline | Phase 2 target |
|--------|---------------|----------------|
| Calibration partial-credit | 10% | ≥60% (methodology fix) |
| Parse failure rate | 83% | <20% |
| Failure-mode distribution | 100% B/B* | Shift to A (valid JSON, wrong value) |
| Pass-2 failure rate | 6/30 unobserved | All failures classified with raw_output_p2 |
| **EOS-termination rate** (generation stopped by EOS, not max_new_tokens) | **~0%** | **≥80%** — cleanest signal that EOS training worked, independent of accuracy |

**Decision matrix:**

| Phase 2 result | Interpretation | Next step |
|----------------|----------------|-----------|
| ≥60% partial-credit | Methodology fix worked | Proceed to GGUF conversion |
| 40–60% partial-credit | Methodology helped but ceiling lower than expected; three candidates: (a) corpus thinness, (b) base-SFT difficulty, (c) **undertraining under masked-loss regime** (model now only sees completion tokens as signal — same epochs cover less gradient signal than full-sequence loss) | Cheap diagnostic first: 2× epochs at same LR (~7 min extra); if that clears 60%, undertraining was the cause; if not, analyse residual failure-mode distribution before deciding Phase 3 vs other changes |
| 25–40% partial-credit | Ambiguous: could be corpus thinness OR base-SFT difficulty on this model family (IBM has never demonstrated base-variant SFT in their published recipes) | Phase 3 (format corpus) is one option; switching LoRA target to instruct variant is another; choose based on failure-mode distribution |
| <25% partial-credit | Deeper structural problem beyond the three known issues | STOP and rediagnose before any further training |

**Note on the 25–40% band:** Task 2 found that IBM's published granite-snack-cookbook contains no base-model SFT examples — both fine-tuning notebooks use `granite-3.3-2b-instruct`. If Phase 2 lands in this band, it may reflect an inherent difficulty of SFTing the base variant for structured JSON output, not a methodology error. Both options (Phase 3 corpus expansion vs instruct-variant LoRA) should be on the table at that point.

---

## 5. What we are NOT doing in Phase 2

- **Not introducing `apply_chat_template` anywhere** — not in training, not in inference. Adding it now would confound the comparison against both Phase 1 and v0.1.0 instruct baseline.
- **Not switching LoRA target from base to instruct variant** — deferred decision pending Phase 2 results (falls in the 25–40% outcome path if needed).
- **Not adding new training records** — corpus held at 214 records; corpus expansion (Phase 3 format corpus) is conditional on Phase 2 results.
- **Not changing hyperparameters** — rank, learning rate, epochs, batch size, seed all held constant from run_1780979597. The point of Phase 2 is to isolate the methodology fix, not to sweep hyperparameters.
- **Not doing a hyperparameter sweep** — even if Phase 2 underperforms, a sweep comes only after the methodology is confirmed sound.
- **Not doing teacher distillation or new chunks from the broader corpus.**

---

## 6. Open questions and risks

**R1 — Tokeniser context-sensitivity of `</text>` anchor (high priority)**  
`DataCollatorForCompletionOnlyLM` converts the template string to token IDs and searches for them in the tokenised sequence. Granite 4.1's tokeniser may assign different IDs to `</text>` in isolation vs. in the context of `\n---\n\n\n</text>{`. If so, the collator silently falls back to full-sequence loss. The smoke test (Check 2) will surface this before training.

**Fallback anchor pre-checked and found UNUSABLE:** `\n\n---\n\n\n</text>` appears **0 times** in 50/169 records in both pass1 and pass2 corpora — some prompts don't use the `---` section separator before `</text>`. Using this as a fallback would silently skip 50 records. If `</text>` fails the smoke test, a new fallback must be identified (e.g., just `</text>` with a different tokenization approach, or a dedicated separator token injected into `_format_training_text`). Do not use `\n\n---\n\n\n</text>` as a fallback.

**R2 — `WeightedSFTTrainer` compatibility with `data_collator`**  
`WeightedSFTTrainer` extends TRL's `SFTTrainer`. Passing `data_collator` overrides the default collator; verify that `WeightedSFTTrainer.__init__` passes `**kwargs` to `SFTTrainer` and that no internal weight-computation logic re-wraps the collator. A quick `grep` for `data_collator` in the `WeightedSFTTrainer` source should suffice before training.

**R3 — `add_eos_token=False` means the tokenizer will NOT double-append EOS**  
Verified: `tok.add_eos_token = False` for granite-4.1-3b-base. Appending `<|end_of_text|>` explicitly in the completion string (Change 1) will not be duplicated. If this flag were `True`, EOS would appear twice, potentially confusing the model. Confirm this is still False when the corpus builder loads the tokenizer.

**R4 — B\* pass-2 failure root cause is still unobserved**  
The 6 B* failures from Phase 1 were unobserved because pass-2 raw was not captured. Change 4 closes this gap for Phase 2. If Phase 2 still has B* failures, we can now classify them. The hypothesis is that pass-2 generates the same B-type document continuation — which would be fixed by the same EOS + masking changes. This is unconfirmed until Phase 2 eval.

**R5 — Mode D (hard_14) may recur even after the methodology fix**  
The byte-range metadata JSON was memorised from Cerebra source-file content embedded in prompt bodies, not from completion targets (corpus is clean). The model may still regurgitate this structure if that memorisation pattern persists after Phase 2. If Mode D recurs in Phase 2, the fix is to filter or rewrite training records whose prompt body contains byte-range fields.

**R6 — Key conflict between open-instruct and granite-cookbook**  
open-instruct uses `apply_chat_template` throughout; granite-cookbook also uses `apply_chat_template`. Both sources use chat templates; neither demonstrates non-chat-template base-model SFT for structured JSON output. Our approach (explicit EOS + completion-only collator, no chat template) is derived from principles in both sources but has no direct precedent in either repo. This is noted as a gap — if Phase 2 fails despite the methodology fix, revisiting chat-template-based training is a valid next diagnostic.

---

## 7. Phase 2 results (actual, 2026-06-09)

### Adapters produced

| Run | Epochs | Final train loss | Val loss (final) | Adapter path |
|-----|--------|-----------------|-----------------|-------------|
| run_1781024893 | 3 | 0.0316 | 0.0213 | `output/lora_adapters/run_1781024893/adapter` |
| run_6epoch_diag | 6 (diagnostic) | 0.0175 | 0.0349 | `output/lora_adapters/run_6epoch_diag/adapter` |

Val loss for 6-epoch run: 0.032 → 0.029 → 0.028 → **0.038 (rises)** → 0.034 → 0.035. Overfitting begins at epoch 4. 3-epoch adapter is the deliverable.

### Calibration eval (30 fixtures)

| Run | Strict acc | Partial acc | Parse failures |
|-----|-----------|-------------|----------------|
| Run 1 (Phase 1 baseline) | 10% | 10% | 25/30 |
| run_1781024893 (Phase 2, 3-ep) | **46.7%** | **48.3%** | **0/30** |
| run_6epoch_diag (6-ep) | 43.3% | 48.3% | 0/30 |
| v0.1.0 instruct baseline | — | 65% | — |

**Parse failures: resolved completely.** The EOS + `SFTConfig(completion_only_loss=True)` fix eliminated all 25 B/C/D mode failures.

### Pass-level breakdown (run_1781024893)

- Pass-1 quadrant routing: **17/30 = 56.7%**
- Pass-2 D1 | correct quadrant: **14/17 = 82.4%**
- Combined: 56.7% × 82.4% ≈ 46.7% ✓

Pass-2 is working well. Pass-1 quadrant routing is the bottleneck.

### Root cause of remaining accuracy gap

RELATIONAL quadrant is critically underrepresented in the corpus (~12 records). AGENT is absent entirely. NORMATIVE/PRINCIPLE dominates (168 records). The `WeightedRandomSampler` class weights operate at the D1 level but do not compensate for quadrant imbalance in pass-1 training.

13 of 16 wrong predictions involved a wrong quadrant. Common misroutes: RELATIONAL→EMPIRICAL, RELATIONAL→GENERATIVE, GENERATIVE→EMPIRICAL.

### Recommended action for Phase 3

Add **quadrant-level class weights for pass-1 training** so RELATIONAL examples are upsampled when building pass-1 pairs. This is a corpus-builder change (`build_training_corpus.py`) combined with a `train_lora.py` change to apply separate pass-1 weights. Not a hyperparameter change.

### Technical fixes landed in this phase

- `DataCollatorForCompletionOnlyLM` does not exist in TRL 0.24.0 — replaced with `SFTConfig(completion_only_loss=True)` + `"prompt"`/`"completion"` columns in dataset
- `build_hf_dataset` now exposes `"prompt"` and `"completion"` columns (not just `"text"`)
- `TrainingArguments` → `SFTConfig` with `max_length=2048`, `packing=False`, `dataset_num_proc=1`
- `SFTTrainer` now uses `processing_class=tokenizer` (TRL 0.24 API)
- Smoke test checks 2–3 updated: now tests prompt-ends-with-`</text>` and completion-ends-with-EOS at tokenization level
- EOS termination rate metric: currently unmeasurable from `evaluate_lora.py` because `skip_special_tokens=True` strips EOS in decode. Needs a code change to track at token-ID level if required.
