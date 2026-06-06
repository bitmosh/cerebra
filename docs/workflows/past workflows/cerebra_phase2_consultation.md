# Cerebra Phase 2 Classifier — Architectural Consultation

## Why we're asking

We're at a Phase 2 calibration impasse and we want a fresh, deep read on the situation before deciding the path forward.

We're not asking you to write code. We're asking you to read the codebase carefully, then offer your most honest engineering analysis. This is an architectural consultation, not an implementation task.

Read the project's planning docs, read the implementation, run the tests if useful, and then tell us what you actually think — including the parts where you disagree with the current direction.

Your audience is the developer (Ryan) and a senior planner who has been guiding the project from the architectural side. We want substance over diplomacy.

---

## Project context

Cerebra is a local-first cognitive runtime under the **Lattica** suite (alongside LumaWeave, Bons.ai, and the deferred Policy Scout). It is architecture-complete at v0.1 with ~28 planning docs at `docs/refined-runtime-model/`. The implementing agent is named **bandit**; it has shipped Phase 0 (v0.0.0), Phase 1 (v0.0.1), and a v0.0.1a follow-up. The protocol it operates under is in `.claude/AGENTS.md`, with the Discord coordination in `docs/agent/CEREBRA_DISCORD_PROTOCOL.md` and the persistent reference in `docs/agent/CEREBRA_CLAUDE.md`.

Phase 2 — **SKU classifier and addressing** — is the first phase where LLM calls become load-bearing. The classifier assigns a 10-digit hex SKU address to every memory record (~745 ingested chunks from the planning docs). The full SKU format is documented in `docs/refined-runtime-model/CEREBRA_SKU_ADDRESSING.md`. For v0.1.0 (Phase 2 target version), only D1 (primary cognitive category from 16 options), D4 (relationship axis), D7-D8 (occupancy index), D9 (modality), and D10 (provenance) are populated. D2, D3, D5, D6 are intentionally stubbed.

LLM backend: a local Docker Compose stack at `~/Projects/ai-stack/`. LiteLLM proxy at `http://localhost:4000` routing `cerebra-classifier` → `ollama/qwen3.5:latest` (Qwen 2.5 family, 6.6GB, ~7B params). Hardware: RTX 4070 Super, 12GB VRAM. The LLMAdapter (`cerebra/cognition/llm_adapter.py`) talks to the proxy via stdlib `urllib.request` — no PyPI dependency for LLM access.

The deviation log for Phase 2 is at `docs/agent/deviations/v0.1.0.md` — read it for the running narrative of what bandit has surfaced as deviations from plan.

---

## What we're hitting

The Phase 2 plan included a calibration gate: 70% top-1 D1 agreement on a hand-labeled 30-fixture set before merge.

**v1.0.0 prompt result: 12/30 = 40%.** Bandit identified six systematic category-pair confusions: TECHNIQUE↔MECHANISM, CONSTRAINT↔PRINCIPLE, DESIGN↔TECHNIQUE, TOOL↔MECHANISM, CONTEXT↔DESIGN, OBSERVATION↔EVENT. The model couldn't distinguish these pairs from the original short category descriptions.

**v1.1.0 prompt response:** bandit added a `KEY DISTINCTIONS` section with detailed disambiguation rules, examples, and decision tests per confused pair. The full prompt is in `cerebra/cognition/sku_classifier.py` (look for `PROMPT_VERSION = "1.1.0"`). It is roughly 5000 characters.

**The calibration test on v1.1.0 has been running for 5+ hours and hasn't completed.** Per-call latency to the Ollama backend (visible in `docker logs ai-stack_ollama_1`) ranges from 41 seconds to 5 minutes per classification, with most calls landing in the 1-3 minute range. The test process is alive but appears genuinely stuck (last LLM call was ~30 minutes before this prompt was written).

The test file is `tests/integration/test_sku_fixtures.py`. The fixture set is `tests/fixtures/sku_fixtures.py` (30 chunks: 15 marked `difficulty="clear"`, 15 marked `difficulty="hard"` with `ambiguous_with` annotations).

