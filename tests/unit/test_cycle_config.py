# SPDX-License-Identifier: Apache-2.0
"""Unit tests for cerebra.cognition.cycle_config — Phase 8 Step 2."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cerebra.cognition.cycle_config import (
    CycleConfig,
    CycleConfigLoader,
    CycleConfigValidationError,
    StepPromptTemplate,
    _parse_config,
    render_template,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _minimal_config_dict() -> dict:
    """Minimal valid config dict for parsing tests."""
    return {
        "name": "test.v0",
        "version": 1,
        "description": "A test cycle",
        "max_steps": 3,
        "steps": [
            {
                "name": "step_a",
                "description": "First step",
                "prompt_template": {
                    "template": "Hello {{ goal }}",
                    "expected_output_format": "free_form",
                },
            },
            {
                "name": "step_b",
                "description": "Second step",
                "prompt_template": {
                    "template": "Continue with {{ prior_step_output }}",
                    "expected_output_format": "free_form",
                },
            },
        ],
        "stop_conditions": [
            {"name": "cap", "type": "max_steps_reached", "parameters": {}},
        ],
        "clutch_rules": [
            {
                "name": "default",
                "description": "Always accept",
                "predicate_name": "always",
                "action": "accept",
                "parameters": {},
            }
        ],
    }


def _make_config(**overrides) -> CycleConfig:
    d = _minimal_config_dict()
    d.update(overrides)
    return _parse_config(d)


# ── render_template ───────────────────────────────────────────────────────────


class TestRenderTemplate:
    def test_simple_variable(self) -> None:
        assert render_template("Hello {{ goal }}", {"goal": "world"}) == "Hello world"

    def test_multiple_variables(self) -> None:
        result = render_template("{{ a }} and {{ b }}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_missing_variable_renders_empty(self) -> None:
        assert render_template("{{ missing }}", {}) == ""

    def test_list_indexing(self) -> None:
        ctx = {"prior_steps": ["first", "second", "third"]}
        assert render_template("{{ prior_steps[0] }}", ctx) == "first"
        assert render_template("{{ prior_steps[1] }}", ctx) == "second"
        assert render_template("{{ prior_steps[2] }}", ctx) == "third"

    def test_list_index_out_of_bounds(self) -> None:
        ctx = {"prior_steps": ["only"]}
        assert render_template("{{ prior_steps[5] }}", ctx) == ""

    def test_list_variable_not_a_list(self) -> None:
        ctx = {"prior_steps": "not a list"}
        assert render_template("{{ prior_steps[0] }}", ctx) == ""

    def test_none_value_renders_empty(self) -> None:
        assert render_template("{{ prior_step_output }}", {"prior_step_output": None}) == ""

    def test_non_string_value_converted(self) -> None:
        assert render_template("score={{ score }}", {"score": 0.75}) == "score=0.75"

    def test_whitespace_around_variable_name(self) -> None:
        assert render_template("{{  goal  }}", {"goal": "hi"}) == "hi"

    def test_multiline_template(self) -> None:
        tpl = "# {{ step_name }}\n{{ goal }}\n{{ retrieved_context }}"
        ctx = {"step_name": "plan", "goal": "Build X", "retrieved_context": "Notes"}
        assert render_template(tpl, ctx) == "# plan\nBuild X\nNotes"

    def test_template_with_no_variables(self) -> None:
        assert render_template("static text", {}) == "static text"


# ── StepPromptTemplate ────────────────────────────────────────────────────────


class TestStepPromptTemplate:
    def test_free_form_no_schema(self) -> None:
        tpl = StepPromptTemplate(template="{{ goal }}", expected_output_format="free_form")
        assert tpl.output_schema is None

    def test_json_with_schema(self) -> None:
        schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        tpl = StepPromptTemplate(
            template="{{ goal }}", expected_output_format="json", output_schema=schema
        )
        assert tpl.output_schema == schema

    def test_frozen(self) -> None:
        tpl = StepPromptTemplate(template="x", expected_output_format="free_form")
        with pytest.raises((AttributeError, TypeError)):
            tpl.template = "y"  # type: ignore[misc]


# ── CycleConfig validation ────────────────────────────────────────────────────


class TestCycleConfigValidation:
    def test_valid_minimal_config(self) -> None:
        cfg = _make_config()
        assert cfg.name == "test.v0"
        assert len(cfg.steps) == 2

    def test_duplicate_step_names_raise(self) -> None:
        d = _minimal_config_dict()
        d["steps"][1]["name"] = "step_a"  # duplicate
        with pytest.raises(CycleConfigValidationError, match="Duplicate step names"):
            _parse_config(d)

    def test_max_steps_below_step_count_raises(self) -> None:
        d = _minimal_config_dict()
        d["max_steps"] = 1  # < 2 steps
        with pytest.raises(CycleConfigValidationError, match="max_steps"):
            _parse_config(d)

    def test_max_steps_equal_to_step_count_ok(self) -> None:
        d = _minimal_config_dict()
        d["max_steps"] = 2
        cfg = _parse_config(d)
        assert cfg.max_steps == 2

    def test_no_stop_conditions_raises(self) -> None:
        d = _minimal_config_dict()
        d["stop_conditions"] = []
        with pytest.raises(CycleConfigValidationError, match="stop condition"):
            _parse_config(d)

    def test_no_accept_rule_raises(self) -> None:
        d = _minimal_config_dict()
        d["clutch_rules"] = [
            {
                "name": "only_stop",
                "description": "",
                "predicate_name": "always",
                "action": "stop",
                "parameters": {},
            }
        ]
        with pytest.raises(CycleConfigValidationError, match="accept"):
            _parse_config(d)

    def test_unknown_predicate_raises(self) -> None:
        d = _minimal_config_dict()
        d["clutch_rules"][0]["predicate_name"] = "not_a_real_predicate"
        with pytest.raises(CycleConfigValidationError, match="Unknown predicate"):
            _parse_config(d)

    def test_unknown_action_raises(self) -> None:
        d = _minimal_config_dict()
        # Keep the first rule's action unknown AND add a valid accept rule so that
        # validation check #4 (accept rule required) passes before check #5 fires.
        d["clutch_rules"][0]["action"] = "fly_to_mars"
        d["clutch_rules"].append(
            {
                "name": "fallback",
                "description": "",
                "predicate_name": "always",
                "action": "accept",
                "parameters": {},
            }
        )
        with pytest.raises(CycleConfigValidationError, match="Unknown action"):
            _parse_config(d)

    def test_json_step_without_schema_raises(self) -> None:
        d = _minimal_config_dict()
        d["steps"][0]["prompt_template"]["expected_output_format"] = "json"
        # no output_schema
        with pytest.raises(CycleConfigValidationError, match="output_schema"):
            _parse_config(d)

    def test_json_step_with_schema_ok(self) -> None:
        d = _minimal_config_dict()
        d["steps"][0]["prompt_template"]["expected_output_format"] = "json"
        d["steps"][0]["prompt_template"]["output_schema"] = {"type": "object"}
        cfg = _parse_config(d)
        assert cfg.steps[0].prompt_template.output_schema == {"type": "object"}

    def test_config_is_frozen(self) -> None:
        cfg = _make_config()
        with pytest.raises((AttributeError, TypeError)):
            cfg.name = "other"  # type: ignore[misc]

    def test_steps_frozen(self) -> None:
        cfg = _make_config()
        with pytest.raises((AttributeError, TypeError)):
            cfg.steps[0].name = "modified"  # type: ignore[misc]


# ── _parse_config ─────────────────────────────────────────────────────────────


class TestParseConfig:
    def test_parses_name_version_description(self) -> None:
        cfg = _make_config()
        assert cfg.name == "test.v0"
        assert cfg.version == 1
        assert cfg.description == "A test cycle"

    def test_parses_steps(self) -> None:
        cfg = _make_config()
        assert len(cfg.steps) == 2
        assert cfg.steps[0].name == "step_a"
        assert cfg.steps[1].name == "step_b"

    def test_parses_stop_conditions(self) -> None:
        cfg = _make_config()
        assert len(cfg.stop_conditions) == 1
        assert cfg.stop_conditions[0].type == "max_steps_reached"

    def test_parses_clutch_rules(self) -> None:
        cfg = _make_config()
        assert len(cfg.clutch_rules) == 1
        assert cfg.clutch_rules[0].predicate_name == "always"
        assert cfg.clutch_rules[0].action == "accept"

    def test_null_parameters_normalized_to_empty_dict(self) -> None:
        d = _minimal_config_dict()
        d["stop_conditions"][0]["parameters"] = None  # type: ignore[assignment]
        cfg = _parse_config(d)
        assert cfg.stop_conditions[0].parameters == {}

    def test_missing_description_defaults_empty(self) -> None:
        d = _minimal_config_dict()
        del d["steps"][0]["description"]
        cfg = _parse_config(d)
        assert cfg.steps[0].description == ""


# ── CycleConfigLoader ─────────────────────────────────────────────────────────


class TestCycleConfigLoader:
    def test_loads_builtin_simple_planning(self) -> None:
        loader = CycleConfigLoader()
        cfg = loader.load("simple.planning.v0")
        assert cfg.name == "simple.planning.v0"
        assert cfg.version == 1
        assert len(cfg.steps) == 5
        assert cfg.max_steps == 8

    def test_builtin_steps_names(self) -> None:
        loader = CycleConfigLoader()
        cfg = loader.load("simple.planning.v0")
        names = [s.name for s in cfg.steps]
        assert names == [
            "understand_goal",
            "draft_plan",
            "critique_plan",
            "refine_plan",
            "finalize",
        ]

    def test_builtin_stop_conditions(self) -> None:
        loader = CycleConfigLoader()
        cfg = loader.load("simple.planning.v0")
        types = {sc.type for sc in cfg.stop_conditions}
        assert "max_steps_reached" in types
        assert "all_steps_completed" in types
        assert "composite_floor_consecutive" in types
        assert "explicit_clutch_stop" in types
        assert "user_interrupt" in types

    def test_builtin_clutch_rules(self) -> None:
        loader = CycleConfigLoader()
        cfg = loader.load("simple.planning.v0")
        assert any(r.action == "accept" for r in cfg.clutch_rules)
        assert any(r.action == "stop" for r in cfg.clutch_rules)
        assert any(r.action == "refine" for r in cfg.clutch_rules)

    def test_refine_plan_uses_prior_steps_indexing(self) -> None:
        loader = CycleConfigLoader()
        cfg = loader.load("simple.planning.v0")
        refine = next(s for s in cfg.steps if s.name == "refine_plan")
        assert "{{ prior_steps[1] }}" in refine.prompt_template.template

    def test_unknown_config_raises_file_not_found(self) -> None:
        loader = CycleConfigLoader()
        with pytest.raises(FileNotFoundError, match="does.not.exist"):
            loader.load("does.not.exist")

    def test_vault_cycles_directory_takes_priority(self, tmp_path: Path) -> None:
        vault_cycles = tmp_path / "cycles"
        vault_cycles.mkdir()
        d = _minimal_config_dict()
        d["name"] = "test.v0"
        d["description"] = "vault override"
        (vault_cycles / "test.v0.yaml").write_text(yaml.dump(d))

        loader = CycleConfigLoader()
        cfg = loader.load("test.v0", vault_path=tmp_path)
        assert cfg.description == "vault override"

    def test_falls_back_to_builtin_when_not_in_vault(self, tmp_path: Path) -> None:
        # vault has no cycles/ dir
        loader = CycleConfigLoader()
        cfg = loader.load("simple.planning.v0", vault_path=tmp_path)
        assert cfg.name == "simple.planning.v0"

    def test_parse_error_propagates(self, tmp_path: Path) -> None:
        vault_cycles = tmp_path / "cycles"
        vault_cycles.mkdir()
        d = _minimal_config_dict()
        d["steps"][0]["name"] = d["steps"][1]["name"]  # duplicate → validation error
        (vault_cycles / "bad.yaml").write_text(yaml.dump(d))
        loader = CycleConfigLoader()
        with pytest.raises(CycleConfigValidationError):
            loader.load("bad", vault_path=tmp_path)
