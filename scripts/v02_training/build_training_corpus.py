"""
Build v0.2 LoRA training corpus using Path A-lite rules (no Stage 3 review).

Reads stage2_consensus.jsonl, applies:
  Rule 1 — consensus records (≥2 Stage 2 models agree with v0.1.0 label)
           → include with v0.1.0 label as ground truth
  Rule 2 — unanimous disagreement (all 3 Stage 2 models pick same non-v0.1.0 label)
           → include with Stage 2 unanimous label as corrected ground truth
  Rule 3 — contested/split → exclude

Constructs Pass 1 + Pass 2 JSONL training pairs, applies class balancing weights,
splits into train/val/test, and runs hygiene checks.

Usage:
    cd /home/boop/Projects/cerebra
    python scripts/v02_training/build_training_corpus.py [--output-dir PATH]

Output:
    output/corpus/pass1_train.jsonl
    output/corpus/pass1_val.jsonl
    output/corpus/pass1_test.jsonl
    output/corpus/pass2_train.jsonl
    output/corpus/pass2_val.jsonl
    output/corpus/pass2_test.jsonl
    output/corpus/class_weights.json
    output/corpus/split_manifest.json

The training JSONL format (for Unsloth):
    {"prompt": "<prompt text>", "completion": "<expected JSON output>"}
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cerebra.cognition.sku_classifier import _build_pass1_prompt, _build_pass2_prompt

STAGE2_CONSENSUS_PATH = Path(__file__).parent / "output/stage2_consensus.jsonl"

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
# Within-quadrant D1 sets
QUADRANT_D1 = {
    "EMPIRICAL":   [0, 1, 2, 3],
    "GENERATIVE":  [4, 5, 6, 7],
    "NORMATIVE":   [8, 9, 10, 11],
    "RELATIONAL":  [12, 13, 14, 15],
}
D1_BY_NAME = {v: k for k, v in D1_NAMES.items()}

# EOS verified: granite-4.1-3b-base tokenizer.eos_token == '<|end_of_text|>' (id=100257)
_EOS = "<|end_of_text|>"


def load_path_a_lite(path: Path) -> tuple[list[dict], dict]:
    """
    Load records from stage2_consensus.jsonl and apply Path A-lite selection rules.
    Returns (records, stats_dict).

    Rule 1 — consensus (stage2_consensus == 'consensus'):
        Include with v0.1.0 d1_name as ground truth.
    Rule 2 — unanimous disagreement (all 3 votes same non-v0.1.0 label):
        Include with corrected label. Updates d1_name, d1, quadrant in-place.
    Rule 3 — contested/split:
        Exclude.
    """
    records_raw = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    included_r1: list[dict] = []
    included_r2: list[dict] = []
    excluded = 0

    for r in records_raw:
        if r.get("stage2_consensus") == "consensus":
            included_r1.append(r)
            continue

        votes = list(r.get("stage2_votes", {}).values())
        valid_votes = [v for v in votes if v]
        if (len(valid_votes) == 3
                and len(set(valid_votes)) == 1
                and valid_votes[0] != r["d1_name"]):
            corrected = dict(r)
            unanimous_label = valid_votes[0]
            corrected["d1_name"] = unanimous_label
            new_d1 = D1_BY_NAME.get(unanimous_label, r["d1"])
            corrected["d1"] = new_d1
            corrected["quadrant"] = D1_QUADRANT[new_d1]
            included_r2.append(corrected)
            continue

        excluded += 1

    stats = {"rule1": len(included_r1), "rule2": len(included_r2), "excluded": excluded}

    print(f"\nPath A-lite corpus construction:")
    print(f"  Rule 1 (consensus, v0.1.0 label kept):        {len(included_r1):4d}")
    print(f"  Rule 2 (unanimous correction, label changed): {len(included_r2):4d}")
    print(f"  Rule 3 (excluded — contested/split):          {excluded:4d}")
    print(f"  Total included: {len(included_r1) + len(included_r2)}")

    return included_r1 + included_r2, stats


def compute_class_weights(records: list[dict]) -> dict[str, float]:
    """Inverse-frequency class weights, normalized so mean weight = 1."""
    counts: dict[str, int] = defaultdict(int)
    for r in records:
        counts[r["d1_name"]] += 1
    total = len(records)
    raw_weights = {cat: total / count for cat, count in counts.items()}
    mean_w = sum(raw_weights.values()) / len(raw_weights)
    return {cat: w / mean_w for cat, w in raw_weights.items()}


def stratified_split(records: list[dict], train_frac: float = 0.80, val_frac: float = 0.10,
                     seed: int = 42) -> tuple[list, list, list]:
    """Stratify by D1 category. Returns (train, val, test)."""
    rng = random.Random(seed)
    by_category: dict[str, list] = defaultdict(list)
    for r in records:
        by_category[r["d1_name"]].append(r)

    train, val, test = [], [], []
    for cat, group in by_category.items():
        rng.shuffle(group)
        n = len(group)
        n_val = max(1, math.floor(n * val_frac))
        n_test = max(1, math.floor(n * (1 - train_frac - val_frac)))
        n_train = n - n_val - n_test
        train.extend(group[:n_train])
        val.extend(group[n_train:n_train + n_val])
        test.extend(group[n_train + n_val:])

    rng.shuffle(train)
    rng.shuffle(val)
    rng.shuffle(test)
    return train, val, test


def build_pass1_pair(record: dict) -> dict:
    """Build a Pass 1 training example. Completion is the expected quadrant JSON."""
    prompt = _build_pass1_prompt(record["content"])
    pass1_data = record.get("raw_scores_pass1", {})

    # Reconstruct expected completion from stored pass1 scores
    quadrant = record["quadrant"]
    scores = pass1_data.get("scores", {})
    if not scores:
        # Reconstruct a minimal valid completion if scores aren't available
        scores = {"EMPIRICAL": 0.0, "GENERATIVE": 0.0, "NORMATIVE": 0.0, "RELATIONAL": 0.0}
        scores[quadrant] = 1.0

    completion = json.dumps({
        "scores": scores,
        "confidence": pass1_data.get("confidence", record["d1_confidence"]),
        "primary": quadrant,
    }) + _EOS
    return {"prompt": prompt, "completion": completion, "record_id": record["record_id"],
            "d1_name": record["d1_name"]}


def build_pass2_pair(record: dict) -> dict:
    """Build a Pass 2 training example. Completion is the expected D1 category JSON."""
    quadrant = record["quadrant"]
    prompt = _build_pass2_prompt(record["content"], quadrant)
    pass2_data = record.get("raw_scores_pass2", {})

    d1_name = record["d1_name"]
    scores = pass2_data.get("scores", {})
    if not scores:
        # Only include the 4 quadrant members — must match the pass2 prompt format
        quad_members = [D1_NAMES[i] for i in QUADRANT_D1[quadrant]]
        scores = {cat: 0.0 for cat in quad_members}
        scores[d1_name] = 1.0

    completion = json.dumps({
        "scores": scores,
        "confidence": record["d1_confidence"],
        "primary": d1_name,
        "reasoning": f"This excerpt is best classified as {d1_name} within the {quadrant} quadrant.",
    }) + _EOS
    return {"prompt": prompt, "completion": completion, "record_id": record["record_id"],
            "d1_name": record["d1_name"]}


def hygiene_checks(train: list, val: list, test: list,
                   calibration_hashes: set[int] | None = None) -> bool:
    """Check for data leakage and missing categories. Returns True if clean."""
    ok = True

    train_ids = {r["record_id"] for r in train}
    val_ids = {r["record_id"] for r in val}
    test_ids = {r["record_id"] for r in test}
    overlaps = (train_ids & val_ids) | (train_ids & test_ids) | (val_ids & test_ids)
    if overlaps:
        print(f"  ERROR: {len(overlaps)} record IDs appear in multiple splits!")
        ok = False
    else:
        print("  ✓ No record ID overlap between splits")

    train_hashes = {hash(r["content"]) for r in train}
    for split_name, split in [("val", val), ("test", test)]:
        near_dups = [r for r in split if hash(r["content"]) in train_hashes]
        if near_dups:
            print(f"  WARNING: {len(near_dups)} near-duplicate contents in {split_name}")
        else:
            print(f"  ✓ No content duplicates between train and {split_name}")

    if calibration_hashes:
        all_splits = [("train", train), ("val", val), ("test", test)]
        for split_name, split in all_splits:
            leaks = [r for r in split if hash(r["content"].strip()) in calibration_hashes]
            if leaks:
                print(f"  ERROR: {len(leaks)} calibration fixture(s) found in {split_name}!")
                ok = False
            else:
                print(f"  ✓ No calibration fixtures in {split_name}")

    for split_name, split in [("train", train), ("val", val), ("test", test)]:
        cats = {r["d1_name"] for r in split}
        missing = set(D1_NAMES.values()) - cats - {"AGENT"}  # AGENT absent from corpus
        if missing:
            print(f"  WARNING: {split_name} missing categories: {missing}")
        else:
            print(f"  ✓ {split_name}: all expected categories present")

    return ok


def write_jsonl(pairs: list[dict], path: Path) -> None:
    with path.open("w") as fh:
        for pair in pairs:
            fh.write(json.dumps({
                "prompt": pair["prompt"],
                "completion": pair["completion"],
                "d1_name": pair["d1_name"],
            }) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "output/corpus")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not STAGE2_CONSENSUS_PATH.exists():
        print(f"ERROR: {STAGE2_CONSENSUS_PATH} not found. Run recover_stage2.py first.")
        sys.exit(1)

    print(f"\nLoading stage2_consensus.jsonl from: {STAGE2_CONSENSUS_PATH}")
    records, corpus_stats = load_path_a_lite(STAGE2_CONSENSUS_PATH)

    if not records:
        print("ERROR: No records survived Path A-lite selection.")
        sys.exit(1)

    print(f"\nPath A-lite corpus: {len(records)} records")

    # ── Calibration fixture hashes (must not appear in training) ──────────────
    calibration_hashes: set[int] = set()
    try:
        from tests.fixtures.sku_fixtures import SKU_FIXTURES
        calibration_hashes = {hash(f.content.strip()) for f in SKU_FIXTURES}
        print(f"Loaded {len(calibration_hashes)} calibration fixture hashes for hygiene check.")
    except ImportError:
        print("WARNING: Could not import SKU_FIXTURES — calibration fixture check skipped.")

    # ── Class weights ─────────────────────────────────────────────────────────
    weights = compute_class_weights(records)
    print("\nClass weights (inverse-frequency, normalized):")
    for cat, w in sorted(weights.items(), key=lambda x: -x[1]):
        count = sum(1 for r in records if r["d1_name"] == cat)
        print(f"  {cat:12s}: {count:4d} records  weight={w:.2f}")

    # ── Train/val/test split ───────────────────────────────────────────────────
    train, val, test = stratified_split(records, seed=args.seed)
    print(f"\nSplit (stratified by D1 category):")
    print(f"  train: {len(train)} ({len(train)*100/len(records):.0f}%)")
    print(f"  val:   {len(val)} ({len(val)*100/len(records):.0f}%)")
    print(f"  test:  {len(test)} ({len(test)*100/len(records):.0f}%)")

    # ── Hygiene checks ────────────────────────────────────────────────────────
    print("\nHygiene checks:")
    clean = hygiene_checks(train, val, test,
                           calibration_hashes=calibration_hashes or None)
    if not clean:
        print("\nFix hygiene issues before training. Exiting.")
        sys.exit(1)

    # ── Build JSONL pairs ─────────────────────────────────────────────────────
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for split_name, split in [("train", train), ("val", val), ("test", test)]:
        p1_pairs = [build_pass1_pair(r) for r in split]
        p2_pairs = [build_pass2_pair(r) for r in split]
        write_jsonl(p1_pairs, args.output_dir / f"pass1_{split_name}.jsonl")
        write_jsonl(p2_pairs, args.output_dir / f"pass2_{split_name}.jsonl")
        print(f"  {split_name}: {len(p1_pairs)} Pass 1 pairs + {len(p2_pairs)} Pass 2 pairs written")

    # ── Manifest ──────────────────────────────────────────────────────────────
    manifest = {
        "corpus_rule": "path_a_lite",
        "rule1_consensus": corpus_stats["rule1"],
        "rule2_unanimous_correction": corpus_stats["rule2"],
        "rule3_excluded": corpus_stats["excluded"],
        "total_included": len(records),
        "splits": {"train": len(train), "val": len(val), "test": len(test)},
        "total_pairs": len(records) * 2,  # pass1 + pass2 per record
        "class_weights": weights,
        "seed": args.seed,
        "absent_from_corpus": ["AGENT"],
    }
    (args.output_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2))
    (args.output_dir / "class_weights.json").write_text(json.dumps(weights, indent=2))

    print(f"\nCorpus written to: {args.output_dir}")
    print(f"Total JSONL pairs: {len(records) * 2} (Pass 1 + Pass 2)")
    print("\nNext step: run Unsloth QLoRA training using the Pass 1 + Pass 2 JSONL files.")


if __name__ == "__main__":
    main()
