# Instruction-load log

This directory holds the record of instruction files delivered into sessions
and sub-agents, so a rule that silently stopped loading — a `paths:` glob that
no longer matches, a retired rule still expected somewhere — is visible instead
of inert. It is the instructions counterpart of `docs/aide/permissions/`.

## How it works

- A Claude Code hook — `.claude/hooks/log_instructions_loaded.py`, registered on
  `InstructionsLoaded` in `.claude/settings.json` — appends one JSONL record per
  instruction file the runtime loads, with the runtime's reason
  (`session_start`, `path_glob_match`, …). It fires inside sub-agents too.
- The hook records and never blocks; all interpretation happens later in the
  reviewer. It measures **delivery, not reading** — a plain `Read` of a file
  loads no instructions and appears nowhere here, and a section skill preloaded
  via an agent's `skills:` frontmatter is asserted structurally by the
  framework's own tests rather than logged.

## Files

| File | Tracked? | Purpose |
|---|---|---|
| `README.md` | committed | this file |
| `log.jsonl` | **gitignored** | raw, per-machine append-only event log |
| `log.reviewed.jsonl` | **gitignored** | rotated-away entries already reviewed |

The raw logs are per-machine and gitignored for the same reason the permission
logs are: an append-only JSONL written from several machines is a merge-conflict
hotspot, and only the reviewed outcome (a corrected glob, a retired rule) is
shared, via the normal PR.

## Reviewing

Run `/aide-review-instructions` (or `python .claude/scripts/review_instructions.py`
directly) for the delivery report, judge each silent rule on what it is, then
rotate the log (`--rotate`). `/aide-feedback-loop` triggers this review at the
queue boundary alongside the permission review.
