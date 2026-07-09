# SPDX-License-Identifier: Apache-2.0
"""
Granite 4.1 3B — base vs instruct comparison on 30 calibration fixtures.

Establishes the base model's pre-LoRA classification accuracy so post-training
improvements can be attributed honestly.

Run with the training venv (not the main cerebra venv):
    <lora-venv>/bin/python \\
        scripts/v02_training/base_vs_instruct.py [--skip-ollama]

Flags:
    --skip-ollama   Skip instruct (Ollama) comparison; base model only.
    --output PATH   Save results JSON to this path (default: print only).

Requirements in training venv:
    unsloth, transformers, torch

The cerebra repo (llm_adapter, sku_classifier prompts, fixtures) is loaded via
sys.path — no install required.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ── Cerebra imports (stdlib-only modules, safe to import from any venv) ───────
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from tests.fixtures.sku_fixtures import (
    SKU_FIXTURES,
    CLEAR_FIXTURES,
    HARD_FIXTURES,
    AMBIGUOUS_FIXTURES,
    SKUFixture,
)
from cerebra.cognition.sku_classifier import (
    _build_pass1_prompt,
    _build_pass2_prompt,
    PASS2_PROMPTS,
)

HF_BASE_MODEL = "ibm-granite/granite-4.1-3b-base"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M"

QUADRANT_NAMES = {"EMPIRICAL", "GENERATIVE", "NORMATIVE", "RELATIONAL"}
D1_NAMES = {
    "OBSERVATION", "PATTERN", "MECHANISM", "PHENOMENON",
    "TECHNIQUE", "DESIGN", "CREATION", "TOOL",
    "PRINCIPLE", "JUDGMENT", "GOAL", "CONSTRAINT",
    "EVENT", "AGENT", "CONTEXT", "RELATION",
}


# ── JSON extraction ────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    """Extract the first parseable JSON object from generated text."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}', text, re.DOTALL):
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            continue
    # Broader search: find { and match to closing }
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


# ── Base model (HF) inference ─────────────────────────────────────────────────

