# vendor/

Pre-built dependencies that ship with the archive. Each file here exists for
a specific reason; this doc explains why and how to rebuild if needed.

## fossic-1.8.1-cp312-cp312-manylinux_2_34_x86_64.whl

### Why it's vendored

`fossic` is a Rust/PyO3 extension that backs Cerebra's content-addressed
event store. It is developed in a private repository
([`bitmosh/fossic`](https://github.com/bitmosh/fossic)) and has no PyPI
release.

Earlier iterations of `pyproject.toml` referenced fossic in two ways, both
broken for distribution:

- `"fossic @ file:///home/boop/Projects/fossic/fossic-py"` — absolute path on
  one specific developer's machine. CI runs and clones on any other machine
  failed at install.
- `"fossic @ git+https://github.com/bitmosh/fossic.git#subdirectory=fossic-py"`
  — git URL pointing at a private repo. `GITHUB_TOKEN` in workflows is scoped
  to the host repo only and cannot read sibling private repos, so CI failed
  with "Repository not found."

Vendoring a pre-built wheel solves both: no network, no credentials, no
Rust toolchain needed on installation. Appropriate for an archive repo
where the goal is reproducible install in perpetuity.

### What this wheel is

- **Upstream:** `bitmosh/fossic`, tag `v1.8.1`
- **Build profile:** release
- **Target platform:** CPython 3.12 on Linux x86_64 with `glibc >= 2.34`
- **Size:** ~3.4 MB

The wheel ships only `cp312` for Linux x86_64. If you're on macOS, Windows,
older Linux, or a different Python version, the wheel won't match and you'll
need to build fossic from source (see below).

### How to rebuild

If the wheel ever needs updating (security patch in upstream fossic, new
target platform, etc.), the rebuild flow is:

```bash
# 1. Clone upstream
git clone https://github.com/bitmosh/fossic.git /tmp/fossic
cd /tmp/fossic

# 2. Check out the desired tag
git checkout v1.8.1   # or whatever target version

# 3. Build a release wheel
cd fossic-py
maturin build --release

# 4. Copy the resulting wheel back here
cp target/wheels/fossic-*.whl /path/to/cerebra-classic/vendor/

# 5. Update pyproject.toml's `fossic @ file:vendor/...` to match the new filename
# 6. Delete the old wheel
```

Note: `maturin` is fossic's chosen build backend; the upstream README in
`bitmosh/fossic` has the canonical build instructions.

### Building fossic from source on an unsupported platform

If the vendored wheel doesn't fit your platform and you have access to the
upstream `bitmosh/fossic` repository, you can install from source:

```bash
# 1. Edit pyproject.toml: replace the `fossic @ file:vendor/...` line with:
#    "fossic @ git+ssh://git@github.com/bitmosh/fossic.git#subdirectory=fossic-py",
# 2. Install Rust via rustup.rs
# 3. Run: pip install -e ".[dev]"
```

(SSH avoids the GITHUB_TOKEN limitation but requires your SSH key to have
access to the private repo. This is local-dev only — don't commit this
change.)
