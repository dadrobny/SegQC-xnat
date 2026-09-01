# AIDE — rules that bind before anything points at them

**Framework-owned**: the installer maintains this file; edits here are lost on
the next update. It carries only what must bind *before* anything points
anywhere.

The rest of the contract is [`conventions.md`](conventions.md), an **index** — a
pointer to `§N` resolves to `conventions/N-*.md`. Each heading below names the
section carrying its full treatment; when a decision is not obvious, go read it.

## Durable artifacts must read cold — §1

Item specs, `insights.md` entries, commit messages and issue bodies outlive the
session that produced them. Write for the reader who opens one months from now
with none of the conversation.

1. **No chat-local identifiers.** A label coined for one conversation's
   convenience resolves only for someone who was there. Name a thing by what it
   is; title a change by the change.
2. **Cross-reference by resolvable identity** — an issue number, a file path, a
   commit, a stage number, a dated `insights.md` entry. Never "the companion PR"
   or "as discussed above".
3. **Record the decision and why it holds, not the route to it.** "My earlier
   lean was wrong", "agreed direction", "settled while drafting" narrate a
   process the reader was not part of.

## Out-of-scope learning is captured, never acted on — §1 → `insights.md`

Noticing something true but outside the current task means appending **one line**
to `docs/aide/insights.md` and returning to the task. Capturing is always
allowed; acting on it out of scope is not.

```
- [ ] <knowledge|defect|gap|automation|framework> — <one line> *(item NNN, YYYY-MM-DD, engine X.Y.Z)*
```

The date is required. What precedes it is free-form provenance and says where
the insight came from: `item NNN` from inside an item, `queue-NNN` from planning
done before any item exists, `items NNN-NNN` for a finding spanning several, or
nothing at all. What follows it is the engine version the observation was made
under — one read of `.aide/VERSION`, and the date cannot stand in for it.

A captured claim is **immutable**: never reworded, reordered or deleted, not even
when it turns out to be wrong. Ticking its checkbox is the one in-place edit, and
`aide insights tick N --pointer` owns it; anything that happens to it afterwards
goes in dated lines indented beneath it.

## Status lives in one place — §1 → `progress.md`

`docs/aide/progress.md` is the single source of truth for what is done, and the
only place the CLI reads. A status claim written anywhere else — a checklist in a
spec, a "current focus" heading, a summary in a README — is a second truth that
will disagree with the first. Move it, do not copy it.

## Root documents go through their entry point — §5

`vision.md` and `roadmap.md` are authored via the loop's create-vision /
create-roadmap entry points, never written free-hand — the entry point carries
the safeguards a direct file write skips. Authoring them is interactive
regardless of `loop.clarify`: ask until the mandatory sections are grounded in
the human's answers, and present the result as a draft. A wrong assumption at
the root propagates into every queue and item derived from it.

## Mechanical actions go through the CLI — §2, §4, [`README.md`](README.md)

```
python .aide/scripts/aide.py check | status | env | sync | claim | scope
    | merge | gc | progress set/accept | gate list/approve/decline
    | insights list/tick/archive | queue start/tidy
```

Prefer the verb to hand-editing a document or improvising git: it is what keeps
the documents parseable and an unattended run reproducible.

## Command hygiene — §3

One command per call; no `cd`; no chained `&&`; no `2>&1`. A long unattended run
stalls on a permission prompt for any command shape nothing pre-approved.

## Only a person resolves a human gate — §1 → Human gates

Any role may *raise* a gate — the worst case is work pausing. No agent may
approve or decline one: a gate exists precisely because the decision is not
derivable from the work.

## Another repository's instructions bind before you edit it — §8

A runtime loads instruction files for the working directory's repo only. A
sibling repo declared in `.aide/loop/loop.local.toml` — the framework clone
included — gets nothing, and nothing announces the gap. Read that repo's own
instruction file before acting inside it; where two repos disagree about a file,
the repo that owns the file wins.
