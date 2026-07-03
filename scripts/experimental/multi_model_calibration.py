"""
Run v0.1.0 two-pass calibration against multiple Ollama model backends.
Produces comparison table to inform Phase 2 production model choice
and v0.2 LoRA training target.

NOT PRODUCTION CODE. Experimental harness.

Usage:
    cd <repo-root>
    python scripts/experimental/multi_model_calibration.py

Output:
    docs/agent/multi_model_comparison.md
    docs/agent/multi_model_comparison_raw.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from statistics import mean, stdev

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cerebra.cognition.llm_adapter import OllamaDirectAdapter, ClassificationError
from cerebra.cognition.sku_categories import D1Category
from cerebra.cognition.sku_classifier import (
    _build_pass1_prompt,
    _build_pass2_prompt,
    _build_classification_prompt,
)
from tests.fixtures.sku_fixtures import (
    SKU_FIXTURES,
    CLEAR_FIXTURES,
    AMBIGUOUS_FIXTURES,
    HARD_FIXTURES,
    SKUFixture,
)

# ── Models to test ─────────────────────────────────────────────────────────────

MODELS_TO_TEST = [
    # Tag in Ollama            | display name          | param size  | notes
    ("qwen3.5:latest",          "qwen3.5-9b",           "9.7B",      "baseline"),
    ("qwen3.5:4b",              "qwen3.5-4b",           "4B",        ""),
    ("qwen3.5:2b",              "qwen3.5-2b",           "2B",        "bonus"),
    ("qwen3.5:0.8b",            "qwen3.5-0.8b",         "0.8B",      "bonus"),
    ("llama3.1:8b",             "llama3.1-8b",          "8B",        ""),
    ("olmo-3:7b",               "olmo3-7b",             "7B",        "LoRA candidate"),
    ("ibm/granite4:tiny-h",     "granite4-tiny-h",      "~7B MoE",   ""),
    ("ibm/granite4:micro",      "granite4-micro",       "3B",        ""),
    ("hf.co/unsloth/SmolLM3-3B-GGUF:Q4_K_M", "smollm3-3b", "3B",   ""),
    ("hermes3:latest",          "hermes3",              "8B",        ""),
    ("mistral-nemo:latest",     "mistral-nemo",         "12B",       "bonus"),
]

NUM_RUNS_PER_MODEL = 3
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
TIMEOUT = 300  # seconds per call — cold-load can be slow

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class FixtureRunResult:
    fixture_id: str
    expected_d1: str
    predicted_d1: str
    pass1_quadrant: str
    pass1_confidence: float
    pass2_confidence: float
    partial_credit: float         # 1.0 / 0.5 / 0.0
    strict_correct: bool
    pass1_correct: bool           # was quadrant correct?
    pass2_correct_given_pass1: bool  # was D1 correct given correct quadrant?
    latency_ms: int
    pass1_latency_ms: int
    pass2_latency_ms: int
    parse_failed: bool
    ambiguous_with: str | None


@dataclass
class ModelRunSummary:
    model_tag: str
    model_name: str
    run_num: int
    fixture_results: list[FixtureRunResult] = field(default_factory=list)
    vram_mb: int | None = None
    run_elapsed_s: float = 0.0

    @property
    def total(self) -> int:
        return len(self.fixture_results)

    @property
    def strict_correct(self) -> int:
        return sum(1 for r in self.fixture_results if r.strict_correct)

    @property
    def partial_sum(self) -> float:
        return sum(r.partial_credit for r in self.fixture_results)

    @property
    def strict_acc(self) -> float:
        return self.strict_correct / self.total if self.total else 0.0

    @property
    def partial_acc(self) -> float:
        return self.partial_sum / self.total if self.total else 0.0

    @property
    def parse_failures(self) -> int:
        return sum(1 for r in self.fixture_results if r.parse_failed)

    @property
    def pass1_acc(self) -> float:
        return sum(1 for r in self.fixture_results if r.pass1_correct) / self.total if self.total else 0.0

    @property
    def pass2_acc_given_pass1(self) -> float:
        p1_correct = [r for r in self.fixture_results if r.pass1_correct]
        if not p1_correct:
            return 0.0
        return sum(1 for r in p1_correct if r.pass2_correct_given_pass1) / len(p1_correct)

    @property
    def mean_latency_ms(self) -> float:
        lats = [r.latency_ms for r in self.fixture_results if not r.parse_failed]
        return mean(lats) if lats else 0.0

    @property
    def min_latency_ms(self) -> float:
        lats = [r.latency_ms for r in self.fixture_results if not r.parse_failed]
        return min(lats) if lats else 0.0

    @property
    def max_latency_ms(self) -> float:
        lats = [r.latency_ms for r in self.fixture_results if not r.parse_failed]
        return max(lats) if lats else 0.0

    @property
    def p95_latency_ms(self) -> float:
        lats = sorted(r.latency_ms for r in self.fixture_results if not r.parse_failed)
        if not lats:
            return 0.0
        idx = int(len(lats) * 0.95)
        return lats[min(idx, len(lats) - 1)]

    def per_category_correct(self) -> dict[str, tuple[int, int]]:
        """Returns {category_name: (correct, total)} for each D1 category."""
        counts: dict[str, list[int]] = {}
        for r in self.fixture_results:
            if r.expected_d1 not in counts:
                counts[r.expected_d1] = [0, 0]
            counts[r.expected_d1][1] += 1
            if r.strict_correct:
                counts[r.expected_d1][0] += 1
        return {k: (v[0], v[1]) for k, v in counts.items()}

    def quadrant_table(self) -> dict[str, int]:
        """4-quadrant table: hc_correct, hc_wrong, lc_correct, lc_wrong."""
        HIGH_CONF = 0.5
        out = {"hc_correct": 0, "hc_wrong": 0, "lc_correct": 0, "lc_wrong": 0}
        for r in self.fixture_results:
            high = r.pass2_confidence >= HIGH_CONF
            key = ("hc" if high else "lc") + "_" + ("correct" if r.strict_correct else "wrong")
            out[key] += 1
        return out


# ── VRAM snapshot ──────────────────────────────────────────────────────────────

def sample_vram_mb() -> int | None:
    """Sample current GPU VRAM usage in MB via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5,
        )
        return int(out.decode().strip().split("\n")[0])
    except Exception:
        return None


