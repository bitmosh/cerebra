"""
cerebra.cognition — public cognitive runtime API.

Other Cerebra modules access cognitive primitives only through this module.
This discipline approximates the eventual lattica-cognition package extraction.

Phase 0: Lattica primitives surface.
Phase 2: SKU classifier, address model, LLM adapter.
Phase 3+: working memory, signal pipeline, clutch, catalyst.
"""

# Lattica primitives
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

# Phase 2 — SKU addressing
from cerebra.cognition.llm_adapter import (
    ClassificationError,
    ClassificationResult,
    LLMAdapter,
    OllamaDirectAdapter,
    ProxyLLMAdapter,
)
from cerebra.cognition.sku import (
    D9Modality,
    D10Provenance,
    SKUAddress,
    SKUAssignment,
    d9_from_detected_type,
)
from cerebra.cognition.sku_categories import CATEGORY_DESCRIPTIONS, D1Category, quadrant_of
from cerebra.cognition.sku_classifier import (
    CLASSIFIER_VERSION,
    PROMPT_VERSION,
    BackfillReport,
    SKUClassifier,
)
from cerebra.cognition.sku_relationships import D4Relationship

__all__ = [
    # Lattica primitives
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
    # SKU addressing
    "D1Category",
    "CATEGORY_DESCRIPTIONS",
    "quadrant_of",
    "D4Relationship",
    "D9Modality",
    "D10Provenance",
    "SKUAddress",
    "SKUAssignment",
    "d9_from_detected_type",
    "LLMAdapter",
    "OllamaDirectAdapter",
    "ProxyLLMAdapter",
    "ClassificationResult",
    "ClassificationError",
    "SKUClassifier",
    "BackfillReport",
    "CLASSIFIER_VERSION",
    "PROMPT_VERSION",
]
