# Lattica Primitives — §11 Bandit Selector

*Drop-in addition to `docs/refined-runtime-model/LATTICA_PRIMITIVES.md`. Insert as §11 (after §10 Component Score Composer), and add the §3.7 summary entry to the "Six Initial Primitives" section.*

---

## §3.7 Bandit Selector

A UCB-based arm selector with per-arm reward tracking. Provides arm-statistics primitives that higher-level scorers can compose into multi-factor selection, or use directly for simple bandit-style choices.

```text
Used by: Cerebra (Catalyst's base_reward and confidence_ramp factors),
         Bons.ai (cycle-config strategy and mutation selection),
         Policy Scout (planned: tool-selection learning)
Stability: medium-high; algorithm is textbook UCB, but multi-consumer
           validation pending
```

See full specification in §11.

*Note: this changes the §3 count from "six" to "seven" initial primitives. Update §3 preamble accordingly: "Seven primitives have demonstrated reuse potential..."*

---

## §11. Bandit Selector Specification

```python
# lattica/_primitives/bandit.py
"""
Bandit selector — UCB-based arm selection with per-arm reward statistics.

Maintains per-arm count and total_reward. Provides UCB selection
(forced exploration of unselected arms, exploration bonus weighted by
log(total_steps)/count) and exposes raw arm statistics for higher-level
multi-factor selectors.

This primitive is the foundation for richer selectors. Cerebra's Catalyst
uses arm statistics from this primitive to compute a five-factor score
and applies weighted-random sampling. Other consumers (Policy Scout's
tool selection, Bons.ai's strategy selection) can use UCB selection
directly.

The primitive is domain-agnostic. Arm identifiers are caller-supplied
strings; no hardcoded categories.
"""

import math
import random
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ArmStats:
    """Per-arm reward statistics."""
    count: int = 0
    total_reward: float = 0.0
    last_selected_step: int | None = None

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.count if self.count > 0 else 0.0


@dataclass
class BanditSelection:
    """Result of a bandit selection, with full decision trace."""
    arm: str
    selection_reason: str         # "forced_exploration" | "ucb_score"
    ucb_score: float              # the score computed for the selected arm
    mean_reward: float            # arm's mean reward at selection time
    exploration_bonus: float      # the UCB bonus component
    candidates_seen: int          # how many arms were evaluated


class Bandit:
    """UCB-based arm selector with per-arm reward tracking."""

    def __init__(
        self,
        exploration_weight: float = 1.4,
        rng: random.Random | None = None,
    ):
        self.exploration_weight = exploration_weight
        self.arms: dict[str, ArmStats] = {}
        self._rng = rng if rng is not None else random.Random()

    def ensure_arms(self, arm_ids: Iterable[str]) -> None:
        """Register arms in the bandit. Idempotent."""
        for arm_id in arm_ids:
            if arm_id not in self.arms:
                self.arms[arm_id] = ArmStats()

    def select(
        self,
        arm_ids: Iterable[str],
        total_steps: int,
    ) -> BanditSelection:
        """Select an arm via UCB. Forces exploration of unseen arms first."""
        arm_list = list(arm_ids)
        if not arm_list:
            raise ValueError("Cannot select from empty arm list")

        self.ensure_arms(arm_list)

        # Force exploration: pick first unselected arm in declared order
        for arm_id in arm_list:
            if self.arms[arm_id].count == 0:
                self.arms[arm_id].last_selected_step = total_steps
                return BanditSelection(
                    arm=arm_id,
                    selection_reason="forced_exploration",
                    ucb_score=float("inf"),
                    mean_reward=0.0,
                    exploration_bonus=float("inf"),
                    candidates_seen=len(arm_list),
                )

        # All arms have been tried — apply UCB
        best_score = float("-inf")
        best_arm = arm_list[0]
        best_mean = 0.0
        best_bonus = 0.0

        for arm_id in arm_list:
            arm = self.arms[arm_id]
            mean = arm.mean_reward
            bonus = self.exploration_weight * math.sqrt(
                math.log(total_steps + 1) / arm.count
            )
            score = mean + bonus

            if score > best_score:
                best_score = score
                best_arm = arm_id
                best_mean = mean
                best_bonus = bonus

        self.arms[best_arm].last_selected_step = total_steps

        return BanditSelection(
            arm=best_arm,
            selection_reason="ucb_score",
            ucb_score=best_score,
            mean_reward=best_mean,
            exploration_bonus=best_bonus,
            candidates_seen=len(arm_list),
        )

    def update(self, arm_id: str, reward: float) -> None:
        """Apply reward feedback to an arm. Creates the arm if missing."""
        if arm_id not in self.arms:
            self.arms[arm_id] = ArmStats()
        self.arms[arm_id].count += 1
        self.arms[arm_id].total_reward += reward

    def get_stats(self, arm_id: str) -> ArmStats:
        """Return arm statistics for inspection or higher-level scoring.

        Returns a fresh ArmStats() if arm has never been registered or updated.
        Use this when consuming the bandit as a stats provider for a richer
        selector (e.g., Cerebra's Catalyst).
        """
        return self.arms.get(arm_id, ArmStats())

    def explain(self, arm_ids: Iterable[str], total_steps: int) -> list[dict]:
        """Return per-arm scoring trace for inspector."""
        self.ensure_arms(arm_ids)
        trace = []
        for arm_id in arm_ids:
            arm = self.arms[arm_id]
            mean = arm.mean_reward
            if arm.count == 0:
                bonus = float("inf")
                score = float("inf")
            else:
                bonus = self.exploration_weight * math.sqrt(
                    math.log(total_steps + 1) / arm.count
                )
                score = mean + bonus
            trace.append({
                "arm": arm_id,
                "count": arm.count,
                "mean_reward": mean,
                "exploration_bonus": bonus,
                "ucb_score": score,
            })
        return trace

    def to_state(self) -> dict:
        """Serialize bandit state for persistence."""
        return {
            "exploration_weight": self.exploration_weight,
            "arms": {
                arm_id: {
                    "count": stats.count,
                    "total_reward": stats.total_reward,
                    "last_selected_step": stats.last_selected_step,
                }
                for arm_id, stats in self.arms.items()
            },
        }

    @classmethod
    def from_state(cls, state: dict, rng: random.Random | None = None) -> "Bandit":
        """Deserialize bandit from persisted state."""
        bandit = cls(
            exploration_weight=state.get("exploration_weight", 1.4),
            rng=rng,
        )
        for arm_id, arm_data in state.get("arms", {}).items():
            bandit.arms[arm_id] = ArmStats(
                count=arm_data.get("count", 0),
                total_reward=arm_data.get("total_reward", 0.0),
                last_selected_step=arm_data.get("last_selected_step"),
            )
        return bandit
```

