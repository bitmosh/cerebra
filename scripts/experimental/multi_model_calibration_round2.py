"""
Round 2 calibration — Granite 4.1 base models only.
Compares against Round 1 baselines (Qwen 3.5 9B, Granite 4.0 Micro).

NOT PRODUCTION CODE. Experimental harness.

Usage:
    cd <repo-root>
    python scripts/experimental/multi_model_calibration_round2.py

Output:
    docs/agent/multi_model_comparison_round2.md
    docs/agent/multi_model_comparison_raw_round2.json
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cerebra.cognition.llm_adapter import OllamaDirectAdapter, ClassificationError
from tests.fixtures.sku_fixtures import (
    SKU_FIXTURES,
    CLEAR_FIXTURES,
    AMBIGUOUS_FIXTURES,
    HARD_FIXTURES,
    SKUFixture,
)

# ── Models to test (Round 2 only) ─────────────────────────────────────────────

MODELS_TO_TEST = [
    # Tag in Ollama                                           | display name       | size | notes
    ("huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M",  "granite41-3b",      "3B",  "base model"),
    ("huggingface.co/unsloth/granite-4.1-8b-GGUF:Q4_K_M",  "granite41-8b",      "8B",  "base model"),
]

NUM_RUNS_PER_MODEL = 3
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
TIMEOUT = 300

# ── Round 1 baseline data (pre-computed from multi_model_comparison.md) ────────

ROUND1_BASELINES = {
    "qwen3.5-9b": {
        "size": "9.7B", "notes": "baseline",
        "mean_partial": 0.5833, "mean_strict": 0.5333, "mean_pass1": 0.6667,
        "mean_latency_s": 3.3, "vram_mb": 8932,
        "diff_clear": 0.69, "diff_ambig": 0.75, "diff_hard": 0.47,
        "strict_partial_gap": 0.05,
        "per_category": {
            "AGENT": (1,1), "CONSTRAINT": (2,3), "CONTEXT": (0,1), "CREATION": (0,1),
            "DESIGN": (1,5), "EVENT": (0,1), "GOAL": (1,1), "MECHANISM": (3,6),
            "OBSERVATION": (2,3), "PHENOMENON": (1,1), "PRINCIPLE": (3,4),
            "RELATION": (1,1), "TECHNIQUE": (1,1), "TOOL": (0,1),
        },
        "consensus_failures_correct": [],  # which of the 5 consensus failures it got right
    },
    "granite4-micro": {
        "size": "3B", "notes": "Round 1",
        "mean_partial": 0.5333, "mean_strict": 0.4667, "mean_pass1": 0.7000,
        "mean_latency_s": 2.5, "vram_mb": 8348,
        "diff_clear": 0.46, "diff_ambig": 1.00, "diff_hard": 0.53,
        "strict_partial_gap": 0.0667,
        "per_category": {
            "AGENT": (0,1), "CONSTRAINT": (1,3), "CONTEXT": (0,1), "CREATION": (1,1),
            "DESIGN": (2,5), "EVENT": (0,1), "GOAL": (1,1), "MECHANISM": (2,6),
            "OBSERVATION": (2,3), "PHENOMENON": (0,1), "PRINCIPLE": (3,4),
            "RELATION": (0,1), "TECHNIQUE": (1,1), "TOOL": (1,1),
        },
        "consensus_failures_correct": [],
    },
}

CONSENSUS_FAILURES = ["clear_07", "clear_11", "hard_02", "hard_07", "hard_11"]

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class FixtureRunResult:
    fixture_id: str
    expected_d1: str
    predicted_d1: str
    pass1_quadrant: str
    pass1_confidence: float
    pass2_confidence: float
    partial_credit: float
    strict_correct: bool
    pass1_correct: bool
    pass2_correct_given_pass1: bool
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
        counts: dict[str, list[int]] = {}
        for r in self.fixture_results:
            if r.expected_d1 not in counts:
                counts[r.expected_d1] = [0, 0]
            counts[r.expected_d1][1] += 1
            if r.strict_correct:
                counts[r.expected_d1][0] += 1
        return {k: (v[0], v[1]) for k, v in counts.items()}

    def quadrant_table(self) -> dict[str, int]:
        HIGH_CONF = 0.5
        out = {"hc_correct": 0, "hc_wrong": 0, "lc_correct": 0, "lc_wrong": 0}
        for r in self.fixture_results:
            high = r.pass2_confidence >= HIGH_CONF
            key = ("hc" if high else "lc") + "_" + ("correct" if r.strict_correct else "wrong")
            out[key] += 1
        return out


# ── VRAM snapshot ──────────────────────────────────────────────────────────────

def sample_vram_mb() -> int | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5,
        )
        return int(out.decode().strip().split("\n")[0])
    except Exception:
        return None


# ── Quadrant mapping ───────────────────────────────────────────────────────────

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


# ── Fixture classification ─────────────────────────────────────────────────────

def classify_fixture(adapter: OllamaDirectAdapter, fixture: SKUFixture) -> FixtureRunResult:
    t_start = time.monotonic()
    parse_failed = False
    predicted_d1 = "OBSERVATION"
    pass1_quadrant = "EMPIRICAL"
    pass1_conf = 0.0
    pass2_conf = 0.0
    pass1_lat = 0
    pass2_lat = 0

    try:
        p1 = adapter.classify_quadrant(fixture.content)
        pass1_quadrant = p1.primary
        pass1_conf = p1.confidence
        pass1_lat = p1.latency_ms or 0

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


# ── Model run ──────────────────────────────────────────────────────────────────

def run_model(model_tag: str, model_name: str, run_num: int) -> ModelRunSummary:
    print(f"\n{'='*60}")
    print(f"  {model_name}  (run {run_num + 1}/{NUM_RUNS_PER_MODEL})")
    print(f"{'='*60}")

    adapter = OllamaDirectAdapter(
        base_url=OLLAMA_BASE_URL,
        model=model_tag,
        timeout=TIMEOUT,
        temperature=0.0,
    )

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
        credit_str = "✓ +1.0" if result.partial_credit == 1.0 else \
                     "~ +0.5" if result.partial_credit == 0.5 else "✗ +0.0"
        print(f"{result.predicted_d1:<12} {credit_str}  {result.latency_ms}ms")

    vram_after = sample_vram_mb()
    summary.vram_mb = vram_after if vram_after is not None else vram_before
    summary.run_elapsed_s = time.monotonic() - t_run_start

    print(f"\n  → strict={summary.strict_acc:.0%}  partial={summary.partial_acc:.0%}  "
          f"pass1={summary.pass1_acc:.0%}  failures={summary.parse_failures}  "
          f"elapsed={summary.run_elapsed_s:.0f}s  vram={summary.vram_mb}MB")

    return summary


# ── Report generation ──────────────────────────────────────────────────────────

def build_round2_report(
    all_runs: dict[str, list[ModelRunSummary]],
    model_meta: dict[str, tuple[str, str, str]],
) -> str:
    lines = []
    lines.append("# Multi-Model SKU Classifier Calibration — Round 2 (Granite 4.1)")
    lines.append("")
    lines.append("Round 2 follow-up: tests two newly-pulled Granite 4.1 base models against")
    lines.append("Round 1 results. Settings held constant with Round 1: temperature 0.0,")
    lines.append("think: false, v0.1.0 two-pass prompts (PROMPT_VERSION 2.0.0),")
    lines.append("30 fixtures (13 clear / 2 ambiguous / 15 hard), 0.5-credit scoring.")
    lines.append(f"Runs per model: {NUM_RUNS_PER_MODEL}")
    lines.append("")
    lines.append("Note: Granite 4.1 models are **base** (non-instruct) — instruct pull failed")
    lines.append("with HuggingFace 500. Base models are preferred for v0.2 LoRA training.")
    lines.append("")

    # ── Section 1: Summary table ──────────────────────────────────────────────
    lines.append("## 1. Results Table")
    lines.append("")
    lines.append("Round 1 baselines shown at top for direct comparison.")
    lines.append("")
    lines.append("| Model | Size | Mean Partial | Std Dev | Mean Strict | Pass1 Acc | Mean Latency | VRAM |")
    lines.append("|-------|------|:------------:|:-------:|:-----------:|:---------:|:------------:|:----:|")

    # Round 1 baselines first
    for bname, bdata in ROUND1_BASELINES.items():
        note_str = f" _{bdata['notes']}_" if bdata.get("notes") else ""
        lines.append(
            f"| {bname}{note_str} | {bdata['size']} | {bdata['mean_partial']:.0%} | ±0.0% "
            f"| {bdata['mean_strict']:.0%} | {bdata['mean_pass1']:.0%} "
            f"| {bdata['mean_latency_s']:.1f}s | {bdata['vram_mb']}MB |"
        )

    # Round 2 models
    r2_rows = []
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
        vram_str = f"{mean_vram}MB" if mean_vram > 0 else "n/a"
        r2_rows.append((mean_partial, model_name, size, mean_partial, std_partial,
                        mean_strict, mean_p1, mean_lat, mean_vram, note_str, vram_str))

    r2_rows.sort(reverse=True)
    for _, model_name, size, mean_partial, std_partial, mean_strict, mean_p1, mean_lat, _, note_str, vram_str in r2_rows:
        lines.append(
            f"| {model_name}{note_str} | {size} | **{mean_partial:.0%}** | ±{std_partial:.1%} "
            f"| {mean_strict:.0%} | {mean_p1:.0%} | {mean_lat/1000:.1f}s | {vram_str} |"
        )
    lines.append("")

    # ── Section 2: Per-model detail ───────────────────────────────────────────
    lines.append("## 2. Per-Model Detail")
    lines.append("")

    for model_name, runs in all_runs.items():
        tag, size, notes = model_meta[model_name]
        lines.append(f"### {model_name} ({size}){' — ' + notes if notes else ''}")
        lines.append("")

        for run in runs:
            lines.append(
                f"**Run {run.run_num + 1}:** "
                f"strict={run.strict_acc:.0%}  partial={run.partial_acc:.0%}  "
                f"pass1={run.pass1_acc:.0%}  "
                f"failures={run.parse_failures}  elapsed={run.run_elapsed_s:.0f}s"
            )

        lines.append("")

        ref = runs[0]
        qt = ref.quadrant_table()
        lines.append("**4-Quadrant table (run 1):**")
        lines.append(f"- High-conf correct: {qt['hc_correct']}")
        lines.append(f"- High-conf WRONG:   {qt['hc_wrong']} ← investigate")
        lines.append(f"- Low-conf correct:  {qt['lc_correct']}")
        lines.append(f"- Low-conf wrong:    {qt['lc_wrong']}")
        lines.append("")

        lines.append("**Difficulty breakdown (run 1):**")
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

        cat_acc = ref.per_category_correct()
        lines.append("**Per-D1-category accuracy (run 1):**")
        for cat, (correct, total) in sorted(cat_acc.items()):
            bar = "█" * correct + "░" * (total - correct)
            lines.append(f"- {cat:<12} {correct}/{total}  {bar}")
        lines.append("")

        wrong = [r for r in ref.fixture_results if not r.strict_correct]
        if wrong:
            lines.append(f"**Wrong predictions (run 1):** {len(wrong)} fixture(s)")
            for r in wrong:
                credit = " (0.5 credit)" if r.partial_credit == 0.5 else ""
                lines.append(f"- `{r.fixture_id}` expected={r.expected_d1} got={r.predicted_d1}{credit}")
        else:
            lines.append("**All fixtures correct (run 1)** ✓")
        lines.append("")

        lats_ms = [r.latency_ms for r in ref.fixture_results]
        lines.append(
            f"**Latency (run 1):** min={min(lats_ms)}ms  max={max(lats_ms)}ms  "
            f"mean={int(mean(lats_ms))}ms  p95={int(sorted(lats_ms)[int(len(lats_ms)*0.95)])}"
        )
        lines.append("")

        if len(runs) > 1:
            partials = [r.partial_acc for r in runs]
            var_str = f"±{stdev(partials):.1%}" if len(partials) > 1 else "n/a"
            lines.append(f"**Run-to-run variance:** {' / '.join(f'{r.partial_acc:.0%}' for r in runs)} — std dev {var_str}")
            predictions_per_run = [tuple(r.predicted_d1 for r in run.fixture_results) for run in runs]
            all_same = len(set(predictions_per_run)) == 1
            lines.append(f"**Determinism:** {'✓ all 3 runs produced identical predictions' if all_same else '⚠ predictions differed between runs'}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── Section 3: Head-to-head comparisons ──────────────────────────────────
    lines.append("## 3. Head-to-Head Comparisons")
    lines.append("")

    # 3a: Granite 4.1 3B vs Granite 4.0 Micro
    lines.append("### Granite 4.1 3B (base) vs Granite 4.0 Micro (instruct)")
    lines.append("")
    lines.append("Tests IBM's '4.1 beats 4.0 at same size' claim on Cerebra's task.")
    lines.append("")
    if "granite41-3b" in all_runs:
        runs_41_3b = all_runs["granite41-3b"]
        p41_3b = mean(r.partial_acc for r in runs_41_3b)
        s41_3b = mean(r.strict_acc for r in runs_41_3b)
        p1_41_3b = mean(r.pass1_acc for r in runs_41_3b)
        lat_41_3b = mean(r.mean_latency_ms for r in runs_41_3b) / 1000

        p40_micro = ROUND1_BASELINES["granite4-micro"]

        lines.append(f"| Metric | Granite 4.1 3B (base) | Granite 4.0 Micro (instruct) | Delta |")
        lines.append(f"|--------|:---------------------:|:----------------------------:|:-----:|")
        lines.append(f"| Partial acc | {p41_3b:.0%} | {p40_micro['mean_partial']:.0%} | {p41_3b - p40_micro['mean_partial']:+.0%} |")
        lines.append(f"| Strict acc | {s41_3b:.0%} | {p40_micro['mean_strict']:.0%} | {s41_3b - p40_micro['mean_strict']:+.0%} |")
        lines.append(f"| Pass 1 quadrant acc | {p1_41_3b:.0%} | {p40_micro['mean_pass1']:.0%} | {p1_41_3b - p40_micro['mean_pass1']:+.0%} |")
        lines.append(f"| Mean latency | {lat_41_3b:.1f}s | {p40_micro['mean_latency_s']:.1f}s | {lat_41_3b - p40_micro['mean_latency_s']:+.1f}s |")
        lines.append("")

        delta = p41_3b - p40_micro['mean_partial']
        if delta > 0.03:
            lines.append(f"**Outcome:** Granite 4.1 3B **outperforms** Granite 4.0 Micro by {delta:.0%}. IBM's 4.1>4.0 claim holds on Cerebra's task.")
        elif delta > -0.03:
            lines.append(f"**Outcome:** Granite 4.1 3B is **comparable** to Granite 4.0 Micro (within ±3%). Base vs instruct difference may account for the gap.")
        else:
            lines.append(f"**Outcome:** Granite 4.1 3B **underperforms** Granite 4.0 Micro by {abs(delta):.0%}. Base-model instruction-following gap likely explains the difference.")
    lines.append("")

    # 3b: Granite 4.1 8B vs Qwen 3.5 9B
    lines.append("### Granite 4.1 8B (base) vs Qwen 3.5 9B (instruct, current production)")
    lines.append("")
    lines.append("Tests whether a Granite 4.1 dense model can match or exceed current production accuracy.")
    lines.append("")
    if "granite41-8b" in all_runs:
        runs_41_8b = all_runs["granite41-8b"]
        p41_8b = mean(r.partial_acc for r in runs_41_8b)
        s41_8b = mean(r.strict_acc for r in runs_41_8b)
        p1_41_8b = mean(r.pass1_acc for r in runs_41_8b)
        lat_41_8b = mean(r.mean_latency_ms for r in runs_41_8b) / 1000

        qwen9b = ROUND1_BASELINES["qwen3.5-9b"]

        lines.append(f"| Metric | Granite 4.1 8B (base) | Qwen 3.5 9B (instruct) | Delta |")
        lines.append(f"|--------|:---------------------:|:----------------------:|:-----:|")
        lines.append(f"| Partial acc | {p41_8b:.0%} | {qwen9b['mean_partial']:.0%} | {p41_8b - qwen9b['mean_partial']:+.0%} |")
        lines.append(f"| Strict acc | {s41_8b:.0%} | {qwen9b['mean_strict']:.0%} | {s41_8b - qwen9b['mean_strict']:+.0%} |")
        lines.append(f"| Pass 1 quadrant acc | {p1_41_8b:.0%} | {qwen9b['mean_pass1']:.0%} | {p1_41_8b - qwen9b['mean_pass1']:+.0%} |")
        lines.append(f"| Mean latency | {lat_41_8b:.1f}s | {qwen9b['mean_latency_s']:.1f}s | {lat_41_8b - qwen9b['mean_latency_s']:+.1f}s |")
        lines.append("")

        delta = p41_8b - qwen9b['mean_partial']
        if delta > 0.03:
            lines.append(f"**Outcome:** Granite 4.1 8B **outperforms** Qwen 3.5 9B by {delta:.0%}. Production model switch is warranted.")
        elif delta > -0.03:
            lines.append(f"**Outcome:** Granite 4.1 8B is **competitive** with Qwen 3.5 9B (within ±3%). See recommendation section for tie-breaking criteria.")
        else:
            lines.append(f"**Outcome:** Granite 4.1 8B **underperforms** Qwen 3.5 9B by {abs(delta):.0%}. Base-model gap is significant. Keep Qwen 9B for production; evaluate Granite 4.1 instruct if available.")
    lines.append("")

    # 3c: Granite 4.1 8B vs Granite 4.0 32B MoE (can't test — note why)
    lines.append("### Granite 4.1 8B vs Granite 4.0 32B MoE")
    lines.append("")
    lines.append("IBM's claim: Granite 4.1 8B matches Granite 4.0 32B MoE at 4× fewer parameters.")
    lines.append("Cannot test directly — `ibm/granite4:tiny-h` in ollama list is the ~7B MoE variant")
    lines.append("(granite4-tiny-h in Round 1), not the 32B MoE. 32B does not fit in 12GB VRAM.")
    lines.append("")
    lines.append("Round 1 data for granite4-tiny-h (~7B MoE): 32% partial accuracy, 40% pass1.")
    if "granite41-8b" in all_runs:
        runs_41_8b = all_runs["granite41-8b"]
        p41_8b = mean(r.partial_acc for r in runs_41_8b)
        p1_41_8b = mean(r.pass1_acc for r in runs_41_8b)
        lines.append(f"Granite 4.1 8B (this run): {p41_8b:.0%} partial, {p1_41_8b:.0%} pass1.")
        if p41_8b > 0.32:
            lines.append(f"Granite 4.1 8B outperforms the 7B MoE variant by {p41_8b - 0.32:.0%} — consistent with IBM's architectural improvements.")
        else:
            lines.append("Granite 4.1 8B does not outperform the 7B MoE on this task.")
    lines.append("")

    # ── Section 4: Consensus failure analysis (task 7) ───────────────────────
    lines.append("## 4. Consensus Failure Analysis")
    lines.append("")
    lines.append("Round 1 identified 5 fixtures no model got right: `clear_07` (DESIGN), `clear_11` (EVENT),")
    lines.append("`hard_02` (MECHANISM), `hard_07` (DESIGN), `hard_11` (CONSTRAINT).")
    lines.append("")
    lines.append("Did either Round 2 model break any of these?")
    lines.append("")

    for model_name, runs in all_runs.items():
        ref = runs[0]
        broken = []
        still_wrong = []
        for fid in CONSENSUS_FAILURES:
            result = next((r for r in ref.fixture_results if r.fixture_id == fid), None)
            if result is None:
                continue
            if result.strict_correct:
                broken.append((fid, result.expected_d1, result.predicted_d1))
            elif result.partial_credit == 0.5:
                broken.append((fid, result.expected_d1, f"{result.predicted_d1} (0.5 credit)"))
            else:
                still_wrong.append((fid, result.expected_d1, result.predicted_d1))

        lines.append(f"**{model_name}:**")
        if broken:
            for fid, exp, pred in broken:
                lines.append(f"- ✓ `{fid}` ({exp}): correctly predicted `{pred}` — consensus broken!")
        else:
            lines.append("- No consensus failures broken")
        if still_wrong:
            for fid, exp, pred in still_wrong:
                lines.append(f"- ✗ `{fid}` ({exp}): got `{pred}`")
        lines.append("")

    # ── Section 5: Updated recommendation ────────────────────────────────────
    lines.append("## 5. Updated Recommendation")
    lines.append("")

    # Determine recommendation
    results_for_rec = {}
    for model_name, runs in all_runs.items():
        results_for_rec[model_name] = mean(r.partial_acc for r in runs)

    qwen9b_partial = ROUND1_BASELINES["qwen3.5-9b"]["mean_partial"]
    granite40_micro_partial = ROUND1_BASELINES["granite4-micro"]["mean_partial"]

    g41_8b_partial = results_for_rec.get("granite41-8b", 0.0)
    g41_3b_partial = results_for_rec.get("granite41-3b", 0.0)

    lines.append("### Phase 2 Production Model")
    lines.append("")

    if g41_8b_partial > qwen9b_partial + 0.03:
        lines.append(f"**Recommend switching to granite41-8b ({g41_8b_partial:.0%} partial).**")
        lines.append(f"Granite 4.1 8B outperforms Qwen 3.5 9B ({qwen9b_partial:.0%}) by more than 3 percentage points.")
        lines.append("No thinking mode means predictable latency. Apache 2.0 license. Same Granite family as v0.2 LoRA target.")
    elif g41_8b_partial >= qwen9b_partial - 0.03:
        lines.append(f"**Recommend keeping Qwen 3.5 9B for v0.1.0 ship, evaluating Granite 4.1 8B in v0.1.1.**")
        lines.append(f"Granite 4.1 8B ({g41_8b_partial:.0%}) is competitive with Qwen 3.5 9B ({qwen9b_partial:.0%})")
        lines.append("but this is a base model (non-instruct). Instruct variant may perform better once available.")
        lines.append("For v0.1.1: if instruct pull succeeds, re-run this calibration and decide then.")
    else:
        lines.append(f"**Recommend keeping Qwen 3.5 9B ({qwen9b_partial:.0%} partial).**")
        lines.append(f"Granite 4.1 8B base ({g41_8b_partial:.0%}) underperforms the current production model.")
        lines.append("Base vs instruct gap is significant for instruction-following tasks like classification.")
    lines.append("")

    lines.append("### v0.2 LoRA Training Target")
    lines.append("")
    lines.append("OLMo 3 was disqualified in Round 1 by latency (65s/fixture). Granite 4.1 is the")
    lines.append("strongest candidate for v0.2 LoRA:")
    lines.append("")
    lines.append("- **Base model availability**: base weights are ideal for LoRA fine-tuning (instruct variants are already instruction-tuned, reducing LoRA leverage)")
    lines.append("- **IBM training docs**: Granite 4.x has documented QLoRA methodology")
    lines.append("- **VRAM fit**: both 3B (2.1GB) and 8B (5.3GB) fit comfortably in 12GB for QLoRA")
    lines.append("- **Predictable inference**: no thinking mode means stable classification latency")
    lines.append("")

    if g41_8b_partial >= g41_3b_partial + 0.05:
        lines.append(f"**Recommend Granite 4.1 8B** as primary LoRA target ({g41_8b_partial:.0%} partial baseline).")
        lines.append("The 8B provides substantially more headroom for LoRA to improve over.")
    elif g41_3b_partial >= g41_8b_partial:
        lines.append(f"**Recommend Granite 4.1 3B** as primary LoRA target ({g41_3b_partial:.0%} partial baseline).")
        lines.append("The 3B model is competitive with 8B, faster to fine-tune, and cheaper to run post-LoRA.")
    else:
        lines.append(f"**Recommend Granite 4.1 8B** as primary LoRA target ({g41_8b_partial:.0%} partial baseline).")
        lines.append("Slight accuracy advantage; 8B typically responds better to LoRA signal on multi-class classification.")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 6. Raw Data")
    lines.append("")
    lines.append("Full per-fixture predictions and metrics for all Round 2 runs: `multi_model_comparison_raw_round2.json`")
    lines.append("")

    return "\n".join(lines)


def build_raw_json(
    all_runs: dict[str, list[ModelRunSummary]],
    model_meta: dict[str, tuple[str, str, str]],
) -> dict:
    out: dict = {"round": 2, "models": {}}
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
    report_path = out_dir / "multi_model_comparison_round2.md"
    raw_path = out_dir / "multi_model_comparison_raw_round2.json"

    print("Cerebra Multi-Model Calibration — Round 2 (Granite 4.1 Base Models)")
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
            if run_num < NUM_RUNS_PER_MODEL - 1:
                time.sleep(3)

        print(f"\n  Pausing 10s between models...\n")
        time.sleep(10)

    total_elapsed = time.monotonic() - t_total
    print(f"\nAll runs complete in {total_elapsed/60:.1f} minutes")

    report_md = build_round2_report(all_runs, model_meta)
    report_path.write_text(report_md, encoding="utf-8")

    raw_json = build_raw_json(all_runs, model_meta)
    raw_path.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")

    print(f"Written: {report_path}")
    print(f"Written: {raw_path}")

    print("\n── QUICK SUMMARY ──────────────────────────────────")
    for model_name, runs in all_runs.items():
        accs = [r.partial_acc for r in runs]
        print(f"  {model_name:<25} {mean(accs):.0%}  ({' / '.join(f'{a:.0%}' for a in accs)})")
    print(f"\n  [Round 1 baseline] qwen3.5-9b          58%")
    print(f"  [Round 1 baseline] granite4-micro       53%")


if __name__ == "__main__":
    main()
