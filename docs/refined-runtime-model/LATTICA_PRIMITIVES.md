# Lattica — Shared Primitives Reference

## 1. Purpose

This document specifies the small set of pure primitives that are intended to be reused across the Lattica suite (Cerebra, LumaWeave, Policy Scout, Bons.ai as a cycle config).

Per the project independence doctrine, Lattica projects do not have runtime dependencies on each other. This is a hard rule.

The primitives below are the sanctioned exception. They are small, stable, conservative, and useful enough that the duplication cost across projects exceeds the dependency cost. Initially they are *vendored* into each project — copied into a `_primitives/` directory, not imported from a shared package. When two real consumers have used them in production for some time and the primitives have stabilized, they will be extracted into `lattica-primitives` as a real Python package.

This doc serves three purposes:

```text
1. Establishes which primitives qualify for vendoring
2. Specifies the canonical implementation contracts
3. Documents the eventual extraction plan
```

---

## 2. Core Doctrine

Lattica primitives should be:

```text
small (< 200 lines each, ideally < 100)
pure or near-pure (no I/O, minimal state)
stateless or with simple state
dependency-free (no external libraries beyond stdlib)
language-portable (concept translates to other languages cleanly)
stable (interface doesn't churn)
conservative (added only when reuse is proven)
documented as if they were already external
```

A primitive that needs even one external dependency is not Lattica-primitive material. A primitive that has interface churn after 3 months in production is too unstable.

---

## 3. The Six Initial Primitives

Six primitives have demonstrated reuse potential across at least two Lattica projects.

### 3.1 Clutch

A priority-rule control function. Pure function from typed signal bundle to typed control action via priority-ordered cascade of guarded rules, with explanation as a first-class output.

```text
Used by: Bons.ai (cycle control), Policy Scout (enforcement mode routing),
         Cerebra (cycle runtime control valve)
Stability: high; pattern has held across two distinct domains already
```

See full specification in §6.

### 3.2 Signal Triangulator

Combines a raw score with a confidence multiplier and signal-strength multiplier to produce a triangulated reward.

```text
reward = score × confidence × signal_strength

Used by: Bons.ai (reward computation), Cerebra (signal pipeline),
         Policy Scout (risk score triangulation)
Stability: high; ubiquitous pattern
```

See full specification in §7.

### 3.3 Trajectory Tracker

Maintains rolling delta history, computes smoothed trend, labels trajectory state, tracks failure streak. Pure-ish (has bounded internal state).

```text
Used by: Bons.ai (cycle dynamics), Cerebra (signal evolution),
         Policy Scout (incident-trajectory tracking)
Stability: high
```

See full specification in §8.

### 3.4 Hysteresis Mode Router

Mode-persistence with minimum duration and emergency-override.

```text
Used by: Bons.ai (cognitive_router), Policy Scout (clutch mode routing),
         Cerebra (will need it for cycle mode selection)
Stability: high
```

See full specification in §9.

### 3.5 Component Score Composer

Multi-component scoring with named weights, normalized output, preserved components ("don't collapse early" doctrine).

```text
Used by: Bons.ai (scoring), Cerebra (salience scoring + signal composition),
         Policy Scout (risk component composition)
Stability: high; the pattern is identical across all three uses
```

See full specification in §10.

### 3.6 Tombstone-Aware Set

A set with three states per item: present, tombstoned, absent. Tombstoned items don't return but block re-insertion of identical items unless explicit restore.

```text
Used by: Cerebra (memory lifecycle), Policy Scout (revoked approval semantics)
Stability: medium; less proven than the other five but pattern is clean
```

See full specification in §11.

---

## 4. Vendoring Discipline

While in vendor mode (pre-extraction):

```text
Each Lattica project has a _primitives/ directory inside its package
The directory contains a verbatim copy of the canonical implementation
The directory has a VENDORED_FROM.md file noting:
  - which canonical version this was copied from
  - the date copied
  - any project-specific modifications (should be none; if needed,
    they are flagged and the canonical version should be updated)
```

When a primitive is improved, the improvement is applied to the canonical reference and then re-vendored to each project. The canonical reference lives initially in a Cerebra subdirectory (`cerebra/_primitives_canonical/`); when extraction happens, the canonical reference becomes the published package.

This discipline avoids the "pip package with one consumer" trap while still maintaining single-source-of-truth for the primitives.

---

## 5. Extraction Criteria

A primitive moves from vendor mode to published package when:

```text
1. Two or more Lattica projects have been using it in production for 90+ days
2. No interface changes have been needed in the last 30 days
3. At least one external (non-Lattica) developer has expressed interest in using it
4. The maintenance burden of vendoring exceeds the cost of a small published package
```

