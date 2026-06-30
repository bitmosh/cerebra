"""PRECISION signal prompt — v1.

Maps to Thread 5 (Clarity of Distinction): does the output keep distinct what should be kept distinct?
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "precision_v1"

PROMPT_TEMPLATE = """\
You are evaluating the PRECISION of an LLM output. PRECISION measures whether the output \
keeps distinct what should be kept distinct — no vague terms where precision matters, \
no undefined references, no sloppy collapsing of distinctions that survive examination.

OUTPUT TO EVALUATE:
{output}

CONTEXT (if any):
{context}

For this output, evaluate each item below. Rate severity 0-3 where:
  0 = not present / no issue
  1 = minor — a few imprecise phrasings but meaning is recoverable
  2 = moderate — imprecision affects the conclusion or recommendation
  3 = severe — distinctions critical to the argument are collapsed

  1. Are any terms used that have multiple meanings where the distinction matters for this argument?
  2. Are there undefined references — pronouns, "it", "this", "they" without clear referents?
  3. Are weasel words ("some argue", "many believe", "it is said") used without attribution?
  4. Does any claim's scope creep — starts narrow, expands to general without justification?
  5. Are any distinctions collapsed that should be kept separate for the argument to hold?

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

overall_score must be a float between 0.0 (very imprecise) and 1.0 (highly precise).\
"""


def render(output: str, context: dict[str, Any] | None = None) -> str:
    return PROMPT_TEMPLATE.format(output=output, context=context or {})
