# Cerebra — Prediction and Evaluation

## 1. Purpose

Cerebra should not only store what happened. It should record what it expected to happen and measure the gap.

That gap becomes a learning signal.

---

## 2. Core Doctrine

Prediction/evaluation should be:

```text
component-based
traceable
task-aware
non-mystical
source-grounded where possible
useful for control
useful for consolidation
```

Prediction is an engineering tool, not a claim of consciousness.

---

## 3. Why Prediction Matters

Without prediction, Cerebra reacts.

With prediction, Cerebra can learn from expectation gaps.

Examples:

```text
expected output coherence was high, actual score was low
expected retrieval relevance was high, user ignored context
expected refinement to improve output, but it reduced novelty
expected no contradiction, but contradiction was found
```

---

## 4. Prediction Types

Initial prediction types:

```text
output_quality
retrieval_usefulness
goal_alignment
coherence
novelty
user_acceptance
need_for_consolidation
risk_of_goal_drift
contradiction_likelihood
```

---

## 5. Prediction Record

Example:

```json
{
  "prediction_id": "pred_123",
  "session_id": "sess_123",
  "cycle_id": "cycle_123",
  "step_id": "step_456",
  "prediction_type": "output_quality",
  "expected": 0.78,
  "confidence": 0.72,
  "basis": [
    "high context relevance",
    "similar prior cycle succeeded"
  ],
  "created_at": 1710000000
}
```

---

## 6. Outcome Record

Example:

```json
{
  "outcome_id": "out_123",
  "prediction_id": "pred_123",
  "actual": 0.54,
  "measured_by": "signal_pipeline",
  "evidence": [
    "low coherence metric",
    "clutch requested refinement"
  ],
  "created_at": 1710000040
}
```

---

## 7. Prediction Error

```text
prediction_error = actual - expected
absolute_error = abs(actual - expected)
```

Preserve components and interpretation.

Example:

```json
{
  "prediction_error_id": "perr_123",
  "prediction_id": "pred_123",
  "expected": 0.78,
  "actual": 0.54,
  "delta": -0.24,
  "absolute_error": 0.24,
  "interpretation": "overestimated output quality"
}
```

---

## 8. Signal Pipeline

Evaluation signals may include:

```text
coherence
specificity
novelty
utility
goal_alignment
contradiction
retrieval_fit
source_support
confidence
progress_delta
```

Signals should remain componentized.

---

## 9. Evaluation Packet

Each runtime step should produce an evaluation packet.

```json
{
  "evaluation_id": "eval_123",
  "step_id": "step_123",
  "signals": {
    "coherence": 0.72,
    "novelty": 0.61,
    "goal_alignment": 0.84,
    "source_support": 0.77
  },
  "composite": 0.74,
  "confidence": 0.70,
  "notes": []
}
```

The composite is a summary.

Signals are the source of truth.

---

## 10. Control Use

Prediction error can influence:

```text
clutch action
retrieval strategy
catalyst strategy weights
working memory attention
consolidation priority
cycle stop/continue decisions
```

Example:

```text
large negative prediction error on retrieval usefulness
  -> broaden retrieval next time
  -> lower salience for similar source cluster
```

---

## 11. Consolidation Use

Prediction errors should be consolidated.

Patterns to detect:

```text
Cerebra often overestimates refinement quality.
Certain source types produce poor retrieval usefulness.
Goal drift follows long exploration cycles.
Certain catalyst strategies work better for planning tasks.
```

These become procedural or predictive memory.

---

## 12. MVP Scope

Cerebra v0.1 should support:

```text
prediction records
outcome records
prediction error calculation
evaluation packet with component signals
basic use in clutch/controller
graph event emission
```

Do not build advanced learned prediction models in v0.1.

Start deterministic.

---

## 13. Prediction Doctrine

Prediction gives Cerebra a way to improve without pretending to be alive.

It is simply this:

```text
I expected X.
Y happened.
The gap matters.
Update future behavior.
```
