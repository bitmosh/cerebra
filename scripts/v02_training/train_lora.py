# SPDX-License-Identifier: Apache-2.0
"""
Unsloth QLoRA training script for Cerebra v0.2 SKU classifier.

Trains a LoRA adapter on Granite 4.1 3B base using the Path A-lite corpus
(Pass 1 + Pass 2 JSONL pairs), with inverse-frequency class balancing.

Run with the training venv:
    <lora-venv>/bin/python \\
        scripts/v02_training/train_lora.py [options]

Modes:
    --sandbox       Validate pipeline: 50 random records, 1 epoch, adapter NOT saved.
    (default)       Full training with Path A-lite corpus.

Flags:
    --corpus-dir    Directory with pass1_train.jsonl etc. (default: output/corpus)
    --output-dir    Where to save the adapter (default: output/lora_adapters)
    --epochs N      Number of epochs (default: 3)
    --rank N        LoRA rank (default: 16)
    --lr FLOAT      Learning rate (default: 2e-4)
    --run-name STR  Label for output directory (default: auto from timestamp)
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

STAGE2_PATH = Path(__file__).parent / "output/stage2_consensus.jsonl"
DEFAULT_CORPUS_DIR = Path(__file__).parent / "output/corpus"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output/lora_adapters"

HF_BASE_MODEL = "ibm-granite/granite-4.1-3b-base"
MAX_SEQ_LEN = 2048
_RESPONSE_TEMPLATE = "</text>"   # boundary between prompt and completion in all training records
_EOS = "<|end_of_text|>"         # verified: granite-4.1-3b-base tokenizer.eos_token

D1_QUADRANT = {
    "OBSERVATION": "EMPIRICAL", "PATTERN": "EMPIRICAL",
    "MECHANISM": "EMPIRICAL", "PHENOMENON": "EMPIRICAL",
    "TECHNIQUE": "GENERATIVE", "DESIGN": "GENERATIVE",
    "CREATION": "GENERATIVE", "TOOL": "GENERATIVE",
    "PRINCIPLE": "NORMATIVE", "JUDGMENT": "NORMATIVE",
    "GOAL": "NORMATIVE", "CONSTRAINT": "NORMATIVE",
    "EVENT": "RELATIONAL", "AGENT": "RELATIONAL",
    "CONTEXT": "RELATIONAL", "RELATION": "RELATIONAL",
}


# ── Data loading ───────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _format_training_text(prompt: str, completion: str) -> str:
    return prompt + completion


def load_corpus(corpus_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Load pass1+pass2 train/val/test from corpus_dir."""
    splits = {}
    for split in ("train", "val", "test"):
        p1 = _load_jsonl(corpus_dir / f"pass1_{split}.jsonl")
        p2 = _load_jsonl(corpus_dir / f"pass2_{split}.jsonl")
        splits[split] = p1 + p2
    return splits["train"], splits["val"], splits["test"]


def build_sandbox_corpus(n: int = 50) -> list[dict]:
    """
    Build a throwaway training set from n random stage2_consensus records.
    Used for pipeline validation only — adapter is not saved.
    """
    from cerebra.cognition.sku_classifier import _build_pass1_prompt, _build_pass2_prompt

    all_records = _load_jsonl(STAGE2_PATH)
    rng = random.Random(123)
    sample = rng.sample(all_records, min(n, len(all_records)))

    pairs: list[dict] = []
    for r in sample:
        quadrant = r["quadrant"]
        d1_name = r["d1_name"]
        content = r["content"]

        # Pass 1 example
        p1_prompt = _build_pass1_prompt(content)
        scores_q = {"EMPIRICAL": 0.0, "GENERATIVE": 0.0, "NORMATIVE": 0.0, "RELATIONAL": 0.0}
        scores_q[quadrant] = 1.0
        p1_completion = json.dumps({"scores": scores_q, "confidence": 0.9, "primary": quadrant}) + _EOS
        pairs.append({"prompt": p1_prompt, "completion": p1_completion, "d1_name": d1_name})

        # Pass 2 example
        p2_prompt = _build_pass2_prompt(content, quadrant)
        scores_d1: dict[str, float] = {}
        for cat, q in D1_QUADRANT.items():
            scores_d1[cat] = 1.0 if cat == d1_name else 0.0
        p2_completion = json.dumps({"scores": scores_d1, "confidence": 0.9, "primary": d1_name}) + _EOS
        pairs.append({"prompt": p2_prompt, "completion": p2_completion, "d1_name": d1_name})

    rng.shuffle(pairs)
    return pairs


