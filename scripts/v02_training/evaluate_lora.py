"""
Evaluate a LoRA adapter against the 30 calibration fixtures and the 24-example
held-out test set from build_training_corpus.py.

Run with the training venv:
    /home/boop/Projects/cerebra-v02-training/.venv/bin/python \\
        scripts/v02_training/evaluate_lora.py \\
        --adapter output/lora_adapters/run_1780979597/adapter \\
        --output  output/lora_run_1780979597_eval.json

Flags:
    --adapter PATH   Path to the LoRA adapter directory (required).
    --output  PATH   Where to save the full results JSON.
    --no-prime       Force disable JSON prime (use if LoRA fixed EOS issue).
    --prime          Force enable JSON prime.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from tests.fixtures.sku_fixtures import (
    SKU_FIXTURES,
    CLEAR_FIXTURES,
    HARD_FIXTURES,
    AMBIGUOUS_FIXTURES,
    SKUFixture,
)
from cerebra.cognition.sku_classifier import _build_pass1_prompt, _build_pass2_prompt

CORPUS_DIR = Path(__file__).parent / "output/corpus"
DEFAULT_OUTPUT = Path(__file__).parent / "output/lora_eval.json"
HF_BASE_MODEL = "ibm-granite/granite-4.1-3b-base"
CONF_THRESHOLD = 0.5

QUADRANT_NAMES = {"EMPIRICAL", "GENERATIVE", "NORMATIVE", "RELATIONAL"}
D1_NAMES = {
    "OBSERVATION", "PATTERN", "MECHANISM", "PHENOMENON",
    "TECHNIQUE", "DESIGN", "CREATION", "TOOL",
    "PRINCIPLE", "JUDGMENT", "GOAL", "CONSTRAINT",
    "EVENT", "AGENT", "CONTEXT", "RELATION",
}

# v0.1.0 documented baseline (instruct GGUF Q4_K_M, 30 calibration fixtures)
V01_PARTIAL_CREDIT = 0.65


# ── JSON extraction (same as base_vs_instruct.py) ─────────────────────────────

def _extract_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# ── LoRA classifier ────────────────────────────────────────────────────────────

class LoRAClassifier:
    JSON_PRIME = '\n{"scores":'

    def __init__(self, adapter_path: Path, use_prime: bool | None = None) -> None:
        import torch
        from unsloth import FastLanguageModel
        from peft import PeftModel

        print(f"\nLoading base model ({HF_BASE_MODEL}) + adapter...")
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=HF_BASE_MODEL,
            max_seq_length=2048,
            load_in_4bit=True,
            dtype=None,
        )
        self.model = PeftModel.from_pretrained(self.model, str(adapter_path))
        FastLanguageModel.for_inference(self.model)
        print(f"  Adapter loaded from: {adapter_path}")

        if use_prime is None:
            self.use_prime = self._autodetect_prime()
        else:
            self.use_prime = use_prime
        print(f"  JSON prime: {'enabled' if self.use_prime else 'disabled (LoRA produces output directly)'}\n")

    def _autodetect_prime(self) -> bool:
        """Return True if the model emits EOS immediately without JSON prime."""
        import torch
        test_prompt = _build_pass1_prompt(SKU_FIXTURES[0].content)
        inputs = self.tokenizer(test_prompt, return_tensors="pt").to("cuda")
        input_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            out = self.model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=10,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        new_ids = out[0][input_len:].tolist()
        decoded = self.tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        # If empty or EOS-only, the model isn't generating — prime needed
        needs_prime = not decoded
        if needs_prime:
            print("  Auto-detect: EOS immediately without prime — enabling JSON prime.")
        else:
            print(f"  Auto-detect: model generates output without prime ({repr(decoded[:40])}).")
        return needs_prime

    def _generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        import torch
        full_prompt = (prompt + self.JSON_PRIME) if self.use_prime else prompt
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to("cuda")
        input_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = outputs[0][input_len:]
        decoded = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return (self.JSON_PRIME + decoded) if self.use_prime else decoded

    def classify(self, content: str) -> tuple[str | None, float, str | None, str, str]:
        """Two-pass classification. Returns (d1_name, confidence, quadrant, p1_raw, p2_raw)."""
        # Pass 1 — quadrant
        p1_raw = self._generate(_build_pass1_prompt(content))
        p1_data = _extract_json(p1_raw)

        quadrant: str | None = None
        if p1_data:
            raw_q = p1_data.get("primary") or p1_data.get("primary_quadrant")
            if raw_q and raw_q.upper() in QUADRANT_NAMES:
                quadrant = raw_q.upper()
            elif isinstance(p1_data.get("scores"), dict):
                valid = {k: v for k, v in p1_data["scores"].items() if k in QUADRANT_NAMES}
                if valid:
                    quadrant = max(valid, key=valid.get)
        if quadrant is None:
            return None, 0.0, None, p1_raw, ""

        # Pass 2 — D1 within quadrant
        p2_raw = self._generate(_build_pass2_prompt(content, quadrant))
        p2_data = _extract_json(p2_raw)

        if not p2_data:
            return None, 0.0, quadrant, p1_raw, p2_raw

        d1 = p2_data.get("primary")
        if d1:
            d1 = d1.upper()
        confidence = float(p2_data.get("confidence", 0.0))

        if d1 not in D1_NAMES:
            if isinstance(p2_data.get("scores"), dict):
                valid = {k: v for k, v in p2_data["scores"].items() if k in D1_NAMES}
                if valid:
                    d1 = max(valid, key=valid.get)
                    confidence = valid.get(d1, 0.0)

        if d1 not in D1_NAMES:
            return None, 0.0, quadrant, p1_raw, p2_raw

        return d1, confidence, quadrant, p1_raw, p2_raw


# ── Result data ────────────────────────────────────────────────────────────────

@dataclass
class FixtureResult:
    expected: str
    predicted: str | None
    confidence: float
    quadrant: str | None
    latency_s: float
    fixture_id: str = ""
    ambiguous_with: str | None = None
    raw_output: str = ""
    raw_output_p2: str = ""

    @property
    def correct(self) -> bool:
        return self.predicted == self.expected

    @property
    def partial_credit(self) -> float:
        if self.correct:
            return 1.0
        if self.ambiguous_with and self.predicted == self.ambiguous_with:
            return 0.5
        return 0.0

    @property
    def high_conf(self) -> bool:
        return self.confidence >= CONF_THRESHOLD

    @property
    def quadrant_label(self) -> str:
        hc = "hc" if self.high_conf else "lc"
        ok = "correct" if self.correct else "wrong"
        return f"{hc}_{ok}"


# ── Evaluation runners ─────────────────────────────────────────────────────────

def evaluate_calibration(clf: LoRAClassifier) -> list[FixtureResult]:
    results: list[FixtureResult] = []
    print(f"Evaluating {len(SKU_FIXTURES)} calibration fixtures...")
    for i, f in enumerate(SKU_FIXTURES):
        t0 = time.monotonic()
        d1, conf, quad, p1_raw, p2_raw = clf.classify(f.content)
        lat = time.monotonic() - t0
        r = FixtureResult(
            expected=f.expected_d1.name,
            predicted=d1,
            confidence=conf,
            quadrant=quad,
            latency_s=round(lat, 2),
            fixture_id=f.fixture_id,
            ambiguous_with=f.ambiguous_with.name if f.ambiguous_with else None,
            raw_output=p1_raw,
            raw_output_p2=p2_raw,
        )
        sym = "✓" if r.correct else ("~" if r.partial_credit == 0.5 else "✗")
        print(f"  [{i+1:2d}/30] {sym}  {r.expected:<13s}→ {d1 or 'FAIL':<13s}  "
              f"conf={conf:.2f}  q={quad or '?':<12s}  {lat:.1f}s")
        results.append(r)
    return results


def evaluate_test_set(clf: LoRAClassifier) -> list[FixtureResult] | None:
    """
    Load pass1_test.jsonl, extract chunk content from each prompt,
    run two-pass classification, compare against d1_name ground truth.
    Returns None if test set is not available.
    """
    test_path = CORPUS_DIR / "pass1_test.jsonl"
    if not test_path.exists():
        print(f"  Test set not found at {test_path} — skipping.")
        return None

    records = [json.loads(l) for l in test_path.read_text().splitlines() if l.strip()]
    # Deduplicate by content (pass1+pass2 produce two entries per chunk;
    # pass1_test.jsonl has one entry per chunk)
    print(f"\nEvaluating {len(records)} held-out test records...")

    results: list[FixtureResult] = []
    for i, rec in enumerate(records):
        # Extract chunk content from prompt (between <text> tags)
        m = re.search(r'<text>\n(.*?)\n</text>', rec["prompt"], re.DOTALL)
        if not m:
            print(f"  [{i+1:2d}/{len(records)}] ?  Could not extract content from prompt")
            continue
        content = m.group(1)
        expected = rec["d1_name"]

        t0 = time.monotonic()
        d1, conf, quad, p1_raw, p2_raw = clf.classify(content)
        lat = time.monotonic() - t0

        r = FixtureResult(
            expected=expected,
            predicted=d1,
            confidence=conf,
            quadrant=quad,
            latency_s=round(lat, 2),
            fixture_id=f"test_{i+1}",
            raw_output=p1_raw,
            raw_output_p2=p2_raw,
        )
        sym = "✓" if r.correct else "✗"
        print(f"  [{i+1:2d}/{len(records)}] {sym}  {expected:<13s}→ {d1 or 'FAIL':<13s}  "
              f"conf={conf:.2f}  {lat:.1f}s")
        results.append(r)
    return results


# ── Metrics ────────────────────────────────────────────────────────────────────

def compute_metrics(results: list[FixtureResult]) -> dict:
    total = len(results)
    if not total:
        return {}
    pc_sum = sum(r.partial_credit for r in results)
    strict = sum(1 for r in results if r.correct)
    failed = sum(1 for r in results if r.predicted is None)

    qgroups: dict[str, list[FixtureResult]] = defaultdict(list)
    for r in results:
        qgroups[r.quadrant_label].append(r)

    per_cat: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "partial": 0.0})
    for r in results:
        per_cat[r.expected]["total"] += 1
        if r.correct:
            per_cat[r.expected]["correct"] += 1
        per_cat[r.expected]["partial"] += r.partial_credit

    return {
        "total": total,
        "strict_correct": strict,
        "strict_accuracy": round(strict / total, 4),
        "partial_credit_sum": round(pc_sum, 1),
        "partial_credit_accuracy": round(pc_sum / total, 4),
        "parse_failures": failed,
        "quadrant_breakdown": {k: len(v) for k, v in qgroups.items()},
        "hc_wrong": [
            {"fixture_id": r.fixture_id, "expected": r.expected,
             "predicted": r.predicted, "confidence": round(r.confidence, 3)}
            for r in qgroups.get("hc_wrong", [])
        ],
        "per_category": {
            cat: {
                "total": d["total"],
                "correct": d["correct"],
                "accuracy": round(d["correct"] / d["total"], 3) if d["total"] else 0,
                "partial": round(d["partial"], 1),
            }
            for cat, d in sorted(per_cat.items())
        },
    }


def compute_clarity_metrics(results: list[FixtureResult]) -> dict:
    """Only meaningful for calibration fixtures which have clarity buckets."""
    fixture_map = {f.fixture_id: f for f in SKU_FIXTURES}
    clear_r = [r for r in results if fixture_map.get(r.fixture_id) in CLEAR_FIXTURES]
    hard_r = [r for r in results if fixture_map.get(r.fixture_id) in HARD_FIXTURES]
    amb_r = [r for r in results if fixture_map.get(r.fixture_id) in AMBIGUOUS_FIXTURES]

    def _acc(lst):
        if not lst:
            return None
        return round(sum(r.correct for r in lst) / len(lst), 3)

    def _pc(lst):
        if not lst:
            return None
        return round(sum(r.partial_credit for r in lst) / len(lst), 3)

    return {
        "clear":     {"n": len(clear_r), "accuracy": _acc(clear_r)},
        "hard":      {"n": len(hard_r),  "accuracy": _acc(hard_r)},
        "ambiguous": {"n": len(amb_r),   "partial_credit_accuracy": _pc(amb_r)},
    }


# ── Report printing ────────────────────────────────────────────────────────────

def print_report(metrics: dict, label: str,
                 clarity: dict | None = None,
                 v01_baseline: float | None = None) -> None:
    total = metrics["total"]
    pc_acc = metrics["partial_credit_accuracy"]
    strict_acc = metrics["strict_accuracy"]

    print(f"\n{'='*62}")
    print(f"  {label}  ({total} examples)")
    print(f"{'='*62}")
    print(f"  Strict accuracy:         {metrics['strict_correct']}/{total} = {strict_acc:.0%}")
    print(f"  Partial-credit accuracy: {metrics['partial_credit_sum']:.1f}/{total} = {pc_acc:.0%}")
    if v01_baseline is not None:
        delta = pc_acc - v01_baseline
        sign = "+" if delta >= 0 else ""
        print(f"  vs v0.1.0 baseline:      {v01_baseline:.0%}  (delta {sign}{delta:.0%})")
    if metrics["parse_failures"]:
        print(f"  Parse failures:          {metrics['parse_failures']}")

    qb = metrics["quadrant_breakdown"]
    print(f"\n  4-quadrant (conf ≥ {CONF_THRESHOLD}):")
    print(f"    High-conf correct:  {qb.get('hc_correct', 0):2d}  ← target")
    print(f"    High-conf WRONG:    {qb.get('hc_wrong',   0):2d}  ← investigate")
    print(f"    Low-conf correct:   {qb.get('lc_correct', 0):2d}  ← acceptable")
    print(f"    Low-conf wrong:     {qb.get('lc_wrong',   0):2d}")

    if clarity:
        print(f"\n  Clarity breakdown:")
        c, h, a = clarity["clear"], clarity["hard"], clarity["ambiguous"]
        if c["n"]:
            print(f"    Clear    ({c['n']:2d}):  {c['accuracy']:.0%} strict")
        if h["n"]:
            print(f"    Hard     ({h['n']:2d}):  {h['accuracy']:.0%} strict")
        if a["n"]:
            print(f"    Ambig    ({a['n']:2d}):  {a['partial_credit_accuracy']:.0%} partial-credit")

    if metrics["hc_wrong"]:
        print(f"\n  High-conf wrong (investigate):")
        for r in metrics["hc_wrong"]:
            print(f"    [{r['fixture_id']}]  expected={r['expected']:<13s}  "
                  f"got={r['predicted'] or 'FAIL':<13s}  conf={r['confidence']:.3f}")

    # Per-category table (only rows with data)
    pc_rows = [(cat, d) for cat, d in metrics["per_category"].items() if d["total"] > 0]
    if pc_rows:
        print(f"\n  Per-category accuracy:")
        for cat, d in sorted(pc_rows, key=lambda x: -x[1]["total"]):
            bar = "█" * d["correct"] + "░" * (d["total"] - d["correct"])
            print(f"    {cat:<13s} {d['correct']:2d}/{d['total']:2d}  {d['accuracy']:.0%}  {bar}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, required=True,
                        help="Path to LoRA adapter directory.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    prime_group = parser.add_mutually_exclusive_group()
    prime_group.add_argument("--prime", dest="prime", action="store_true", default=None,
                             help="Force-enable JSON prime.")
    prime_group.add_argument("--no-prime", dest="prime", action="store_false",
                             help="Force-disable JSON prime.")
    parser.add_argument("--calibration-only", action="store_true", default=False,
                        help="Skip held-out test set; only run calibration fixtures.")
    args = parser.parse_args()

    if not args.adapter.exists():
        print(f"ERROR: adapter not found: {args.adapter}")
        sys.exit(1)

    clf = LoRAClassifier(args.adapter, use_prime=args.prime)

    # ── Calibration ────────────────────────────────────────────────────────────
    cal_results = evaluate_calibration(clf)
    cal_metrics = compute_metrics(cal_results)
    cal_clarity = compute_clarity_metrics(cal_results)
    print_report(cal_metrics, "LoRA — Calibration fixtures (Tier 1)",
                 clarity=cal_clarity, v01_baseline=V01_PARTIAL_CREDIT)

    # ── Test set ───────────────────────────────────────────────────────────────
    test_results = None if args.calibration_only else evaluate_test_set(clf)
    test_metrics = compute_metrics(test_results) if test_results else {}
    if test_metrics:
        print_report(test_metrics, "LoRA — Held-out test set (Tier 2, 24 examples)")

    if cal_metrics and test_metrics:
        cal_pc = cal_metrics["partial_credit_accuracy"]
        test_pc = test_metrics["partial_credit_accuracy"]
        delta = test_pc - cal_pc
        sign = "+" if delta >= 0 else ""
        print(f"\n  Tier 2 vs Tier 1 delta: {sign}{delta:.0%}  "
              f"({'no significant gap' if abs(delta) < 0.10 else 'WARNING: >10% gap — check for overfit'})")

    # ── Save ───────────────────────────────────────────────────────────────────
    output = {
        "adapter_path": str(args.adapter),
        "use_prime": clf.use_prime,
        "v01_partial_credit_baseline": V01_PARTIAL_CREDIT,
        "calibration": {
            "metrics": cal_metrics,
            "clarity": cal_clarity,
            "results": [
                {
                    "fixture_id": r.fixture_id,
                    "expected": r.expected,
                    "predicted": r.predicted,
                    "confidence": r.confidence,
                    "quadrant": r.quadrant,
                    "partial_credit": r.partial_credit,
                    "latency_s": r.latency_s,
                    "raw_output": r.raw_output,
                    "raw_output_p2": r.raw_output_p2,
                }
                for r in cal_results
            ],
        },
        "test_set": {
            "metrics": test_metrics,
            "results": [
                {
                    "fixture_id": r.fixture_id,
                    "expected": r.expected,
                    "predicted": r.predicted,
                    "confidence": r.confidence,
                    "quadrant": r.quadrant,
                    "partial_credit": r.partial_credit,
                    "latency_s": r.latency_s,
                    "raw_output": r.raw_output,
                    "raw_output_p2": r.raw_output_p2,
                }
                for r in (test_results or [])
            ],
        } if test_results is not None else None,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to: {args.output}")
    print("\n── STOP GATE ─────────────────────────────────────────────────────")
    print("Read accuracy numbers above before deciding on GGUF conversion.")
    print("─────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
