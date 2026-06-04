# Cerebra — Catalyst

## 1. Purpose

The catalyst is Cerebra's strategy and action selector under uncertainty.

Where the clutch is a *priority-rule controller* that maps signal state to typed control action via declarative cascades, the catalyst is a *bandit-driven multi-factor selector* that picks among cognitive strategies when no clear rule fires. The clutch handles known situations with known responses; the catalyst handles open situations where the system has to choose what to try.

The two primitives compose. The clutch decides "I should mutate strategy now." The catalyst decides "I should mutate to *this specific* strategy among the available options, weighted by what's worked before and what hasn't been tried lately."

This document defines the catalyst's scoring formula, the action vocabulary it selects over, the bandit integration, the diversity preservation discipline, and the integration points with the rest of the runtime.

---

## 2. Core Doctrine

The catalyst should be:

```text
bandit-driven
multi-factor-scored
diversity-preserving
chain-aware
weighted-random (not argmax)
confidence-ramping
safety-bounded
explainable
```

The catalyst is the place where the system tries things. It must explore enough to learn, exploit enough to make progress, and never lose access to actions that didn't perform well in the past — yesterday's failure may be tomorrow's success.

---

## 3. The Multi-Factor Scoring Formula

The catalyst's score for any candidate action is:

```text
score(action) = base_reward × chain_bonus × decay_factor × type_penalty × confidence_ramp
```

Each factor is bounded and explainable.

### 3.1 base_reward

Learned reward from the bandit. Mean reward this action has received in past selections, weighted by recency.

```text
base_reward = exponential_moving_average(past_rewards, decay=0.85)
range: [0, 1]
```

New actions (no past data) start at a neutral baseline (0.5) and ramp by the confidence factor.

### 3.2 chain_bonus

Reward for actions that have produced successful chains. If action A is frequently followed by action B in successful sequences, A earns a chain bonus.

```text
chain_bonus = 1 + (chain_success_rate × chain_weight)
range: [1, 1.5]
chain_weight default: 0.3
```

This is the catalyst's memory of *combinations that work*, not just individual actions that work.

### 3.3 decay_factor

Recency decay for actions that haven't been selected lately. Prevents the catalyst from getting stuck on early winners.

```text
cycles_since_last_selection = N
decay_factor = max(0.7, 1.0 - (N / decay_horizon))
decay_horizon default: 50 cycles
```

An action that hasn't been picked in 50 cycles still scores at 70% of its base. Never penalized below that floor — yesterday's loser is tomorrow's surprise.

### 3.4 type_penalty

Diversity preservation. If the catalyst has been picking actions of the same type repeatedly, similar-type actions get a penalty.

```text
recent_type_count = count of selections of this action's type in last K selections
type_penalty = max(0.5, 1.0 - (recent_type_count × type_pressure))
K default: 5
type_pressure default: 0.15
```

This is what keeps the system from converging on a narrow strategy band. Even if "refine" is the best-performing action, picking refine 5 times in a row triggers diversity pressure that makes "explore" or "branch" more attractive.

### 3.5 confidence_ramp

New actions get gentler scoring until enough samples exist to trust the data.

```text
samples = number of times this action has been selected and evaluated
confidence_ramp = min(1.0, samples / 10)
```

An action with 0 samples scores at 0% confidence — it relies entirely on its baseline. An action with 10+ samples scores at full confidence. Between 0 and 10, the ramp interpolates linearly.

---

## 4. Weighted-Random Selection

The catalyst does not pick the argmax. It samples from a weighted distribution over the candidate actions.

```text
weights = [score(action_i) for action_i in candidates]
selected = weighted_random_sample(candidates, weights)
```

This preserves exploration even after preferences form. The best-scoring action wins most of the time; the second-best wins sometimes; the lowest-scoring still has nonzero probability.

This is also what makes the catalyst safe to combine with the clutch. The clutch decides *whether* to mutate (deterministic policy); the catalyst decides *what* to mutate to (weighted-random sample). The combination has explainable structure plus exploratory freedom.

---

## 5. Action Vocabulary

The catalyst selects from action vocabularies declared by the cycle config. Vocabularies are per-cycle-config; what's available depends on what the cycle is doing.

For a Bons.ai-shaped ideation cycle:

