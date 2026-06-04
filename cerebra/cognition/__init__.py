"""
cerebra.cognition — public cognitive runtime API.

Other Cerebra modules access cognitive primitives only through this module.
This discipline approximates the eventual lattica-cognition package extraction.

Phase 0: empty surface — populated as phases add runtime components.
Phase 1+: SKU classifier, working memory, signal pipeline, clutch, catalyst.
"""

# Re-export the six Lattica primitives as the cognition module's public surface.
# Consumers should import from here, not directly from cerebra._primitives.
from cerebra._primitives import (
    Clutch,
    CompositeScore,
    Decision,
    HysteresisModeRouter,
    ItemState,
    ModeDecision,
    Rule,
    TombstoneInfo,
    TombstoneSet,
    TrajectoryState,
    TrajectoryTracker,
    compose,
    triangulate,
    triangulate_with_components,
)

__all__ = [
    "Clutch",
    "Decision",
    "Rule",
    "HysteresisModeRouter",
    "ModeDecision",
    "CompositeScore",
    "compose",
    "ItemState",
    "TombstoneInfo",
    "TombstoneSet",
    "TrajectoryState",
    "TrajectoryTracker",
    "triangulate",
    "triangulate_with_components",
]
