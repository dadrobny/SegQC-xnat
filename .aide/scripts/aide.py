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
    python .aide/scripts/aide.py sync [--item NNN]     # preflight: fetch, clean-tree check, right branch
    python .aide/scripts/aide.py gc [--merged] [--yes] # delete claim branches whose work landed
    python .aide/scripts/aide.py status                # one-call roadmap-state report

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
# A stage header's status icon is the TRAILING icon only (the "— <icon>" tail);
# an icon inside the title text is plain text.
_TRAILING_ICON_RE = re.compile(r"(" + _ICON_ALT + r")\s*$")


# Every file this CLI reads is project-owned and hand-editable — aide.toml and the
# docs/aide/ living documents. Windows editors (Notepad, PowerShell's Out-File,
# "Save as UTF-8" in several IDEs) prepend a BOM, and a leading U+FEFF breaks
# first-line parsing *silently*: on the 3.9 fallback parser a BOM'd aide.toml loses
# only its FIRST table, because "^\[table\]$" fails on that one line while every
# later table still matches. [project] vanishes (source_dir back to its default)
# while [git] is honoured — a half-correct config, no error, every command
# reporting success. On 3.11 the same file raises an uncaught TOMLDecodeError.
# "utf-8-sig" strips a BOM when present and is byte-identical to "utf-8" when
# absent, so it is the correct default for anything a human may have touched.
_ENCODING = "utf-8-sig"


#: The accepted item-reference forms, as ONE definition (see conventions.md §1):
#:   *(Item 006)*            a single item
#:   *(Items 006, 044)*      a list — what create-queue tells authors to write
#:   *(Items 089/090)*       a list, slash-separated
#:   *(Items 071–075)*       an inclusive range, hyphen or en-dash
#: Everything that asks "does this line reference item NNN" goes through
#: _referenced_item_numbers, so the answer cannot differ between callers. It did
#: once: the status parse read only the FIRST number of a list, while the
#: progress-set matcher read any number literally present. Items after the first
#: were then orphaned — planned forever on a ✅ bullet, holding their queue open
#: and (since the live queue is the lowest-numbered open one) stranding
#: `aide claim` on a finished queue, while `aide progress set` acted on them
#: happily.
_ITEM_REF_GROUP_RE = re.compile(r"[Ii]tems?\s+(0*\d+(?:\s*[,/–-]\s*0*\d+)*)")
_ITEM_REF_SPLIT_RE = re.compile(r"\s*[,/]\s*")
_ITEM_REF_RANGE_RE = re.compile(r"^0*(\d+)\s*[–-]\s*0*(\d+)$")

#: An inclusive range wider than this is treated as a typo and contributes only
#: its endpoints, so a stray "Items 6-9999" cannot invent thousands of items.
_ITEM_RANGE_MAX_SPAN = 50


def _referenced_item_numbers(text: str) -> List[int]:
    """Every item number referenced in ``text``, ranges expanded inclusively."""
    nums: List[int] = []
    for group in _ITEM_REF_GROUP_RE.finditer(text):
        for part in _ITEM_REF_SPLIT_RE.split(group.group(1)):
            part = part.strip()
            if not part:
                continue
            rng = _ITEM_REF_RANGE_RE.match(part)
            if rng is None:
                nums.append(int(part))
                continue
            lo, hi = int(rng.group(1)), int(rng.group(2))
            if lo <= hi <= lo + _ITEM_RANGE_MAX_SPAN:
                nums.extend(range(lo, hi + 1))
            else:
                nums.extend((lo, hi))
    return nums


def _references_item(text: str, num: int) -> bool:
    """Does ``text`` reference item ``num`` in any accepted form?"""
    return num in _referenced_item_numbers(text)


# --------------------------------------------------------------------------- #
# TOML config (tomllib on 3.11+, tiny fallback for the aide.toml subset on 3.9)
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG: Dict[str, Dict[str, object]] = {
    "project": {"name": "project", "source_dir": "src", "tests_dir": "tests", "docs_dir": "docs/aide"},
    "python": {"venv": ".venv", "bootstrap": "pip install -e .[dev]",
               "test_command": "python -m pytest", "import_check": ""},
    "git": {"mode": "auto-merge", "main_branch": "main", "branch_prefix": "aide/"},
    "loop": {"queue_cap": 10, "validation_rounds": 3, "clarify": "assume",
             "claim_scope": "live-queue"},
    "framework": {"repo": ""},
    # [validation] — named environment profiles for stage-validation items:
    # <name> = <python expression>, true iff the environment provides the
    # capability (e.g. gpu = "__import__('torch').cuda.is_available()").
    "validation": {},
}


# Escape sequences this reader decodes inside a basic (double-quoted) string. TOML
# also defines \b \t \n \f \r \uXXXX \UXXXXXXXX; rather than half-implement them and
# quietly disagree with tomllib, an unlisted escape is a ConfigError (see below).
_BASIC_ESCAPES = {'"': '"', "\\": "\\"}


