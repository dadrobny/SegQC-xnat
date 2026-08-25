# AIDE — rules that bind before anything points at them

This file is **framework-owned**: the installer maintains it, and edits made here
are overwritten on the next update. It is imported into the project's default
instructions so it is in context from the first message, which is the whole
reason it exists — everything else the framework knows lives in
[`conventions.md`](conventions.md) and is read only when something points at it.
That works for an agent told what to read. It fails for an interactive session,
where a person and the runtime produce durable artifacts with no agent spec in
play.

So this page carries only what must bind *before* the first read. Each rule
names its full treatment; when a decision is not obvious, go read that.

## Durable artifacts must read cold

Everything the loop produces outlives the session that produced it: item specs,
`insights.md` entries, commit messages, issue bodies. Write for the reader who
opens it months from now with none of the conversation.

1. **No chat-local identifiers.** A label coined for one conversation's
   convenience is scaffolding, not a name — it resolves only for someone who was
   there. Name a thing by what it is; title a change by the change.
2. **Cross-reference by resolvable identity** — an issue number, a file path, a
   commit, a stage number, a dated `insights.md` entry. Never "the companion PR"
   or "as discussed above".
3. **Record the decision and why it holds, not the route to it.** "My earlier
   lean was wrong", "agreed direction", "settled while drafting" narrate a
   process the reader was not part of, and they age badly.

Full treatment: `conventions.md` §1.

## Out-of-scope learning is captured, never acted on

Noticing something true but outside the current task means appending **one line**
to `docs/aide/insights.md` and returning to the task. Capturing is cheap and
always allowed; acting on it out of scope is not.

```
- [ ] <knowledge|defect|gap|automation|framework> — <one line> *(item NNN, YYYY-MM-DD)*
```

A captured claim is **immutable** — never reworded, reordered or deleted, not
even when it turns out to be wrong. Ticking its checkbox is the one in-place
edit; anything that happens to it afterwards goes in dated lines indented
beneath it. Full treatment: `conventions.md` §1 → `insights.md`.

## Status lives in one place

`docs/aide/progress.md` is the single source of truth for what is done, and the
only place the CLI reads. A status claim written anywhere else — a checklist in a
spec, a "current focus" heading, a summary in a README — is a second truth that
will disagree with the first. Move it, do not copy it. Full treatment:
`conventions.md` §1 → `progress.md`.

## Mechanical actions go through the CLI

Document edits, claims, merges, scope and status checks have verbs:

```
python .aide/scripts/aide.py check | claim | scope | progress set | merge | sync
```

Prefer the verb to hand-editing a document or improvising git. It is what keeps
the documents parseable and what makes an unattended run reproducible. Full
surface: `conventions.md` §2 and §4, and [`README.md`](README.md).

## Command hygiene

One command per call; no `cd`; no chained `&&`; no `2>&1`. These exist so a
long unattended run does not stall on a permission prompt for a command shape
nothing pre-approved. Full treatment: `conventions.md` §3.

## Only a person resolves a human gate

Any role may *raise* a gate — the worst case is work pausing. No agent may
approve or decline one: a gate exists precisely because the decision is not
derivable from the work. Full treatment: `conventions.md` §1 → Human gates.

## Another repository's instructions bind before you edit it

A runtime loads instruction files for the working directory's repo only. A
sibling repo declared in `.aide/loop/loop.local.toml` — the framework clone
included — gets nothing, and nothing announces the gap. Read that repo's own
instruction file before acting inside it; where two repos disagree about a file,
the repo that owns the file wins. Full treatment: `conventions.md` §8.
