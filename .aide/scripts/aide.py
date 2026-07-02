#!/usr/bin/env python3
"""aide — the AIDE framework CLI.

A single, stdlib-only command-line tool for the deterministic parts of the AIDE
loop, so agents don't spend reasoning tokens on mechanical git/document surgery.
It is **venv-independent** (it must run before/without the project venv) and
**project-agnostic** — every project fact comes from ``aide.toml``.

Subcommands::

    python .aide/scripts/aide.py check                 # consistency gate over docs/aide
    python .aide/scripts/aide.py progress set NNN <in-progress|done>
    python .aide/scripts/aide.py queue tidy NNN        # mark a superseded queue as completed
    python .aide/scripts/aide.py claim [--queue NNN]   # pick + claim the next 📋 item
    python .aide/scripts/aide.py merge NNN             # merge a validated item per git.mode
    python .aide/scripts/aide.py env                   # venv existence / import check + bootstrap

The parsing/editing helpers are pure functions so they can be unit-tested without
touching git or the real filesystem (see ``.aide/scripts/tests``).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Status icons (the format contract — see .aide/conventions.md)
# --------------------------------------------------------------------------- #
STATUS_TO_ICON = {
    "planned": "📋",
    "in-progress": "🚧",
    "complete": "✅",
    "deferred": "⏸️",
    "excluded": "❌",
}
ICON_TO_STATUS = {v: k for k, v in STATUS_TO_ICON.items()}
RANK = {"planned": 0, "excluded": 1, "deferred": 2, "in-progress": 3, "complete": 4}

# Icons may be multi-codepoint (⏸️ = U+23F8 U+FE0F), so match by alternation
# (longest first), never a character class.
_ICON_ALT = "(?:" + "|".join(re.escape(i) for i in sorted(ICON_TO_STATUS, key=len, reverse=True)) + ")"
_ICON_RE = re.compile(_ICON_ALT)
# A deliverable bullet: leading "- " then a status icon.
_BULLET_RE = re.compile(r"^(?P<indent>\s*[-*]\s*)(?P<icon>" + _ICON_ALT + r")")
_CHECKBOX_RE = re.compile(r"^(?P<pre>\s*[-*]\s*\[)(?P<mark>[ xX])(?P<post>\].*)$")
_STAGE_HEADER_RE = re.compile(r"^##\s+Stage\s+(\d+)\b(.*)$")
_ANY_HEADER_RE = re.compile(r"^#{1,2}\s+")


def _item_ref_re(num: int) -> re.Pattern:
    """Match ``*(Item NNN)*`` / ``*(Items 006, NNN)*`` for a specific number."""
    return re.compile(r"\bItems?\b[^)]*\b0*" + str(num) + r"\b")


# --------------------------------------------------------------------------- #
# TOML config (tomllib on 3.11+, tiny fallback for the aide.toml subset on 3.9)
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG: Dict[str, Dict[str, object]] = {
    "project": {"name": "project", "source_dir": "src", "tests_dir": "tests", "docs_dir": "docs/aide"},
    "python": {"venv": ".venv", "bootstrap": "pip install -e .[dev]",
               "test_command": "python -m pytest", "import_check": ""},
    "git": {"mode": "auto-merge", "main_branch": "main", "branch_prefix": "aide/"},
    "loop": {"queue_cap": 10, "validation_rounds": 3, "clarify": "assume"},
}


def _parse_toml(text: str) -> Dict[str, Dict[str, object]]:
    """Minimal TOML reader for the flat ``[table] key = value`` shape of aide.toml.

    Supports string/int/float/bool scalars and ``#`` comments. Used only when the
    stdlib ``tomllib`` (Python 3.11+) is unavailable, so the CLI and its tests run
    on the project's 3.9 venv too.
    """
    data: Dict[str, Dict[str, object]] = {}
    table: Optional[Dict[str, object]] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[([A-Za-z0-9_.]+)\]$", line)
        if m:
            table = data.setdefault(m.group(1), {})
            continue
        if table is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split("#", 1)[0].strip() if not value.lstrip().startswith('"') else value.strip()
        # strip trailing comment for unquoted values only (quoted may contain #)
        if value and value[0] in "\"'":
            table[key] = value[1:].split(value[0], 1)[0]
        elif value.lower() in ("true", "false"):
            table[key] = value.lower() == "true"
        else:
            token = value.split("#", 1)[0].strip()
            try:
                table[key] = int(token)
            except ValueError:
                try:
                    table[key] = float(token)
                except ValueError:
                    table[key] = token
    return data


def load_config(repo_root: Path) -> Dict[str, Dict[str, object]]:
    """Load ``aide.toml`` merged over defaults. Missing file -> defaults."""
    merged = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    path = repo_root / "aide.toml"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        try:
            import tomllib  # type: ignore
            parsed = tomllib.loads(text)
        except ModuleNotFoundError:
            parsed = _parse_toml(text)
        for section, values in parsed.items():
            merged.setdefault(section, {})
            if isinstance(values, dict):
                merged[section].update(values)
    return merged


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up from ``start`` (default cwd) to the directory holding aide.toml."""
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "aide.toml").is_file():
            return candidate
    return start


