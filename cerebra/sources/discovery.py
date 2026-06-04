"""
File discovery — recursive directory walk with exclusion patterns and
canonical path resolution.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "archive/",
    ".git/",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "dist/",
    "build/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytest_cache/",
]

DEFAULT_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt", ".rst"})


def canonical_path(p: Path) -> Path:
    """Resolve symlinks and normalize to absolute path."""
    return p.resolve()


def _is_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """Return True if any component of path (relative to root) matches a pattern."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = rel.parts
    for pattern in patterns:
        # Strip trailing slash for matching against directory components
        pat = pattern.rstrip("/")
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


def discover_files(
    root: Path,
    extensions: frozenset[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """
    Recursively discover files under root.

    Args:
        root: directory to walk (resolved before use)
        extensions: file extensions to include (with dot, e.g. {".md", ".txt"}).
                    None means use DEFAULT_EXTENSIONS.
        exclude_patterns: directory/file name patterns to skip.
                          None means use DEFAULT_EXCLUDE_PATTERNS.

    Returns:
        List of canonical (resolved) paths, sorted for stable ordering.
        Symlinks are followed; canonical paths deduplicate files that appear
        under multiple symlinks.
    """
    exts = extensions if extensions is not None else DEFAULT_EXTENSIONS
    patterns = exclude_patterns if exclude_patterns is not None else DEFAULT_EXCLUDE_PATTERNS
    root_canon = canonical_path(root)

    seen: set[Path] = set()
    result: list[Path] = []

    for path in root_canon.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path, root_canon, patterns):
            continue
        if exts and path.suffix.lower() not in exts:
            continue
        canon = canonical_path(path)
        if canon in seen:
            continue  # deduplicate symlinks pointing to same real file
        seen.add(canon)
        result.append(canon)

    return sorted(result)
