"""
Inspector event envelope — full schema per CEREBRA_INSPECTOR.md §4.

All nullable fields (cycle_id, step_id, etc.) are None in Phase 0 events;
they will be populated when the cycle runtime is built in later phases.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# Controlled vocabulary from CEREBRA_INSPECTOR.md §5.
# Phase 0 uses only the system/governance subset; full vocabulary added per phase.
PHASE_0_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # System / vault lifecycle
        "SystemInitialized",
        "VaultCreated",
        "MigrationRun",
        # Governance
        "ConfigLoaded",
        "LeewayRuleLoaded",
        "ConstitutionalBlock",
    }
)

PHASE_5_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # Working memory lifecycle
        "WorkingMemoryCreated",
        "AttentionItemProposed",
        "AttentionItemPromoted",
        "AttentionItemEvicted",
        "AttentionItemDeferred",
        "InterruptCandidateCreated",
        "WorkingMemoryRendered",
        "WorkingMemoryCleared",
        # Truth tower lifecycle
        "TowerInitialized",
        "TowerItemPromoted",
        "TowerItemEvicted",
        "TowerCrossReferenceAdded",
        "TowerItemStaled",
        "TowerTierRebuilt",  # Phase 6+ — defined here, never emitted in Phase 5
        "TowerCollapsed",  # Phase 6+ — defined here, never emitted in Phase 5
        "TowerRendered",
    }
)

LATTICE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "LatticeCommit",  # emitted once per chunk when ≥2 categories clear threshold
        "LatticeSiblingResolved",  # emitted once per lineage group when siblings are deduped
    }
)

# Phase 6 block — cycle runtime events (defined here for type-check coverage;
# not yet emitted until Phase 6 Step 2+).
PHASE_6_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # Session + cycle lifecycle
        "SessionOpened",
        "CycleStarted",
        "CycleCompleted",
        # Step execution
        "StepStarted",
        "ContextPacketBuilt",
        "StepExecuted",
        "StepExecutionFailed",
        # Prediction + evaluation
        "PredictionMade",
        "SignalEvaluated",
        "EvaluationComposed",
        "OutcomeRecorded",
        "PredictionSevereMiss",
        # Control decisions
        "ClutchDecisionMade",
        "CatalystInvoked",
        "CatalystArmSelected",
        # Safety gate
        "LeewayGrantApplied",
        # Re-injection
        "ContinuationBundleCreated",
        "ReinjectionTriggered",
        # Working memory + session end
        "MemoryWriteFromCycle",
        "SessionFlushed",
        # Consolidation (Phase 10)
        "ConsolidationStarted",
        "ConsolidationCompleted",
        # Lifecycle (Phase 11)
        "MemoryRecordArchived",
        "MemoryRecordTombstoned",
        "MemoryRecordRestored",
        # Graph export (Phase 12)
        "GraphExported",
    }
)

ALL_KNOWN_EVENT_TYPES: frozenset[str] = (
    PHASE_0_EVENT_TYPES | PHASE_5_EVENT_TYPES | LATTICE_EVENT_TYPES | PHASE_6_EVENT_TYPES
)


@dataclass
class InspectorEvent:
    """Structured event envelope — every cognitive action produces one."""

    event_type: str
    actor: str
    summary: str
    data: dict[str, Any]

    # Auto-populated at construction
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    schema_version: int = 1
    timestamp: int = field(default_factory=lambda: int(time.time()))

    # Nullable context fields — None until the cycle runtime exists
    session_id: str | None = None
    cycle_id: str | None = None
    step_id: str | None = None
    subject_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "step_id": self.step_id,
            "subject_id": self.subject_id,
            "actor": self.actor,
            "summary": self.summary,
            "data": self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def make_event(
    event_type: str,
    actor: str,
    summary: str,
    data: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
    cycle_id: str | None = None,
    step_id: str | None = None,
    subject_id: str | None = None,
) -> InspectorEvent:
    """Convenience factory for creating inspector events."""
    return InspectorEvent(
        event_type=event_type,
        actor=actor,
        summary=summary,
        data=data or {},
        session_id=session_id,
        cycle_id=cycle_id,
        step_id=step_id,
        subject_id=subject_id,
    )
