"""
Topology Probe — Proof of Concept

Tests "conceptual topology probing": can models classify text chunks into
cognitive categories at different clarity levels, and does their reasoning
reflect the actual content or surface-level pattern matching?

8 probes × 4 Granite 4.1 variants × 2 calls (classification + reasoning) = 64 calls.
Expected runtime: ~10-15 minutes including model swap overhead.

Usage:
    cd ~/Projects/cerebra
    python scripts/v02_training/topology_probe.py

Output:
    scripts/v02_training/output/topology_probe_results.jsonl

Resumable: already-processed (probe_id, model) pairs are skipped on restart.

Methodological notes:
- Classification and reasoning are separate calls (not combined) to avoid
  post-hoc reasoning shaped during generation. Model commits first, explains after.
- Reasoning is captured for ALL probes regardless of match/mismatch. Asymmetric
  capture (reasoning only on wrong answers) would introduce a confound — you
  can't compare reasoning shape between right and wrong answers.
- Reasoning prompt is neutral: asks the model to explain its choice, not to
  justify or defend it. Evaluative framing shifts behavior into performative mode.
"""

from __future__ import annotations

import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cerebra.cognition.llm_adapter import OllamaDirectAdapter, ClassificationError

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
TIMEOUT_SECONDS = 300
REASONING_MAX_TOKENS = 500

OUTPUT_PATH = Path(__file__).parent / "output/topology_probe_results.jsonl"

# Sequential — no parallel execution across models (VRAM pressure)
MODELS = [
    (
        "huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M",
        "granite-4.1-3b",
    ),
    (
        "hf.co/mradermacher/granite-4.1-3b-Abliterated-AND-Disinhibited-GGUF:Q8_0",
        "granite-4.1-3b-abliterated",
    ),
    (
        "huggingface.co/unsloth/granite-4.1-8b-GGUF:Q4_K_M",
        "granite-4.1-8b",
    ),
    (
        "hf.co/mradermacher/Granite-4.1-8B-SFT-Claude-Opus-Reasoning-Unsloth-GGUF:Q6_K",
        "granite-4.1-8b-sft-claude",
    ),
]

