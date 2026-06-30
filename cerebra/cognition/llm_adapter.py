"""
LLM adapter layer — abstract interface + two implementations.

LLMAdapter is the seam that lets the SKU classifier swap backends without
code changes.

OllamaDirectAdapter (preferred for classification):
  Calls Ollama at its native HTTP API (/api/chat). Used for the SKU
  classifier to pass options that LiteLLM drops (think: false, format: json).
  Config via env vars:
    OLLAMA_BASE_URL  default: http://127.0.0.1:11434
    OLLAMA_MODEL     default: huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M

ProxyLLMAdapter (legacy; retained for other backends):
  Calls the LiteLLM Docker proxy at ~/Projects/ai-stack/. JSON adherence
  via prompt only (response_format/format silently dropped by drop_params: true).
  Config via env vars:
    LITELLM_BASE_URL   default: http://127.0.0.1:4000
    LITELLM_API_KEY    default: sk-fake
    CEREBRA_LLM_MODEL  default: cerebra-classifier

First-call cold-load note: the local Ollama model may take up to 164s to
load on first use after stack startup. The adapter timeout is set to
TIMEOUT_SECONDS=300 to survive model cold-load.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, cast

# Cold model load observed at ~164s; 300s gives safe margin for load + inference.
# Subsequent warm calls are ~1-3s. Calibration/backfill ETA should account for
# the slow first call rather than projecting from it.
TIMEOUT_SECONDS = 300


class ClassificationError(Exception):
    """Raised when the LLM returns unparseable or invalid output."""


@dataclass
class ClassificationResult:
    """Raw output from one D1 classification call."""

    scores: dict[str, float]  # all 16 category names → 0.0–1.0
    confidence: float
    primary: str  # name of highest-scoring category
    reasoning: str
    model_string: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_scores_json_override: str | None = None  # two-pass stores full pass1+pass2 JSON here


class LLMAdapter(ABC):
    """Abstract LLM adapter."""

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """Synchronous completion call. Returns model output text."""
        raise NotImplementedError("complete() not implemented by this adapter")

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Synchronous structured completion. Returns parsed JSON matching schema.

        Raises ClassificationError on parse failure or non-200 response.
        """
        raise NotImplementedError("complete_structured() not implemented by this adapter")

    @abstractmethod
    def classify_d1(self, content: str) -> ClassificationResult:
        """
        Score content against all 16 D1 cognitive categories.

        Returns ClassificationResult with all 16 scores (0.0–1.0),
        a global confidence value, the primary category name, and
        telemetry (latency_ms, token counts, model_string).

        Raises ClassificationError on parse failure or non-200 response.
        """

    @abstractmethod
    def classify_quadrant(self, content: str) -> ClassificationResult:
        """Pass 1: score content against the 4 cognitive quadrants."""

    @abstractmethod
    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        """Pass 2: score content within the given quadrant's 4 categories."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the LLM backend is reachable."""