def _read_quoted_value(key: str, stripped: str, lineno: int) -> str:
    """Decode the quoted string at the start of ``stripped``, or raise ``ConfigError``.

    Finding where a string ENDS and extracting what it CONTAINS are the same scan, so
    they live in one function. Splitting them is what produced the bug this replaces:
    the validator walked the value escape-aware while the extractor used a naive
    ``split(quote, 1)[0]``, so ``msg = "he said \\"hi\\""`` passed validation and was
    then silently truncated to ``he said \\``.

    Single-quoted strings are TOML *literal* strings: no escapes, backslash is itself.
    Double-quoted are *basic* strings, where a backslash escapes the next character.
    """
    quote = stripped[0]
    out: List[str] = []
    i = 1
    while i < len(stripped):
        ch = stripped[i]
        if quote == '"' and ch == "\\":
            nxt = stripped[i + 1] if i + 1 < len(stripped) else ""
            if not nxt:
                raise ConfigError(
                    f"line {lineno}: unterminated escape in the value for key {key!r} — "
                    "a backslash at the end of a basic string escapes nothing"
                )
            if nxt not in _BASIC_ESCAPES:
                raise ConfigError(
                    f"line {lineno}: unsupported escape '\\{nxt}' in the value for "
                    f"key {key!r} — this minimal reader decodes only \\\\ and \\\"; "
                    f"use a single-quoted 'literal string' (backslashes are literal "
                    f"there) or forward slashes"
                )
            out.append(_BASIC_ESCAPES[nxt])
            i += 2
            continue
        if ch == quote:
            tail = stripped[i + 1:].lstrip()
            if tail and not tail.startswith("#"):
                raise ConfigError(
                    f"line {lineno}: trailing characters after the quoted value for "
                    f"key {key!r}: {tail!r}"
                )
            return "".join(out)
        out.append(ch)
        i += 1

    raise ConfigError(
        f"line {lineno}: unterminated string for key {key!r} — "
        f"the value opens with {quote} but never closes it"
    )


class ConfigError(Exception):
    """``aide.toml`` cannot be trusted — malformed, so its facts are unknowable.

    Raised instead of guessing. Every project fact the framework acts on comes from
    that file, so silently falling back to defaults would scope the builder at the
    wrong directory, pick the wrong git mode, or run the wrong test command while
    reporting success. ``main`` catches this and prints it as a plain error.
    """


def _parse_toml(text: str) -> Dict[str, Dict[str, object]]:
    """Minimal TOML reader for the flat ``[table] key = value`` shape of aide.toml.

    Supports string/int/float/bool scalars and ``#`` comments. Used only when the
    stdlib ``tomllib`` (Python 3.11+) is unavailable, so the CLI and its tests run
    on the project's 3.9 venv too.

    Deliberately lenient about what it *ignores* (unknown lines, blank tables) but
    strict about what it would otherwise *misread*, because a wrong-but-plausible
    value is worse than a refusal: an unterminated quoted string used to yield the
    truncated text, so a typo became a believable answer on 3.9 while 3.11's tomllib
    rejected the same file. Quoted values are decoded by ``_read_quoted_value``,
    which raises ``ConfigError`` rather than guess — so both parser paths agree on
    which files are readable.
    """
    data: Dict[str, Dict[str, object]] = {}
    table: Optional[Dict[str, object]] = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
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
        value = value.strip()
        # A quoted value owns everything up to its closing quote — a '#' inside it is
        # data, not a comment — so it is scanned before any comment stripping. Only
        # an UNquoted value is truncated at '#'.
        if value and value[0] in "\"'":
            table[key] = _read_quoted_value(key, value, lineno)
            continue
        token = value.split("#", 1)[0].strip()
        if not token:
            raise ConfigError(f"line {lineno}: missing value for key {key!r}")
        if token.lower() in ("true", "false"):
            table[key] = token.lower() == "true"
        else:
            try:
                table[key] = int(token)
            except ValueError:
                try:
                    table[key] = float(token)
                except ValueError:
                    table[key] = token
    return data


def _config_error(path: Path, what: str, exc: object) -> "ConfigError":
    """One phrasing for every way ``aide.toml`` can fail, so they cannot drift.

    ``what`` distinguishes the causes a reader would act on differently: a file that
    ``is malformed`` needs an edit, one that ``cannot be read`` needs permissions or
    disk attention. The rest — naming the path, and why defaults are not an
    acceptable fallback — is identical in every case.
    """
    return ConfigError(
        f"{path} {what}: {exc}\n"
        f"  aide.toml states this project's facts (source_dir, git mode, test "
        f"command); refusing to continue with defaults that would be silently wrong."
    )