When extraction happens:

```text
lattica-primitives package published to PyPI
Canonical reference moves to its own repo
Each Lattica project's _primitives/ directory is removed
Each Lattica project depends on lattica-primitives>=X.Y.Z
Semver discipline begins
```

Estimated timeline: 9-12 months from Cerebra v0.1 ship.

---

## 6. Clutch Specification

```python
# lattica/_primitives/clutch.py
"""
Priority-rule controller for cognitive or operational decisions.

A clutch maps signal state to typed action via priority-ordered cascade.
First matching rule wins. Explanation is part of the return type.
"""

from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class Decision:
    action: str           # action identifier
    intensity: str | None # optional intensity tag
    reason: str           # human-readable explanation
    confidence: float     # 0-1 confidence in this decision
    metadata: dict        # additional context (e.g. cooldown, hysteresis state)


@dataclass
class Rule:
    name: str
    guard: Callable[[dict, dict], bool]  # (signals, state) -> bool
    action: Decision | Callable[[dict, dict], Decision]


class Clutch:
    """Priority-ordered rule cascade with explainable output."""
    
    def __init__(self, rules: list[Rule], default: Decision):
        self.rules = rules
        self.default = default
    
    def decide(self, signals: dict, state: dict) -> Decision:
        for rule in self.rules:
            if rule.guard(signals, state):
                action = rule.action
                return action(signals, state) if callable(action) else action
        return self.default
    
    def explain(self, signals: dict, state: dict) -> list[dict]:
        """Return per-rule firing trace for inspector."""
        trace = []
        for rule in self.rules:
            fired = rule.guard(signals, state)
            trace.append({"rule": rule.name, "fired": fired})
            if fired:
                break
        return trace
```

Approximately 50 lines. No external dependencies. Pure function over inputs.

---

## 7. Signal Triangulator Specification

```python
# lattica/_primitives/triangulator.py
"""
Triangulates a raw score with confidence and signal-strength multipliers.

The composition: reward = score × confidence × signal_strength
"""

def triangulate(score: float, confidence: float, signal_strength: float,
                clamp_lo: float = 0.0, clamp_hi: float = 1.2) -> float:
    """
    Args:
        score: raw composite score, typically [0, 1]
        confidence: confidence in the scoring, [0, 1]
        signal_strength: strength of underlying signal, [0, 1]
        clamp_lo: lower clamp (default 0.0)
        clamp_hi: upper clamp (default 1.2 — allows positive shaping bonuses)
    
    Returns:
        Triangulated reward in [clamp_lo, clamp_hi]
    """
    reward = score * confidence * signal_strength
    return max(clamp_lo, min(clamp_hi, reward))


def triangulate_with_components(score: float, confidence: float, 
                                 signal_strength: float) -> dict:
    """Variant that returns components alongside reward for inspection."""
    return {
        "score": score,
        "confidence": confidence,
        "signal_strength": signal_strength,
        "reward": triangulate(score, confidence, signal_strength),
    }
```

Approximately 25 lines. Stateless. Used wherever score-confidence-signal triangulation matters.

---

## 8. Trajectory Tracker Specification

```python
# lattica/_primitives/trajectory.py
"""
Maintains rolling delta history, derives smoothed trend and trajectory label,
tracks failure streak.
"""

from collections import deque
from dataclasses import dataclass


@dataclass
class TrajectoryState:
    trend: float                # smoothed trend over recent window
    label: str                  # 'improving' | 'flat' | 'degrading'
    failure_streak: int         # consecutive low-composite cycles
    delta_history: list[float]  # rolling history for inspection


class TrajectoryTracker:
    def __init__(self, history_cap: int = 20, trend_window: int = 3,
                 failure_threshold: float = 5.0,
                 improving_threshold: float = 0.05,
                 degrading_threshold: float = -0.05):
        self.history = deque(maxlen=history_cap)
        self.trend_window = trend_window
        self.failure_threshold = failure_threshold
        self.improving_threshold = improving_threshold
        self.degrading_threshold = degrading_threshold
        self.failure_streak = 0
    
    def update(self, composite: float, delta: float) -> TrajectoryState:
        self.history.append(delta)
        
        if composite < self.failure_threshold:
            self.failure_streak += 1
        else:
            self.failure_streak = 0
        
        recent = list(self.history)[-self.trend_window:]
        trend = sum(recent) / len(recent) if recent else 0.0
        
        if trend > self.improving_threshold:
            label = "improving"
        elif trend < self.degrading_threshold:
            label = "degrading"
        else:
            label = "flat"
        
        return TrajectoryState(
            trend=trend,
            label=label,
            failure_streak=self.failure_streak,
            delta_history=list(self.history),
        )
```

