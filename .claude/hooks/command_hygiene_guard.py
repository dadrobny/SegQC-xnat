#!/usr/bin/env python
"""Claude Code hook: enforce AIDE command hygiene on Bash tool calls.

Registered on ``PreToolUse`` for ``Bash`` in ``.claude/settings.json``. It is
the *enforcement* layer for the command-hygiene contract documented once in
``.aide/conventions.md`` §3 — the doc explains **why**, this hook guarantees the
mechanical rules are **followed** regardless of whether a (sub-)agent read the
doc. Without it, a reshapeable command that misses the allow-list stalls an
unattended run on a permission prompt; with it, the offending shape is bounced
back to the agent with the fix, so the run self-corrects and stays unattended.

Contract (mirrors the companion logging hook):
- Reads the PreToolUse hook JSON on stdin (``tool_name``, ``tool_input`` …).
- On a **high-confidence** mechanical violation it writes a corrective message
  to **stderr** and exits **2** — a non-zero PreToolUse exit blocks the tool
  call and surfaces stderr to the agent, which then reshapes and retries.
- Otherwise it writes nothing and exits **0** (no opinion — defer to the
  allow-list / normal permission flow).

Design rules:
- **Fail-open.** Any parse error, unexpected payload shape, or internal
  exception exits 0 (allow). A guard bug must never wedge the loop; the worst
  case is falling back to the ordinary permission prompt.
- **Narrow and conservative.** Only the unambiguous, high-frequency offenders
  are flagged, and string literals are blanked first so operators *inside* a
  commit message or quoted argument never trigger a false positive. Positive-
  form guidance (use the venv-relative path, the ``aide`` CLI form) is left to
  the agent prose in ``.aide/conventions.md`` §3 — a hook can reject a wrong
  shape but cannot supply the right one.
"""

import json
import re
import sys


def _blank_quoted(cmd):
    """Replace single/double-quoted spans with spaces.

    Operators (``&&``, ``;``, ``$(`` …) inside a string literal — most commonly
    a commit message — must not be read as shell syntax. Blanking preserves
    offsets so nothing outside the quotes shifts.
    """
    out = []
    quote = None
    for ch in cmd:
        if quote:
            out.append(" ")
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _blank_single_quoted(cmd):
    """Blank only single-quoted spans (where bash treats ``$(``/backticks as
    literal text). Inside double quotes they still substitute, so those spans
    must stay visible to rule 4."""
    out = []
    quoted = False
    for ch in cmd:
        if quoted:
            out.append(" ")
            if ch == "'":
                quoted = False
        elif ch == "'":
            quoted = True
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _framework_local_path():
    """``[framework] local_path`` from aide.toml (cwd = repo root), or None.

    The documented framework-update workflow operates on a second repo (the
    framework clone), which structurally needs ``git -C`` — the one legitimate
    use. Declaring that clone's path here gives it a narrow carve-out from
    rule 1 instead of leaving the workflow a dead end.
    """
    try:
        with open("aide.toml", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    in_framework = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_framework = s == "[framework]"
        elif in_framework and s.split("=", 1)[0].strip() == "local_path":
            value = s.split("=", 1)[1].split("#", 1)[0].strip().strip("\"'")
            return value or None
    return None


def _git_c_is_declared_framework_repo(cmd):
    m = re.search(r"\bgit\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)", cmd)
    if not m:
        return False
    declared = _framework_local_path()
    if not declared:
        return False
    import os
    target = m.group(1).strip("\"'")
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.abspath(p)))
    return norm(target) == norm(declared)


def violations(cmd):
    """Return a list of (title, fix) for each hygiene rule ``cmd`` breaks."""
    bare = _blank_quoted(cmd)
    found = []

    # 1. No `cd` prefix / `git -C <path>` — cwd is already the repo root and the
    #    prefix breaks allow-list prefix matching (this repo's path has spaces).
    #    Exception: `git -C <[framework] local_path>` — the documented
    #    framework-update workflow legitimately targets that second repo.
    if re.match(r"\s*cd\s", cmd) or (
        re.search(r"\bgit\s+-C\b", bare) and not _git_c_is_declared_framework_repo(cmd)
    ):
        found.append(
            "Drop the `cd`/`git -C` prefix: the Bash tool's cwd is already the "
            "repo root, and the prefix breaks allow-list matching. Run the bare "
            "command. (Exception: `git -C` targeting the [framework] local_path "
            "declared in aide.toml.)"
        )

    # 2. One command per Bash call — `&&`, `||`, `;` sequencing isn't
    #    auto-approved. A single `|` pipe (e.g. `git branch -r | grep aide/`) is
    #    fine and is NOT flagged; a `\;` (find -exec terminator) is excluded.
    if re.search(r"&&|\|\|", bare) or re.search(r"(?<!\\);", bare):
        found.append(
            "Split into one command per Bash call: `&&`, `||`, `;` chaining "
            "isn't auto-approved (a single `|` pipe like `git branch -r | grep "
            "aide/` is fine). Issue each command as its own Bash call."
        )

    # 3. No stderr redirection — the Bash tool already captures stderr.
    if re.search(r"2>&1|2>|&>|>&", bare):
        found.append(
            "Remove the stderr redirection (`2>&1`, `2>`, `&>`): the Bash tool "
            "already captures stderr."
        )

    # 4. No command substitution in a commit message — never auto-approved.
    #    Checked on a blanked command like the other rules, but blanking only
    #    single-quoted spans: there bash keeps "$(...)"/backticks literal
    #    (prose), while inside double quotes they still substitute for real.
    no_single = _blank_single_quoted(cmd)
    if re.search(r"\bgit\s+commit\b", bare) and ("$(" in no_single or "`" in no_single):
        found.append(
            "No `$(...)`/backtick command substitution in a commit: it's never "
            'auto-approved. Use `-m "msg"` (repeat `-m` for paragraphs) or '
            "`git commit -F <file>`."
        )

    # 5. Recon via the Bash tool with `grep`, not PowerShell `Select-String` —
    #    only `Bash(...)` rules are allow-listed.
    if re.search(r"\bSelect-String\b", bare):
        found.append(
            "Use `grep` via the Bash tool, not `Select-String`: only Bash rules "
            "are allow-listed."
        )

    return found


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    payload = json.loads(raw)

    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return 0

    issues = violations(cmd)
    if not issues:
        return 0

    lines = [
        "Command-hygiene violation — this shape isn't auto-approved and would "
        "stall an unattended run. Reshape and retry:",
    ]
    lines += [f"  - {fix}" for fix in issues]
    lines.append("Full contract + rationale: .aide/conventions.md §3.")
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        # Fail-open: never let a guard bug block or wedge a real tool call.
        code = 0
    sys.exit(code)