class ProxyLLMAdapter(LLMAdapter):
    """
    LLM adapter that calls the LiteLLM Docker proxy over HTTP.
    Uses stdlib urllib.request — no PyPI dependencies.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        # Use 127.0.0.1 (IPv4) not localhost — Docker port forwarding only works on
        # IPv4; localhost resolves to ::1 (IPv6) first and the connection hangs.
        self._base_url = (
            base_url or os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000")
        ).rstrip("/")
        self._api_key = api_key or os.environ.get("LITELLM_API_KEY", "sk-fake")
        # timeout: None = use TIMEOUT_SECONDS (300s for cold-load backfill).
        # Pass a shorter value for calibration tests on a warm model.
        self._timeout = timeout if timeout is not None else TIMEOUT_SECONDS
        self._model = model or os.environ.get("CEREBRA_LLM_MODEL", "cerebra-classifier")

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        raw = self._call_chat_completions(prompt)
        return str(raw["choices"][0]["message"]["content"])

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        content = self.complete(prompt)
        # Strip markdown fences the proxy may add
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            end = len(lines) - 1
            while end > 0 and not lines[end].startswith("```"):
                end -= 1
            text = "\n".join(lines[1:end]) if end > 0 else "\n".join(lines[1:])
            text = text.strip()
        try:
            return cast(dict[str, Any], json.loads(text))
        except json.JSONDecodeError as e:
            raise ClassificationError(
                f"complete_structured: JSON parse failed: {content[:400]}"
            ) from e

    def health_check(self) -> bool:
        """
        Return True if the proxy is reachable and the model responds.

        Uses a minimal chat completion probe instead of /health, because
        some LiteLLM builds leave /health unresponsive while the completions
        endpoint works correctly. The probe uses max_tokens=1 to minimize cost.
        """
        try:
            body = json.dumps(
                {
                    "model": self._model,
                    "messages": [{"role": "user", "content": "Reply with just the word OK"}],
                    "max_tokens": 10,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=self._timeout)
            return True
        except Exception:
            return False

    def classify_d1(self, content: str) -> ClassificationResult:
        from cerebra.cognition.sku_classifier import _build_classification_prompt

        prompt = _build_classification_prompt(content)
        t0 = time.monotonic()

        raw_response = self._call_chat_completions(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw_text = raw_response["choices"][0]["message"]["content"]
        usage = raw_response.get("usage", {})
        model_string = raw_response.get("model", self._model)

        result = _parse_classification_response(raw_text)
        result.latency_ms = latency_ms
        result.input_tokens = usage.get("prompt_tokens")
        result.output_tokens = usage.get("completion_tokens")
        result.model_string = model_string
        return result

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError("ProxyLLMAdapter does not support two-pass classification")

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError("ProxyLLMAdapter does not support two-pass classification")

    def _call_chat_completions(self, prompt: str) -> Any:
        body = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise ClassificationError(f"Proxy returned HTTP {e.code}: {error_body[:400]}") from e
        except urllib.error.URLError as e:
            raise ClassificationError(
                f"Proxy unreachable at {self._base_url}: {e.reason}\n"
                "Start the AI stack: cd ~/Projects/ai-stack && docker compose up -d"
            ) from e


class OllamaDirectAdapter(LLMAdapter):
    """
    LLM adapter that calls Ollama at its native HTTP API, bypassing LiteLLM.

    Used for the SKU classifier because LiteLLM's drop_params: true silently
    strips Ollama-specific options (think, format) that we need for:
      think: false  — disables Qwen 3's extended chain-of-thought reasoning,
                      which was causing 1–3 minute per-call latency
      format: json  — grammar-constrained JSON output, eliminating parse failures

    Production default: huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M (Granite 4.1 3B instruct — verified by modelfile template having full chat/tool-call format).
    Granite 4.1 3B has no thinking mode by design — think: false is a no-op but harmless.
    Override via OLLAMA_MODEL env var or constructor argument.
    Fallback (legacy): if options.think is not respected by the running Ollama version,
    prepend "/no_think\n\n" to the user message — Qwen 3 recognised this token.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        temperature: float = 0.0,
    ) -> None:
        # Use 127.0.0.1 (IPv4) not localhost — Docker port forwarding only works
        # on IPv4; localhost resolves to ::1 first and the connection hangs.
        self._base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        ).rstrip("/")
        self._model = model or os.environ.get(
            "OLLAMA_MODEL", "huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M"
        )
        self._timeout = timeout if timeout is not None else TIMEOUT_SECONDS
        self._temperature = temperature

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        raw = self._call_ollama_chat(prompt, json_mode=False)
        return str(raw["message"]["content"])

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        raw = self._call_ollama_chat(prompt, json_mode=True)
        content = str(raw["message"]["content"])
        try:
            return cast(dict[str, Any], json.loads(content))
        except json.JSONDecodeError as e:
            raise ClassificationError(
                f"complete_structured: JSON parse failed: {content[:400]}"
            ) from e

    def health_check(self) -> bool:
        """
        Return True if Ollama is reachable and the model responds.
        Uses a minimal inference probe (num_predict=10) to warm the model.
        """
        try:
            body = json.dumps(
                {
                    "model": self._model,
                    "messages": [{"role": "user", "content": "Reply with just the word OK"}],
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 10},
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=self._timeout)
            return True
        except Exception:
            return False

    def classify_d1(self, content: str) -> ClassificationResult:
        from cerebra.cognition.sku_classifier import _build_classification_prompt

        prompt = _build_classification_prompt(content)
        t0 = time.monotonic()

        raw_response = self._call_ollama_chat(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw_text = raw_response["message"]["content"]
        model_string = raw_response.get("model", self._model)
        input_tokens = raw_response.get("prompt_eval_count")
        output_tokens = raw_response.get("eval_count")

        result = _parse_classification_response(raw_text)
        result.latency_ms = latency_ms
        result.input_tokens = input_tokens
        result.output_tokens = output_tokens
        result.model_string = model_string
        return result

    def classify_quadrant(self, content: str) -> ClassificationResult:
        from cerebra.cognition.sku_classifier import _build_pass1_prompt

        prompt = _build_pass1_prompt(content)
        t0 = time.monotonic()
        raw_response = self._call_ollama_chat(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)
        raw_text = raw_response["message"]["content"]
        model_string = raw_response.get("model", self._model)
        result = _parse_quadrant_response(raw_text)
        result.latency_ms = latency_ms
        result.input_tokens = raw_response.get("prompt_eval_count")
        result.output_tokens = raw_response.get("eval_count")
        result.model_string = model_string
        return result

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        from cerebra.cognition.sku_classifier import _build_pass2_prompt

        prompt = _build_pass2_prompt(content, quadrant)
        t0 = time.monotonic()
        raw_response = self._call_ollama_chat(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)
        raw_text = raw_response["message"]["content"]
        model_string = raw_response.get("model", self._model)
        result = _parse_classification_response(raw_text)
        result.latency_ms = latency_ms
        result.input_tokens = raw_response.get("prompt_eval_count")
        result.output_tokens = raw_response.get("eval_count")
        result.model_string = model_string
        return result

    def _call_ollama_chat(self, prompt: str, json_mode: bool = True) -> Any:
        body_dict: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {
                "temperature": self._temperature,
            },
        }
        if json_mode:
            body_dict["format"] = "json"
        body = json.dumps(body_dict).encode("utf-8")

        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise ClassificationError(f"Ollama returned HTTP {e.code}: {error_body[:400]}") from e
        except urllib.error.URLError as e:
            raise ClassificationError(
                f"Ollama unreachable at {self._base_url}: {e.reason}\n"
                "Start the AI stack: cd ~/Projects/ai-stack && docker compose up -d"
            ) from e


