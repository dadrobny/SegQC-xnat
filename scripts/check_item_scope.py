#!/usr/bin/env python3
"""Diff-based scope check for an AIDE work item (item 107).

Replaces the byte-hash "scope fence" pytests removed by item 107. A scope
fence encoded a *diff-time* claim -- "item N did not modify file X" -- as a
*permanent runtime invariant* -- "X equals these bytes forever" -- which is
false the moment a later item is legitimately authorised to edit X. This
script asserts the diff-time claim directly, on the branch, once, instead of
enshrining it as a suite assertion that outlives its truth.

Usage::

    python scripts/check_item_scope.py <spec-path> [--base <ref>]

Reads the ``## Authorised paths`` section of the given item spec (one glob
per Markdown bullet, e.g. ``- `src/segfacet/foo.py` `` or ``- `dir/**` ``),
computes the changed-file set as ``git diff --name-only $(git merge-base
<base> HEAD)`` (merge-base, not a two-dot/tip diff, so commits landing on the
base branch after this branch forked are not misreported), and checks every
changed path against the authorised globs.

Glob semantics:

- An entry with no ``*`` matches only that exact repo-relative path.
- An entry ending in ``/**`` matches any path at any depth below that
  directory (the directory itself is not a path, so nothing "below" an empty
  string is matched by ``**`` alone).

A small, explicit set of paths (see ``_ALWAYS_AUTHORISED_PATHS``) is treated
as authorised for every item regardless of its spec's list -- currently just
``docs/aide/progress.md``, which the ``aide`` CLI itself rewrites on every
item as loop bookkeeping, not item work.

Exit codes:

- ``0`` -- every changed path is authorised (including a zero-change diff).
- ``1`` -- one or more changed paths are not authorised; each is printed as
  ``<path> not authorised by <spec>``.
- ``2`` -- the spec has no ``## Authorised paths`` section, or the section is
  present but empty; this is always an error, never a silent pass.

No third-party imports, no network access. Requires a ``git`` executable on
PATH and a working tree that is a git repository.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SECTION_HEADING = "## Authorised paths"
_BULLET_PATTERN_CHARS = "-*+"

# Paths that are always authorised, regardless of what any spec's
# `## Authorised paths` section lists. Kept minimal and explicit -- no
# directories, no wildcards -- so this set cannot silently grow into a scope
# hole. `docs/aide/progress.md` is loop bookkeeping: `python
# .aide/scripts/aide.py progress set` rewrites it on every single item as
# part of the claim protocol, not as item work, so a diff touching it is
# never evidence of scope creep and every spec would otherwise have to
# repeat the same boilerplate bullet just to pass this check.
_ALWAYS_AUTHORISED_PATHS = frozenset({"docs/aide/progress.md"})


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _parse_authorised_paths(spec_text: str) -> list[str] | None:
    """Return the glob list from ``## Authorised paths``, or None if missing.

    An empty list (section present, zero bullets) is distinguished from a
    missing section by returning ``[]`` vs ``None`` respectively -- both are
    treated as an error by the caller (AC8), but the distinction keeps the
    parser's contract honest.
    """
    lines = spec_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _SECTION_HEADING:
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## ") and stripped != _SECTION_HEADING:
            end = i
            break

    globs: list[str] = []
    for line in lines[start:end]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] not in _BULLET_PATTERN_CHARS:
            continue
        # Strip the bullet marker, then optional backtick fencing.
        body = stripped[1:].strip()
        body = body.strip("`").strip()
        if body:
            globs.append(body)
    return globs


def _path_matches(changed_path: str, glob: str) -> bool:
    if glob.endswith("/**"):
        prefix = glob[: -len("/**")]
        return changed_path == prefix or changed_path.startswith(prefix + "/")
    return changed_path == glob


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that a branch's changed files stay within an "
        "item spec's `## Authorised paths`."
    )
    parser.add_argument("spec", type=Path, help="path to the item spec markdown file")
    parser.add_argument(
        "--base",
        default="main",
        help="base ref to diff against (default: main)",
    )
    args = parser.parse_args(argv)

    spec_path: Path = args.spec
    if not spec_path.exists():
        print(f"spec not found: {spec_path}", file=sys.stderr)
        return 2

    spec_text = spec_path.read_text(encoding="utf-8")
    globs = _parse_authorised_paths(spec_text)
    if not globs:
        print(
            f"{spec_path}: missing or empty '## Authorised paths' section "
            "-- this is a hard error, never a silent pass",
            file=sys.stderr,
        )
        return 2

    cwd = Path.cwd()

    merge_base = _run_git(["merge-base", args.base, "HEAD"], cwd)
    if merge_base.returncode != 0:
        print(
            f"could not resolve merge-base for base ref '{args.base}': "
            f"{merge_base.stderr.strip()}",
            file=sys.stderr,
        )
        return 2
    merge_base_sha = merge_base.stdout.strip()

    diff = _run_git(["diff", "--name-only", merge_base_sha], cwd)
    if diff.returncode != 0:
        print(f"git diff failed: {diff.stderr.strip()}", file=sys.stderr)
        return 2

    changed = [line for line in diff.stdout.splitlines() if line.strip()]

    violations = [
        path
        for path in changed
        if path not in _ALWAYS_AUTHORISED_PATHS
        and not any(_path_matches(path, g) for g in globs)
    ]

    if violations:
        for path in violations:
            print(f"{path} not authorised by {spec_path}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
