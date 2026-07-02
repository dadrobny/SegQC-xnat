#!/usr/bin/env python3
"""Generate an evolving HTML project-status summary for Seg-QC-xnat.

This is an AIDE *process* tool, not part of the shipped ``segqc`` package. It
reads the living AIDE documents under ``docs/aide/`` (vision, roadmap, progress,
queues, item specs), summarises the test suite, and renders a single
self-contained HTML dashboard that answers, at a glance:

* **Work-Queue Overview** — which items are finished vs. upcoming, and how each
  maps to a roadmap stage and a vision objective.
* **Testing Overview** — how many tests exist and (optionally) their last
  pass/fail outcome from a pytest JUnit-XML report.
* **Project Feature Highlights** — QC overlay images and feature-distribution
  plots. These are *extension points*: they auto-populate once the evaluation
  artifacts they depend on (roadmap Stages 5–7) exist, and render an explicit
  "not yet available" placeholder until then.

The output is designed to be **regenerated and extended** throughout
development — it is a living summary, not a one-off report. Rendering is
deterministic given the same inputs (only the "generated at" timestamp varies),
so re-runs produce stable diffs.

Usage::

    python scripts/aide_status_report.py                 # writes docs/aide/status/index.html
    python scripts/aide_status_report.py --out report.html
    python scripts/aide_status_report.py --junit results.xml   # include test outcomes
    python scripts/aide_status_report.py --qc-images out/qc     # embed QC overlay PNGs
    python scripts/aide_status_report.py --distributions out/dist

The module also exposes pure parsing/rendering functions (``parse_progress``,
``parse_queues``, ``parse_items``, ``summarise_tests``, ``build_report_model``,
``render_html``) so they can be unit-tested without touching the filesystem.
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Locations (resolved relative to the repo root, i.e. this file's parent's parent)
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[1]
AIDE_DIR = REPO_ROOT / "docs" / "aide"
DEFAULT_OUT = AIDE_DIR / "status" / "index.html"

STATUS_ICONS = {
    "📋": "planned",
    "🚧": "in-progress",
    "✅": "complete",
    "⏸️": "deferred",
    "❌": "excluded",
}
# Precedence when an item is referenced on several progress lines: the most
# advanced status wins (complete beats in-progress beats planned …).
_STATUS_RANK = {"complete": 4, "in-progress": 3, "deferred": 2, "excluded": 1, "planned": 0}

_ICON_RE = re.compile("|".join(re.escape(k) for k in STATUS_ICONS))
_ITEM_REF_RE = re.compile(r"[Ii]tem\s+0*(\d+)")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Stage:
    number: str
    title: str
    objectives: str
    status: str  # one of STATUS_ICONS values


@dataclass
class Objective:
    code: str  # e.g. "G1"
    description: str
    delivered_by: str
    status: str


@dataclass
class WorkItem:
    number: int
    title: str
    status: str = "planned"
    stage: Optional[str] = None  # roadmap stage number this item sits under


@dataclass
class TestSummary:
    file_count: int = 0
    test_count: int = 0
    passed: Optional[int] = None
    failed: Optional[int] = None
    errors: Optional[int] = None
    skipped: Optional[int] = None

    @property
    def has_outcomes(self) -> bool:
        return self.passed is not None or self.failed is not None


@dataclass
class ReportModel:
    generated_at: str
    project: str = "Seg-QC-xnat"
    stages: List[Stage] = field(default_factory=list)
    objectives: List[Objective] = field(default_factory=list)
    items: List[WorkItem] = field(default_factory=list)
    tests: TestSummary = field(default_factory=TestSummary)
    qc_images: List[Tuple[str, str]] = field(default_factory=list)  # (label, data-uri or path)
    distributions: List[Tuple[str, str]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _icon_to_status(text: str) -> Optional[str]:
    m = _ICON_RE.search(text)
    return STATUS_ICONS[m.group(0)] if m else None


def _split_table_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_progress(text: str) -> Tuple[List[Stage], List[Objective], Dict[int, Tuple[str, Optional[str]]]]:
    """Parse ``progress.md``.

    Returns ``(stages, objectives, item_status)`` where ``item_status`` maps an
    item number to ``(status, stage_number)`` derived from the ``*(Item NNN)*``
    references and the status icon on their line / their stage section.
    """
    lines = text.splitlines()
    stages: List[Stage] = []
    objectives: List[Objective] = []
    item_status: Dict[int, Tuple[str, Optional[str]]] = {}

    # --- Stage summary + objective-coverage tables ---
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = _split_table_row(line)
        if len(cells) == 4 and re.fullmatch(r"\d+", cells[0]):
            status = _icon_to_status(cells[3])
            if status:
                stages.append(Stage(cells[0], cells[1], cells[2], status))
        elif len(cells) == 3 and re.fullmatch(r"G\d+.*", cells[0]):
            status = _icon_to_status(cells[2])
            code_m = re.match(r"(G\d+)\s*(.*)", cells[0])
            if code_m and status:
                objectives.append(
                    Objective(code_m.group(1), code_m.group(2).strip(), cells[1], status)
                )

    # --- Per-item status, tracked by which "## Stage N" section it appears in ---
    # A deliverable may wrap across physical lines, leaving its ``*(Item NNN)*``
    # reference on a continuation line that carries no status icon. Such a line
    # inherits the icon of the list item (``- ✅ …``) it belongs to, so the item
    # is not misread as "planned".
    current_stage: Optional[str] = None
    bullet_status: Optional[str] = None
    stage_header_re = re.compile(r"^##\s+Stage\s+(\d+)")
    bullet_re = re.compile(r"^\s*-\s")
    for line in lines:
        hm = stage_header_re.match(line)
        if hm:
            current_stage = hm.group(1)
            bullet_status = None
            continue
        line_icon = _icon_to_status(line)
        if bullet_re.match(line):
            bullet_status = line_icon
        for ref in _ITEM_REF_RE.finditer(line):
            num = int(ref.group(1))
            status = line_icon or bullet_status or "planned"
            prev = item_status.get(num)
            if prev is None or _STATUS_RANK[status] > _STATUS_RANK[prev[0]]:
                item_status[num] = (status, current_stage)
            elif prev[1] is None and current_stage is not None:
                item_status[num] = (prev[0], current_stage)
    return stages, objectives, item_status


def parse_items(items_dir: Path) -> Dict[int, str]:
    """Map item number -> human title from ``docs/aide/items/NNN-*.md`` files."""
    titles: Dict[int, str] = {}
    if not items_dir.is_dir():
        return titles
    for path in sorted(items_dir.glob("*.md")):
        m = re.match(r"0*(\d+)", path.name)
        if not m:
            continue
        num = int(m.group(1))
        titles[num] = _item_title(path)
    return titles


def _item_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("# "):
                # e.g. "# Work Item 027: Level-aware bounds" -> keep after the colon
                heading = line[2:].strip()
                return heading.split(":", 1)[1].strip() if ":" in heading else heading
    except OSError:
        pass
    # Fall back to a slug derived from the filename.
    slug = re.sub(r"^0*\d+[-_]?", "", path.stem)
    return slug.replace("-", " ").replace("_", " ").strip().title() or path.stem


def parse_queues(queue_dir: Path) -> List[int]:
    """Return the ordered list of item numbers referenced across queue files."""
    seen: List[int] = []
    if not queue_dir.is_dir():
        return seen
    heading_re = re.compile(r"^###\s+Item\s+0*(\d+)", re.MULTILINE)
    for path in sorted(queue_dir.glob("queue-*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in heading_re.finditer(text):
            num = int(m.group(1))
            if num not in seen:
                seen.append(num)
    return seen


def summarise_tests(tests_dir: Path, junit_xml: Optional[Path] = None) -> TestSummary:
    """Count test files/functions statically; enrich with JUnit outcomes if given."""
    summary = TestSummary()
    if tests_dir.is_dir():
        test_files = sorted(tests_dir.glob("test_*.py"))
        summary.file_count = len(test_files)
        count = 0
        for path in test_files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            count += len(re.findall(r"^\s*def\s+test_\w+", text, re.MULTILINE))
        summary.test_count = count

    if junit_xml and junit_xml.is_file():
        _apply_junit(summary, junit_xml)
    return summary


def _apply_junit(summary: TestSummary, junit_xml: Path) -> None:
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(junit_xml).getroot()
    except (ET.ParseError, OSError):
        return
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = failures = errors = skipped = 0
    for s in suites:
        total += int(s.get("tests", 0))
        failures += int(s.get("failures", 0))
        errors += int(s.get("errors", 0))
        skipped += int(s.get("skipped", 0))
    if total:
        summary.failed = failures
        summary.errors = errors
        summary.skipped = skipped
        summary.passed = total - failures - errors - skipped
        summary.test_count = summary.test_count or total


def _collect_images(directory: Optional[Path], embed: bool) -> List[Tuple[str, str]]:
    """Return (label, src) pairs for PNG/SVG images in a directory (sorted)."""
    out: List[Tuple[str, str]] = []
    if not directory or not directory.is_dir():
        return out
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
            continue
        label = path.stem.replace("_", " ").replace("-", " ")
        if embed:
            out.append((label, _data_uri(path)))
        else:
            out.append((label, path.as_posix()))
    return out


def _data_uri(path: Path) -> str:
    mime = {
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }[path.suffix.lower()]
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


# --------------------------------------------------------------------------- #
# Model assembly
# --------------------------------------------------------------------------- #
def build_report_model(
    aide_dir: Path = AIDE_DIR,
    tests_dir: Optional[Path] = None,
    junit_xml: Optional[Path] = None,
    qc_images_dir: Optional[Path] = None,
    distributions_dir: Optional[Path] = None,
    embed_images: bool = True,
    now: Optional[_dt.datetime] = None,
) -> ReportModel:
    tests_dir = tests_dir or (REPO_ROOT / "tests")
    now = now or _dt.datetime.now(_dt.timezone.utc)

    progress_path = aide_dir / "progress.md"
    stages: List[Stage] = []
    objectives: List[Objective] = []
    item_status: Dict[int, Tuple[str, Optional[str]]] = {}
    if progress_path.is_file():
        stages, objectives, item_status = parse_progress(
            progress_path.read_text(encoding="utf-8")
        )

    titles = parse_items(aide_dir / "items")
    queued = parse_queues(aide_dir / "queue")

    # Union of every item we know about, from specs and queues.
    numbers = sorted(set(titles) | set(item_status) | set(queued))
    items: List[WorkItem] = []
    for num in numbers:
        status, stage = item_status.get(num, ("planned", None))
        items.append(
            WorkItem(
                number=num,
                title=titles.get(num, f"Item {num:03d}"),
                status=status,
                stage=stage,
            )
        )

    model = ReportModel(
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        stages=stages,
        objectives=objectives,
        items=items,
        tests=summarise_tests(tests_dir, junit_xml),
        qc_images=_collect_images(qc_images_dir, embed_images),
        distributions=_collect_images(distributions_dir, embed_images),
    )
    return model


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
_CSS = """
:root { --done:#1a7f37; --wip:#bf8700; --plan:#57606a; --bg:#f6f8fa; --line:#d0d7de; }
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       margin: 0; color: #1f2328; background: var(--bg); }
header { background: #24292f; color: #fff; padding: 24px 32px; }
header h1 { margin: 0 0 4px; font-size: 22px; }
header .meta { color: #b1bac4; font-size: 13px; }
main { max-width: 1080px; margin: 0 auto; padding: 24px 32px 64px; }
section { background: #fff; border: 1px solid var(--line); border-radius: 8px;
          padding: 20px 24px; margin: 20px 0; }
h2 { font-size: 18px; margin: 0 0 16px; border-bottom: 1px solid var(--line); padding-bottom: 8px; }
h3 { font-size: 14px; margin: 20px 0 8px; color: #57606a; text-transform: uppercase; letter-spacing: .04em; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: #57606a; font-weight: 600; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
         font-weight: 600; color: #fff; white-space: nowrap; }
.b-complete { background: var(--done); }
.b-in-progress { background: var(--wip); }
.b-planned { background: var(--plan); }
.b-deferred { background: #8250df; }
.b-excluded { background: #cf222e; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; }
.card { flex: 1 1 150px; background: var(--bg); border: 1px solid var(--line); border-radius: 8px;
        padding: 14px 16px; }
.card .n { font-size: 26px; font-weight: 700; }
.card .l { font-size: 12px; color: #57606a; }
.gallery { display: flex; flex-wrap: wrap; gap: 16px; }
.gallery figure { margin: 0; flex: 1 1 260px; }
.gallery img { max-width: 100%; border: 1px solid var(--line); border-radius: 6px; }
.gallery figcaption { font-size: 12px; color: #57606a; margin-top: 6px; }
.placeholder { border: 1px dashed var(--line); border-radius: 8px; padding: 24px;
               color: #57606a; background: var(--bg); font-size: 14px; }
.placeholder strong { color: #1f2328; }
.progress-bar { height: 10px; background: var(--line); border-radius: 999px; overflow: hidden; }
.progress-bar > span { display: block; height: 100%; background: var(--done); }
footer { text-align: center; color: #57606a; font-size: 12px; padding: 24px; }
"""


def _badge(status: str) -> str:
    return f'<span class="badge b-{status}">{html.escape(status)}</span>'


def _esc(text: str) -> str:
    return html.escape(str(text))


def _render_stage_section(model: ReportModel) -> str:
    if not model.stages:
        return ""
    done = sum(1 for s in model.stages if s.status == "complete")
    pct = round(100 * done / len(model.stages)) if model.stages else 0
    rows = "\n".join(
        f"<tr><td>{_esc(s.number)}</td><td>{_esc(s.title)}</td>"
        f"<td>{_esc(s.objectives)}</td><td>{_badge(s.status)}</td></tr>"
        for s in model.stages
    )
    return f"""
<section id="phase">
  <h2>Project Phase Alignment</h2>
  <p>{done} of {len(model.stages)} roadmap stages complete ({pct}%).</p>
  <div class="progress-bar"><span style="width:{pct}%"></span></div>
  <table>
    <tr><th>Stage</th><th>Title</th><th>Objectives</th><th>Status</th></tr>
    {rows}
  </table>
</section>"""


def _render_objectives_section(model: ReportModel) -> str:
    if not model.objectives:
        return ""
    rows = "\n".join(
        f"<tr><td><strong>{_esc(o.code)}</strong></td><td>{_esc(o.description)}</td>"
        f"<td>{_esc(o.delivered_by)}</td><td>{_badge(o.status)}</td></tr>"
        for o in model.objectives
    )
    return f"""
<section id="objectives">
  <h2>Vision Objective Coverage</h2>
  <table>
    <tr><th>Objective</th><th>Description</th><th>Delivered by</th><th>Status</th></tr>
    {rows}
  </table>
</section>"""


def _render_queue_section(model: ReportModel) -> str:
    finished = [i for i in model.items if i.status == "complete"]
    active = [i for i in model.items if i.status == "in-progress"]
    upcoming = [i for i in model.items if i.status not in {"complete", "in-progress"}]

    def _rows(items: Sequence[WorkItem]) -> str:
        if not items:
            return '<tr><td colspan="4"><em>none</em></td></tr>'
        return "\n".join(
            f"<tr><td>{i.number:03d}</td><td>{_esc(i.title)}</td>"
            f"<td>{_esc(i.stage or '—')}</td><td>{_badge(i.status)}</td></tr>"
            for i in items
        )

    return f"""
<section id="queue">
  <h2>Work-Queue Overview</h2>
  <div class="cards">
    <div class="card"><div class="n">{len(finished)}</div><div class="l">Finished</div></div>
    <div class="card"><div class="n">{len(active)}</div><div class="l">In progress</div></div>
    <div class="card"><div class="n">{len(upcoming)}</div><div class="l">Upcoming</div></div>
  </div>
  <h3>Finished work items</h3>
  <table><tr><th>#</th><th>Title</th><th>Stage</th><th>Status</th></tr>{_rows(finished)}</table>
  <h3>In progress</h3>
  <table><tr><th>#</th><th>Title</th><th>Stage</th><th>Status</th></tr>{_rows(active)}</table>
  <h3>Upcoming / planned</h3>
  <table><tr><th>#</th><th>Title</th><th>Stage</th><th>Status</th></tr>{_rows(upcoming)}</table>
</section>"""


def _render_tests_section(model: ReportModel) -> str:
    t = model.tests
    cards = [
        f'<div class="card"><div class="n">{t.file_count}</div><div class="l">Test files</div></div>',
        f'<div class="card"><div class="n">{t.test_count}</div><div class="l">Test functions</div></div>',
    ]
    if t.has_outcomes:
        cards += [
            f'<div class="card"><div class="n">{t.passed}</div><div class="l">Passed</div></div>',
            f'<div class="card"><div class="n">{t.failed}</div><div class="l">Failed</div></div>',
        ]
        if t.errors:
            cards.append(f'<div class="card"><div class="n">{t.errors}</div><div class="l">Errors</div></div>')
        note = ""
    else:
        note = (
            '<p class="placeholder">Static counts shown. Pass '
            "<code>--junit results.xml</code> (from "
            "<code>pytest --junitxml=results.xml</code>) to include pass/fail outcomes and trends.</p>"
        )
    return f"""
<section id="tests">
  <h2>Testing Overview</h2>
  <div class="cards">{''.join(cards)}</div>
  {note}
</section>"""


def _render_highlights_section(model: ReportModel) -> str:
    def _gallery(pairs: Sequence[Tuple[str, str]]) -> str:
        figs = "\n".join(
            f'<figure><img src="{_esc(src)}" alt="{_esc(label)}"/>'
            f"<figcaption>{_esc(label)}</figcaption></figure>"
            for label, src in pairs
        )
        return f'<div class="gallery">{figs}</div>'

    if model.qc_images:
        qc_block = _gallery(model.qc_images)
    else:
        qc_block = (
            '<p class="placeholder"><strong>Extension point.</strong> QC overlay images '
            "populate here once cases have been run and their sagittal projections "
            "(roadmap item 021) are written out. Point the generator at an output "
            "folder with <code>--qc-images &lt;dir&gt;</code>.</p>"
        )

    if model.distributions:
        dist_block = _gallery(model.distributions)
    else:
        dist_block = (
            '<p class="placeholder"><strong>Extension point.</strong> Feature-distribution '
            "plots populate here once the evaluation corpus and reference distributions "
            "(roadmap Stages 5–7) exist. Point the generator at a folder of plots with "
            "<code>--distributions &lt;dir&gt;</code>.</p>"
        )

    return f"""
<section id="highlights">
  <h2>Project Feature Highlights</h2>
  <h3>QC overlay images</h3>
  {qc_block}
  <h3>Feature distributions</h3>
  {dist_block}
</section>"""


def render_html(model: ReportModel) -> str:
    body = "".join(
        [
            _render_queue_section(model),
            _render_stage_section(model),
            _render_objectives_section(model),
            _render_tests_section(model),
            _render_highlights_section(model),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(model.project)} — Project Status</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>{_esc(model.project)} — Project Status Summary</h1>
  <div class="meta">Living AIDE summary · generated {_esc(model.generated_at)}</div>
</header>
<main>
{body}
</main>
<footer>Regenerate with <code>python scripts/aide_status_report.py</code>. This is a living
document — re-run it as development progresses to extend the summary.</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output HTML path")
    parser.add_argument("--aide-dir", type=Path, default=AIDE_DIR, help="docs/aide directory")
    parser.add_argument("--tests-dir", type=Path, default=REPO_ROOT / "tests", help="tests directory")
    parser.add_argument("--junit", type=Path, default=None, help="pytest JUnit-XML for pass/fail outcomes")
    parser.add_argument("--qc-images", type=Path, default=None, help="folder of QC overlay images to embed")
    parser.add_argument("--distributions", type=Path, default=None, help="folder of feature-distribution plots")
    parser.add_argument("--no-embed", action="store_true", help="reference images by path instead of embedding")
    args = parser.parse_args(argv)

    model = build_report_model(
        aide_dir=args.aide_dir,
        tests_dir=args.tests_dir,
        junit_xml=args.junit,
        qc_images_dir=args.qc_images,
        distributions_dir=args.distributions,
        embed_images=not args.no_embed,
    )
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(model), encoding="utf-8")
    print(f"Wrote {out} ({len(model.items)} items, {len(model.stages)} stages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
