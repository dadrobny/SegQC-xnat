# Permission-prompt log

This directory holds the record of permission prompts hit during agent runs
(notably unattended `/aide-run-queue` batches), so the safe, recurring ones can be
promoted into the pre-approved allow-list instead of stalling every run.

## How it works

- A Claude Code hook — `.claude/hooks/log_permission_event.py`, registered on
  `PreToolUse` and `PostToolUse` in `.claude/settings.json` — appends one JSONL
  record per prompt-eligible tool call (Bash / Edit / Write / MultiEdit /
  NotebookEdit / WebFetch / WebSearch). It fires inside sub-agents too, so prompts
  the orchestrator never sees are still captured.
- The hook is deliberately minimal: it records **every** matched call and never
  blocks or alters one (it always exits 0). All filtering and grant/deny inference
  happens later in the reviewer.

## Files

| File | Tracked? | Purpose |
|---|---|---|
| `README.md` | committed | this file |
| `log.jsonl` | **gitignored** | raw, per-machine append-only event log |
| `log.reviewed.jsonl` | **gitignored** | rotated-away entries already reviewed |

The raw logs are **per-machine and gitignored** on purpose: an append-only JSONL
written from several machines would be a constant merge-conflict hotspot (like
`progress.md`). Only the *reviewed outcome* — additions to `permissions.allow` in
`.claude/settings.json` — is shared, via the normal PR.

## Record schema

```json
{"ts": "<ISO-8601 UTC>", "session_id": "...", "event": "PreToolUse|PostToolUse",
 "tool": "Bash", "detail": "<command / path / url / query>", "cwd": "..."}
```

A `PreToolUse` record is a *request*; a matching `PostToolUse` (same session, tool
and detail) means it *completed* → granted/auto-approved. A request with no matching
completion was denied (or errored before running).

## Reviewing

Run `/aide-review-permissions` (or `python .claude/scripts/review_permissions.py`
directly) to get a ranked table of bottlenecks with grant/deny counts and suggested
allow rules, decide which to promote, and rotate the log. `/speckit-aide-feedback-loop`
triggers this review as part of its process check.
