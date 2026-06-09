# Deferred: v0.2 LoRA Training Track

**Status:** Benched 2026-06-09  
**Decision:** Ship Granite 4.1 3B instruct via Ollama as production classifier for the v0.1.x line. Resume LoRA when resume conditions are met.  
**Resume conditions:** See §4 below.

---

## 1. Work completed

### Phase 1 — Run 1 (run_1780979597)

- **Base model:** `ibm-granite/granite-4.1-3b-base` (4-bit QLoRA via Unsloth)
- **Corpus:** 214 records (169 train / 21 val / 24 held-out test), Path A-lite selection rules
- **Calibration result:** 10% partial-credit, 25/30 parse failures (83%)
- **Root cause identified (Phase 1 diagnostic):** Three compounding errors:
  1. `"primary_quadrant"` key in pass-1 completions but `"primary"` in inference prompt's in-context example
  2. No EOS token appended to completions — model had no stop signal; fell back to document continuation (Mode B failures)
  3. No completion-only loss masking — model trained on both prompt and completion tokens, reinforcing document continuation

### Phase 2 — Run 2 (run_1781024893) + 6-epoch diagnostic

**Methodology changes applied:**
- `build_pass1_pair()`: `"primary_quadrant"` → `"primary"`, EOS appended (`<|end_of_text|>`)
- `build_pass2_pair()`: EOS appended
- `DataCollatorForCompletionOnlyLM` unavailable in TRL 0.24 → switched to `SFTConfig(completion_only_loss=True)` with `"prompt"`/`"completion"` dataset columns; prompt tokens masked to -100
- `TrainingArguments` → `SFTConfig`, `processing_class=tokenizer` (TRL 0.24 API)
- Smoke test (4 checks) confirms EOS, prompt boundary, completion masking, and EOS-termination before each run

**Run 2 calibration result (3 epochs, run_1781024893):**

| Metric | Run 1 | Run 2 (Phase 2) | v0.1.0 instruct baseline |
|--------|-------|-----------------|--------------------------|
| Parse failures | 25/30 (83%) | **0/30 (0%)** | 0/30 |
| Strict accuracy | 10% | **46.7%** | — |
| Partial-credit accuracy | 10% | **48.3%** | 65% |

**6-epoch diagnostic:** Val loss minimum at epoch 3 (0.028); rises at epoch 4 (0.038). Overfitting confirmed — 3-epoch adapter is optimal. 6-epoch adapter is 43.3% strict (worse).

**Adapter:** `scripts/v02_training/output/lora_adapters/run_1781024893/adapter`

### Phase 3 — Coverage audit (partial, task was halted)

Pass-level breakdown on run_1781024893:

| Pass | Accuracy |
|------|---------|
| Pass-1 quadrant routing | 56.7% (17/30) |
| Pass-2 D1 given correct quadrant | 82.4% (14/17) |

Pass-2 is performing well. Pass-1 is the bottleneck.

**Corpus distribution (all 214 records):**

| Quadrant | Count | Notes |
|----------|-------|-------|
| NORMATIVE | 107 | PRINCIPLE: 104, CONSTRAINT: 3 |
| EMPIRICAL | 52 | OBSERVATION: 31, MECHANISM: 16, PATTERN: 4, PHENOMENON: 1 |
| GENERATIVE | 45 | TECHNIQUE: 25, DESIGN: 18, TOOL: 1, CREATION: 1 |
| **RELATIONAL** | **10** | RELATION: 8, CONTEXT: 2, **AGENT: 0, EVENT: 0** |

RELATIONAL is structurally underrepresented (10:1 vs NORMATIVE). The 8 RELATION training records cover a narrow register: Mermaid diagrams, typed graph edge vocabulary, architectural connectors. The calibration RELATIONAL fixtures test four distinct sub-patterns:
- AGENT: person-actor ("bitmosh is the sole developer") — **zero training examples**
- EVENT: milestone ("Phase 0 complete at commit 5747c7e") — **zero training examples**
- CONTEXT: filesystem context (vault directory structure) — stylistically different from 2 CONTEXT records in corpus
- RELATION: prose system-relationship ("LumaWeave visualizes; Cerebra produces") — training records cover graph-edge register only

**Coverage judgment:** "Training records cover narrow patterns; fixtures test broader patterns." Class weighting alone cannot fix this.

---

## 2. Key learnings

**Confirmed working:**
- EOS + `SFTConfig(completion_only_loss=True)` fully resolves parse failures. Run 1's 83% failure rate drops to 0%.
- Pass-2 D1 classification (within-quadrant) works well at 82.4% given correct quadrant — the 16-way D1 problem is tractable with 214 records once the training format is correct.
- QLoRA via Unsloth on 4070 Super (12GB) is viable: 4.7 min per 3-epoch full run, ~10 min for 6 epochs. Hardware is not a constraint.
- `SFTConfig.completion_only_loss=True` + `"prompt"`/`"completion"` dataset columns is the correct TRL 0.24 pattern; `DataCollatorForCompletionOnlyLM` was removed in TRL 0.24.

**Confirmed broken:**
- The 214-record Path A-lite corpus cannot reach the v0.1.0 baseline (65%) for the 4-quadrant routing problem. 10 RELATIONAL records covering 2 of 4 sub-categories (RELATION and CONTEXT only) cannot teach quadrant boundaries.

