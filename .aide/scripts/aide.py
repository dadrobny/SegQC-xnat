#!/usr/bin/env python3
"""aide — the AIDE framework CLI.

A single, stdlib-only command-line tool for the deterministic parts of the AIDE
loop, so agents don't spend reasoning tokens on mechanical git/document surgery.
It is **venv-independent** (it must run before/without the project venv) and
**project-agnostic** — every project fact comes from ``aide.toml``.

Subcommands::

    python .aide/scripts/aide.py check [--queue NNN]   # consistency gate over docs/aide
    python .aide/scripts/aide.py scope [NNN]           # branch diff vs the item's authorised paths
    python .aide/scripts/aide.py progress set NNN <in-progress|done>
    python .aide/scripts/aide.py queue tidy NNN        # mark a superseded queue as completed
    python .aide/scripts/aide.py claim [--queue NNN]   # pick + claim the next 📋 item
    python .aide/scripts/aide.py merge NNN [--base R]  # merge a validated item per git.mode
    python .aide/scripts/aide.py env                   # venv existence / import check + bootstrap
    python .aide/scripts/aide.py sync [--item NNN]     # preflight: fetch, clean-tree check, right branch
    python .aide/scripts/aide.py gc [--merged] [--yes] # delete claim branches whose work landed
    python .aide/scripts/aide.py status                # one-call roadmap-state report

The parsing/editing helpers are pure functions so they can be unit-tested without
touching git or the real filesystem (see ``.aide/scripts/tests``).
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

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
# Outcome targets (optional table — see conventions.md §1)
# --------------------------------------------------------------------------- #
_TARGETS_HEADING_RE = re.compile(r"^#{1,2}\s+Outcome targets\b", re.IGNORECASE)
#: Table-local status vocabulary (like the env-gated verification table's):
#: the cell's LEADING mark decides, the rest is evidence/notes for humans.
_TARGET_STATUS_KIND = {"✅": "met", "❌": "not-met", "❓": "unverified"}


class OutcomeTarget(NamedTuple):
    lineno: int              # 1-based line number in progress.md
    text: str                # the Target cell
    objectives: List[str]    # G-codes named in the Objective cell
    kind: Optional[str]      # "met" | "not-met" | "unverified" | None (unrecognised)


#: The optional `## Human gates` table — a decision only a person can make,
#: blocking work until they make it. Kept separate from acceptance boxes
#: deliberately: conventions.md §1 defines those as observable checks OF THE
#: BUILT THING, which a steering decision is not. Same reasoning that gave
#: Outcome targets their own table rather than overloading the checkboxes.
_GATES_HEADING_RE = re.compile(r"^#{1,2}\s+Human gates\b", re.IGNORECASE)
#: Table-local vocabulary, like Outcome targets': the LEADING mark decides.
_GATE_STATUS_KIND = {"⏳": "awaiting", "✅": "approved", "❌": "declined"}
#: A gate whose Blocks cell says this halts every item, everywhere — for a
#: programme-level decision ("no work proceeds until sign-off").
_GATE_BLOCKS_ALL = "all"
#: `stage N` — every item the named stage's deliverables reference. Blocking is
#: tied to a STAGE, never to a queue: a queue is an incidental batch boundary
#: (part of a stage, a stage, or several small ones), so "the live queue" names
#: different work from one week to the next while the decision has not changed.
#: A stage is the roadmap's own unit and means the same thing over time.
_GATE_BLOCKS_STAGE_RE = re.compile(r"^stage\s+0*(\d+)$", re.IGNORECASE)


class HumanGate(NamedTuple):
    lineno: int              # 1-based line number in progress.md
    text: str                # the Gate cell
    blocks: List[int]        # item numbers named directly (empty for stage/all)
    stage: Optional[str]     # stage number when the cell reads "stage N"
    blocks_all: bool         # True when the cell reads "all"
    kind: Optional[str]      # "awaiting" | "approved" | "declined" | None

    @property
    def reach(self) -> str:
        """How far this gate reaches, for a human-readable report."""
        if self.blocks_all:
            return "all items"
        if self.stage is not None:
            return f"stage {self.stage}"
        return ("items " + ", ".join(f"{i:03d}" for i in self.blocks)
                if self.blocks else "nothing named")


def stage_item_numbers(lines: List[str], stage: str) -> List[int]:
    """Item numbers referenced by *stage*'s deliverable bullets in progress.md.

    Reuses the §1 rule that only a deliverable bullet (and its wrapped
    continuation lines) carries an item reference, so a Notes cell or an
    acceptance checkbox naming an item does not widen a stage gate's reach.
    """
    section = next((sec for sec in stage_sections(lines)
                    if _same_stage(sec[2], stage)), None)
    if section is None:
        return []
    start, end, _ = section
    return sorted(_parse_item_status(lines[start:end])[2])


def _blocked_item_numbers(cell: str) -> List[int]:
    """Item numbers in a gate's ``Blocks`` cell.

    Accepts the §1 reference forms (``Items 106, 110–112``) *and* the bare
    numbers an author naturally writes in a column already headed "Blocks"
    (``106``, ``110, 111``). The shared extractor keys off the word "Item", so
    a bare list would parse as **nothing** — and a gate blocking nothing is a
    gate that silently does not work, the one failure mode this table exists to
    prevent. Normalising the cell first reuses that extractor's list/range
    handling rather than growing a second dialect.
    """
    text = cell if re.search(r"\bitems?\b", cell, re.IGNORECASE) else f"Items {cell}"
    return _referenced_item_numbers(text)


def human_gates(lines: List[str]) -> List[HumanGate]:
    """Rows of the optional ``## Human gates`` table in progress.md.

    A gate is a decision only a person can make — approving a direction,
    signing off an irreversible change, confirming an out-of-band prerequisite
    arrived. It blocks work until resolved, and **no agent may resolve one**:
    that is the entire point, and the reason the state lives in a CLI-written
    table rather than a checkbox any role could tick.

    ``Blocks`` accepts the item-reference forms of §1 (``106``, ``106, 107``,
    ``106–108``), ``stage N`` for every item that stage's deliverables
    reference, or ``all`` for a programme-level stop.
    """
    out: List[HumanGate] = []
    in_section = False
    for i, line in enumerate(lines):
        if _GATES_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _ANY_HEADER_RE.match(line):
            break  # next section — the table is over
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if _is_gate_table_furniture(cells) or len(cells) != 4:
            continue
        kind = next((k for icon, k in _GATE_STATUS_KIND.items()
                     if cells[2].startswith(icon)), None)
        blocks_cell = cells[1].strip()
        blocks_all = blocks_cell.lower() == _GATE_BLOCKS_ALL
        sm = _GATE_BLOCKS_STAGE_RE.match(blocks_cell)
        stage = sm.group(1) if sm else None
        blocks = [] if (blocks_all or stage) else _blocked_item_numbers(blocks_cell)
        out.append(HumanGate(i + 1, cells[0], blocks, stage, blocks_all, kind))
    return out


def blocking_gates(lines: List[str]) -> List[HumanGate]:
    """Gates still holding work up — every gate that is not ``✅ Approved``.

    **A declined gate keeps blocking.** It is *resolved* — a person decided —
    but the decision was "no", so releasing the work it guards would run
    exactly what was refused. The remedy is to re-plan (drop the item, or
    change what the gate asks), not to let the loop proceed. Only approval
    opens a gate.

    An unrecognised status also blocks: a typo in the mark must not silently
    open one.
    """
    return [g for g in human_gates(lines) if g.kind != "approved"]


def gate_blocked_items(lines: List[str]) -> Tuple[set, List[HumanGate]]:
    """``(blocked item numbers, block-everything gates)`` from the blocking gates.

    A ``stage N`` gate resolves through progress.md to the items that stage's
    deliverables reference, so its reach follows the roadmap as the stage's
    contents change — which is the whole reason reach is anchored to a stage
    rather than to whichever queue happens to be live.
    """
    blocked, everything = set(), []
    for g in blocking_gates(lines):
        if g.blocks_all:
            everything.append(g)
        elif g.stage is not None:
            blocked.update(stage_item_numbers(lines, g.stage))
        else:
            blocked.update(g.blocks)
    return blocked, everything


def outcome_targets(lines: List[str]) -> List[OutcomeTarget]:
    """Rows of the optional ``## Outcome targets`` table in progress.md.

    An outcome target is a MEASURED result the roadmap commits to (an error
    rate, a benchmark) — something shipped work can enable but never guarantee,
    so it is deliberately outside the stage rollup: a stage's ✅ keeps meaning
    "the planned work shipped", and goal truth lives here, gating the
    OBJECTIVE rows instead (an objective linked to a target that is not
    ``✅ Met`` cannot roll up to ✅).
    """
    out: List[OutcomeTarget] = []
    in_section = False
    for i, line in enumerate(lines):
        if _TARGETS_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _ANY_HEADER_RE.match(line):
            break  # next section — the table is over
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        # Skip anything but a data row: wrong arity, the header row, the
        # separator row (only -/:), or an empty Target cell.
        if len(cells) != 5 or cells[0].lower() == "target" or set(cells[0]) <= set("-: "):
            continue
        kind = next((k for icon, k in _TARGET_STATUS_KIND.items()
                     if cells[3].startswith(icon)), None)
        out.append(OutcomeTarget(i + 1, cells[0], re.findall(r"G\d+", cells[1]), kind))
    return out


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


def _same_stage(a: str, b: str) -> bool:
    """Compare two stage numbers, ignoring zero-padding when both are numeric."""
    sa, sb = str(a).strip(), str(b).strip()
    if sa.isdigit() and sb.isdigit():
        return int(sa) == int(sb)
    return sa == sb


def acceptance_boxes(lines: List[str], start: int, end: int) -> List[int]:
    """Line indices of the acceptance checkboxes in one stage section, in order.

    An acceptance box is an *attestation*: a human states that an observable
    criterion holds. It is deliberately not derived from anything — the rollup
    skips checkbox lines (see ``stage_deliverable_statuses``), no ``aide check``
    rule gates a ✅ stage on them, and nothing else reads them. That is why
    ``set_item_status`` no longer ticks them as a side effect of a status
    change: a rollup cannot attest, and auto-ticking made the honest state
    "shipped, but this criterion is not met" impossible to keep — the same
    state Outcome targets exist to express at the objective level.

    Ticking now goes through ``aide progress accept``, which is deliberate,
    logged, and cannot be undone by an unrelated item's status change.
    """
    return [i for i in range(start, end) if _CHECKBOX_RE.match(lines[i])]


def accept_criteria(text: str, stage: str, criteria: Optional[List[int]],
                    evidence: Optional[str] = None) -> Tuple[str, List[str]]:
    """Tick acceptance boxes in *stage*; return (updated text, messages).

    ``criteria`` is a list of 1-based box indices, or None for every box in the
    stage. An already-ticked box is reported and left alone rather than being
    silently counted as newly accepted. Raises ``ValueError`` when the stage or
    an index does not exist — a typo'd stage must not pass as a no-op.

    The stage is matched numerically, so ``accept 6`` finds a section headed
    ``## Stage 06`` — ``stage_sections`` reports the header text verbatim, and
    a caller typing the correct number should not have to guess its padding.
    """
    lines = text.splitlines()
    section = next((s for s in stage_sections(lines)
                    if _same_stage(s[2], stage)), None)
    if section is None:
        raise ValueError(f"no Stage {stage} section in progress.md")
    start, end, _ = section
    boxes = acceptance_boxes(lines, start, end)
    if not boxes:
        raise ValueError(f"Stage {stage} has no acceptance checkboxes")
    wanted = list(range(1, len(boxes) + 1)) if criteria is None else criteria
    for n in wanted:
        if not 1 <= n <= len(boxes):
            raise ValueError(
                f"Stage {stage} has {len(boxes)} acceptance criteria; {n} is out of range")
    messages: List[str] = []
    for n in wanted:
        i = boxes[n - 1]
        m = _CHECKBOX_RE.match(lines[i])
        if m.group("mark") != " ":
            messages.append(f"criterion {n}: already ticked, unchanged")
            continue
        post = m.group("post")
        if evidence:
            post = post.rstrip() + f" *({evidence})*"
        lines[i] = m.group("pre") + "x" + post
        messages.append(f"criterion {n}: accepted")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), messages


def _objective_stages(delivered_by: str) -> List[str]:
    return re.findall(r"\bStage[s]?\s+([\d,\s]+)", delivered_by)


def _apply_objective_rollup(lines: List[str], stage_status: Dict[str, str]) -> None:
    # An objective linked to an outcome target that is not ✅ Met can never
    # roll up to ✅: its stages shipping is necessary but not sufficient.
    blocked = {g for t in outcome_targets(lines) if t.kind != "met"
               for g in t.objectives}
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        gm = re.match(r"G\d+", cells[0]) if len(cells) == 3 else None
        if gm and _icon_status(cells[2]):
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
            if derived == "complete" and gm.group(0) in blocked:
                derived = "in-progress"
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

    ``status`` is ``in-progress`` or ``complete``. Updates summary/header/
    objective rows only for stages that fully complete. Never downgrades an
    existing status (additive log), and never touches an acceptance checkbox —
    those are human attestations, ticked only by ``aide progress accept``.
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
#: An AIDE slot is a bare ``{{name}}``. The negative lookbehind exempts a `$`
#: immediately before the braces — GitHub Actions expression syntax, which is
#: foreign syntax a living document may legitimately quote when it documents a
#: workflow. Without it, an item spec explaining what a CI step runs, or an
#: insight recording a workflow's arguments, turns `aide check` red on prose
#: that is correct as written, and the only remedy is to stop naming the real
#: syntax — making the documentation worse exactly where accuracy matters.
#:
#: Suppressing matches inside backtick code spans would be the wrong fix: the
#: item template's own `Suggested branch` line carries a genuine slot inside a
#: code span (``aide/{{nnn}}-descriptive-name``), so that rule would make a
#: real unfilled slot invisible. AIDE slots are never `$`-prefixed, so keying
#: on the `$` is precise in both directions.
_TEMPLATE_SLOT_RE = re.compile(r"(?<!\$)\{\{[^}]*\}\}")


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
                    f"{path.relative_to(ddir).as_posix()}:{lineno}: "
                    f"unfilled template slot {m.group(0)}"
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


def absolute_path_test_warnings(repo_root: Path,
                                config: Dict[str, Dict[str, object]]) -> List[str]:
    """Warn on a test file containing the repository's own absolute path.

    The one portability rule of conventions.md §6 a script can decide, and the
    one whose recorded instance was invisible to every other gate for weeks: a
    test pinned the authoring sandbox's own filesystem path instead of
    resolving relative to the test file. Because that path *is* where the
    project sits on that machine, it passed the builder's run, both validator
    rounds, and even a fresh clone into a different directory — an absolute
    path ignores where the process runs from. On every CI runner the glob
    matched nothing, the digest collapsed to SHA-256 of empty input, and all
    four legs failed.

    Matching the repo root literally keeps this exact: a test that hardcodes
    the path of the repository it lives in is wrong on any other machine, with
    no judgement call and no false positive to argue about.
    """
    tests_dir = repo_root / str(config["project"].get("tests_dir", "tests"))
    if not tests_dir.is_dir():
        return []
    # Three spellings, because the offending literal is whatever the authoring
    # platform wrote and this check must fire wherever it runs. On POSIX all
    # three collapse to one string; on Windows they are genuinely different:
    #   as_posix()  C:/path/to/repo    — a forward-slash literal
    #   str()       C:\path\to\repo    — a raw string, r"C:\path\to\repo"
    #   escaped     C:\\path\\to\\repo — an ordinary literal, the COMMON form
    # Omitting the third would make this portability lint miss the most likely
    # Windows spelling of the very defect it exists to catch.
    root = repo_root.resolve()
    needles = {root.as_posix(), str(root), str(root).replace("\\", "\\\\")}
    out: List[str] = []
    for path in sorted(tests_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding=_ENCODING)
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(n in line for n in needles):
                rel = _rel_display(path, repo_root)
                out.append(
                    f"{rel}:{lineno}: contains this repository's absolute path — "
                    f"it passes here and matches nothing on any other checkout; "
                    f"resolve from the test file instead "
                    f"(Path(__file__).resolve().parents[N]). See conventions.md §6")
                break   # one warning per file is enough to act on
    return out


def _is_gate_table_furniture(cells: List[str]) -> bool:
    """True for the gates table's header or separator row — never for data.

    The separator test requires a NON-EMPTY cell. `set("") <= set("-: ")` is
    true, so an empty first cell used to read as a separator: a malformed row
    like `| | 028 | ⏳ Awaiting | a | pipe |` was skipped *silently*, which is
    precisely the vanishing-gate failure the warning below exists to catch.
    """
    if not cells:
        return True
    first = cells[0]
    return first.lower() == "gate" or bool(first.strip()) and set(first) <= set("-: ")


def _malformed_gate_row_warnings(lines: List[str]) -> List[str]:
    """Rows inside the gates table the parser had to skip.

    A gate is only useful if it is read, so a row with the wrong column count
    must not vanish in silence — that turns "a person must decide this" into
    "nothing is blocking", which is the most dangerous way this feature can
    fail. The CLI refuses to write a `|` into a cell; this catches the rest
    (a hand edit, a paste).
    """
    out: List[str] = []
    in_section = False
    for i, line in enumerate(lines):
        if _GATES_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _ANY_HEADER_RE.match(line):
            break
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_row(line)
        if _is_gate_table_furniture(cells) or len(cells) == 4:
            continue
        out.append(
            f"progress.md:{i + 1}: human-gate row has {len(cells)} columns, not 4 — "
            f"it is being SKIPPED, so whatever it was meant to block is not "
            f"blocked. A '|' inside a cell is the usual cause.")
    return out


def gate_warnings(lines: List[str]) -> List[str]:
    """One warning per unresolved human gate, plus one per unreadable row.

    A warning, never an error: an outstanding gate is a normal state — work is
    waiting on a person, which is what it is for. The point is that the state
    is *visible* rather than buried in an item spec's prose.
    """
    out: List[str] = []
    out.extend(_malformed_gate_row_warnings(lines))
    for n, g in enumerate(human_gates(lines), start=1):
        if g.kind == "approved":
            continue
        if g.kind is None:
            out.append(
                f"progress.md:{g.lineno}: human gate {n} ({g.text}) has an "
                f"unrecognised status — use ⏳ Awaiting, ✅ Approved or ❌ Declined; "
                f"until it reads one of those the gate counts as unresolved")
            continue
        if g.kind == "declined":
            out.append(
                f"progress.md:{g.lineno}: human gate {n} ({g.text}) was DECLINED "
                f"and still blocks {g.reach} — a refusal does not release the "
                f"work it guards; drop those items or change what the gate asks")
            continue
        if g.stage is not None and not stage_item_numbers(lines, g.stage):
            # A typo here is invisible otherwise: the gate looks like it guards
            # a stage while holding nothing at all.
            reach = (f"stage {g.stage} — which has no deliverable referencing "
                     f"any item, so this gate holds NOTHING; check the stage "
                     f"number")
        elif g.blocks or g.stage or g.blocks_all:
            reach = g.reach
        else:
            reach = ("nothing named — the Blocks cell names no item, no "
                     "'stage N', and is not 'all', so this gate holds nothing")
        out.append(f"progress.md:{g.lineno}: human gate {n} ({g.text}) is "
                   f"awaiting a decision — blocks {reach}")
    return out


#: A deliverable bullet must be FLAT (conventions.md §1). `_BULLET_RE` allows
#: leading whitespace, so a nested bullet is read as a **full deliverable** —
#: not ignored. That is the hazard: nesting implies subordination to a reader
#: while the rollup counts it as a peer, so a `📋` child silently drags its ✅
#: parent's stage to 🚧. Verified: ['complete', 'planned'] -> in-progress.
_NESTED_DELIVERABLE_RE = re.compile(r"^\s+[-*]\s*(?P<icon>" + _ICON_ALT + r")")

#: Documents whose template carries a header blockquote. Not every file under
#: docs_dir: a generated artifact or a project note is not a living document,
#: and insights.md's template deliberately opens with a comment instead.
_BLOCKQUOTE_DOCS = ("vision.md", "roadmap.md", "progress.md")

#: A status FIELD in an item header: `**Status:** x` or `**Status**: x`. The
#: colon is required, so bold emphasis on the word in prose is not a match.
_ITEM_STATUS_FIELD_RE = re.compile(
    r"\*\*\s*(?P<name>Status|Completed)\s*(?::\s*\*\*|\*\*\s*:)")


#: Calls that spawn a process. Matched through the AST, never by line text: the
#: one occurrence in the consumer measured against was a DOCSTRING explaining
#: why the author had removed a subprocess — a line-based lint flags the file
#: documenting the correct practice.
_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output", "check_call", "call"})


def _rel_display(path: Path, repo_root: Path) -> str:
    """*path* relative to the repo for a message, falling back to absolute.

    `tests_dir` may be configured absolute or resolve outside the repo via a
    symlink, and `relative_to` raises then. Shared by every test-hygiene lint:
    fixing this once in `absolute_path_test_warnings` and then hand-writing the
    same call in two new ones is exactly how it came back.
    """
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _test_files(repo_root: Path, config: Dict[str, Dict[str, object]]) -> List[Path]:
    tests_dir = repo_root / str(config["project"].get("tests_dir", "tests"))
    if not tests_dir.is_dir():
        return []
    return [p for p in sorted(tests_dir.rglob("*.py"))
            if "__pycache__" not in p.parts]


def separator_dependent_test_warnings(repo_root: Path,
                                      config: Dict[str, Dict[str, object]]) -> List[str]:
    """Tests stringifying a relative `Path` into a value that gets compared.

    conventions.md §6: any `Path` entering a hash, comparison or match must be
    `.as_posix()`. Narrowed to `.relative_to(`, the shape all four recorded
    CI-only failures took, reached two ways — an explicit `str(...)` and an
    f-string, which calls `str()` for you.

    Matched through the AST, because a regex cannot tell an f-string's `{...}`
    from a dict or set literal: `{p.relative_to(root): 1}` never stringifies the
    Path and must not be flagged. A lint that cries wolf stops being read.
    """
    out: List[str] = []
    for path in _test_files(repo_root, config):
        try:
            tree = ast.parse(path.read_text(encoding=_ENCODING))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        def _ends_in_relative_to(node) -> bool:
            """True when the OUTERMOST call of *node* is `.relative_to(...)`.

            Deliberately the outermost, not anywhere in the subtree: searching
            the subtree flags `str(p.relative_to(root).as_posix())`, which is
            already separator-stable and is exactly what the rule asks for.
            Flagging compliant code is how a lint stops being read, so this
            errs narrow — it reports the recorded shape and stays quiet on
            anything already normalised.
            """
            return (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "relative_to")

        for node in ast.walk(tree):
            hit = False
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "str" and len(node.args) == 1):
                hit = _ends_in_relative_to(node.args[0])
            elif isinstance(node, ast.JoinedStr):
                hit = any(_ends_in_relative_to(v.value) for v in node.values
                          if isinstance(v, ast.FormattedValue))
            if hit:
                out.append(
                    f"{_rel_display(path, repo_root)}:{node.lineno}: a relative "
                    f"Path rendered with str() carries the OS separator, so this "
                    f"value differs on Windows — use .as_posix() "
                    f"(conventions.md §6)")
                break
    return out


def cli_subprocess_test_warnings(repo_root: Path,
                                 config: Dict[str, Dict[str, object]]) -> List[str]:
    """Tests shelling out to `aide.py` instead of calling its function.

    conventions.md §6: prefer calling the function over shelling out to the
    command that calls it. The logic is importable and returns structured data;
    the subprocess adds stdout encoding, platform quirks, and a re-parse of what
    was structured a moment earlier. The recorded instance returned
    ``stdout is None`` on a Windows runner — and had it returned ``""`` the test
    would have passed while checking nothing.
    """
    out: List[str] = []
    for path in _test_files(repo_root, config):
        try:
            tree = ast.parse(path.read_text(encoding=_ENCODING))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _SUBPROCESS_FUNCS:
                continue
            if any(isinstance(c, ast.Constant) and isinstance(c.value, str)
                   and "aide.py" in c.value for c in ast.walk(node)):
                rel = _rel_display(path, repo_root)
                out.append(
                    f"{rel}:{node.lineno}: shells out to aide.py — call the "
                    f"function instead (e.g. run_checks); a subprocess adds a "
                    f"stdout/encoding surface that has failed on Windows only, "
                    f"and can pass while checking nothing (conventions.md §6)")
                break
    return out


def nested_deliverable_warnings(lines: List[str]) -> List[str]:
    """Status-bearing bullets nested anywhere inside a stage section.

    The parser matches indented bullets, so a nested one counts as a full
    deliverable in the rollup and in item-status parsing. The nesting says
    "subordinate" to a reader while the tooling says "peer" — so a `📋` child
    quietly holds its ✅ parent's stage open, and nothing reconciles the two
    readings.

    **Scanned across the whole stage section, deliberately, not just the
    Deliverables block.** `stage_deliverable_statuses` reads `lines[start:end]`
    — every leading-icon bullet in the section, skipping only checkboxes — so an
    indented status bullet under **Acceptance** drags the stage exactly the same
    way. Verified: such a bullet turns `['complete']` into
    `['complete', 'planned']` and a ✅ stage into 🚧. Narrowing this to the
    Deliverables block would under-report a bullet that really does break the
    rollup.
    """
    out: List[str] = []
    for start, end, num in stage_sections(lines):
        for i in range(start, end):
            m = _NESTED_DELIVERABLE_RE.match(lines[i])
            if m:
                out.append(
                    f"progress.md:{i + 1}: stage {num} has a nested status bullet "
                    f"({m.group('icon')}) — the rollup counts it as a full "
                    f"deliverable despite the indent, so it can hold the stage "
                    f"open while reading as subordinate. Flatten it, or drop "
                    f"its icon.")
    return out


def _line_after_title(lines: List[str]) -> str:
    """The first content line after the `#` title, or "" if there is none.

    Two subtleties. A multi-line HTML comment must be skipped **whole** — only
    its opening line starts with `<!--`, so testing line-by-line lets its body
    read as content. And the search stops at the first line after the title
    rather than skipping further headings: "opens with a blockquote" means the
    next thing, so `# Title` / `## Intro` / `> …` does not satisfy it.
    """
    in_comment = False
    seen_title = False
    for line in lines:
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        if not stripped:
            continue
        if not seen_title:
            if stripped.startswith("#"):
                seen_title = True
            continue
        return stripped
    return ""


def header_blockquote_warnings(ddir: Path) -> List[str]:
    """Living documents that do not open with their header blockquote.

    The blockquote carries the document's place in the loop and what it derives
    from — structural facts a reader landing anywhere needs (conventions.md §1).
    """
    out: List[str] = []
    targets = [ddir / name for name in _BLOCKQUOTE_DOCS]
    for sub in ("queue", "items"):
        if (ddir / sub).is_dir():
            targets.extend(sorted((ddir / sub).glob("*.md")))
    for path in targets:
        if not path.is_file():
            continue
        first = _line_after_title(path.read_text(encoding=_ENCODING).splitlines())
        if not first.startswith(">"):
            # Relative to docs_dir, matching `progress.md:12` and `items/…`.
            rel = path.relative_to(ddir).as_posix()
            out.append(f"{rel}: no header blockquote — the line after the title "
                       f"should carry this document's place in the loop and what "
                       f"it derives from")
    return out


def item_spec_warnings(ddir: Path) -> List[str]:
    """Item specs that break the shapes §1 and §5 fix.

    Three rules, none previously checked: the `# Item NNN — Title` heading must
    agree with the filename (the status report parses the title from it); the
    header must carry NO status field (status lives only in progress.md, and a
    duplicate has no owner and only drifts); and the **Assumptions** block is
    mandatory, since it is what the validator surfaces for audit.

    The missing-Assumptions finding is reported as ONE aggregated line. Specs
    predating the rule are common — 32 of 112 in the consumer this was measured
    against — and 32 separate warnings would bury the substantive ones, which is
    the failure mode issue #13 was filed for.
    """
    idir = ddir / "items"
    if not idir.is_dir():
        return []
    out: List[str] = []
    missing_assumptions: List[str] = []
    for path in sorted(idir.glob("*.md")):
        m = re.match(r"0*(\d+)", path.name)
        if not m:
            continue
        num = int(m.group(1))
        text = path.read_text(encoding=_ENCODING)
        if not re.search(rf"^#\s+Item\s+0*{num}\s*[—–-]\s*\S", text, re.MULTILINE):
            out.append(f"items/{path.name}: no '# Item {num:03d} — Title' heading "
                       f"matching the filename")
        head = text.split("\n---", 1)[0]
        # A FIELD, not bold emphasis. Two conditions keep this precise: the line
        # is part of the header blockquote, and a colon sits beside the bold —
        # inside it (`**Status:**`, the template's own spelling) or right after
        # (`**Status**:`). Matching bare `**Status**` anywhere would flag prose
        # that merely emphasises the word.
        sm = next((m for line in head.splitlines() if line.lstrip().startswith(">")
                   for m in [_ITEM_STATUS_FIELD_RE.search(line)] if m), None)
        if sm:
            out.append(f"items/{path.name}: header carries a '{sm.group('name')}' field — "
                       f"status lives only in progress.md; a duplicate has no owner "
                       f"and only drifts")
        if not re.search(r"^##\s+Assumptions", text, re.MULTILINE):
            missing_assumptions.append(f"{num:03d}")
    if missing_assumptions:
        shown = ", ".join(missing_assumptions[:8])
        more = (f" (+{len(missing_assumptions) - 8} more)"
                if len(missing_assumptions) > 8 else "")
        out.append(f"{len(missing_assumptions)} item spec(s) have no mandatory "
                   f"'## Assumptions' block: {shown}{more} — it is what the "
                   f"validator surfaces for audit at the queue boundary")
    return out


def _stray_icons_in_line(line: str) -> List[str]:
    """Status icons on this line that sit where one could plausibly be
    mistaken for a structural status declaration.

    conventions.md §1 is explicit that icons are read *only* at structural
    positions — a deliverable bullet's leading icon, a table row's last cell,
    a stage header's trailing icon — and that "an icon anywhere else […] is
    plain text and is never read as status, so authors need not avoid the
    icon vocabulary in free text." A bullet with no leading icon, or an
    ordinary paragraph, therefore has *no* structural position at all, and
    any icon it contains is exactly that free text — never stray. Only a
    heading, whose sole structural slot is the trailing icon, can still carry
    a status-shaped icon somewhere a reader would misread as the header's
    status.
    """
    icons = list(_ICON_RE.finditer(line))
    if not icons:
        return []
    if _QUEUE_STATUS_RE.match(line):
        return []  # "> **Status:** …" lines legitimately carry an icon
    if line.strip().startswith("|"):
        return []  # table rows: parsers read specific cells only, never prose
    if _BULLET_RE.match(line):
        return []  # bullets: only the leading icon is structural; the rest is free prose
    if re.match(r"^#{1,6}\s", line):  # any heading level may carry a trailing icon
        t = _TRAILING_ICON_RE.search(line)
        allowed = t.span(1) if t else None
        return [i.group(0) for i in icons if i.span() != allowed]
    return []  # ordinary paragraph text: no structural position exists here at all


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
                    f"{path.relative_to(ddir).as_posix()}:{lineno}: status icon {icon} outside a "
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
    warnings.extend(absolute_path_test_warnings(repo_root, config))
    warnings.extend(separator_dependent_test_warnings(repo_root, config))
    warnings.extend(cli_subprocess_test_warnings(repo_root, config))
    warnings.extend(header_blockquote_warnings(ddir))
    warnings.extend(item_spec_warnings(ddir))
    if not progress_path.is_file():
        return [f"missing {progress_path}"], warnings
    # One read, reused: two reads can disagree if the file changes between them.
    text = progress_path.read_text(encoding=_ENCODING)
    lines = text.splitlines()
    warnings.extend(gate_warnings(lines))
    warnings.extend(nested_deliverable_warnings(lines))

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
            warnings.append(
                f"stage {num}: all deliverables ✅ but summary shows {summ} — "
                f"if the work shipped but the stage's goal is unmet, record the "
                f"goal as an Outcome target (❌ Not met) and close the stage; "
                f"stages track shipped work, targets track measured outcomes")
        if summ == "complete" and derived and derived != "complete":
            errors.append(f"stage {num}: summary marked ✅ but has non-complete deliverables")
        if header_status and summ and header_status != summ:
            warnings.append(f"stage {num}: header {header_status} disagrees with summary {summ}")

    for num in summary_status:
        if num not in section_nums:
            warnings.append(f"stage {num}: in summary table but has no '## Stage {num}' section")

    # Outcome targets: goal truth gates the OBJECTIVE rows. Claiming an
    # objective ✅ over an unmet target is the goal-level over-claim this
    # table exists to prevent (issue #14) — the mirror of the deliverable-level
    # error above.
    obj_status: Dict[str, str] = {}
    for l in lines:
        cells = _split_row(l) if l.strip().startswith("|") else []
        if len(cells) == 3 and re.match(r"G\d+", cells[0]) and _icon_status(cells[2]):
            obj_status[re.match(r"G\d+", cells[0]).group(0)] = _icon_status(cells[2])
    for t in outcome_targets(lines):
        if t.kind is None:
            warnings.append(
                f"progress.md:{t.lineno}: outcome target '{t.text}' has an "
                f"unrecognised Status (expected '✅ Met', '❌ Not met' or "
                f"'❓ Unverified')")
        for g in t.objectives:
            if obj_status.get(g) != "complete":
                continue
            if t.kind == "not-met":
                errors.append(
                    f"objective {g} marked ✅ but outcome target '{t.text}' "
                    f"is ❌ Not met")
            elif t.kind != "met":
                warnings.append(
                    f"objective {g} marked ✅ but outcome target '{t.text}' "
                    f"is not ✅ Met")

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
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    if branches is None:
        branches = _list_claim_branches(repo_root, prefix)
    _, _, item_status = _parse_item_status(lines)
    for br in branches:
        n = _branch_item_number(br, prefix)
        if n is None:
            # Not a claim branch. A queue branch is expected and silent; anything
            # else carrying the prefix is reported rather than ignored, so a real
            # stale claim named unconventionally cannot hide behind the anchor.
            if not _is_queue_branch(br, prefix):
                warnings.append(
                    f"unrecognised branch {br}: carries the claim prefix but is "
                    f"not '{prefix}NNN-short-name' (conventions.md §4), so no "
                    f"item status is tracked for it — rename it to the claim "
                    f"shape, or once it is merged run 'aide gc --merged' to "
                    f"delete it")
            continue
        if item_status.get(n) == "complete":
            warnings.append(f"stale claim branch {br}: item {n:03d} is already ✅")

    return errors, warnings


def _parse_item_status(lines: List[str]) -> Tuple[List[str], List[str], Dict[int, str]]:
    """Map item number -> most-advanced status found on its deliverable bullets.

    The only structural status declaration (conventions.md §1) is a deliverable
    bullet's leading icon — a line matching ``_BULLET_RE`` — together with any
    of its wrapped continuation lines (indented text carrying no bullet marker
    of its own). A reference anywhere else — a table cell, an acceptance
    checkbox, an ordinary paragraph — is free text and is never read as status,
    however many item numbers it happens to name (issue #15): a verification
    table's Notes column narrating what went wrong with several items, or a
    checkbox that merely cites the item that satisfies it, must not pull that
    item's tracked status backwards.
    """
    item_status: Dict[int, str] = {}
    bullet_status: Optional[str] = None
    for line in lines:
        m = _BULLET_RE.match(line)
        if m:
            bullet_status = ICON_TO_STATUS[m.group("icon")]
        elif not line.strip() or re.match(r"^\s*[-*]\s", line) or not re.match(r"^\s+\S", line):
            bullet_status = None  # blank line, a non-deliverable bullet, or an unindented new block
        if bullet_status is None:
            continue
        for num in _referenced_item_numbers(line):
            if num not in item_status or RANK[bullet_status] > RANK[item_status[num]]:
                item_status[num] = bullet_status
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
# --------------------------------------------------------------------------- #
# Cross-spec queue check — do a queue's specs conflict, before any is built?
# --------------------------------------------------------------------------- #
class SpecFinding(NamedTuple):
    """One cross-item conflict between the specs on a queue."""

    severity: str          # "error" | "warning"
    kind: str              # machine-readable class, for the --report seam
    items: Tuple[int, ...]
    message: str


def patterns_overlap(a: str, b: str) -> bool:
    """True when two ``## Authorised paths`` patterns can cover the same file.

    Deliberately decides only the cases a script *can* decide: an identical
    pattern, a subtree wildcard swallowing the other, and a literal path
    covered by the other's glob. Two unrelated globs that would happen to
    intersect on some file neither spec has thought of are not modelled —
    reporting those would mean guessing at a future tree, and this check exists
    to be trusted, not to be argued with.
    """
    a = _strip_dot_slash(a.strip())
    b = _strip_dot_slash(b.strip())
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x.endswith("/**"):
            prefix = x[: -len("/**")]
            if y == prefix or y.startswith(prefix + "/"):
                return True
    if not any(c in a for c in "*?[") and path_matches(a, b):
        return True
    if not any(c in b for c in "*?[") and path_matches(b, a):
        return True
    return False


def _dependency_cycles(graph: Dict[int, List[int]]) -> List[List[int]]:
    """Every dependency cycle in *graph*, each reported once.

    A cycle deadlocks `aide claim` outright: every item in it is blocked by
    another item in it, so none is ever claimable and the queue silently stops
    producing work rather than failing.
    """
    cycles: List[List[int]] = []
    seen: set = set()
    state: Dict[int, int] = {}   # 0 = visiting, 1 = done

    def walk(node: int, stack: List[int]) -> None:
        state[node] = 0
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 0:
                cycle = stack[stack.index(nxt):]
                key = tuple(sorted(cycle))
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif nxt not in state and nxt in graph:
                walk(nxt, stack)
        stack.pop()
        state[node] = 1

    for node in sorted(graph):
        if node not in state:
            walk(node, [])
    return cycles


def queue_spec_findings(repo_root: Path, config: Dict[str, Dict[str, object]],
                        queue_number: int) -> Tuple[List[SpecFinding], List[int]]:
    """``(findings, unspecced)`` for every spec on queue *queue_number*.

    Runs in the window `/aide-spec-queue` creates and currently leaves
    unguarded: N specs authored on one branch before any is built, where every
    cross-item conflict is both possible and cheap to fix. The invariant it
    enforces is the one a consumer's post-mortem arrived at — *predicting the
    one collision a spec happens to name is not the same as proving no sibling
    assertion depends on state this item's authorised edit changes.*
    """
    ddir = docs_dir(repo_root, config)
    qpath = ddir / "queue" / f"queue-{queue_number:03d}.md"
    if not qpath.is_file():
        return ([SpecFinding("error", "missing-queue", (),
                             f"no queue file at {qpath.relative_to(repo_root).as_posix()}")],
                [])

    numbers = queue_item_numbers(qpath.read_text(encoding=_ENCODING))
    idir = ddir / "items"
    findings: List[SpecFinding] = []
    unspecced: List[int] = []
    declared: Dict[int, AuthorisedPaths] = {}

    for num in numbers:
        specs = sorted(idir.glob(f"{num:03d}-*.md")) if idir.is_dir() else []
        if not specs:
            # Normal mid-queue state, not a conflict: /aide-spec-queue exists to
            # fill these. Counted and reported, never silently dropped.
            unspecced.append(num)
            continue
        parsed = parse_authorised_paths(specs[0].read_text(encoding=_ENCODING))
        rel = specs[0].relative_to(repo_root).as_posix()
        if declares_nothing(parsed):
            findings.append(SpecFinding(
                "warning", "undeclared-scope", (num,),
                f"item {num:03d} ({rel}) declares no '## Authorised paths' — its "
                f"scope cannot be compared with its siblings'. Add the section "
                f"(conventions.md §1); until then this item needs a human scope "
                f"review, and `aide scope` cannot check it either"))
            continue
        declared[num] = parsed

    # The loop bookkeeping every item writes anyway (`aide scope` authorises
    # these without them being listed). Specs often list them redundantly, and
    # two items "conflicting" over progress.md is not a conflict — it is the
    # claim protocol working. Excluded from the overlap check, never from the
    # pinned-state check: pinning progress.md would be a real assertion.
    ddir_rel = ddir.relative_to(repo_root).as_posix()
    bookkeeping = {f"{ddir_rel}/{name}" for name in _ALWAYS_AUTHORISED}

    ordered = sorted(declared)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            # Row 1 — two items claim edit rights on the same file.
            for pa in declared[a].may_change:
                if pa in bookkeeping:
                    continue
                for pb in declared[b].may_change:
                    if patterns_overlap(pa, pb):
                        findings.append(SpecFinding(
                            "warning", "may-change-overlap", (a, b),
                            f"items {a:03d} and {b:03d} both claim '{pa}'"
                            + (f" / '{pb}'" if pa != pb else "")
                            + " under May change — whichever builds second "
                              "inherits the first's edits; confirm that is intended"))
        # Rows 2+3 — one item may change what another pins. Under the
        # `## Authorised paths` vocabulary these are one check: an "Asserts
        # against" entry covers a byte-hash pin and a live recomputation alike,
        # which is the point — the live-recomputed case is the one a survey
        # hunting fragile-looking hashes missed.
        for b in ordered:
            if a == b:
                continue
            for pa in declared[a].may_change:
                for pb in declared[b].asserts_against:
                    if patterns_overlap(pa, pb):
                        findings.append(SpecFinding(
                            "error", "changes-pinned-state", (a, b),
                            f"item {a:03d} may change '{pa}', which item {b:03d} "
                            f"pins as '{pb}' under Asserts against — item {b:03d}'s "
                            f"assertion breaks when item {a:03d} lands. Decide now "
                            f"which side is wrong: widen the pin, or narrow the edit"))

    # Row 5 — the dependency graph. A cycle deadlocks `aide claim`: every item
    # in it is blocked by another in it, so the queue silently stops producing
    # work rather than failing.
    graph = {num: _item_dependencies(repo_root, config, num)
             for num in numbers if num not in unspecced}
    for cycle in _dependency_cycles(graph):
        chain = " → ".join(f"{n:03d}" for n in cycle + [cycle[0]])
        findings.append(SpecFinding(
            "error", "dependency-cycle", tuple(cycle),
            f"dependency cycle {chain} — every item in it is blocked by another "
            f"in it, so `aide claim` will never offer any of them"))

    known = set(numbers)
    for num, deps in graph.items():
        for dep in deps:
            if dep in known:
                continue
            has_spec = bool(sorted(idir.glob(f"{dep:03d}-*.md"))) if idir.is_dir() else False
            in_a_queue = any(dep in queue_item_numbers(p.read_text(encoding=_ENCODING))
                             for p in _queue_paths(ddir / "queue"))
            if not has_spec and not in_a_queue:
                findings.append(SpecFinding(
                    "warning", "unknown-dependency", (num, dep),
                    f"item {num:03d} depends on item {dep:03d}, which has no spec "
                    f"and appears in no queue — a typo here blocks the item forever"))

    return findings, unspecced


def _write_findings_report(path: Path, queue_number: int,
                           findings: List[SpecFinding],
                           unspecced: List[int]) -> None:
    """Write the machine-readable report — the seam a reviewer pass consumes as
    its worklist rather than re-deriving what this check already decided."""
    payload = {
        "queue": queue_number,
        "unspecced_items": unspecced,
        "findings": [
            {"severity": f.severity, "kind": f.kind,
             "items": list(f.items), "message": f.message}
            for f in findings
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Plain utf-8, NOT `_ENCODING`: that is utf-8-sig, which writes a BOM. A BOM
    # is right for the markdown documents (Windows editors add one and the
    # parsers must tolerate it) and wrong here — `json.loads` rejects a leading
    # BOM outright, so the seam would be unreadable by the very consumer it
    # exists for.
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def cmd_check(args: argparse.Namespace) -> int:
    queue_number = getattr(args, "queue", None)
    if getattr(args, "report", None) and queue_number is None:
        # Silently ignoring it would be worse than refusing: the caller asked
        # for a file that would never appear, and only the missing file would
        # ever say so.
        print("aide check: --report needs --queue; there are no cross-spec "
              "findings to report without one", file=sys.stderr)
        return 2

    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    errors, warnings = run_checks(repo_root, config)

    if queue_number is not None:
        findings, unspecced = queue_spec_findings(repo_root, config, queue_number)
        for f in findings:
            (errors if f.severity == "error" else warnings).append(f.message)
        if unspecced:
            listed = ", ".join(f"{n:03d}" for n in unspecced)
            print(f"aide check: queue {queue_number:03d} — {len(unspecced)} item(s) "
                  f"not yet specced, so not compared: {listed}")
        report = getattr(args, "report", None)
        if report:
            _write_findings_report(Path(report), queue_number, findings, unspecced)
            print(f"aide check: wrote {report}")

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"aide check: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 1
    print(f"aide check: OK ({len(warnings)} warning(s))")
    return 0


def set_gate_status(text: str, index: int, kind: str,
                    note: Optional[str] = None, today: Optional[str] = None) -> str:
    """Resolve the *index*-th (1-based) row of the ``## Human gates`` table.

    Writes the decision and the date into the Status cell, and *note* into the
    last cell. Raises ``ValueError`` for a missing table or an out-of-range
    index — a typo must not pass as a silent no-op, which is exactly how a
    hand-edited gate went wrong before there was a verb for it.
    """
    lines = text.splitlines()
    gates = human_gates(lines)
    if not gates:
        raise ValueError("no '## Human gates' table in progress.md")
    if not 1 <= index <= len(gates):
        raise ValueError(f"there are {len(gates)} human gate(s); {index} is out of range")
    gate = gates[index - 1]
    if note and ("|" in note or "\n" in note or "\r" in note):
        raise ValueError(
            "the note may not contain '|' or a line break — either breaks the "
            "row's shape, and a row the parser cannot read is skipped, making a "
            "still-blocking gate silently disappear")
    icon = {"approved": "✅ Approved", "declined": "❌ Declined"}[kind]
    import datetime as _dt
    stamp = today or _dt.date.today().isoformat()
    i = gate.lineno - 1
    cells = _split_row(lines[i])
    cells[2] = f"{icon} ({stamp})"
    if note:
        cells[3] = note
    lines[i] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def cmd_gate(args: argparse.Namespace) -> int:
    """List or resolve the human gates in progress.md.

    Resolving a gate is a **person's** act. No agent may run `approve` or
    `decline`: a gate exists precisely because the decision is not derivable
    from the work, so an agent resolving one destroys the only thing it was
    protecting.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    ppath = docs_dir(repo_root, config) / "progress.md"
    if not ppath.is_file():
        print(f"aide gate: missing {ppath}", file=sys.stderr)
        return 2
    text = ppath.read_text(encoding=_ENCODING)
    gates = human_gates(text.splitlines())

    if args.action == "list":
        if not gates:
            print("aide gate: no '## Human gates' table (nothing gated)")
            return 0
        for n, g in enumerate(gates, start=1):
            reach = g.reach
            mark = {"approved": "✅", "declined": "❌", "awaiting": "⏳"}.get(g.kind, "⚠")
            print(f"  {n}. {mark} {g.text} — blocks {reach}")
        outstanding = len(blocking_gates(text.splitlines()))
        print(f"aide gate: {len(gates)} gate(s), {outstanding} still blocking")
        return 0

    if args.number is None:
        print(f"aide gate: '{args.action}' needs a gate number — see `aide gate list`",
              file=sys.stderr)
        return 2
    kind = "approved" if args.action == "approve" else "declined"
    try:
        updated = set_gate_status(text, args.number, kind, args.note)
    except ValueError as exc:
        print(f"aide gate: {exc}", file=sys.stderr)
        return 2
    ppath.write_text(updated, encoding=_ENCODING)
    print(f"gate {args.number}: {kind}")
    if not args.no_commit:
        _commit_progress_file(repo_root, config,
                              f"docs: human gate {args.number} {kind}")
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    if args.action == "accept":
        return _cmd_progress_accept(args)
    if args.action != "set":
        print("usage: aide progress set NNN <in-progress|done>", file=sys.stderr)
        return 2
    if args.status is None:
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


def _cmd_progress_accept(args: argparse.Namespace) -> int:
    """``aide progress accept STAGE --criterion N`` — tick an acceptance box.

    The explicit counterpart to the auto-tick ``set_item_status`` used to
    perform. An acceptance criterion is attested by a human who checked it, so
    it takes a deliberate command that records what was accepted and, with
    ``--evidence``, on what basis.
    """
    if args.criterion is None and not args.all_criteria:
        print("usage: aide progress accept STAGE (--criterion N | --all) "
              "[--evidence TEXT]", file=sys.stderr)
        return 2
    if args.criterion is not None and args.all_criteria:
        print("aide progress accept: pass --criterion or --all, not both", file=sys.stderr)
        return 2
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    progress_path = docs_dir(repo_root, config) / "progress.md"
    if not progress_path.is_file():
        print(f"error: {progress_path} not found", file=sys.stderr)
        return 1
    text = progress_path.read_text(encoding=_ENCODING)
    criteria = None if args.all_criteria else [args.criterion]
    try:
        updated, messages = accept_criteria(text, str(args.number), criteria, args.evidence)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for msg in messages:
        print(f"stage {args.number}: {msg}")
    if updated == text:
        return 0
    progress_path.write_text(updated, encoding="utf-8")
    if not args.no_commit and (repo_root / ".git").exists():
        what = "all criteria" if args.all_criteria else f"criterion {args.criterion}"
        _commit_progress_file(
            repo_root, config, f"progress(aide): stage {args.number} accept {what}")
    return 0


def _commit_progress(repo_root: Path, config, number: int, status: str) -> None:
    _commit_progress_file(
        repo_root, config, f"progress(aide): item {number:03d} -> {status}")


def _commit_progress_file(repo_root: Path, config, message: str) -> None:
    git(["pull", "--rebase"], repo_root, check=False)
    rel = str(config["project"].get("docs_dir", "docs/aide")) + "/progress.md"
    git(["add", rel], repo_root, check=False)
    res = git(["commit", "-m", message], repo_root, check=False)
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


#: Marks the start of a **forward-looking** aside inside a Dependencies section
#: — later items that depend on THIS one, not items this one depends on (e.g.
#: "**Downstream:** item 099 depends on this item's CI job"). Item numbers
#: after this marker are never read as blocking dependencies: extracting every
#: "Item NNN" mention in the section without it would misread "X depends on
#: this" as "this depends on X" and block on a backward reference to a later,
#: still-open item. Authors: put such asides after this exact marker so the
#: parser (and a human skimming the section) can tell the two apart.
_DEPENDENCIES_DOWNSTREAM_MARKER_RE = re.compile(r"\*\*Downstream\b", re.IGNORECASE)


def _item_dependencies(repo_root: Path, config, number: int) -> List[int]:
    """Item numbers named in the spec's Dependencies section (best effort).

    Uses the same multi-item/range-aware, case-insensitive extraction as every
    other "does this reference item NNN" call site (`_referenced_item_numbers`)
    — a naive first-number-only regex here previously left every number after
    the first in "Items 093, 094, 095" unrecognised as a blocker. Text at or
    after a "**Downstream" marker is excluded (see
    `_DEPENDENCIES_DOWNSTREAM_MARKER_RE`), so a forward-looking "item 099
    depends on this" aside does not register as a backward blocker.
    """
    idir = docs_dir(repo_root, config) / "items"
    if not idir.is_dir():
        return []
    specs = list(idir.glob(f"{number:03d}-*.md"))
    if not specs:
        return []
    text = specs[0].read_text(encoding=_ENCODING)
    m = re.search(r"^##\s+Dependencies\s*$(.*?)(^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    section = m.group(1) if m else ""
    downstream = _DEPENDENCIES_DOWNSTREAM_MARKER_RE.search(section)
    if downstream is not None:
        section = section[: downstream.start()]
    deps = set(_referenced_item_numbers(section))
    deps.discard(number)
    return sorted(deps)


def _pick_item(repo_root: Path, config, queue_text: str,
               claim_branches: List[str]) -> Optional[Tuple[int, str]]:
    """First queue item that is planned, unclaimed, and unblocked. (number, title).

    "Unblocked" covers three things: its `## Dependencies` are all under way,
    no claim branch exists for it, and **no unresolved human gate holds it**. A
    gate naming items (directly, or via `stage N`) skips just those, so the
    queue keeps producing other work; an `all` gate stops everything, which is
    the point of declaring one — a pending decision that could invalidate what
    comes next must not have the loop racing ahead of it.
    """
    ppath = docs_dir(repo_root, config) / "progress.md"
    plines = ppath.read_text(encoding=_ENCODING).splitlines() if ppath.is_file() else []
    _, _, item_status = _parse_item_status(plines) if plines else ([], [], {})
    gate_blocked, block_everything = gate_blocked_items(plines)
    if block_everything:
        return None
    # Anchored resolution, like every other branch->item call site since 1.5.0.
    # The old unanchored search read `aide/queue-016` as item 016 and
    # `aide/specs-queue-015` as item 015, marking those items permanently
    # "claimed" and therefore unclaimable — a queue branch is not an item claim.
    # This call site was missed when the shared helper landed.
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    claimed_nums = {n for n in (_branch_item_number(br, prefix) for br in claim_branches)
                    if n is not None}
    titles = _queue_titles(queue_text)
    for num in queue_item_numbers(queue_text):
        if item_status.get(num, "planned") != "planned":
            continue
        if num in claimed_nums:
            continue
        if num in gate_blocked:
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
        # "none left" is a claim about the ground checked, not the repository —
        # an unresolved gate is the one reason nothing is claimable that a
        # reader would otherwise have no way to see (conventions.md §8).
        ppath = docs_dir(repo_root, config) / "progress.md"
        plines = ppath.read_text(encoding=_ENCODING).splitlines() if ppath.is_file() else []
        # Attribute the empty result to a gate ONLY when a gate actually
        # explains it: an `all` gate, or a gate reaching an item that is still
        # open in a queue we just scanned. A gate holding unrelated items — or
        # naming nothing — is not why this run found no work, and blaming it
        # would be a false explanation, which is worse than none.
        _, _, gate_item_status = _parse_item_status(plines) if plines else ([], [], {})
        queued = set()
        for qt in candidates:
            queued.update(queue_item_numbers(qt))
        open_items = {n for n in queued
                      if gate_item_status.get(n, "planned") == "planned"}
        def _reached(g):
            if g.blocks_all:
                return set(open_items)
            if g.stage is not None:
                return set(stage_item_numbers(plines, g.stage)) & open_items
            return set(g.blocks) & open_items

        relevant = [(n, g) for n, g in enumerate(human_gates(plines), start=1)
                    if g.kind != "approved" and (g.blocks_all or _reached(g))]
        if relevant:
            print("none left — held by an unresolved human gate:")
            for n, g in relevant:
                held = sorted(_reached(g))
                where = "everything" if g.blocks_all else (
                    f"{g.reach} — holding " + ", ".join(f"{i:03d}" for i in held))
                print(f"  gate {n}: {g.text} — blocks {where}")
            print("  A person decides these, never an agent. Once decided: "
                  "aide gate approve <n> --evidence \"…\" (or gate decline <n>).")
            return 0
        print("none left")
        return 0
    number, title = pick
    branch = f"{prefix}{number:03d}-{_slug(title)}"

    # What this claim branches off, and what its `merge` will return it to.
    # `switch -c` already branches from whatever is checked out, so claiming
    # from a queue branch has always branched correctly — only the merge target
    # was fixed. Inferring the base from a *recognised queue branch* (never from
    # an arbitrary branch, which would silently retarget a merge) closes that
    # half without asking every caller to pass a flag it cannot know.
    current = _current_branch(repo_root)
    base = args.base or (current if _is_queue_branch(current, prefix)
                         else str(config["git"].get("main_branch", "main")))

    if not _local_branch_exists(repo_root, base):
        print(f"aide claim: base '{base}' is not a local branch — an item is "
              f"branched from its base and merged back into it, so the base "
              f"must be a branch this checkout can update", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"would claim item {number:03d} -> {branch} ({title}); base {base}")
        return 0
    # Branch FROM the base, explicitly. `switch -c` with no start point uses
    # HEAD, which would let the branch's actual starting point disagree with
    # the base it records — claiming with `--base main` while a queue branch is
    # checked out would start from the queue branch and then merge the whole of
    # it into main. Naming the start point makes the two agree by construction.
    git(["switch", "-c", branch, base], repo_root)
    _record_branch_base(repo_root, branch, base)
    if mode != "local":
        git(["push", "-u", "origin", branch], repo_root)
    note = "" if base == str(config["git"].get("main_branch", "main")) else f" (base {base})"
    print(f"claimed item {number:03d}: {branch} — {title}{note}")
    return 0


def _find_claim_branch(repo_root: Path, prefix: str, number: int) -> Optional[str]:
    for br in _list_claim_branches(repo_root, prefix):
        if _branch_item_number(br, prefix) == number:
            return br
    return None


def cmd_merge(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    branch = args.branch or _find_claim_branch(repo_root, prefix, args.number)
    if not branch:
        print(f"aide merge: no claim branch found for item {args.number:03d}", file=sys.stderr)
        return 1

    # Where this item lands: --base > what the claim recorded > main_branch.
    # Hard-wiring main_branch is what forced a consumer to merge every item of a
    # queue by hand — the queue file, a roadmap deliverable and nine item specs
    # lived only on the queue branch and had to land as one reviewed PR, so each
    # item needed to merge *back into* that branch.
    main = resolve_base(repo_root, config, args.base, branch)
    if not _local_branch_exists(repo_root, main):
        detail = ("it resolves, but not to a local branch — `git switch` would "
                  "detach HEAD, and a merge into a detached HEAD updates no "
                  "branch while still reporting success"
                  if _ref_exists(repo_root, main) else "no such local branch")
        print(f"aide merge: base '{main}' cannot be merged into: {detail}. "
              f"Pass a local branch as --base.", file=sys.stderr)
        return 1

    if mode == "pr":
        git(["push", "-u", "origin", branch], repo_root)
        print(f"aide merge (pr mode): pushed {branch}. Open a PR against {main} "
              f"to land it (e.g. 'gh pr create'); merge is left to the human "
              f"review gate.")
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


def _branch_item_number(branch: str, prefix: str) -> Optional[int]:
    """Item number claimed by *branch*, or None when it is not a claim branch.

    A claim branch is ``<branch_prefix>NNN-short-name`` (conventions.md §4), so
    the number must sit *immediately* after the prefix. Anchoring is what makes
    this correct: queue numbers and item numbers share one namespace with no
    syntactic marker between them, so an unanchored digit search reads
    ``aide/queue-016`` as item 016 — an unrelated, usually long-finished work
    item — and ``aide/specs-queue-015`` likewise.

    That misread is not cosmetic. ``gc`` targets any branch whose item is ✅ and
    deletes it with ``git branch -D`` plus a remote delete, independently of
    ``--merged``; under the old unanchored match that destroyed an in-flight
    queue branch, and the unreviewed queue file and item specs living only on it.
    """
    m = re.match(re.escape(prefix) + r"0*(\d+)(?:-|$)", branch)
    return int(m.group(1)) if m else None


#: Branches the framework itself tells authors to create that are deliberately
#: NOT item claims: `/aide-create-queue`'s hand-off and `/aide-run-roadmap` name
#: `<prefix>queue-NNN`, `/aide-spec-queue` names `<prefix>specs-queue-NNN`.
#: Recognised positively so they are reported as what they are, rather than
#: lumped in with a branch nothing can parse.
_QUEUE_BRANCH_RE = re.compile(r"(?:specs-)?queue-\d+$")


def _is_queue_branch(branch: str, prefix: str) -> bool:
    """True when *branch* is a queue/specs-queue branch rather than a claim."""
    return (branch.startswith(prefix)
            and _QUEUE_BRANCH_RE.match(branch[len(prefix):]) is not None)


def _has_origin(repo_root: Path) -> bool:
    out = git(["remote"], repo_root, check=False).stdout
    return "origin" in out.split()


# --------------------------------------------------------------------------- #
# Base refs — what a claim branched from, and what its merge returns to
# --------------------------------------------------------------------------- #
#: Where a claim branch remembers its base. A git-config key under the branch's
#: own section, so it travels with the branch through switch/rebase and needs no
#: file in the repo. It is deliberately *local* config: the base is a fact about
#: this checkout's branching, not something to commit and share. A machine that
#: never ran the `claim` falls back to `main_branch`, and `--base` is always
#: available — nothing silently merges somewhere unexpected.
_BASE_CONFIG_KEY = "aide-base"


def _record_branch_base(repo_root: Path, branch: str, base: str) -> None:
    git(["config", f"branch.{branch}.{_BASE_CONFIG_KEY}", base],
        repo_root, check=False)


def _recorded_branch_base(repo_root: Path, branch: str) -> Optional[str]:
    if not branch:
        return None
    res = git(["config", "--get", f"branch.{branch}.{_BASE_CONFIG_KEY}"],
              repo_root, check=False)
    value = res.stdout.strip()
    return value or None


def _current_branch(repo_root: Path) -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"],
               repo_root, check=False).stdout.strip()


def _ref_exists(repo_root: Path, ref: str) -> bool:
    return git(["rev-parse", "--verify", "--quiet", ref],
               repo_root, check=False).returncode == 0


def _local_branch_exists(repo_root: Path, ref: str) -> bool:
    """True only for an existing **local branch**, not any resolvable ref.

    A base must be a local branch, and merely resolving is not enough: `git
    switch` on a tag, a raw commit or a remote-tracking ref like `origin/main`
    detaches HEAD. A merge into a detached HEAD updates no branch at all, yet
    still reports success and lets the claim branch be deleted — the work
    survives only as an unreferenced commit. So the check is on the ref's
    *kind*, not its existence.
    """
    return git(["show-ref", "--verify", "--quiet", f"refs/heads/{ref}"],
               repo_root, check=False).returncode == 0


def _remote_or_local(repo_root: Path, ref: str) -> str:
    """``origin/<ref>`` when it resolves, else *ref* unchanged.

    Used where the question is "what has this branch actually diverged from" —
    the remote-tracking ref is what CI compares against and what the branch will
    merge into, and a local ref sitting behind the work answers that wrongly.
    """
    if _has_origin(repo_root):
        remote = f"origin/{ref}"
        if _ref_exists(repo_root, remote):
            return remote
    return ref


def resolve_base(repo_root: Path, config: Dict[str, Dict[str, object]],
                 explicit: Optional[str] = None,
                 branch: Optional[str] = None) -> str:
    """The base ref for a branch: explicit ``--base`` > recorded > config.

    ``main_branch`` stays the default and is never removed as one — this only
    adds the two ways a branch can legitimately have a *different* base, which
    is what stacked work produces: a queue branch's items branch off it and must
    merge back into it, so the whole queue lands as one reviewed PR.
    """
    if explicit:
        return explicit
    if branch is None:
        branch = _current_branch(repo_root)
    recorded = _recorded_branch_base(repo_root, branch)
    if recorded:
        return recorded
    return str(config["git"].get("main_branch", "main"))


# --------------------------------------------------------------------------- #
# Scope check — a branch's diff against its item's `## Authorised paths`
# --------------------------------------------------------------------------- #
_AUTHORISED_HEADING = "## Authorised paths"
#: The two sub-lists of that section (conventions.md §1), matched case- and
#: punctuation-insensitively so `**May change:**`, `**May change**` and
#: `May change:` all read the same.
_MAY_CHANGE_LABEL = "may change"
_ASSERTS_LABEL = "asserts against"

#: Loop bookkeeping the `aide` CLI and the agent roles are mandated to write on
#: *any* item, whatever that item is about — so a change to one is never
#: evidence of scope creep, and listing them would force every spec to repeat
#: the same boilerplate bullets just to pass. Kept explicit and wildcard-free so
#: the set cannot silently grow into a scope hole:
#:
#: - ``progress.md`` — rewritten by ``aide progress set`` on every item.
#: - ``insights.md`` — the compound-engineering inbox; conventions.md §1 names
#:   appending to it as the one write allowed outside an agent's edit scope, so
#:   flagging it would punish exactly the behaviour the framework requires.
#:
#: The item's own spec is authorised separately, by number, in ``cmd_scope`` —
#: the builder records Decisions & Trade-offs there on every item.
_ALWAYS_AUTHORISED = ("progress.md", "insights.md")


class AuthorisedPaths(NamedTuple):
    """The two lists of an item spec's ``## Authorised paths`` section."""

    may_change: List[str]
    asserts_against: List[str]


def _strip_dot_slash(path: str) -> str:
    """Drop a leading ``./``, and only that.

    Never ``lstrip("./")``, which strips leading *characters* from that set and
    so silently renames the dotfiles specs routinely authorise —
    ``.gitattributes`` to ``gitattributes``, ``.github/workflows/ci.yml`` to
    ``github/workflows/ci.yml`` — turning a declared path into one that matches
    nothing git ever reports.
    """
    while path.startswith("./"):
        path = path[2:]
    return path


def _sub_list_label(line: str) -> Optional[str]:
    """The normalised sub-list label on *line*, or None if it is not one."""
    text = line.strip().strip("*_").strip().rstrip(":").strip().lower()
    if text == _MAY_CHANGE_LABEL:
        return _MAY_CHANGE_LABEL
    if text == _ASSERTS_LABEL:
        return _ASSERTS_LABEL
    return None


def _bullet_path(line: str) -> Optional[str]:
    """The repo-relative path a section bullet declares, or None.

    A bullet is ``- `path` — why``: the path is the FIRST backtick span, never
    the whole body, because the reason that follows it is prose. Falls back to
    the text before the first dash/colon separator for a bullet written without
    backticks. Returns None for a bullet that declares no path — an unfilled
    ``{{slot}}`` (``aide check`` already errors on those, so failing here as
    well would report one authoring slip twice) or a literal "None."
    """
    stripped = line.strip()
    if not stripped or stripped[0] not in "-*+":
        return None
    body = stripped[1:].strip()
    if not body or "{{" in body:
        return None
    m = re.search(r"`([^`]+)`", body)
    if m:
        candidate = m.group(1)
    else:
        candidate = re.split(r"\s+[—–-]\s+|:", body, maxsplit=1)[0]
    candidate = candidate.strip().strip("`").strip()
    if not candidate or candidate.rstrip(".").lower() == "none":
        return None
    return _strip_dot_slash(candidate)


def declares_nothing(parsed: Optional[AuthorisedPaths]) -> bool:
    """True when a spec's scope cannot be compared with anything.

    An **empty May change is not the same as nothing declared**: a
    stage-validation item legitimately changes only the loop bookkeeping every
    item may write, while still pinning the tree it validates under *Asserts
    against*. Treating that as undeclared would drop exactly the specs whose
    whole purpose is to assert — so the test is that *both* lists are empty.
    """
    return parsed is None or not (parsed.may_change or parsed.asserts_against)


def parse_authorised_paths(text: str) -> Optional[AuthorisedPaths]:
    """Parse an item spec's ``## Authorised paths`` section.

    Returns None when the section is absent — distinct from a present-but-empty
    section (``AuthorisedPaths([], [])``), because the two need different
    remedies and neither may be read as "unconstrained" (conventions.md §1).

    Bullets appearing before either sub-list label are read as **May change**,
    which is what makes the flat single-list form — the shape consumers wrote
    before the labels existed — parse correctly rather than silently empty.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _AUTHORISED_HEADING:
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start, len(lines)):
        if _ANY_HEADER_RE.match(lines[i]) and lines[i].strip() != _AUTHORISED_HEADING:
            end = i
            break

    may_change: List[str] = []
    asserts_against: List[str] = []
    current = may_change
    for line in lines[start:end]:
        label = _sub_list_label(line)
        if label is not None:
            current = may_change if label == _MAY_CHANGE_LABEL else asserts_against
            continue
        path = _bullet_path(line)
        if path is not None:
            current.append(path)
    return AuthorisedPaths(may_change, asserts_against)


def path_matches(changed: str, pattern: str) -> bool:
    """True when repo-relative *changed* is covered by *pattern*.

    Three forms, per conventions.md §1:

    - ``dir/**`` — the directory and anything at any depth below it.
    - any other pattern containing ``*``, ``?`` or ``[`` — an ordinary shell
      glob matched **per path segment**, so ``tests/golden/*.json`` covers a
      JSON file in that directory but not one a level deeper. Anchoring per
      segment is the point: ``fnmatch``'s ``*`` crosses ``/`` and would quietly
      widen every glob a spec writes into a subtree wildcard.
    - anything else — an exact path.
    """
    pattern = _strip_dot_slash(pattern.strip())
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return changed == prefix or changed.startswith(prefix + "/")
    if any(ch in pattern for ch in "*?["):
        pat_parts = pattern.split("/")
        path_parts = changed.split("/")
        if len(pat_parts) != len(path_parts):
            return False
        return all(fnmatch.fnmatchcase(p, g) for p, g in zip(path_parts, pat_parts))
    return changed == pattern


def scope_findings(changed: List[str], authorised: AuthorisedPaths,
                   always: Tuple[str, ...] = ()) -> Tuple[List[str], List[str]]:
    """``(unauthorised, contradictions)`` for a branch's *changed* paths.

    A contradiction is a path the spec declared under **Asserts against** — "my
    tests pin this without changing it" — and then changed anyway. It is
    reported separately from an unauthorised path because the remedy differs:
    one widens a list, the other means an assertion in this very item is now
    asserting against state the item moved.
    """
    unauthorised = [p for p in changed
                    if p not in always
                    and not any(path_matches(p, g) for g in authorised.may_change)]
    contradictions = [p for p in changed
                      if any(path_matches(p, g) for g in authorised.asserts_against)]
    return unauthorised, contradictions


def _scope_base_ref(repo_root: Path, config, explicit: Optional[str]) -> str:
    """The ref ``scope`` diffs against: ``--base`` > the branch's recorded base
    > ``main_branch``.

    An explicit ``--base`` is used **verbatim** — the caller named a ref, so
    silently substituting ``origin/`` for it would make ``--base main`` mean
    something the caller did not write, and leave no way to ask for the local
    ref at all. The two *derived* answers do prefer their ``origin/``
    counterpart, since neither was chosen by anyone.

    The remote-tracking preference is the footgun this exists to avoid: on a
    checkout whose local ``main`` sits behind the work, the merge-base with it
    *is* it, so every file the earlier items touched gets reported against the
    current item's spec. Consulting the recorded base first is what makes the
    verb correct on stacked work — an item claimed from a queue branch has
    diverged from *that*, not from ``main``, and diffing against ``main`` would
    report every sibling item already merged into the queue.
    """
    if explicit:
        return explicit
    return _remote_or_local(repo_root, resolve_base(repo_root, config))


def cmd_scope(args: argparse.Namespace) -> int:
    """Check that this branch's changed files stay inside the item's spec.

    The diff-time counterpart to a byte-hash "scope fence": it asserts the
    claim the fence encoded — "item N changed only these files" — once, on the
    branch, instead of enshrining it as a suite assertion that outlives its
    truth and goes red the moment a later item is authorised to touch the
    pinned file (conventions.md §1).

    Exit 0 in scope · 1 something changed outside it · 2 could not check.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))

    number = args.number
    if number is None:
        branch = _current_branch(repo_root)
        if _is_queue_branch(branch, prefix):
            print(f"aide scope: {branch} is a queue branch, not an item claim — "
                  "per-item scope is checked on each claim branch as it merges "
                  "here, and a queue branch legitimately aggregates many items' "
                  "authorised paths. Nothing to check.")
            return 0
        number = _branch_item_number(branch, prefix)
        if number is None:
            print(f"aide scope: cannot tell which item to check — branch "
                  f"'{branch}' is not {prefix}NNN-short-name. Name the item "
                  f"explicitly: aide scope NNN", file=sys.stderr)
            return 2

    idir = docs_dir(repo_root, config) / "items"
    specs = sorted(idir.glob(f"{number:03d}-*.md")) if idir.is_dir() else []
    if not specs:
        print(f"aide scope: no spec for item {number:03d} under {idir}",
              file=sys.stderr)
        return 2
    spec = specs[0]
    rel_spec = spec.relative_to(repo_root).as_posix()

    authorised = parse_authorised_paths(spec.read_text(encoding=_ENCODING))
    if declares_nothing(authorised):
        what = ("has no '## Authorised paths' section" if authorised is None
                else "declares no path under '## Authorised paths'")
        print(f"aide scope: {rel_spec} {what} — cannot check scope. This is "
              "reported, never passed silently: an undeclared spec is not an "
              "unconstrained one. Add the section (see conventions.md §1) and "
              "re-run.", file=sys.stderr)
        return 2

    base = _scope_base_ref(repo_root, config, args.base)
    mb = git(["merge-base", base, "HEAD"], repo_root, check=False)
    if mb.returncode != 0:
        print(f"aide scope: could not resolve a merge-base with '{base}' — "
              f"{mb.stderr.strip()}", file=sys.stderr)
        return 2
    diff = git(["diff", "--name-only", mb.stdout.strip()], repo_root, check=False)
    if diff.returncode != 0:
        print(f"aide scope: git diff failed — {diff.stderr.strip()}",
              file=sys.stderr)
        return 2

    changed = [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]
    ddir_rel = docs_dir(repo_root, config).relative_to(repo_root).as_posix()
    always = tuple(f"{ddir_rel}/{name}" for name in _ALWAYS_AUTHORISED) + (rel_spec,)
    unauthorised, contradictions = scope_findings(changed, authorised, always)

    for path in contradictions:
        print(f"error: {path} changed, but {rel_spec} lists it under "
              "'Asserts against' as pinned-not-changed")
    for path in unauthorised:
        print(f"error: {path} not authorised by {rel_spec}")

    total = len(unauthorised) + len(contradictions)
    if total:
        print(f"aide scope: FAIL (item {number:03d}, {total} of {len(changed)} "
              f"changed file(s) outside scope, vs {base})")
        return 1
    print(f"aide scope: OK (item {number:03d}, {len(changed)} changed file(s) "
          f"all authorised, vs {base})")
    return 0


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

    if not args.no_fetch and mode != "local" and _has_origin(repo_root):
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    branch = _current_branch(repo_root)
    # Report divergence from the base this branch actually has, not always from
    # main — on stacked work the interesting distance is to the queue branch.
    main = resolve_base(repo_root, config, args.base, branch)
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

    # Outcome targets not yet ✅ Met — the goal-level state a summary table's
    # stage icons deliberately do not carry (conventions.md §1).
    ppath = docs_dir(repo_root, config) / "progress.md"
    if ppath.is_file():
        plines = ppath.read_text(encoding=_ENCODING).splitlines()
        for n, g in enumerate(human_gates(plines), start=1):
            if g.kind == "approved":
                continue
            reach = g.reach
            label = {"declined": "❌ declined", "awaiting": "⏳ awaiting a decision"}.get(
                g.kind, "⚠ unrecognised status")
            print(f"  gate {n}: {g.text} [blocks {reach}] — {label}")
        for t in outcome_targets(plines):
            if t.kind == "met":
                continue
            label = {"not-met": "❌ not met", "unverified": "❓ unverified"}.get(
                t.kind, "⚠ unrecognised status")
            objs = f" [{', '.join(t.objectives)}]" if t.objectives else ""
            print(f"  target: {t.text}{objs} — {label}")

    branches = _list_claim_branches(repo_root, prefix)
    if branches:
        for br in branches:
            num = _branch_item_number(br, prefix)
            if num is None:
                kind = "queue branch" if _is_queue_branch(br, prefix) else "unrecognised"
                print(f"  branch: {br} ({kind} — not an item claim)")
                continue
            st = item_status.get(num, "planned")
            stale = " — STALE (item ✅; run 'aide gc')" if st == "complete" else ""
            print(f"  claim: {br} (item {num:03d}: {st}){stale}")
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


def _merged_prefixed_branches(repo_root: Path, main: str, prefix: str) -> List[str]:
    """Prefixed local branches already merged into *main*, per git itself."""
    out = git(["branch", "--merged", main, "--format=%(refname:short)"],
              repo_root, check=False).stdout
    return [l.strip() for l in out.splitlines() if l.strip().startswith(prefix)]


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many}"


def _gc_empty_notes(repo_root: Path, prefix: str, main: str,
                    merged_flag: bool, local: List[str],
                    remote: List[str]) -> List[str]:
    """Why an empty ``gc`` result may still leave cleanup available.

    Two things the bare message hides. First, the default invocation checks
    only the item ground, so a branch that no longer resolves to an item —
    every queue and specs-queue branch — is structurally invisible to it while
    ``--merged`` would take it. Second, `gc` only ever looks at branches under
    ``prefix``, so a merged branch named anything else is never considered on
    either ground.

    Returns [] when there is genuinely nothing further to say, so the common
    case stays a single terse line. The ``--merged`` probe runs only on this
    empty path, never in the normal one.
    """
    notes: List[str] = []
    if not merged_flag and (local or remote):
        extra = _merged_prefixed_branches(repo_root, main, prefix)
        if extra:
            notes.append(
                f"{_plural(len(extra), 'branch', 'branches')} under '{prefix}' "
                f"{'is' if len(extra) == 1 else 'are'} merged into {main} — "
                f"'aide gc --merged' will take {'it' if len(extra) == 1 else 'them'}")
    others = [b for b in _local_branches(repo_root)
              if not b.startswith(prefix) and b != main]
    if others:
        notes.append(
            f"{_plural(len(others), 'local branch', 'local branches')} outside "
            f"the '{prefix}' scope {'was' if len(others) == 1 else 'were'} not "
            f"considered — gc only ever manages claim branches")
    return notes


def cmd_gc(args: argparse.Namespace) -> int:
    """Delete claim branches whose work has landed (item ✅ in progress.md, or
    ``--merged`` branches already merged into main). Dry-run by default; pass
    ``--yes`` to delete. The one destructive verb in the CLI, so it is never
    implicit."""
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    # The `--merged` ground is "already merged into <base>", so it takes a base
    # like everything else: on stacked work the branches that have landed have
    # landed into the queue branch, and asking about `main` finds none of them.
    main = resolve_base(repo_root, config, args.base)

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
        merged_local = _merged_prefixed_branches(repo_root, main, prefix)

    targets: Dict[str, str] = {}  # branch -> reason
    for br in sorted(set(local) | set(remote)):
        # Only a positively-identified item claim is deletable on the "item is
        # ✅" ground. A queue branch shares the number namespace but not the
        # lifecycle: it aggregates many items and lands as one reviewed PR, so
        # deleting it because some same-numbered item finished would discard
        # unreviewed work. It stays eligible under --merged, where the ground
        # is "already merged into main" and is checked against git itself.
        num = _branch_item_number(br, prefix)
        if num is not None and item_status.get(num) == "complete":
            targets[br] = f"item {num:03d} is ✅"
        elif br in merged_local:
            targets[br] = f"merged into {main}"

    if not targets:
        # "Nothing to clean" is a claim about the ground and the scope this run
        # actually checked, not about the repository — say which. The default
        # invocation checks only the item ground, and every invocation ignores
        # branches outside `prefix` (deliberately: gc is the one destructive
        # verb and must not delete branches it does not own). Left unqualified,
        # the message reads as "no cleanup is available here" and the next
        # reach is the raw `git branch -d` the CLI exists to replace.
        print("aide gc: nothing to clean")
        for note in _gc_empty_notes(repo_root, prefix, main, args.merged, local, remote):
            print(f"  {note}")
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
    p_check.add_argument("--queue", type=int, default=None,
                         help="also check this queue's specs against each other "
                              "(scope overlaps, pinned state, dependency graph)")
    p_check.add_argument("--report", default=None,
                         help="with --queue: write the findings as JSON to this path")
    p_check.set_defaults(func=cmd_check)

    p_prog = sub.add_parser("progress", help="edit progress.md status / acceptance")
    p_prog.add_argument("action", choices=["set", "accept"])
    p_prog.add_argument("number", type=int,
                        help="item number (set) | stage number (accept)")
    p_prog.add_argument("status", nargs="?", default=None, help="set: in-progress | done")
    p_prog.add_argument("--criterion", type=int, default=None,
                        help="accept: 1-based acceptance-criterion index within the stage")
    p_prog.add_argument("--all", action="store_true", dest="all_criteria",
                        help="accept: every acceptance criterion in the stage")
    p_prog.add_argument("--evidence", default=None,
                        help="accept: annotation appended to the ticked criterion")
    p_prog.add_argument("--no-commit", action="store_true", help="edit only, do not git commit")
    p_prog.set_defaults(func=cmd_progress)

    p_gate = sub.add_parser("gate", help="list / resolve human gates in progress.md")
    p_gate.add_argument("action", choices=["list", "approve", "decline"])
    p_gate.add_argument("number", type=int, nargs="?", default=None,
                        help="1-based gate row (approve/decline); see `aide gate list`")
    p_gate.add_argument("--evidence", "--reason", dest="note", default=None,
                        help="decision note written into the gate's last cell")
    p_gate.add_argument("--no-commit", action="store_true", help="edit only, do not git commit")
    p_gate.set_defaults(func=cmd_gate)

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
    p_claim.add_argument("--base", default=None,
                         help="branch this claim off, and merge it back into "
                              "(default: the current branch when it is a queue "
                              "branch, else main_branch)")
    p_claim.add_argument("--dry-run", action="store_true", help="print the pick, do not create/push a branch")
    p_claim.set_defaults(func=cmd_claim)

    p_merge = sub.add_parser("merge", help="merge a validated item per git.mode")
    p_merge.add_argument("number", type=int)
    p_merge.add_argument("branch", nargs="?", default=None, help="claim branch (default: found from number)")
    p_merge.add_argument("--base", default=None,
                         help="merge into this ref (default: what the claim "
                              "recorded, else main_branch)")
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
                      help="also delete claim branches already merged into the base")
    p_gc.add_argument("--base", default=None,
                      help="ref --merged is measured against (default: the "
                           "current branch's recorded base, else main_branch)")
    p_gc.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    p_gc.set_defaults(func=cmd_gc)

    p_status = sub.add_parser("status", help="one-call roadmap-state report (branch, queues, claims, PRs)")
    p_status.add_argument("--no-fetch", action="store_true", help="skip the fetch --all --prune preflight")
    p_status.add_argument("--base", default=None,
                          help="ref to report ahead/behind against (default: the "
                               "current branch's recorded base, else main_branch)")
    p_status.set_defaults(func=cmd_status)

    p_scope = sub.add_parser("scope",
                             help="check this branch's diff against the item's authorised paths")
    p_scope.add_argument("number", type=int, nargs="?", default=None,
                         help="item number (default: read from the current claim branch)")
    p_scope.add_argument("--base", default=None,
                         help="base ref to diff against (default: origin/<main_branch>, "
                              "falling back to the local ref)")
    p_scope.set_defaults(func=cmd_scope)


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
