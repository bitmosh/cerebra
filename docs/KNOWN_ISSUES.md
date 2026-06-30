# Known Issues

Tracked defects in the archived `v0.4.4-pre-dyson` baseline. Each entry links
to a GitHub issue with full reproduction and discussion. Entries here are
acknowledged limitations of the archive, not bugs awaiting triage.

Per the maintenance policy in [README.md](../README.md), these will be left
in place rather than fixed in this fork. Fixes — when they happen — land in
active development at [bitmosh/cerebra](https://github.com/bitmosh/cerebra).

## Open

### [#2](https://github.com/bitmosh/cerebra-classic/issues/2) — `dedup_siblings` SKU-match routing is dead code

**Where:** `cerebra/retrieval/lattice_dedup.py` (function `_pick_winner_scored`)

**What:** The comparison `c.sku_address.split("::")[0] == query_d1` is dead
code. `sku_address` is `.`-separated per `SKUAddress.to_hex_string()`, not
`::`-separated, so `split("::")` returns the whole address as a single element.
Even after the type annotation was corrected to `int | None` (matching the
caller), the comparison cannot match.

**Effect:** `_pick_winner_scored` always falls through to composite-score
routing instead of preferring SKU-match candidates. The function still
returns a valid winner; the SKU-aware routing path has just never fired.

**Surfaced when:** mypy was run against the whole tree for the first time
during CI cleanup (mypy hadn't been validated whole-tree previously because
pre-commit only checks staged files).

**Why not fixed here:** Fixing the logic requires deciding on the intended
key format (D1 hex char only, or the full D1–D6 location?) and adding a
unit test that exercises the SKU-match path. That's design work, not a
patch. See the issue for proposed approaches.

## Closed

None yet.