# ── QUADRANT mapping ───────────────────────────────────────────────────────────

D1_TO_QUADRANT = {
    "OBSERVATION": "EMPIRICAL", "PATTERN": "EMPIRICAL",
    "MECHANISM": "EMPIRICAL", "PHENOMENON": "EMPIRICAL",
    "TECHNIQUE": "GENERATIVE", "DESIGN": "GENERATIVE",
    "CREATION": "GENERATIVE", "TOOL": "GENERATIVE",
    "PRINCIPLE": "NORMATIVE", "JUDGMENT": "NORMATIVE",
    "GOAL": "NORMATIVE", "CONSTRAINT": "NORMATIVE",
    "EVENT": "RELATIONAL", "AGENT": "RELATIONAL",
    "CONTEXT": "RELATIONAL", "RELATION": "RELATIONAL",
}


# ── Single fixture classification ──────────────────────────────────────────────

def classify_fixture(
    adapter: OllamaDirectAdapter,
    fixture: SKUFixture,
) -> FixtureRunResult:
    """Run two-pass classification on one fixture. Returns result even on failure."""
    t_start = time.monotonic()
    parse_failed = False
    predicted_d1 = "OBSERVATION"  # fallback
    pass1_quadrant = "EMPIRICAL"
    pass1_conf = 0.0
    pass2_conf = 0.0
    pass1_lat = 0
    pass2_lat = 0

    try:
        # Pass 1: quadrant
        p1 = adapter.classify_quadrant(fixture.content)
        pass1_quadrant = p1.primary
        pass1_conf = p1.confidence
        pass1_lat = p1.latency_ms or 0

        # Pass 2: within-quadrant
        p2 = adapter.classify_within_quadrant(fixture.content, pass1_quadrant)
        predicted_d1 = p2.primary
        pass2_conf = p2.confidence
        pass2_lat = p2.latency_ms or 0

    except (ClassificationError, ValueError, Exception) as e:
        parse_failed = True
        print(f"    FAILED [{fixture.fixture_id}]: {str(e)[:80]}")

    total_lat = int((time.monotonic() - t_start) * 1000)

    expected = fixture.expected_d1.name
    strict_correct = predicted_d1 == expected

    if strict_correct:
        partial_credit = 1.0
    elif fixture.ambiguous_with is not None and predicted_d1 == fixture.ambiguous_with.name:
        partial_credit = 0.5
    else:
        partial_credit = 0.0

    expected_quadrant = D1_TO_QUADRANT.get(expected, "EMPIRICAL")
    pass1_correct = pass1_quadrant == expected_quadrant
    pass2_correct_given_pass1 = strict_correct if pass1_correct else False

    return FixtureRunResult(
        fixture_id=fixture.fixture_id,
        expected_d1=expected,
        predicted_d1=predicted_d1,
        pass1_quadrant=pass1_quadrant,
        pass1_confidence=pass1_conf,
        pass2_confidence=pass2_conf,
        partial_credit=partial_credit,
        strict_correct=strict_correct,
        pass1_correct=pass1_correct,
        pass2_correct_given_pass1=pass2_correct_given_pass1,
        latency_ms=total_lat,
        pass1_latency_ms=pass1_lat,
        pass2_latency_ms=pass2_lat,
        parse_failed=parse_failed,
        ambiguous_with=fixture.ambiguous_with.name if fixture.ambiguous_with else None,
    )


