# Security Policy

## Supported versions

This repository is the `v0.4.4-pre-dyson` archival snapshot of Cerebra. Only
the tagged commit `v0.4.4-pre-dyson` is supported; security patches will be
applied on top of that tag if they affect the runnable baseline. Active
development continues at [bitmosh/cerebra](https://github.com/bitmosh/cerebra),
which is the appropriate place to report issues affecting current versions.

| Version          | Supported |
| ---------------- | --------- |
| v0.4.4-pre-dyson | Yes       |
| Earlier tags     | No        |

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:

1. Use GitHub's [private vulnerability reporting](https://github.com/bitmosh/cerebra-classic/security/advisories/new)
   on this repository.
2. Or contact the maintainer directly via GitHub
   ([@bitmosh](https://github.com/bitmosh)).

Expect a response within seven days. Because this is an archival fork, fixes
will be released as patches on top of the `v0.4.4-pre-dyson` tag rather than
as a new minor version.

## Scope

Reports are in scope if they affect Cerebra at its archive state. Examples:

- Vulnerabilities in pinned dependencies that the archive depends on
- Vulnerabilities in vendored code (e.g. `vendor/fossic-*.whl`)
- Privilege-escalation or data-exfiltration issues in the runtime itself

Out of scope:

- Issues fixed in later Cerebra versions (report at the
  [main Cerebra repository](https://github.com/bitmosh/cerebra))
- Issues only reproducible in non-archival forks or modifications
