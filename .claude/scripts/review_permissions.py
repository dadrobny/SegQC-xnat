#!/usr/bin/env python
"""Aggregate the permission-prompt log into a review of recurring bottlenecks.

Reads the JSONL written by ``.claude/hooks/log_permission_event.py`` plus the
project ``.claude/settings.json``, correlates each requested call with its
completion to infer grant vs deny, drops calls already covered by an ``allow``
rule, and ranks what is left so the safe, recurring prompts can be promoted into
the allow-list.

Everything below the ``main`` boundary is a pure function so it can be unit
tested (see ``tests/test_permission_review.py``). Normalised rules and coverage
checks are deliberately *advisory* — the full command is always shown so a human
makes the final allow/ask/leave call. The real allow-list edit is made by the
``/aide-review-permissions`` command, gated by the existing permission policy and
landed via PR.
"""

import argparse
import fnmatch
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = _ROOT / "docs" / "aide" / "permissions" / "log.jsonl"
DEFAULT_SETTINGS = _ROOT / ".claude" / "settings.json"

# How many leading tokens form a stable Bash prefix per CLI (subcommand depth).
_BASH_PREFIX_DEPTH = {
    "gh": 3,        # gh pr view
    "git": 2,       # git status
    "npm": 2,       # npm run
    "yarn": 2,
    "pnpm": 2,
    "pip": 2,       # pip install
    "pip3": 2,
    "docker": 2,    # docker build
    "cargo": 2,
    "dotnet": 2,
    "poetry": 2,
    "uv": 2,
    "kubectl": 2,
}


# --------------------------------------------------------------------------- #
# Normalisation: a single call -> a candidate permission rule.
# --------------------------------------------------------------------------- #
def normalize_command(tool, detail):
    """Return an advisory ``Tool(pattern)`` rule that would cover ``detail``."""
    detail = (detail or "").strip()
    if tool == "Bash":
        tokens = detail.split()
        if not tokens:
            return "Bash"
        head = tokens[0]
        if head in ("python", "python3"):
            depth = 3 if len(tokens) > 1 and tokens[1] == "-m" else 1
        else:
            depth = _BASH_PREFIX_DEPTH.get(head, 1)
        prefix = " ".join(tokens[:depth])
        return f"Bash({prefix}:*)"
    if tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        rule_tool = "Edit" if tool == "MultiEdit" else tool
        path = detail.replace("\\", "/")
        parent, _, name = path.rpartition("/")
        if parent and parent not in (".", ""):
            return f"{rule_tool}({parent}/**)"
        return f"{rule_tool}({name or path})"
    if tool == "WebFetch":
        host = urlparse(detail).netloc or detail
        return f"WebFetch(domain:{host})"
    if tool == "WebSearch":
        return "WebSearch"
    return tool


# --------------------------------------------------------------------------- #
# Correlation: requested + completed -> grant / deny.
# --------------------------------------------------------------------------- #
def _phase(event):
    if event.endswith("PreToolUse") or event == "requested":
        return "requested"
    if event.endswith("PostToolUse") or event == "completed":
        return "completed"
    return None


def correlate(records):
    """Infer an outcome for every ``requested`` record.

    A ``requested`` record matched by a later ``completed`` of the same
    (session, tool, detail) was granted/auto-approved; an unmatched one was
    denied (or errored before completion). Returns one dict per request:
    ``{session_id, tool, detail, outcome}`` with outcome ``granted``/``denied``.
    """
    pending = defaultdict(list)  # (session, tool, detail) -> [request dicts]
    results = []
    for rec in records:
        phase = _phase(rec.get("event", ""))
        if phase is None:
            continue
        key = (rec.get("session_id", ""), rec.get("tool", ""), rec.get("detail", ""))
        if phase == "requested":
            entry = {
                "session_id": key[0],
                "tool": key[1],
                "detail": key[2],
                "outcome": "denied",
            }
            pending[key].append(entry)
            results.append(entry)
        else:  # completed
            if pending[key]:
                pending[key].pop(0)["outcome"] = "granted"
    return results


# --------------------------------------------------------------------------- #
# Coverage: would an existing rule already auto-approve this call?
# --------------------------------------------------------------------------- #
def _parse_rule(rule):
    """``Bash(git status:*)`` -> ``("Bash", "git status:*")``; ``Read`` -> ``("Read", None)``."""
    rule = rule.strip()
    if rule.endswith(")") and "(" in rule:
        tool, _, inner = rule[:-1].partition("(")
        return tool, inner
    return rule, None


