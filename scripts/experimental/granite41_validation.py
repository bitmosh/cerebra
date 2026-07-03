"""
Granite 4.1 3B production substrate validation.
Runs the v0.1.0 two-pass classifier on 50 sampled real corpus chunks,
capturing mechanical reliability, quality, distribution, and performance.

NOT PRODUCTION CODE. Validation harness.

Usage:
    cd <repo-root>
    python scripts/experimental/granite41_validation.py

Output:
    docs/agent/validation_sample_chunks.json
    docs/agent/granite41_3b_validation_raw.json
    docs/agent/granite41_3b_validation.md
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cerebra.cognition.llm_adapter import OllamaDirectAdapter, ClassificationError

# ── Config ─────────────────────────────────────────────────────────────────────

DB_PATH = Path.home() / "cerebra-vaults/dev/data/cerebra.db"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODEL_TAG = "huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M"
TEMPERATURE = 0.0
TIMEOUT = 120
RANDOM_SEED = 42

OUT_DIR = Path(__file__).parent.parent.parent / "docs" / "agent"
SAMPLE_PATH = OUT_DIR / "validation_sample_chunks.json"
RAW_PATH = OUT_DIR / "granite41_3b_validation_raw.json"
REPORT_PATH = OUT_DIR / "granite41_3b_validation.md"

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


# ── Sampling ───────────────────────────────────────────────────────────────────

def sample_chunks() -> list[dict]:
    """Select 50 stratified chunks from the vault."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    def fetch(query: str, params=()) -> list[dict]:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    base_where = "mr.sku_address IS NULL AND mr.lifecycle_state = 'active'"
    base_select = """
        SELECT mr.record_id, mr.content, mr.token_estimate, mr.document_id,
               d.title as doc_title, LENGTH(mr.content) as content_len,
               CASE
                 WHEN mr.content LIKE '%```%' THEN 1
                 WHEN mr.content LIKE '%    %' AND LENGTH(mr.content) > 100 THEN 1
                 ELSE 0
               END as has_code
        FROM memory_records mr
        JOIN documents d ON mr.document_id = d.document_id
        WHERE {where}
        ORDER BY RANDOM()
        LIMIT {limit}
    """

    selected = {}
    strata_counts = {}

    def add(rows: list[dict], stratum: str, target: int):
        count = 0
        for r in rows:
            if r["record_id"] not in selected and count < target:
                r["stratum"] = stratum
                selected[r["record_id"]] = r
                count += 1
        strata_counts[stratum] = count

    # Short < 200 chars
    short = fetch(base_select.format(
        where=f"{base_where} AND LENGTH(mr.content) < 200", limit=15))
    add(short, "short", 10)

    # Long 1000+ chars
    long_ = fetch(base_select.format(
        where=f"{base_where} AND LENGTH(mr.content) >= 1000", limit=15))
    add(long_, "long", 10)

    # Code blocks
    code = fetch(base_select.format(
        where=f"{base_where} AND (mr.content LIKE '%```%' OR (mr.content LIKE '%    %' AND LENGTH(mr.content) > 100))",
        limit=20))
    add(code, "code", 10)

    # Medium 200-999
    medium = fetch(base_select.format(
        where=f"{base_where} AND LENGTH(mr.content) BETWEEN 200 AND 999", limit=20))
    add(medium, "medium", 10)

    # Random fill to reach 50
    remaining = 50 - len(selected)
    if remaining > 0:
        exclude = "', '".join(selected.keys())
        random_fill = fetch(base_select.format(
            where=f"{base_where} AND mr.record_id NOT IN ('{exclude}')",
            limit=remaining + 10))
        add(random_fill, "random", remaining)

    conn.close()

    chunks = list(selected.values())
    print(f"Sampled {len(chunks)} chunks:")
    for stratum, count in strata_counts.items():
        print(f"  {stratum}: {count}")
    return chunks


# ── Classification ─────────────────────────────────────────────────────────────

