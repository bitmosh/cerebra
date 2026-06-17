# Cycle Config Schema (v0.1)

*Type contract for cycle configurations. Step 2 of Phase 8 implements the CycleConfig loader against this schema. Forward-compatible for v0.2+ extensions.*

---

## Top-level type

```python
@dataclass(frozen=True)
class CycleConfig:
    """Full configuration for a cycle."""
    name: str                              # e.g., "simple.planning.v0"
    version: int                           # schema version, currently 1
    description: str                       # human-readable description
    steps: list[CycleStep]                 # ordered sequence of steps
    max_steps: int                         # total step executions allowed (incl. refinements)
    stop_conditions: list[StopCondition]   # any condition stops the cycle
    clutch_rules: list[ClutchRule]         # decision cascade, evaluated in order
```

CycleConfig is **frozen** — once loaded, immutable. Mutations require loading a new config.

`name` and `version` together form the canonical identifier. Future versions of a cycle (e.g., `simple.planning.v1`) can coexist; loader resolves by `name` with `version` as tiebreaker.

`steps` is an **ordered sequence**. The Clutch decision tree determines which step runs next (accept advances, refine repeats current, stop terminates). The order in `steps` is the natural progression when Clutch keeps accepting.

## CycleStep

```python
@dataclass(frozen=True)
class CycleStep:
    """Specification of one step in a cycle."""
    name: str                              # unique within cycle (e.g., "understand_goal")
    description: str                       # human-readable description
    prompt_template: StepPromptTemplate    # how the LLM is prompted
    # v0.2 extension point: per-step signal weight overrides
    # v0.1 always uses cycle-level default weights
```

Step names must be unique within a cycle. The loader validates this.

`description` is for human readability — appears in PASS COMPLETE logs and the `cerebra run-cycle` output stream.

## StepPromptTemplate

```python
@dataclass(frozen=True)
class StepPromptTemplate:
    """Prompt template specification for a cycle step."""
    template: str                          # Jinja2 template string
    expected_output_format: str            # "free_form" | "json"
    output_schema: dict[str, Any] | None = None  # JSON schema if expected_output_format == "json"
```

**Template variables available to all steps:**
- `goal` — the user-provided goal (immutable through the cycle)
- `step_index` — 0-based index in the cycle
- `step_name` — the step's name
- `session_id`, `cycle_id` — for traceability
- `retrieved_context` — formatted text from the ContextPacket
- `prior_step_output` — text output from the immediately previous step (None for step 0)
- `prior_steps` — list of all prior step outputs in this cycle (in order)

For Jinja2 templates, all variables are passed in `render_context`. Missing variables raise (no silent default substitution).

**Output formats:**
- `free_form`: LLM produces unstructured text. SignalEvaluator scores it.
- `json`: LLM produces JSON matching `output_schema`. Useful for steps that need structured outputs (e.g., a critique step producing `{"issues": [...], "severity": int}`). The cycle runtime validates against schema before passing to next step.

For v0.1, all simple.planning.v0 steps use `free_form`. JSON-mode steps are forward-compatible.

## StopCondition

```python
@dataclass(frozen=True)
class StopCondition:
    """A condition under which the cycle terminates."""
    name: str                              # human-readable identifier
    type: str                              # one of STOP_CONDITION_TYPES
    parameters: dict[str, Any]             # type-specific parameters
```

Stop conditions are evaluated at the **start of each step** (before LLM call). If any condition is satisfied, the cycle terminates with the corresponding outcome.

**Stop condition types in v0.1:**

```python
STOP_CONDITION_TYPES = {
    "max_steps_reached": "Cycle has executed >= cycle.max_steps total steps",
    "all_steps_completed": "Cycle has completed all steps in steps[] (last accept)",
    "composite_floor_consecutive": "Composite score < threshold for N consecutive steps",
    "explicit_clutch_stop": "Clutch decision was 'stop' on last step",
    "user_interrupt": "User sent SIGINT/SIGTERM during cycle",
}
```

`parameters` carries type-specific config:
- `max_steps_reached`: `{}` (uses cycle.max_steps)
- `all_steps_completed`: `{}` (just checks completion flag)
- `composite_floor_consecutive`: `{"threshold": 0.3, "consecutive_count": 2}`
- `explicit_clutch_stop`: `{}` (checked when Clutch returns "stop")
- `user_interrupt`: `{}` (signal-based, set by signal handler)

