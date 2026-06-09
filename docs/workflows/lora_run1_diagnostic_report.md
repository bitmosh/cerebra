# LoRA Run 1 — Training/Inference Format Diagnostic Report

**Date:** 2026-06-09  
**Adapter:** `scripts/v02_training/output/lora_adapters/run_1780979597/adapter`  
**Base model:** `ibm-granite/granite-4.1-3b-base`  
**Eval output:** `scripts/v02_training/output/lora_run_1780979597_eval.json`

---

## Context

LoRA run 1 regressed badly against the v0.1.0 baseline:

| Metric | v0.1.0 baseline | LoRA run 1 | Delta |
|---|---|---|---|
| Partial-credit accuracy (calibration) | 65% | 10% | −55% |
| Strict accuracy (calibration) | — | 10% (3/30) | — |
| Parse failures (calibration) | — | 83% (25/30) | — |
| Partial-credit accuracy (test set) | — | 0% (0/24) | — |
| Parse failures (test set) | — | 96% (23/24) | — |

**Hypothesis under investigation:** training/inference format mismatch — the LoRA
learned the wrong target because of a structural difference between training and
inference.

---

## 1. Training data format

File: `scripts/v02_training/output/corpus/pass1_train.jsonl`  
Builder: `build_training_corpus.py` → `build_pass1_pair()`

**Keys per record:** `prompt`, `completion`, `d1_name`

**Prompt:** built by `_build_pass1_prompt(content)` — the same function call used
at inference. Prompt header is byte-for-byte identical between training and
inference. ✓

**Completion (all 169 pass1 records):**
```json
{"scores": {"EMPIRICAL": 0.0, "GENERATIVE": 0.0, "NORMATIVE": 1.0, "RELATIONAL": 0.0}, "confidence": 0.9, "primary_quadrant": "NORMATIVE"}
```
Key used: **`"primary_quadrant"`**.