def docs_dir(repo_root: Path, config: Dict[str, Dict[str, object]]) -> Path:
    return repo_root / str(config["project"].get("docs_dir", "docs/aide"))


# --------------------------------------------------------------------------- #
# progress.md — parsing helpers
# --------------------------------------------------------------------------- #
def _icon_status(text: str) -> Optional[str]:
    m = _ICON_RE.search(text)
    return ICON_TO_STATUS[m.group(0)] if m else None


def _split_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def stage_sections(lines: List[str]) -> List[Tuple[int, int, str]]:
    """Return ``(start_index, end_index_exclusive, stage_number)`` per stage section."""
    out: List[Tuple[int, int, str]] = []
    starts: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _STAGE_HEADER_RE.match(line)
        if m:
            starts.append((i, m.group(1)))
    for idx, (start, num) in enumerate(starts):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if _ANY_HEADER_RE.match(lines[j]):
                end = j
                break
        out.append((start, end, num))
    return out


def stage_deliverable_statuses(lines: List[str], start: int, end: int) -> List[str]:
    """Statuses of the flat deliverable bullets within a stage section."""
    statuses: List[str] = []
    for line in lines[start:end]:
        if _CHECKBOX_RE.match(line):
            continue
        m = _BULLET_RE.match(line)
        if m:
            statuses.append(ICON_TO_STATUS[m.group("icon")])
    return statuses


def rollup_status(statuses: List[str]) -> Optional[str]:
    """Derive a stage status from its deliverable statuses (None if no bullets)."""
    if not statuses:
        return None
    if all(s in ("complete", "deferred", "excluded") for s in statuses) and any(
        s == "complete" for s in statuses
    ):
        return "complete"
    if any(s in ("complete", "in-progress") for s in statuses):
        return "in-progress"
    return "planned"


# --------------------------------------------------------------------------- #
# progress.md — editing
# --------------------------------------------------------------------------- #
def _replace_first_icon(line: str, status: str) -> str:
    return _ICON_RE.sub(STATUS_TO_ICON[status], line, count=1)


def _set_summary_row(lines: List[str], stage_num: str, status: str) -> None:
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if len(cells) == 4 and cells[0] == stage_num and _icon_status(cells[3]):
            current = _icon_status(cells[3])
            if current in ("deferred", "excluded"):
                return
            if RANK[status] >= RANK[current]:
                lines[i] = _ICON_RE.sub(STATUS_TO_ICON[status], line)
            return


def _set_stage_header(lines: List[str], start: int, status: str) -> None:
    line = lines[start]
    current = _icon_status(line)
    if current in ("deferred", "excluded"):
        return
    if current is None:
        lines[start] = line.rstrip() + f" — {STATUS_TO_ICON[status]}"
    elif RANK[status] >= RANK[current]:
        lines[start] = _ICON_RE.sub(STATUS_TO_ICON[status], line)


def _tick_acceptance(lines: List[str], start: int, end: int) -> None:
    for i in range(start, end):
        m = _CHECKBOX_RE.match(lines[i])
        if m and m.group("mark") == " ":
            lines[i] = m.group("pre") + "x" + m.group("post")


def _objective_stages(delivered_by: str) -> List[str]:
    return re.findall(r"\bStage[s]?\s+([\d,\s]+)", delivered_by)


