### Status icons (the only six)

| Icon | Meaning | Rank |
|------|---------|------|
| 📋 | Planned | 0 |
| 🚧 | In Progress | 3 |
| 🔍 | In Review | 4 |
| ✅ | Complete | 5 |
| ⏸️ | Deferred | 2 |
| ❌ | Excluded | 1 |

Rank is used when one item is referenced on several lines: the most-advanced
status wins.

**✅ means merged — in every `git.mode`.** It is written by `aide merge` when
the merge actually happens, not by an agent ahead of one. 🔍 is the state
between: the work is pushed and awaiting a human's merge. It exists because ✅
used to mean two different things depending on the mode — merged under
`auto-merge`, *pushed and awaiting review* under `pr` — while everything
downstream read it as "done", including `aide gc`, whose default ground is "the
item is ✅" and whose action is `git branch -D` plus a remote delete. The
exhaustion sweep therefore offered to delete the head branch of an open PR, and
the line a human was asked to approve read like confirmation. A run must be
stable under either mode, so the mode no longer changes what a status asserts.

A 🔍 item **holds its stage at 🚧** (an open PR has not shipped) and **holds its
queue open**. `aide check` does not call its claim branch stale, and `aide
status` reports it as awaiting review rather than recommending `gc`. Because in
`pr` mode nothing inside the loop ever observes the merge, `aide sync` and `aide
status` name any 🔍 item whose work has since landed in the base and print the
`aide progress set NNN done` that closes it — the same content check `gc` uses,
so it needs no forge call that could silently degrade to "no open PRs found".

**Structural positions only.** The parsers read icons *only* at structural
positions: a table row's **Status (last) cell**, a stage header's **trailing**
`— <icon>`, and the **leading** icon of a deliverable bullet. An icon anywhere
else — prose, mid-bullet, a title — is plain text and is never read as status,
so authors need not avoid the icon vocabulary in free text. `aide check` still
*warns* on such stray icons in the status-bearing documents (`progress.md`,
queue files) so they stay unambiguous for human readers; other documents are
not scanned.