Approximately 60 lines. Has bounded internal state. Reusable wherever directional state derivation matters.

---

## 9. Hysteresis Mode Router Specification

```python
# lattica/_primitives/mode_router.py
"""
Mode router with minimum-duration persistence and emergency override.

Prevents mode flapping while still allowing emergency mode changes.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class ModeDecision:
    mode: str
    changed: bool
    reason: str
    duration: int   # cycles spent in returned mode


class HysteresisModeRouter:
    def __init__(self, modes: list[str], default_mode: str,
                 min_duration: int = 3,
                 override_conditions: list[Callable[[dict], bool]] = None):
        self.modes = modes
        self.default_mode = default_mode
        self.min_duration = min_duration
        self.override_conditions = override_conditions or []
        self.current_mode = default_mode
        self.duration = 0
    
    def decide(self, signals: dict, candidate_mode: str) -> ModeDecision:
        # Check for emergency override
        for cond in self.override_conditions:
            if cond(signals):
                if candidate_mode != self.current_mode:
                    self.current_mode = candidate_mode
                    self.duration = 0
                    return ModeDecision(
                        mode=self.current_mode,
                        changed=True,
                        reason="emergency_override",
                        duration=self.duration,
                    )
        
        # Normal mode persistence
        if self.duration < self.min_duration:
            self.duration += 1
            return ModeDecision(
                mode=self.current_mode,
                changed=False,
                reason="min_duration_not_met",
                duration=self.duration,
            )
        
        # Permit mode change
        if candidate_mode != self.current_mode and candidate_mode in self.modes:
            self.current_mode = candidate_mode
            self.duration = 0
            changed = True
            reason = "mode_change_accepted"
        else:
            self.duration += 1
            changed = False
            reason = "no_change_requested" if candidate_mode == self.current_mode else "invalid_candidate"
        
        return ModeDecision(
            mode=self.current_mode,
            changed=changed,
            reason=reason,
            duration=self.duration,
        )
```

Approximately 70 lines. Stateful (current mode + duration). Used wherever mode persistence with override matters.

---

## 10. Component Score Composer Specification

```python
# lattica/_primitives/score_composer.py
"""
Multi-component scoring with named weights and preserved components.

Implements the 'don't collapse early' doctrine — components are always
visible alongside the composite for inspection and debugging.
"""

from dataclasses import dataclass


@dataclass
class CompositeScore:
    composite: float
    components: dict[str, float]
    weights: dict[str, float]
    
    def explain(self) -> list[dict]:
        """Per-component contribution breakdown."""
        return [
            {
                "component": name,
                "value": self.components[name],
                "weight": self.weights[name],
                "contribution": self.components[name] * self.weights[name],
            }
            for name in self.components
        ]


def compose(components: dict[str, float], weights: dict[str, float],
            validate_weights: bool = True) -> CompositeScore:
    """
    Compute weighted-mean composite from named components.
    
    Args:
        components: {name: value} where each value is in [0, 1]
        weights: {name: weight} where weights sum to 1.0 (within tolerance)
        validate_weights: if True, raises on weight sum out of tolerance
    
    Returns:
        CompositeScore with preserved components for inspection
    """
    if set(components.keys()) != set(weights.keys()):
        raise ValueError(
            f"Component and weight keys must match. "
            f"Components: {set(components)}, Weights: {set(weights)}"
        )
    
    if validate_weights:
        weight_sum = sum(weights.values())
        if not (0.95 <= weight_sum <= 1.05):
            raise ValueError(
                f"Weights must sum to ~1.0, got {weight_sum}"
            )
    
    composite = sum(components[name] * weights[name] for name in components)
    
    return CompositeScore(
        composite=composite,
        components=dict(components),
        weights=dict(weights),
    )
```

Approximately 50 lines. Pure function. Used wherever multi-component scoring with preserved components matters.

---

## 11. Tombstone-Aware Set Specification

