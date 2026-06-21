# cerebra-classic

Archival fork of [Cerebra](https://github.com/bitmosh/cerebra) at the
pre-dyson-sphere baseline state.

**Tagged commit:** `v0.4.4-pre-dyson` (2026-06-21)

## What this repository is

This is a frozen snapshot of Cerebra immediately after the fossic v1.6.0
substrate release and immediately before the dyson sphere migration begins.
The migration absorbs portions of Cerebra's persistence layer into a
Rust-backed substrate, transforming the architecture in measurable ways.

This fork exists so the *before* state remains:

- **Inspectable** — every architectural decision, every line of code, every
  schema migration is preserved as it was on 2026-06-21
- **Runnable** — the system can be cloned, set up, and executed at this
  exact state for empirical comparison with the post-state
- **Citable** — academic and technical references can point to a specific
  commit rather than a moving target

## What this repository is not

- Not the current Cerebra. Active development continues at the main
  [Cerebra repository](https://github.com/bitmosh/cerebra).
- Not feature-frozen by accident. New work does not land here. This fork
  is maintained in archive mode only.
- Not a deprecated version. It represents a deliberate architectural
  baseline, not a superseded release.

## Maintenance policy

This fork accepts:

- Critical security patches that affect the runnable baseline (so the
  archive remains usable)
- Documentation corrections that improve accuracy of the snapshot
- Dependency version pin updates if a pinned dependency becomes
  permanently unavailable

This fork rejects:

- New features
- Architectural changes
- Performance improvements (those go in the live Cerebra and become part
  of the post-state comparison)
- Cosmetic refactors

## How to use this fork

**For comparison reading:**
See `CEREBRA_PRE_DYSON_SNAPSHOT.md` (forthcoming) for the architectural
narrative that explains what this state represents.

**For comparison running:**
Clone this repository, follow the original Cerebra setup instructions
(preserved in `README_CEREBRA_ORIGINAL.md`), and run against a sample
vault. The same vault should run on both this fork and the live Cerebra
for direct empirical comparison.

**For academic citation:**
Cite the tagged commit:
> Cerebra (pre-dyson-sphere baseline). Tag v0.4.4-pre-dyson.
> https://github.com/bitmosh/cerebra-classic

## Related resources

- **[fossic v1.6.0](https://github.com/bitmosh/fossic)** — the
  substrate that the dyson sphere transformation builds on. Phase 1
  shipped 2026-06-21.
- **[Cerebra](https://github.com/bitmosh/cerebra)** — live development,
  post-fossic-integration evolution
- **CEREBRA_PRE_DYSON_SNAPSHOT.md** (forthcoming) — narrative architecture
  document explaining what this fork represents
- **CEREBRA_POST_DYSON_SNAPSHOT.md** (forthcoming, Q4 2026) — the
  corresponding post-transformation state, with measured deltas
- **Aseptic methodology paper** (forthcoming) — companion document
  describing the multi-Claude development methodology that produced this
  transformation

## License

Same license as the original Cerebra repository. See `LICENSE` for terms.

---

*Repository established 2026-06-21 immediately following the fossic v1.6.0
publication. Maintained by boop ([@bitmosh](https://github.com/bitmosh)).*
