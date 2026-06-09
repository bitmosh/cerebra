"""
Stage 1 — confidence filtering and export for v0.2 LoRA training corpus.

Queries the production vault for all 745 backfill records, analyzes the
d1_confidence distribution, applies the chosen threshold, and exports the
filtered records to JSONL for use in Stage 2 (cross-model consensus) and
Stage 3 (manual review).

Usage:
    cd /home/boop/Projects/cerebra
    python scripts/v02_training/stage1_export.py [--threshold 0.70] [--vault PATH]

Output:
    scripts/v02_training/output/stage1_analysis.json   — distribution stats
    scripts/v02_training/output/stage1_filtered.jsonl  — filtered records
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

VAULT_DEFAULT = Path.home() / "cerebra-vaults/dev"

D1_NAMES = {
    0: "OBSERVATION", 1: "PATTERN", 2: "MECHANISM", 3: "PHENOMENON",
    4: "TECHNIQUE",   5: "DESIGN",  6: "CREATION",  7: "TOOL",
    8: "PRINCIPLE",   9: "JUDGMENT", 10: "GOAL",     11: "CONSTRAINT",
    12: "EVENT",      13: "AGENT",  14: "CONTEXT",   15: "RELATION",
}

D1_QUADRANT = {
    0: "EMPIRICAL", 1: "EMPIRICAL", 2: "EMPIRICAL", 3: "EMPIRICAL",
    4: "GENERATIVE", 5: "GENERATIVE", 6: "GENERATIVE", 7: "GENERATIVE",
    8: "NORMATIVE", 9: "NORMATIVE", 10: "NORMATIVE", 11: "NORMATIVE",
    12: "RELATIONAL", 13: "RELATIONAL", 14: "RELATIONAL", 15: "RELATIONAL",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: confidence filtering")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="Minimum d1_confidence to retain (default: 0.70)")
    parser.add_argument("--vault", type=Path, default=VAULT_DEFAULT)
    args = parser.parse_args()

    db_path = args.vault / "data/cerebra.db"
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    rows = con.execute("""
        SELECT
            sa.record_id,
            sa.d1,
            sa.d1_confidence,
            sa.sku_address,
            sa.raw_scores_json,
            sa.latency_ms,
            mr.content
        FROM sku_assignments sa
        JOIN memory_records mr ON sa.record_id = mr.record_id
        ORDER BY sa.d1_confidence DESC
    """).fetchall()
    con.close()

    total = len(rows)
    print(f"\nTotal backfill records: {total}")

    # ── Distribution analysis ──────────────────────────────────────────────────
    buckets = {">=0.9": 0, "0.8-0.9": 0, "0.7-0.8": 0, "0.6-0.7": 0, "<0.6": 0}
    cat_counts: dict[str, dict[str, int | float]] = {}

    for row in rows:
        c = row["d1_confidence"]
        if c >= 0.9:
            buckets[">=0.9"] += 1
        elif c >= 0.8:
            buckets["0.8-0.9"] += 1
        elif c >= 0.7:
            buckets["0.7-0.8"] += 1
        elif c >= 0.6:
            buckets["0.6-0.7"] += 1
        else:
            buckets["<0.6"] += 1

        name = D1_NAMES[row["d1"]]
        if name not in cat_counts:
            cat_counts[name] = {"total": 0, "above_threshold": 0, "conf_sum": 0.0}
        cat_counts[name]["total"] += 1
        cat_counts[name]["conf_sum"] += c

    print("\nConfidence distribution:")
    for label, count in buckets.items():
        bar = "█" * (count // 5)
        print(f"  {label:8s} {count:4d}  ({count*100/total:5.1f}%)  {bar}")

    threshold = args.threshold
    print(f"\nThreshold: {threshold}")
    for label, count in buckets.items():
        lo = {">=0.9": 0.9, "0.8-0.9": 0.8, "0.7-0.8": 0.7, "0.6-0.7": 0.6, "<0.6": 0.0}[label]
        if lo >= threshold:
            print(f"  KEEP  {label}: {count}")
        else:
            print(f"  DROP  {label}: {count}")

    # ── Per-category survival ──────────────────────────────────────────────────
    for row in rows:
        name = D1_NAMES[row["d1"]]
        if row["d1_confidence"] >= threshold:
            cat_counts[name]["above_threshold"] += 1

    retained = [r for r in rows if r["d1_confidence"] >= threshold]
    dropped = [r for r in rows if r["d1_confidence"] < threshold]

    print(f"\nRetained at >= {threshold}: {len(retained)}/{total} ({len(retained)*100/total:.1f}%)")
    print(f"Dropped:                    {len(dropped)}/{total} ({len(dropped)*100/total:.1f}%)")

    print("\nPer-category survival:")
    for name, stats in sorted(cat_counts.items(), key=lambda x: -x[1]["total"]):
        t = stats["total"]
        a = stats["above_threshold"]
        mean_conf = stats["conf_sum"] / t if t else 0
        print(f"  {name:12s}  total={t:3d}  kept={a:3d} ({a*100//t if t else 0:3d}%)  "
              f"mean_conf={mean_conf:.3f}")

    categories_retained = {D1_NAMES[r["d1"]] for r in retained}
    missing = set(D1_NAMES.values()) - categories_retained
    if missing:
        print(f"\n  WARNING: categories absent after filtering: {missing}")
    else:
        print(f"\n  All {len(categories_retained)} categories retained ✓")

    # ── Export ────────────────────────────────────────────────────────────────
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    analysis = {
        "total": total,
        "threshold": threshold,
        "retained": len(retained),
        "dropped": len(dropped),
        "distribution": {k: {"count": v, "pct": round(v * 100 / total, 1)} for k, v in buckets.items()},
        "per_category": {
            name: {
                "total": s["total"],
                "retained": s["above_threshold"],
                "pct_retained": round(s["above_threshold"] * 100 / s["total"], 1) if s["total"] else 0,
                "mean_conf": round(s["conf_sum"] / s["total"], 3) if s["total"] else 0,
            }
            for name, s in cat_counts.items()
        },
    }
    analysis_path = out_dir / "stage1_analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2))
    print(f"\nAnalysis written to: {analysis_path}")

    filtered_path = out_dir / "stage1_filtered.jsonl"
    written = 0
    with filtered_path.open("w") as fh:
        for row in retained:
            raw_scores = json.loads(row["raw_scores_json"]) if row["raw_scores_json"] else {}
            record = {
                "record_id": row["record_id"],
                "content": row["content"],
                "d1": row["d1"],
                "d1_name": D1_NAMES[row["d1"]],
                "quadrant": D1_QUADRANT[row["d1"]],
                "d1_confidence": row["d1_confidence"],
                "sku_address": row["sku_address"],
                "raw_scores_pass1": raw_scores.get("pass1", {}),
                "raw_scores_pass2": raw_scores.get("pass2", {}),
                "latency_ms": row["latency_ms"],
                # Stage 2/3 fields (filled later)
                "stage2_votes": {},
                "stage2_consensus": None,
                "stage3_verdict": None,
                "stage3_label": None,
                "stage3_notes": "",
            }
            fh.write(json.dumps(record) + "\n")
            written += 1

    print(f"Filtered records written to: {filtered_path}  ({written} records)")
    print("\nNext step: run stage2_consensus.py to add cross-model votes.")


if __name__ == "__main__":
    main()
