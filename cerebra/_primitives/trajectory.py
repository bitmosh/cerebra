"""
Maintains rolling delta history, derives smoothed trend and trajectory label,
tracks failure streak.
"""

from collections import deque
from dataclasses import dataclass


@dataclass
class TrajectoryState:
    trend: float
    label: str  # 'improving' | 'flat' | 'degrading'
    failure_streak: int
    delta_history: list[float]


class TrajectoryTracker:
    def __init__(
        self,
        history_cap: int = 20,
        trend_window: int = 3,
        failure_threshold: float = 5.0,
        improving_threshold: float = 0.05,
        degrading_threshold: float = -0.05,
    ) -> None:
        self.history: deque[float] = deque(maxlen=history_cap)
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

        recent = list(self.history)[-self.trend_window :]
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