def load_config(repo_root: Path) -> Dict[str, Dict[str, object]]:
    """Load ``aide.toml`` merged over defaults.

    A *missing* file is fine — defaults apply, which is what an unconfigured repo
    means. A *malformed* file is not: it states project facts that cannot be read,
    so this raises ``ConfigError`` naming the file rather than falling back to
    defaults that would silently be wrong.
    """
    merged = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    path = repo_root / "aide.toml"
    if path.is_file():
        try:
            text = path.read_text(encoding=_ENCODING)
        except UnicodeDecodeError as exc:
            raise _config_error(path, "is malformed", exc) from exc
        except OSError as exc:
            # Present but unreadable (permissions, a device error, a dangling
            # link). The file may be perfectly well-formed — say so accurately
            # rather than sending the reader to hunt for a syntax mistake.
            raise _config_error(path, "cannot be read", exc) from exc
        try:
            import tomllib  # type: ignore
        except ModuleNotFoundError:
            detail_source = _parse_toml
        else:
            # tomllib.TOMLDecodeError subclasses ValueError; catching ValueError
            # keeps this working if that relationship ever changes.
            detail_source = tomllib.loads
        try:
            parsed = detail_source(text)
        except (ConfigError, ValueError) as exc:
            # Both parsers report line/column but neither knows the path, and the
            # path is the one thing a reader needs to go fix it.
            raise _config_error(path, "is malformed", exc) from exc
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


def _header_status(line: str) -> Optional[str]:
    """A stage header's status — its trailing icon only."""
    m = _TRAILING_ICON_RE.search(line)
    return ICON_TO_STATUS[m.group(1)] if m else None


def _split_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _structural_status(line: str) -> Optional[str]:
    """Status conveyed by a line's STRUCTURAL icon position only.

    Structural positions (the format contract, conventions.md §1): the leading
    icon of a deliverable bullet, a table row's Status (last) cell, and a stage
    header's trailing icon. An icon anywhere else on a line is plain text and
    is never read as status — prose stays free of the icon vocabulary.
    """
    m = _BULLET_RE.match(line)
    if m:
        return ICON_TO_STATUS[m.group("icon")]
    if line.strip().startswith("|"):
        cells = _split_row(line)
        return _icon_status(cells[-1]) if cells else None
    if _STAGE_HEADER_RE.match(line):
        return _header_status(line)
    return None


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


def _sub_status_cell(line: str, status: str) -> str:
    """Replace the icon in a table row's Status (last) cell only.

    Icons in other cells (a title, an objective description) are plain text and
    must survive the edit untouched.
    """
    head, sep, tail = line.rpartition("|")
    if sep:
        body, sep2, cell = head.rpartition("|")
        if sep2:
            return body + "|" + _ICON_RE.sub(STATUS_TO_ICON[status], cell, count=1) + "|" + tail
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
                lines[i] = _sub_status_cell(line, status)
            return


def _set_stage_header(lines: List[str], start: int, status: str) -> None:
    line = lines[start]
    current = _header_status(line)
    if current in ("deferred", "excluded"):
        return
    if current is None:
        lines[start] = line.rstrip() + f" — {STATUS_TO_ICON[status]}"
    elif RANK[status] >= RANK[current]:
        lines[start] = _TRAILING_ICON_RE.sub(STATUS_TO_ICON[status], line)


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
                lines[i] = _sub_status_cell(line, derived)


def _spec_stage_and_title(repo_root: Path, config, number: int) -> Tuple[Optional[str], Optional[str]]:
    """(stage, title) from the item's spec header, best effort."""
    idir = docs_dir(repo_root, config) / "items"
    specs = sorted(idir.glob(f"{number:03d}-*.md")) if idir.is_dir() else []
    if not specs:
        return None, None
    text = specs[0].read_text(encoding=_ENCODING)
    tm = re.search(r"^#\s+Item\s+0*" + str(number) + r"\s*[—–-]\s*(.+?)\s*$", text, re.MULTILINE)
    sm = re.search(r"\*\*Stage:\*\*\s*(\d+)", text)
    return (sm.group(1) if sm else None), (tm.group(1) if tm else None)


def insert_item_reference(text: str, number: int, stage: str, title: str) -> Optional[str]:
    """Append a planned deliverable bullet for item ``number`` to the given
    stage's Deliverables block (used when a queue back-fill was missed, so
    ``progress set`` can self-heal instead of hard-erroring). Returns the
    updated text, or None when the stage section / Deliverables block is
    missing — that stays a loud error."""
    lines = text.splitlines()
    for start, end, snum in stage_sections(lines):
        if snum != str(stage):
            continue
        insert_at = None
        for i in range(start, end):
            if _BULLET_RE.match(lines[i]):
                insert_at = i + 1
            elif insert_at is None and lines[i].strip().startswith("**Deliverables"):
                insert_at = i + 1
        if insert_at is None:
            return None
        lines.insert(insert_at, f"- 📋 {title}. *(Item {number:03d})*")
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return None


