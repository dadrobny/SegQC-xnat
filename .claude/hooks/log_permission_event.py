#!/usr/bin/env python
"""Claude Code hook: log prompt-eligible tool calls and their outcomes.

Registered on both ``PreToolUse`` (phase ``requested``) and ``PostToolUse``
(phase ``completed``) in ``.claude/settings.json`` for the tools that can
actually trigger a permission prompt (Bash / Edit / Write / Web...). Together
the two phases let the reviewer infer grant vs deny: a ``requested`` record
with no matching ``completed`` in the same session was denied (or errored); a
matching pair was granted (or auto-approved).

Design rules:
- This hook is *dumb on purpose*. It records every matched call — including
  already-allowed ones — and never tries to replicate the allow-list. All
  filtering / classification happens later in
  ``.claude/scripts/review_permissions.py``.
- It MUST NEVER interfere with the real tool. It writes no JSON to stdout (so
  it cannot alter the permission decision) and always exits 0 — a non-zero
  exit from a PreToolUse hook would *block* the tool. Every failure mode is
  swallowed.

The raw log lives at ``docs/aide/permissions/log.jsonl`` (per-machine,
gitignored). The path is resolved relative to this file, not the cwd, so it is
correct no matter where the hook is invoked from.
"""

import datetime
import json
import sys
from pathlib import Path

# .claude/hooks/log_permission_event.py -> parents[2] is the project root.
LOG_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "aide" / "permissions" / "log.jsonl"
)

# Per-tool key in ``tool_input`` that best identifies *what* was requested.
_DETAIL_KEYS = {
    "Bash": "command",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "Write": "file_path",
    "NotebookEdit": "notebook_path",
    "WebFetch": "url",
    "WebSearch": "query",
}


def _extract_detail(tool_name, tool_input):
    """Return a compact string describing the requested action."""
    if not isinstance(tool_input, dict):
        return ""
    key = _DETAIL_KEYS.get(tool_name)
    if key and isinstance(tool_input.get(key), str):
        return tool_input[key]
    # Fallback: first string-valued field, so unknown tools still log something.
    for value in tool_input.values():
        if isinstance(value, str):
            return value
    return ""


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    payload = json.loads(raw)

    tool_name = payload.get("tool_name", "")
    record = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": payload.get("session_id", ""),
        "event": payload.get("hook_event_name", ""),
        "tool": tool_name,
        "detail": _extract_detail(tool_name, payload.get("tool_input")),
        "cwd": payload.get("cwd", ""),
    }

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never let a logging failure block or alter the real tool call.
        pass
    sys.exit(0)
