#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
verify_docs.py — archive-aware check that every reference in CEREBRA_DOC_INDEX.md
exists somewhere in docs/.

Archive-aware: files in docs/*/archive/ directories count as present.

Exit 0 if all references are found.
Exit 1 if any references are missing, listing the missing files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
INDEX_FILE = DOCS_DIR / "refined-runtime-model" / "CEREBRA_DOC_INDEX.md"

# Regex: match any CEREBRA_*.md or LATTICA_*.md filename in the index
DOC_REF_RE = re.compile(r"\b((?:CEREBRA|LATTICA)_[A-Z0-9_]+\.md)\b")


def find_all_doc_files() -> set[str]:
    """Collect basenames of all .md files anywhere under docs/."""
    return {p.name for p in DOCS_DIR.rglob("*.md")}


def extract_references(index_path: Path) -> set[str]:
    """Extract all doc filenames referenced in the index."""
    content = index_path.read_text(encoding="utf-8")
    return set(DOC_REF_RE.findall(content))


def main() -> int:
    if not INDEX_FILE.exists():
        print(f"ERROR: index file not found: {INDEX_FILE}")
        return 1

    on_disk = find_all_doc_files()
    referenced = extract_references(INDEX_FILE)

    missing = sorted(referenced - on_disk)
    present = sorted(referenced & on_disk)

    print(f"verify-docs: {len(present)} referenced docs found on disk")

    if missing:
        print(f"\nMISSING ({len(missing)} files):")
        for f in missing:
            print(f"  - {f}")
        return 1

    print("All referenced docs are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