```text
exploration       try a divergent direction
refinement        improve the current best
disruption        break from the current frame
analogy           bring in cross-domain mapping
structure         add formal scaffolding
optimization      tune existing parameters
memory_integration  retrieve and weave in prior context
self_optimize     adjust own scoring weights
```

For a planning cycle:

```text
decomposition     break the goal into sub-goals
constraint_check  validate against constraints
prerequisite_id   identify missing prerequisites
sequencing        determine order of operations
risk_assessment   identify failure modes
resource_estimate estimate required resources
```

For a debugging cycle:

```text
hypothesis_form   generate explanation candidates
trace_follow      walk through execution path
state_inspect     examine variable/memory state
diff_compare      compare working vs broken version
isolate           reduce to minimal reproducer
verify_assumption  test assumption that's underlying suspicion
```

Each vocabulary is declared in the cycle config. The catalyst loads the vocabulary when the cycle starts and selects from it.

---

## 6. Bandit Integration

The catalyst's `base_reward` and `confidence_ramp` are computed from a bandit primitive (see lattica-primitives §Bandit Selector). The bandit maintains per-arm statistics:

```text
arm_stats[action_id] = {
  count: int             # times selected
  total_reward: float    # sum of rewards received
  recent_rewards: [float]  # last N rewards for EMA
  last_selected_cycle: int  # cycle index of most recent selection
}
```

After every catalyst selection, the cycle evaluates the resulting step and computes a reward. That reward updates the arm stats.

```text
reward_computation = composite_score × confidence × signal_strength
```

This is the same signal-triangulator pattern used elsewhere in Cerebra. The catalyst's learning signal is high-quality because it's confidence-weighted — low-confidence wins teach the catalyst less than high-confidence wins.

---

## 7. Catalyst Invocation

The clutch invokes the catalyst when its rule cascade reaches a "select strategy" decision point.

```text
Clutch fires rule: failure_streak >= 2 and trajectory == "degrading"
Clutch action: ESCALATE
Clutch sub-action: invoke catalyst to select escalation strategy
  Catalyst loads vocabulary for current cycle config
  Catalyst computes scores for each candidate
  Catalyst weighted-samples and returns selection
  Cycle dispatches the selected action
```

The catalyst can also be invoked directly by the cycle runtime when no rule fires but the system needs to make a choice — e.g., at cycle start, the catalyst picks the initial strategy.

---

## 8. Safety Boundaries

The catalyst is exploratory. The leeway network (forthcoming) is the boundary enforcement.

```text
Catalyst sees the full vocabulary declared by the cycle config.
Catalyst scores candidates.
Before sampling, the leeway network filters the candidates:
  any candidate that violates current leeway grants is removed
  any candidate that would trigger constitutional revocation is removed
The catalyst samples from the remaining set.
```

This means the catalyst never has to know about safety. The catalyst's job is *what to try*; the leeway network's job is *what's currently permitted to try*. Two concerns, two layers, no interference.

If the leeway-filtered set is empty, the catalyst returns a `cannot_select` signal and the clutch falls back to a safe default.

---

## 9. Chain-Awareness

The catalyst tracks not just per-action stats but action *sequences*.

```text
chain_stats[(action_a, action_b)] = {
  count: int                # times this pair occurred in succession
  success_count: int        # times this pair led to a good cycle outcome
}

chain_success_rate(a, b) = chain_stats[(a, b)].success_count / chain_stats[(a, b)].count
```

When the catalyst is selecting the *next* action and a previous action was X, the chain_bonus boosts candidates Y such that (X, Y) has a high success rate.

This is how the catalyst learns *patterns*, not just *preferences*. "Exploration is usually best followed by refinement" emerges from chain stats; the catalyst doesn't need it pre-encoded.

---

## 10. Self-Optimization Action

One of the vocabulary entries deserves special treatment: `self_optimize`.

When the catalyst selects `self_optimize`, the resulting step doesn't produce a content output. Instead, it analyzes recent catalyst behavior and recommends adjustments to scoring weights:

```text
"The type_pressure has been over-correcting. We're switching strategies too often
 and not getting enough samples per strategy. Recommend reducing type_pressure
 from 0.15 to 0.10."
```

The cycle runtime can accept or reject these self-recommendations. If accepted, the catalyst's scoring weights update for future cycles.

This is the move that makes the catalyst self-improving in a deep sense. It's not just learning rewards for actions — it's learning the parameters of its own scoring function.

