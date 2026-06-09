"""
Recover stage2_consensus.jsonl from stage2_run.log.

stage2_consensus.py wrote its results to stage1_filtered.jsonl in-place
and to stdout (captured in stage2_run.log) but never produced a separate
stage2_consensus.jsonl. This script parses the log as source of truth,
cross-checks against stage1_filtered.jsonl metadata, and writes the
canonical stage2_consensus.jsonl.

Usage:
    cd ~/Projects/cerebra
    python scripts/v02_training/recover_stage2.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
STAGE1_PATH = SCRIPT_DIR / "output/stage1_filtered.jsonl"
LOG_PATH = SCRIPT_DIR / "output/stage2_run.log"
OUTPUT_PATH = SCRIPT_DIR / "output/stage2_consensus.jsonl"

# Vote order matches CONSENSUS_MODELS in stage2_consensus.py
VOTE_KEYS = ["qwen35-9b", "llama31-8b", "granite4-micro"]

# Pattern: "  [ 127/583] ✗ DESIGN        votes=['A', 'B', 'C']  ETA 3.2min"
LOG_LINE_RE = re.compile(
    r"\[\s*(\d+)/583\]\s+\S+\s+(\w+)\s+votes=(\[.*?\])"
)

EXPECTED_CONSENSUS = 205
EXPECTED_CONTESTED = 378


def parse_log(path: Path) -> dict[int, tuple[str, list[str]]]:
    """
    Parse log lines into {1-based-index: (v01_label, [vote0, vote1, vote2])}.
    Raises on malformed lines or wrong record count.
    """
    parsed: dict[int, tuple[str, list[str]]] = {}
    errors: list[str] = []

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = LOG_LINE_RE.search(line)
        if not m:
            continue
        idx_str, label, votes_str = m.group(1), m.group(2), m.group(3)
        idx = int(idx_str)
        try:
            votes = ast.literal_eval(votes_str)
        except (ValueError, SyntaxError) as e:
            errors.append(f"line {lineno}: could not parse votes {votes_str!r}: {e}")
            continue
        if not isinstance(votes, list) or len(votes) != 3:
            errors.append(f"line {lineno}: expected 3 votes, got {votes!r}")
            continue
        if idx in parsed:
            errors.append(f"line {lineno}: duplicate index {idx}")
            continue
        parsed[idx] = (label, [str(v) for v in votes])

    if errors:
        for e in errors:
            print(f"  PARSE ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    return parsed


def compute_consensus(d1_name: str, votes: dict[str, str]) -> tuple[str, int]:
    """Return (consensus_tag, agreement_count)."""
    valid = [v for v in votes.values() if v is not None]
    if not valid:
        return "split", 0
    agree = sum(1 for v in valid if v == d1_name)
    total = len(valid)
    if agree >= 2:
        return "consensus", agree
    if total - agree >= 2:
        return "contested", agree
    return "split", agree


def main() -> None:
    for path in (STAGE1_PATH, LOG_PATH):
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            sys.exit(1)

    print(f"Reading stage1 records from {STAGE1_PATH.name}...")
    stage1 = [json.loads(l) for l in STAGE1_PATH.read_text().splitlines() if l.strip()]
    print(f"  {len(stage1)} records loaded.")

    print(f"Parsing {LOG_PATH.name}...")
    log_data = parse_log(LOG_PATH)
    print(f"  {len(log_data)} vote lines parsed.")

    if len(log_data) != len(stage1):
        print(
            f"ERROR: log has {len(log_data)} entries but stage1 has {len(stage1)} records.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build output, cross-checking label agreement between log and stage1
    label_mismatches: list[str] = []
    out_records: list[dict] = []
    counts: dict[str, int] = {"consensus": 0, "contested": 0, "split": 0}

    for i, record in enumerate(stage1):
        idx = i + 1  # 1-based
        if idx not in log_data:
            print(f"ERROR: index {idx} missing from log.", file=sys.stderr)
            sys.exit(1)

        log_label, vote_list = log_data[idx]

        # Cross-check: log label should match d1_name in stage1
        if log_label != record["d1_name"]:
            label_mismatches.append(
                f"  idx {idx}: log says {log_label!r}, stage1 says {record['d1_name']!r}"
            )

        votes = dict(zip(VOTE_KEYS, vote_list))
        consensus_tag, agreement_count = compute_consensus(record["d1_name"], votes)
        counts[consensus_tag] = counts.get(consensus_tag, 0) + 1

        out_record = {
            "record_id":        record["record_id"],
            "content":          record["content"],
            "d1":               record["d1"],
            "d1_name":          record["d1_name"],
            "quadrant":         record["quadrant"],
            "d1_confidence":    record["d1_confidence"],
            "sku_address":      record.get("sku_address"),
            "stage2_votes":     votes,
            "agreement_count":  agreement_count,
            "stage2_consensus": consensus_tag,
        }
        out_records.append(out_record)

    if label_mismatches:
        print(f"\nWARNING: {len(label_mismatches)} label mismatches between log and stage1:")
        for m in label_mismatches[:10]:
            print(m)
        if len(label_mismatches) > 10:
            print(f"  ... and {len(label_mismatches) - 10} more")
        print()

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as fh:
        for r in out_records:
            fh.write(json.dumps(r) + "\n")

    print(f"\nWrote {len(out_records)} records to {OUTPUT_PATH.name}")
    print(f"\nConsensus split:")
    print(f"  consensus : {counts.get('consensus', 0):4d}  ({counts.get('consensus', 0)/len(out_records)*100:.1f}%)")
    print(f"  contested : {counts.get('contested', 0):4d}  ({counts.get('contested', 0)/len(out_records)*100:.1f}%)")
    if counts.get("split", 0):
        print(f"  split     : {counts.get('split', 0):4d}")

    # Verify against expected live numbers
    ok_consensus = counts.get("consensus", 0) == EXPECTED_CONSENSUS
    ok_contested = counts.get("contested", 0) == EXPECTED_CONTESTED
    if ok_consensus and ok_contested:
        print(f"\n✓ Matches live Stage 2 numbers (205 consensus / 378 contested).")
    else:
        print(f"\n✗ MISMATCH vs live numbers (expected {EXPECTED_CONSENSUS}/{EXPECTED_CONTESTED}).", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
