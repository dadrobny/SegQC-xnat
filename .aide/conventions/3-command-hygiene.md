## 3. Command hygiene (canonical rules)

These rules keep shell commands robust, legible, and failure-localised on **any**
runtime — they hold whether or not a runtime has a permission model. This section
is the single canonical statement of the rules and their rationale.

An adapter **delivers** this section to its own roles in *positive form*, so the
correct shape is in context before the first command rather than learned from a
rejection. Delivering it once, through whatever always-loaded channel the
runtime has, is the contract; restating it inside every role spec is how the
copies drift. How the rules are **enforced**, and any provider-specific
**command shaping** a permission policy demands on top of them, are likewise
adapter concerns — see the adapter's README.

The rules (runtime-general):

- **If an `aide` verb covers it, the raw git form is wrong.** Session preflight
  (fetch, clean-tree check, landing on the right branch) is `aide sync
  [--item NNN]`; claiming is `aide claim`; starting a queue or specs-queue
  branch is `aide queue start NNN [--specs]`; landing is `aide merge`; branch
  clean-up is `aide gc`; checking a branch's changed files against its item's
  authorised paths is `aide scope`. Do not improvise the equivalent `git
  fetch`/`git status`/`git switch -c`/`git diff --name-only` sequences — the verbs
  exist so every run does these steps identically and no step is forgotten.
- **One command per call.** Never chain with `&&`, `||` or `;` — separate calls
  localise failures and keep each invocation legible. A single `|` pipe
  (`git branch -r | grep aide/`) is fine: a pipeline is one command, and the
  failure it can hide is its own exit status, not a second command's.
- **No `cd` prefix and no directory-changing wrapper** — `git -C "<path>"`,
  `git --git-dir=<path>`, `git --work-tree=<path>`, or a `GIT_DIR=<path>`/
  `GIT_WORK_TREE=<path>` prefix all point git at a repo other than cwd, and
  all four are redundant and brittle the same way `cd` is (a repo path
  containing spaces or apostrophes breaks quoting). The tool's working
  directory is already the repo root — run the bare command. **Unless the repo
  is declared**: a project may legitimately span more than one repo, and an
  adapter may let the operator name the others in personal, machine-local
  config. A command whose repo-override paths all resolve to one declared repo
  is allowed; one naming two different repos stays blocked even when both are
  declared, because history read from one and applied to another's working tree
  is a shape no legitimate workflow needs. Declaring a repo relaxes this rule
  and grants nothing else — the command must still clear whatever permission
  policy the runtime applies.
- **No `2>&1`** or other redirections — the tool already captures stderr.
- **No command substitution in commits.** Avoid `$(…)`/backticks; use single-line
  `-m "msg"`, repeated `-m` for paragraphs, or `git commit -F <file>`.

The `aide` CLI always runs as `python .aide/scripts/aide.py <cmd>` — stdlib-only
and venv-independent, so it works before any project venv exists and identically
across runtimes.

**Python and pytest run from the project venv by relative path** —
`.venv/Scripts/python -m pytest` on Windows, `.venv/bin/python -m pytest` on
macOS and Linux. Relative, because the working directory is already the repo
root (above), so the same command holds in any checkout and needs no absolute
path that only resolves on the machine that wrote it. The venv's interpreter
rather than a bare `python`/`pytest`, because a bare name runs whatever the PATH
reaches first — which is how a suite passes against a dependency set the project
never pinned.

**Against a declared sibling repo** (§8), the CLI needs no `cd` and no git-style
wrapper either — run the *sibling's own install* with an explicit root:

```
python <sibling>/.aide/scripts/aide.py --repo <sibling> <cmd>
```

Both halves matter. The sibling's install, because two consumers may sit on
different engine versions and each repo's documents should be judged by the
engine that shipped with them. And `--repo`, because without it the CLI resolves
its root by walking up from **cwd** — which is the current repo, so the
sibling's engine would silently operate on the wrong project's documents.
