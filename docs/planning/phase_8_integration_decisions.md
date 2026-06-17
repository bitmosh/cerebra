# Phase 8 Integration Decisions

*Seven concrete decisions that determine how Step 2's cycle runtime composes the Phase 6 and Phase 7 infrastructure into a working cycle. Each decision is specified with reasoning so bandit doesn't have to guess during implementation.*

---

## D1 — ContextPacket composition pattern

**Decision:** Each step in the cycle builds its own fresh ContextPacket via Cerebra's existing retrieval pipeline (`cerebra.retrieval.run_query()`).

**Specifics:**
- Step 1 (understand_goal): query = the user's goal text
- Subsequent steps: query = goal + brief summary of prior step output (~200 char summary, not full output)
- Retrieval pipeline returns a ContextPacket per Phase 4's existing semantics
- If retrieval abstains (best score below floor), the ContextPacket is empty but the step proceeds anyway with just the prompt template + goal
- The step's prompt template receives `retrieved_context` as formatted text (records' contents, no metadata clutter)

**Reasoning:** Cerebra's retrieval pipeline is well-tested and produces the right shape. Building ContextPacket more cheaply (e.g., reusing prior step's retrieval) would couple cycle runtime to retrieval internals. Each step gets fresh retrieval = fresh grounding in current memory state, which matters because the prior step's MemoryWriteFromCycle may have added new memory the next step should consult.

**Performance note:** Each retrieval is ~10-50ms typical. Five steps = 50-250ms of retrieval overhead per cycle. Acceptable.

---

## D2 — Working memory update content

**Decision:** After each accepted step, the cycle writes two things to memory:

1. **An episode record** capturing the step's output. `subject_type="episode"`, content is the full step output text, indexed for future retrieval.
2. **Salience boosts** for memory records cited in the step output. The existing Phase 5 working memory promotion path runs automatically — cited records have their `is_pinned` reaffirmed or their salience incremented per existing rules.

**The cycle emits a `MemoryWriteFromCycle` event** after the episode record is written. The event payload includes the new record_id, the step_id that produced it, and which prior records were cited.

**Reasoning:** Episode records make cycle outputs retrievable for future cycles in the session (and across sessions via consolidation). Salience boosts on cited records reinforce what the cycle is consulting. Both compose with Phase 5's existing working memory mechanics without modification.

**What's NOT written:** Raw LLM responses (we keep only the step's structured output text), tool call traces (no tools in v0.1), or signal evaluation details (those live in fossic events, not memory records).

---

## D3 — Which actions get gated by the leeway pre-action gate

**Decision:** v0.1 gates a focused set of state-mutating actions:

**Gated (LeewayGrantApplied fires before action):**
- `MemoryWriteFromCycle` — mutates memory state
- `branch_creation` — creates parallel execution (Phase 9+, but reserved here)
- `continuation_spawn` — creates a new session via re-injection (Phase 9 territory)

**NOT gated (no LeewayGrantApplied):**
- `StepExecuted` — LLM call, no state mutation
- `SignalEvaluated` — read-only on output
- `EvaluationComposed` — pure function of signals
- `PredictionMade` / `OutcomeRecorded` — read-only computation
- `ClutchDecisionMade` — internal decision, not external action
- `CatalystArmSelected` — internal selection, not external action

**Reasoning:** Gating every event would be safety theater — most events are observations, not actions. The leeway gate exists to mediate actions that modify state or have external effects. v0.1 has no external-effect actions (no tool calls, no API requests), so the gated set is just state mutations.

**Causation pattern for gated actions:** Per `phase7_emission_pattern.md`, the sequence is `ClutchDecisionMade → LeewayGrantApplied → action_event`, with the action event's `causation_id` referencing the LeewayGrantApplied event ID. Defensive cross-reference (`leeway_grant_event_id` in action event payload) is included.

---

## D4 — Phase 8 Clutch stub behavior

**Decision:** Phase 8 ships `cerebra/cognition/clutch_stub.py` with a minimal rule cascade that the full Phase 9 ClutchEngine will replace.

