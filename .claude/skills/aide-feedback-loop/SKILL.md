---
name: aide-feedback-loop
description: Analyze issues and suggest improvements to the process and documents.
---

# Feedback Loop

Analyze what went wrong and identify improvements — Step 7 of the AIDE loop,
available at any point. Use whenever work didn't go smoothly: human intervention
needed, unclear requirements, process breakdown.

## Instructions

Analyze the current state of the project documents and recent work.

### 0. Triage the insight inbox (`docs/aide/insights.md`)

The roles capture out-of-scope insights as one-line inbox entries during
execution (see `.aide/conventions.md` §1 → `insights.md`); this step routes
them. It is the boundary for every type that lands in *this* project — a
`framework` entry may already have been handed over on capture, so expect some
to be ticked before you arrive.

**Read the backlog with the verb, not by opening the file:**

```
python .aide/scripts/aide.py insights list --open
```

The file interleaves closed and open entries, so reading it whole costs the
entire history to see a working set that is usually a dozen lines. Open the
file only when you need an entry's full context, and then only that entry.

For each **unchecked** entry, by type:

- **knowledge** → fold the fact into its owning document (`docs/`, `CLAUDE.md`,
  a living document, code comments) — smallest edit that preserves it.
- **defect / gap** → a **candidate item for the next queue**, which the queue
  PR then reviews. Do not fix it inline here — and do not tick it here: you are
  standing *at* the boundary, so the queue that would carry it does not exist
  yet. **Leaving the entry unchecked is the routing**, because the open inbox
  is an input to queue authoring (`.aide/conventions.md` §1 → `insights.md`):
  the next `/aide-create-queue` run reads `insights list --open`, and either
  queues the entry — ticking it with the item number it became — or says why it
  passed over it.
- **automation** → a candidate item that (a) implements the deterministic
  script/CLI verb and (b) edits the skill/agent prose to *mandate* it — both
  halves, or agents keep improvising. (Worked example: the `aide sync`/`aide
  gc` verbs replacing improvised git recon.) It reaches the next queue the same
  way a `defect`/`gap` entry does, and is ticked there, not here.
- **framework** → belongs to AIDE itself, not this project. If
  `[framework] repo` is set in `aide.toml` and `gh` is available, hand it
  over: `gh issue create --repo <owner/repo>` with a body carrying the
  observation and a proposal, and **opening with the engine version the
  observation was made under** (this stays `ask`-gated — a human confirms).
  Otherwise leave the entry unchecked with a `(pending handover)` note.

  That version is the body's **first line**, before the observation
  (`.aide/conventions.md` §1 → `insights.md`):

  ```
  **Project:** <this repo> (consumer). **Observed under engine X.Y.Z**
  (<item ref>, YYYY-MM-DD).
  ```

  **Writing that header is yours; a form on the framework repo cannot reach
  it** — `--body` bypasses any issue template that repo publishes, and no
  template can reach a body composed here and passed on the command line. It
  costs nothing, because **you already hold the fact**: the version comes from
  the entry's own marker (`*(item 042, 2026-08-29, engine 1.22.0)*`). If the
  entry carries none, read `.aide/VERSION` and write it as *the version at
  triage time, not at capture* — say so in the body. The framework repo cannot
  see this one, so an unmarked guess reads there as an observed fact, and every
  claim about an older engine is then re-verified by hand.

Tick each entry you routed *here* — a `knowledge` fold, a handed-over
`framework` issue — with the verb, naming where it landed, never by editing the
line by hand, which is how a claim gets silently reworded:

```
python .aide/scripts/aide.py insights tick 7 --pointer "docs/architecture.md"
```

That appends `→ docs/architecture.md` to the entry and flips its checkbox.

A `defect`, `gap` or `automation` entry is **not** one of those, so that command
is not for it: it is ticked by the queue that absorbs it, and you leave it open.

Never reword, reorder or delete a captured claim — including one that turned
out to be wrong; the correction goes *beneath* it, as a dated line in the
entry's status trail, which is what the same command writes when the entry is
**already** ticked:

```
- [x] defect — <the original claim, never touched> *(item 117, 2026-08-20)*
  - **2026-09-02** → superseded: the fence it names was retired by item 121
```

Use the trail for anything after the first routing — a re-route, a resolution,
a premise that decayed. Add one when you find a ticked entry whose status you
now know to be stale; that is triage too, and it is what stops the next reader
re-deriving it.

When the closed history has grown past the live working set, propose an
`insights archive --before <date>` to the human — it is a dry run until `--yes`,
and it renumbers the entries that remain, so it belongs at the *end* of a triage
pass, never the middle.

### 1. Document gaps

- What should have been in `docs/aide/vision.md` but wasn't?
- What should have been in `docs/aide/roadmap.md` (dependencies, prerequisites)?
- What should have been in `docs/aide/progress.md` for tracking?
- Was the work item specification missing critical information? Were its
  **Assumptions** wrong or missing?

### 2. Process issues

- Did the human need to intervene? Why?
- Were requirements unclear (would `loop.clarify = "interactive"` have helped)?
- Were dependencies not identified upfront?
- Did scope expand unexpectedly?

### 3. Framework adaptations needed

The framework surface is: `.aide/` (conventions, templates, `aide.py`, loop),
`aide.toml`, `.claude/skills/aide-*`, `.claude/commands/aide-*`,
`.claude/agents/`. Consider:

- Should a template in `.aide/templates/` gain/lose a section for this project's
  needs? (Add project-specific blocks via the item template's guidance, not
  boilerplate.)
- Should an `aide.toml` value change (queue cap, clarify mode, git mode)?
- Should a deterministic step move into `aide.py` rather than agent prose?
- What worked well that should be kept?

Framework/process changes land via a **reviewed PR**, never a direct merge.

### 4. Consistency, permission bottlenecks & instruction delivery

- Run `python .aide/scripts/aide.py check` — fix any format-contract errors it
  reports (they break the scripts the loop depends on).
- Unattended runs stall on permission prompts. Every prompt-eligible call is
  auto-logged (see `docs/aide/permissions/`): run `/aide-review-permissions` (or
  `python .claude/scripts/review_permissions.py`) for a ranked table, promote the
  safe recurring ones into `permissions.allow` in `.claude/settings.json` (via
  PR), and rotate the log.
- Which rules reached which sessions this queue is a queue-boundary question
  too. Every instruction file the runtime loads is auto-logged (see
  `docs/aide/instructions/`): run `/aide-review-instructions` (or
  `python .claude/scripts/review_instructions.py`), act on a rule that never
  loaded — a framework rule silent over a non-empty log means the hook or the
  trust flag; a project rule means its globs — and rotate that log too. It
  measures delivery, not reading, and a preloaded section skill never appears
  in it by design.

### 5. Recommendations

Provide specific, actionable suggestions: updates to vision/roadmap/progress,
template changes, `aide.toml` changes, new skills, process improvements.

### 6. Refresh the status summary (optional)

Regenerate the living HTML status page so the visible snapshot stays current —
run the `/aide-status-report` skill (or the generator directly):

```bash
.venv/Scripts/python scripts/aide_status_report.py    # Windows (Git Bash)
.venv/bin/python scripts/aide_status_report.py        # macOS / Linux
```

### Important notes

- **Routine decisions** during smooth implementation belong in the work item's
  "Decisions" section, not here.
- This loop is for **systemic issues** needing process/document/framework change.
- **Be minimal** — the smallest set of changes that prevents recurrence.

## Hand-off

Close your turn by telling the user, in chat, to resume the workflow where they
left off, in a fresh chat session.