# Final 8 probes — user-approved corpus (Phase 2)
# 4 categories × 2 clarity levels (L2 strong fit, L4 weak fit)
CORPUS = [
    {
        "probe_id": "design_l2_001",
        "expected_d1": "DESIGN",
        "expected_level": 2,
        "chunk_content": (
            "The registry is the authoritative source of truth for all active panel types. "
            "No component discovers available panels by importing them directly; instead, each "
            "panel registers itself at load time, and consumers query the registry at runtime. "
            "This means adding a new panel type requires only a single registration — no consumer "
            "needs to be updated. The registry's structure also serves as the contract: any object "
            "satisfying the registration interface is a valid panel, regardless of its "
            "implementation. Hardcoded panel lists are explicitly prohibited because they create "
            "a parallel taxonomy that diverges from the registry over time."
        ),
    },
    {
        "probe_id": "design_l4_001",
        "expected_d1": "DESIGN",
        "expected_level": 4,
        "chunk_content": (
            "When a component needs to communicate a state change to other parts of the system, "
            "it emits a typed signal rather than calling a function directly. The signal carries "
            "a payload; receivers subscribe independently. This decouples the emitter from knowing "
            "which receivers exist, and allows receivers to be added or removed without modifying "
            "the emitter. The same pattern applies at the graph layer: when the graph topology "
            "changes, the layout engine receives a signal rather than being called directly. In "
            "practice this means the emitter and the layout engine can evolve on separate schedules."
        ),
    },
    {
        "probe_id": "mechanism_l2_001",
        "expected_d1": "MECHANISM",
        "expected_level": 2,
        "chunk_content": (
            "The physics layout runs on each animation frame. At each frame, the engine reads "
            "the current node positions and applies three force terms: a spring force pulling "
            "connected nodes toward their preferred separation distance, a repulsion force pushing "
            "all nodes apart, and a drag term reducing velocity proportional to current speed. "
            "After summing the forces, the engine updates each node's position by multiplying "
            "velocity by the frame delta. Nodes pinned by the user are exempt from force "
            "application but still affect other nodes through the spring term."
        ),
    },
    {
        "probe_id": "mechanism_l4_001",
        "expected_d1": "MECHANISM",
        "expected_level": 4,
        "chunk_content": (
            "When two nodes are merged, the system resolves their edges before removing the "
            "source node. Any edges pointing to the source are redirected to the target. Any "
            "edges pointing from the source are duplicated onto the target, except for edges "
            "that would create a self-loop. After edge resolution, the source node is removed "
            "from the node collection and its identifier is added to a tombstone list. Components "
            "holding a reference to the old identifier will receive a null on lookup rather than "
            "an error."
        ),
    },
    {
        "probe_id": "principle_l2_001",
        "expected_d1": "PRINCIPLE",
        "expected_level": 2,
        "chunk_content": (
            "A fix must never be committed before the failure has been confirmed. Diagnosing "
            "from a hypothesis and patching from that diagnosis without verifying the diagnosis "
            "first is how fixes that 'should work' create new failures. The cost of a "
            "false-positive diagnosis — time spent on a wrong fix — is always higher than the "
            "cost of running the diagnostic steps that would have ruled it out. Confirm the "
            "failure is real. Confirm the mechanism that causes it. Then write the fix."
        ),
    },
    {
        "probe_id": "principle_l4_001",
        "expected_d1": "PRINCIPLE",
        "expected_level": 4,
        "chunk_content": (
            "When it is not clear whether a new piece of state belongs in local component state "
            "or in the global store, the default should be local. Moving state from local to "
            "global is easy. Moving state from global to local is harder — it requires identifying "
            "all consumers, verifying none of them need the state to survive remounts, and "
            "removing the global store entry without breaking any consumers. The asymmetry means "
            "the cost of choosing global when local would have sufficed is higher than the cost "
            "of choosing local when global turns out to be needed."
        ),
    },
    {
        "probe_id": "observation_l2_001",
        "expected_d1": "OBSERVATION",
        "expected_level": 2,
        "chunk_content": (
            "In load testing across twelve deployments, cold-start latency for containerized "
            "services ranged from 800ms to 14 seconds depending on image size and memory "
            "allocation. Services under 200MB consistently cold-started under 2 seconds. Services "
            "over 800MB showed high variance — median cold-start around 8 seconds but with a "
            "long tail above 12 seconds on instances with memory pressure from other containers. "
            "Warm instances showed no such variance: response times on warm containers were "
            "stable within 50ms of each other regardless of image size. The cold/warm latency "
            "gap was the dominant performance variable, larger than any difference between "
            "request types or payload sizes."
        ),
    },
    {
        "probe_id": "observation_l4_001",
        "expected_d1": "OBSERVATION",
        "expected_level": 4,
        "chunk_content": (
            "Models trained primarily on instruction-following data tend to report higher "
            "confidence on ambiguous inputs than models trained on reasoning-heavy data. In the "
            "calibration runs, instruction-tuned models averaged 0.85-0.90 confidence on hard "
            "fixtures regardless of whether they were right or wrong. Reasoning-trained models "
            "averaged 0.65-0.75 on the same fixtures, with a more pronounced gap between correct "
            "(higher confidence) and incorrect (lower confidence) predictions. The "
            "reasoning-trained models' confidence was better calibrated even though their overall "
            "accuracy was similar."
        ),
    },
]


