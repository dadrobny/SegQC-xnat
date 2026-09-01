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
  are flagged, and string literals and heredoc bodies are blanked first so
  operators *inside* a commit message — quoted, or piped via
  ``git commit -F - <<'EOF'`` — never trigger a false positive. Positive-
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


#: A heredoc opener CANDIDATE: `<<` or `<<-`, then the delimiter word, whose
#: quoting decides whether the body interpolates. `(?<!<)` / `(?!<)` keep a
#: `<<<` here-string (which has no body) from matching at either offset. The
#: delimiter must sit on the opener's own line (`[ \t]*`, never a newline).
#: A match is only a candidate — `_heredoc_body_spans` still rejects one that
#: is not in redirection position, or sits inside quotes or `((…))`
#: arithmetic, where `<<` is prose or a shift, not a redirection.
_HEREDOC_OPEN_RE = re.compile(
    r"(?<!<)<<(?!<)(?P<dash>-?)[ \t]*"
    r"(?:'(?P<sq>[^'\n]+)'|\"(?P<dq>[^\"\n]+)\"|\\(?P<bs>\S+)"
    r"|(?P<bare>[A-Za-z0-9_][A-Za-z0-9_.-]*))"
)


def _heredoc_body_spans(cmd):
    """Every heredoc body in *cmd*, as ``(start, end, interpolates)`` character
    spans over the raw command.

    A heredoc body is data on stdin, not commands — ``;``, ``&&``, ``2>&1`` in
    its prose are never shell syntax, so the body must be invisible to the
    operator lints exactly as a quoted string is (issue #88: the guard blocked
    the multi-paragraph commit messages the framework itself asks for, via
    ``git commit -F - <<'EOF'``). The one thing that IS live in a body is
    ``$(…)``/backtick substitution, and only under an unquoted delimiter
    (``<<EOF``) — a quoted one (``<<'EOF'``, ``<<"EOF"``, ``<<\\EOF``) keeps
    the body fully literal — hence the ``interpolates`` flag, which lets rule 4
    keep watching the bodies where substitution really runs.

    The body runs from the line after its opener to the terminator line (bare
    delimiter; ``<<-`` also strips leading tabs; a trailing ``\\r`` is
    tolerated so a CRLF command does not read as unterminated). Several
    openers on one line stack their bodies in order. An unterminated body
    extends to the end — which is what the shell does with it too.

    A candidate that is not actually a redirection is REJECTED, because a
    phantom opener's "body" runs to the end of the input and would blank —
    i.e. exempt from every rule — everything after it. Rejected: an opener
    inside an already-collected body (prose quoting a heredoc); one not in
    redirection position (must follow start-of-line, whitespace, ``|``,
    ``&``, ``;`` or ``(`` — so ``a<<b`` never fires, which forgoes bash's
    mid-word redirection — including the spaceless ``-<<'EOF'`` spelling of
    ``git commit -F -`` — and the ``3<<EOF`` fd form, in exchange for never
    misreading a shift or prose, the pre-existing posture for those); one
    under an unclosed ``((`` seen outside quotes, where ``<<`` shifts; and
    one inside quotes, where it is a string. A rejected candidate's body
    text stays visible to the lints, which is exactly the pre-#88 behaviour
    for that command. Known residual: `#` comments are not parsed, so a
    ``<<WORD`` in a trailing comment still passes the gauntlet and blanks
    the rest of the call.

    Quote and arithmetic state come from ONE forward scan shared by every
    candidate (``_advance``), never a per-candidate rescan from the start —
    the hook runs on every Bash call, and rescanning made it quadratic in
    the candidate count. The scan skips collected bodies (a body is data: an
    apostrophe or ``((`` in its prose opens nothing), and only a ``((`` seen
    outside quotes counts as arithmetic, so a quoted ``"(("`` — a grep
    pattern, say — suppresses no later heredoc.
    """
    spans = []
    # (quote char | None, unclosed-(( depth, scan position, spans consumed)
    state = [None, 0, 0, 0]

    def _advance(pos):
        """Fold cmd[state-position:pos) into the quote/arithmetic state."""
        quote, arith, i, skip = state
        while i < pos:
            if skip < len(spans) and i >= spans[skip][0]:
                i = max(i, spans[skip][1])
                skip += 1
                continue
            ch = cmd[i]
            if quote:
                if quote == '"' and ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch == "\\":
                i += 2
                continue
            elif ch in "'\"":
                quote = ch
            elif ch == "(" and cmd[i:i + 2] == "((":
                arith += 1
                i += 2
                continue
            elif ch == ")" and cmd[i:i + 2] == "))" and arith:
                arith -= 1
                i += 2
                continue
            i += 1
        state[:] = [quote, arith, i, skip]

    mem = 0  # membership pointer — spans and candidates both ascend
    for m in _HEREDOC_OPEN_RE.finditer(cmd):
        while mem < len(spans) and spans[mem][1] <= m.start():
            mem += 1
        if mem < len(spans) and spans[mem][0] <= m.start():
            continue
        prev = cmd[m.start() - 1] if m.start() else ""
        if prev and prev not in " \t\n|&;(":
            continue
        _advance(m.start())
        if state[0] is not None or state[1]:
            continue
        delim = m.group("sq") or m.group("dq") or m.group("bs") or m.group("bare")
        interpolates = m.group("bare") is not None
        prev_end = spans[-1][1] if spans else 0
        nl = cmd.find("\n", max(m.end(), prev_end))
        if nl == -1:
            continue  # single-line call: the body isn't in this command at all
        start = nl + 1
        end = len(cmd)  # unterminated → the rest of the input is the body
        i = start
        while i < len(cmd):
            j = cmd.find("\n", i)
            line = cmd[i:j] if j != -1 else cmd[i:]
            line = line.rstrip("\r")
            if (line.lstrip("\t") if m.group("dash") else line) == delim:
                end = i  # up to, not including, the terminator line
                break
            if j == -1:
                break
            i = j + 1
        spans.append((start, end, interpolates))
    return spans