The senior planner's read of the situation:

1. The v1.1.0 prompt traded throughput for accuracy by packing all disambiguation logic into every call. Most of each call's latency is the model re-reading the same instructions for a different chunk. ~96% of each prompt is unchanging instructions; ~4% is the chunk being classified.

2. Qwen2.5's default Ollama context is 4096 tokens. The v1.1.0 prompt uses ~1500 tokens of that on instructions alone. The model has limited remaining attention budget for the actual classification reasoning.

3. The calibration test design has no per-fixture timeout enforcement that fires fast enough to keep the test bounded, no parallel execution, no fast-iteration vs final-gate tier separation, and no partial result persistence (results only emit if the test completes cleanly).

4. The category-pair confusions may not actually be solvable by adding more prompt instructions. They may be a signal that the architecture wants two-pass classification: a fast coarse pass to identify candidates, then a targeted disambiguation pass only when the top two candidates are a known-confusable pair.

5. Ollama supports KV cache reuse and prompt caching via `keep_alive`, but the developer believes these are not currently being utilized. Verifying this and exploiting it could change the cost profile dramatically without touching the prompt at all.

6. LoRA adapters trained on the classification task could move the disambiguation logic from prompt-time to weight-time, dramatically reducing per-call prompt size while preserving (or improving) accuracy. The developer has 12GB VRAM and the hardware to do this, but Cerebra doesn't yet have a corpus of labeled examples for training. The full Phase 2 backfill would *produce* that corpus.

