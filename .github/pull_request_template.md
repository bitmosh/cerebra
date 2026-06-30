<!--
Reminder: this fork is archival. Acceptable PR categories per the maintenance
policy in README.md:
  - Critical security patches affecting the runnable baseline
  - Documentation corrections that improve snapshot accuracy
  - Dependency pin updates if a pinned dep becomes unavailable
Anything else (features, refactors, perf, cosmetic) should go to bitmosh/cerebra.
-->

## Summary

<!-- 1-3 sentences. What does this change and why? -->

## Category

<!-- Pick one. Reject the PR if none fit. -->

- [ ] Security patch
- [ ] Documentation correction
- [ ] Dependency pin update

## Test plan

<!-- How you verified the change works. -->

- [ ] `make test-quick` passes locally
- [ ] `ruff check cerebra tests` clean
- [ ] `black --check cerebra tests` clean
- [ ] `mypy cerebra` clean
- [ ] Manual verification (describe):

## Related

<!-- Link issues, prior PRs, upstream advisories. -->