Approximately 130 lines. Pure stdlib (`math`, `random`). Stateful (per-arm counts and rewards). Deterministic-when-seeded via injected `rng`. Serializable via `to_state` / `from_state` for persistence.

---

## Design notes

### Why UCB, not Thompson Sampling or epsilon-greedy

UCB requires no probability distribution priors and no separate exploration rate parameter — the exploration bonus comes from arm statistics directly. Thompson Sampling needs distribution assumptions (Beta for binary rewards, Gaussian for continuous). Epsilon-greedy requires tuning the exploration rate per consumer. UCB is the minimal-tuning choice for a primitive.

The exploration_weight parameter (default 1.4 ≈ √2) lets consumers tune exploration aggressiveness without changing the algorithm. Higher weights produce more exploration; lower weights produce more exploitation.

### Why force exploration of unseen arms

The standard UCB formulation has unselected arms score at +∞ (because `log(N+1)/0` is undefined). In practice, this means the bandit will pick each arm at least once before any UCB computation matters. The primitive makes this explicit: when an arm has count==0, return immediately with `selection_reason="forced_exploration"` and `ucb_score=float("inf")`.

This avoids the divide-by-zero edge case cleanly and produces a clear trace for inspector tooling.

### Why expose `get_stats` for external consumers

Higher-level selectors (like Cerebra's Catalyst) compute multi-factor scores that USE the bandit's mean_reward and count but DON'T use UCB directly. They need `arm.mean_reward` for the base_reward factor and `arm.count` for the confidence_ramp factor.

`get_stats` returns the raw statistics so external consumers can compose without re-implementing arm tracking. This is the primary integration pattern for the Catalyst.

### Why caller-supplied RNG

Tests need deterministic bandit behavior. By accepting an injected `random.Random` instance, tests can seed the RNG (`Bandit(rng=random.Random(42))`) and get reproducible selections. Production code passes nothing, getting fresh randomness.

The RNG is currently used only in `select`'s tiebreaking path (not implemented in v0.1 — first-wins for ties is acceptable). Future versions may use it for weighted-random selection within the primitive itself.

### Serialization via `to_state` / `from_state`

The primitive doesn't dictate where arm stats live. Consumers can:

- Persist `to_state()` output in a SQLite column (session-scoped or vault-scoped)
- Emit it as a fossic event payload (for cross-session learning via event replay)
- Hold it in-memory only (per-process bandit state, lost between runs)

This decision belongs to the consumer's persistence model, not the primitive.

### What this primitive does NOT do

- **Weighted-random sampling.** UCB selection is argmax-based. If a consumer wants weighted-random selection (e.g., Cerebra's Catalyst), it sources `mean_reward` and `count` via `get_stats` and implements sampling itself.
- **Multi-factor scoring.** UCB is single-factor (mean + exploration bonus). Multi-factor scoring (decay, type_penalty, chain_bonus) belongs in higher-level selectors.
- **Reward shaping.** Consumers compute their own reward values before calling `update`. The primitive accepts any float; semantic interpretation is the consumer's concern.
- **Arm vocabulary management.** The primitive doesn't enforce a fixed arm set. Consumers can change the arm vocabulary mid-session by passing different `arm_ids` to `select`. The primitive tolerates this; semantic correctness is the consumer's concern.

---

## Test requirements

A complete test suite for this primitive should cover:

```text
ArmStats.mean_reward returns 0.0 when count == 0
ArmStats.mean_reward returns total_reward / count when count > 0

Bandit.ensure_arms is idempotent (no double-init)
Bandit.ensure_arms preserves existing arm stats

Bandit.select on empty arm list raises ValueError
Bandit.select picks first unseen arm with selection_reason="forced_exploration"
Bandit.select on all-explored arms applies UCB with selection_reason="ucb_score"
Bandit.select updates last_selected_step on the chosen arm
Bandit.select ties broken by declaration order (first-wins for equal UCB scores)

Bandit.update increments count by 1 and adds reward to total_reward
Bandit.update creates the arm if it doesn't exist
Bandit.update with negative reward is allowed (semantics are consumer-defined)

Bandit.get_stats returns ArmStats() for unknown arm (does not raise)
Bandit.get_stats returns the actual stats for known arms

Bandit.explain produces trace entries for all candidate arms
Bandit.explain reports infinite scores for unselected arms

Bandit.to_state / Bandit.from_state round-trip preserves all arm stats
Bandit.from_state with missing fields uses defaults (backward compat)

Determinism: same seed + same operations produce identical state
```

---

## Adjacent: legacy ai-lab implementation

The proof-of-concept implementation at `~/Projects/ai-lab/core/bandit.py` predates this specification. It implements the same UCB algorithm but with the following differences:

- Procedural (free functions over dicts) rather than class-based
- Hardcoded domain assumption in `ensure_bandit_structure` (strategy/mutation/tool)
- No type hints, no dataclasses
- No serialization helpers
- No explain trace
- No deterministic RNG injection

The algorithm core in ai-lab's `select_option` is structurally identical to this primitive's `select` UCB branch. Implementations targeting this spec can verify behavioral equivalence by running both against the same arm-update sequences and confirming identical selections.

The ai-lab implementation should be considered the historical precedent, not the canonical reference. This specification supersedes it.
