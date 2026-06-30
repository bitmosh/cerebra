"""Tests for emit_leeway_grant_applied event emission helper."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cerebra.cognition.event_emitter import EventEmitter
from cerebra.governance.defaults import DEFAULT_CONSTITUTIONAL_RULES, DEFAULT_LEEWAY_RULES
from cerebra.governance.gate_events import emit_leeway_grant_applied
from cerebra.governance.pre_action_gate import LeewayPreActionGate
from cerebra.governance.types import ProposedAction
from cerebra.storage.fossic_store import FossicStore

# ── helpers ───────────────────────────────────────────────────────────────────


def _temp_vault() -> Path:
    return Path(tempfile.mkdtemp())


def _make_store_and_emitter(cycle_id: str = "cycle_evt") -> tuple[FossicStore, EventEmitter]:
    vault = _temp_vault()
    store = FossicStore(vault)
    emitter = EventEmitter(store=store, session_id="sess_001", cycle_id=cycle_id)
    return store, emitter


def _stub_event(emitter: EventEmitter, cycle_id: str) -> bytes:
    return emitter.emit_cycle_event(
        event_type="ClutchDecisionMade",
        payload={"session_id": "sess_001", "cycle_id": cycle_id, "action": "refine"},
    )


def _action(name: str = "retrieve_from_memory", cycle_id: str = "cycle_evt") -> ProposedAction:
    return ProposedAction(
        action_name=name,
        session_id="sess_001",
        cycle_id=cycle_id,
        step_id="step_001",
    )


def _gate_with_default_rules() -> LeewayPreActionGate:
    return LeewayPreActionGate(
        leeway_rules=DEFAULT_LEEWAY_RULES,
        constitutional_rules=DEFAULT_CONSTITUTIONAL_RULES,
    )


def _gate_empty() -> LeewayPreActionGate:
    return LeewayPreActionGate(leeway_rules=[], constitutional_rules=[])


# ── emit_leeway_grant_applied tests ───────────────────────────────────────────


@pytest.mark.unit
class TestEmitLeewayGrantApplied:
    def test_returns_bytes_on_permitted(self) -> None:
        store, emitter = _make_store_and_emitter("cycle_perm")
        trigger_id = _stub_event(emitter, "cycle_perm")
        decision = _gate_with_default_rules().evaluate(
            _action("retrieve_from_memory", "cycle_perm")
        )
        event_id = emit_leeway_grant_applied(emitter, decision, trigger_id)
        assert isinstance(event_id, bytes)
        assert len(event_id) > 0

    def test_returns_bytes_on_forbidden(self) -> None:
        store, emitter = _make_store_and_emitter("cycle_forb")
        trigger_id = _stub_event(emitter, "cycle_forb")
        decision = _gate_empty().evaluate(_action("retrieve_from_memory", "cycle_forb"))
        assert decision.final_decision == "forbidden"
        event_id = emit_leeway_grant_applied(emitter, decision, trigger_id)
        assert isinstance(event_id, bytes)

    def test_permitted_payload_has_required_fields(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_pf")
        trigger_id = _stub_event(emitter, "cycle_pf")
        decision = _gate_with_default_rules().evaluate(_action("retrieve_from_memory", "cycle_pf"))
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        payload = lga.payload()
        assert payload["session_id"] == "sess_001"
        assert payload["cycle_id"] == "cycle_pf"
        assert payload["step_id"] == "step_001"
        assert payload["proposed_action"] == "retrieve_from_memory"
        assert payload["final_decision"] == "permitted"
        assert "grants_applied" in payload
        assert "applied_at" in payload

    def test_permitted_payload_has_grants_list(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_grants")
        trigger_id = _stub_event(emitter, "cycle_grants")
        decision = _gate_with_default_rules().evaluate(
            _action("retrieve_from_memory", "cycle_grants")
        )
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        grants = lga.payload()["grants_applied"]
        assert isinstance(grants, list)
        assert len(grants) > 0
        assert "LR-001" in grants

    def test_forbidden_payload_has_forbidden_by(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_fb")
        trigger_id = _stub_event(emitter, "cycle_fb")
        decision = _gate_empty().evaluate(_action("retrieve_from_memory", "cycle_fb"))
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        payload = lga.payload()
        assert payload["final_decision"] == "forbidden"
        assert payload["forbidden_by"] == "no_grants"

    def test_permitted_payload_has_no_forbidden_by(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_nfb")
        trigger_id = _stub_event(emitter, "cycle_nfb")
        decision = _gate_with_default_rules().evaluate(_action("retrieve_from_memory", "cycle_nfb"))
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        assert "forbidden_by" not in lga.payload()

    def test_permitted_payload_has_no_review_required_by(self) -> None:
        """DEV-010: review_required_by absent from payload when list is empty."""
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_nrr")
        trigger_id = _stub_event(emitter, "cycle_nrr")
        decision = _gate_with_default_rules().evaluate(_action("retrieve_from_memory", "cycle_nrr"))
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        assert "review_required_by" not in lga.payload()

    def test_causation_chains_to_triggering_event(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_cause")
        trigger_id = _stub_event(emitter, "cycle_cause")
        decision = _gate_with_default_rules().evaluate(
            _action("retrieve_from_memory", "cycle_cause")
        )
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        assert lga.causation_id is not None
        assert lga.causation_id.as_bytes() == trigger_id

    def test_indexed_tags_contain_final_decision(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_tags")
        trigger_id = _stub_event(emitter, "cycle_tags")
        decision = _gate_with_default_rules().evaluate(
            _action("retrieve_from_memory", "cycle_tags")
        )
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        tags = lga.indexed_tags()
        assert tags.get("final_decision") == "permitted"

    def test_indexed_tags_contain_session_cycle_step(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_tagsfull")
        trigger_id = _stub_event(emitter, "cycle_tagsfull")
        decision = _gate_with_default_rules().evaluate(
            _action("retrieve_from_memory", "cycle_tagsfull")
        )
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        tags = lga.indexed_tags()
        assert tags.get("session_id") == "sess_001"
        assert tags.get("cycle_id") == "cycle_tagsfull"
        assert tags.get("step_id") == "step_001"

    def test_custom_proposed_at_ms_in_payload(self) -> None:
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_time")
        trigger_id = _stub_event(emitter, "cycle_time")
        decision = _gate_with_default_rules().evaluate(
            _action("retrieve_from_memory", "cycle_time")
        )
        emit_leeway_grant_applied(emitter, decision, trigger_id, proposed_at_ms=99999)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga = next(e for e in events if e.event_type == "LeewayGrantApplied")
        assert lga.payload()["applied_at"] == 99999

    def test_forbidden_event_also_emitted_not_suppressed(self) -> None:
        """Gate decisions are always recorded — even forbidden."""
        from fossic import ReadQuery

        store, emitter = _make_store_and_emitter("cycle_forb2")
        trigger_id = _stub_event(emitter, "cycle_forb2")
        decision = _gate_empty().evaluate(_action("retrieve_from_memory", "cycle_forb2"))
        emit_leeway_grant_applied(emitter, decision, trigger_id)

        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/sess_001"))
        lga_events = [e for e in events if e.event_type == "LeewayGrantApplied"]
        assert len(lga_events) == 1
