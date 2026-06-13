"""CycleRuntime — Phase 8 Step 2 composition class.

Binds Phase 6 evaluation pipeline, Phase 7 governance gate, and Phase 8
config/clutch/stop-conditions into a single synchronous cycle execution.

D7: strictly single-threaded. No async, no threading. The cycle blocks
until completion (accept, stop, cap_reached, or error).

D2: episode record write is STUBBED (record_id generated but no DB write).
Awaiting brainstorm resolution on memory_records FK strategy.
"""

from __future__ import annotations

import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cerebra.cognition._constants import ELEVATED_SALIENCE
from cerebra.cognition.clutch_stub import ClutchContext, ClutchStubEngine
from cerebra.cognition.cycle_config import CycleConfig, render_template
from cerebra.cognition.episode_writer import EpisodeWriter
from cerebra.cognition.evaluation import EvaluationComposer, emit_evaluation_events
from cerebra.cognition.event_emitter import EventEmitter
from cerebra.cognition.llm_adapter import ClassificationError, LLMAdapter
from cerebra.cognition.predictions import (
    PredictionInput,
    PredictionPipeline,
    emit_outcome_recorded,
    emit_prediction_made,
    write_outcome,
    write_prediction,
)
from cerebra.cognition.session import RuntimeSession
from cerebra.cognition.signals import SignalEvaluator
from cerebra.cognition.stop_conditions import CycleState, StopConditionEvaluator
from cerebra.cognition.working_memory import WorkingMemory, get_active_session
from cerebra.governance.defaults import DEFAULT_CONSTITUTIONAL_RULES, DEFAULT_LEEWAY_RULES
from cerebra.governance.gate_events import emit_leeway_grant_applied
from cerebra.governance.pre_action_gate import LeewayPreActionGate
from cerebra.governance.types import ProposedAction
from cerebra.retrieval.context_packet import (
    ContextPacket,
    build_abstained_packet,
    build_context_packet,
    render_text,
)
from cerebra.retrieval.planner import query_plan
from cerebra.retrieval.scorer import score_candidates
from cerebra.retrieval.trace import TraceData
from cerebra.retrieval.traversal import run_traversal
from cerebra.storage.fossic_store import FossicStore

_RETRIEVAL_FLOOR = 0.35


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class StepResult:
    step_id: str
    step_name: str
    step_index: int
    output_text: str
    composite_score: float
    clutch_action: str
    failed: bool = False
    error_message: str | None = None


@dataclass
class CycleResult:
    cycle_id: str
    session_id: str
    total_steps: int
    outcome: str  # "accept" | "stop" | "cap_reached" | "error"
    final_output: str | None
    step_results: list[StepResult] = field(default_factory=list)