def is_covered(tool, detail, rules):
    """True if ``rules`` (a list of permission strings) already auto-approve the call."""
    detail_norm = (detail or "").replace("\\", "/")
    for rule in rules:
        rule_tool, inner = _parse_rule(rule)
        if rule_tool != tool:
            continue
        if inner is None:  # bare tool, e.g. "Read" / "Grep"
            return True
        if tool == "Bash":
            if inner.endswith(":*"):
                prefix = inner[:-2]
                if detail == prefix or detail.startswith(prefix + " "):
                    return True
            elif detail == inner:
                return True
        else:
            pattern = inner.replace("**", "*")
            if fnmatch.fnmatch(detail_norm, pattern) or fnmatch.fnmatch(
                detail_norm, "*" + pattern
            ):
                return True
    return False


# --------------------------------------------------------------------------- #
# Aggregation.
# --------------------------------------------------------------------------- #
def aggregate(calls, allow_rules, ask_rules):
    """Group correlated calls by normalised rule with counts and a status.

    status: ``auto-allowed`` (every call already covered by allow — not a
    bottleneck), ``ask-gated`` (intentionally gated), or ``new`` (a real
    bottleneck candidate for the allow-list).
    """
    groups = defaultdict(
        lambda: {"total": 0, "granted": 0, "denied": 0, "samples": Counter(),
                 "covered_all": True, "ask_any": False, "tool": ""}
    )
    for call in calls:
        rule = normalize_command(call["tool"], call["detail"])
        g = groups[rule]
        g["tool"] = call["tool"]
        g["total"] += 1
        g[call["outcome"]] += 1
        g["samples"][call["detail"]] += 1
        if not is_covered(call["tool"], call["detail"], allow_rules):
            g["covered_all"] = False
        if is_covered(call["tool"], call["detail"], ask_rules):
            g["ask_any"] = True

    out = []
    for rule, g in groups.items():
        if g["covered_all"]:
            status = "auto-allowed"
        elif g["ask_any"]:
            status = "ask-gated"
        else:
            status = "new"
        out.append({
            "rule": rule,
            "tool": g["tool"],
            "total": g["total"],
            "granted": g["granted"],
            "denied": g["denied"],
            "status": status,
            "sample": g["samples"].most_common(1)[0][0] if g["samples"] else "",
        })
    out.sort(key=lambda r: (r["status"] != "new", -r["total"], r["rule"]))
    return out


# --------------------------------------------------------------------------- #
# IO + CLI.
# --------------------------------------------------------------------------- #
def load_records(log_path):
    records = []
    path = Path(log_path)
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate partial/corrupt lines
    return records


def load_rules(settings_path):
    path = Path(settings_path)
    if not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    perms = data.get("permissions", {})
    return perms.get("allow", []), perms.get("ask", [])


def _render_table(rows):
    if not rows:
        return "No prompt-eligible tool calls logged yet.\n"
    header = f"{'#':>2}  {'count':>5}  {'grant':>5}  {'deny':>4}  {'status':<12}  rule"
    lines = [header, "-" * len(header)]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i:>2}  {r['total']:>5}  {r['granted']:>5}  {r['denied']:>4}  "
            f"{r['status']:<12}  {r['rule']}"
        )
        lines.append(f"      e.g. {r['sample']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    records = load_records(args.log)
    allow_rules, ask_rules = load_rules(args.settings)
    rows = aggregate(correlate(records), allow_rules, ask_rules)

    new_rules = [r for r in rows if r["status"] == "new"]

    if args.json:
        print(json.dumps({"rows": rows, "suggested_allow": [r["rule"] for r in new_rules]},
                         indent=2))
        return 0

    print(f"Permission review - {len(records)} log records, {args.log}\n")
    print(_render_table(rows))
    if new_rules:
        print("\nSuggested `allow` additions (review each - full command shown above):")
        for r in new_rules:
            print(f'  "{r["rule"]}",')
        print("\nAdd the safe/routine ones to permissions.allow in .claude/settings.json,")
        print("leave anything with side effects under `ask`. Lands via PR (framework file).")
    else:
        print("\nNo new bottlenecks: every prompted call is already covered or intentionally gated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