```python
# lattica/_primitives/tombstone_set.py
"""
A set with three states per item: present, tombstoned, absent.

Tombstoned items don't return on retrieval but block re-insertion of
identical items unless explicit restore.
"""

from dataclasses import dataclass
from enum import Enum


class ItemState(Enum):
    PRESENT = "present"
    TOMBSTONED = "tombstoned"
    ABSENT = "absent"


@dataclass
class TombstoneInfo:
    reason: str
    tombstoned_at: int          # timestamp
    tombstoned_by: str          # actor


class TombstoneSet:
    def __init__(self):
        self._present: dict = {}   # id -> value
        self._tombstoned: dict = {}  # id -> TombstoneInfo
    
    def add(self, item_id: str, value) -> bool:
        """Add item. Returns True if added, False if blocked by tombstone."""
        if item_id in self._tombstoned:
            return False
        self._present[item_id] = value
        return True
    
    def tombstone(self, item_id: str, reason: str, timestamp: int, actor: str):
        """Tombstone an item. Removes from present, marks tombstoned."""
        if item_id in self._present:
            del self._present[item_id]
        self._tombstoned[item_id] = TombstoneInfo(
            reason=reason,
            tombstoned_at=timestamp,
            tombstoned_by=actor,
        )
    
    def restore(self, item_id: str, value):
        """Explicitly restore a tombstoned item."""
        if item_id in self._tombstoned:
            del self._tombstoned[item_id]
        self._present[item_id] = value
    
    def state(self, item_id: str) -> ItemState:
        if item_id in self._present:
            return ItemState.PRESENT
        if item_id in self._tombstoned:
            return ItemState.TOMBSTONED
        return ItemState.ABSENT
    
    def get(self, item_id: str):
        """Get item if present. Returns None for tombstoned or absent."""
        return self._present.get(item_id)
    
    def get_with_tombstones(self, item_id: str) -> tuple:
        """Get (value, state, tombstone_info). For audit/admin contexts."""
        if item_id in self._present:
            return (self._present[item_id], ItemState.PRESENT, None)
        if item_id in self._tombstoned:
            return (None, ItemState.TOMBSTONED, self._tombstoned[item_id])
        return (None, ItemState.ABSENT, None)
    
    def __contains__(self, item_id: str) -> bool:
        return item_id in self._present
    
    def __len__(self) -> int:
        return len(self._present)
```

Approximately 80 lines. Stateful (in-memory; persistence is consumer's responsibility). Used wherever tombstone semantics matter.

---

## 12. What's Not in the Primitives Package

Things that look like they might be primitives but aren't (yet):

**Bandit Selector.** Well-known algorithm with a specific Bons.ai shape. Lives in the catalyst doc. Not a primitive yet because the shape is still maturing — it may evolve toward Thompson Sampling or other approaches before stabilizing.

**Multi-Factor Action Selector (catalyst pattern).** Mature in Bons.ai but Cerebra-specific in current shape. Wait for second consumer before extracting.

**Provenance Chain Edge.** Used everywhere but the implementations differ slightly across projects. Wait for shape convergence before extracting.

**Truth Tower.** Cerebra-specific. Not Lattica-wide.

**Re-injection Loop.** Cerebra-specific. Not Lattica-wide.

**Leeway Network.** Cerebra-specific. The pattern may eventually be Lattica-wide (Policy Scout could use a leeway-network-shaped permission system) but extraction premature.

The rule is: **two consumers, stable shape, 90+ days of production use, no external dependencies — only then does something graduate from project-internal to Lattica primitive.**

---

## 13. Testing Requirements

Each primitive should have:

```text
unit tests in the canonical source location
"contract" tests that verify the same behavior in each vendored copy
   (catches drift if a project modifies its vendored copy)
documentation of expected behavior
example usage from at least one real Lattica project
```

When a primitive's behavior changes, the canonical version is updated first. Then each project's vendored copy is updated. Tests catch divergence.

---

## 14. Eventual Package Structure

When extracted, the package structure will be:

```text
lattica-primitives/
  pyproject.toml
  README.md
  
  lattica/
    primitives/
      __init__.py
      clutch.py
      triangulator.py
      trajectory.py
      mode_router.py
      score_composer.py
      tombstone_set.py
  
  tests/
    test_clutch.py
    test_triangulator.py
    test_trajectory.py
    test_mode_router.py
    test_score_composer.py
    test_tombstone_set.py
```

Import path: `from lattica.primitives import Clutch, triangulate, ...`

Versioning: semver strict from day one of extraction. Pre-1.0 during the first 6 months of public use; 1.0 when interfaces have proven stable for an additional 6 months.

---

## 15. Lattica Primitives Doctrine

The Lattica suite values project independence. The hard rule is no runtime dependencies between projects.

These six primitives are the sanctioned exception. They earned the exception by being small, stable, dependency-free, and demonstrably useful across at least two projects. Future additions to the primitive set must clear the same bar.

The vendoring discipline reflects a deeper principle: extraction is a cost, not a benefit. A primitive that lives in its consumer is easier to modify; a primitive in a published package is easier to share but harder to evolve. The right time to extract is when sharing matters more than evolution. For most primitives, that time arrives slowly.

When in doubt: vendor. When extraction is clearly net-positive: publish.

The six primitives above are the floor of what makes the Lattica suite cohesive without compromising independence. They are the bare minimum of shared infrastructure. They will not grow quickly.