**Stub structure:**

```python
class ClutchStubEngine:
    """Phase 8 minimal Clutch. Replaced by full ClutchEngine in Phase 9."""

    def __init__(self, cycle_config: CycleConfig):
        self.rules = cycle_config.clutch_rules
        self.predicates = BUILTIN_PREDICATES

    def decide(self, context: ClutchContext) -> ClutchDecision:
        """Evaluate rules in order. First match wins. Default accept if no rule matches."""
        for rule in self.rules:
            predicate = self.predicates[rule.predicate_name]
            if predicate(context, rule.parameters):
                return ClutchDecision(
                    action=rule.action,
                    rule_matched=rule.name,
                    escalate_to_catalyst=False,  # v0.1: catalyst not invoked
                )
        return ClutchDecision(action="accept", rule_matched="default_no_match")
```

**The stub:**
- Reads `clutch_rules` from the cycle config (simple.planning.v0 has 4 rules)
- Evaluates rules in order, first match wins
- Returns ClutchDecision with the matched rule's action
- Never escalates to catalyst (Phase 9 introduces that)
- Defaults to `accept` if no rule matches (safety net)

**File naming:** `clutch_stub.py` not `clutch.py`. Phase 9 ships `clutch.py` with the full engine. Naming makes the stub status explicit.

**Reasoning:** The cycle needs Clutch decisions to terminate. Stubbing just enough logic (rule cascade + builtin predicates) means the cycle works end-to-end in Phase 8 without waiting for Phase 9. The stub interface matches what Phase 9 will replace, so the migration is mechanical.

---

## D5 — LLM error handling in the cycle loop

**Decision:** Single retry with 5-second backoff, then explicit failure event.

**Behavior:**
```python
try:
    output = llm_adapter.complete(prompt)
except LLMError:
    time.sleep(5)
    try:
        output = llm_adapter.complete(prompt)
    except LLMError as e:
        emit_step_execution_failed(step_id, error=str(e))
        # Treat as a step with composite_score=0 for Clutch evaluation
        # Clutch will likely refine (which retries the step) or stop (catastrophic)
        return StepResult(failed=True, error=e)
```

**Specifics:**
- One retry, fixed 5-second backoff
- After retry failure, emit `StepExecutionFailed` event (new event type — add to vocabulary spec in Step 2 deviation log)
- The cycle treats failed steps as composite_score=0 for Clutch evaluation purposes
- Clutch's `refine` action retries the step (third attempt at the LLM call); `stop` terminates the cycle
- The failure is logged and recorded; cycles don't crash silently

**Reasoning:** LLM failures are operationally expected (network issues, model timeouts, rate limits). Retry handles transient issues; explicit failure events surface persistent issues to the user. Avoiding fancy retry logic (exponential backoff, fallback adapters) keeps v0.1 simple — v0.2 adds sophistication if needed.

**New event type required:** `StepExecutionFailed` joins the Phase 6 vocabulary. Payload: `{session_id, cycle_id, step_id, error_type, error_message, retry_count, failed_at}`. Document as Step 2 deviation since it wasn't in the original vocabulary spec.

---

## D6 — `cerebra run-cycle` CLI argument surface

**Decision:** The CLI surface for v0.1:

```bash
cerebra run-cycle <config_name> --goal "<text>" [options]
```

**Required arguments:**
- `<config_name>` (positional) — cycle config name, e.g., `simple.planning.v0`
- `--goal "<text>"` — the user-provided goal

**Optional arguments:**
- `--vault <path>` — vault path (defaults to `CEREBRA_VAULT` env var, then config file)
- `--continue <session_id>` — resume from prior session via continuation bundle (Phase 9 wires this; v0.1 CLI accepts the flag and stubs behavior)
- `--max-steps <N>` — override cycle config's `max_steps`
- `--dry-run` — parse and validate config without running, exit with status
- `--quiet` / `--verbose` — output verbosity for the live stream

