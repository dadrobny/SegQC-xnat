"""Human-readable report renderer for ``segqc`` (item 010).

Converts a :class:`~segqc.verdict.Verdict` plus case metadata and heuristic
config into a structured plain-text string that a clinician or reviewer can
read directly — in a terminal, XNAT notes, or email.

Public API
----------
``render_human_report(verdict, case_id, config) -> str``
    Build and return the plain-text report string. Pure function; no file I/O.

Design decisions (item 010)
----------------------------
1. **Plain text, not Markdown**: compatible with terminals, XNAT notes, and
   email without a Markdown renderer.  Markdown headings are an option once
   the output channel is known.
2. **Pure string builder, no file I/O**: same pattern as ``serialize_report``.
   File writing is done by the CLI so the renderer is trivially testable.
3. **No third-party imports at module level**: this module only uses stdlib so
   ``import segqc.human_report`` stays fast and import-clean (AC-17).
4. **Deterministic output**: per-label sections are emitted in sorted label
   order so output is stable regardless of dict insertion order.
5. **No raw Python internals in output**: severity is rendered via
   ``Severity.label`` (e.g. "fail"), reason lists are iterated directly —
   no repr(), str(frozenset), or class-name strings appear in the output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from segqc.config import HeuristicConfig
    from segqc.verdict import Verdict

__all__ = ["render_human_report"]


def render_human_report(
    verdict: "Verdict",
    case_id: str,
    config: "HeuristicConfig",
) -> str:
    """Render a human-readable QC report string.

    Parameters
    ----------
    verdict:
        The QC verdict to render.
    case_id:
        Non-empty string identifier for the case (used in the report title).
    config:
        The :class:`~segqc.config.HeuristicConfig` used for this run.
        Carried as a parameter for future use (e.g. threshold display);
        currently used only for structural consistency with ``serialize_report``.

    Returns
    -------
    str
        A structured plain-text report string.  Always non-empty.  Contains
        no raw Python class names, frozensets, or exception tracebacks.
    """
    lines: list[str] = []

    # ------------------------------------------------------------------ #
    # Title and overall verdict
    # ------------------------------------------------------------------ #
    title = f"SegQC Report -- {case_id}"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append(f"Verdict: {verdict.overall.label}")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Case-level reasons
    # ------------------------------------------------------------------ #
    lines.append("Reasons:")
    if verdict.reasons:
        for reason in verdict.reasons:
            lines.append(f"  [{reason.severity.label}] {reason.message}")
    else:
        lines.append("  (none)")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Per-label findings
    # ------------------------------------------------------------------ #
    lines.append("Per-label findings:")
    if verdict.per_label:
        for label in sorted(verdict.per_label.keys()):
            label_reasons = verdict.per_label[label]
            lines.append(f"  Label {label}:")
            for reason in label_reasons:
                lines.append(f"    [{reason.severity.label}] {reason.message}")
    else:
        lines.append("  (none)")
    lines.append("")

    return "\n".join(lines)
