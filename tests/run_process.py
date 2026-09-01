"""UTF-8-safe subprocess wrapper for tests that shell out.

Why this exists: ``subprocess.run(..., text=True)`` without an explicit
``encoding=`` decodes the child's output with ``locale.getpreferredencoding(False)``
— UTF-8 on the Linux/macOS CI runners, but the ANSI code page (cp1252 by
default) on Windows. Any non-ASCII byte in the captured output then decodes to
mojibake on Windows only, which the Linux-side loop can never catch. The defect
class first fired on PR #58: ``git show`` of ``docs/aide/golden-decision-table.md``
returned its em-dash heading cp1252-decoded, and
``test_134_decision_table_evidence_companion.py``'s AC10 section lookup raised
``KeyError`` on ``windows-latest`` alone.

Every command a test captures text from here (git, docker, a pytest
subprocess) emits UTF-8 regardless of platform, so decoding as UTF-8
unconditionally is correct — never gate it on ``sys.platform``. Decoding stays
``errors="strict"`` deliberately: a genuine decode failure should crash the
test loudly, not flow onward as replacement characters.

See ``.aide/conventions.md`` §6 (test hygiene) for the neighbouring
portability rules this sits beside.
"""

from __future__ import annotations

import subprocess


def run_utf8(argv, *, cwd=None, timeout=None):
    """Run ``argv`` capturing stdout/stderr as UTF-8 text.

    A drop-in replacement for the test suite's
    ``subprocess.run(argv, cwd=..., capture_output=True, text=True, timeout=...)``
    pattern, differing only in pinning the decode to UTF-8. Exceptions
    (``OSError``, ``subprocess.TimeoutExpired``, ...) propagate exactly as
    from ``subprocess.run``; the caller still checks ``returncode``.
    """
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=timeout,
    )
