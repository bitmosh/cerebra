"""
Stage 3 Review TUI — manual curation for v0.2 LoRA training corpus.

Single-screen TUI, per-record writes, zero work lost on crash or quit.

Usage:
    cd ~/Projects/cerebra
    python scripts/v02_training/stage3_review.py
    python scripts/v02_training/stage3_review.py --calibration

Requires: pip install textual
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.markup import escape as _esc
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

# ── Paths ─────────────────────────────────────────────────────────────────────

_DIR = Path(__file__).parent
INPUT_PATH = _DIR / "output/stage2_consensus.jsonl"
OUTPUT_PATH = _DIR / "output/stage3_curated.jsonl"
CAL_OUTPUT_PATH = _DIR / "output/stage3_calibration.jsonl"
CAL_COUNT = 20

# ── Config ────────────────────────────────────────────────────────────────────

MODEL_DISPLAY = {
    "qwen35-9b":      "Qwen 3.5 9B",
    "llama31-8b":     "Llama 3.1 8B",
    "granite4-micro": "Granite 4.0 Micro",
}

ALL_CATEGORIES = [
    "DESIGN",      "MECHANISM",  "TECHNIQUE", "TOOL",
    "PRINCIPLE",   "CONSTRAINT", "JUDGMENT",  "GOAL",
    "OBSERVATION", "PHENOMENON", "PATTERN",   "EVENT",
    "RELATION",    "CONTEXT",    "CREATION",  "AGENT",
]

# Two-letter hotkeys shown in the full 16-category picker (Phase 2 flow)
CATEGORY_HOTKEYS: dict[str, str] = {
    "D1": "DESIGN",      "M1": "MECHANISM",  "T1": "TECHNIQUE", "T2": "TOOL",
    "P1": "PRINCIPLE",   "C1": "CONSTRAINT", "J1": "JUDGMENT",  "G1": "GOAL",
    "O1": "OBSERVATION", "P2": "PHENOMENON", "P3": "PATTERN",   "E1": "EVENT",
    "R1": "RELATION",    "C2": "CONTEXT",    "C3": "CREATION",  "A1": "AGENT",
}
HOTKEY_BY_CAT = {v: k for k, v in CATEGORY_HOTKEYS.items()}

CHUNK_MAX = 520  # chars shown in chunk panel before truncation

# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_records(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _load_curated(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    curated: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            curated[e["record_id"]] = e  # last entry wins (handles duplicates)
        except (json.JSONDecodeError, KeyError):
            pass
    return curated


def _append_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _rewrite_curated(path: Path, curated: dict[str, dict]) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w") as fh:
        for e in curated.values():
            fh.write(json.dumps(e) + "\n")
    tmp.replace(path)


# ── Rendering ─────────────────────────────────────────────────────────────────

def _conf_color(conf: float) -> str:
    if conf >= 0.8:
        return "green"
    if conf >= 0.6:
        return "yellow"
    return "red"


def _vote_markup(vote: str | None, label: str) -> str:
    if vote is None:
        return "[dim]—[/dim]"
    safe = _esc(vote)
    if vote == label:
        return f"[bold green]{safe}[/bold green]"
    return f"[yellow]{safe}[/yellow]"


def _render_header(s: "ReviewSession") -> str:
    pos = s.position + 1
    total_f = len(s.filtered)
    avg = s.avg_time_per_record
    avg_s = f"{avg:.0f}s" if avg else "—"
    return (
        f"[bold]Stage 3 Review[/bold]  ·  "
        f"Record [cyan]{pos}/{total_f}[/cyan]  ·  "
        f"Session: [cyan]{s.session_count}[/cyan] reviewed  ·  "
        f"Overall: [cyan]{s.total_reviewed}/{s.total_records}[/cyan] "
        f"([cyan]{s.overall_pct:.1f}%[/cyan])\n"
        f"[dim]Filter:[/dim] [yellow]{s.filter_name}[/yellow]  "
        f"[dim]Sort:[/dim] [yellow]{s.sort_name}[/yellow]  "
        f"[dim]Avg:[/dim] [yellow]{avg_s}/record[/yellow]"
    )


def _render_chunk(record: dict) -> str:
    text = _esc(record["content"])
    if len(text) > CHUNK_MAX:
        text = text[:CHUNK_MAX] + "[dim] …[/dim]"
    return f"[bold dim]Chunk content:[/bold dim]\n\n{text}"


def _render_context(record: dict, curated: dict) -> str:
    label = record["d1_name"]
    conf = record["d1_confidence"]
    col = _conf_color(conf)
    votes: dict[str, str | None] = record["stage2_votes"]
    consensus = record["stage2_consensus"]

    label_line = (
        f"[bold]v0.1.0 label:[/bold]  [bold white]{_esc(label)}[/bold white]"
        f"  [dim](confidence: [{col}]{conf:.2f}[/{col}])[/dim]"
    )

    vote_lines: list[str] = []
    for i, (key, vote_val) in enumerate(votes.items()):
        display = MODEL_DISPLAY.get(key, key)
        vote_lines.append(
            f"  \\[{i + 1}] {_esc(display):<20s} → {_vote_markup(vote_val, label)}"
        )

    agree = sum(1 for v in votes.values() if v == label)
    total_v = len([v for v in votes.values() if v is not None])
    if consensus == "consensus":
        cons_markup = f"[green]consensus[/green] ({agree}/{total_v} agree with v0.1.0)"
    else:
        cons_markup = f"[yellow]contested[/yellow] ({agree}/{total_v} agree with v0.1.0)"

    existing = curated.get(record["record_id"])
    if existing:
        v = existing["verdict"]
        fl = existing["final_label"] or "null"
        vcolor = {"KEEP": "green", "RELABEL": "cyan", "MARK_AMBIGUOUS": "yellow", "DROP": "red"}.get(v, "white")
        notes_hint = "  [dim](has notes)[/dim]" if existing.get("notes") else ""
        verdict_line = f"[bold]Verdict:[/bold]  [{vcolor}]{_esc(v)}[/{vcolor}] → {_esc(fl)}{notes_hint}"
    else:
        verdict_line = "[dim]Verdict: unreviewed[/dim]"

    return (
        f"{label_line}\n\n"
        f"[bold]Stage 2 votes:[/bold]\n"
        + "\n".join(vote_lines) + "\n\n"
        f"[bold]Consensus:[/bold]  {cons_markup}\n\n"
        f"{verdict_line}"
    )


def _render_controls(phase2: bool = False) -> str:
    k = "[bold green]\\[K][/bold green]eep"
    r = "[bold cyan]\\[R][/bold cyan]elabel"
    a = "[bold yellow]\\[A][/bold yellow]mbiguous"
    d = "[bold red]\\[D][/bold red]rop"
    if phase2:
        nav = "[dim]\\[←] Prev  \\[→/Space] Next  \\[J]ump  \\[F]ilter  \\[S]ort  \\[N]otes  \\[Q]uit[/dim]"
    else:
        nav = "[dim]\\[←] Prev  \\[→/Space] Next  \\[Q]uit[/dim]  [dim italic](R/A/N/F/S/J in next pass)[/dim]"
    return f"[bold]Verdict:[/bold]  {k}  {r}  {a}  {d}\n[bold]Navigate:[/bold]  {nav}"


# ── Session state ─────────────────────────────────────────────────────────────

class ReviewSession:
    """All mutable review state and file I/O. No Textual dependency."""

    def __init__(
        self,
        records: list[dict],
        curated: dict[str, dict],
        output_path: Path,
        calibration: bool = False,
    ) -> None:
        self.all_records = records
        self.curated = curated
        self.output_path = output_path
        self.calibration = calibration

        self.filter_mode = "all"
        self.filter_category: str | None = None
        self.filter_conf_range: tuple[float, float] | None = None
        self.sort_mode = "original"

        self.filtered: list[dict] = []
        self.position = 0
        self._rebuild_filtered()

        # On resume, skip to first unreviewed record
        if curated:
            self.position = self._first_unreviewed_index()

        self.session_start = time.monotonic()
        self.record_start = time.monotonic()
        self.session_verdicts: list[tuple[str, float]] = []
        self.notes_buffer = ""

    # ── Filter / sort ──────────────────────────────────────────────────────────

    def _rebuild_filtered(self) -> None:
        records = list(self.all_records)
        fm = self.filter_mode

        if self.calibration:
            records = records[:CAL_COUNT]
        elif fm == "consensus":
            records = [r for r in records if r["stage2_consensus"] == "consensus"]
        elif fm == "contested":
            records = [r for r in records if r["stage2_consensus"] == "contested"]
        elif fm == "unreviewed":
            records = [r for r in records if r["record_id"] not in self.curated]
        elif fm == "category" and self.filter_category:
            records = [r for r in records if r["d1_name"] == self.filter_category]
        elif fm == "conf_range" and self.filter_conf_range:
            lo, hi = self.filter_conf_range
            records = [r for r in records if lo <= r["d1_confidence"] <= hi]
        elif fm == "unanimous_against":
            def _all_against(r: dict) -> bool:
                lbl = r["d1_name"]
                return all(v != lbl for v in r["stage2_votes"].values() if v)
            records = [r for r in records if _all_against(r)]

        if self.sort_mode == "conf_asc":
            records.sort(key=lambda r: r["d1_confidence"])
        elif self.sort_mode == "conf_desc":
            records.sort(key=lambda r: r["d1_confidence"], reverse=True)
        elif self.sort_mode == "category":
            records.sort(key=lambda r: r["d1_name"])

        self.filtered = records
        self.position = min(self.position, max(0, len(self.filtered) - 1))

    def _first_unreviewed_index(self) -> int:
        for i, r in enumerate(self.filtered):
            if r["record_id"] not in self.curated:
                return i
        return 0

    def apply_filter(self, mode: str, **kwargs: object) -> None:
        self.filter_mode = mode
        self.filter_category = kwargs.get("category")  # type: ignore[assignment]
        self.filter_conf_range = kwargs.get("conf_range")  # type: ignore[assignment]
        self._rebuild_filtered()
        self.position = self._first_unreviewed_index()

    def apply_sort(self, mode: str) -> None:
        self.sort_mode = mode
        self._rebuild_filtered()

    # ── Navigation ─────────────────────────────────────────────────────────────

    def current_record(self) -> dict | None:
        return self.filtered[self.position] if self.filtered else None

    def advance(self) -> bool:
        if self.position < len(self.filtered) - 1:
            self.position += 1
            self.record_start = time.monotonic()
            self.notes_buffer = ""
            return True
        return False

    def go_back(self) -> bool:
        if self.position > 0:
            self.position -= 1
            self.record_start = time.monotonic()
            self.notes_buffer = ""
            return True
        return False

    def jump_to_id(self, record_id: str) -> bool:
        for i, r in enumerate(self.filtered):
            if r["record_id"] == record_id:
                self.position = i
                self.record_start = time.monotonic()
                self.notes_buffer = ""
                return True
        return False

    # ── Verdict recording ──────────────────────────────────────────────────────

    def record_verdict(
        self,
        record: dict,
        verdict: str,
        final_label: str | None,
        ambiguous_with: list[str] | None = None,
    ) -> None:
        entry = {
            "record_id": record["record_id"],
            "verdict": verdict,
            "final_label": final_label,
            "ambiguous_with": ambiguous_with,
            "notes": self.notes_buffer,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "v01_label_was": record["d1_name"],
            "stage2_votes_were": record["stage2_votes"],
        }
        # Write first — if it raises, in-memory state stays consistent
        _append_entry(self.output_path, entry)
        elapsed = time.monotonic() - self.record_start
        self.curated[record["record_id"]] = entry
        self.session_verdicts.append((verdict, elapsed))
        self.notes_buffer = ""
        self.advance()

    def update_notes(self, record_id: str, notes: str) -> None:
        if record_id in self.curated:
            self.curated[record_id]["notes"] = notes
            _rewrite_curated(self.output_path, self.curated)

    # ── Stats ──────────────────────────────────────────────────────────────────

    @property
    def total_records(self) -> int:
        return len(self.all_records)

    @property
    def total_reviewed(self) -> int:
        return len(self.curated)

    @property
    def session_count(self) -> int:
        return len(self.session_verdicts)

    @property
    def avg_time_per_record(self) -> float:
        if not self.session_verdicts:
            return 0.0
        return sum(t for _, t in self.session_verdicts) / len(self.session_verdicts)

    @property
    def session_duration(self) -> float:
        return time.monotonic() - self.session_start

    @property
    def overall_pct(self) -> float:
        return (self.total_reviewed / self.total_records * 100) if self.total_records else 0.0

    @property
    def filter_name(self) -> str:
        names: dict[str, str] = {
            "all": "all",
            "consensus": "consensus",
            "contested": "contested",
            "unreviewed": "unreviewed",
            "category": f"cat:{self.filter_category}",
            "conf_range": (
                f"conf {self.filter_conf_range[0]:.1f}-{self.filter_conf_range[1]:.1f}"
                if self.filter_conf_range else "conf"
            ),
            "unanimous_against": "vs-all",
        }
        return names.get(self.filter_mode, self.filter_mode)

    @property
    def sort_name(self) -> str:
        return {
            "original": "original",
            "conf_asc": "conf↑",
            "conf_desc": "conf↓",
            "category": "category",
        }.get(self.sort_mode, self.sort_mode)

    def session_summary(self) -> str:
        dur = self.session_duration
        mins, secs = int(dur // 60), int(dur % 60)
        avg = self.avg_time_per_record
        counts: dict[str, int] = {}
        for v, _ in self.session_verdicts:
            counts[v] = counts.get(v, 0) + 1
        n = self.session_count
        remaining = self.total_records - self.total_reviewed
        with_notes = sum(1 for e in self.curated.values() if e.get("notes"))

        lines = [
            "",
            "Session summary:",
            f"  Records reviewed:  {n}",
            f"  Time elapsed:      {mins}m {secs:02d}s",
            f"  Average per record: {avg:.1f}s",
            "",
            "  Verdict breakdown:",
        ]
        for verdict in ("KEEP", "RELABEL", "MARK_AMBIGUOUS", "DROP"):
            cnt = counts.get(verdict, 0)
            pct = (cnt / n * 100) if n else 0
            lines.append(f"    {verdict:<16s}: {cnt:3d}  ({pct:.0f}%)")
        lines += [
            "",
            f"  Records with notes: {with_notes}",
            "",
            f"  Total progress: {self.total_reviewed}/{self.total_records} "
            f"({self.overall_pct:.1f}%) — {remaining} remaining",
            "",
        ]
        return "\n".join(lines)


# ── Modal screens ─────────────────────────────────────────────────────────────

class JumpScreen(ModalScreen[str | None]):
    """Jump to a record by ID."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Label("Jump to record ID (ESC to cancel):", id="jump-label")
        yield Input(placeholder="record_id", id="jump-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    JumpScreen {
        align: center middle;
    }
    JumpScreen > Label {
        width: 50;
        padding: 1;
    }
    JumpScreen > Input {
        width: 50;
    }
    """


class NotesScreen(ModalScreen[str | None]):
    """Capture or edit notes for the current record."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, existing: str = "") -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        yield Label("Notes (Enter to save, ESC to cancel):", id="notes-label")
        yield Input(value=self._existing, placeholder="optional observation…", id="notes-input")

    def on_mount(self) -> None:
        self.query_one("#notes-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    NotesScreen {
        align: center middle;
    }
    NotesScreen > Label {
        width: 60;
        padding: 1;
    }
    NotesScreen > Input {
        width: 60;
    }
    """


class RelabelScreen(ModalScreen[str | None]):
    """Pick the relabel target from vote shortcuts or full picker."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._record = record
        # Unique vote options (deduplicated, ordered)
        votes = record["stage2_votes"]
        seen: set[str] = set()
        self._options: list[tuple[str, str, str]] = []  # (key, display_name, category)
        for i, (mkey, cat) in enumerate(votes.items()):
            if cat and cat not in seen:
                seen.add(cat)
                label = record["d1_name"]
                note = " ← same as v0.1.0" if cat == label else ""
                self._options.append((str(i + 1), MODEL_DISPLAY.get(mkey, mkey), cat + note))

    def compose(self) -> ComposeResult:
        lines = ["[bold]Relabel to:[/bold]\n"]
        for key, model, cat in self._options:
            lines.append(f"  \\[[bold]{key}[/bold]] {cat}  [dim]({model})[/dim]")
        lines.append("  \\[[bold]O[/bold]] Other → full 16-category picker")
        lines.append("  \\[[bold]ESC[/bold]] Cancel")
        yield Static("\n".join(lines), id="relabel-body")

    def on_key(self, event) -> None:
        key = event.key.lower()
        for opt_key, _, cat in self._options:
            # Strip notes suffix before returning
            cat_clean = cat.split(" ←")[0].strip()
            if key == opt_key:
                self.dismiss(cat_clean)
                return
        if key == "o":
            self.app.push_screen(CategoryPickerScreen(), self._on_picker)

    def _on_picker(self, result: str | None) -> None:
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    RelabelScreen {
        align: center middle;
    }
    RelabelScreen > Static {
        width: 60;
        border: round $primary;
        padding: 1 2;
    }
    """


class CategoryPickerScreen(ModalScreen[str | None]):
    """Full 16-category picker with two-letter hotkeys."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        rows = [
            ("D1", "DESIGN"),      ("M1", "MECHANISM"),  ("T1", "TECHNIQUE"), ("T2", "TOOL"),
            ("P1", "PRINCIPLE"),   ("C1", "CONSTRAINT"),  ("J1", "JUDGMENT"),  ("G1", "GOAL"),
            ("O1", "OBSERVATION"), ("P2", "PHENOMENON"),  ("P3", "PATTERN"),   ("E1", "EVENT"),
            ("R1", "RELATION"),    ("C2", "CONTEXT"),     ("C3", "CREATION"),  ("A1", "AGENT"),
        ]
        # Build 4-column display
        lines = ["[bold]Pick category (two-letter hotkey or ESC):[/bold]\n"]
        for i in range(0, len(rows), 4):
            chunk = rows[i:i + 4]
            cols = [f"[bold]{hk}[/bold]: {cat:<12s}" for hk, cat in chunk]
            lines.append("  " + "  ".join(cols))
        lines.append("\n  \\[[bold]ESC[/bold]] Cancel")
        yield Static("\n".join(lines), id="picker-body")
        yield Input(placeholder="type hotkey (e.g. D1, M1)", id="picker-input", max_length=2)

    def on_mount(self) -> None:
        self.query_one("#picker-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        val = event.value.upper()
        if val in CATEGORY_HOTKEYS:
            self.dismiss(CATEGORY_HOTKEYS[val])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.upper()
        if val in CATEGORY_HOTKEYS:
            self.dismiss(CATEGORY_HOTKEYS[val])
        # else stay open for correction

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    CategoryPickerScreen {
        align: center middle;
    }
    CategoryPickerScreen > Static {
        width: 70;
        border: round $primary;
        padding: 1 2;
    }
    CategoryPickerScreen > Input {
        width: 30;
        margin: 0 20;
    }
    """


class AmbiguousScreen(ModalScreen[tuple[str, list[str]] | None]):
    """Two-step ambiguous flow: confirm primary, then pick alternatives."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._record = record
        self._primary: str = record["d1_name"]
        self._selected: set[str] = set()
        self._step = 1  # 1 = confirm primary, 2 = pick alternatives

    def compose(self) -> ComposeResult:
        yield Static(id="ambig-body")

    def on_mount(self) -> None:
        self._render_step()

    def _render_step(self) -> None:
        body = self.query_one("#ambig-body", Static)
        if self._step == 1:
            body.update(
                f"[bold]Primary label:[/bold]\n\n"
                f"  \\[[bold]Enter[/bold]] Keep [bold white]{self._primary}[/bold white] as primary\n"
                f"  \\[[bold]C[/bold]] Change primary → category picker\n"
                f"  \\[[bold]ESC[/bold]] Cancel"
            )
        else:
            votes = self._record["stage2_votes"]
            unique_cats = list(dict.fromkeys(v for v in votes.values() if v))
            lines = [
                f"[bold]Primary: {self._primary}[/bold]\n",
                "[bold]Also defensible[/bold] (toggle, [bold]Enter[/bold] when done):\n",
            ]
            for i, (mkey, cat) in enumerate(votes.items()):
                if not cat:
                    continue
                chk = "[bold green]✓[/bold green]" if cat in self._selected else " "
                display = MODEL_DISPLAY.get(mkey, mkey)
                lines.append(f"  \\[[bold]{i + 1}[/bold]] [{chk}] {cat}  [dim]({display})[/dim]")
            lines.append("  \\[[bold]O[/bold]] Other → category picker")
            lines.append("  \\[[bold]Enter[/bold]] Done   \\[[bold]ESC[/bold]] Cancel")
            body.update("\n".join(lines))

    def on_key(self, event) -> None:
        key = event.key.lower()
        if self._step == 1:
            if key == "enter":
                self._step = 2
                self._render_step()
            elif key == "c":
                self.app.push_screen(CategoryPickerScreen(), self._set_primary)
        else:
            votes = self._record["stage2_votes"]
            items = list(votes.items())
            for i, (_, cat) in enumerate(items):
                if cat and key == str(i + 1):
                    if cat in self._selected:
                        self._selected.discard(cat)
                    else:
                        self._selected.add(cat)
                    self._render_step()
                    return
            if key == "o":
                self.app.push_screen(CategoryPickerScreen(), self._add_from_picker)
            elif key == "enter":
                self.dismiss((self._primary, sorted(self._selected)))

    def _set_primary(self, cat: str | None) -> None:
        if cat:
            self._primary = cat
        self._step = 2
        self._render_step()

    def _add_from_picker(self, cat: str | None) -> None:
        if cat:
            self._selected.add(cat)
        self._render_step()

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    AmbiguousScreen {
        align: center middle;
    }
    AmbiguousScreen > Static {
        width: 60;
        border: round $primary;
        padding: 1 2;
    }
    """


class FilterScreen(ModalScreen[dict | None]):
    """Filter mode picker."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Filter mode:[/bold]\n\n"
            "  \\[[bold]1[/bold]] All records\n"
            "  \\[[bold]2[/bold]] Consensus only (~205 records)\n"
            "  \\[[bold]3[/bold]] Contested only (~378 records)\n"
            "  \\[[bold]4[/bold]] By D1 category\n"
            "  \\[[bold]5[/bold]] By confidence range\n"
            "  \\[[bold]6[/bold]] Unanimous against v0.1.0\n"
            "  \\[[bold]7[/bold]] Unreviewed only\n"
            "  \\[[bold]ESC[/bold]] Cancel",
            id="filter-body",
        )

    def on_key(self, event) -> None:
        mapping = {
            "1": {"mode": "all"},
            "2": {"mode": "consensus"},
            "3": {"mode": "contested"},
            "6": {"mode": "unanimous_against"},
            "7": {"mode": "unreviewed"},
        }
        key = event.key
        if key in mapping:
            self.dismiss(mapping[key])
        elif key == "4":
            self.app.push_screen(CategoryInputScreen(), self._on_category)
        elif key == "5":
            self.dismiss({"mode": "conf_range", "conf_range": (0.0, 0.7)})

    def _on_category(self, cat: str | None) -> None:
        if cat:
            self.dismiss({"mode": "category", "category": cat})
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    FilterScreen {
        align: center middle;
    }
    FilterScreen > Static {
        width: 50;
        border: round $primary;
        padding: 1 2;
    }
    """


class CategoryInputScreen(ModalScreen[str | None]):
    """Simple input to type a category name for filtering."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Label("Filter by category (type name, Enter):", id="catinput-label")
        cats = "  ".join(ALL_CATEGORIES)
        yield Static(f"[dim]{cats}[/dim]", id="catinput-list")
        yield Input(placeholder="e.g. DESIGN", id="catinput-input")

    def on_mount(self) -> None:
        self.query_one("#catinput-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip().upper()
        self.dismiss(val if val in ALL_CATEGORIES else None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    CategoryInputScreen {
        align: center middle;
    }
    CategoryInputScreen > Label { width: 55; padding: 1; }
    CategoryInputScreen > Static { width: 55; padding: 0 1; }
    CategoryInputScreen > Input { width: 55; }
    """


class SortScreen(ModalScreen[str | None]):
    """Sort mode picker."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Sort mode:[/bold]\n\n"
            "  \\[[bold]A[/bold]] Original order\n"
            "  \\[[bold]B[/bold]] Confidence ascending (hardest first)\n"
            "  \\[[bold]C[/bold]] Confidence descending (easiest first)\n"
            "  \\[[bold]D[/bold]] By D1 category\n"
            "  \\[[bold]ESC[/bold]] Cancel",
            id="sort-body",
        )

    def on_key(self, event) -> None:
        mapping = {"a": "original", "b": "conf_asc", "c": "conf_desc", "d": "category"}
        key = event.key.lower()
        if key in mapping:
            self.dismiss(mapping[key])

    def action_cancel(self) -> None:
        self.dismiss(None)

    DEFAULT_CSS = """
    SortScreen {
        align: center middle;
    }
    SortScreen > Static {
        width: 55;
        border: round $primary;
        padding: 1 2;
    }
    """


# ── Main app ──────────────────────────────────────────────────────────────────

class ReviewApp(App):

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }
    #header {
        height: 2;
        padding: 0 1;
        background: $primary-darken-3;
        color: $text;
    }
    #chunk-panel {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
        overflow-y: hidden;
    }
    #context-panel {
        height: 12;
        border: round $primary;
        padding: 0 1;
        overflow-y: hidden;
    }
    #controls-panel {
        height: 4;
        border: round $accent-darken-2;
        padding: 0 1;
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        Binding("k", "keep", "Keep"),
        Binding("d", "drop", "Drop"),
        Binding("r", "relabel", "Relabel"),
        Binding("a", "ambiguous", "Ambiguous"),
        Binding("n", "notes", "Notes"),
        Binding("f", "filter_mode", "Filter"),
        Binding("s", "sort_mode", "Sort"),
        Binding("j", "jump", "Jump"),
        Binding("right", "next_record", "Next"),
        Binding("space", "next_record", "Next"),
        Binding("left", "prev_record", "Prev"),
        Binding("q", "quit_clean", "Quit"),
    ]

    def __init__(self, session: ReviewSession) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield Static(id="chunk-panel")
        yield Static(id="context-panel")
        yield Static(id="controls-panel")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        record = self.session.current_record()
        self.query_one("#header", Static).update(_render_header(self.session))
        if record is None:
            self.query_one("#chunk-panel", Static).update(
                "[dim]No records match the current filter.[/dim]"
            )
            self.query_one("#context-panel", Static).update("")
        else:
            self.query_one("#chunk-panel", Static).update(_render_chunk(record))
            self.query_one("#context-panel", Static).update(
                _render_context(record, self.session.curated)
            )
        self.query_one("#controls-panel", Static).update(_render_controls(phase2=True))

    # ── Verdict actions ────────────────────────────────────────────────────────

    def action_keep(self) -> None:
        record = self.session.current_record()
        if record is None:
            return
        try:
            self.session.record_verdict(record, "KEEP", record["d1_name"])
        except OSError as e:
            self.notify(f"Write failed: {e}", severity="error", timeout=5)
            return
        self._refresh()

    def action_drop(self) -> None:
        record = self.session.current_record()
        if record is None:
            return
        try:
            self.session.record_verdict(record, "DROP", None)
        except OSError as e:
            self.notify(f"Write failed: {e}", severity="error", timeout=5)
            return
        self._refresh()

    def action_relabel(self) -> None:
        record = self.session.current_record()
        if record is None:
            return
        self.push_screen(RelabelScreen(record), self._on_relabel)

    def _on_relabel(self, category: str | None) -> None:
        if not category:
            return
        record = self.session.current_record()
        if record is None:
            return
        try:
            self.session.record_verdict(record, "RELABEL", category)
        except OSError as e:
            self.notify(f"Write failed: {e}", severity="error", timeout=5)
            return
        self._refresh()

    def action_ambiguous(self) -> None:
        record = self.session.current_record()
        if record is None:
            return
        self.push_screen(AmbiguousScreen(record), self._on_ambiguous)

    def _on_ambiguous(self, result: tuple[str, list[str]] | None) -> None:
        if result is None:
            return
        primary, alternatives = result
        record = self.session.current_record()
        if record is None:
            return
        try:
            self.session.record_verdict(
                record, "MARK_AMBIGUOUS", primary, ambiguous_with=alternatives or None
            )
        except OSError as e:
            self.notify(f"Write failed: {e}", severity="error", timeout=5)
            return
        self._refresh()

    # ── Notes action ───────────────────────────────────────────────────────────

    def action_notes(self) -> None:
        record = self.session.current_record()
        if record is None:
            return
        existing = self.session.curated.get(record["record_id"], {}).get("notes", "")
        if not existing:
            existing = self.session.notes_buffer
        self.push_screen(NotesScreen(existing), self._on_notes)

    def _on_notes(self, text: str | None) -> None:
        if text is None:
            return
        record = self.session.current_record()
        if record is None:
            return
        rid = record["record_id"]
        if rid in self.session.curated:
            # Verdict already recorded — update the written entry
            try:
                self.session.update_notes(rid, text)
            except OSError as e:
                self.notify(f"Notes write failed: {e}", severity="error", timeout=5)
                return
        else:
            # Verdict not yet recorded — hold in buffer
            self.session.notes_buffer = text
        self._refresh()

    # ── Filter / sort actions ──────────────────────────────────────────────────

    def action_filter_mode(self) -> None:
        self.push_screen(FilterScreen(), self._on_filter)

    def _on_filter(self, opts: dict | None) -> None:
        if opts is None:
            return
        mode = opts.pop("mode")
        self.session.apply_filter(mode, **opts)
        self._refresh()

    def action_sort_mode(self) -> None:
        self.push_screen(SortScreen(), self._on_sort)

    def _on_sort(self, mode: str | None) -> None:
        if mode is None:
            return
        self.session.apply_sort(mode)
        self._refresh()

    # ── Navigation actions ─────────────────────────────────────────────────────

    def action_jump(self) -> None:
        self.push_screen(JumpScreen(), self._on_jump)

    def _on_jump(self, record_id: str | None) -> None:
        if not record_id:
            return
        if not self.session.jump_to_id(record_id):
            self.notify(f"Record ID not found in current filter: {record_id}", timeout=3)
            return
        self._refresh()

    def action_next_record(self) -> None:
        self.session.advance()
        self._refresh()

    def action_prev_record(self) -> None:
        self.session.go_back()
        self._refresh()

    def action_quit_clean(self) -> None:
        self.exit()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3 manual review TUI")
    parser.add_argument(
        "--calibration",
        action="store_true",
        help=f"Calibration mode: first {CAL_COUNT} records, separate output file",
    )
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        print(f"ERROR: input file not found: {INPUT_PATH}", file=sys.stderr)
        sys.exit(1)

    records = _load_records(INPUT_PATH)
    output_path = CAL_OUTPUT_PATH if args.calibration else OUTPUT_PATH
    curated = _load_curated(output_path)

    if curated and not args.calibration:
        print(f"Resuming: {len(curated)} records already reviewed. Skipping to first unreviewed.")

    session = ReviewSession(
        records=records,
        curated=curated,
        output_path=output_path,
        calibration=args.calibration,
    )

    app = ReviewApp(session)
    app.run()

    # Print session summary after TUI exits
    if session.session_count > 0:
        print(session.session_summary())
    elif not args.calibration:
        remaining = session.total_records - session.total_reviewed
        print(f"\nNo records reviewed this session. {remaining} remaining.\n")

    # Calibration mode: print final count and exit note
    if args.calibration and session.session_count > 0:
        print(
            f"Calibration verdicts written to: {CAL_OUTPUT_PATH}\n"
            "These do not affect the main review state.\n"
        )


if __name__ == "__main__":
    main()
