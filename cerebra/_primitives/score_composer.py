# SPDX-License-Identifier: Apache-2.0
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

    def explain(self) -> list[dict[str, float | str]]:
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


def compose(
    components: dict[str, float],
    weights: dict[str, float],
    validate_weights: bool = True,
) -> CompositeScore:
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
            raise ValueError(f"Weights must sum to ~1.0, got {weight_sum}")

    composite = sum(components[name] * weights[name] for name in components)

    return CompositeScore(
        composite=composite,
        components=dict(components),
        weights=dict(weights),
    )