class BaseModelClassifier:
    def __init__(self) -> None:
        print(f"\nLoading {HF_BASE_MODEL} (4-bit QLoRA config)...")
        from unsloth import FastLanguageModel
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=HF_BASE_MODEL,
            max_seq_length=2048,
            load_in_4bit=True,
            dtype=None,  # auto-detect
        )
        FastLanguageModel.for_inference(self.model)
        print("  Base model loaded.\n")

    # Base model emits EOS immediately when the prompt ends with </text> because
    # it treats the XML tag as end-of-document. Priming with the JSON opening
    # bypasses this: the model continues the in-progress JSON instead of halting.
    JSON_PRIME = '\n{"scores":'

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """Tokenize prompt + JSON_PRIME, generate, return prime + new tokens."""
        full_prompt = prompt + self.JSON_PRIME
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to("cuda")
        input_len = inputs["input_ids"].shape[1]
        with __import__("torch").no_grad():
            outputs = self.model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = outputs[0][input_len:]
        return self.JSON_PRIME + self.tokenizer.decode(new_tokens, skip_special_tokens=True)

    def classify_raw(self, content: str) -> tuple[str, str | None]:
        """Return (pass1_raw, pass2_raw_or_None) without parsing. For diagnostics."""
        pass1_raw = self.generate(_build_pass1_prompt(content), max_new_tokens=200)
        # Determine quadrant so pass2 uses the right prompt
        pass1_data = _extract_json(pass1_raw)
        quadrant = None
        if pass1_data:
            raw_q = pass1_data.get("primary") or pass1_data.get("primary_quadrant")
            if raw_q and raw_q.upper() in QUADRANT_NAMES:
                quadrant = raw_q.upper()
            elif isinstance(pass1_data.get("scores"), dict):
                valid = {k: v for k, v in pass1_data["scores"].items() if k in QUADRANT_NAMES}
                if valid:
                    quadrant = max(valid, key=valid.get)
        if quadrant is None:
            return pass1_raw, None
        pass2_raw = self.generate(_build_pass2_prompt(content, quadrant), max_new_tokens=200)
        return pass1_raw, pass2_raw

    def classify(self, content: str) -> tuple[str | None, float, str | None]:
        """
        Run two-pass classification. Returns (d1_name, confidence, quadrant).
        Returns (None, 0.0, None) on failure.
        """
        # Pass 1 — quadrant
        pass1_prompt = _build_pass1_prompt(content)
        pass1_raw = self.generate(pass1_prompt, max_new_tokens=200)
        pass1_data = _extract_json(pass1_raw)

        quadrant = None
        if pass1_data:
            raw_q = pass1_data.get("primary") or pass1_data.get("primary_quadrant")
            if raw_q and raw_q.upper() in QUADRANT_NAMES:
                quadrant = raw_q.upper()

        if quadrant is None:
            # Fall back to highest score if available
            if pass1_data and isinstance(pass1_data.get("scores"), dict):
                scores = pass1_data["scores"]
                valid = {k: v for k, v in scores.items() if k in QUADRANT_NAMES}
                if valid:
                    quadrant = max(valid, key=valid.get)
            if quadrant is None:
                return None, 0.0, None

        # Pass 2 — within-quadrant D1
        pass2_prompt = _build_pass2_prompt(content, quadrant)
        pass2_raw = self.generate(pass2_prompt, max_new_tokens=200)
        pass2_data = _extract_json(pass2_raw)

        if not pass2_data:
            return None, 0.0, quadrant

        d1 = pass2_data.get("primary")
        if d1:
            d1 = d1.upper()
        confidence = float(pass2_data.get("confidence", 0.0))

        if d1 not in D1_NAMES:
            # Try highest score
            if isinstance(pass2_data.get("scores"), dict):
                scores = pass2_data["scores"]
                valid = {k: v for k, v in scores.items() if k in D1_NAMES}
                if valid:
                    d1 = max(valid, key=valid.get)
                    confidence = valid[d1]

        if d1 not in D1_NAMES:
            return None, 0.0, quadrant

        return d1, confidence, quadrant


# ── Instruct (Ollama) inference ────────────────────────────────────────────────

def _check_ollama() -> bool:
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=5):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _run_ollama_classify(content: str) -> tuple[str | None, float, str | None]:
    """Use OllamaDirectAdapter (stdlib only) for two-pass classification."""
    from cerebra.cognition.llm_adapter import OllamaDirectAdapter, ClassificationError
    adapter = OllamaDirectAdapter(model=OLLAMA_MODEL, temperature=0.0)
    try:
        pass1 = adapter.classify_quadrant(content)
        quadrant = pass1.primary
        pass2 = adapter.classify_within_quadrant(content, quadrant)
        return pass2.primary, pass2.confidence, quadrant
    except ClassificationError:
        return None, 0.0, None


# ── Scoring ────────────────────────────────────────────────────────────────────

@dataclass
class Result:
    fixture: SKUFixture
    model: str
    predicted_d1: str | None
    confidence: float
    quadrant: str | None
    latency_s: float

    @property
    def correct(self) -> bool:
        return self.predicted_d1 == self.fixture.expected_d1.name

    @property
    def partial_credit(self) -> float:
        if self.correct:
            return 1.0
        if (self.fixture.ambiguous_with is not None
                and self.predicted_d1 == self.fixture.ambiguous_with.name):
            return 0.5
        return 0.0