**Output behavior:**
- Streams cycle progress to stdout: each event's type and key payload fields
- On accept outcome: prints the final step's output to stdout
- On stop outcome: prints "Cycle stopped: <reason>" to stderr
- On cap_reached: prints "Max steps reached without acceptance" to stderr
- On error outcome: prints error details to stderr

**Exit codes:**
- `0` — accept outcome (cycle completed normally)
- `1` — stop outcome (Clutch decided to terminate)
- `2` — cap_reached outcome (max_steps hit)
- `3` — error (LLM failure, config error, system issue)

**Reasoning:** Standard CLI surface — required positional + required flag + sensible defaults via env var. `--continue` stubs in v0.1 because the continuation flow lands in Phase 9, but the flag is reserved so v0.1 users get clear error messages instead of "unknown flag" surprises.

---

## D7 — Concurrent execution boundary

**Decision:** v0.1 cycle runtime is **strictly single-threaded**.

**Specifics:**
- The cycle runs in the calling Python thread (CLI invocation thread)
- No `asyncio`, no `threading`, no `multiprocessing` in cycle code
- All events emit through one EventEmitter instance on the calling thread
- LLM calls block; signal evaluations block; the cycle blocks until completion
- Signal handlers (SIGINT/SIGTERM) are installed for graceful interrupt — they set a flag the cycle loop checks at step boundaries

**What this means for fossic:**
- All `store.append()` calls happen on the cycle thread, sequentially
- Causation chains are preserved trivially (single-threaded sequential emission per Phase 7's discipline)
- No locks needed in Cerebra code; fossic handles its own internal concurrency

**What this means for the witness layer (v0.2):**
- The witness layer (when it ships) runs in a separate process or async task
- It subscribes to fossic streams independently
- It does NOT interleave with cycle execution — they're entirely decoupled via fossic's subscriber model
- The cycle doesn't know subscribers exist; the witness doesn't block cycle execution

**Reasoning:** Concurrent cycle execution would introduce complexity (locks, async error handling, race conditions in event ordering) without v0.1 benefit. Single-threaded is correct for the cycle's semantic structure (steps are sequentially ordered) and matches the LeewayGrantApplied causation discipline. v0.2 can introduce daemon mode (`cerebra serve`) with proper async at the IPC boundary; the cycle itself stays sequential.

**Concrete code rule:** No `async def` in cycle runtime code. No `threading.Thread` in cycle runtime code. The cycle is a `while not should_stop()` loop with synchronous calls.

---

## Cross-cutting implications

These seven decisions compose to a specific picture of how Step 2 works:

The cycle runs synchronously in the user's terminal. For each step, it builds a fresh ContextPacket from retrieval, calls Ollama with the prompt template + retrieved context, gets back output, evaluates with six signals, composes composite, computes prediction error against the prediction made before the step, asks the Clutch stub to decide (accept/refine/stop), and on accept, runs the leeway gate to permit the memory write, then writes the episode record. Move to next step. Loop until stop condition fires.

That's the cycle in one paragraph. Everything else is implementation detail.

**Decisions NOT covered here that bandit may need to surface:**

- Specific summarization logic for "brief summary of prior step output" in D1 (probably 200 chars of truncated last sentence; Step 2 implementation detail)
- Indexed_tags strategy for cycle events (probably matches the vocabulary spec; check there)
- Where the ClutchContext type lives (cerebra/cognition/clutch_stub.py or cerebra/cognition/clutch_types.py — bandit's call)
- How `--continue` stub fails in v0.1 (probably "Continuation not yet supported — coming in Phase 9" with non-zero exit code)
- Whether the cycle prints intermediate step outputs to stdout (probably yes with `--verbose`, no by default)

These are step-level implementation choices, not architectural decisions. Bandit makes them and logs as deviations only if they surprise the design.

---

*These seven decisions plus the cycle config schema and simple.planning.v0 content are the complete input set for Phase 8 Step 2. Bandit reads all three documents at Step 2 kickoff and implements against them.*
