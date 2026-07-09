# SPDX-License-Identifier: Apache-2.0
"""RELEVANCE signal prompt — v1.

Maps to Thread 4 (Fit to Purpose): does the output serve what was actually asked?
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "relevance_v1"

PROMPT_TEMPLATE = """\
You are evaluating the RELEVANCE of an LLM output. RELEVANCE measures whether the output \
serves what was actually asked — fit to purpose, responsive to the user's real need, \
not just technically correct but unhelpfully tangential.

OUTPUT TO EVALUATE:
{output}

CONTEXT (if any):
{context}

For this output, evaluate each item below. Rate severity 0-3 where:
  0 = not present / no issue
  1 = minor — slight drift from the question
  2 = moderate — significant portion of output misses the point
  3 = severe — output addresses a different question entirely

  1. Does this output directly address the question or goal stated in the context?
  2. Is the response calibrated to the context provided, or does it address a different problem?
  3. Does any tangent appear that is not responsive to the stated need?
  4. Does the output stay within the project scope implied by the context?
  5. Would the user's actual need be meaningfully met by this response?

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

overall_score must be a float between 0.0 (completely irrelevant) and 1.0 (highly relevant).\
"""


def render(output: str, context: dict[str, Any] | None = None) -> str:
    return PROMPT_TEMPLATE.format(output=output, context=context or {})
