<!-- reach: all
     No `paths:` block, so this loads in every session and every sub-agent —
     it is part of the always-on floor every spawn pays for. Deliberate: the
     hygiene rules bind any Bash call, and there is no file whose opening
     predicts one. See `tests/test_structural_budget.py` for the convention. -->

<!-- pins: .aide/conventions/3-command-hygiene.md
     Quoted from that section; `test_rule_pins.py` fails if either copy moves
     alone. The PowerShell bullet is unpinned — §3 leaves shaping to the adapter.
     - If an `aide` verb covers it, the raw git form is wrong
     - Never chain with `&&`, `||` or `;`
     - A single `|` pipe (`git branch -r | grep aide/`) is fine
     - No `cd` prefix and no directory-changing wrapper
     - Declaring a repo relaxes this rule and grants nothing else
     - No `2>&1`
     - No command substitution in commits
     - Python and pytest run from the project venv by relative path
     - The `aide` CLI always runs as `python .aide/scripts/aide.py <cmd>`
     - python <sibling>/.aide/scripts/aide.py --repo <sibling>
-->

# Command hygiene

The rules and the reasoning behind them are `.aide/conventions.md` §3. This file
is how they reach a Claude session; it is **delivery, not a second source of
truth**. A `PreToolUse` hook enforces the mechanical ones and bounces a
violating shape back with the fix, and an unattended run that emits a shape
nothing pre-approved stalls on a permission prompt — so getting them right first
time is what keeps a long run moving.

- **Use the Bash tool, not PowerShell**, for git / `aide` / venv / grep commands
  — only `Bash(...)` rules are allow-listed.
- **One command per Bash call.** Never chain with `&&`, `||` or `;`. A single
  `|` pipe (`git branch -r | grep aide/`) is fine.
- **No `cd` prefix and no directory-changing wrapper** — no `git -C`,
  `--git-dir`, `--work-tree` or `GIT_DIR=` either; the working directory is
  already the repo root. The one exception is a repo declared in
  `.aide/loop/loop.local.toml`, and **declaring a repo relaxes this rule and
  grants nothing else** (§3).
- **No `2>&1`** or other stderr redirection — the tool captures stderr already.
- **No command substitution in commits** — no `$(…)` or backticks in a commit
  message; use `-m "msg"`, repeated `-m` for paragraphs, or
  `git commit -F <file>`.
- **Python and pytest run from the project venv by relative path** —
  `.venv/Scripts/python -m pytest` on Windows, `.venv/bin/python -m pytest` on
  macOS and Linux. **The `aide` CLI always runs as
  `python .aide/scripts/aide.py <cmd>`**, which is stdlib-only and works before
  any venv exists. Against a declared sibling repo, run the sibling's own
  install with an explicit root —
  `python <sibling>/.aide/scripts/aide.py --repo <sibling> …` (§3) — never a
  `cd` or a cwd-resolved root.
- **If an `aide` verb covers it, the raw git form is wrong** — `aide sync`,
  `claim`, `queue start`, `merge`, `gc`, `scope`. Do not improvise the
  equivalent `git fetch` / `switch -c` / `diff --name-only` sequence.
