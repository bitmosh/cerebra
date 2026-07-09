# SPDX-License-Identifier: Apache-2.0
"""GROUNDEDNESS signal prompt — v1.

Maps to Thread 2 (Grounding in Evidence): is the output anchored in evidence or experience?
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "groundedness_v1"

PROMPT_TEMPLATE = """\
You are evaluating the GROUNDEDNESS of an LLM output. GROUNDEDNESS measures whether the \
output is anchored in evidence or experience — not floating free of any anchor. \
Hallucination is the canonical failure mode.

OUTPUT TO EVALUATE:
{output}

CONTEXT (if any):
{context}

For this output, evaluate each item below. Rate severity 0-3 where:
  0 = not present / no issue
  1 = minor issue, limited impact
  2 = moderate issue, affects reliability
  3 = severe issue, claims unsupported or fabricated

  1. Which claims have explicit source backing? (severity 0 if all are sourced, higher if many are not)
  2. For unsourced claims: are they verifiable common knowledge, or are they bare assertion?
  3. Are sources cited recent enough to be relevant to the claims they support?
  4. Is the derivation chain from source to claim traceable and honest?
  5. Are any claims confidently asserted that the provided sources do not actually support?

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

overall_score must be a float between 0.0 (entirely ungrounded) and 1.0 (fully grounded).\
"""


def render(output: str, context: dict[str, Any] | None = None) -> str:
    return PROMPT_TEMPLATE.format(output=output, context=context or {})
