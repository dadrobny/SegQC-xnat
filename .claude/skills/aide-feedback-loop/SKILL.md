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
- **defect / gap** → make it a **candidate item for the queue being authored**
  (or note it for the next `/aide-create-queue` run) so the queue PR reviews
  it. Do not fix it inline here.
- **automation** → a candidate item that (a) implements the deterministic
  script/CLI verb and (b) edits the skill/agent prose to *mandate* it — both
  halves, or agents keep improvising. (Worked example: the `aide sync`/`aide
  gc` verbs replacing improvised git recon.)
- **framework** → belongs to AIDE itself, not this project. If
  `[framework] repo` is set in `aide.toml` and `gh` is available, hand it
  over: `gh issue create --repo <owner/repo>` with a body naming the project,
  the observation, and a proposal (this stays `ask`-gated — a human confirms).
  Otherwise leave the entry unchecked with a `(pending handover)` note.

Tick each routed entry with the verb, naming where it landed — never by
editing the line by hand, which is how a claim gets silently reworded:

```
python .aide/scripts/aide.py insights tick 7 --pointer "item 042"
```

That appends `→ item 042` to the entry and flips its checkbox. Never reword,
reorder or delete a captured claim — including one that turned out to be wrong;
the correction goes *beneath* it, as a dated line in the entry's status trail,
which is what the same command writes when the entry is **already** ticked:

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

### 4. Consistency & permission bottlenecks

- Run `python .aide/scripts/aide.py check` — fix any format-contract errors it
  reports (they break the scripts the loop depends on).
- Unattended runs stall on permission prompts. Every prompt-eligible call is
  auto-logged (see `docs/aide/permissions/`): run `/aide-review-permissions` (or
  `python .claude/scripts/review_permissions.py`) for a ranked table, promote the
  safe recurring ones into `permissions.allow` in `.claude/settings.json` (via
  PR), and rotate the log.

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