# ── Single model run ───────────────────────────────────────────────────────────

def run_model(
    model_tag: str,
    model_name: str,
    run_num: int,
) -> ModelRunSummary:
    """Run full 30-fixture calibration for one model."""
    print(f"\n{'='*60}")
    print(f"  {model_name}  (run {run_num + 1}/{NUM_RUNS_PER_MODEL})")
    print(f"{'='*60}")

    adapter = OllamaDirectAdapter(
        base_url=OLLAMA_BASE_URL,
        model=model_tag,
        timeout=TIMEOUT,
        temperature=0.0,
    )

    # Health check / model warm-up
    print("  health check + warm-up...")
    try:
        ok = adapter.health_check()
        if not ok:
            print(f"  WARNING: health check failed for {model_tag}")
    except Exception as e:
        print(f"  WARNING: health check error: {e}")

    summary = ModelRunSummary(model_tag=model_tag, model_name=model_name, run_num=run_num)
    t_run_start = time.monotonic()

    vram_before = sample_vram_mb()

    for i, fixture in enumerate(SKU_FIXTURES):
        print(f"  [{i+1:2d}/30] {fixture.fixture_id}...", end=" ", flush=True)
        result = classify_fixture(adapter, fixture)
        summary.fixture_results.append(result)
        credit_str = f"✓ +1.0" if result.partial_credit == 1.0 else \
                     f"~ +0.5" if result.partial_credit == 0.5 else "✗ +0.0"
        print(f"{result.predicted_d1:<12} {credit_str}  {result.latency_ms}ms")

    vram_after = sample_vram_mb()
    summary.vram_mb = vram_after if vram_after is not None else vram_before
    summary.run_elapsed_s = time.monotonic() - t_run_start

    print(f"\n  → strict={summary.strict_acc:.0%}  partial={summary.partial_acc:.0%}  "
          f"pass1={summary.pass1_acc:.0%}  failures={summary.parse_failures}  "
          f"elapsed={summary.run_elapsed_s:.0f}s  vram={summary.vram_mb}MB")

    return summary


# ── Report generation ──────────────────────────────────────────────────────────

