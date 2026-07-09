# SPDX-License-Identifier: Apache-2.0
"""
Triangulates a raw score with confidence and signal-strength multipliers.

The composition: reward = score × confidence × signal_strength
"""


def triangulate(
    score: float,
    confidence: float,
    signal_strength: float,
    clamp_lo: float = 0.0,
    clamp_hi: float = 1.2,
) -> float:
    """
    Args:
        score: raw composite score, typically [0, 1]
        confidence: confidence in the scoring, [0, 1]
        signal_strength: strength of underlying signal, [0, 1]
        clamp_lo: lower clamp (default 0.0)
        clamp_hi: upper clamp (default 1.2 — allows positive shaping bonuses)

    Returns:
        Triangulated reward in [clamp_lo, clamp_hi]
    """
    reward = score * confidence * signal_strength
    return max(clamp_lo, min(clamp_hi, reward))


def triangulate_with_components(
    score: float,
    confidence: float,
    signal_strength: float,
) -> dict[str, float]:
    """Variant that returns components alongside reward for inspection."""
    return {
        "score": score,
        "confidence": confidence,
        "signal_strength": signal_strength,
        "reward": triangulate(score, confidence, signal_strength),
    }