@dataclass
class ChunkResult:
    record_id: str
    doc_title: str
    content_len: int
    token_estimate: int
    stratum: str
    has_code: bool
    pass1_quadrant: str
    pass1_confidence: float
    pass2_d1: str
    pass2_confidence: float
    total_latency_ms: int
    pass1_latency_ms: int
    pass2_latency_ms: int
    parse_failed: bool
    failure_reason: str
    refused: bool


def classify_chunk(adapter: OllamaDirectAdapter, chunk: dict) -> ChunkResult:
    t_start = time.monotonic()
    parse_failed = False
    refused = False
    failure_reason = ""
    pass1_quadrant = ""
    pass1_conf = 0.0
    pass2_d1 = ""
    pass2_conf = 0.0
    pass1_lat = 0
    pass2_lat = 0

    content = chunk["content"]

    try:
        p1 = adapter.classify_quadrant(content)
        pass1_quadrant = p1.primary
        pass1_conf = p1.confidence
        pass1_lat = p1.latency_ms or 0

        # Check for refusal patterns
        if not pass1_quadrant or pass1_quadrant.upper() in ("UNKNOWN", "NONE", ""):
            refused = True
            failure_reason = f"pass1 refusal: quadrant='{pass1_quadrant}'"

        p2 = adapter.classify_within_quadrant(content, pass1_quadrant)
        pass2_d1 = p2.primary
        pass2_conf = p2.confidence
        pass2_lat = p2.latency_ms or 0

        if not pass2_d1 or pass2_d1.upper() in ("UNKNOWN", "NONE", ""):
            refused = True
            failure_reason = f"pass2 refusal: d1='{pass2_d1}'"

    except ClassificationError as e:
        parse_failed = True
        failure_reason = str(e)[:120]
    except Exception as e:
        parse_failed = True
        failure_reason = f"{type(e).__name__}: {str(e)[:100]}"

    total_lat = int((time.monotonic() - t_start) * 1000)

    return ChunkResult(
        record_id=chunk["record_id"],
        doc_title=chunk["doc_title"],
        content_len=chunk["content_len"],
        token_estimate=chunk["token_estimate"],
        stratum=chunk["stratum"],
        has_code=bool(chunk["has_code"]),
        pass1_quadrant=pass1_quadrant,
        pass1_confidence=pass1_conf,
        pass2_d1=pass2_d1,
        pass2_confidence=pass2_conf,
        total_latency_ms=total_lat,
        pass1_latency_ms=pass1_lat,
        pass2_latency_ms=pass2_lat,
        parse_failed=parse_failed,
        failure_reason=failure_reason,
        refused=refused,
    )


# ── VRAM ───────────────────────────────────────────────────────────────────────

def sample_vram_mb() -> int | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5,
        )
        return int(out.decode().strip().split("\n")[0])
    except Exception:
        return None


# ── Report ─────────────────────────────────────────────────────────────────────