The cycle runtime handles signal_handler installation for `user_interrupt`. Other types are checked declaratively.

## ClutchRule

```python
@dataclass(frozen=True)
class ClutchRule:
    """A single rule in the Clutch decision cascade."""
    name: str                              # human-readable identifier
    description: str
    predicate_name: str                    # built-in predicate function name
    action: str                            # one of CLUTCH_ACTIONS
    parameters: dict[str, Any]             # predicate-specific parameters
```

For v0.1, predicates are **built-in by name** rather than user-defined. The Phase 8 stub Clutch engine has a registered set of predicates that ship with Cerebra. User-defined predicates are v0.2.

**Built-in predicates in v0.1:**

```python
BUILTIN_PREDICATES = {
    "at_terminal_step": "Returns True if current step is the last in cycle.steps",
    "composite_below_threshold": "Returns True if eval composite < parameter['threshold']",
    "composite_above_threshold": "Returns True if eval composite >= parameter['threshold']",
    "first_step": "Returns True if step_index == 0",
    "step_index_at": "Returns True if step_index == parameter['index']",
    "always": "Always returns True (fallback / default rule)",
}
```

Rules are evaluated in order. **First matching rule fires.** The cycle runtime then executes the action.

Example cycle's Clutch rules (matches simple.planning.v0):

```yaml
clutch_rules:
  - name: catastrophic_first_step
    description: First step scored very low — bail out
    predicate_name: composite_below_threshold
    action: stop
    parameters: {threshold: 0.3, with_constraint: first_step}

  - name: refine_low_score
    description: Score below floor — repeat the step
    predicate_name: composite_below_threshold
    action: refine
    parameters: {threshold: 0.3}

  - name: terminate_on_terminal
    description: At final step with reasonable score — accept and end
    predicate_name: at_terminal_step
    action: accept
    parameters: {min_composite: 0.5}

  - name: default_accept
    description: Otherwise accept and move on
    predicate_name: always
    action: accept
    parameters: {}
```

The first matching rule wins. Order matters.

## Validation rules

The CycleConfig loader runs these checks on load:

1. **Step name uniqueness:** No two steps in `steps[]` may have the same `name`.
2. **Max steps lower bound:** `max_steps >= len(steps)`. A cycle must be able to run all its declared steps.
3. **At least one stop condition:** `len(stop_conditions) >= 1`. Otherwise the cycle could run forever.
4. **At least one accept-action rule:** `any(r.action == "accept" for r in clutch_rules)`. Otherwise the cycle can never progress.
5. **All predicate_names are built-ins:** `all(r.predicate_name in BUILTIN_PREDICATES for r in clutch_rules)` for v0.1.
6. **All actions are in CLUTCH_ACTIONS:** `all(r.action in CLUTCH_ACTIONS for r in clutch_rules)`.
7. **Output schemas match expected_output_format:** If `expected_output_format == "json"`, `output_schema` must be present and valid JSON schema.

Validation errors raise `CycleConfigValidationError` with the specific failure reason. Loader is fail-fast.

## File format and storage

Cycle configs ship as **YAML files** in `cycles/` directory (vault-relative).

For v0.1: `cycles/simple.planning.v0.yaml` ships with Cerebra as the demonstration config.

Loader behavior:
- `CycleConfigLoader.load(name: str, vault_path: Path) -> CycleConfig`
- Searches vault's `cycles/` first, falls back to Cerebra's built-in `cycles/` directory
- Parses YAML, validates against schema, returns frozen CycleConfig

## v0.2 forward-compatibility extension points

These fields are NOT in v0.1 but will be added:

- `CycleConfig.signal_weights_override: dict[str, float] | None` — cycle-level weight override
- `CycleStep.signal_weight_override: dict[str, float] | None` — step-level weight override
- `CycleConfig.catalyst_vocabulary: list[CatalystArm] | None` — Phase 9 catalyst arms
- `CycleStep.prompt_template.input_schema: dict | None` — for structured input validation
- `ClutchRule.predicate_callable: str | None` — for user-defined predicates

Adding these in v0.2 won't break v0.1 configs. The validator treats missing fields as None.

---

*This is the type contract. Step 2 implements the loader, validator, and consumers against it. simple.planning.v0 is the v0.1 instantiation (see `simple_planning_v0_cycle_config.md`).*