class CycleRuntime:
    """Synchronous cycle execution engine.

    Usage:
        runtime = CycleRuntime(config, session, db_path, store, llm)
        result = runtime.run()
    """

    def __init__(
        self,
        config: CycleConfig,
        session: RuntimeSession,
        db_path: Path,
        store: FossicStore,
        llm: LLMAdapter,
        opened_event_id: bytes | None = None,
        episode_writer: EpisodeWriter | None = None,
    ) -> None:
        self.config = config
        self.session = session
        self.db_path = db_path
        self.store = store
        self.llm = llm
        self._opened_event_id = opened_event_id  # DEV-018: causation for CycleStarted
        self._episode_writer = episode_writer or EpisodeWriter(db_path)
        self._gate = LeewayPreActionGate(DEFAULT_LEEWAY_RULES, DEFAULT_CONSTITUTIONAL_RULES)
        self._signal_evaluator = SignalEvaluator(llm)
        self._eval_composer = EvaluationComposer()
        self._pred_pipeline = PredictionPipeline(self._eval_composer)
        self._interrupted = False

        # D7: install signal handlers for graceful interrupt
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        self._interrupted = True

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self) -> CycleResult:
        """Execute the cycle synchronously. Returns CycleResult when done."""
        cycle_id = _generate_id("cycle")
        session_id = self.session.session_id
        emitter = EventEmitter(self.store, session_id, cycle_id)

        # CycleStarted — causation chains to SessionOpened if event_id provided (DEV-018)
        cycle_started_id = emitter.emit_cycle_event(
            "CycleStarted",
            {
                "session_id": session_id,
                "cycle_id": cycle_id,
                "cycle_config": self.config.name,
                "started_at": _now_ms(),
            },
            causation_id=self._opened_event_id,
            indexed_tags={
                "session_id": session_id,
                "cycle_id": cycle_id,
                "cycle_config": self.config.name,
            },
        )

        stop_evaluator = StopConditionEvaluator(self.config)
        clutch_engine = ClutchStubEngine(self.config)

        current_step_pos = 0        # position in config.steps (advances on accept)
        total_steps_run = 0         # total LLM executions
        step_pos_outputs: dict[int, str] = {}  # accepted output by step position
        recent_composites: list[float] = []   # all composites in order
        within_cycle_composites: list[float] = []
        last_per_signal: dict[str, float] | None = None
        last_clutch_action: str | None = None
        last_clutch_decision_id: bytes = cycle_started_id
        all_completed = False
        outcome = "cap_reached"
        final_output: str | None = None
        step_results: list[StepResult] = []

        while True:
            # ── Stop condition check (before each step) ──────────────────────
            cycle_state = CycleState(
                steps_run=total_steps_run,
                all_steps_completed=all_completed,
                recent_composites=list(recent_composites),
                explicit_stop=(last_clutch_action == "stop"),
                user_interrupted=self._interrupted,
            )
            should_stop, _cond_name = stop_evaluator.check(cycle_state)
            if should_stop:
                if all_completed:
                    outcome = "accept"
                    final_output = step_pos_outputs.get(len(self.config.steps) - 1)
                elif last_clutch_action == "stop":
                    outcome = "stop"
                else:
                    outcome = "cap_reached"
                break

            # ── Resolve current step definition ──────────────────────────────
            step = self.config.steps[current_step_pos]
            step_id = _generate_id("step")
            step_type = "refine" if last_clutch_action == "refine" else "generate"

            # ── StepStarted ──────────────────────────────────────────────────
            step_started_id = emitter.emit_cycle_event(
                "StepStarted",
                {
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "step_index": total_steps_run,
                    "started_at": _now_ms(),
                    "step_type": step_type,
                },
                causation_id=last_clutch_decision_id,
                indexed_tags={
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "step_type": step_type,
                },
            )

            # ── ContextPacket ─────────────────────────────────────────────────
            packet = self._build_context_packet(
                current_step_pos, step_pos_outputs
            )
            context_built_id = emitter.emit_cycle_event(
                "ContextPacketBuilt",
                {
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "packet_id": packet.context_packet_id,
                    "selected_count": packet.selected_count,
                    "packet_version": packet.packet_version,
                    "abstained": packet.is_abstained,
                },
                causation_id=step_started_id,
                indexed_tags={
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "abstained": packet.is_abstained,
                },
            )

            # ── PredictionMade (causation = StepStarted, not ContextPacketBuilt)
            pred_input = PredictionInput(
                session_id=session_id,
                cycle_id=cycle_id,
                step_id=step_id,
                prior_step_composites=list(within_cycle_composites),
                prior_step_per_signal=last_per_signal,
            )
            prediction = self._pred_pipeline.predict(pred_input)
            write_prediction(self.db_path, prediction)
            emit_prediction_made(emitter, prediction, step_started_id)

            # ── Prompt rendering ──────────────────────────────────────────────
            prior_steps_list = [
                step_pos_outputs.get(i, "") for i in range(current_step_pos)
            ]
            prior_step_output = prior_steps_list[-1] if prior_steps_list else None
            tpl_context: dict[str, Any] = {
                "goal": self.session.goal,
                "step_index": current_step_pos,
                "step_name": step.name,
                "session_id": session_id,
                "cycle_id": cycle_id,
                "retrieved_context": render_text(packet) if not packet.is_abstained else "",
                "prior_step_output": prior_step_output,
                "prior_steps": prior_steps_list,
            }
            prompt = render_template(step.prompt_template.template, tpl_context)

            # ── LLM call with retry (D5) ──────────────────────────────────────
            output_text, llm_failed, llm_error = self._call_llm_with_retry(
                prompt, session_id, cycle_id, step_id, emitter, context_built_id
            )

            if llm_failed:
                # Treat as composite=0.0 for Clutch; skip evaluation events
                clutch_ctx = ClutchContext(
                    step_index=current_step_pos,
                    step_count=len(self.config.steps),
                    composite_score=0.0,
                    last_clutch_action=last_clutch_action,
                    total_steps_run=total_steps_run,
                )
                clutch_decision = clutch_engine.decide(clutch_ctx)
                last_clutch_decision_id = emitter.emit_cycle_event(
                    "ClutchDecisionMade",
                    {
                        "session_id": session_id,
                        "cycle_id": cycle_id,
                        "step_id": step_id,
                        "decision_id": _generate_id("decision"),
                        "action": clutch_decision.action,
                        "rule_matched": clutch_decision.rule_matched,
                        "decided_at": _now_ms(),
                    },
                    indexed_tags={
                        "session_id": session_id,
                        "cycle_id": cycle_id,
                        "step_id": step_id,
                        "action": clutch_decision.action,
                    },
                )
                recent_composites.append(0.0)
                within_cycle_composites.append(0.0)
                last_clutch_action = clutch_decision.action
                total_steps_run += 1
                step_results.append(
                    StepResult(
                        step_id=step_id,
                        step_name=step.name,
                        step_index=current_step_pos,
                        output_text="",
                        composite_score=0.0,
                        clutch_action=clutch_decision.action,
                        failed=True,
                        error_message=llm_error,
                    )
                )
                if clutch_decision.action == "stop":
                    outcome = "stop"
                    break
                continue

            # ── StepExecuted ─────────────────────────────────────────────────
            llm_model = getattr(self.llm, "_model", "unknown")
            step_executed_id = emitter.emit_cycle_event(
                "StepExecuted",
                {
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "executed_at": _now_ms(),
                    "llm_model": llm_model,
                    "prompt_tokens": len(prompt) // 4,
                    "completion_tokens": len(output_text) // 4,
                    "output_text": output_text,
                },
                causation_id=context_built_id,
                indexed_tags={
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "llm_model": llm_model,
                },
            )

            # ── Signal evaluation + composition ───────────────────────────────
            signal_context: dict[str, Any] = {
                "goal": self.session.goal,
                "step_name": step.name,
            }
            signal_scores = self._signal_evaluator.evaluate_all(
                output_text, signal_context
            )
            eval_packet = self._eval_composer.compose(
                signal_scores, session_id, cycle_id, step_id
            )
            eval_composed_id = emit_evaluation_events(
                emitter, signal_scores, eval_packet, step_executed_id
            )

            # ── Outcome recording ─────────────────────────────────────────────
            outcome_record = self._pred_pipeline.resolve(prediction, eval_packet)
            write_outcome(self.db_path, outcome_record)
            outcome_event_id, _ = emit_outcome_recorded(
                emitter, outcome_record, eval_composed_id
            )

            composite_score = eval_packet.composite_score
            recent_composites.append(composite_score)
            within_cycle_composites.append(composite_score)
            last_per_signal = dict(eval_packet.per_signal_scores)

            # ── Clutch decision ───────────────────────────────────────────────
            clutch_ctx = ClutchContext(
                step_index=current_step_pos,
                step_count=len(self.config.steps),
                composite_score=composite_score,
                last_clutch_action=last_clutch_action,
                total_steps_run=total_steps_run,
            )
            clutch_decision = clutch_engine.decide(clutch_ctx)
            decision_id = _generate_id("decision")
            last_clutch_decision_id = emitter.emit_cycle_event(
                "ClutchDecisionMade",
                {
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "decision_id": decision_id,
                    "action": clutch_decision.action,
                    "rule_matched": clutch_decision.rule_matched,
                    "decided_at": _now_ms(),
                    "evaluation_id": eval_packet.evaluation_id,
                },
                causation_id=outcome_event_id,
                indexed_tags={
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "step_id": step_id,
                    "action": clutch_decision.action,
                },
            )

            total_steps_run += 1
            last_clutch_action = clutch_decision.action
            step_results.append(
                StepResult(
                    step_id=step_id,
                    step_name=step.name,
                    step_index=current_step_pos,
                    output_text=output_text,
                    composite_score=composite_score,
                    clutch_action=clutch_decision.action,
                )
            )

            # ── Action dispatch ───────────────────────────────────────────────
            if clutch_decision.action == "accept":
                # Gate the memory write (D3: MemoryWriteFromCycle is state-mutating)
                proposed = ProposedAction(
                    action_name="write_to_episodic_memory",
                    session_id=session_id,
                    cycle_id=cycle_id,
                    step_id=step_id,
                )
                gate_decision = self._gate.evaluate(proposed)
                leeway_id = emit_leeway_grant_applied(
                    emitter, gate_decision, last_clutch_decision_id
                )

                if gate_decision.final_decision == "permitted":
                    # D1 closed (v0.3.5a): real episode DB write to cycle_episode_records
                    wm_session_id = self._get_active_working_memory_session()
                    cited_ids = self._extract_citations(output_text)

                    record_id = self._episode_writer.write(
                        content=output_text,
                        runtime_session_id=session_id,
                        cycle_id=cycle_id,
                        step_id=step_id,
                        step_name=step.name,
                        working_memory_session_id=wm_session_id,
                        leeway_grant_event_id=leeway_id,
                        cited_record_ids=cited_ids,
                        metadata={
                            "step_index": current_step_pos,
                            "step_executions_count": total_steps_run,
                        },
                    )

                    self._boost_salience_for_cited(cited_ids, wm_session_id)

                    emitter.emit_cycle_event(
                        "MemoryWriteFromCycle",
                        {
                            "session_id": session_id,
                            "cycle_id": cycle_id,
                            "step_id": step_id,
                            "record_id": record_id,
                            "write_reason": "accept",
                            "content_summary": output_text[:200],
                            "written_at": _now_ms(),
                            "cited_record_ids": cited_ids,
                            "working_memory_session_id": wm_session_id,
                            "table_target": "cycle_episode_records",
                        },
                        causation_id=leeway_id,
                        indexed_tags={
                            "session_id": session_id,
                            "cycle_id": cycle_id,
                            "step_id": step_id,
                            "record_id": record_id,
                            "write_reason": "accept",
                        },
                    )

                step_pos_outputs[current_step_pos] = output_text
                current_step_pos += 1
                if current_step_pos >= len(self.config.steps):
                    all_completed = True
                    final_output = output_text

            elif clutch_decision.action == "stop":
                outcome = "stop"
                break
            # else: refine, critique, explore, etc. — stay on same step

        # ── CycleCompleted ────────────────────────────────────────────────────
        cycle_completed_id = emitter.emit_cycle_event(
            "CycleCompleted",
            {
                "session_id": session_id,
                "cycle_id": cycle_id,
                "completed_at": _now_ms(),
                "outcome": outcome,
                "total_steps": total_steps_run,
            },
            causation_id=last_clutch_decision_id,
            indexed_tags={"session_id": session_id, "cycle_id": cycle_id, "outcome": outcome},
        )

        # ── SessionFlushed ────────────────────────────────────────────────────
        _OUTCOME_MAP: dict[str, str] = {
            "accept": "accepted",
            "stop": "user_requested",
            "cap_reached": "cap_reached",
            "error": "error",
        }
        emitter.emit_cycle_event(
            "SessionFlushed",
            {
                "session_id": session_id,
                "cycle_id": cycle_id,
                "total_cycles": 1,
                "total_steps": total_steps_run,
                "flushed_at": _now_ms(),
                "final_outcome": _OUTCOME_MAP.get(outcome, outcome),
                "consolidation_pending": True,
            },
            causation_id=cycle_completed_id,
            indexed_tags={
                "session_id": session_id,
                "cycle_id": cycle_id,
                "final_outcome": _OUTCOME_MAP.get(outcome, outcome),
            },
        )

        emitter.trigger_lattice_snapshots_at_cycle_boundary(set())

        return CycleResult(
            cycle_id=cycle_id,
            session_id=session_id,
            total_steps=total_steps_run,
            outcome=outcome,
            final_output=final_output,
            step_results=step_results,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_active_working_memory_session(self) -> str | None:
        """Return active Phase 5 working memory session_id for this vault, or None.

        Per Decision 1: episodes persist even without an active WM session.
        The nullable FK working_memory_session_id handles the None case.
        """
        return get_active_session(self.db_path, str(self.session.vault_path))

    def _extract_citations(self, output_text: str) -> list[str]:
        """Best-effort v0.1: extract memory_records record_ids cited in output.

        Looks for 'rec_<12hexchars>' patterns. Empty list is normal — most LLM
        outputs won't use the exact citation format in v0.1.
        """
        import re
        return re.findall(r"\brec_[0-9a-f]{12}\b", output_text)

    def _boost_salience_for_cited(
        self,
        cited_record_ids: list[str],
        wm_session_id: str | None,
    ) -> None:
        """Promote cited memory_records into working memory with elevated salience.

        Per Decision 3: salience boost via WorkingMemory.promote() with
        ELEVATED_SALIENCE. Silent skip when no WM session active or record missing.
        """
        if not cited_record_ids or wm_session_id is None:
            return

        import sqlite3 as _sqlite3
        wm = WorkingMemory(self.db_path, wm_session_id)
        conn = _sqlite3.connect(self.db_path)
        conn.row_factory = _sqlite3.Row
        try:
            for record_id in cited_record_ids:
                row = conn.execute(
                    "SELECT record_id, content FROM memory_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    continue
                try:
                    wm.promote(
                        slot_type="context",
                        record_id=record_id,
                        content_summary=row["content"][:200],
                        salience_score=ELEVATED_SALIENCE,
                        is_pinned=False,
                    )
                except Exception:
                    pass  # silent: eviction failure, slot full of pinned items, etc.
        finally:
            conn.close()

    def _build_context_packet(
        self,
        current_step_pos: int,
        step_pos_outputs: dict[int, str],
    ) -> ContextPacket:
        """Run retrieval pipeline and return ContextPacket. Per D1: fresh per step."""
        # D1: step 0 queries on goal; subsequent steps include a brief prior summary
        goal = self.session.goal
        if current_step_pos == 0 or not step_pos_outputs:
            query = goal
        else:
            last_output = step_pos_outputs.get(current_step_pos - 1, "")
            summary = last_output[:200]
            query = f"{goal}\n{summary}"

        started = int(time.time())
        plan = query_plan(query, self.db_path)
        raw = run_traversal(plan, self.db_path)
        scored = score_candidates(raw, plan, self.db_path)
        finished = int(time.time())

        above_floor = [c for c in scored if c.score.composite >= _RETRIEVAL_FLOOR]
        trace = TraceData(
            plan=plan,
            scored_all=scored,
            floor=_RETRIEVAL_FLOOR,
            started_at=started,
            finished_at=finished,
            duration_ms=max(0, (finished - started) * 1000),
        )

        if above_floor:
            return build_context_packet(trace, above_floor, self.db_path)

        best = max((c.score.composite for c in scored), default=0.0)
        return build_abstained_packet(trace, best_score_seen=best)

    def _call_llm_with_retry(
        self,
        prompt: str,
        session_id: str,
        cycle_id: str,
        step_id: str,
        emitter: EventEmitter,
        context_built_id: bytes,
    ) -> tuple[str, bool, str | None]:
        """Single retry with 5s backoff per D5. Returns (output, failed, error_msg)."""
        try:
            return self.llm.complete(prompt), False, None
        except ClassificationError:
            time.sleep(5)
            try:
                return self.llm.complete(prompt), False, None
            except ClassificationError as exc:
                error_str = str(exc)
                emitter.emit_cycle_event(
                    "StepExecutionFailed",
                    {
                        "session_id": session_id,
                        "cycle_id": cycle_id,
                        "step_id": step_id,
                        "error_type": "LLMError",
                        "error_message": error_str,
                        "retry_count": 1,
                        "failed_at": _now_ms(),
                    },
                    causation_id=context_built_id,
                    indexed_tags={
                        "session_id": session_id,
                        "cycle_id": cycle_id,
                        "step_id": step_id,
                    },
                )
                return "", True, error_str