def _try_extract_partial_json(text: str) -> dict[str, object] | None:
    """
    Fallback extractor for malformed JSON responses.

    The model sometimes includes unescaped quotes in the `reasoning` field,
    breaking `json.loads`. This extracts the scores block and primary field
    via regex so the load-bearing fields are recovered even when reasoning
    is malformed. Returns None if scores cannot be extracted.
    """
    scores: dict[str, float] = {}
    # Extract individual score values: "CATEGORY_NAME": 0.XX
    score_pattern = re.compile(r'"([A-Z_]+)":\s*([\d.]+)')
    category_names = {
        "OBSERVATION",
        "PATTERN",
        "MECHANISM",
        "PHENOMENON",
        "TECHNIQUE",
        "DESIGN",
        "CREATION",
        "TOOL",
        "PRINCIPLE",
        "JUDGMENT",
        "GOAL",
        "CONSTRAINT",
        "EVENT",
        "AGENT",
        "CONTEXT",
        "RELATION",
    }
    for m in score_pattern.finditer(text):
        name, val = m.group(1), m.group(2)
        if name in category_names:
            import contextlib

            with contextlib.suppress(ValueError):
                scores[name] = max(0.0, min(1.0, float(val)))

    if not scores:
        return None

    # Extract confidence
    conf_match = re.search(r'"confidence":\s*([\d.]+)', text)
    confidence = float(conf_match.group(1)) if conf_match else 0.0

    # Extract primary (before it might be truncated)
    primary_match = re.search(r'"primary":\s*"([A-Z_]+)"', text)
    primary = primary_match.group(1) if primary_match else max(scores, key=lambda k: scores[k])

    return {"scores": scores, "confidence": confidence, "primary": primary, "reasoning": ""}


