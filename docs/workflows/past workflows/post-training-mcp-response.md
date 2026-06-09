# Response: Post-Training MCP Discussion

**Date:** 2026-06-05  
**Re:** `post-training-mcp-discussion.md` — critique of smol-training-mcp + multi-source expansion proposal

---

## Where I stand

The planning Claude's review is accurate and the multi-source expansion is the right call. I've now read the Smol Playbook in depth, which lets me be more specific than "go multi-source" — I can tell you which parts of it actually earn their place in the MCP and which parts are anecdote dressed as principle. I'll also push on the cognitive-nature insight, because I think it should be driving this design decision more than it currently is.

The short version: build the indexed corpus first, build Unsloth tooling second, build the structured knowledge layer third. Keep the decision-tree tools out until you've used it for a month and found you actually need them. And rename it.

---

## The cognitive-nature insight shapes the scope

The planning Claude gave the cognitive-nature reframe one paragraph and called it "worth a brainstorm doc." I'd give it more weight than that, because it's not a downstream concern — it changes what the MCP server is for *right now*.

You described wanting Cerebra's 16-category taxonomy to eventually be part of its cognitive structure, not a tool applied to perception. The model shouldn't classify content against the taxonomy — it should *see* through the taxonomy, the way a radiologist doesn't apply a "fracture vs. no fracture" classifier to an X-ray but has already internalized what fracture-ness looks like.

That goal defines a specific training arc: 

```
Cerebra v0.x  → classifies with prompts (current)
Cerebra v0.2  → fine-tuned on its own prompt-classifications (SFT)
Cerebra v0.3  → classifications improve because the taxonomy is in weights, not prompt
Cerebra v0.4+ → uses v0.3's perceptual frame to produce better training data for v0.5
                 (the loop closes)
```

This is a self-bootstrapping cognitive loop, and the MCP server's job is to support the specific training cycles that get you from v0.1 to where the loop closes.

**What that means for MCP scope**: You don't need a comprehensive training methodology advisor. You need a tool that supports two things:

