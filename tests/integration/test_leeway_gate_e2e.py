"""End-to-end integration test for the leeway pre-action gate.

Tests the full load → evaluate → emit → persist → read cycle against
a real FossicStore and vault with written defaults. No LLM calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.cognition.event_emitter import EventEmitter
from cerebra.governance.gate_events import emit_leeway_grant_applied
from cerebra.governance.loader import load_pre_action_gate, write_defaults_to_vault
from cerebra.governance.types import ProposedAction
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    db_path = tmp_path / "cerebra.db"
    db_path.touch()
    run_migrations(db_path)
    write_defaults_to_vault(tmp_path)
    return tmp_path


@pytest.fixture()
def store(vault: Path) -> FossicStore:
    return FossicStore(vault)


# ── integration tests ─────────────────────────────────────────────────────────


@pytest.mark.integration
class TestLeewayGateE2E:
    def test_full_load_evaluate_emit_read_permitted(
        self,
        vault: Path,
        store: FossicStore,
    ) -> None:
        gate = load_pre_action_gate(vault)
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_gate_e2e")

        trigger_id = emitter.emit_cycle_event(
            event_type="ClutchDecisionMade",
            payload={
                "session_id": "sess_e2e",
                "cycle_id": "cycle_gate_e2e",
                "action": "retrieve_from_memory",
            },
        )

        action = ProposedAction(
            action_name="retrieve_from_memory",
            session_id="sess_e2e",
            cycle_id="cycle_gate_e2e",
            step_id="step_e2e",
        )
        decision = gate.evaluate(action)
        assert decision.final_decision == "permitted"
        assert len(decision.grants_applied) > 0

        lga_event_id = emit_leeway_grant_applied(emitter, decision, trigger_id)
        assert isinstance(lga_event_id, bytes)

        from fossic import ReadQuery

        events = store._store.read_range(
            ReadQuery(stream_id="cerebra/agent-trace/sess_e2e")
        )
        lga_events = [e for e in events if e.event_type == "LeewayGrantApplied"]
        assert len(lga_events) == 1

        payload = lga_events[0].payload()
        assert payload["session_id"] == "sess_e2e"
        assert payload["proposed_action"] == "retrieve_from_memory"
        assert payload["final_decision"] == "permitted"
        assert "LR-001" in payload["grants_applied"]

    def test_causation_chain_verified(self, vault: Path, store: FossicStore) -> None:
        gate = load_pre_action_gate(vault)
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_gate_chain")

        trigger_id = emitter.emit_cycle_event(
            event_type="ClutchDecisionMade",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_gate_chain", "action": "end_cycle"},
        )
        action = ProposedAction(
            action_name="end_cycle",
            session_id="sess_e2e",
            cycle_id="cycle_gate_chain",
            step_id="step_chain",
        )
        decision = gate.evaluate(action)
        lga_event_id = emit_leeway_grant_applied(emitter, decision, trigger_id)

        from fossic import ReadQuery

        events = store._store.read_range(
            ReadQuery(stream_id="cerebra/agent-trace/sess_e2e")
        )
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        assert lga.causation_id is not None
        assert lga.causation_id.as_bytes() == trigger_id

        # Simulate gated action event chaining to leeway grant
        emitter.emit_cycle_event(
            event_type="CycleEnded",
            payload={
                "session_id": "sess_e2e",
                "cycle_id": "cycle_gate_chain",
                "step_id": "step_chain",
                "leeway_grant_event_id": lga_event_id.hex(),
            },
            causation_id=lga_event_id,
        )
        events = store._store.read_range(
            ReadQuery(stream_id="cerebra/agent-trace/sess_e2e")
        )
        cycle_ended = next(e for e in events if e.event_type == "CycleEnded")
        assert cycle_ended.causation_id is not None
        assert cycle_ended.causation_id.as_bytes() == lga_event_id

    def test_forbidden_decision_emits_lga_event(
        self, store: FossicStore
    ) -> None:
        from cerebra.governance.pre_action_gate import LeewayPreActionGate

        # Gate with empty leeway rules: all forbidden
        empty_gate = LeewayPreActionGate(leeway_rules=[], constitutional_rules=[])
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_gate_forb")

        trigger_id = emitter.emit_cycle_event(
            event_type="ClutchDecisionMade",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_gate_forb", "action": "end_cycle"},
        )
        action = ProposedAction(
            action_name="end_cycle",
            session_id="sess_e2e",
            cycle_id="cycle_gate_forb",
            step_id="step_forb",
        )
        decision = empty_gate.evaluate(action)
        assert decision.final_decision == "forbidden"

        emit_leeway_grant_applied(emitter, decision, trigger_id)

        from fossic import ReadQuery

        events = store._store.read_range(
            ReadQuery(stream_id="cerebra/agent-trace/sess_e2e")
        )
        lga_events = [e for e in events if e.event_type == "LeewayGrantApplied"]
        assert len(lga_events) == 1
        assert lga_events[0].payload()["final_decision"] == "forbidden"
        assert lga_events[0].payload()["forbidden_by"] == "no_grants"

    def test_vocabulary_payload_structure_matches_spec(
        self, vault: Path, store: FossicStore
    ) -> None:
        """Verify payload matches cerebra_phase6_event_vocabulary.md LeewayGrantApplied schema."""
        gate = load_pre_action_gate(vault)
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_gate_vocab")

        trigger_id = emitter.emit_cycle_event(
            event_type="ClutchDecisionMade",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_gate_vocab", "action": "ask_user"},
        )
        action = ProposedAction(
            action_name="ask_user",
            session_id="sess_e2e",
            cycle_id="cycle_gate_vocab",
            step_id="step_vocab",
        )
        decision = gate.evaluate(action)
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        from fossic import ReadQuery

        events = store._store.read_range(
            ReadQuery(stream_id="cerebra/agent-trace/sess_e2e")
        )
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        payload = lga.payload()

        # Required fields per vocabulary spec
        for field in [
            "session_id",
            "cycle_id",
            "step_id",
            "proposed_action",
            "grants_applied",
            "final_decision",
            "applied_at",
        ]:
            assert field in payload, f"Required field missing: {field}"

        assert isinstance(payload["grants_applied"], list)
        assert isinstance(payload["applied_at"], int)
