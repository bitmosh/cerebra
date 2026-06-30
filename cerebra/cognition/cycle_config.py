"""Cycle configuration schema, loader, and validator — Phase 8 Step 2.

Public API:
    CycleConfig, CycleStep, StepPromptTemplate, StopCondition, ClutchRule
    CycleConfigValidationError
    CycleConfigLoader.load(name, vault_path) -> CycleConfig
    render_template(template, context) -> str

YAML search order: vault's cycles/ first, then built-in cycles/ next to cerebra package.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cerebra.cognition._constants import (
    BUILTIN_PREDICATE_NAMES,
    BUILTIN_REINJECTION_PREDICATE_NAMES,
    CLUTCH_ACTIONS,
)

# Built-in cycles/ directory ships alongside the cerebra package at repo root.
_BUILTIN_CYCLES_DIR = Path(__file__).parent.parent.parent / "cycles"


class CycleConfigValidationError(ValueError):
    """Raised when a loaded cycle config fails validation."""


@dataclass(frozen=True)
class StepPromptTemplate:
    template: str
    expected_output_format: str  # "free_form" | "json"
    output_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class CycleStep:
    name: str
    description: str
    prompt_template: StepPromptTemplate
    role: str = ""


@dataclass(frozen=True)
class CatalystArm:
    """One selectable arm in the CatalystEngine bandit."""

    arm_id: str
    type: str
    mapped_action: str
    strategy_prompt: str


@dataclass(frozen=True)
class ReinjectionTrigger:
    """One re-injection trigger predicate in a cycle config."""

    name: str
    predicate: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StopCondition:
    name: str
    type: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ClutchRule:
    name: str
    description: str
    predicate_name: str
    action: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class CycleConfig:
    name: str
    version: int
    description: str
    steps: list[CycleStep]
    max_steps: int
    stop_conditions: list[StopCondition]
    clutch_rules: list[ClutchRule]
    composite_floor: float = 0.3  # Phase 9: floor for consecutive_steps_below_floor tracking
    catalyst_arms: list[CatalystArm] = field(default_factory=list)
    reinjection_triggers: list[ReinjectionTrigger] = field(default_factory=list)
    max_recursion_depth: int = 0  # 0 = no recursion; set > 0 to enable re-injection


def render_template(template: str, context: dict[str, Any]) -> str:
    """Render a Jinja2-compatible template with simple variable substitution.

    Supports {{ var }}, {{ var[N] }} (integer list indexing), and single-level
    {% if var %}...{% endif %} blocks. Missing variables render as empty string;
    if-blocks collapse to empty string when the variable is falsy.
    Does NOT support loops, nested conditionals, filters, or attribute access.
    """

    def _process_if_blocks(tmpl: str) -> str:
        def _replace_if(m: re.Match) -> str:  # type: ignore[type-arg]
            var_name = m.group(1).strip()
            block_content = m.group(2)
            val = context.get(var_name)
            return block_content if val else ""

        return re.sub(
            r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}",
            _replace_if,
            tmpl,
            flags=re.DOTALL,
        )

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        expr = m.group(1).strip()
        # List indexing: var[N]
        idx_match = re.match(r"^(\w+)\[(\d+)\]$", expr)
        if idx_match:
            var_name, idx_str = idx_match.group(1), idx_match.group(2)
            val = context.get(var_name)
            if not isinstance(val, list):
                return ""
            idx = int(idx_str)
            return str(val[idx]) if 0 <= idx < len(val) else ""
        # Simple variable
        val = context.get(expr)
        return "" if val is None else str(val)

    processed = _process_if_blocks(template)
    return re.sub(r"\{\{\s*(.*?)\s*\}\}", _replace, processed)


# ── Validation ────────────────────────────────────────────────────────────────


def _validate_config(config: CycleConfig) -> None:
    """Raise CycleConfigValidationError on any violation of the 8 spec rules."""
    # 1. Step name uniqueness
    names = [s.name for s in config.steps]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise CycleConfigValidationError(f"Duplicate step names: {dupes}")

    # 2. max_steps >= len(steps)
    if config.max_steps < len(config.steps):
        raise CycleConfigValidationError(
            f"max_steps ({config.max_steps}) must be >= number of steps ({len(config.steps)})"
        )

    # 3. At least one stop condition
    if not config.stop_conditions:
        raise CycleConfigValidationError("At least one stop condition is required")

    # 4. At least one accept-action rule
    if not any(r.action == "accept" for r in config.clutch_rules):
        raise CycleConfigValidationError("At least one clutch rule must have action='accept'")

    # 5. All predicate_names are built-ins
    for rule in config.clutch_rules:
        if rule.predicate_name not in BUILTIN_PREDICATE_NAMES:
            raise CycleConfigValidationError(
                f"Unknown predicate '{rule.predicate_name}' in rule '{rule.name}'. "
                f"Built-in predicates: {sorted(BUILTIN_PREDICATE_NAMES)}"
            )

    # 6. All actions are in CLUTCH_ACTIONS
    for rule in config.clutch_rules:
        if rule.action not in CLUTCH_ACTIONS:
            raise CycleConfigValidationError(
                f"Unknown action '{rule.action}' in rule '{rule.name}'. "
                f"Valid actions: {sorted(CLUTCH_ACTIONS)}"
            )

    # 7. JSON schema present when expected_output_format='json'
    for step in config.steps:
        tpl = step.prompt_template
        if tpl.expected_output_format == "json" and tpl.output_schema is None:
            raise CycleConfigValidationError(
                f"Step '{step.name}' has expected_output_format='json' "
                "but output_schema is missing"
            )

    # 8. Catalyst arm IDs must be unique (if any)
    arm_ids = [a.arm_id for a in config.catalyst_arms]
    if len(arm_ids) != len(set(arm_ids)):
        dupes = sorted({aid for aid in arm_ids if arm_ids.count(aid) > 1})
        raise CycleConfigValidationError(f"Duplicate catalyst arm IDs: {dupes}")

    # 9. Reinjection trigger predicates must be known
    for trigger in config.reinjection_triggers:
        if trigger.predicate not in BUILTIN_REINJECTION_PREDICATE_NAMES:
            raise CycleConfigValidationError(
                f"Unknown reinjection predicate '{trigger.predicate}' in trigger "
                f"'{trigger.name}'. Known predicates: "
                f"{sorted(BUILTIN_REINJECTION_PREDICATE_NAMES)}"
            )

    # 10. max_recursion_depth must be non-negative; triggers require depth > 0
    if config.max_recursion_depth < 0:
        raise CycleConfigValidationError(
            f"max_recursion_depth must be >= 0; got {config.max_recursion_depth}"
        )
    if config.reinjection_triggers and config.max_recursion_depth == 0:
        raise CycleConfigValidationError(
            "reinjection_triggers defined but max_recursion_depth is 0 (recursion disabled). "
            "Set max_recursion_depth > 0 to enable re-injection."
        )


# ── Parser ────────────────────────────────────────────────────────────────────


def _parse_config(data: dict[str, Any]) -> CycleConfig:
    """Parse a raw YAML dict into a validated CycleConfig. Raises on invalid data."""
    steps: list[CycleStep] = []
    for s in data.get("steps", []):
        tpl_data = s["prompt_template"]
        tpl = StepPromptTemplate(
            template=tpl_data["template"],
            expected_output_format=tpl_data.get("expected_output_format", "free_form"),
            output_schema=tpl_data.get("output_schema"),
        )
        steps.append(
            CycleStep(
                name=s["name"],
                description=s.get("description", ""),
                prompt_template=tpl,
                role=s.get("role", ""),
            )
        )

    catalyst_arms: list[CatalystArm] = [
        CatalystArm(
            arm_id=a["arm_id"],
            type=a["type"],
            mapped_action=a["mapped_action"],
            strategy_prompt=a["strategy_prompt"],
        )
        for a in data.get("catalyst_arms", [])
    ]

    stop_conditions: list[StopCondition] = [
        StopCondition(
            name=sc["name"],
            type=sc["type"],
            parameters=sc.get("parameters") or {},
        )
        for sc in data.get("stop_conditions", [])
    ]

    clutch_rules: list[ClutchRule] = [
        ClutchRule(
            name=r["name"],
            description=r.get("description", ""),
            predicate_name=r["predicate_name"],
            action=r["action"],
            parameters=r.get("parameters") or {},
        )
        for r in data.get("clutch_rules", [])
    ]

    reinjection_triggers: list[ReinjectionTrigger] = [
        ReinjectionTrigger(
            name=t["name"],
            predicate=t["predicate"],
            parameters=t.get("parameters") or {},
        )
        for t in data.get("reinjection_triggers", [])
    ]

    config = CycleConfig(
        name=data["name"],
        version=int(data.get("version", 1)),
        description=data.get("description", ""),
        steps=steps,
        max_steps=int(data["max_steps"]),
        stop_conditions=stop_conditions,
        clutch_rules=clutch_rules,
        composite_floor=float(data.get("composite_floor", 0.3)),
        catalyst_arms=catalyst_arms,
        reinjection_triggers=reinjection_triggers,
        max_recursion_depth=int(data.get("max_recursion_depth", 0)),
    )
    _validate_config(config)
    return config


# ── Loader ────────────────────────────────────────────────────────────────────


class CycleConfigLoader:
    """Load and validate cycle configs from YAML.

    Search order: vault's cycles/ first, then built-in cycles/.
    """

    def load(self, name: str, vault_path: Path | None = None) -> CycleConfig:
        """Load config by name. Raises FileNotFoundError if not found."""
        filename = f"{name}.yaml"

        # 1. Vault's cycles/ directory
        if vault_path is not None:
            vault_file = vault_path / "cycles" / filename
            if vault_file.exists():
                return self._load_file(vault_file)

        # 2. Built-in cycles/ directory
        builtin_file = _BUILTIN_CYCLES_DIR / filename
        if builtin_file.exists():
            return self._load_file(builtin_file)

        searched: list[str] = []
        if vault_path is not None:
            searched.append(str(vault_path / "cycles" / filename))
        searched.append(str(builtin_file))
        raise FileNotFoundError(f"Cycle config '{name}' not found. Searched: {searched}")

    def _load_file(self, path: Path) -> CycleConfig:
        with open(path) as f:
            data = yaml.safe_load(f)
        return _parse_config(data)