def _apply_objective_rollup(lines: List[str], stage_status: Dict[str, str]) -> None:
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if len(cells) == 3 and re.match(r"G\d+", cells[0]) and _icon_status(cells[2]):
            nums: List[str] = []
            for chunk in re.findall(r"\d+", cells[1]):
                nums.append(chunk)
            if not nums:
                continue
            current = _icon_status(cells[2])
            if current in ("deferred", "excluded"):
                continue
            statuses = [stage_status.get(n) for n in nums if stage_status.get(n)]
            if statuses and all(s == "complete" for s in statuses):
                derived = "complete"
            elif any(s in ("complete", "in-progress") for s in statuses):
                derived = "in-progress"
            else:
                derived = current
            if RANK[derived] >= RANK[current]:
                lines[i] = _ICON_RE.sub(STATUS_TO_ICON[derived], line)


def set_item_status(text: str, num: int, status: str) -> str:
    """Flip item NNN's deliverable bullet(s) to ``status`` and roll stages up.

    ``status`` is ``in-progress`` or ``complete``. Ticks acceptance boxes and
    updates summary/header/objective rows only for stages that fully complete.
    Never downgrades an existing status (additive log).
    """
    lines = text.splitlines()
    ref = _item_ref_re(num)
    # Flip the owning bullet's icon for every line that references this item.
    bullet_line: Optional[int] = None
    for i, line in enumerate(lines):
        if _BULLET_RE.match(line) or re.match(r"^\s*[-*]\s", line):
            if _BULLET_RE.match(line):
                bullet_line = i
        if ref.search(line):
            target = bullet_line if bullet_line is not None and _BULLET_RE.match(lines[bullet_line]) else i
            if _BULLET_RE.match(lines[target]):
                current = _icon_status(lines[target])
                if current and RANK[status] > RANK[current]:
                    lines[target] = _replace_first_icon(lines[target], status)

    # Recompute rollups for every stage (never downgrading).
    stage_status: Dict[str, str] = {}
    for start, end, stage_num in stage_sections(lines):
        derived = rollup_status(stage_deliverable_statuses(lines, start, end))
        if derived is None:
            continue
        stage_status[stage_num] = derived
        _set_stage_header(lines, start, derived)
        _set_summary_row(lines, stage_num, derived)
        if derived == "complete":
            _tick_acceptance(lines, start, end)
    _apply_objective_rollup(lines, stage_status)

    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# queue.md helpers
# --------------------------------------------------------------------------- #
_QUEUE_STATUS_RE = re.compile(r"^>\s*\*\*Status:\*\*\s*(.*)$")
_QUEUE_ITEM_RE = re.compile(r"^###\s+Item\s+0*(\d+)\b", re.MULTILINE)


def queue_status(text: str) -> Optional[str]:
    for line in text.splitlines():
        m = _QUEUE_STATUS_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def is_live_queue(text: str) -> bool:
    status = queue_status(text) or ""
    return status.lower().startswith("live")


def queue_item_numbers(text: str) -> List[int]:
    return [int(m.group(1)) for m in _QUEUE_ITEM_RE.finditer(text)]