def _print_report(results: list[Result], model_label: str) -> None:
    total = len(results)
    pc_sum = sum(r.partial_credit for r in results)
    strict = sum(1 for r in results if r.correct)
    failed = sum(1 for r in results if r.predicted_d1 is None)

    print(f"\n{'='*60}")
    print(f"  {model_label}  ({total} fixtures)")
    print(f"{'='*60}")
    print(f"  Strict accuracy:         {strict}/{total} = {strict/total:.0%}")
    print(f"  Partial-credit accuracy: {pc_sum:.1f}/{total} = {pc_sum/total:.0%}")
    if failed:
        print(f"  Parse failures:          {failed}")

    # Quadrant breakdown
    threshold = 0.5
    qgroups = {"hc_correct": [], "hc_wrong": [], "lc_correct": [], "lc_wrong": []}
    for r in results:
        hc = r.confidence >= threshold
        if hc and r.correct:
            qgroups["hc_correct"].append(r)
        elif hc and not r.correct:
            qgroups["hc_wrong"].append(r)
        elif not hc and r.correct:
            qgroups["lc_correct"].append(r)
        else:
            qgroups["lc_wrong"].append(r)

    print(f"\n  4-quadrant (conf threshold {threshold}):")
    print(f"    High-conf correct:  {len(qgroups['hc_correct']):2d}  ← target")
    print(f"    High-conf WRONG:    {len(qgroups['hc_wrong']):2d}  ← investigate")
    print(f"    Low-conf correct:   {len(qgroups['lc_correct']):2d}  ← acceptable")
    print(f"    Low-conf wrong:     {len(qgroups['lc_wrong']):2d}")

    # Clear / hard / ambiguous
    clear_r = [r for r in results if r.fixture in CLEAR_FIXTURES]
    hard_r = [r for r in results if r.fixture in HARD_FIXTURES]
    amb_r = [r for r in results if r.fixture in AMBIGUOUS_FIXTURES]
    if clear_r:
        print(f"\n  Clear ({len(clear_r)}):   {sum(r.correct for r in clear_r)}/{len(clear_r)} correct")
    if hard_r:
        print(f"  Hard  ({len(hard_r)}):   {sum(r.correct for r in hard_r)}/{len(hard_r)} correct")
    if amb_r:
        print(f"  Ambig ({len(amb_r)}):   {sum(r.partial_credit for r in amb_r):.1f}/{len(amb_r)} partial-credit")

    # Per-fixture table for hc_wrong (most important to investigate)
    if qgroups["hc_wrong"]:
        print(f"\n  High-conf wrong (investigate):")
        for r in qgroups["hc_wrong"]:
            print(f"    [{r.fixture.fixture_id}]  expected={r.fixture.expected_d1.name}  "
                  f"got={r.predicted_d1}  conf={r.confidence:.2f}")


RAW_DUMP_PATH = Path(__file__).parent / "output/base_raw_dump.txt"
RAW_DUMP_N = 5