**Training text seam** (last 30 chars of prompt → first 30 chars of completion):
```
...remains?\n```\n\n---\n\n\n</text>{"scores": {"EMPIRICAL": 0.0, ...
```
No separator between `</text>` and `{`. Raw concatenation, no EOS token appended.
The training text ends with the closing `}` of the JSON.

---

## 2. Inference prompt structure

The in-context JSON example embedded inside `_build_pass1_prompt()`:

```
Return ONLY valid JSON:
{"scores": {"EMPIRICAL": 0.0, "GENERATIVE": 0.0, "NORMATIVE": 0.0, "RELATIONAL": 0.0},
 "confidence": 0.0, "primary": "QUADRANT_NAME"}
```

Key used: **`"primary"`** — not `"primary_quadrant"`.

### Pass1 key mismatch

| Location | Key |
|---|---|
| Training completion (169/169 pass1 records) | `"primary_quadrant"` |
| In-context example shown in prompt to model | `"primary"` |
| Evaluator (`evaluate_lora.py`) | handles both via `p1_data.get("primary") or p1_data.get("primary_quadrant")` |

This inconsistency is **cosmetic for evaluation purposes** — the evaluator catches
either key. It is not the root cause of 83% parse failures, but it is confusing to
the model and should be fixed.

---

## 3. Training code path (train_lora.py)

```python
def _format_training_text(prompt: str, completion: str) -> str:
    return prompt + completion        # raw concatenation — no EOS appended
```

```python
trainer = WeightedSFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_ds,
    dataset_text_field="text",        # whole text as LM objective
    packing=False,
    # no response_template → loss computed over all tokens (prompt + completion)
    # no apply_chat_template()
)
```

**Tokenizer special token config** (from `adapter/tokenizer_config.json`):

```
eos_token:        <|end_of_text|>
bos_token:        <|end_of_text|>   ← same token ID as EOS
add_eos_token:    None              ← EOS is NOT auto-appended
add_bos_token:    None
chat_template:    absent
```

Granite 4.1 uses the same token for BOS and EOS. With `add_eos_token: None`,
training sequences do **not** get an EOS terminator after the completion JSON.
The model is never shown a clean stop signal.

---

## 4. Inference code path (evaluate_lora.py)

```python
def _generate(self, prompt: str, max_new_tokens: int = 256) -> str:
    full_prompt = (prompt + self.JSON_PRIME) if self.use_prime else prompt
    inputs = self.tokenizer(full_prompt, return_tensors="pt").to("cuda")
    input_len = inputs["input_ids"].shape[1]
    outputs = self.model.generate(
        ...
        max_new_tokens=max_new_tokens,
        do_sample=False,
        eos_token_id=self.tokenizer.eos_token_id,
    )
    new_tokens = outputs[0][input_len:]
    decoded = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
```

- No `apply_chat_template()`. ✓ Consistent with training.
- `eos_token_id` is set — generation stops if the model emits EOS. But the model
  was never trained to emit EOS, so `max_new_tokens=256` is the only hard stop.
- `use_prime: false` for both evaluated runs — auto-detect found non-empty output
  without the prime. This means the model *generates something*, but that something
  is failing to parse as valid quadrant JSON 83% of the time.

---

## 5. Training vs inference side-by-side

| Dimension | Training | Inference |
|---|---|---|
| Prompt builder | `_build_pass1_prompt()` | `_build_pass1_prompt()` |
| Prompt content | Identical | Identical |
| Chat template | Not applied | Not applied |
| JSON example key in prompt | `"primary"` | `"primary"` |
| Expected output key | `"primary_quadrant"` (completion) | handled by evaluator |
| Separator after `</text>` | None (raw concat) | None |
| EOS after completion | **None** | `eos_token_id` arg set |
| Loss masking | All tokens | N/A |

The prompt path is structurally consistent — **no chat template or tokenization
mode mismatch** between training and inference.

---

## 6. Raw output for failing cases — NOT available

`FixtureResult` stores `predicted`, `confidence`, `quadrant`, `latency_s` — but
**not the raw generation string**. For the 25 pass1 failures we know:

- `predicted: None, confidence: 0.0, quadrant: None` — pass1 returned nothing parseable
- Auto-detect on `clear_01` with 10 tokens found non-empty output → the model
  generates *something*, but the full generation for `clear_01` failed pass1 parsing

We cannot distinguish between these failure modes without raw output:

| Mode | Description |
|---|---|
| **(A)** | Model outputs valid JSON but with invalid/placeholder quadrant values |
| **(B)** | Model outputs natural language before/instead of JSON (base document-continuation) |
| **(C)** | Model generates truncated/malformed JSON — runs into `max_new_tokens=256` limit mid-object |
| **(D)** | Model generates valid JSON but with completely wrong top-level structure |

`base_raw_dump.txt` was generated **with** JSON prime (`\n{"scores":`), so it
doesn't tell us what the base model or LoRA outputs without the prime.

---

## 7. Confirmed issues

### Issue 1 — No EOS in training sequences *(root cause candidate)*

`_format_training_text = prompt + completion` appends nothing.  
Tokenizer `add_eos_token: None` — no automatic appending.  
The model is never trained to stop cleanly after the closing `}`.  
At inference, `max_new_tokens=256` is the only stop gate. If the model
never learned to terminate, it may generate 256 tokens of continuation past
the JSON, corrupting the output that `_extract_json` tries to parse.

### Issue 2 — Pass1 key inconsistency (`"primary_quadrant"` vs `"primary"`)

Minor; handled by evaluator. Should be fixed for clarity (training completion
should match the in-prompt example schema). Not the root cause of 83% failures.

### Issue 3 — Raw output is unobserved *(diagnostic gap)*

`evaluate_lora.py` doesn't store the raw generation string. The actual failure
mode (A/B/C/D above) is unknown. **This is the most important thing to add
before the next diagnostic iteration.**

---

## 8. What is confirmed sound

- Prompt text is identical at training and inference — same function, same format.
- No chat template inconsistency — neither path uses one.
- Tokenization is consistent (both call `tokenizer(text, return_tensors="pt")`).
- The `_extract_json` brace-matcher is robust enough that trailing garbage after
  valid JSON should still parse — mode C is less likely than B.

---

## 9. Most likely hypothesis

The base Granite 4.1 base model without JSON prime defaults to
document-continuation (it treats the prompt as a partial document and continues
generating document-style text after `</text>`). The LoRA adapted this for a
subset of inputs (5/30 worked) but not consistently, likely because:

1. The training set was small (169 pass1 examples × 3 epochs ≈ 507 update steps)
2. EOS was never trained, so generation at inference runs past the JSON for most
   inputs and/or generates non-JSON text

This is a **hypothesis, not a confirmed diagnosis**.

---

## 10. Recommended next step (before any retraining)

Add `raw_output: str` to `FixtureResult` in `evaluate_lora.py` and store the full
decoded generation string before it hits `_extract_json`. Print it (or store it in
the JSON output) for the failing cases. That single field would let us distinguish
A/B/C/D definitively and pick the right fix.
