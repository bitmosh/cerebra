# SPDX-License-Identifier: Apache-2.0
"""GENERATIVITY signal prompt — v1.

Maps to Thread 3 (Productive Tension): does the output advance understanding?
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "generativity_v1"

PROMPT_TEMPLATE = """\
You are evaluating the GENERATIVITY of an LLM output. GENERATIVITY measures whether the \
output advances understanding — producing genuine novelty or productive tension rather than \
sycophantic agreement, flat repetition, or destructive contradiction.

OUTPUT TO EVALUATE:
{output}

CONTEXT (if any):
{context}

For this output, evaluate each item below. Rate severity 0-3 where:
  0 = not present / no issue
  1 = minor concern
  2 = moderate — noticeably limits generative value
  3 = severe — the output is purely repetitive or purely destructive

  1. Does this output say something that was not already stated in the context? \
(severity 0 = yes, novel; 3 = complete repetition)
  2. If novel content appears, does it represent productive advance — or empty contradiction \
without synthesis?
  3. Does the output engage dialectically with prior positions (challenges, extends, \
or synthesizes rather than just agreeing)?
  4. Does any insight emerge that could not have been derived by rearranging the input?
  5. Would a thoughtful reader's understanding be meaningfully different after reading this output?

Respond with valid JSON only — no markdown, no prose outside the JSON:
{{
  "checks": [
    {{"item": 1, "severity": 0, "specific_lines": ""}},
    {{"item": 2, "severity": 0, "specific_lines": ""}},
    {{"item": 3, "severity": 0, "specific_lines": ""}},
    {{"item": 4, "severity": 0, "specific_lines": ""}},
    {{"item": 5, "severity": 0, "specific_lines": ""}}
  ],
  "overall_score": 1.0,
  "reasoning": "brief explanation of the score"
}}

overall_score must be a float between 0.0 (no generative value) and 1.0 (highly generative).\
"""


def render(output: str, context: dict[str, Any] | None = None) -> str:
    return PROMPT_TEMPLATE.format(output=output, context=context or {})