7. Schema-driven generation (Ollama's `format: "json"` parameter, or stricter grammar-constrained decoding) could reduce JSON parse failure rate and possibly latency by eliminating the model's freedom to wander outside the schema.

We've been considering several architectural directions and want your read.

---

## What we'd like from you

Read the actual code and planning docs. Specifically worth reading:

- `cerebra/cognition/sku_classifier.py` — the classifier, the prompt strings, the backfill orchestrator
- `cerebra/cognition/llm_adapter.py` — the HTTP client adapter
- `tests/integration/test_sku_fixtures.py` — the calibration test
- `tests/fixtures/sku_fixtures.py` — the 30-fixture labeled set
- `docs/refined-runtime-model/CEREBRA_SKU_ADDRESSING.md` — the SKU spec
- `docs/refined-runtime-model/CEREBRA_INGESTION_ARCHITECTURE.md` — the classifier's role in the pipeline
- `docs/refined-runtime-model/CEREBRA_DEV_ROADMAP_v8.1.md` — what Phase 2 is supposed to enable for Phase 3+
- `docs/refined-runtime-model/CEREBRA_PROJECT_SCOPE.md` — the doctrine and what v0.1 is
- `docs/agent/deviations/v0.1.0.md` — what bandit has surfaced as deviations from plan
- The litellm config at `~/Projects/ai-stack/litellm/litellm-config.yaml` if you can reach it (read-only)

You're welcome to run the failing test, run small probes against the proxy (`curl http://localhost:4000/v1/chat/completions` with a small prompt), inspect the SQLite vault at `~/cerebra-vaults/dev/data/cerebra.db`, or do anything else that helps you understand the actual situation. Don't write production code or modify anything.

Once you've read enough to have a grounded view, answer these questions in a single markdown document. Be honest where you disagree with our framing.

### 1. The classifier prompt

Read the v1.1.0 prompt in `sku_classifier.py`. Is the size genuinely the throughput problem we think it is, or is something else dominating?

If you ran a 1500-char version of the prompt against the same fixtures, what would you predict happens to accuracy and to latency? Argue from what you can see in the prompt and what you know about Qwen2.5.

Are there specific lines or sections of the v1.1.0 prompt you'd cut first? Why those?

### 2. The two-pass architecture

If you were to redesign Phase 2 to use a coarse classifier followed by targeted disambiguation:

- What would the coarse prompt look like?
- What's the data structure for routing from coarse output to targeted disambiguation?
- When does the second pass NOT fire (most chunks should be one-pass)?
- How does this interact with the existing `LLMAdapter` and `sku_assignments` schema? Is the data model already compatible or does it need v1.2 changes?

Is this actually better, or is it just shifting cost around? Quantify if you can.

### 3. KV cache and prompt caching at the inference layer

Verify (don't guess) whether Ollama is currently reusing KV cache across requests. Look at the Ollama logs, run a few probes, check the config. What's the current behavior?

If KV cache reuse is not happening, what's the minimum change to enable it? Is the cost-benefit worth doing as a Phase 2 squeeze-in, or does it belong in Phase 3?

If KV cache IS being reused but isn't helping, why not? (Possible: every call has unique system prompt + chunk content, no shared prefix.)

### 4. Schema-driven generation

Ollama's `format` parameter and the `format: "json"` option (or full JSON schema constraint) — would using these eliminate the model's wander-outside-the-schema failure modes? What's the right level of constraint (free-form, json-mode, full-schema)?

Does LiteLLM pass through the format parameter, or does its `drop_params: true` setting strip it? Check the proxy behavior.

If JSON-mode works at the Ollama level but LiteLLM strips it, is there a clean way around (direct Ollama HTTP from Cerebra, bypassing LiteLLM for classification)?

### 5. LoRA / fine-tuning track

Realistically: how far away is a working classifier-specific LoRA?
- What corpus would we need to train it?
- What's the minimum viable training pipeline given the developer's hardware (RTX 4070S, 12GB VRAM)?
- What's the expected accuracy lift vs. v1.1.0 prompt-only?
- Could LoRA-tuning the *evaluation* task (judging whether a classification is correct) be a separate higher-leverage path?

If LoRA is realistic for v0.2, what does the Phase 2 close-out need to capture from production runs so we have training data when we get there?

### 6. The calibration test itself

Honest read: is the current calibration test fit for purpose?

Specifically:
- Is the 30-fixture/serial/all-or-nothing design appropriate for iterative prompt development, or does it need a fast iteration tier?
- Should test failures be graceful (per-fixture pass/fail with partial reports written to disk as they happen) rather than catastrophic (whole-test crash if any call hangs)?
- Is the fixture set itself well-designed? Look at `sku_fixtures.py` and judge.

Propose changes if needed. Don't be precious about preserving bandit's existing test design.

### 7. Phase 2 close-out path

Given everything you've read, what should we actually do?

Option A: ship v1.1.0 at slow throughput, accept that the full backfill is a one-time multi-hour run, defer architecture changes to v0.1.1+.

Option B: ship a v1.2.0 with the two-pass architecture, accepting another iteration delay but a more sustainable foundation.

Option C: ship v1.2.0 with two-pass AND KV cache exploitation, fully de-risk the throughput problem before merging.

Option D: don't ship Phase 2 yet; the calibration set and threshold are wrong; redesign the test before more prompt work.

Option E: something we haven't named.

Pick one with your reasoning. Be specific about what "ship" means in your chosen option — what's the version number, what's in the merge gate, what's the calibration evidence required, what's documented as deferred to a future version.

### 8. Anything we're missing

What questions should we be asking that we're not? What concerns surface from reading the code that aren't in this prompt? Where is the architecture more fragile than the developer realizes, and where is it stronger than they realize?

The Phase 2 close-out matters because every subsequent phase reads SKUs from storage. If the substrate is wrong, Phase 3-8 inherit that wrongness. Better to surface concerns now than discover them in Phase 5.

---

## Format

Reply in markdown. Use headers per section. Be substantive — short answers are fine when the question is answered, but don't pad anything. Where you disagree with the framing, say so directly and explain why. Where you're uncertain, say so explicitly rather than papering it over.

If your read changes mid-investigation (you start with one hypothesis and the code shows you a different picture), include that change of mind in the response — it's useful signal.

Quote specific code or doc passages when they're load-bearing for your argument. Don't refer to things abstractly when you can point at the exact file and line.

Time horizon: take whatever time you need. This is a planning consultation, not a sprint task.