def build_report(
    chunks: list[dict],
    results: list[ChunkResult],
    spot_check_indices: list[int],
    vram_peak: int | None,
    total_elapsed_s: float,
) -> str:
    from collections import Counter

    lines = []
    lines.append("# Granite 4.1 3B — Production Substrate Validation")
    lines.append("")
    lines.append(f"**Model:** `{MODEL_TAG}`  ")
    lines.append(f"**Date:** 2026-06-06  ")
    lines.append(f"**Prompt version:** 2.0.0 (v0.1.0 two-pass)  ")
    lines.append(f"**Temperature:** 0.0  ")
    lines.append(f"**Corpus:** ~/cerebra-vaults/dev/ (740 unclassified records)")
    lines.append("")

    # ── Section 1: Sample ──────────────────────────────────────────────────────
    lines.append("## 1. Sample")
    lines.append("")
    lines.append("50 chunks stratified from the vault's unclassified corpus:")
    lines.append("")

    strata = Counter(r.stratum for r in results)
    for s, n in sorted(strata.items()):
        lines.append(f"- **{s}**: {n} chunks")
    lines.append("")

    len_dist = [r.content_len for r in results]
    lines.append(f"Content length: min={min(len_dist)} / mean={int(mean(len_dist))} / max={max(len_dist)} chars")
    lines.append(f"Code-containing: {sum(1 for r in results if r.has_code)}/50")
    lines.append(f"Chunk IDs saved to: `validation_sample_chunks.json`")
    lines.append("")

    # ── Section 2: Mechanical reliability ─────────────────────────────────────
    lines.append("## 2. Mechanical Reliability")
    lines.append("")

    failures = [r for r in results if r.parse_failed]
    refusals = [r for r in results if r.refused and not r.parse_failed]
    slow = [r for r in results if r.total_latency_ms > 10_000]

    lines.append(f"| Check | Result |")
    lines.append(f"|-------|--------|")
    lines.append(f"| Parse failures | {len(failures)}/50 ({len(failures)/50:.0%}) |")
    lines.append(f"| Refusals (non-committal output) | {len(refusals)}/50 |")
    lines.append(f"| Chunks >10s | {len(slow)}/50 |")
    lines.append(f"| NULL/empty outputs | {sum(1 for r in results if not r.pass2_d1 and not r.parse_failed)}/50 |")
    lines.append("")

    if failures:
        lines.append("**Parse failures:**")
        for r in failures:
            lines.append(f"- `{r.record_id[:20]}...` ({r.stratum}, {r.content_len} chars): {r.failure_reason}")
        lines.append("")

    if slow:
        lines.append("**Slow chunks (>10s):**")
        for r in slow:
            lines.append(f"- `{r.record_id[:20]}...` ({r.stratum}, {r.content_len} chars): {r.total_latency_ms}ms")
        lines.append("")

    if not failures and not refusals:
        lines.append("All 50 chunks classified successfully with no parse failures or refusals.")
        lines.append("")

    # ── Section 3: Quality spot-check ─────────────────────────────────────────
    lines.append("## 3. Quality Spot-Check")
    lines.append("")
    lines.append("10 randomly selected classifications reviewed for reasonableness.")
    lines.append("Verdict: **reasonable** (correct neighborhood) / **questionable** / **obviously wrong**.")
    lines.append("")

    for i, idx in enumerate(spot_check_indices):
        r = results[idx]
        chunk = chunks[idx]
        content_preview = chunk["content"][:300].replace("\n", " ")
        if len(chunk["content"]) > 300:
            content_preview += "..."
        lines.append(f"### Spot-check {i+1}: `{r.record_id[:24]}`")
        lines.append(f"**Source:** {r.doc_title}  ")
        lines.append(f"**Stratum:** {r.stratum} ({r.content_len} chars)  ")
        lines.append(f"**Classification:** Pass 1 → {r.pass1_quadrant} ({r.pass1_confidence:.2f}) | Pass 2 → {r.pass2_d1} ({r.pass2_confidence:.2f})  ")
        lines.append(f"**Content:** *{content_preview}*")
        lines.append("")
        lines.append(f"**Verdict:** [see analysis below]")
        lines.append("")

    lines.append("")

    # ── Section 4: Distribution ────────────────────────────────────────────────
    lines.append("## 4. Distribution")
    lines.append("")

    valid = [r for r in results if not r.parse_failed]

    d1_counts = Counter(r.pass2_d1 for r in valid)
    q_counts = Counter(r.pass1_quadrant for r in valid)

    lines.append("### Pass 1 quadrant distribution")
    lines.append("")
    lines.append("| Quadrant | Count | % |")
    lines.append("|----------|:-----:|:-:|")
    for q in ["EMPIRICAL", "GENERATIVE", "NORMATIVE", "RELATIONAL"]:
        n = q_counts.get(q, 0)
        lines.append(f"| {q} | {n} | {n/len(valid):.0%} |")
    lines.append("")

    lines.append("### Pass 2 D1 category distribution")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|:-----:|")
    for cat, n in sorted(d1_counts.items(), key=lambda x: -x[1]):
        bar = "█" * n
        lines.append(f"| {cat} | {n} {bar} |")
    lines.append("")

    zero_cats = [cat for cat in D1_TO_QUADRANT if cat not in d1_counts]
    if zero_cats:
        lines.append(f"**Unrepresented categories:** {', '.join(zero_cats)}")
        lines.append("")

    # Check for bias
    top_cat, top_n = d1_counts.most_common(1)[0]
    if top_n > 20:
        lines.append(f"⚠ **Potential bias**: {top_cat} accounts for {top_n}/{len(valid)} ({top_n/len(valid):.0%}) of classifications. "
                     f"Expected ~3-4 per category if uniform. Investigate if this reflects corpus reality or model over-prediction.")
    else:
        lines.append("Distribution appears reasonable — no single category dominates (>40%).")
    lines.append("")

    # ── Section 5: Performance ─────────────────────────────────────────────────
    lines.append("## 5. Performance")
    lines.append("")

    lats = [r.total_latency_ms for r in valid]
    lats_sorted = sorted(lats)
    mean_lat = mean(lats)
    p50 = lats_sorted[len(lats)//2]
    p95 = lats_sorted[int(len(lats)*0.95)]

    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Mean latency | {mean_lat/1000:.2f}s |")
    lines.append(f"| Min latency | {min(lats)/1000:.2f}s |")
    lines.append(f"| Max latency | {max(lats)/1000:.2f}s |")
    lines.append(f"| p50 latency | {p50/1000:.2f}s |")
    lines.append(f"| p95 latency | {p95/1000:.2f}s |")
    lines.append(f"| VRAM peak | {vram_peak}MB |" if vram_peak else "| VRAM peak | n/a |")
    lines.append(f"| Total run (50 chunks) | {total_elapsed_s:.0f}s |")
    lines.append("")

    backfill_estimate_s = 740 * (mean_lat / 1000)
    backfill_min = backfill_estimate_s / 60
    lines.append(f"**Estimated full-backfill duration (740 chunks):** {backfill_estimate_s/60:.0f} minutes "
                 f"({backfill_estimate_s:.0f}s at mean {mean_lat/1000:.2f}s/chunk)")
    lines.append("")

    # Content-length vs latency
    by_stratum: dict[str, list[int]] = {}
    for r in valid:
        by_stratum.setdefault(r.stratum, []).append(r.total_latency_ms)
    lines.append("**Latency by stratum:**")
    for stratum, strat_lats in sorted(by_stratum.items()):
        lines.append(f"- {stratum}: mean={mean(strat_lats)/1000:.2f}s  min={min(strat_lats)/1000:.2f}s  max={max(strat_lats)/1000:.2f}s")
    lines.append("")

    # ── Section 6: Verdict ─────────────────────────────────────────────────────
    lines.append("## 6. Verdict")
    lines.append("")

    parse_fail_rate = len(failures) / 50
    if parse_fail_rate == 0 and not refusals and not slow:
        lines.append("### ✓ Cleared for backfill")
        lines.append("")
        lines.append("No mechanical issues detected across 50 real corpus chunks:")
        lines.append(f"- Parse failure rate: 0/50")
        lines.append(f"- Refusal rate: 0/50")
        lines.append(f"- No chunks exceeded 10s latency")
        lines.append(f"- Estimated backfill time: ~{backfill_min:.0f} minutes for 740 chunks")
        lines.append("")
        lines.append(f"Granite 4.1 3B (`{MODEL_TAG}`) is ready for Phase 2 close-out.")
        lines.append("Proceed with updating the production model configuration in the Phase 2 close-out pass.")
    elif parse_fail_rate <= 0.04:
        lines.append("### ⚠ Cleared with observations")
        lines.append("")
        lines.append(f"Minor issues detected ({len(failures)} parse failure(s), {len(slow)} slow chunk(s)).")
        lines.append("See Sections 2 and 5 for details. Not blocking for backfill, but monitor during the run.")
    else:
        lines.append("### ✗ Blocked")
        lines.append("")
        lines.append(f"Parse failure rate {parse_fail_rate:.0%} exceeds acceptable threshold.")
        lines.append("Investigate failure patterns before proceeding to backfill.")

    lines.append("")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    random.seed(RANDOM_SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Granite 4.1 3B Validation — Production Substrate Check")
    print(f"Model: {MODEL_TAG}")
    print(f"DB: {DB_PATH}")
    print()

    # Step 1: Sample
    print("Sampling 50 chunks...")
    chunks = sample_chunks()
    if len(chunks) < 50:
        print(f"WARNING: only {len(chunks)} chunks available (expected 50)")

    # Save sample
    sample_data = [
        {"record_id": c["record_id"], "doc_title": c["doc_title"],
         "stratum": c["stratum"], "content_len": c["content_len"]}
        for c in chunks
    ]
    SAMPLE_PATH.write_text(json.dumps(sample_data, indent=2))
    print(f"Sample saved to {SAMPLE_PATH}")

    # Step 2: Run classifier
    print(f"\nRunning two-pass classifier on {len(chunks)} chunks...")
    adapter = OllamaDirectAdapter(
        base_url=OLLAMA_BASE_URL,
        model=MODEL_TAG,
        timeout=TIMEOUT,
        temperature=TEMPERATURE,
    )

    print("  health check...")
    try:
        adapter.health_check()
    except Exception as e:
        print(f"  WARNING: health check failed: {e}")

    results: list[ChunkResult] = []
    vram_peak = sample_vram_mb()
    t_run_start = time.monotonic()

    for i, chunk in enumerate(chunks):
        print(f"  [{i+1:2d}/50] {chunk['record_id'][:20]}... ({chunk['stratum']}, {chunk['content_len']}ch)",
              end=" ", flush=True)
        result = classify_chunk(adapter, chunk)
        results.append(result)

        v = sample_vram_mb()
        if v and (vram_peak is None or v > vram_peak):
            vram_peak = v

        if result.parse_failed:
            print(f"FAILED: {result.failure_reason[:50]}")
        else:
            print(f"{result.pass1_quadrant[:3]}→{result.pass2_d1:<12} {result.total_latency_ms}ms")

    total_elapsed = time.monotonic() - t_run_start
    print(f"\nRun complete in {total_elapsed:.0f}s")

    # Step 3: Pick spot-check indices
    valid_indices = [i for i, r in enumerate(results) if not r.parse_failed]
    spot_check_indices = random.sample(valid_indices, min(10, len(valid_indices)))
    spot_check_indices.sort()

    # Step 4: Write raw JSON
    raw = {
        "model": MODEL_TAG,
        "temperature": TEMPERATURE,
        "total_chunks": len(chunks),
        "total_elapsed_s": total_elapsed,
        "vram_peak_mb": vram_peak,
        "spot_check_indices": spot_check_indices,
        "results": [asdict(r) for r in results],
        "chunks": [
            {"record_id": c["record_id"], "content": c["content"],
             "doc_title": c["doc_title"], "stratum": c["stratum"]}
            for c in chunks
        ],
    }
    RAW_PATH.write_text(json.dumps(raw, indent=2))
    print(f"Raw results saved to {RAW_PATH}")

    # Step 5: Write report
    report_md = build_report(chunks, results, spot_check_indices, vram_peak, total_elapsed)
    REPORT_PATH.write_text(report_md, encoding="utf-8")
    print(f"Report saved to {REPORT_PATH}")

    # Quick summary
    failures = sum(1 for r in results if r.parse_failed)
    valid = [r for r in results if not r.parse_failed]
    from collections import Counter
    d1_dist = Counter(r.pass2_d1 for r in valid)
    lats = [r.total_latency_ms for r in valid]
    print(f"\n── QUICK SUMMARY ──────────────────────")
    print(f"  Parse failures: {failures}/50")
    print(f"  Mean latency:   {mean(lats)/1000:.2f}s")
    print(f"  Top D1 cats:    {dict(d1_dist.most_common(5))}")
    print(f"  VRAM peak:      {vram_peak}MB")


if __name__ == "__main__":
    main()