def set_item_status(text: str, num: int, status: str) -> str:
    """Flip item NNN's deliverable bullet(s) to ``status`` and roll stages up.

    ``status`` is ``in-progress`` or ``complete``. Ticks acceptance boxes and
    updates summary/header/objective rows only for stages that fully complete.
    Never downgrades an existing status (additive log).
    """
    lines = text.splitlines()
    # Flip the owning bullet's icon for every line that references this item.
    bullet_line: Optional[int] = None
    for i, line in enumerate(lines):
        if _BULLET_RE.match(line) or re.match(r"^\s*[-*]\s", line):
            if _BULLET_RE.match(line):
                bullet_line = i
        if _references_item(line, num):
            target = bullet_line if bullet_line is not None and _BULLET_RE.match(lines[bullet_line]) else i
            tm = _BULLET_RE.match(lines[target])
            if tm:
                current = ICON_TO_STATUS[tm.group("icon")]
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


def queue_is_open(text: str, item_status: Dict[int, str]) -> bool:
    """Derived queue state: open iff any of its items is 📋/🚧 per progress.md.

    Queue state is DERIVED, never declared — a ``> **Status:**`` line in a
    queue file is decorative (kept for human readers), and the "live" queue is
    simply the lowest-numbered open one. An item progress.md doesn't know yet
    counts as planned, so a freshly wired queue is open.
    """
    return any(item_status.get(n, "planned") in ("planned", "in-progress")
               for n in queue_item_numbers(text))


def _progress_item_status(repo_root: Path, config) -> Dict[int, str]:
    path = docs_dir(repo_root, config) / "progress.md"
    if not path.is_file():
        return {}
    _, _, item_status = _parse_item_status(path.read_text(encoding=_ENCODING).splitlines())
    return item_status


def _queue_paths(qdir: Path) -> List[Path]:
    return sorted(qdir.glob("queue-*.md"))


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
_TEMPLATE_SLOT_RE = re.compile(r"\{\{[^}]*\}\}")


def template_residue_errors(ddir: Path) -> List[str]:
    """Flag unfilled ``{{slot}}`` template markers left in generated documents.

    Templates use ``{{slot-name}}`` for values an author must fill in (see
    ``.aide/templates/``); a real ``docs/aide/`` document should never contain
    one. Scanning for the literal ``{{`` is deterministic and cheap — the
    format contract's answer to "did someone forget to fill in the template".
    """
    errors: List[str] = []
    if not ddir.is_dir():
        return errors
    for path in sorted(ddir.rglob("*.md")):
        text = path.read_text(encoding=_ENCODING)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _TEMPLATE_SLOT_RE.finditer(line):
                errors.append(
                    f"{path.relative_to(ddir)}:{lineno}: unfilled template slot {m.group(0)}"
                )
    return errors


_INSIGHT_TYPES = ("knowledge", "defect", "gap", "automation", "framework")
# "- [ ] <type> — <one line> *(item NNN, YYYY-MM-DD)*"; the item ref is optional
# and ticked entries append " → <where it landed>" after the provenance.
_INSIGHT_RE = re.compile(
    r"^- \[[ xX]\] (?:" + "|".join(_INSIGHT_TYPES) + r") [—–-] .+\*\((?:[Ii]tem \d+, )?\d{4}-\d{2}-\d{2}\)\*"
)


def insight_warnings(ddir: Path) -> List[str]:
    """Shape-check ``insights.md`` (the compound-engineering inbox), if present.

    Non-blocking: capture must stay cheap, so a malformed entry is a warning,
    never an error. Every ``- `` bullet in the file is expected to be an entry.
    """
    path = ddir / "insights.md"
    if not path.is_file():
        return []
    out: List[str] = []
    for lineno, line in enumerate(path.read_text(encoding=_ENCODING).splitlines(), start=1):
        if not line.startswith("- "):
            continue
        if not _INSIGHT_RE.match(line):
            out.append(
                f"insights.md:{lineno}: entry does not match "
                f"'- [ ] <{'|'.join(_INSIGHT_TYPES)}> — <one line> "
                f"*(item NNN, YYYY-MM-DD)*'"
            )
    return out


def _stray_icons_in_line(line: str) -> List[str]:
    """Status icons on this line that sit OUTSIDE any structural position."""
    icons = list(_ICON_RE.finditer(line))
    if not icons:
        return []
    if _QUEUE_STATUS_RE.match(line):
        return []  # "> **Status:** …" lines legitimately carry an icon
    if line.strip().startswith("|"):
        return []  # table rows: parsers read specific cells only, never prose
    allowed: Optional[Tuple[int, int]] = None
    m = _BULLET_RE.match(line)
    if m:
        allowed = m.span("icon")
    elif re.match(r"^#{1,6}\s", line):  # any heading level may carry a trailing icon
        t = _TRAILING_ICON_RE.search(line)
        if t:
            allowed = t.span(1)
    return [i.group(0) for i in icons if i.span() != allowed]


