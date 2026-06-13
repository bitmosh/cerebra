# Phase 7 — Governance Module Audit

Produced before any Phase 7 implementation. All findings are from reading the actual files;
the design doc (v01_phase6_design.md §5) is a reference point but the code wins on conflicts.

---

## Existing module structure

| File | Purpose |
|---|---|
| `models.py` | `LeewayRule`, `ConstitutionalRule`, `SignalCondition`, `RevocationTrigger` + literal types |
| `defaults.py` | `DEFAULT_LEEWAY_RULES` (LR-001→LR-015), `DEFAULT_CONSTITUTIONAL_RULES` (CONST-001→CONST-005) |
| `loader.py` | YAML loaders + `write_defaults_to_vault(vault_path)` |
| `__init__.py` | Re-exports loader + model types |

---

## Rule type analysis

### LeewayRule

Regular (non-frozen) dataclass. Key fields:

| Field | Type | Notes |
|---|---|---|
| `rule_id` | `str` | e.g. `"LR-001"` — design doc calls this `name` |
| `capability` | `str` | Single capability string (e.g. `"retrieve_from_memory"`) |
| `conditions` | `list[SignalCondition]` | Signal-based conditions |
| `condition_join` | `ConditionJoin` | `"AND"` or `"OR"` |
| `phase` | `LeewayPhase` | `"pre_action"`, `"post_action"`, or `"both"` |
| `revocation_conditions` | `list[SignalCondition]` | Signal-based revocation |

Existing methods: `is_granted(signals: dict[str, Any]) -> bool` and `is_revoked(signals)`.

**No action-name matching method.** The design doc assumes `r.grants(action)` and `r.requires_review(action)`, neither of which exist.

**No `requires_review` concept.** There is no field, method, or model construct representing "requires human review."

### ConstitutionalRule

Regular (non-frozen) dataclass. Key fields:

| Field | Type | Notes |
|---|---|---|
| `rule_id` | `str` | e.g. `"CONST-001"` — design doc calls this `name` |
| `description` | `str` | Human-readable description |
| `revokes_leeway_when` | `list[RevocationTrigger]` | Trigger conditions (output analysis) |
| `applies_to` | `str` | `"all_capabilities"` or a specific capability name |
| `is_inviolable` | `bool` | Always `True` in existing defaults |

**No `forbids(action)` method.** The design doc assumes `c_rule.forbids(proposed_action)`.

**Semantic mismatch — critical:** The existing ConstitutionalRules are POST-ACTION output analyzers. Their `revokes_leeway_when` triggers check what the output **contains** (e.g. `"output_topic_in": ["cbrn_weapons", ...]`). None are pre-action capability blocks. CONST-001 through CONST-005 all operate on output content, not on which capability is being proposed.

### Loader API

```python
load_leeway_rules(leeway_dir: Path) -> list[LeewayRule]       # leeway/*.yaml
load_constitutional_rules(constitutional_dir: Path) -> list[ConstitutionalRule]  # constitutional/*.yaml
```

Takes **subdirectory paths**, not `vault_path`. Design doc's `load_pre_action_gate(vault_path)` helper must pass `vault_path / "leeway"` and `vault_path / "constitutional"`.

---

## Design doc assumptions vs. actual structure

| Design doc assumption | Actual structure | Resolution |
|---|---|---|
| `r.name` | `r.rule_id` | Use `rule_id` throughout — minor rename |
| `r.grants(action)` | Not present | Add method — capability == action_name match |
| `r.requires_review(action)` | Not present | **Question for #brainstorm** |
| `c_rule.name` | `c_rule.rule_id` | Use `rule_id` — minor rename |
| `c_rule.forbids(action)` | Not present | **Question for #brainstorm (semantic mismatch)** |
| Constitutional = pre-action blocker | Constitutional = post-action output analyzer | **Major divergence — needs decision** |
| `load_pre_action_gate(vault_path)` | Loaders take subdirectory paths | Wrap in helper, pass correct subpaths |

---

## Questions raised (pending #brainstorm response)

**Q1 — ConstitutionalRule.forbids() semantics**

The existing ConstitutionalRules are output-analysis revocations (post-action). None say "this capability is pre-emptively forbidden at action proposal time." So `forbids(action)` would return `False` for every existing rule.

Options:
- A: `forbids(action)` always returns `False` in v0.1; constitutional blocking is a v0.2 concept once rules with pre-action semantics exist. Log as DEV-009.
- B: Interpret `applies_to != "all_capabilities"` + `is_inviolable == True` as a pre-action block for that specific capability. (CONST-005 → forbids `tombstone_memory` pre-emptively.) This re-purposes an existing field but it's not what the field was designed to express.
- C: Add a separate `pre_action_forbidden: bool = False` field to ConstitutionalRule and `forbids()` checks that. Only set by future rule definitions, existing rules stay False.

**Q2 — LeewayRule.requires_review() and review_required path**

No existing field or method for "requires human review." Options:
- A: Omit `requires_review` from v0.1 gate entirely. Gate only produces `"permitted"` or `"forbidden"`. Document the path as v0.2. The test suite doesn't test review_required.
- B: Add `requires_review_capabilities: list[str] = field(default_factory=list)` to `LeewayRule` (no defaults set it), and `requires_review(action)` returns `action.action_name in self.requires_review_capabilities`. Review path tested with hand-crafted rules in tests.

---

## Resolved items (no question needed)

- **Option A vs B for predicate placement**: Both rule types are regular (non-frozen) dataclasses. Methods can be added directly. Use Option A.
- **Name identifier**: Use `rule_id` as the rule identity string in `GateDecision.grants_applied` and `forbidden_by`.
- **LeewayRule.grants(action)**: `return self.capability == action.action_name and self.phase in ("pre_action", "both")`
- **Loader helper**: `load_pre_action_gate(vault_path)` will call existing loaders with `vault_path / "leeway"` and `vault_path / "constitutional"`.