def _parse_quadrant_response(raw_text: str) -> ClassificationResult:
    """Parse Pass 1 quadrant response: {"scores": {"EMPIRICAL":..., ...}, "confidence":..., "primary":"QUADRANT"}"""
    text = raw_text.strip()
    if not text:
        raise ClassificationError("Model returned empty response for quadrant pass")
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1
        while end > 0 and not lines[end].startswith("```"):
            end -= 1
        text = "\n".join(lines[1:end]) if end > 0 else "\n".join(lines[1:])
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ClassificationError(f"Quadrant response JSON parse failed: {raw_text[:400]}") from e

    valid_quadrants = {"EMPIRICAL", "GENERATIVE", "NORMATIVE", "RELATIONAL"}
    scores_raw = data.get("scores", {})
    if not scores_raw:
        scores_raw = {k: v for k, v in data.items() if k in valid_quadrants}
    if not scores_raw:
        raise ClassificationError(f"Quadrant response has no scores: {raw_text[:400]}")

    scores: dict[str, float] = {}
    for name in valid_quadrants:
        val = scores_raw.get(name, 0.0)
        try:
            scores[name] = max(0.0, min(1.0, float(val)))
        except (TypeError, ValueError):
            scores[name] = 0.0

    confidence = float(data.get("confidence", 0.0))
    primary = str(data.get("primary", max(scores, key=lambda k: scores[k]))).upper()
    if primary not in valid_quadrants:
        primary = max(scores, key=lambda k: scores[k])

    return ClassificationResult(scores=scores, confidence=confidence, primary=primary, reasoning="")


def _parse_classification_response(raw_text: str) -> ClassificationResult:
    """
    Parse the model's JSON response into a ClassificationResult.

    Handles three model output variants observed in practice:
    1. Canonical:  {"scores": {"MECHANISM": 0.9, ...}, "confidence": 0.8, "primary": "MECHANISM", ...}
    2. Flat:       {"MECHANISM": 0.9, ..., "reasoning": "..."}  (no "scores" wrapper)
    3. Malformed:  valid JSON except for unescaped quote in "reasoning" field

    Strips markdown code fences if present. Raises ClassificationError on total failure.
    """
    from cerebra.cognition.sku_categories import D1Category

    text = raw_text.strip()
    if not text:
        raise ClassificationError("Model returned empty response")

    # Strip markdown code fences if the model wrapped its JSON
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1
        while end > 0 and not lines[end].startswith("```"):
            end -= 1
        text = "\n".join(lines[1:end]) if end > 0 else "\n".join(lines[1:])
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract scores + primary with regex (handles unescaped quotes in reasoning)
        data = _try_extract_partial_json(text)
        if data is None:
            raise ClassificationError(
                f"JSON parse failed and fallback extraction found no scores.\n"
                f"Raw response (first 500 chars): {raw_text[:500]}"
            ) from None

    all_names = {c.name for c in D1Category}

    # Accept both canonical ("scores" wrapper) and flat format
    scores_raw = data.get("scores", {})
    if not scores_raw:
        # Flat format: model put scores at top level mixed with other fields
        scores_raw = {k: v for k, v in data.items() if k in all_names}
    if not scores_raw:
        raise ClassificationError(f"Response has no recognizable scores. Raw: {raw_text[:400]}")

    # Normalize: fill any missing categories with 0.0
    all_names = {c.name for c in D1Category}
    scores: dict[str, float] = {}
    for name in all_names:
        val = scores_raw.get(name, 0.0)
        try:
            scores[name] = max(0.0, min(1.0, float(val)))
        except (TypeError, ValueError):
            scores[name] = 0.0

    confidence = float(data.get("confidence", 0.0))
    primary = str(data.get("primary", max(scores, key=lambda k: scores[k]))).upper()
    reasoning = str(data.get("reasoning", ""))

    # Validate primary is a known category
    if primary not in all_names:
        # Fallback to highest scorer
        primary = max(scores, key=lambda k: scores[k])

    return ClassificationResult(
        scores=scores,
        confidence=confidence,
        primary=primary,
        reasoning=reasoning,
    )