def build_report(
    all_runs: dict[str, list[ModelRunSummary]],
    model_meta: dict[str, tuple[str, str, str]],
) -> str:
    """Build the full markdown comparison report."""
    lines = []
    lines.append("# Multi-Model SKU Classifier Calibration — v0.1.0 Two-Pass")
    lines.append("")
    lines.append("Compares Cerebra's v0.1.0 two-pass classifier across available local models.")
    lines.append("Settings held constant: temperature 0.0, think: false, v0.1.0 prompts (PROMPT_VERSION 2.0.0),")
    lines.append("30 fixtures (13 clear / 2 ambiguous / 15 hard), 0.5-credit scoring on ambiguous_with matches.")
    lines.append(f"Runs per model: {NUM_RUNS_PER_MODEL}")
    lines.append("")

    # ── Summary table ──
    lines.append("## 1. Summary Table")
    lines.append("")
    lines.append("| Model | Size | Mean Partial | Std Dev | Mean Strict | Pass1 Acc | Mean Latency | VRAM |")
    lines.append("|-------|------|:------------:|:-------:|:-----------:|:---------:|:------------:|:----:|")

    rows = []
    for model_name, runs in all_runs.items():
        tag, size, notes = model_meta[model_name]
        partials = [r.partial_acc for r in runs]
        stricts = [r.strict_acc for r in runs]
        p1s = [r.pass1_acc for r in runs]
        lats = [r.mean_latency_ms for r in runs]
        vrams = [r.vram_mb for r in runs if r.vram_mb is not None]

        mean_partial = mean(partials) if partials else 0.0
        std_partial = stdev(partials) if len(partials) > 1 else 0.0
        mean_strict = mean(stricts) if stricts else 0.0
        mean_p1 = mean(p1s) if p1s else 0.0
        mean_lat = mean(lats) if lats else 0.0
        mean_vram = int(mean(vrams)) if vrams else 0
        note_str = f" _{notes}_" if notes else ""
        rows.append((mean_partial, model_name, size, mean_partial, std_partial, mean_strict, mean_p1, mean_lat, mean_vram, note_str))

    rows.sort(reverse=True)
    for _, model_name, size, mean_partial, std_partial, mean_strict, mean_p1, mean_lat, mean_vram, note_str in rows:
        vram_str = f"{mean_vram}MB" if mean_vram > 0 else "n/a"
        lines.append(
            f"| {model_name}{note_str} | {size} | **{mean_partial:.0%}** | ±{std_partial:.1%} "
            f"| {mean_strict:.0%} | {mean_p1:.0%} | {mean_lat/1000:.1f}s | {vram_str} |"
        )
    lines.append("")

    # ── Per-model detail ──
    lines.append("## 2. Per-Model Detail")
    lines.append("")

    for model_name, runs in all_runs.items():
        tag, size, notes = model_meta[model_name]
        lines.append(f"### {model_name} ({size}){' — ' + notes if notes else ''}")
        lines.append("")

        for run in runs:
            lines.append(f"**Run {run.run_num + 1}:** "
                         f"strict={run.strict_acc:.0%}  partial={run.partial_acc:.0%}  "
                         f"pass1={run.pass1_acc:.0%}  "
                         f"failures={run.parse_failures}  elapsed={run.run_elapsed_s:.0f}s")

        lines.append("")

        # Use run 1 for detailed breakdown (all runs at temp=0 should be near-identical)
        ref = runs[0]
        qt = ref.quadrant_table()
        lines.append("**4-Quadrant table (run 1):**")
        lines.append(f"- High-conf correct: {qt['hc_correct']}")
        lines.append(f"- High-conf WRONG:   {qt['hc_wrong']} ← investigate")
        lines.append(f"- Low-conf correct:  {qt['lc_correct']}")
        lines.append(f"- Low-conf wrong:    {qt['lc_wrong']}")
        lines.append("")

        lines.append(f"**Difficulty breakdown (run 1):**")
        clear_results = [r for r in ref.fixture_results if r.fixture_id in {f.fixture_id for f in CLEAR_FIXTURES}]
        ambig_results = [r for r in ref.fixture_results if r.fixture_id in {f.fixture_id for f in AMBIGUOUS_FIXTURES}]
        hard_results = [r for r in ref.fixture_results if r.fixture_id in {f.fixture_id for f in HARD_FIXTURES}]

        clear_partial = sum(r.partial_credit for r in clear_results)
        ambig_partial = sum(r.partial_credit for r in ambig_results)
        hard_partial = sum(r.partial_credit for r in hard_results)

        lines.append(f"- Clear ({len(CLEAR_FIXTURES)}):    {clear_partial:.1f}/{len(clear_results)} = {clear_partial/len(clear_results):.0%} partial")
        lines.append(f"- Ambiguous ({len(AMBIGUOUS_FIXTURES)}): {ambig_partial:.1f}/{len(ambig_results)} = {ambig_partial/max(len(ambig_results),1):.0%} partial")
        lines.append(f"- Hard ({len(HARD_FIXTURES)}):     {hard_partial:.1f}/{len(hard_results)} = {hard_partial/len(hard_results):.0%} partial")
        lines.append("")

        # Per-category accuracy
        cat_acc = ref.per_category_correct()
        lines.append("**Per-D1-category accuracy (run 1):**")
        for cat, (correct, total) in sorted(cat_acc.items()):
            bar = "█" * correct + "░" * (total - correct)
            lines.append(f"- {cat:<12} {correct}/{total}  {bar}")
        lines.append("")

        # Wrong fixtures
        wrong = [r for r in ref.fixture_results if not r.strict_correct]
        if wrong:
            lines.append(f"**Wrong predictions (run 1):** {len(wrong)} fixture(s)")
            for r in wrong:
                credit = " (0.5 credit)" if r.partial_credit == 0.5 else ""
                lines.append(f"- `{r.fixture_id}` expected={r.expected_d1} got={r.predicted_d1}{credit}")
        else:
            lines.append("**All fixtures correct (run 1)** ✓")
        lines.append("")

        # Latency
        lats_ms = [r.latency_ms for r in ref.fixture_results]
        lines.append(f"**Latency (run 1):** min={min(lats_ms)}ms  max={max(lats_ms)}ms  "
                     f"mean={int(mean(lats_ms))}ms  p95={int(sorted(lats_ms)[int(len(lats_ms)*0.95)])}")
        lines.append("")

        # Variance across runs
        if len(runs) > 1:
            partials = [r.partial_acc for r in runs]
            var_str = f"±{stdev(partials):.1%}" if len(partials) > 1 else "n/a"
            lines.append(f"**Run-to-run variance:** {' / '.join(f'{r.partial_acc:.0%}' for r in runs)} — std dev {var_str}")
            # Check if same predictions
            predictions_per_run = [tuple(r.predicted_d1 for r in run.fixture_results) for run in runs]
            all_same = len(set(predictions_per_run)) == 1
            lines.append(f"**Determinism:** {'✓ all 3 runs produced identical predictions' if all_same else '⚠ predictions differed between runs'}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── Strict vs partial gap ──
    lines.append("## 3. Strict vs Partial Accuracy Gap")
    lines.append("")
    lines.append("Gap = partial_acc − strict_acc. A larger gap means the model frequently predicts")
    lines.append("the defensible-alternative answer on ambiguous fixtures — it's directionally correct")
    lines.append("but picking the 'other' reasonable category.")
    lines.append("")
    lines.append("| Model | Strict | Partial | Gap |")
    lines.append("|-------|:------:|:-------:|:---:|")

    for _, model_name, _, mean_partial, _, mean_strict, _, _, _, _ in sorted(rows, reverse=True):
        gap = mean_partial - mean_strict
        lines.append(f"| {model_name} | {mean_strict:.0%} | {mean_partial:.0%} | +{gap:.1%} |")
    lines.append("")

    # ── Cross-model agreement ──
    lines.append("## 4. Cross-Model Agreement Analysis")
    lines.append("")
    lines.append("Per fixture: how many models got it correct (strict) across all runs?")
    lines.append("")

    # Aggregate per fixture across all model run-1s
    fixture_votes: dict[str, list[bool]] = {}
    fixture_credits: dict[str, list[float]] = {}
    for model_name, runs in all_runs.items():
        ref = runs[0]
        for r in ref.fixture_results:
            fixture_votes.setdefault(r.fixture_id, []).append(r.strict_correct)
            fixture_credits.setdefault(r.fixture_id, []).append(r.partial_credit)

    n_models = len(all_runs)
    consensus_correct = []
    consensus_wrong = []
    split = []

    for fid in sorted(fixture_votes.keys()):
        votes = fixture_votes[fid]
        n_correct = sum(votes)
        if n_correct == n_models:
            consensus_correct.append(fid)
        elif n_correct == 0:
            consensus_wrong.append(fid)
        else:
            split.append((fid, n_correct, n_models))

    lines.append(f"**Consensus correct** ({len(consensus_correct)} fixtures — all {n_models} models got these right):")
    lines.append(", ".join(f"`{f}`" for f in consensus_correct) if consensus_correct else "_none_")
    lines.append("")
    lines.append(f"**Consensus failure** ({len(consensus_wrong)} fixtures — no model got these right):")
    lines.append(", ".join(f"`{f}`" for f in consensus_wrong) if consensus_wrong else "_none_")
    lines.append("")
    lines.append(f"**Split** ({len(split)} fixtures):")
    for fid, n_correct, n_total in sorted(split, key=lambda x: x[1]):
        fixture = next(f for f in SKU_FIXTURES if f.fixture_id == fid)
        lines.append(f"- `{fid}` ({fixture.expected_d1.name}): {n_correct}/{n_total} models correct")
    lines.append("")

    # ── Recommendation ──
    lines.append("## 5. Recommendation")
    lines.append("")

    # Find winner for production
    best_partial = max(rows, key=lambda x: x[3])
    best_model_name = best_partial[1]
    best_acc = best_partial[3]

    lines.append(f"### Phase 2 Production Model")
    lines.append("")
    lines.append(f"**Winner: {best_model_name}** — {best_acc:.0%} mean partial-credit accuracy")
    lines.append("")

    # Find best LoRA candidate: high accuracy + smaller/fits VRAM + documented training
    lora_candidates = [(name, data) for name, data in all_runs.items()
                       if "olmo" in name.lower() or "smollm" in name.lower() or "granite" in name.lower()]
    lines.append("### v0.2 LoRA Training Target")
    lines.append("")
    lines.append("OLMo 3 7B is the recommended LoRA training target per the v0.1.0 consultation")
    lines.append("(documented training methodology, fits comfortably in 12GB VRAM for QLoRA).")
    lines.append("Calibration data for OLMo 3 and alternatives:")
    lines.append("")

    for model_name in ["olmo3-7b", "smollm3-3b", "granite4-micro", "granite4-tiny-h"]:
        if model_name in all_runs:
            runs = all_runs[model_name]
            mean_partial = mean(r.partial_acc for r in runs)
            lines.append(f"- **{model_name}**: {mean_partial:.0%} mean partial accuracy")

    lines.append("")
    lines.append("If OLMo 3 scored ≥60%, it remains the recommended LoRA target.")
    lines.append("If another model significantly outperformed OLMo 3, discuss before committing.")
    lines.append("")

    lines.append("## 6. Raw Data")
    lines.append("")
    lines.append("Full per-fixture predictions and metrics for all runs: `multi_model_comparison_raw.json`")
    lines.append("")

    return "\n".join(lines)


def build_raw_json(
    all_runs: dict[str, list[ModelRunSummary]],
    model_meta: dict[str, tuple[str, str, str]],
) -> dict:
    """Build raw JSON output for all runs."""
    out: dict = {"models": {}}
    for model_name, runs in all_runs.items():
        tag, size, notes = model_meta[model_name]
        out["models"][model_name] = {
            "tag": tag,
            "size": size,
            "notes": notes,
            "runs": [],
        }
        for run in runs:
            run_dict = {
                "run_num": run.run_num,
                "strict_acc": run.strict_acc,
                "partial_acc": run.partial_acc,
                "pass1_acc": run.pass1_acc,
                "parse_failures": run.parse_failures,
                "vram_mb": run.vram_mb,
                "elapsed_s": run.run_elapsed_s,
                "mean_latency_ms": run.mean_latency_ms,
                "fixtures": [asdict(r) for r in run.fixture_results],
            }
            out["models"][model_name]["runs"].append(run_dict)
    return out


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    out_dir = Path(__file__).parent.parent.parent / "docs" / "agent"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "multi_model_comparison.md"
    raw_path = out_dir / "multi_model_comparison_raw.json"

    print("Cerebra Multi-Model Calibration — v0.1.0 Two-Pass")
    print(f"Models: {len(MODELS_TO_TEST)}  |  Runs per model: {NUM_RUNS_PER_MODEL}  |  Fixtures: {len(SKU_FIXTURES)}")
    print(f"Output: {report_path}")
    print()

    all_runs: dict[str, list[ModelRunSummary]] = {}
    model_meta: dict[str, tuple[str, str, str]] = {}

    t_total = time.monotonic()

    for model_tag, model_name, size, notes in MODELS_TO_TEST:
        model_meta[model_name] = (model_tag, size, notes)
        all_runs[model_name] = []

        for run_num in range(NUM_RUNS_PER_MODEL):
            run_summary = run_model(model_tag, model_name, run_num)
            all_runs[model_name].append(run_summary)
            # Brief pause between runs to let VRAM settle
            if run_num < NUM_RUNS_PER_MODEL - 1:
                time.sleep(3)

        # Pause between models to let Ollama unload the current model
        print(f"\n  Pausing 10s between models to let Ollama settle...\n")
        time.sleep(10)

    total_elapsed = time.monotonic() - t_total
    print(f"\nAll runs complete in {total_elapsed/60:.1f} minutes")
    print(f"Writing report to {report_path}")

    report_md = build_report(all_runs, model_meta)
    report_path.write_text(report_md, encoding="utf-8")

    raw_json = build_raw_json(all_runs, model_meta)
    raw_path.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")

    print(f"Written: {report_path}")
    print(f"Written: {raw_path}")

    # Print quick summary
    print("\n── QUICK SUMMARY ──────────────────────────────────")
    results_by_acc = sorted(
        [(name, [r.partial_acc for r in runs]) for name, runs in all_runs.items()],
        key=lambda x: mean(x[1]),
        reverse=True,
    )
    for name, accs in results_by_acc:
        mean_acc = mean(accs)
        print(f"  {name:<25} {mean_acc:.0%}  ({' / '.join(f'{a:.0%}' for a in accs)})")


if __name__ == "__main__":
    main()