def _run_raw_dump(base_clf: "BaseModelClassifier") -> None:
    lines: list[str] = []

    def emit(s: str) -> None:
        print(s)
        lines.append(s)

    emit(f"Base model raw output dump — first {RAW_DUMP_N} calibration fixtures")
    emit("=" * 70)

    for i, fixture in enumerate(SKU_FIXTURES[:RAW_DUMP_N]):
        emit(f"\n=== FIXTURE {i + 1} (expected: {fixture.expected_d1.name}) ===")
        emit(f"CHUNK CONTENT (first 200 chars):")
        emit(fixture.content[:200])
        emit("")

        pass1_raw, pass2_raw = base_clf.classify_raw(fixture.content)

        emit("PASS 1 RAW OUTPUT:")
        emit(pass1_raw if pass1_raw.strip() else "(empty)")
        emit("")

        emit("PASS 2 RAW OUTPUT:")
        if pass2_raw is None:
            emit("(not attempted — pass 1 returned no parseable quadrant)")
        else:
            emit(pass2_raw if pass2_raw.strip() else "(empty)")
        emit("")
        emit("=" * 70)

    RAW_DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_DUMP_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nRaw dump saved to: {RAW_DUMP_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ollama", action="store_true",
                        help="Skip instruct (Ollama) run; base model only.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Save full results to this JSON file.")
    parser.add_argument("--raw-dump", action="store_true",
                        help=f"Capture raw base model output for first {RAW_DUMP_N} fixtures "
                             f"and save to {RAW_DUMP_PATH}. Exits after dump.")
    args = parser.parse_args()

    if args.raw_dump:
        base_clf = BaseModelClassifier()
        _run_raw_dump(base_clf)
        return

    print(f"Calibration fixtures: {len(SKU_FIXTURES)}")

    all_results: dict[str, list[Result]] = {}

    # ── Base model ─────────────────────────────────────────────────────────────
    base_clf = BaseModelClassifier()
    base_results: list[Result] = []
    print("Running base model on calibration fixtures...")
    for i, fixture in enumerate(SKU_FIXTURES):
        t0 = time.monotonic()
        d1, conf, quad = base_clf.classify(fixture.content)
        lat = time.monotonic() - t0
        r = Result(fixture=fixture, model="base", predicted_d1=d1, confidence=conf,
                   quadrant=quad, latency_s=round(lat, 2))
        base_results.append(r)
        sym = "✓" if r.correct else "✗"
        print(f"  [{i+1:2d}/{len(SKU_FIXTURES)}] {sym}  {fixture.expected_d1.name:<12s} → "
              f"{d1 or 'FAIL':<12s}  conf={conf:.2f}  {lat:.1f}s")

    _print_report(base_results, "Granite 4.1 3B BASE (HF, 4-bit)")
    all_results["base"] = base_results

    # ── Instruct model (Ollama) ────────────────────────────────────────────────
    if not args.skip_ollama:
        if not _check_ollama():
            print("\nOllama not reachable — skipping instruct comparison.")
            print("Run: cd ~/Projects/ai-stack && docker compose up -d")
        else:
            print("\nRunning instruct model (Ollama) on calibration fixtures...")
            instruct_results: list[Result] = []
            for i, fixture in enumerate(SKU_FIXTURES):
                t0 = time.monotonic()
                d1, conf, quad = _run_ollama_classify(fixture.content)
                lat = time.monotonic() - t0
                r = Result(fixture=fixture, model="instruct", predicted_d1=d1,
                           confidence=conf, quadrant=quad, latency_s=round(lat, 2))
                instruct_results.append(r)
                sym = "✓" if r.correct else "✗"
                print(f"  [{i+1:2d}/{len(SKU_FIXTURES)}] {sym}  "
                      f"{fixture.expected_d1.name:<12s} → {d1 or 'FAIL':<12s}  "
                      f"conf={conf:.2f}  {lat:.1f}s")

            _print_report(instruct_results, "Granite 4.1 3B INSTRUCT (Ollama GGUF Q4_K_M)")
            all_results["instruct"] = instruct_results

            # ── Side-by-side delta ─────────────────────────────────────────────
            print(f"\n{'='*60}")
            print("  Delta: instruct vs base (same fixture ordering)")
            print(f"{'='*60}")
            base_pc = sum(r.partial_credit for r in base_results) / len(base_results)
            inst_pc = sum(r.partial_credit for r in instruct_results) / len(instruct_results)
            print(f"  Base partial-credit:     {base_pc:.0%}")
            print(f"  Instruct partial-credit: {inst_pc:.0%}")
            delta = inst_pc - base_pc
            sign = "+" if delta >= 0 else ""
            print(f"  Delta (instruct - base): {sign}{delta:.0%}")

    if args.output:
        serialized = {
            model_key: [
                {
                    "fixture_id": r.fixture.fixture_id,
                    "expected": r.fixture.expected_d1.name,
                    "predicted": r.predicted_d1,
                    "confidence": r.confidence,
                    "quadrant": r.quadrant,
                    "correct": r.correct,
                    "partial_credit": r.partial_credit,
                    "latency_s": r.latency_s,
                }
                for r in rlist
            ]
            for model_key, rlist in all_results.items()
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(serialized, indent=2))
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