def stray_icon_warnings(ddir: Path) -> List[str]:
    """Warn on status icons outside structural positions in the status-bearing
    documents (``progress.md`` and queue files).

    The parsers only ever read icons at structural positions (conventions.md
    §1), so a stray icon is never *misread* — this lint surfaces near-misses so
    the status documents stay unambiguous to human readers too. Other documents
    (vision, roadmap, item specs) are not scanned: nothing parses icons there,
    so their prose is free.
    """
    out: List[str] = []
    paths: List[Path] = []
    progress = ddir / "progress.md"
    if progress.is_file():
        paths.append(progress)
    qdir = ddir / "queue"
    if qdir.is_dir():
        paths.extend(sorted(qdir.glob("queue-*.md")))
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding=_ENCODING).splitlines(), start=1):
            for icon in _stray_icons_in_line(line):
                out.append(
                    f"{path.relative_to(ddir)}:{lineno}: status icon {icon} outside a "
                    f"structural status position (parsers treat it as plain text; move "
                    f"or remove it if status was intended)"
                )
    return out


def run_checks(repo_root: Path, config: Dict[str, Dict[str, object]],
               branches: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)``. Empty errors == pass."""
    errors: List[str] = []
    warnings: List[str] = []
    ddir = docs_dir(repo_root, config)
    progress_path = ddir / "progress.md"

    errors.extend(template_residue_errors(ddir))
    warnings.extend(stray_icon_warnings(ddir))
    warnings.extend(insight_warnings(ddir))

    if not progress_path.is_file():
        return [f"missing {progress_path}"], warnings
    text = progress_path.read_text(encoding=_ENCODING)
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
        header_status = _header_status(lines[start])
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

    # Queues: state is DERIVED from progress.md (open = any 📋/🚧 item); a
    # declared "> **Status:**" line is decorative — warn only when it lies.
    qdir = ddir / "queue"
    seen: Dict[int, str] = {}
    if qdir.is_dir():
        _, _, istat = _parse_item_status(lines)
        for qpath in _queue_paths(qdir):
            qtext = qpath.read_text(encoding=_ENCODING)
            derived_open = queue_is_open(qtext, istat)
            declared = queue_status(qtext)
            if declared:
                declared_live = declared.lower().startswith("live")
                if declared_live and not derived_open:
                    warnings.append(
                        f"{qpath.name}: declares 'Live' but every item is finished — "
                        f"state is derived from progress.md; run 'aide queue tidy' "
                        f"or drop the decorative Status line")
                elif not declared_live and derived_open:
                    warnings.append(
                        f"{qpath.name}: marked completed but still has open items "
                        f"in progress.md")
            for n in queue_item_numbers(qtext):
                if n in seen and seen[n] != qpath.name:
                    errors.append(f"item {n:03d} appears in both {seen[n]} and {qpath.name}")
                seen[n] = qpath.name

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
    for line in lines:
        hm = _STAGE_HEADER_RE.match(line)
        if hm:
            current_stage = hm.group(1)
            bullet_status = None
            continue
        line_icon = _structural_status(line)
        if re.match(r"^\s*[-*]\s", line):
            bullet_status = line_icon
        for num in _referenced_item_numbers(line):
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
    text = progress_path.read_text(encoding=_ENCODING)
    original = text
    # An item is only trackable if some deliverable bullet references it (a
    # missing "*(Item NNN)*" would make set_item_status a silent no-op). When
    # the queue back-fill was missed, self-heal deterministically from the item
    # spec's own Stage/title header; only when that context is missing too does
    # this stay a loud, blocking error.
    if not _references_item(text, args.number):
        stage, title = _spec_stage_and_title(repo_root, config, args.number)
        healed = insert_item_reference(text, args.number, stage, title) if stage and title else None
        if healed is None:
            print(
                f"item {args.number:03d}: ERROR — no deliverable in progress.md "
                f"references 'Item {args.number:03d}', and no item spec with a "
                f"Stage header was found to insert one from; status NOT "
                f"recorded. Add the reference to the owning stage's deliverable "
                f"bullet (e.g. '- 📋 <deliverable>. *(Item {args.number:03d})*'), "
                f"then re-run.",
                file=sys.stderr,
            )
            return 1
        text = healed
        print(f"item {args.number:03d}: back-filled missing deliverable reference "
              f"under Stage {stage} (from the item spec)")
    updated = set_item_status(text, args.number, status_map[args.status])
    if updated == original:
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
    text = target.read_text(encoding=_ENCODING)
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

    if getattr(args, "profile", None):
        # Evaluate a named [validation] environment profile deterministically.
        profiles = {k: str(v) for k, v in (config.get("validation") or {}).items()}
        expr = profiles.get(args.profile)
        if expr is None:
            known = ", ".join(sorted(profiles)) or "(none defined)"
            print(f"aide env: unknown profile '{args.profile}' — [validation] defines: {known}",
                  file=sys.stderr)
            return 2
        vpy = venv_python(repo_root, config)
        interpreter = str(vpy) if vpy.exists() else sys.executable
        code = f"import sys\nsys.exit(0 if ({expr}) else 1)"
        res = subprocess.run([interpreter, "-c", code], cwd=str(repo_root),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            print(f"aide env: profile '{args.profile}' satisfied")
            return 0
        detail = (res.stderr or "").strip().splitlines()
        suffix = f" ({detail[-1]})" if detail else ""
        print(f"aide env: profile '{args.profile}' NOT satisfied{suffix} — "
              f"validation gated on it must record '❓ Unverified', never a silent pass")
        return 1

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
    text = specs[0].read_text(encoding=_ENCODING)
    m = re.search(r"^##\s+Dependencies\s*$(.*?)(^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    section = m.group(1) if m else ""
    deps = {int(x) for x in re.findall(r"\bItem[s]?\s+0*(\d+)", section)}
    deps.discard(number)
    return sorted(deps)


def _pick_item(repo_root: Path, config, queue_text: str,
               claim_branches: List[str]) -> Optional[Tuple[int, str]]:
    """First queue item that is planned, unclaimed, and unblocked. (number, title)."""
    _, _, item_status = _parse_item_status(
        (docs_dir(repo_root, config) / "progress.md").read_text(encoding=_ENCODING).splitlines()
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


def _open_queue_texts(repo_root: Path, config) -> List[str]:
    """Texts of the open queues, lowest-numbered first (derived state)."""
    qdir = docs_dir(repo_root, config) / "queue"
    if not qdir.is_dir():
        return []
    item_status = _progress_item_status(repo_root, config)
    out: List[str] = []
    for path in _queue_paths(qdir):
        text = path.read_text(encoding=_ENCODING)
        if queue_is_open(text, item_status):
            out.append(text)
    return out


def _live_queue_text(repo_root: Path, config, queue_number: Optional[int]) -> Optional[str]:
    """The queue to work: an explicit number, else the lowest-numbered OPEN
    queue (state derived from progress.md). Falls back to the highest queue
    declaring ``Status: Live`` only when progress.md is missing (legacy)."""
    qdir = docs_dir(repo_root, config) / "queue"
    if queue_number is not None:
        path = qdir / f"queue-{queue_number:03d}.md"
        return path.read_text(encoding=_ENCODING) if path.is_file() else None
    if not qdir.is_dir():
        return None
    if (docs_dir(repo_root, config) / "progress.md").is_file():
        open_texts = _open_queue_texts(repo_root, config)
        return open_texts[0] if open_texts else None
    for path in sorted(_queue_paths(qdir), reverse=True):
        text = path.read_text(encoding=_ENCODING)
        if is_live_queue(text):
            return text
    return None


def cmd_claim(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    scope = str(config["loop"].get("claim_scope", "live-queue"))
    if mode != "local":
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    if args.queue is None and scope == "all-open":
        # Cross-queue claiming (opt-in): scan every open queue in number order.
        candidates = _open_queue_texts(repo_root, config)
    else:
        queue_text = _live_queue_text(repo_root, config, args.queue)
        candidates = [queue_text] if queue_text is not None else []
    if not candidates:
        print("aide claim: no open queue found", file=sys.stderr)
        return 1
    branches = _list_claim_branches(repo_root, prefix)
    pick = None
    for queue_text in candidates:
        pick = _pick_item(repo_root, config, queue_text, branches)
        if pick is not None:
            break
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

    # Clean up the merged claim branch — and VERIFY it, never assume. `-d` can
    # refuse even though the work landed (e.g. `pull --rebase` rewrote main so
    # the branch tip is no longer an ancestor); this process just merged the
    # branch, so escalating to -D is safe.
    del_res = git(["branch", "-d", branch], repo_root, check=False)
    if del_res.returncode != 0:
        del_res = git(["branch", "-D", branch], repo_root, check=False)
    local_gone = branch not in _local_branches(repo_root)
    remote_gone = True
    if mode != "local":
        push_res = git(["push", "origin", "--delete", branch], repo_root, check=False)
        remote_gone = (push_res.returncode == 0
                       or "remote ref does not exist" in (push_res.stderr or ""))
    if local_gone and remote_gone:
        print(f"aide merge: item {args.number:03d} merged to {main} and claim branch {branch} deleted")
    else:
        where = [] if local_gone else ["local"]
        if not remote_gone:
            where.append("remote")
        print(f"aide merge: item {args.number:03d} merged to {main}, but the "
              f"{'/'.join(where)} claim branch {branch} could NOT be deleted:\n"
              f"{(del_res.stderr or '').strip()}\n"
              f"Run 'python .aide/scripts/aide.py gc' to sweep it up.", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# sync / gc — the scripted git workflow (no exploratory git needed)
# --------------------------------------------------------------------------- #
def _local_branches(repo_root: Path) -> List[str]:
    out = git(["branch", "--format=%(refname:short)"], repo_root, check=False).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def _remote_branches(repo_root: Path) -> List[str]:
    out = git(["branch", "-r", "--format=%(refname:short)"], repo_root, check=False).stdout
    names = []
    for l in out.splitlines():
        name = l.strip()
        if name.startswith("origin/") and "HEAD" not in name:
            names.append(name.split("/", 1)[1])
    return names


def _branch_item_number(branch: str) -> Optional[int]:
    m = re.search(r"/(\d+)-", branch) or re.search(r"(\d+)", branch.rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None


def _has_origin(repo_root: Path) -> bool:
    out = git(["remote"], repo_root, check=False).stdout
    return "origin" in out.split()


def cmd_sync(args: argparse.Namespace) -> int:
    """Deterministic preflight: fetch, verify a clean start point, land on the
    right branch. Replaces the exploratory ``git status``/``git branch``/
    ``git fetch`` sequence agents otherwise improvise before starting work.
    Exit 0 == safe to start; exit 1 prints the one reason work must not start.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    main = str(config["git"].get("main_branch", "main"))

    if mode != "local" and _has_origin(repo_root):
        res = git(["fetch", "--all", "--prune"], repo_root, check=False)
        if res.returncode != 0:
            print(f"aide sync: fetch failed — {res.stderr.strip()}", file=sys.stderr)
            return 1

    dirty = git(["status", "--porcelain"], repo_root, check=False).stdout.strip()
    if dirty:
        print("aide sync: working tree not clean — commit or stash before starting:",
              file=sys.stderr)
        print(dirty, file=sys.stderr)
        return 1

    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root, check=False).stdout.strip()

    # Bring main up to date when we're on it (safe fast-forward only).
    if branch == main and mode != "local" and _has_origin(repo_root):
        counts = git(["rev-list", "--left-right", "--count", f"{main}...origin/{main}"],
                     repo_root, check=False).stdout.split()
        if len(counts) == 2:
            ahead, behind = int(counts[0]), int(counts[1])
            if behind and not ahead:
                git(["merge", "--ff-only", f"origin/{main}"], repo_root, check=False)
                print(f"aide sync: fast-forwarded {main} ({behind} commit(s))")
            elif behind:
                print(f"aide sync: {main} has diverged from origin/{main} "
                      f"({ahead} ahead / {behind} behind) — reconcile first", file=sys.stderr)
                return 1

    if args.item is not None:
        claim = _find_claim_branch(repo_root, prefix, args.item)
        if not claim:
            print(f"aide sync: no claim branch for item {args.item:03d} — run "
                  f"'python .aide/scripts/aide.py claim' first", file=sys.stderr)
            return 1
        if branch != claim:
            res = git(["switch", claim], repo_root, check=False)
            if res.returncode != 0:
                print(f"aide sync: could not switch to {claim}:\n{res.stderr}", file=sys.stderr)
                return 1
            branch = claim
        if mode != "local" and _has_origin(repo_root) and claim in _remote_branches(repo_root):
            git(["pull", "--rebase", "origin", claim], repo_root, check=False)

    print(f"aide sync: OK — on '{branch}', tree clean"
          + ("" if mode == "local" else ", remotes fetched"))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """One-call roadmap-state report: branch + divergence, derived queue
    states, claim branches, and (best effort) open PRs — replacing the several
    manual git/gh round-trips a resuming orchestrator otherwise makes."""
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    main = str(config["git"].get("main_branch", "main"))

    if not args.no_fetch and mode != "local" and _has_origin(repo_root):
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root, check=False).stdout.strip()
    line = f"branch: {branch or '(unknown)'}"
    if mode != "local" and _has_origin(repo_root):
        counts = git(["rev-list", "--left-right", "--count", f"{main}...origin/{main}"],
                     repo_root, check=False).stdout.split()
        if len(counts) == 2:
            ahead, behind = counts
            line += f" · {main}: {ahead} ahead / {behind} behind origin/{main}"
    print(f"aide status — {repo_root.name}")
    print(f"  {line}")

    dirty = git(["status", "--porcelain"], repo_root, check=False).stdout.strip()
    print(f"  tree: {'dirty (' + str(len(dirty.splitlines())) + ' path(s))' if dirty else 'clean'}")

    item_status = _progress_item_status(repo_root, config)
    qdir = docs_dir(repo_root, config) / "queue"
    live_seen = False
    if qdir.is_dir() and _queue_paths(qdir):
        for path in _queue_paths(qdir):
            nums = queue_item_numbers(path.read_text(encoding=_ENCODING))
            open_nums = [n for n in nums
                         if item_status.get(n, "planned") in ("planned", "in-progress")]
            if open_nums:
                tag = " (live)" if not live_seen else ""
                live_seen = True
                listed = ", ".join(f"{n:03d}" for n in open_nums)
                print(f"  {path.name}: open{tag} — {len(open_nums)}/{len(nums)} items open ({listed})")
            else:
                print(f"  {path.name}: done")
    else:
        print("  queues: none")

    branches = _list_claim_branches(repo_root, prefix)
    if branches:
        for br in branches:
            num = _branch_item_number(br)
            st = item_status.get(num, "planned") if num is not None else "?"
            stale = " — STALE (item ✅; run 'aide gc')" if st == "complete" else ""
            print(f"  claim: {br} (item {num:03d}: {st}){stale}" if num is not None
                  else f"  claim: {br}")
    else:
        print("  claims: none")

    # Open PRs, best effort — informative only, silently skipped without `gh`.
    try:
        res = subprocess.run(["gh", "pr", "list", "--state", "open"],
                             cwd=str(repo_root), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, timeout=20)
        if res.returncode == 0:
            prs = res.stdout.strip()
            if prs:
                print("  open PRs:")
                for l in prs.splitlines():
                    print(f"    {l}")
            else:
                print("  open PRs: none")
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    """Delete claim branches whose work has landed (item ✅ in progress.md, or
    ``--merged`` branches already merged into main). Dry-run by default; pass
    ``--yes`` to delete. The one destructive verb in the CLI, so it is never
    implicit."""
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    main = str(config["git"].get("main_branch", "main"))

    if mode != "local" and _has_origin(repo_root):
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    progress_path = docs_dir(repo_root, config) / "progress.md"
    item_status: Dict[int, str] = {}
    if progress_path.is_file():
        _, _, item_status = _parse_item_status(
            progress_path.read_text(encoding=_ENCODING).splitlines())

    local = [b for b in _local_branches(repo_root) if b.startswith(prefix)]
    remote = [b for b in _remote_branches(repo_root) if b.startswith(prefix)]

    merged_local: List[str] = []
    if args.merged:
        out = git(["branch", "--merged", main, "--format=%(refname:short)"],
                  repo_root, check=False).stdout
        merged_local = [l.strip() for l in out.splitlines()
                        if l.strip().startswith(prefix)]

    targets: Dict[str, str] = {}  # branch -> reason
    for br in sorted(set(local) | set(remote)):
        num = _branch_item_number(br)
        if num is not None and item_status.get(num) == "complete":
            targets[br] = f"item {num:03d} is ✅"
        elif br in merged_local:
            targets[br] = f"merged into {main}"

    if not targets:
        print("aide gc: nothing to clean")
        return 0

    current = git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root, check=False).stdout.strip()
    for br, reason in targets.items():
        where = ("local+remote" if br in local and br in remote
                 else "local" if br in local else "remote")
        if not args.yes:
            print(f"would delete {br} ({where}; {reason})")
            continue
        if br == current:
            print(f"skipping {br}: currently checked out", file=sys.stderr)
            continue
        if br in local:
            # -D: a ✅/merged item's branch may have landed via squash/PR, so
            # git's ancestry-based -d safety check can refuse a branch whose
            # work is in fact on main.
            git(["branch", "-D", br], repo_root, check=False)
        if br in remote and mode != "local":
            git(["push", "origin", "--delete", br], repo_root, check=False)
        print(f"deleted {br} ({where}; {reason})")
    if not args.yes:
        print("aide gc: dry run — re-run with --yes to delete")
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
    p_claim.add_argument("--queue", type=int, default=None,
                         help="queue number (default: the lowest-numbered open queue)")
    p_claim.add_argument("--dry-run", action="store_true", help="print the pick, do not create/push a branch")
    p_claim.set_defaults(func=cmd_claim)

    p_merge = sub.add_parser("merge", help="merge a validated item per git.mode")
    p_merge.add_argument("number", type=int)
    p_merge.add_argument("branch", nargs="?", default=None, help="claim branch (default: found from number)")
    p_merge.add_argument("--no-test", action="store_true", help="skip the post-merge test run")
    p_merge.set_defaults(func=cmd_merge)

    p_env = sub.add_parser("env", help="venv existence / import check + bootstrap")
    p_env.add_argument("--bootstrap", action="store_true", help="create + populate the venv if missing/stale")
    p_env.add_argument("--profile", default=None,
                       help="evaluate a named [validation] environment profile (exit 0 iff satisfied)")
    p_env.set_defaults(func=cmd_env)

    p_sync = sub.add_parser("sync", help="preflight: fetch, verify clean tree, land on the right branch")
    p_sync.add_argument("--item", type=int, default=None,
                        help="verify/switch to this item's claim branch")
    p_sync.set_defaults(func=cmd_sync)

    p_gc = sub.add_parser("gc", help="delete claim branches whose work has landed (dry-run by default)")
    p_gc.add_argument("--merged", action="store_true",
                      help="also delete claim branches already merged into main")
    p_gc.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    p_gc.set_defaults(func=cmd_gc)

    p_status = sub.add_parser("status", help="one-call roadmap-state report (branch, queues, claims, PRs)")
    p_status.add_argument("--no-fetch", action="store_true", help="skip the fetch --all --prune preflight")
    p_status.set_defaults(func=cmd_status)


def main(argv: Optional[List[str]] = None) -> int:
    # Windows consoles often default to a non-UTF-8 codepage (cp1252), where
    # printing a status icon raises UnicodeEncodeError and kills the command
    # instead of reporting. Reconfigure once here so no caller ever needs the
    # PYTHONIOENCODING env-var dance.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        # A broken aide.toml is a user-fixable state, not a crash. Every
        # subcommand loads the config, so catching it once here keeps the
        # traceback off the screen for all of them.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
