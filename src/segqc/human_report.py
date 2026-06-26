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

__all__ = ["render_human_report", "render_feature_table"]


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


def _fmt_num(value: float) -> str:
    """Format a number for the feature table: integers stay bare, floats get 2dp."""
    if isinstance(value, bool):  # bool is an int subclass; render as text
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    # Float: trim to 2 decimals but drop a trailing ".00" for whole values.
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}"


def render_feature_table(features_block: dict) -> str:
    """Render a :func:`segqc.feature_report.build_features_block` block as text.

    Produces a deterministic, stdlib-only plain-text table: one row per label
    (level name, voxel count, physical volume, component count, centroid in mm)
    followed by an overlaps section and a relationships section.

    The renderer consumes the **plain dict** features block (not the source
    dataclasses), so ``human_report.py`` stays stdlib-only and import-clean. The
    output never contains raw Python class names, ``repr()`` output, tuples, or
    ``frozenset`` text — every value is formatted explicitly.

    Parameters
    ----------
    features_block:
        A features block dict as returned by
        :func:`~segqc.feature_report.build_features_block` (or parsed from a
        serialised report's ``features`` key).

    Returns
    -------
    str
        A non-empty plain-text feature table. Deterministic: labels are listed
        in ascending integer order regardless of dict insertion order.
    """
    lines: list[str] = []

    version = features_block.get("features_version", "?")
    title = f"Feature table (features v{version})"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")

    # ------------------------------------------------------------------ #
    # Per-label rows (ascending integer-label order)
    # ------------------------------------------------------------------ #
    per_label = features_block.get("per_label", {})
    lines.append("Per-label features:")
    if per_label:
        header = (
            f"  {'Label':>6}  {'Level':<6}  {'Voxels':>8}  "
            f"{'Volume(mm3)':>12}  {'Comps':>6}  Centroid(mm)"
        )
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for key in sorted(per_label, key=lambda k: int(k)):
            entry = per_label[key]
            geom = entry.get("geometry", {})
            comps = entry.get("components", {})
            centroid_mm = entry.get("centroid", {}).get("centroid_mm", [])
            centroid_txt = ", ".join(_fmt_num(v) for v in centroid_mm)
            lines.append(
                f"  {entry.get('label', key):>6}  "
                f"{str(entry.get('level_name', '?')):<6}  "
                f"{_fmt_num(geom.get('voxel_count', 0)):>8}  "
                f"{_fmt_num(geom.get('physical_volume_mm3', 0)):>12}  "
                f"{_fmt_num(comps.get('component_count', 0)):>6}  "
                f"({centroid_txt})"
            )
    else:
        lines.append("  (none)")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Overlaps
    # ------------------------------------------------------------------ #
    overlaps = features_block.get("overlaps", [])
    lines.append("Overlaps:")
    if overlaps:
        for ov in overlaps:
            lines.append(
                f"  {ov.get('name_a', '?')} (label {ov.get('label_a', '?')}) <-> "
                f"{ov.get('name_b', '?')} (label {ov.get('label_b', '?')}): "
                f"{_fmt_num(ov.get('overlap_voxels', 0))} voxels"
            )
    else:
        lines.append("  (none)")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    rel = features_block.get("relationships")
    lines.append("Relationships:")
    if rel is None:
        lines.append("  (none)")
    else:
        present = rel.get("present_levels", [])
        missing = rel.get("missing_levels", [])
        spacings = rel.get("neighbour_spacings_mm", [])
        out_of_order = rel.get("out_of_order_labels", [])
        lines.append(
            f"  Present levels: {', '.join(present) if present else '(none)'}"
        )
        lines.append(
            f"  Missing levels: {', '.join(missing) if missing else '(none)'}"
        )
        spacing_txt = (
            ", ".join(_fmt_num(s) for s in spacings) if spacings else "(none)"
        )
        lines.append(f"  Neighbour spacings (mm): {spacing_txt}")
        lines.append(
            f"  Continuous: {'yes' if rel.get('is_continuous') else 'no'}"
        )
        if out_of_order:
            lines.append(f"  Out-of-order labels: {', '.join(out_of_order)}")
    lines.append("")

    return "\n".join(lines)
