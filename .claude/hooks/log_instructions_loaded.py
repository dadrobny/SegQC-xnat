#!/usr/bin/env python
"""Claude Code hook: record which instruction files reach a context, and why.

Registered on ``InstructionsLoaded`` in ``.claude/settings.json``, with no
matcher, so it sees every load reason the runtime reports (``session_start``,
``nested_traversal``, ``path_glob_match``, ``include``, ``compact``).

**Why this exists.** ADAPTER-SPEC §7 requires a section be *delivered* rather
than pointed at, and the difference is invisible from inside a session — the
only prior evidence was a hand grep over stored transcripts, run once. This
turns it into a standing measurement: a `paths:`-scoped rule that never fires
is a delivery mechanism that silently degraded to a pointer, and the log is
where that shows up.

It answers "what loaded, when, and why". It does **not** answer "did the agent
follow a pointer" — nothing loads on a `Read`, so that question is still a
transcript question. Do not read an empty log as proof a rule is broken:
`path_glob_match` only fires when a matching file is actually opened.

Design rules, shared with ``log_permission_event.py``:

- *Dumb on purpose.* It records; it classifies nothing. Any analysis happens in
  ``.claude/scripts/review_instructions.py``.
- *It must never alter a session.* It writes nothing to stdout and always exits
  0. The runtime ignores this event's exit code, but the discipline is the same
  one every hook here follows.
- *Schema-tolerant.* The event-specific payload fields are not pinned by the
  public docs, so anything recognisable is lifted into a named column and
  everything else is kept, truncated, under ``extra`` — a renamed field
  degrades the log rather than emptying it.

The raw log lives at ``docs/aide/instructions/log.jsonl`` (per-machine,
gitignored). The path is resolved relative to this file, not the cwd, so it is
correct no matter where the hook is invoked from.
"""

import datetime
import json
import sys
from pathlib import Path

# .claude/hooks/log_instructions_loaded.py -> parents[2] is the project root.
LOG_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "aide" / "instructions" / "log.jsonl"
)

# Envelope fields every hook event carries; recorded under their own names or
# deliberately dropped, never duplicated into `extra`.
_ENVELOPE = {"session_id", "hook_event_name", "cwd", "transcript_path", "prompt_id",
             "permission_mode"}

# A value long enough to be file *content* rather than a description of it.
_MAX_VALUE = 300


def _first_str(payload, *names):
    """The first of `names` present in `payload` with a non-empty string value."""
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


def _paths(payload):
    """Every instruction-file path the payload names, however it spells the key.

    Both a single path and a list of them are accepted: the event fires per
    file today, but a batched shape would otherwise be recorded as no path at
    all, which reads identically to "nothing loaded".
    """
    out = []
    for name in ("file_path", "path", "file", "instruction_file",
                 "file_paths", "paths", "files"):
        value = payload.get(name)
        if isinstance(value, str) and value:
            out.append(value)
        elif isinstance(value, list):
            out.extend(v for v in value if isinstance(v, str) and v)
    # Deduplicate, keeping first-seen order — several key spellings may agree.
    seen = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def _extra(payload):
    """Scalar fields not otherwise recorded, truncated so content cannot flood."""
    out = {}
    for key, value in payload.items():
        if key in _ENVELOPE or key in ("file_path", "path", "file", "instruction_file",
                                       "file_paths", "paths", "files"):
            continue
        if isinstance(value, str):
            out[key] = value[:_MAX_VALUE]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
    return out


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return

    record = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": payload.get("session_id", ""),
        "event": payload.get("hook_event_name", ""),
        "reason": _first_str(payload, "reason", "load_reason", "trigger", "source"),
        "paths": _paths(payload),
        "cwd": payload.get("cwd", ""),
    }
    extra = _extra(payload)
    if extra:
        record["extra"] = extra

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never let a logging failure alter a session.
        pass
    sys.exit(0)
