# Cognitive Architecture Principles

Cognitive architectures model the structure of intelligent behavior. This document
covers the principles most relevant to building cognitive runtime systems.

## The cycle

All cognitive systems operate in cycles:
1. **Perceive** — take in context from memory and environment
2. **Plan** — determine what to do
3. **Act** — produce an output or take a step
4. **Evaluate** — assess the output quality
5. **Learn** — update predictions and strategies

The cycle is the atomic unit. Everything else is configuration or bookkeeping.

## Prediction error as signal

When a system predicts that a step will score 0.8 and it scores 0.5, the error is
information. Systems that track prediction error across many cycles can:
- Identify which step types are reliably hard
- Adjust priors for future cycles
- Surface surprising success patterns alongside failures

Bandit algorithms (epsilon-greedy, UCB) apply well here: balance exploration of
new strategies against exploitation of known-good ones.

## The clutch

A decision mechanism that mediates between "keep going" and "stop or retry" is
sometimes called a clutch. A useful clutch:
- Is explicit about which predicates it checked
- Records its decision and the rule that triggered it
- Supports cascade: a stop from one rule can escalate to a different rule
- Has an "accept" path for the common case

Clutch rules should be legible. If you cannot explain why the clutch stopped a
cycle in plain language, the rule set is too complex.

## Leeway

Structural safety bounds sometimes need to flex. Leeway is the mechanism:
- A leeway grant temporarily lifts a constraint with explicit justification
- Grants are time-bounded and auditable
- Revocation fires when conditions are no longer met

Leeway is different from removing a constraint: the constraint remains; the grant
is a tracked exception with a clear expiry.

## Working memory as contested resource

Working memory slots are finite and contested. When a new item wants to enter:
- Lower-salience items may be evicted
- Slot type matters (code context vs. conceptual background vs. active hypothesis)
- Eviction policy should be explicit, not implicit GC

This models the real cognitive resource constraint: you cannot hold everything in
active context at once, so the system must decide what matters most right now.

## Session continuity

A session is a bounded cognitive context:
- Opened with a goal
- Extended through cycles that share accumulated state
- Flushed when the goal is resolved or abandoned

Sessions enable continuity without requiring infinite context windows. Prior
session outputs can be retrieved as memory records in future sessions.