def tidy_queue_text(text: str, superseded_by: int, date: str) -> str:
    """Rewrite a queue's Status line to 'Completed — superseded by queue-NNN'."""
    new_status = f"> **Status:** ✅ Completed — superseded by queue-{superseded_by:03d} ({date})."
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _QUEUE_STATUS_RE.match(line):
            lines[i] = new_status
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    # No status line: insert after the H1.
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(i + 1, new_status)
            break
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def run_checks(repo_root: Path, config: Dict[str, Dict[str, object]],
               branches: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)``. Empty errors == pass."""
    errors: List[str] = []
    warnings: List[str] = []
    ddir = docs_dir(repo_root, config)
    progress_path = ddir / "progress.md"

    if not progress_path.is_file():
        return [f"missing {progress_path}"], warnings
    text = progress_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Mandatory sections.
    has_stage_table = any(
        len(_split_row(l)) == 4 and re.fullmatch(r"\d+", _split_row(l)[0]) for l in lines
    )
    has_obj_table = any(
        len(_split_row(l)) == 3 and re.match(r"G\d+", _split_row(l)[0]) for l in lines
    )
    sections = stage_sections(lines)
    if not has_stage_table:
        errors.append("progress.md: missing Stage summary table")
    if not has_obj_table:
        errors.append("progress.md: missing Objective coverage table")
    if not sections:
        errors.append("progress.md: no '## Stage N' sections")

    # Summary row status vs. section header + rollup consistency.
    summary_status: Dict[str, str] = {}
    for l in lines:
        cells = _split_row(l) if l.strip().startswith("|") else []
        if len(cells) == 4 and re.fullmatch(r"\d+", cells[0]) and _icon_status(cells[3]):
            summary_status[cells[0]] = _icon_status(cells[3])

    section_nums = set()
    for start, end, num in sections:
        section_nums.add(num)
        header_status = _icon_status(lines[start])
        derived = rollup_status(stage_deliverable_statuses(lines, start, end))
        summ = summary_status.get(num)
        if summ in ("deferred", "excluded"):
            continue
        if derived == "complete" and summ and summ != "complete":
            warnings.append(f"stage {num}: all deliverables ✅ but summary shows {summ}")
        if summ == "complete" and derived and derived != "complete":
            errors.append(f"stage {num}: summary marked ✅ but has non-complete deliverables")
        if header_status and summ and header_status != summ:
            warnings.append(f"stage {num}: header {header_status} disagrees with summary {summ}")

    for num in summary_status:
        if num not in section_nums:
            warnings.append(f"stage {num}: in summary table but has no '## Stage {num}' section")

    # Queues: exactly one Live; no duplicate item numbers.
    qdir = ddir / "queue"
    live = []
    seen: Dict[int, str] = {}
    if qdir.is_dir():
        for qpath in sorted(qdir.glob("queue-*.md")):
            qtext = qpath.read_text(encoding="utf-8")
            if is_live_queue(qtext):
                live.append(qpath.name)
            for n in queue_item_numbers(qtext):
                if n in seen and seen[n] != qpath.name:
                    errors.append(f"item {n:03d} appears in both {seen[n]} and {qpath.name}")
                seen[n] = qpath.name
        if len(live) == 0:
            warnings.append("no queue marked '> **Status:** Live'")
        elif len(live) > 1:
            errors.append("more than one Live queue: " + ", ".join(live))

    # Item spec files: no duplicate numbers.
    idir = ddir / "items"
    if idir.is_dir():
        spec_nums: Dict[int, str] = {}
        for ipath in sorted(idir.glob("*.md")):
            m = re.match(r"0*(\d+)", ipath.name)
            if not m:
                continue
            n = int(m.group(1))
            if n in spec_nums:
                errors.append(f"duplicate item spec number {n:03d}: {spec_nums[n]} and {ipath.name}")
            spec_nums[n] = ipath.name

    # Claim-branch <-> status agreement (best effort).
    if branches is None:
        branches = _list_claim_branches(repo_root, str(config["git"].get("branch_prefix", "aide/")))
    _, _, item_status = _parse_item_status(lines)
    for br in branches:
        m = re.search(r"/(\d+)-", br) or re.search(r"(\d+)", br.rsplit("/", 1)[-1])
        if not m:
            continue
        n = int(m.group(1))
        if item_status.get(n) == "complete":
            warnings.append(f"stale claim branch {br}: item {n:03d} is already ✅")

    return errors, warnings


def _parse_item_status(lines: List[str]) -> Tuple[List[str], List[str], Dict[int, str]]:
    """Map item number -> most-advanced status found on its progress lines."""
    item_status: Dict[int, str] = {}
    bullet_status: Optional[str] = None
    current_stage: Optional[str] = None
    ref_re = re.compile(r"[Ii]tem[s]?\s+0*(\d+)")
    for line in lines:
        hm = _STAGE_HEADER_RE.match(line)
        if hm:
            current_stage = hm.group(1)
            bullet_status = None
            continue
        line_icon = _icon_status(line)
        if re.match(r"^\s*[-*]\s", line):
            bullet_status = line_icon
        for m in ref_re.finditer(line):
            num = int(m.group(1))
            status = line_icon or bullet_status or "planned"
            if num not in item_status or RANK[status] > RANK[item_status[num]]:
                item_status[num] = status
    return [], [], item_status


# --------------------------------------------------------------------------- #
# git plumbing
# --------------------------------------------------------------------------- #
def git(args: List[str], repo_root: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo_root), check=check,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _list_claim_branches(repo_root: Path, prefix: str) -> List[str]:
    if not (repo_root / ".git").exists():
        return []
    try:
        out_local = git(["branch", "--format=%(refname:short)"], repo_root, check=False).stdout
        out_remote = git(["branch", "-r", "--format=%(refname:short)"], repo_root, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names: List[str] = []
    for line in (out_local + out_remote).splitlines():
        name = line.strip()
        short = name.split("/", 1)[1] if name.startswith("origin/") else name
        if short.startswith(prefix):
            names.append(short)
    return sorted(set(names))


# --------------------------------------------------------------------------- #
# command handlers
# --------------------------------------------------------------------------- #
def cmd_check(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    errors, warnings = run_checks(repo_root, config)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"aide check: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 1
    print(f"aide check: OK ({len(warnings)} warning(s))")
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    if args.action != "set":
        print("usage: aide progress set NNN <in-progress|done>", file=sys.stderr)
        return 2
    status_map = {"in-progress": "in-progress", "done": "complete"}
    if args.status not in status_map:
        print("status must be 'in-progress' or 'done'", file=sys.stderr)
        return 2
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    progress_path = docs_dir(repo_root, config) / "progress.md"
    if not progress_path.is_file():
        print(f"error: {progress_path} not found", file=sys.stderr)
        return 1
    text = progress_path.read_text(encoding="utf-8")
    updated = set_item_status(text, args.number, status_map[args.status])
    if updated == text:
        print(f"item {args.number:03d}: no change (already >= {args.status})")
    else:
        progress_path.write_text(updated, encoding="utf-8")
        print(f"item {args.number:03d}: set to {args.status}")
    if not args.no_commit and (repo_root / ".git").exists():
        _commit_progress(repo_root, config, args.number, args.status)
    return 0


def _commit_progress(repo_root: Path, config, number: int, status: str) -> None:
    main = str(config["git"].get("main_branch", "main"))
    git(["pull", "--rebase"], repo_root, check=False)
    rel = str(config["project"].get("docs_dir", "docs/aide")) + "/progress.md"
    git(["add", rel], repo_root, check=False)
    res = git(["commit", "-m", f"progress(aide): item {number:03d} -> {status}"], repo_root, check=False)
    if res.returncode != 0 and "nothing to commit" not in (res.stdout + res.stderr):
        print(res.stderr.strip(), file=sys.stderr)


def cmd_queue(args: argparse.Namespace) -> int:
    if args.action != "tidy":
        print("usage: aide queue tidy NNN", file=sys.stderr)
        return 2
    import datetime as _dt
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    qdir = docs_dir(repo_root, config) / "queue"
    target = qdir / f"queue-{args.number:03d}.md"
    if not target.is_file():
        print(f"error: {target} not found", file=sys.stderr)
        return 1
    # Supersede by the highest-numbered queue after this one.
    later = sorted(
        int(p.stem.split("-")[1]) for p in qdir.glob("queue-*.md")
        if p.stem.split("-")[1].isdigit() and int(p.stem.split("-")[1]) > args.number
    )
    superseded_by = later[-1] if later else args.number + 1
    date = args.date or _dt.date.today().isoformat()
    text = target.read_text(encoding="utf-8")
    target.write_text(tidy_queue_text(text, superseded_by, date), encoding="utf-8")
    print(f"queue-{args.number:03d}: marked completed (superseded by queue-{superseded_by:03d})")
    return 0


# --------------------------------------------------------------------------- #
# git layer — claim / merge / env
# --------------------------------------------------------------------------- #
def venv_python(repo_root: Path, config: Dict[str, Dict[str, object]]) -> Path:
    """Resolve the venv interpreter path (Windows Scripts vs. posix bin)."""
    venv = repo_root / str(config["python"].get("venv", ".venv"))
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def resolve_test_command(repo_root: Path, config: Dict[str, Dict[str, object]]) -> List[str]:
    """The configured test command, with a leading ``python`` bound to the venv."""
    raw = str(config["python"].get("test_command", "python -m pytest")).split()
    vpy = venv_python(repo_root, config)
    if raw and raw[0] == "python" and vpy.exists():
        return [str(vpy), *raw[1:]]
    return raw


def env_status(repo_root: Path, config: Dict[str, Dict[str, object]]) -> str:
    """Return 'ok', 'missing', or 'stale' for the project venv."""
    vpy = venv_python(repo_root, config)
    if not vpy.exists():
        return "missing"
    module = str(config["python"].get("import_check", "") or "").strip()
    if not module:
        return "ok"
    res = subprocess.run([str(vpy), "-c", f"import {module}"],
                         cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "ok" if res.returncode == 0 else "stale"


def cmd_env(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    status = env_status(repo_root, config)
    if status == "ok":
        print("aide env: OK (venv present, import succeeds)")
        return 0
    if not args.bootstrap:
        print(f"aide env: {status} — run 'python .aide/scripts/aide.py env --bootstrap' to build it")
        return 1
    venv = repo_root / str(config["python"].get("venv", ".venv"))
    bootstrap = str(config["python"].get("bootstrap", "pip install -e .[dev]")).split()
    print(f"aide env: bootstrapping {venv} …")
    subprocess.run([sys.executable, "-m", "venv", str(venv)], cwd=str(repo_root), check=True)
    vpy = venv_python(repo_root, config)
    cmd = [str(vpy), "-m", *bootstrap] if bootstrap and bootstrap[0] == "pip" else [str(vpy), *bootstrap]
    subprocess.run(cmd, cwd=str(repo_root), check=True)
    final = env_status(repo_root, config)
    print(f"aide env: bootstrap done ({final})")
    return 0 if final == "ok" else 1


def _slug(title: str, max_words: int = 5) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    return "-".join(words[:max_words]) or "item"


def _queue_titles(text: str) -> Dict[int, str]:
    titles: Dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"^###\s+Item\s+0*(\d+)\s*:\s*(.+?)\s*$", line)
        if m:
            titles[int(m.group(1))] = m.group(2)
    return titles


def _item_dependencies(repo_root: Path, config, number: int) -> List[int]:
    """Item numbers named in the spec's Dependencies section (best effort)."""
    idir = docs_dir(repo_root, config) / "items"
    if not idir.is_dir():
        return []
    specs = list(idir.glob(f"{number:03d}-*.md"))
    if not specs:
        return []
    text = specs[0].read_text(encoding="utf-8")
    m = re.search(r"^##\s+Dependencies\s*$(.*?)(^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    section = m.group(1) if m else ""
    deps = {int(x) for x in re.findall(r"\bItem[s]?\s+0*(\d+)", section)}
    deps.discard(number)
    return sorted(deps)


def _pick_item(repo_root: Path, config, queue_text: str,
               claim_branches: List[str]) -> Optional[Tuple[int, str]]:
    """First queue item that is planned, unclaimed, and unblocked. (number, title)."""
    _, _, item_status = _parse_item_status(
        (docs_dir(repo_root, config) / "progress.md").read_text(encoding="utf-8").splitlines()
    ) if (docs_dir(repo_root, config) / "progress.md").is_file() else ([], [], {})
    claimed_nums = set()
    for br in claim_branches:
        cm = re.search(r"/(\d+)-", br) or re.search(r"(\d+)", br.rsplit("/", 1)[-1])
        if cm:
            claimed_nums.add(int(cm.group(1)))
    titles = _queue_titles(queue_text)
    for num in queue_item_numbers(queue_text):
        if item_status.get(num, "planned") != "planned":
            continue
        if num in claimed_nums:
            continue
        deps = _item_dependencies(repo_root, config, num)
        if any(item_status.get(d, "planned") in ("planned", "in-progress") for d in deps):
            continue
        return num, titles.get(num, f"item {num}")
    return None


def _live_queue_text(repo_root: Path, config, queue_number: Optional[int]) -> Optional[str]:
    qdir = docs_dir(repo_root, config) / "queue"
    if queue_number is not None:
        path = qdir / f"queue-{queue_number:03d}.md"
        return path.read_text(encoding="utf-8") if path.is_file() else None
    if not qdir.is_dir():
        return None
    for path in sorted(qdir.glob("queue-*.md"), reverse=True):
        text = path.read_text(encoding="utf-8")
        if is_live_queue(text):
            return text
    return None


def cmd_claim(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    if mode != "local":
        git(["fetch", "--all", "--prune"], repo_root, check=False)
    queue_text = _live_queue_text(repo_root, config, args.queue)
    if queue_text is None:
        print("aide claim: no Live queue found", file=sys.stderr)
        return 1
    branches = _list_claim_branches(repo_root, prefix)
    pick = _pick_item(repo_root, config, queue_text, branches)
    if pick is None:
        print("none left")
        return 0
    number, title = pick
    branch = f"{prefix}{number:03d}-{_slug(title)}"
    if args.dry_run:
        print(f"would claim item {number:03d} -> {branch} ({title})")
        return 0
    git(["switch", "-c", branch], repo_root)
    if mode != "local":
        git(["push", "-u", "origin", branch], repo_root)
    print(f"claimed item {number:03d}: {branch} — {title}")
    return 0


def _find_claim_branch(repo_root: Path, prefix: str, number: int) -> Optional[str]:
    for br in _list_claim_branches(repo_root, prefix):
        cm = re.search(r"/(\d+)-", br) or re.search(r"(\d+)", br.rsplit("/", 1)[-1])
        if cm and int(cm.group(1)) == number:
            return br
    return None


def cmd_merge(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    main = str(config["git"].get("main_branch", "main"))
    branch = args.branch or _find_claim_branch(repo_root, prefix, args.number)
    if not branch:
        print(f"aide merge: no claim branch found for item {args.number:03d}", file=sys.stderr)
        return 1

    if mode == "pr":
        git(["push", "-u", "origin", branch], repo_root)
        print(f"aide merge (pr mode): pushed {branch}. Open a PR to land it "
              f"(e.g. 'gh pr create'); merge is left to the human review gate.")
        return 0

    git(["switch", main], repo_root)
    if mode != "local":
        git(["pull", "--rebase"], repo_root, check=False)
    merge_res = git(["merge", "--no-edit", branch], repo_root, check=False)
    if merge_res.returncode != 0:
        print(f"aide merge: merge of {branch} failed:\n{merge_res.stdout}{merge_res.stderr}", file=sys.stderr)
        return 1
    if mode != "local":
        git(["push"], repo_root, check=False)

    if not args.no_test:
        cmd = resolve_test_command(repo_root, config)
        test_res = subprocess.run(cmd, cwd=str(repo_root))
        if test_res.returncode != 0:
            print(f"aide merge: merged {branch} but the post-merge test run FAILED — investigate", file=sys.stderr)
            return 1

    # Clean up the merged claim branch (safe -d; refuses if not merged).
    git(["branch", "-d", branch], repo_root, check=False)
    if mode != "local":
        git(["push", "origin", "--delete", branch], repo_root, check=False)
    print(f"aide merge: item {args.number:03d} merged to {main} and claim branch {branch} deleted")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aide", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=None, help="repo root (default: search up for aide.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="consistency gate over docs/aide")
    p_check.set_defaults(func=cmd_check)

    p_prog = sub.add_parser("progress", help="edit progress.md status")
    p_prog.add_argument("action", choices=["set"])
    p_prog.add_argument("number", type=int)
    p_prog.add_argument("status", help="in-progress | done")
    p_prog.add_argument("--no-commit", action="store_true", help="edit only, do not git commit")
    p_prog.set_defaults(func=cmd_progress)

    p_queue = sub.add_parser("queue", help="queue maintenance")
    p_queue.add_argument("action", choices=["tidy"])
    p_queue.add_argument("number", type=int)
    p_queue.add_argument("--date", default=None, help="override the supersede date (YYYY-MM-DD)")
    p_queue.set_defaults(func=cmd_queue)

    register_git_subcommands(sub)  # claim / merge / env (git layer)
    return parser


def register_git_subcommands(sub) -> None:
    """Attach the claim / merge / env subparsers (git layer)."""
    p_claim = sub.add_parser("claim", help="pick + claim the next unclaimed 📋 item")
    p_claim.add_argument("--queue", type=int, default=None, help="queue number (default: the Live queue)")
    p_claim.add_argument("--dry-run", action="store_true", help="print the pick, do not create/push a branch")
    p_claim.set_defaults(func=cmd_claim)

    p_merge = sub.add_parser("merge", help="merge a validated item per git.mode")
    p_merge.add_argument("number", type=int)
    p_merge.add_argument("branch", nargs="?", default=None, help="claim branch (default: found from number)")
    p_merge.add_argument("--no-test", action="store_true", help="skip the post-merge test run")
    p_merge.set_defaults(func=cmd_merge)

    p_env = sub.add_parser("env", help="venv existence / import check + bootstrap")
    p_env.add_argument("--bootstrap", action="store_true", help="create + populate the venv if missing/stale")
    p_env.set_defaults(func=cmd_env)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