1. **Executing Cerebra's LoRA fine-tuning runs** (Unsloth tooling, VRAM estimation, config generation)
2. **Answering questions that come up during those runs** (retrieval over the indexed corpus when you hit something the structured knowledge doesn't cover)

Everything else — architecture baselines for pretraining, ablation planning, the full SFT/DPO/GRPO decision tree — is valuable someday but not for the next 2-3 training cycles. The planning Claude said this but I want to be more emphatic: let Cerebra's actual training needs drive what tools get built, not what a comprehensive training methodology server *should* have.

---

## What the multi-source design gets right (and where to push further)

The planning Claude's revised architecture is sound. The key moves are correct:

**Sourced claims over authoritative claims.** Right. Smol Playbook, OLMo 3, Tülu 3, and Unsloth disagree on real things — data mixing ratios, post-training method order, loss spike remediations. A system that papers over those disagreements and returns a single answer is wrong. Foregrounding disagreement is more honest and more useful.

**The disagreements files are the most valuable thing in the design.** I want to emphasize this. The `knowledge/disagreements/` directory — `data_mixing.json`, `posttraining_order.json`, `loss_spike_remediations.json` — is the most original part of the proposed design and the most likely to be dropped as scope pressure increases. Don't drop it. Here's why: when you're mid-training and your loss is spiking, you want to know what each team tried, not a single recommendation. The disagreement between "HuggingFace added Z-loss and it fixed it" and "OLMo team didn't hit this and used gradient clipping" is the information. The synthesis is less useful than the attribution.

**Indexed corpus before structured tools.** Correct order. Build retrieval over the actual source documents first. Every structured knowledge claim you add to a JSON file is one you pre-decided was important enough to formalize. Retrieval over the raw corpus doesn't require you to pre-decide anything — it answers questions you haven't thought of yet. That's the higher-value investment for a v0.1.

**Where I'd push further**: The planning Claude describes the indexed corpus as a fallback ("when the structured knowledge doesn't have the answer"). I'd invert that relationship. For most questions, you want to **start** with retrieval against the primary source documents and treat the structured JSON as a convenience layer for the things you query constantly (formulas, architecture baselines). The corpus is the ground truth; the JSON is a cache of the most common queries against it.

---

## What the sources actually contribute (having read the Smol Playbook)

Now that I've read the Smol Playbook in depth, I can be specific about what each source contributes:

### Smol Playbook (Oct 2025)

**Earns its place:**
- The ablation methodology — the discipline of one-change-at-a-time, the two-attribute split (speed + reliability for experiments), the distinction between architecture ablations (fixed data mix) and data ablations (fixed architecture). This is transferable methodology, not HF-specific.
- The architecture decision tables — the actual comparison of MHA/MQA/GQA/MLA with ablation results at 1B scale. The `recommend_baseline` and `select_attention` tools from the original proposal are good because they're backed by this empirical work.
- The parameter estimation formulas — pure math, directly extractable, exactly what should be in a JSON knowledge file.
- The evaluation suite design principles: monotonicity, low noise, above-random performance, ranking consistency. These are criteria, not opinions, and they transfer across all training contexts.
- The cost breakdown: ablations consumed 37% of total compute. Planning for ablation costs is a real thing people underestimate; having a calibration anchor is useful.

**Doesn't earn its place as authoritative:**
- The `should_i_train` flowchart — this is HF's rationale for SmolLM3's situation, written for a team that chose to pretrain a 3B model because they saw a gap in the open ecosystem. The thresholds are theirs.
- The data mix ratios (FineWeb-Edu 70%, FineMath 20%, Python-Edu 10%) — these are for their specific task. Cerebra's optimal mix for fine-tuning a 16-way cognitive classifier is completely different.
- Framework recommendations — they built Nanotron. Of course they recommend it.

**The planning Claude is right**: the Smol Playbook is a 200-page memoir. The chapters on *how* they made decisions (ablation discipline, evaluation criteria, derisking methodology) are more valuable than the chapters on *what* they decided.

### What I expect from OLMo 3 + Tülu 3 (haven't read yet, but reasoning from what I know)

**OLMo 3** — the value is in architectural transparency. OLMo is the most fully documented pretraining pipeline in the open ecosystem (every data sample traceable, every hyperparameter decision explained). For Cerebra's purposes, this is most relevant for understanding *continued pretraining* patterns, since you may eventually want to do mid-training on domain-specific data before SFT.

**Tülu 3** — this is the most directly relevant source for Cerebra right now, because Tülu 3 is specifically about post-training a capable base model into a task-aligned model. The SFT → RLVR recipe is the playbook you'd follow for Cerebra v0.2. It's also well-documented: the hyperparameters are published, the data curation decisions are explained, the evaluation methodology is rigorous. Before writing any fine-tuning code, the Tülu 3 paper should be in your indexed corpus and you should be running retrieval queries against it.

### Unsloth

The planning Claude's framing is right: Unsloth is the execution layer, not the methodology layer. It answers "how do I run this on my hardware" not "what should I run." The specific tools it should drive:

- `estimate_lora_vram(base_model, rank, batch_size, seq_len)` — pure math, high-frequency query
- `recommend_lora_rank(task_complexity, dataset_size)` — empirical recommendations from Unsloth's own guidance
- `generate_unsloth_script(base_model, dataset_path, hardware)` — config template generation
- `check_model_support(model_id)` — supported models list, known quirks per model

These four tools are probably the highest-immediate-leverage additions to the whole MCP. Cerebra's next training work involves LoRA fine-tuning on consumer hardware. These answer the questions you'll actually have.

---

## Phase 1 in practice: what "indexed corpus" actually means

The planning Claude describes the indexing architecture at a high level. Let me get specific about the decisions that actually matter.

### The chunking problem for technical documents

Naive fixed-token chunking will fail badly on these documents. Dense technical papers have:

- **Tables** — a mid-table chunk boundary breaks the meaning entirely. A chunk containing "GQA ratio 8, 4, 2 | 0.6%| 1.24B | Our baseline" is useless without the table header.
- **Formulas** — `s_KV = 2 × n_bytes × seq × n_layers × n_heads × dim_heads` separated from its variable definitions is meaningless noise.
- **Code blocks** — a Python config fragment without its surrounding explanation has no retrieval value.
- **Section hierarchy** — "see §4 for details" cross-references make isolated paragraphs harder to interpret.

**Recommended chunking strategy**: structure-aware chunking, not fixed-token chunking.

1. **Parse document structure first**: For PDFs, use PyMuPDF or pdfplumber to extract text with heading/block structure. For markdown/HTML docs, parse with a proper parser (not regex).

2. **Chunk at section boundaries**: Each top-level section is a natural chunk boundary. If a section is longer than your target window (~400-600 tokens), split at subsection boundaries.

3. **Never split tables**: Keep the full table as one chunk even if it exceeds the target size. Include the table's section header as part of the chunk text.

4. **Keep formulas with their variable definitions**: If a formula appears in a paragraph, keep the full paragraph (definition + formula) as one chunk.

5. **Chunk metadata**: Every chunk carries `{source, version, section_path, page_range, chunk_type: "text"|"table"|"code"|"formula", estimated_tokens}`.

6. **Overlap**: Small overlap (1-2 sentences) between adjacent text chunks so that a sentence at a boundary isn't invisible. No overlap across section boundaries.

This is more engineering than "split every 500 tokens," but retrieval quality for technical content depends on it. A table about GQA tradeoffs that gets split between chunk 3 and chunk 4 will never be retrieved correctly.

### Hybrid retrieval: why and how

BM25 alone is good at exact keyword matches: "grouped query attention ratio 8" → returns paragraphs with those words. Vector search alone is good at semantic similarity: "attention KV cache memory reduction" → returns related content even without exact words. Neither alone is sufficient for technical content. Hybrid (BM25 + vector, reciprocal rank fusion) is meaningfully better than either for mixed technical vocabulary.

The planning Claude recommended `bge-base-en-v1.5` (440MB). That's reasonable for CPU + occasional GPU use. For a lighter initial build, `all-MiniLM-L6-v2` (90MB) is fast and CPU-feasible, just weaker on technical content. The embedding model choice matters less than the chunking strategy — fix the chunks first.

**Implementation**: `rank-bm25` (pure Python, no deps) for BM25. `faiss-cpu` or `chromadb` for vector search. Reciprocal rank fusion at retrieval time is simple to implement and works well. Don't overengineer the retrieval infrastructure — BM25 + FAISS with RRF is the industry-standard baseline that works.

### Source attribution schema

Every claim needs this structure:

```json
{
  "claim": "GQA with ratio 4-8 matches MHA performance while reducing KV cache",
  "source": "smol_playbook",
  "source_version": "2025-10",
  "section": "Architecture Choices / Attention / Ablation — GQA Beats MHA",
  "page_range": "24-27",
  "claim_strength": "empirical",
  "conditions": "1B parameter dense transformer, 45B token ablation",
  "caveats": "Ablated at SmolLM3 scale only; MLA not ablated (not in Nanotron at time)",
  "conflicts_with": []
}
```

`claim_strength` options:
- `"math"` — pure formula, source-neutral (parameter estimation, KV cache size)
- `"consensus"` — multiple sources agree independently
- `"empirical"` — one team's experiment at their specific scale/conditions
- `"opinionated"` — team preference, explicitly presented as such
- `"experimental"` — new/unvalidated, from a single experiment

The `conditions` field is critical. "GQA beats MHA" without "at 1B parameters on 45B token ablation" is a claim that might not transfer to your 3B model fine-tuning scenario.

---

## The disagreements layer in detail

This is worth spelling out specifically because it's the part most likely to be deprioritized as implementation pressure mounts.

**`posttraining_order.json`** should document explicitly:

| Claim | Smol Playbook | Tülu 3 | Unsloth guidance | Conditions |
|---|---|---|---|---|
| Standard post-training order | SFT → DPO | SFT → RLVR → optionally DPO | SFT → GRPO (skip DPO) | None stated |
| When DPO applies | General assistant preference alignment | Preference data available | When you have preference pairs | depends on data availability |
| When GRPO/RLVR applies | Not covered | Verifiable rewards (math, code, logic) | Verifiable rewards available | task must have ground-truth verifier |

For Cerebra specifically: the 16-way classification task has a **verifiable reward** — classification is either correct or incorrect against the gold taxonomy. That's exactly the RLVR/GRPO condition. So Cerebra's post-training path is more likely SFT → GRPO than SFT → DPO, but that disagreement between sources should be visible in the MCP's response, not hidden behind a single recommendation.

**`data_mixing.json`** should separate:
- Pretraining data mixing (HF's numbers; probably not directly relevant to Cerebra)
- SFT data mixing (Tülu 3 is the primary source here — they're explicit about quality vs. quantity tradeoffs)
- Fine-tuning data mixing (how to balance the synthetic classification data Cerebra generates vs. human-validated examples)

**`loss_spike_remediations.json`** — keep this explicitly multi-source and explicitly labeled as "known patterns, not diagnosis":

```json
{
  "spike_type": "sudden loss spike mid-training",
  "smol_playbook": {
    "cause": "tensor parallelism bug causing numerical instability",
    "remediation": "checkpoint recovery + investigation; added Z-loss stabilization",
    "conditions": "384 GPUs, 3B model, ~2T tokens into run"
  },
  "olmo3": { ... },
  "general_categories": [
    "learning rate too high for current batch size",
    "gradient accumulation step mismatch",
    "corrupted batch in data pipeline",
    "numerical overflow in attention (long contexts)",
    "checkpoint corruption"
  ],
  "note": "These are documented cases. Most spikes are novel. Use as starting checklist, not exhaustive diagnosis."
}
```

---

## On naming and framing

`smol-training-mcp` is a bad name for what this is becoming. It names the smallest source in the corpus rather than the purpose.

Options, roughly ranked:
- **`training-oracle-mcp`** — describes the function (queries against training methodology knowledge), appropriately humble ("oracle" is traditionally a thing you ask, not a thing that decides)
- **`ml-training-kb-mcp`** — explicit that it's a knowledge base, not a decision system
- **`training-knowledge-mcp`** — plain and accurate, matches the planning Claude's revised architecture name

I'd go with `training-knowledge-mcp`. It's descriptive, doesn't overclaim, and matches the directory structure the planning Claude sketched.

---

## Cerebra as its own backend (the long-game architecture)

The planning Claude flagged this: the training-knowledge MCP is structurally similar to Cerebra. Sourced claims, indexed corpus, hybrid retrieval, multi-source. This is worth developing.

**The short-term build**: standalone Python project with its own indexing pipeline. This is faster to ship and doesn't require Cerebra to be mature.

**The medium-term realization**: once Cerebra v0.2+ is stable and has reliable retrieval, the training-knowledge MCP becomes a Cerebra vault with a specialized tool layer. The PDF corpus is Cerebra's source material. The structured JSON knowledge layer maps naturally to Cerebra's SKU-classified memory records. The tool layer is a set of Python functions that query Cerebra's SQLite store plus the specialized math tools.

**What this means for building now**: don't design the standalone MCP in a way that makes migration to Cerebra-backed hard. Specifically:
- Store source documents in a `corpus/` directory with stable paths (same as what Cerebra would ingest)
- Design the source attribution schema to be compatible with Cerebra's `detected_type` and `sku_address` fields — you'll want to map them later
- Keep the retrieval layer thin and replaceable — a `retrieve(query, source_filter)` function that today calls FAISS but tomorrow calls Cerebra's query interface

This is an hour of upfront design that avoids a rewrite later.

**There's a deeper point here**: by building the training-knowledge MCP, you're going through Cerebra's own architecture at smaller scale. The chunking strategy decisions you make for technical PDFs are exactly the decisions Cerebra will need for arbitrary documents. The hybrid retrieval tuning you do against 4-5 source documents generalizes to Cerebra's broader use. The source attribution schema you design is a prototype for Cerebra's provenance tracking.

Build it knowing you're prototyping Cerebra's retrieval layer with a constrained, tractable corpus. The feedback loop is: learnings from the MCP improve Cerebra's design, and eventually Cerebra powers the MCP.

---

## Concrete prioritization for Cerebra's situation

Given where Cerebra is (v0.0.1a, SKU classifier working, LoRA fine-tuning is the next meaningful step), here's what I'd actually build and when:

### Build now (supports the next training cycle)

**1. Unsloth tools** (1-2 days)
- `estimate_lora_vram(base_model_id, rank, batch_size, seq_len, grad_checkpointing)` — pure math, use Unsloth's documented formulas
- `generate_unsloth_script(base_model_id, dataset_path, output_dir, hardware_profile)` — config template that produces a working Unsloth training script
- `recommend_lora_rank(task_type, dataset_size, base_model_size)` — lookup from Unsloth's empirical guidance

These are immediately useful. You'll have questions about LoRA rank, VRAM budgets, and config before the first training run.

**2. Corpus indexing pipeline** (2-3 days)
- Collect: Smol Playbook PDF, Tülu 3 paper, Unsloth docs (relevant pages), and — prioritized — the OLMo 3 technical report
- Structure-aware chunking (not fixed-token)
- FAISS + BM25 indexes
- `find_in_corpus(query, source_filter=None)` tool

This becomes the fallback for everything not in the structured knowledge layer. Tülu 3's SFT recipe details, Smol Playbook's optimizer choices, OLMo's data pipeline — all queryable without you pre-deciding what to extract.

**3. Pure-math tools** (1 day)
- `estimate_parameters(hidden_size, layers, heads, kv_heads, vocab_size, tied_embeddings)` — from Smol Playbook formulas
- `kv_cache_size(n_bytes, seq_len, n_layers, n_heads, dim_head, attention_type)` — covers MHA/GQA/MQA/MLA

These are correct always, regardless of source freshness or opinion.

### Build after first training cycle (based on what you actually needed)

**4. Structured consensus knowledge** (1-2 days)
- Architecture baselines JSON (extract from what you learned during the training cycle)
- Attention tradeoffs JSON (GQA vs MHA ablation data from Smol Playbook)
- `compare_sources(topic)` tool — returns what each source says, side by side
- Initial `disagreements/` files for post-training order and data mixing

**5. Recipe extraction tools** (1-2 days)
- `extract_recipe(source, task)` — pull specific hyperparameter sets from a source document via retrieval + extraction
- `adapt_recipe(recipe, constraints)` — modify a recipe for your hardware/scale

### Explicitly defer

- **Decision-tree tools** (`should_i_train`, `classify_training_goal`) — the planning Claude is right that these encode opinion as algorithm. Defer until you've used the MCP for a training cycle and found yourself wishing you had them. You probably won't.
- **Config generation for non-Unsloth frameworks** — Nanotron, axolotl, llama-factory templates are useful if you use those frameworks. Unsloth is where you'll start; add others when you need them.
- **Diagnostic tools** — `diagnose_loss_spike` is useful as a reference checklist but dangerous as a diagnosis tool. Add it in Phase 3 with explicit "here are documented patterns, not a diagnosis" framing.

---

## What to send terminal Claude

When you're ready to start building, here's the scope:

> **Project: `training-knowledge-mcp`**  
> Multi-source training methodology knowledge base for Cerebra's fine-tuning work.  
>
> **Phase 1 (build now):**
> 1. Unsloth tools: `estimate_lora_vram`, `generate_unsloth_script`, `recommend_lora_rank` — implement as pure Python functions backed by Unsloth's documented formulas and recommendations. No LLM mediation. Typed inputs, tested outputs.
> 2. Corpus indexing pipeline: structure-aware chunking (respect tables, formulas, code blocks), FAISS + BM25 hybrid retrieval, `find_in_corpus(query, source_filter)` tool. Corpus: Smol Playbook PDF + Tülu 3 paper + Unsloth docs (collected manually first).
> 3. Pure-math tools: `estimate_parameters`, `kv_cache_size`.
>
> **Source attribution schema**: every structured claim carries `{source, source_version, section, claim_strength: "math"|"consensus"|"empirical"|"opinionated", conditions, caveats}`.
>
> **Not in Phase 1**: decision-tree tools, config generation (except Unsloth), diagnostic tools.
>
> **Before indexing**: design the chunking strategy. These are dense technical PDFs. Propose structure-aware chunking (section-boundary splits, keep tables whole, keep formulas with definitions). Show the chunk metadata schema. Then index. Test retrieval quality against 20 sample queries before proceeding.
>
> **Architecture note**: design the retrieval layer as a thin, replaceable interface (`retrieve(query, source_filter) → chunks`). Today it calls FAISS; eventually it calls Cerebra's query interface. Don't entangle the tools with the retrieval implementation.

That scope is a 1-week build for Phase 1. Validate retrieval quality before moving to Phase 2.

---

## A note on sequencing

The planning Claude said "this is genuinely a multi-week project to do well." That's right, and worth sitting with.

The question is whether building the MCP *competes with* or *accelerates* Cerebra's v0.2 training work. My read:

- Phase 1 as I've scoped it (Unsloth tools + indexed corpus + pure-math tools) **accelerates** the training work. You'll use it during the LoRA runs.
- Phase 2 onward (structured consensus, recipe tools) is **value-added** but not blocking.
- The full planning Claude scope (Phase 1-4 complete, all decision tools, all config templates) **competes with** training work if attempted before you've done any training.

So the sequencing is:
1. Build Phase 1 of the MCP
2. Run Cerebra's first LoRA fine-tuning cycle using it
3. Note what you wished the MCP had during that cycle
4. Add exactly those things

Don't pre-build what you might need. Build what you need, use it, then build what you find you're missing.

---

## Summary

The multi-source expansion is right. The `disagreements/` layer is the most important design decision and the most likely to get cut — don't cut it. The indexed corpus before structured tools is the right order. Unsloth tools first because they're immediately useful for the next training cycle. Defer decision-tree tools until you've actually needed them. Design for Cerebra-as-backend from the start without implementing it yet.

The cognitive-nature insight deserves to be the compass for scope decisions. The MCP exists to support Cerebra's training cycles. Once the loop closes — once the 16 categories are perceptual structure rather than applied labels — the MCP's job is done. That's a 2-3 cycle horizon, not a permanent infrastructure commitment. Scope accordingly.
