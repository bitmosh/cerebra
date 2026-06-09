"""
Stage 2 — cross-model consensus filtering for v0.2 LoRA training corpus.

For each record that passed Stage 1, runs it through 2-3 consensus models using
the same v2.0.0 two-pass prompts. Records where ≥2/3 models agree with the
v0.1.0 label are marked "consensus". Records where models disagree are marked
"contested" — these get extra attention in Stage 3 manual review.

Estimated runtime: ~3 hours for 583 records × 3 models. Resumable: already-
processed records are skipped on restart.

Usage:
    cd /home/boop/Projects/cerebra
    python scripts/v02_training/stage2_consensus.py [--limit N] [--dry-run]

    --limit N    Process only first N records (for testing)
    --dry-run    Show what would run without calling Ollama

Output (in-place updates to stage1_filtered.jsonl):
    stage2_votes: {model: d1_name}
    stage2_consensus: "consensus" | "contested" | "split"

Time estimate:
    583 records × 3 models × 2 passes ≈ 3500 Ollama calls
    At ~2.5-4s per call = 2.5-4 hours total. Run overnight or while away.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cerebra.cognition.llm_adapter import OllamaDirectAdapter, ClassificationError

CONSENSUS_MODELS = [
    ("qwen3.5:latest",     "qwen35-9b"),
    ("llama3.1:8b",        "llama31-8b"),
    ("ibm/granite4:micro", "granite4-micro"),
]

D1_NAMES = {
    0: "OBSERVATION", 1: "PATTERN", 2: "MECHANISM", 3: "PHENOMENON",
    4: "TECHNIQUE",   5: "DESIGN",  6: "CREATION",  7: "TOOL",
    8: "PRINCIPLE",   9: "JUDGMENT", 10: "GOAL",     11: "CONSTRAINT",
    12: "EVENT",      13: "AGENT",  14: "CONTEXT",   15: "RELATION",
}
D1_BY_NAME = {v: k for k, v in D1_NAMES.items()}

OUTPUT_PATH = Path(__file__).parent / "output/stage1_filtered.jsonl"
CONSENSUS_OUTPUT_PATH = Path(__file__).parent / "output/stage2_consensus.jsonl"


def classify_two_pass(adapter: OllamaDirectAdapter, content: str, max_attempts: int = 2) -> str | None:
    """Run two-pass classification, return D1 name or None on failure."""
    pass1 = None
    for _ in range(max_attempts):
        try:
            pass1 = adapter.classify_quadrant(content)
            break
        except ClassificationError:
            time.sleep(1)
    if pass1 is None:
        return None

    for _ in range(max_attempts):
        try:
            pass2 = adapter.classify_within_quadrant(content, pass1.primary)
            return pass2.primary
        except ClassificationError:
            time.sleep(1)
    return None


def compute_consensus(v0_label: str, votes: dict[str, str]) -> str:
    """
    Returns:
      consensus   — ≥2 of 3 models agree with v0.1.0 label
      contested   — ≥2 of 3 models agree on something OTHER than v0.1.0 label
      split       — no majority (all disagree, or 1 right + 1 wrong + 1 failure)
    """
    valid_votes = [v for v in votes.values() if v is not None]
    if not valid_votes:
        return "split"
    agree_count = sum(1 for v in valid_votes if v == v0_label)
    total = len(valid_votes)
    if agree_count >= 2:
        return "consensus"
    if total - agree_count >= 2:
        return "contested"
    return "split"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not OUTPUT_PATH.exists():
        print(f"ERROR: {OUTPUT_PATH} not found. Run stage1_export.py first.")
        sys.exit(1)

    records = [json.loads(l) for l in OUTPUT_PATH.read_text().splitlines() if l.strip()]
    if args.limit:
        records = records[: args.limit]

    # Find records that still need Stage 2
    pending = [r for r in records if not r.get("stage2_votes")]
    done = [r for r in records if r.get("stage2_votes")]
    print(f"\nStage 2 status: {len(done)} done, {len(pending)} pending, {len(records)} total")

    if not pending:
        print("All records already processed. Nothing to do.")
        _print_summary(records)
        return

    if args.dry_run:
        print(f"\nDRY RUN: would process {len(pending)} records through {len(CONSENSUS_MODELS)} models")
        est_calls = len(pending) * len(CONSENSUS_MODELS) * 2
        print(f"Estimated API calls: {est_calls}")
        print(f"Estimated time: ~{est_calls * 3 // 60} minutes")
        return

    adapters = {
        label: OllamaDirectAdapter(model=tag, temperature=0.0)
        for tag, label in CONSENSUS_MODELS
    }

    # Build record index for in-place updates
    record_map = {r["record_id"]: r for r in records}

    t0 = time.monotonic()
    for i, record in enumerate(pending):
        rid = record["record_id"]
        v0_label = record["d1_name"]
        content = record["content"]

        votes: dict[str, str | None] = {}
        for tag, label in CONSENSUS_MODELS:
            adapter = adapters[label]
            result = classify_two_pass(adapter, content)
            votes[label] = result

        consensus = compute_consensus(v0_label, {k: v for k, v in votes.items() if v})
        record_map[rid]["stage2_votes"] = votes
        record_map[rid]["stage2_consensus"] = consensus

        elapsed = time.monotonic() - t0
        rate = (i + 1) / elapsed
        remaining = (len(pending) - i - 1) / rate if rate > 0 else 0

        agree_symbol = "✓" if consensus == "consensus" else ("✗" if consensus == "contested" else "~")
        print(f"  [{i+1:4d}/{len(pending)}] {agree_symbol} {v0_label:12s}  "
              f"votes={list(votes.values())}  "
              f"ETA {remaining/60:.1f}min", flush=True)

        # Write after every record (resume safety)
        _write_records(list(record_map.values()), OUTPUT_PATH)

    print(f"\nStage 2 complete. {len(pending)} records processed.")
    _print_summary(list(record_map.values()))
    _write_consensus_output(list(record_map.values()), CONSENSUS_OUTPUT_PATH)
    print(f"Canonical output written to {CONSENSUS_OUTPUT_PATH.name}")


def _print_summary(records: list[dict]) -> None:
    counts: dict[str, int] = {}
    for r in records:
        key = r.get("stage2_consensus", "pending") or "pending"
        counts[key] = counts.get(key, 0) + 1
    print("\nConsensus summary:")
    for k, v in sorted(counts.items()):
        print(f"  {k:12s}: {v:4d}  ({v*100/len(records):.1f}%)")


def _write_consensus_output(records: list[dict], path: Path) -> None:
    """Write canonical stage2_consensus.jsonl with a clean, minimal schema."""
    VOTE_KEYS = ["qwen35-9b", "llama31-8b", "granite4-micro"]
    with path.open("w") as fh:
        for r in records:
            if not r.get("stage2_votes"):
                continue
            votes = r["stage2_votes"]
            agree = sum(1 for v in votes.values() if v == r["d1_name"])
            out = {
                "record_id":        r["record_id"],
                "content":          r["content"],
                "d1":               r["d1"],
                "d1_name":          r["d1_name"],
                "quadrant":         r["quadrant"],
                "d1_confidence":    r["d1_confidence"],
                "sku_address":      r.get("sku_address"),
                "stage2_votes":     {k: votes.get(k) for k in VOTE_KEYS},
                "agreement_count":  agree,
                "stage2_consensus": r["stage2_consensus"],
            }
            fh.write(json.dumps(out) + "\n")


def _write_records(records: list[dict], path: Path) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    tmp.replace(path)


if __name__ == "__main__":
    main()
