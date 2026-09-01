#!/usr/bin/env python
"""Summarise which instruction files actually reach a context, and why.

Reads the JSONL written by ``.claude/hooks/log_instructions_loaded.py`` and
answers the question ADAPTER-SPEC §7 makes a contract point: is each rule being
*delivered*, or has it quietly degraded to a pointer nobody follows?

Three things it reports, in order of what they cost to get wrong:

1. **Rules that never loaded.** A `paths:`-scoped rule whose globs stopped
   matching is silently inert — the file is still there, still correct, and
   reaches nobody. This is the failure the whole mechanism exists to avoid, so
   it is reported first and it is the only one that sets a non-zero exit under
   ``--strict`` — an empty or missing log included, since nothing loaded there
   either. ``--strict`` is for a log you know covers work the rule should
   have matched; over a log of sessions that touched nothing relevant, a silent
   rule is the correct outcome, not a fault.
2. **Load reason per file**, since `session_start` and `path_glob_match` mean
   very different things: the first is a cost paid in every context, the second
   is a cost paid only where the rule is relevant.
3. **Per-session totals**, which is how a rule that fires far more often than
   expected — an over-broad glob — shows up.

What it deliberately does **not** claim: a file absent from the log was not
necessarily unread. A `Read` is never logged as a load, so an agent that
opened a conventions section by hand leaves no trace here. This measures
delivery, not reading.

Nor does it see a **preloaded section skill** (`.claude/skills/aide-*/SKILL.md`
named in an agent's `skills:` frontmatter). A preload is not an instruction
file to the runtime, so it never appears in this log — and it needs no
measuring: it is unconditional per spawn, so its cost is an exact structural
sum, printed by `tests/test_structural_budget.py` in the framework repo. Only
files actually in `.claude/rules/` are ever reported silent here; a rule the
framework has retired is removed from that directory by `install.py --update`
and is not a fault.

``--strict`` stays a human-invoked check, never a CI gate. The log has no
notion of which sessions *should* have armed a rule: a consumer's own
``paths:``-scoped rule beside the framework's is legitimately silent over
sessions that read nothing it matches, and a gate that fails on that teaches
the reader to ignore it. Reach is asserted structurally instead, in the
framework repo's ``tests/test_structural_budget.py``.

``--rotate`` archives the current log into ``log.reviewed.jsonl`` beside it
(``--reviewed`` to put it elsewhere) and truncates the live one, the way
``review_permissions.py --rotate`` does. Beside the *reviewed* log, not the
default one: rotating a log from another checkout must not mix its records
into this project's archive. A
log that only grows makes "never loaded" progressively less meaningful — it
averages over sessions from before a glob was last changed — so a review ends
with a rotation, and the next one starts from the sessions since.

Everything below the ``main`` boundary is a pure function so it can be unit
tested (see ``.claude/tests/test_instructions_loaded.py`` in this repo's
source tree).
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# The log and its archive live in a consumer repo and may be opened in a
# Windows editor, which prepends a BOM; `utf-8-sig` reads one transparently
# and reads plain UTF-8 unchanged (the same choice review_permissions.py makes).
_ENCODING = "utf-8-sig"

# .claude/scripts/review_instructions.py -> parents[2] is the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = _PROJECT_ROOT / "docs" / "aide" / "instructions" / "log.jsonl"
DEFAULT_REVIEWED = _PROJECT_ROOT / "docs" / "aide" / "instructions" / "log.reviewed.jsonl"
RULES_DIR = _PROJECT_ROOT / ".claude" / "rules"

EMPTY_HINT = (
    "The log is empty. Before reading that as 'nothing loads', check the three\n"
    "causes that produce an empty log with a perfectly healthy setup:\n"
    "  1. The project folder is not trusted, which silently disables every hook\n"
    "     in .claude/settings.json -- including the one that writes this log.\n"
    "  2. No session has run since the hook was installed.\n"
    "  3. The log was rotated by a review (--rotate) and no session has run\n"
    "     since; the reviewed records are in log.reviewed.jsonl beside it.\n"
)


def load_records(log_path):
    """Parsed JSONL records, skipping malformed lines rather than dying on one.

    A half-written final line is normal for a log appended to by a hook that
    may be killed with the session; refusing to report anything because of it
    would make the tool useless exactly when a run went wrong.
    """
    path = Path(log_path)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding=_ENCODING).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _rel(path_str, root=None):
    """A path as written relative to the project root, for stable grouping.

    Falls back to the original string: the log may carry an absolute path from
    another checkout, and mangling it into something that looks local would be
    worse than showing it as it is.

    `root` resolves at CALL time for the same reason `shipped_rules` does — a
    module-level default binds once, so redirecting `_PROJECT_ROOT` would leave
    this reading the original tree while its caller read the new one.
    """
    try:
        base = _PROJECT_ROOT if root is None else root
        return Path(path_str).resolve().relative_to(base).as_posix()
    except (ValueError, OSError):
        return path_str


def by_file(records):
    """``{relative path: Counter(reason)}`` over every path each record names."""
    out = defaultdict(Counter)
    for record in records:
        paths = record.get("paths") or []
        reason = record.get("reason") or "(unreported)"
        for path_str in paths:
            if isinstance(path_str, str) and path_str:
                out[_rel(path_str)][reason] += 1
    return dict(out)


def by_session(records):
    """``{session_id: load count}`` — an over-broad glob shows up as an outlier."""
    counts = Counter()
    for record in records:
        counts[record.get("session_id") or "(unknown)"] += len(record.get("paths") or [])
    return counts


def shipped_rules(rules_dir=None):
    """Rule files present on disk, project-relative, sorted.

    `rules_dir` defaults to `RULES_DIR` at CALL time, not at import time: a
    module-level default is bound once, so `RULES_DIR` could be redirected and
    every caller would keep reading the original directory — reporting "no
    silent rules" against a tree nobody asked about.
    """
    directory = Path(RULES_DIR if rules_dir is None else rules_dir)
    if not directory.is_dir():
        return []
    return sorted(_rel(str(p)) for p in directory.rglob("*.md"))


def silent_rules(records, rules_dir=None):
    """Shipped rule files that never appear in the log.

    Compared on the trailing path segments rather than the full path, because
    the runtime may report a rule by an absolute path from a different
    checkout, and a mismatch there would report every rule as silent — a
    false alarm on the one signal that is supposed to mean something.
    """
    seen = set()
    for record in records:
        for path_str in record.get("paths") or []:
            if isinstance(path_str, str) and path_str:
                seen.add(Path(path_str).name)
    return [rule for rule in shipped_rules(rules_dir)
            if Path(rule).name not in seen]


def render(records, rules_dir=None):
    """The whole report as lines. Pure, so a test can assert on it."""
    lines = []
    silent = silent_rules(records, rules_dir)
    if silent:
        lines.append("Rules that never loaded:")
        lines += [f"  ! {rule}" for rule in silent]
        lines.append("")
        lines.append("  A paths:-scoped rule only fires when a matching file is READ.")
        lines.append("  Confirm its globs still match before assuming it is broken.")
        lines.append("")
    else:
        lines.append("Rules that never loaded: none.")
        lines.append("")

    files = by_file(records)
    if files:
        lines.append("Loads per file, by reason:")
        for path in sorted(files, key=lambda p: (-sum(files[p].values()), p)):
            reasons = ", ".join(f"{reason} x{n}"
                                for reason, n in sorted(files[path].items()))
            lines.append(f"  {sum(files[path].values()):5d}  {path}  ({reasons})")
        lines.append("")

    sessions = by_session(records)
    if sessions:
        lines.append(f"Sessions: {len(sessions)}; "
                     f"loads: {sum(sessions.values())}; "
                     f"median per session: {_median(sorted(sessions.values()))}")
    return lines


def rotate_log(log_path, reviewed_path):
    """Move every line of ``log_path`` into ``reviewed_path`` and truncate the log.

    Returns the number of non-blank lines rotated. Lines are moved verbatim —
    a malformed one is archived, not dropped, since the archive is the record
    of what the hook wrote. Both files stay gitignored (per-machine). A
    missing log is a no-op returning 0; an empty one is normalised to empty.
    """
    log = Path(log_path)
    if not log.exists():
        return 0
    lines = [ln for ln in log.read_text(encoding=_ENCODING).splitlines() if ln.strip()]
    if not lines:
        log.write_text("", encoding="utf-8")
        return 0
    reviewed = Path(reviewed_path)
    reviewed.parent.mkdir(parents=True, exist_ok=True)
    with reviewed.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    log.write_text("", encoding="utf-8")
    return len(lines)


def _median(values):
    if not values:
        return 0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("log", nargs="?", default=str(DEFAULT_LOG),
                        help=f"path to the JSONL log (default: {DEFAULT_LOG})")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any shipped rule never loaded, an empty or "
                             "missing log included (a human-invoked check over a log "
                             "known to cover the rule's work; never a CI gate)")
    parser.add_argument("--reviewed", default=None,
                        help="where --rotate archives the log (default: "
                             "log.reviewed.jsonl beside the log being rotated, i.e. "
                             f"{DEFAULT_REVIEWED} for the default log)")
    parser.add_argument("--rotate", action="store_true",
                        help="archive the current log to the reviewed file and truncate "
                             "it, so the next review starts from the sessions since")
    args = parser.parse_args(argv)

    if args.rotate:
        reviewed = args.reviewed or Path(args.log).with_name(DEFAULT_REVIEWED.name)
        moved = rotate_log(args.log, reviewed)
        print(f"Rotated {moved} record(s) from {args.log} to {reviewed}.")
        return 0

    if not Path(args.log).is_file():
        # A mistyped path must not read as a clean, empty log: the hint below
        # explains an empty file, and a missing one is a different fact.
        print(f"{args.log}: no such file.\n")
    records = load_records(args.log)
    if not records:
        print(EMPTY_HINT)
        # Nothing loaded, so every shipped rule is silent: --strict says so
        # rather than passing the one log it can say nothing about.
        return 1 if args.strict and shipped_rules() else 0

    print("\n".join(render(records)))
    if args.strict and silent_rules(records):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
