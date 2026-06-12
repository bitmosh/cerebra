"""COHERENCE signal prompt — v1.

Maps to Thread 1 (Internal Consistency): does the output hold together?
"""

from __future__ import annotations

PROMPT_VERSION = "coherence_v1"

PROMPT_TEMPLATE = """\
You are evaluating the COHERENCE of an LLM output. COHERENCE measures whether the output \
holds together internally — no contradictions, consistent term usage, valid logical flow.

OUTPUT TO EVALUATE:
{output}

CONTEXT (if any):
{context}

For this output, evaluate each item below. Rate severity 0-3 where:
  0 = not present / no issue
  1 = minor issue, limited impact
  2 = moderate issue, affects reasoning
  3 = severe issue, undermines the output

  1. Does any claim contradict any other claim in this output?
  2. Are any terms used with different meanings in different places (equivocation)?
  3. Do conclusions follow logically from their stated premises (non-sequiturs)?
  4. Are any premises hidden that the argument depends on?
  5. Does the reasoning loop back to assume what it is trying to prove (circular reasoning)?

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

overall_score must be a float between 0.0 (completely incoherent) and 1.0 (fully coherent).\
"""


def render(output: str, context: dict | None = None) -> str:
    return PROMPT_TEMPLATE.format(output=output, context=context or {})
