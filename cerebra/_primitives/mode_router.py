"""
Mode router with minimum-duration persistence and emergency override.

Prevents mode flapping while still allowing emergency mode changes.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ModeDecision:
    mode: str
    changed: bool
    reason: str
    duration: int  # cycles spent in returned mode


class HysteresisModeRouter:
    def __init__(
        self,
        modes: list[str],
        default_mode: str,
        min_duration: int = 3,
        override_conditions: list[Callable[[dict[str, object]], bool]] | None = None,
    ) -> None:
        self.modes = modes
        self.default_mode = default_mode
        self.min_duration = min_duration
        self.override_conditions: list[Callable[[dict[str, object]], bool]] = (
            override_conditions or []
        )
        self.current_mode = default_mode
        self.duration = 0

    def decide(self, signals: dict[str, object], candidate_mode: str) -> ModeDecision:
        for cond in self.override_conditions:
            if cond(signals) and candidate_mode != self.current_mode:
                self.current_mode = candidate_mode
                self.duration = 0
                return ModeDecision(
                    mode=self.current_mode,
                    changed=True,
                    reason="emergency_override",
                    duration=self.duration,
                )

        if self.duration < self.min_duration:
            self.duration += 1
            return ModeDecision(
                mode=self.current_mode,
                changed=False,
                reason="min_duration_not_met",
                duration=self.duration,
            )

        if candidate_mode != self.current_mode and candidate_mode in self.modes:
            self.current_mode = candidate_mode
            self.duration = 0
            changed = True
            reason = "mode_change_accepted"
        else:
            self.duration += 1
            changed = False
            reason = (
                "no_change_requested"
                if candidate_mode == self.current_mode
                else "invalid_candidate"
            )

        return ModeDecision(
            mode=self.current_mode,
            changed=changed,
            reason=reason,
            duration=self.duration,
        )