def _call_ollama_reasoning(
    model_tag: str, chunk: str, predicted_d1: str
) -> tuple[str, float]:
    """
    Plain-text reasoning call — no format:json, capped at REASONING_MAX_TOKENS.

    Neutral framing: asks model to explain its choice, not to defend or justify it.
    Returns (reasoning_text, latency_s). Raises ClassificationError on failure.
    """
    system_msg = (
        "You previously classified the following text chunk into a category. "
        "Now explain your reasoning in 2-3 sentences. Focus on what specifically "
        "in the chunk content led to your category choice."
    )
    user_msg = (
        f"Chunk content:\n{chunk}\n\n"
        f"Your classification was: {predicted_d1}\n\n"
        f"Explain in 2-3 sentences why you chose {predicted_d1}."
    )
    body = json.dumps(
        {
            "model": model_tag,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.0,
                "num_predict": REASONING_MAX_TOKENS,
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latency = time.monotonic() - t0
            return data["message"]["content"].strip(), latency
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ClassificationError(f"Ollama HTTP {e.code}: {error_body[:300]}") from e
    except urllib.error.URLError as e:
        raise ClassificationError(f"Ollama unreachable: {e.reason}") from e


def _load_completed() -> set[tuple[str, str]]:
    """Return (probe_id, model_label) pairs already in the output file."""
    if not OUTPUT_PATH.exists():
        return set()
    completed: set[tuple[str, str]] = set()
    for line in OUTPUT_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            completed.add((rec["probe_id"], rec["model"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return completed


def _append_result(result: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("a") as fh:
        fh.write(json.dumps(result) + "\n")


def _print_summary(all_results: list[dict]) -> None:
    n_probes = len(CORPUS)
    n_models = len(MODELS)
    print(
        f"\nTopology probe complete. "
        f"{n_probes} probes × {n_models} models = {n_probes * n_models} probe runs.\n"
    )

    print("Match rate by model:")
    for _, label in MODELS:
        rows = [r for r in all_results if r["model"] == label]
        matched = sum(1 for r in rows if r.get("match") is True)
        total = len(rows)
        pct = matched * 100 // total if total else 0
        print(f"  {label:<38s}  {matched}/{total}  ({pct}%)")

    print("\nMatch rate by clarity level:")
    for level, label in [(2, "L2 (strong)"), (4, "L4 (weak  )")]:
        rows = [r for r in all_results if r.get("expected_level") == level]
        matched = sum(1 for r in rows if r.get("match") is True)
        total = len(rows)
        pct = matched * 100 // total if total else 0
        print(f"  {label}:  {matched}/{total}  ({pct}%)")


def main() -> None:
    completed = _load_completed()
    total_pairs = len(CORPUS) * len(MODELS)

    if completed:
        print(f"Resuming: {len(completed)}/{total_pairs} pairs already done, skipping.")

    for model_idx, (model_tag, model_label) in enumerate(MODELS):
        probes = list(CORPUS)
        random.Random(model_idx).shuffle(probes)

        pending = [p for p in probes if (p["probe_id"], model_label) not in completed]
        if not pending:
            print(f"\n[{model_label}] all probes already done, skipping.")
            continue

        print(f"\n[{model_label}] {len(pending)} probe(s) to run...")
        adapter = OllamaDirectAdapter(model=model_tag, temperature=0.0, timeout=TIMEOUT_SECONDS)

        for probe in pending:
            pid = probe["probe_id"]
            chunk = probe["chunk_content"]
            expected = probe["expected_d1"]

            print(f"  {pid} ... ", end="", flush=True)

            # — Pass 1 + Pass 2 classification —
            predicted_d1: str | None = None
            confidence: float | None = None
            pass1_quadrant: str | None = None
            pass1_scores: dict | None = None
            pass2_scores: dict | None = None
            classification_latency_s: float = 0.0
            classification_error: str | None = None

            t0 = time.monotonic()
            try:
                pass1 = adapter.classify_quadrant(chunk)
                pass1_quadrant = pass1.primary
                pass1_scores = pass1.scores

                pass2 = adapter.classify_within_quadrant(chunk, pass1.primary)
                predicted_d1 = pass2.primary
                confidence = pass2.confidence
                pass2_scores = pass2.scores
            except ClassificationError as e:
                classification_error = str(e)[:300]
            finally:
                classification_latency_s = round(time.monotonic() - t0, 3)

            match: bool | None = (predicted_d1 == expected) if predicted_d1 is not None else None

            # — Reasoning call (all probes, regardless of match) —
            reasoning_text: str | None = None
            reasoning_latency_s: float | None = None
            reasoning_error: str | None = None

            if predicted_d1 is not None:
                try:
                    reasoning_text, _lat = _call_ollama_reasoning(model_tag, chunk, predicted_d1)
                    reasoning_latency_s = round(_lat, 3)
                except ClassificationError as e:
                    reasoning_error = str(e)[:300]
            else:
                reasoning_error = "skipped: classification failed"

            # — Progress line —
            sym = "✓" if match is True else ("✗" if match is False else "?")
            conf_s = f"{confidence:.2f}" if confidence is not None else "n/a"
            r_s = f"{reasoning_latency_s:.1f}s" if reasoning_latency_s is not None else "fail"
            print(
                f"{sym}  got={predicted_d1 or 'FAIL':<13s}  "
                f"conf={conf_s}  "
                f"class={classification_latency_s:.1f}s  "
                f"reason={r_s}"
            )
            if classification_error:
                print(f"    [classification error] {classification_error}")
            if reasoning_error and reasoning_error != "skipped: classification failed":
                print(f"    [reasoning error] {reasoning_error}")

            _append_result(
                {
                    "probe_id": pid,
                    "expected_d1": expected,
                    "expected_level": probe["expected_level"],
                    "chunk_content": chunk,
                    "model": model_label,
                    "predicted_d1": predicted_d1,
                    "match": match,
                    "confidence": confidence,
                    "pass1_quadrant": pass1_quadrant,
                    "pass1_scores": pass1_scores,
                    "pass2_scores": pass2_scores,
                    "reasoning": reasoning_text,
                    "classification_latency_s": classification_latency_s,
                    "reasoning_latency_s": reasoning_latency_s,
                    "classification_error": classification_error,
                    "reasoning_error": reasoning_error,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            completed.add((pid, model_label))

    # — Final summary —
    if not OUTPUT_PATH.exists():
        print("\nNo results written.")
        return

    all_results = [
        json.loads(line)
        for line in OUTPUT_PATH.read_text().splitlines()
        if line.strip()
    ]
    _print_summary(all_results)


if __name__ == "__main__":
    main()
