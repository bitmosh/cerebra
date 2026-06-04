"""
File type detection — combines extension, content sniffing, and
MIME heuristics into a confidence-bearing DetectionResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".mdown", ".mkd"})
TEXT_EXTENSIONS: frozenset[str] = frozenset({".txt", ".rst", ".text"})
SUPPORTED_TYPES: frozenset[str] = frozenset({"markdown", "text"})

# Bytes to read for content sniffing
SNIFF_BYTES = 512


@dataclass
class DetectionResult:
    detected_type: str  # "markdown" | "text" | "unknown"
    confidence: float  # 0.0–1.0
    signals: dict[str, str] = field(default_factory=dict)


def detect_type(path: Path, content_sample: bytes | None = None) -> DetectionResult:
    """
    Detect file type using extension + content sniffing.

    Args:
        path: file path (used for extension signal)
        content_sample: first N bytes of file content; read from path if None

    Returns:
        DetectionResult with type, confidence, and signals dict.
    """
    signals: dict[str, str] = {}
    ext = path.suffix.lower()
    signals["extension"] = ext

    if content_sample is None:
        try:
            with path.open("rb") as f:
                content_sample = f.read(SNIFF_BYTES)
        except OSError:
            return DetectionResult("unknown", 0.0, signals)

    # Binary check — if high ratio of non-printable bytes, it's not text
    if _is_binary(content_sample):
        signals["binary"] = "true"
        return DetectionResult("unknown", 0.9, signals)

    text_sample = content_sample.decode("utf-8", errors="replace")

    # Extension-based detection
    if ext in MARKDOWN_EXTENSIONS:
        signals["extension_match"] = "markdown"
        sniff = _sniff_markdown(text_sample)
        signals["content_sniff"] = sniff
        confidence = 0.95 if sniff == "markdown_headings" else 0.80
        return DetectionResult("markdown", confidence, signals)

    if ext in TEXT_EXTENSIONS:
        signals["extension_match"] = "text"
        return DetectionResult("text", 0.85, signals)

    # Extension unknown — fall back to content sniff
    sniff = _sniff_markdown(text_sample)
    signals["content_sniff"] = sniff
    if sniff == "markdown_headings":
        return DetectionResult("markdown", 0.65, signals)

    # Plain text fallback for any readable file
    return DetectionResult("text", 0.40, signals)


def _is_binary(sample: bytes) -> bool:
    """Heuristic: presence of null bytes or >15% low-control / high bytes → binary."""
    if not sample:
        return False
    # Null byte is a reliable binary indicator
    if b"\x00" in sample:
        return True
    # Count bytes that can't appear in normal UTF-8 text
    non_text = sum(1 for b in sample if (b < 9) or (14 <= b <= 31) or (b == 127) or (b >= 128))
    return (non_text / len(sample)) > 0.15


def _sniff_markdown(text: str) -> str:
    """Return 'markdown_headings' if text contains ATX heading markers."""
    for line in text.splitlines()[:20]:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            return "markdown_headings"
    return "plain_text"