def _blank_spans(cmd, spans):
    """Space out the given ``(start, end)`` spans, newlines kept so every
    offset and line boundary outside them survives."""
    out = list(cmd)
    for start, end in spans:
        for i in range(start, end):
            if out[i] != "\n":
                out[i] = " "
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
    """``[framework] local_path`` from ``.aide/loop/loop.local.toml`` (cwd =
    repo root), or None.

    The documented framework-update workflow operates on a second repo (the
    framework clone), which structurally needs a directory-targeting git
    invocation (``-C``, or the ``--git-dir``/``--work-tree``/``GIT_DIR=``/
    ``GIT_WORK_TREE=`` equivalents) — the one legitimate use. Declaring that
    clone's path here gives it a narrow carve-out from rule 1 instead of
    leaving the workflow a dead end.

    Read from the **personal, gitignored** loop config, never from the shared
    ``aide.toml`` — a machine-specific filesystem path has no business in a
    committed file (the same principle ``aide.toml``'s own ``[validation]``
    section states for its profiles). Copy
    ``.aide/loop/loop.local.toml.example`` to ``.aide/loop/loop.local.toml``
    and add a ``[framework]`` section with ``local_path`` to set this up
    per-machine; nothing here is shared or committed.
    """
    try:
        with open(
            ".aide/loop/loop.local.toml", encoding="utf-8"
        ) as fh:
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