`self_optimize` is gated by the leeway network and should require multiple supporting signals to fire. It's not a default-frequent action.

---

## 11. Integration With Existing Components

**Clutch (`CEREBRA_COGNITIVE_RUNTIME.md`):** the clutch invokes the catalyst at "select strategy" decision points. The catalyst returns a sub-action; the clutch's outer action wraps it.

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** the cycle config declares the catalyst's vocabulary. The runtime initializes the catalyst with cycle-specific arm stats.

**Signal Pipeline (`CEREBRA_PREDICTION_AND_EVALUATION.md`):** evaluation produces the reward that updates catalyst bandit stats. The signal-triangulator formula is the catalyst's learning signal.

**Leeway Network (forthcoming):** filters catalyst candidates before sampling. The catalyst sees only currently-permitted actions.

**Truth Tower (`CEREBRA_TRUTH_TOWER.md`):** catalyst selections become events in the cycle's history, which can be cited at T3 if the selection pattern itself becomes insight-worthy.

**SKU Addressing (`CEREBRA_SKU_ADDRESSING.md`):** catalyst behavior over time becomes a memory cluster — "what strategies has this system tried for this kind of query." This cluster gets its own SKU and becomes retrievable as procedural memory.

**Lattica Primitives:** the bandit selector at the catalyst's core is the same primitive used elsewhere. The catalyst is a *consumer* of the bandit primitive, not a replacement for it.

---

## 12. MVP Scope

Cerebra v0.1 should implement:

```text
Catalyst structure with the 5 scoring factors
Bandit integration for base_reward and confidence_ramp
Weighted-random sampling (not argmax)
Simple action vocabulary for one cycle config (default planning cycle)
type_penalty for diversity preservation
Manual catalyst invocation by clutch (no automatic firing)
Catalyst selection events emitted to graph
```

Cerebra v0.2 adds:

```text
Chain-awareness (chain_bonus factor)
Decay factor for recency
Multiple cycle configs with distinct vocabularies
Self-optimize action with manual approval
Catalyst integration with leeway network filter
```

Cerebra v0.3+:

```text
Self-optimize action with automatic acceptance for low-risk adjustments
Catalyst behavior memory cluster (procedural memory)
Cross-cycle catalyst learning (preferences from one cycle inform another)
Catalyst as bandit-arm-of-catalysts (meta-catalyst for cycle-config selection)
```

---

## 13. Testing Requirements

Catalyst tests should cover:

```text
scoring formula produces expected scores for known inputs
weighted-random sampling distributes correctly over many runs
type_penalty kicks in after N selections of same type
confidence_ramp prevents new actions from dominating
decay_factor keeps stale actions from falling below floor
chain_bonus increases scores for high-chain-success pairs
bandit stats update correctly after evaluation
leeway filter removes prohibited candidates before sampling
empty leeway-filtered set triggers cannot_select signal
self_optimize action produces parseable recommendations
catalyst events emit correctly
catalyst selection respects cycle config's vocabulary
```

---

## 14. Catalyst Doctrine

The clutch is the policy. The catalyst is the choice.

The clutch's rule cascade gives the system stable, explainable, debugging-friendly control behavior. But cognition is not only rule-following — sometimes the right move is "try something." The catalyst is the architectural primitive that does *trying* in a disciplined way.

The discipline comes from the multi-factor scoring: not just what's worked best (base_reward), but what hasn't been tried lately (decay), what's been overdone (type_penalty), what we don't yet have evidence for (confidence_ramp), and what tends to work in sequence (chain_bonus). Five factors, each addressing a different failure mode of pure greedy selection.

The weighted-random sampling is the discipline that makes the catalyst's exploration *durable*. An argmax catalyst converges. A weighted-random catalyst keeps wandering. Convergence feels efficient until you discover the local maximum it converged to wasn't the global one; wandering looks inefficient until you discover it was actually finding spaces you hadn't seen.

Combined with the clutch (which decides when to act) and the leeway network (which decides what's permitted), the catalyst is the *what to try* layer of a system that can think about hard problems without rigid prescription.

It is also where Bons.ai's most sophisticated existing logic lives. The bandit-blended chain-aware type-penalized scoring already in `catalyst.py` is the proof of concept. Cerebra inherits the pattern; the implementation gets cleaned and made primitive-shaped.

This is one of the load-bearing parts of the cognitive runtime. Get it right.
