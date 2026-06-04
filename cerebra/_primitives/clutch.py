"""
Priority-rule controller for cognitive or operational decisions.

A clutch maps signal state to typed action via priority-ordered cascade.
First matching rule wins. Explanation is part of the return type.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    action: str
    intensity: str | None
    reason: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Rule:
    name: str
    guard: Callable[[dict[str, Any], dict[str, Any]], bool]
    action: Decision | Callable[[dict[str, Any], dict[str, Any]], Decision]


class Clutch:
    """Priority-ordered rule cascade with explainable output."""

    def __init__(self, rules: list[Rule], default: Decision) -> None:
        self.rules = rules
        self.default = default

    def decide(self, signals: dict[str, Any], state: dict[str, Any]) -> Decision:
        for rule in self.rules:
            if rule.guard(signals, state):
                action = rule.action
                return action(signals, state) if callable(action) else action
        return self.default

    def explain(self, signals: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
        """Return per-rule firing trace for inspector."""
        trace: list[dict[str, Any]] = []
        for rule in self.rules:
            fired = rule.guard(signals, state)
            trace.append({"rule": rule.name, "fired": fired})
            if fired:
                break
        return trace
