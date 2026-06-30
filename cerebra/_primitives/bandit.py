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
from collections.abc import Iterable
from dataclasses import dataclass


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