def compute_class_weights(samples: list[dict]) -> dict[str, float]:
    """Inverse-frequency class weights, normalized so mean weight = 1."""
    counts: dict[str, int] = defaultdict(int)
    for s in samples:
        counts[s["d1_name"]] += 1
    if not counts:
        return {}
    total = len(samples)
    raw_weights = {cat: total / count for cat, count in counts.items()}
    mean_w = sum(raw_weights.values()) / len(raw_weights)
    return {cat: w / mean_w for cat, w in raw_weights.items()}


def build_hf_dataset(samples: list[dict]):
    """Build a HuggingFace Dataset from list of {prompt, completion, d1_name} dicts.
    Exposes 'prompt' and 'completion' columns so SFTConfig.completion_only_loss can mask the prompt."""
    from datasets import Dataset
    data = {
        "prompt": [s["prompt"] for s in samples],
        "completion": [s["completion"] for s in samples],
        "d1_name": [s["d1_name"] for s in samples],
    }
    return Dataset.from_dict(data)


# ── Training ───────────────────────────────────────────────────────────────────

def train(
    train_samples: list[dict],
    val_samples: list[dict] | None,
    *,
    run_name: str,
    output_dir: Path,
    epochs: int = 3,
    rank: int = 16,
    lr: float = 2e-4,
    save_adapter: bool = True,
    post_train_fn=None,
) -> dict:
    """
    Run QLoRA training. Returns summary dict.
    Class balancing via WeightedRandomSampler (inverse-frequency).
    """
    import torch
    from unsloth import FastLanguageModel, is_bfloat16_supported
    from trl import SFTTrainer, SFTConfig
    from torch.utils.data import WeightedRandomSampler

    # ── Load model ─────────────────────────────────────────────────────────────
    print(f"\nLoading {HF_BASE_MODEL} (4-bit)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=HF_BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
        dtype=None,
    )

    # ── Apply LoRA ─────────────────────────────────────────────────────────────
    model = FastLanguageModel.get_peft_model(
        model,
        r=rank,
        lora_alpha=rank * 2,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        use_rslora=False,
    )
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  LoRA rank={rank}, alpha={rank*2}")
    print(f"  Trainable params: {trainable:,} / {total:,} ({trainable*100/total:.2f}%)")

    # ── Datasets ───────────────────────────────────────────────────────────────
    train_ds = build_hf_dataset(train_samples)
    val_ds = build_hf_dataset(val_samples) if val_samples else None

    # ── Class weights → WeightedRandomSampler ─────────────────────────────────
    class_weights = compute_class_weights(train_samples)
    sample_weights = [class_weights.get(s["d1_name"], 1.0) for s in train_samples]
    print(f"\nClass weights (inverse-frequency, normalized mean=1):")
    for cat, w in sorted(class_weights.items(), key=lambda x: -x[1])[:8]:
        count = sum(1 for s in train_samples if s["d1_name"] == cat)
        print(f"  {cat:<12s}: {count:3d} samples  w={w:.2f}")
    if len(class_weights) > 8:
        print(f"  ... and {len(class_weights) - 8} more categories")

    sampler = WeightedRandomSampler(
        weights=torch.tensor(sample_weights, dtype=torch.float64),
        num_samples=len(sample_weights),
        replacement=True,
    )

    # ── Trainer ────────────────────────────────────────────────────────────────
    # Subclass SFTTrainer to inject WeightedRandomSampler.
    # transformers ≥5.x passes dataset as positional arg — accept and ignore.
    class WeightedSFTTrainer(SFTTrainer):
        def _get_train_sampler(self, dataset=None):
            return sampler

    run_output = output_dir / run_name
    run_output.mkdir(parents=True, exist_ok=True)

    grad_accum = 4
    effective_batch = 1 * grad_accum
    steps_per_epoch = math.ceil(len(train_samples) / effective_batch)

    training_args = SFTConfig(
        output_dir=str(run_output / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=grad_accum,
        warmup_steps=max(5, steps_per_epoch // 10),
        learning_rate=lr,
        weight_decay=0.01,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=max(1, steps_per_epoch // 5),
        eval_strategy="epoch" if val_ds else "no",
        save_strategy="no",
        seed=42,
        report_to="none",
        optim="adamw_8bit",
        lr_scheduler_type="linear",
        # SFT-specific: dataset has "prompt"/"completion" cols; mask prompt tokens
        max_length=MAX_SEQ_LEN,
        packing=False,
        dataset_num_proc=1,
        completion_only_loss=True,
    )

    trainer = WeightedSFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=training_args,
    )

    print(f"\nTraining: {len(train_samples)} examples, {epochs} epoch(s), "
          f"lr={lr}, rank={rank}, batch=1 (accum={grad_accum})")
    print(f"Steps per epoch: {steps_per_epoch}  |  Total steps: {steps_per_epoch * epochs}\n")

    t0 = time.monotonic()
    train_result = trainer.train()
    elapsed = time.monotonic() - t0

    print(f"\nTraining complete in {elapsed/60:.1f} min")
    print(f"  Final training loss: {train_result.training_loss:.4f}")

    if post_train_fn is not None:
        post_train_fn(model, tokenizer)

    # ── Save adapter ───────────────────────────────────────────────────────────
    adapter_path = run_output / "adapter"
    if save_adapter:
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        print(f"\n  Adapter saved to: {adapter_path}")
    else:
        print("\n  Sandbox mode — adapter NOT saved.")

    summary = {
        "run_name": run_name,
        "save_adapter": save_adapter,
        "train_samples": len(train_samples),
        "val_samples": len(val_samples) if val_samples else 0,
        "epochs": epochs,
        "rank": rank,
        "lr": lr,
        "seed": 42,
        "response_template": _RESPONSE_TEMPLATE,
        "effective_batch": effective_batch,
        "final_train_loss": round(train_result.training_loss, 5),
        "elapsed_min": round(elapsed / 60, 1),
        "adapter_path": str(adapter_path) if save_adapter else None,
    }

    if save_adapter:
        (run_output / "training_summary.json").write_text(json.dumps(summary, indent=2))

    return summary


# ── Smoke test ────────────────────────────────────────────────────────────────

def _run_smoke_test(corpus_dir: Path) -> bool:
    """
    Pre-flight smoke test for Phase 2 pipeline changes. Run before full training.
    Returns True if all hard checks (1–3) pass.
    Check 4 (inference EOS) is informational for 1-epoch/5-record training.
    """
    import torch
    from transformers import AutoTokenizer

    print("\n=== SMOKE TEST — Phase 2 pre-flight checks ===\n")
    passed = True

    # Load tokenizer only (no model — fast)
    tokenizer = AutoTokenizer.from_pretrained(HF_BASE_MODEL)
    eos = tokenizer.eos_token
    eos_id = tokenizer.eos_token_id
    print(f"Tokenizer loaded. eos_token={repr(eos)} id={eos_id}\n")

    # Load 5 records from corpus (3 pass1 + 2 pass2)
    p1 = _load_jsonl(corpus_dir / "pass1_train.jsonl")[:3]
    p2 = _load_jsonl(corpus_dir / "pass2_train.jsonl")[:2]
    samples = p1 + p2
    texts = [_format_training_text(s["prompt"], s["completion"]) for s in samples]
    print(f"Loaded {len(samples)} corpus records for smoke checks.\n")

    # ── CHECK 1: text fields end with EOS ─────────────────────────────────────
    bad = [i for i, t in enumerate(texts) if not t.endswith(eos)]
    if bad:
        print(f"✗ CHECK 1 FAIL: {len(bad)}/{len(texts)} text fields do not end with EOS")
        for i in bad:
            print(f"  record {i}: ends with {repr(texts[i][-30:])}")
        passed = False
    else:
        print(f"✓ CHECK 1: all {len(texts)} text fields end with {repr(eos)}")

    # ── CHECK 2: template anchor present at end of prompt tokens ─────────────
    # SFTConfig completion_only_loss splits on "prompt"/"completion" columns directly.
    # Check that prompt tokenizes to end with </text> — confirms the split boundary.
    template_ids = tokenizer(_RESPONSE_TEMPLATE, add_special_tokens=False)["input_ids"]
    prompt_ids_check2 = tokenizer(samples[0]["prompt"], add_special_tokens=False)["input_ids"]
    prompt_tail = prompt_ids_check2[-len(template_ids):]
    if prompt_tail != template_ids:
        print(f"✗ CHECK 2 FAIL: prompt does not end with {repr(_RESPONSE_TEMPLATE)} "
              f"token IDs {template_ids} — got {prompt_tail}")
        passed = False
    else:
        print(f"✓ CHECK 2: prompt ends with {repr(_RESPONSE_TEMPLATE)} (token IDs={template_ids})")

    # ── CHECK 3: completion starts with JSON and ends with EOS ────────────────
    # With SFTConfig completion_only_loss=True + prompt/completion columns,
    # all prompt tokens are masked to -100 and completion tokens are trained.
    # Verify the completion field has the right shape.
    completion_ids_check3 = tokenizer(samples[0]["completion"], add_special_tokens=False)["input_ids"]
    n_prompt = len(prompt_ids_check2)
    n_completion = len(completion_ids_check3)
    n_total = n_prompt + n_completion
    last_completion_id = completion_ids_check3[-1]
    eos_in_labels = last_completion_id == eos_id

    if n_completion == 0:
        print(f"✗ CHECK 3 FAIL: completion tokenizes to 0 tokens")
        passed = False
    elif not eos_in_labels:
        print(f"✗ CHECK 3 FAIL: last completion token {last_completion_id} is not EOS {eos_id}")
        print(f"           Completion tail (last 5 IDs): {completion_ids_check3[-5:]}")
        passed = False
    else:
        print(f"✓ CHECK 3: prompt={n_prompt} tok (masked) | completion={n_completion} tok (trained)")
        print(f"           Total sequence: {n_total} tokens (max={MAX_SEQ_LEN})")
        print(f"           Last completion token: {last_completion_id} (EOS ✓)")

    if not passed:
        print("\n✗ SMOKE TEST FAILED — fix hard checks before full training.")
        return False

    print("\nChecks 1–3 passed. Running 1-epoch training on 5 records (check 4)...\n")

    # ── CHECK 4: inference EOS termination (soft — informational for 1 epoch) ──
    smoke_output = Path(__file__).parent / "output/lora_adapters/smoke"

    def _check4(model, tokenizer):
        from cerebra.cognition.sku_classifier import _build_pass1_prompt
        from unsloth import FastLanguageModel
        FastLanguageModel.for_inference(model)
        test_content = "A utility function that extracts JSON from raw model output by matching balanced braces."
        test_prompt = _build_pass1_prompt(test_content)
        inputs = tokenizer(test_prompt, return_tensors="pt").to("cuda")
        input_len = inputs["input_ids"].shape[1]
        import torch
        with torch.no_grad():
            out = model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=64,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        new_ids = out[0][input_len:]
        n_gen = len(new_ids)
        eos_triggered = new_ids[-1].item() == tokenizer.eos_token_id
        decoded = tokenizer.decode(new_ids, skip_special_tokens=False)
        print(f"\n── CHECK 4 (informational): inference EOS termination")
        print(f"   Generated {n_gen} tokens (max=64)")
        if eos_triggered:
            print(f"   ✓ Stopped at <|end_of_text|> at token {n_gen}/64")
        else:
            print(f"   ~ Hit max_new_tokens=64 without EOS (expected for 1 epoch — not a failure)")
        print(f"   Output (first 200 chars): {repr(decoded[:200])}")

    train(
        train_samples=samples,
        val_samples=None,
        run_name="smoke",
        output_dir=smoke_output,
        epochs=1,
        rank=16,
        lr=2e-4,
        save_adapter=False,
        post_train_fn=_check4,
    )

    print("\n✓ SMOKE TEST PASSED — all hard checks (1–3) cleared. Proceed with full training.")
    return True


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="Pre-flight smoke test: 5 corpus records, checks EOS/anchor/labels/inference. "
                             "Must pass before full training.")
    parser.add_argument("--sandbox", action="store_true",
                        help="Validate pipeline: 50 random records, 1 epoch, no save.")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--run-name", type=str, default=None)
    args = parser.parse_args()

    if args.smoke:
        ok = _run_smoke_test(args.corpus_dir)
        sys.exit(0 if ok else 1)

    if args.sandbox:
        print("=== SANDBOX MODE: pipeline validation only (50 records, 1 epoch) ===")
        train_samples = build_sandbox_corpus(50)
        run_name = args.run_name or "sandbox"
        summary = train(
            train_samples=train_samples,
            val_samples=None,
            run_name=run_name,
            output_dir=args.output_dir,
            epochs=1,
            rank=args.rank,
            lr=args.lr,
            save_adapter=False,
        )
    else:
        if not args.corpus_dir.exists():
            print(f"ERROR: corpus directory not found: {args.corpus_dir}")
            print("Run build_training_corpus.py first.")
            sys.exit(1)

        print("=== FULL TRAINING: Path A-lite corpus ===")
        train_samples, val_samples, test_samples = load_corpus(args.corpus_dir)
        print(f"  Train: {len(train_samples)} pairs  |  Val: {len(val_samples)} pairs  "
              f"|  Test: {len(test_samples)} pairs (held-out, not used here)")

        run_name = args.run_name or f"run_{int(time.time())}"
        summary = train(
            train_samples=train_samples,
            val_samples=val_samples,
            run_name=run_name,
            output_dir=args.output_dir,
            epochs=args.epochs,
            rank=args.rank,
            lr=args.lr,
            save_adapter=True,
        )

    print(f"\n{'='*60}")
    print("Summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print()
    if summary.get("adapter_path"):
        print(f"Adapter: {summary['adapter_path']}")
        print("Next step: merge adapter → GGUF → Ollama → evaluate.")


if __name__ == "__main__":
    main()