**Structural constraint:**
The corpus imbalance is architectural, not methodological. Class weighting at the D1 level does not compensate for absent D1 categories (AGENT, EVENT) or narrow-register coverage (RELATION, CONTEXT). The resume-blocker is not the training code — it is corpus breadth.

---

## 3. What changed in the codebase

The following scripts were modified during Phase 2 work. All changes are on `main` and are forward-compatible with a future Phase 3+ training run:

- **`scripts/v02_training/build_training_corpus.py`**: `"primary_quadrant"` → `"primary"` in pass-1 completions; `_EOS = "<|end_of_text|>"` appended to all completions.
- **`scripts/v02_training/train_lora.py`**: `SFTConfig` replaces `TrainingArguments`; `completion_only_loss=True`; `build_hf_dataset` exposes `"prompt"`/`"completion"` columns; smoke test updated; `processing_class=tokenizer` (TRL 0.24 API); `seed=42` logged in summary.
- **`scripts/v02_training/evaluate_lora.py`**: `raw_output_p2` captured; `classify()` returns 5-tuple; `--calibration-only` flag added.
- **`docs/agent/plans/v02_lora_phase2_plan.md`**: Complete Phase 1/2/3 diagnostic plan with §7 results appendix.

No production path files (`cerebra/cognition/`) were modified during LoRA work.

---

## 4. Resume conditions

Resume this track when **either** of the following is true:

**Condition A — Corpus grown to 1000+ records**  
With 214 records, RELATIONAL quadrant is structurally underrepresented. At 1000+ records (natural growth as Cerebra ingests more content), AGENT, EVENT, and CONTEXT will have meaningful training examples without manual augmentation. This is the preferred path: let the corpus grow from production use rather than hand-crafting synthetic examples.

**Condition B — Specific downstream capability requires the accuracy lift**  
If a feature in v0.3+ (e.g., SKU-based retrieval, SKU-conditioned synthesis, leeway routing) requires >65% classification accuracy to function correctly, that creates a forcing function. Resume LoRA with explicit scope: which capability fails at 65%, what accuracy threshold unblocks it, and measure against that threshold.

Do NOT resume to hit an accuracy number in isolation. Resume when a capability need creates clear success criteria.

---

## 5. Resume plan

When resume conditions are met, the Phase 3 plan was largely scoped and can be picked up from where it stopped:

**Where Phase 3 was halted:** STOP GATE 1 — RELATIONAL coverage audit completed; awaiting confirmation before Task 2 (AGENT augmentation proposal). At that point, the task was benched in favor of shipping Granite 4.1 3B instruct.

**Phase 3 tasks (already designed, partially executed):**
1. **AGENT corpus augmentation:** Mine Cerebra source chunks for person-actor, org-actor, and system-actor content. Propose 15 records. Ryan reviews and approves individual records before training. Target: 15 AGENT records added.
2. **EVENT and CONTEXT augmentation (newly required, not in original Phase 3 scope):** Phase 3 audit revealed CONTEXT training records are stylistically wrong (graph-context vs filesystem-context) and EVENT has zero examples. Both need augmentation alongside AGENT.
3. **Quadrant-level class weights for pass-1 training:** `build_training_corpus.py` + `train_lora.py` changes to apply per-quadrant inverse-frequency weights during pass-1 sampling (separate from the existing D1-level weights for pass-2).
4. **EOS termination metric:** `evaluate_lora.py` — capture whether each generation terminated by EOS vs max_new_tokens. Requires inspecting raw token IDs before `skip_special_tokens=True` decode.

**Three-tier evaluation framework (from v02_lora_planning_v3.md):**
- **Tier 1:** 30 calibration fixtures (hand-labeled, Round 2 audit). Target: ≥75% partial-credit.
- **Tier 2:** 24 held-out test records (Path A-lite, never seen during training). Must match or exceed Tier 1.
- **Tier 3:** 50-100 production chunks, cross-model agreement as ground truth. Should improve, not degrade, vs instruct baseline.
- **Tier 4:** Production observation post-deployment (ongoing).

Pass-2 D1 accuracy (82.4%) already clears the target for within-quadrant classification. Pass-1 quadrant routing (56.7%) is the only gap to close.

**What not to do on resume:**
- Do not change hyperparameters (rank=16, lr=2e-4, 3 epochs confirmed optimal)
- Do not introduce `apply_chat_template` (no instruct variant for base-model SFT)
- Do not synthesize artificial training records — mine Cerebra's own content
- Do not run more than 3 epochs (overfitting confirmed at epoch 4)

---

## 6. References

- Phase 1/2 plan with §7 results: `docs/agent/plans/v02_lora_phase2_plan.md`
- Phase 3 corpus audit (STOP GATE 1 report): `docs/agent/plans/v02_lora_phase2_plan.md` §7 + Phase 3 STOP GATE 1 Discord message (2026-06-09)
- v0.2 planning v2: `docs/planning/v02_lora_planning_v2.md`
- v0.2 planning v3: `docs/workflows/v02_lora_planning_v3.md`
- Run 1 diagnostic: `docs/workflows/lora_run1_diagnostic_report.md`
- Training scripts: `scripts/v02_training/`
- Adapter (Phase 2 best): `scripts/v02_training/output/lora_adapters/run_1781024893/adapter`
