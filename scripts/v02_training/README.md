# v0.2 LoRA Training — Benched

This work is benched as of 2026-06-09.

See `docs/agent/deferred/v02_lora_track.md` for the full record: what was built, what was learned, resume conditions, and the resume plan.

**Short version:** Phase 2 training confirmed 0 parse failures and 46.7% strict accuracy. Pass-2 D1 works well (82.4% given correct quadrant). Pass-1 quadrant routing is the bottleneck (56.7%), blocked by RELATIONAL corpus underrepresentation (10/214 records, 0 AGENT, 0 EVENT examples). Resume when corpus ≥1000 records or a specific downstream capability requires the accuracy lift.

The production classifier is Granite 4.1 3B instruct via Ollama, calibrated at 65% partial-credit on 30 fixtures.