def _hygiene_extra_repos():
    """``[hygiene] extra_repos`` from ``.aide/loop/loop.local.toml``, as a list.

    One project can legitimately span two repos developed together — a library
    and a sibling programme repo, say. Without a declaration the guard refuses
    every git operation against the sibling, while `git init` and plain file
    writes (which take a path argument) sail through: an agent could create the
    repo and write into it but never `add`/`commit`, leaving the work
    uncommitted for a human to finish by hand.

    Named ``[hygiene]`` for its only consumer — *this guard*. The section
    relaxes one lint and grants no permission: a command against a declared
    repo still has to match the allow-list to auto-approve, and `git -C …`
    matches none of the `Bash(git <subcommand>:*)` rules, so it prompts. That
    is the intended posture — the guard exists to stop shapes that would stall
    an unattended run, not to be a trust boundary, and unblocking the honest
    spelling of a legitimate operation is the whole point.

    Deliberately NOT read from the shared, committed ``aide.toml``: these are
    machine-specific filesystem paths, same reasoning as
    ``[framework] local_path``.
    """
    try:
        with open(".aide/loop/loop.local.toml", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []

    in_hygiene = False
    buf = None
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if buf is None:
            if stripped.startswith("["):
                in_hygiene = stripped == "[hygiene]"
                continue
            # Require the `=` before splitting on it. A bare `extra_repos` line
            # would otherwise IndexError, and because the hook fails open that
            # would silently disable the ENTIRE guard — every rule, not just
            # this key — off the back of one typo in a personal config file.
            if not in_hygiene or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if key.strip() != "extra_repos":
                continue
            buf = value.strip()
            # Documented as an array, so anything else is a config we do not
            # understand. Inferring a grant from an undocumented shape is the
            # wrong default for a key that relaxes a guard: no array, no grant.
            if not buf.startswith("["):
                return []
        else:
            # A new section header ends the array whether or not it closed.
            # Without this the header's own `]` satisfies the check below and
            # an unterminated array yields a PARTIAL grant — the real paths
            # plus a junk `[loop` entry — which is precisely the "malformed
            # config grants nothing" posture inverted. A hand parser cannot be
            # exhaustive here; this covers the shape a truncated array actually
            # takes, and anything it still cannot parse grants nothing.
            if stripped.startswith("[") and stripped.endswith("]"):
                return []
            buf += " " + stripped
        # A TOML array may span lines; keep accumulating until it closes. An
        # array left unterminated falls out of the loop and grants nothing.
        if "]" not in buf:
            continue
        inner = buf[1:buf.index("]")]
        return [p for p in
                (item.strip().strip("\"'") for item in inner.split(","))
                if p]
    return []


def _declared_repo_paths():
    """Every repo path rule 1 tolerates: the framework clone plus any
    ``[hygiene] extra_repos``. Empty when nothing is declared, which keeps the
    default posture — every repo-override form blocked — exactly as it was."""
    paths = list(_hygiene_extra_repos())
    framework = _framework_local_path()
    if framework:
        paths.append(framework)
    return paths


#: Every syntax git (or the shell, ahead of git) accepts for "operate on a
#: repo/working-tree other than cwd" — `-C` is only one of four. A regex that
#: recognised `-C` alone left `--git-dir`/`--work-tree` (git's own flags) and
#: the `GIT_DIR=`/`GIT_WORK_TREE=` environment-variable prefixes wide open:
#: the exact same operation, spelled three other ways, none of them caught.
#: An agent that hits the `-C` block and reaches for the next thing it knows
#: achieves the identical effect the exception was built to gate — the guard
#: must recognise all four forms or it is a lint an agent is rewarded for
#: evading, not a rule.
#:
#: Presence (this regex, no captured value — matched against the
#: quote-blanked ``bare`` text, same as every other rule here, so an operator
#: *inside* a commit message never false-positives) is checked separately
#: from the actual path VALUE (`_git_repo_override_paths`, matched with
#: quotes left visible — a legitimately quoted path containing a space
#: would itself be blanked to nothing in ``bare`` and silently vanish from a
#: value-capturing match, wrongly suppressing the trigger — though with
#: heredoc bodies removed, since a flag named in a commit message's prose is
#: not a path the command operates on).
_GIT_REPO_OVERRIDE_TRIGGER_RE = re.compile(
    r"\bgit\s+-C\b|--git-dir\b|--work-tree\b|\bGIT_DIR=|\bGIT_WORK_TREE="
)

_GIT_REPO_OVERRIDE_VALUE_RE = re.compile(
    r"(?:"
    r"\bgit\s+-C\s+(?P<c>\"[^\"]*\"|'[^']*'|\S+)"
    r"|--git-dir(?:=|\s+)(?P<gitdir>\"[^\"]*\"|'[^']*'|\S+)"
    r"|--work-tree(?:=|\s+)(?P<worktree>\"[^\"]*\"|'[^']*'|\S+)"
    r"|\bGIT_DIR=(?P<envdir>\"[^\"]*\"|'[^']*'|\S+)"
    r"|\bGIT_WORK_TREE=(?P<envtree>\"[^\"]*\"|'[^']*'|\S+)"
    r")"
)


#: Which capture groups belong to a `--git-dir`-flavoured flag, whose
#: conventional value is `<repo>/.git` (or a bare repo's own root) rather than
#: the repo root `--work-tree`/`-C`/`GIT_WORK_TREE=` expect. Comparing a
#: `--git-dir=<repo>/.git --work-tree=<repo>` pair against one declared path
#: with a single normalisation would reject that pairing as "two different
#: repos" even though it is the standard, correct way to spell `-C <repo>` —
#: so `--git-dir`/`GIT_DIR=` accept either the declared path itself or
#: `<declared>/.git`.
_GIT_DIR_FLAVOURED_GROUPS = frozenset({"gitdir", "envdir"})


def _git_repo_override_paths(cmd):
    """Every ``(group_name, path)`` argument to `-C`/`--git-dir`/`--work-tree`/
    `GIT_DIR=`/`GIT_WORK_TREE=` in *cmd* (quotes visible, heredoc bodies
    blanked — see `_GIT_REPO_OVERRIDE_TRIGGER_RE`'s docstring for why), in
    order. Empty if
    *cmd* uses none of them, or a flag is present with no parseable value."""
    paths = []
    for m in _GIT_REPO_OVERRIDE_VALUE_RE.finditer(cmd):
        group, value = next(
            (k, v) for k, v in m.groupdict().items() if v is not None
        )
        paths.append((group, value.strip("\"'")))
    return paths


def _git_repo_override_all_declared(cmd):
    """True iff *cmd* names at least one repo-override path and every one of
    them resolves to **the same** declared repo — `[framework] local_path` or
    one of `[hygiene] extra_repos` (see `_declared_repo_paths`).
    `--git-dir`/`GIT_DIR=` accept `<declared>` or `<declared>/.git` (see
    `_GIT_DIR_FLAVOURED_GROUPS`); every other form must equal `<declared>`
    exactly.

    **One repo per command, even with several declared.** A command mixing two
    paths stays blocked whether or not both are declared: git history read from
    one repo and applied to another's working tree is exactly the confusing,
    dangerous shape no legitimate workflow needs, and widening the declaration
    list must not turn it into an approved combination. So each declared repo
    is tried in turn and the command must satisfy one of them wholly — never a
    union across them.
    """
    paths = _git_repo_override_paths(cmd)
    if not paths:
        return False
    declared_paths = _declared_repo_paths()
    if not declared_paths:
        return False
    import os
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.abspath(p)))

    def _all_match(declared):
        declared_norm = norm(declared)
        declared_dotgit_norm = norm(os.path.join(declared, ".git"))

        def _matches(group, path):
            target = norm(path)
            if group in _GIT_DIR_FLAVOURED_GROUPS:
                return target in (declared_norm, declared_dotgit_norm)
            return target == declared_norm

        return all(_matches(group, path) for group, path in paths)

    return any(_all_match(d) for d in declared_paths)


def violations(cmd):
    """Return a list of (title, fix) for each hygiene rule ``cmd`` breaks."""
    heredocs = _heredoc_body_spans(cmd)
    # Bodies are blanked BEFORE quote-blanking: a prose apostrophe ("it's")
    # inside a body would otherwise open a phantom quote and swallow real
    # syntax after the heredoc.
    data = _blank_spans(cmd, [(s, e) for s, e, _ in heredocs])
    bare = _blank_quoted(data)
    found = []

    # 1. No `cd` prefix, and no `-C`/`--git-dir`/`--work-tree`/`GIT_DIR=`/
    #    `GIT_WORK_TREE=` pointing git at a repo other than cwd — the Bash
    #    tool's cwd is already the repo root, and a directory prefix breaks
    #    allow-list prefix matching (this repo's path has spaces).
    #    Exception: every repo-override path in the command resolves to ONE
    #    declared repo — `[framework] local_path` (the documented
    #    framework-update workflow) or one of `[hygiene] extra_repos` (a
    #    project that legitimately spans several repos). Both are sourced from
    #    the personal .aide/loop/loop.local.toml, never aide.toml. Two
    #    different repos in one command stay blocked even when both are
    #    declared — see `_git_repo_override_all_declared`.
    #    The path VALUES are scanned on `data`, not the raw `cmd`: quotes must
    #    stay visible there (see _GIT_REPO_OVERRIDE_TRIGGER_RE's docstring) but
    #    heredoc bodies must not — `--git-dir=/junk` in a commit message's
    #    prose is not a second repo, and reading it as one re-blocks the exact
    #    `git -C <declared> commit -F - <<'EOF'` shape the body-blanking above
    #    exists to allow.
    has_override = bool(_GIT_REPO_OVERRIDE_TRIGGER_RE.search(bare))
    if re.match(r"\s*cd\s", cmd) or (
        has_override and not _git_repo_override_all_declared(data)
    ):
        found.append(
            "Drop the `cd` prefix, and drop `-C`/`--git-dir`/`--work-tree`/"
            "`GIT_DIR=`/`GIT_WORK_TREE=` — all four point git at a repo other "
            "than cwd, which is already the repo root; a directory prefix "
            "breaks allow-list matching. Run the bare command. (Exception: "
            "every repo-override path in the command targeting the SAME "
            "declared repo — [framework] local_path, or one of "
            "[hygiene] extra_repos, in .aide/loop/loop.local.toml, a personal, "
            "gitignored file; copy .aide/loop/loop.local.toml.example to set "
            "it up. Two different repos in one command stay blocked even when "
            "both are declared.) For the aide CLI against a declared repo, no "
            "cd is needed either: run that repo's own install with an explicit "
            "root, `python <repo>/.aide/scripts/aide.py --repo <repo> <verb>`."
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
    #    Heredoc bodies split the same way: literal under a quoted delimiter
    #    (<<'EOF'), live under an unquoted one (<<EOF) — so only the literal
    #    bodies are blanked here and rule 4 still sees real substitution.
    no_single = _blank_single_quoted(
        _blank_spans(cmd, [(s, e) for s, e, interp in heredocs if not interp])
    )
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
