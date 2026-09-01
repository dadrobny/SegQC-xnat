"""Human-readable report renderer for ``segfacet`` (item 010).

Converts a :class:`~segfacet.verdict.Verdict` plus case metadata and heuristic
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
   ``import segfacet.human_report`` stays fast and import-clean (AC-17).
4. **Deterministic output**: per-label sections are emitted in sorted label
   order so output is stable regardless of dict insertion order.
5. **No raw Python internals in output**: severity is rendered via
   ``Severity.label`` (e.g. "fail"), reason lists are iterated directly —
   no repr(), str(frozenset), or class-name strings appear in the output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from segfacet.config import HeuristicConfig
    from segfacet.verdict import Verdict

__all__ = ["render_human_report", "render_feature_table"]


def _finding_fields(finding) -> tuple:
    """Read ``(rule_id, severity_label, reason, sorted_labels)`` from a finding.

    Accepts either a :class:`~segfacet.heuristics.finding.Finding` object or its
    ``to_dict()`` dict, read defensively so this module stays stdlib-only (no
    import of ``segfacet.heuristics``).
    """
    if isinstance(finding, dict):
        rule_id = finding.get("rule_id", "")
        severity_label = finding.get("severity", "")
        reason = finding.get("reason", "")
        labels = finding.get("labels", []) or []
    else:
        rule_id = finding.rule_id
        severity_label = finding.severity.label
        reason = finding.reason
        labels = finding.labels
    return rule_id, severity_label, reason, sorted(labels)


def _render_findings_section(findings) -> "list[str]":
    """Build the 'Findings' section lines for ``render_human_report``.

    One block per finding: ``[severity] (rule_id) reason`` followed by a
    sorted-integer labels line, or an explicit case-level marker when the
    finding has no offending labels. Renders "(none)" for an empty list.
    """
    lines: list[str] = ["Findings:"]
    if not findings:
        lines.append("  (none)")
        lines.append("")
        return lines

    for finding in findings:
        rule_id, severity_label, reason, labels = _finding_fields(finding)
        lines.append(f"  [{severity_label}] ({rule_id}) {reason}")
        if labels:
            labels_txt = ", ".join(str(label) for label in labels)
            lines.append(f"    Labels: {labels_txt}")
        else:
            lines.append("    Labels: (case-level)")
    lines.append("")
    return lines


def render_human_report(
    verdict: "Verdict",
    case_id: str,
    config: "HeuristicConfig",
    findings: "list | None" = None,
    image_features: "dict | None" = None,
    features: "dict | None" = None,
) -> str:
    """Render a human-readable QC report string.

    Parameters
    ----------
    verdict:
        The QC verdict to render.
    case_id:
        Non-empty string identifier for the case (used in the report title).
    config:
        The :class:`~segfacet.config.HeuristicConfig` used for this run.
        Carried as a parameter for future use (e.g. threshold display);
        currently used only for structural consistency with ``serialize_report``.
    findings:
        Optional Stage 4 findings (item 035) — an iterable of
        :class:`~segfacet.heuristics.finding.Finding` objects or their
        ``to_dict()`` dicts. When ``None`` (default) no "Findings" section is
        rendered, preserving the item-010 report shape exactly. When an empty
        list, a "Findings" section is rendered with a "(none)" body.
    image_features:
        Optional Stage 8 ``image_features`` block (item 061/065), as
        produced by :func:`~segfacet.feature_report.build_image_features_block`.
        When non-``None``, delegates to the existing item-061
        ``_render_image_features_section`` so an "Intensity features:"
        section is appended. When ``None`` (default), no section is
        appended, preserving byte-identical output.
    features:
        Optional features block (item 097, Stage 17), as produced by
        :func:`~segfacet.feature_report.build_features_block`. When
        non-``None``, every label present in ``features["per_label"]`` is
        listed in the "Per-label findings" section with its
        ``level_name`` in parentheses -- including labels with no
        findings at all, which previously never appeared in the human
        report text even though their names were visible in the JSON
        report and the CLI's stdout "Label inventory" table. When
        ``None`` (default), the section lists only labels that have
        findings, exactly as before -- preserving byte-identical output
        for every existing caller. When this mapping carries
        ``"stage3_unavailable"`` (item 129), a "Degraded features:" section
        naming the cause is appended after "Per-label findings" and before
        "Findings"; when the key is absent, output is byte-identical to
        before this section existed (AC16).

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
    title = f"FACET Report -- {case_id}"
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
    if features is not None:
        # item 097: list every label present in the features block (not just
        # labels with findings) so the level name is visible end-to-end for
        # every label, mirroring the CLI's stdout "Label inventory" table.
        label_names: dict = {}
        for key, entry in (features.get("per_label") or {}).items():
            try:
                label_names[int(key)] = entry.get("level_name")
            except (TypeError, ValueError):
                continue
        all_labels = sorted(set(label_names) | set(verdict.per_label.keys()))
        if all_labels:
            for label in all_labels:
                name = label_names.get(label)
                header = f"  Label {label} ({name}):" if name else f"  Label {label}:"
                lines.append(header)
                label_reasons = verdict.per_label.get(label, [])
                if label_reasons:
                    for reason in label_reasons:
                        lines.append(f"    [{reason.severity.label}] {reason.message}")
                else:
                    lines.append("    (no findings)")
        else:
            lines.append("  (none)")
    elif verdict.per_label:
        for label in sorted(verdict.per_label.keys()):
            label_reasons = verdict.per_label[label]
            lines.append(f"  Label {label}:")
            for reason in label_reasons:
                lines.append(f"    [{reason.severity.label}] {reason.message}")
    else:
        lines.append("  (none)")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Degraded features section (item 129) — only rendered when the supplied
    # features block carries "stage3_unavailable", so the omitted-key case is
    # byte-for-byte the pre-item report (AC16).
    # ------------------------------------------------------------------ #
    if features is not None and features.get("stage3_unavailable") is not None:
        stage3_unavailable = features["stage3_unavailable"]
        lines.append("Degraded features:")
        lines.append(f"  {stage3_unavailable.get('detail', '')}")
        lines.append("")

    # ------------------------------------------------------------------ #
    # Findings section (item 035) — only rendered when explicitly requested,
    # so the omitted-findings case is byte-for-byte the item-010 report.
    # ------------------------------------------------------------------ #
    if findings is not None:
        lines.extend(_render_findings_section(findings))

    # ------------------------------------------------------------------ #
    # Intensity features section (item 065) — only rendered when explicitly
    # supplied, so the omitted-image_features case is byte-for-byte the
    # pre-item report.
    # ------------------------------------------------------------------ #
    if image_features is not None:
        lines.extend(_render_image_features_section(image_features))

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


def _fmt_or_na(value) -> str:
    """Format a possibly-``None`` number, rendering ``None`` as ``(n/a)``."""
    if value is None:
        return "(n/a)"
    return _fmt_num(value)


def _render_image_features_section(image_features: dict) -> "list[str]":
    """Build the 'Intensity features' section lines for ``render_feature_table``.

    Renders one row per ``per_label`` entry (ascending integer-label order)
    showing label and mean/median/std/min/max/entropy, formatted via
    ``_fmt_or_na`` so ``None`` statistics render as ``(n/a)`` rather than raw
    Python ``None``/``nan`` text. When the block is unavailable (``available``
    is falsy) or ``per_label`` is empty, a single explicit placeholder line is
    rendered instead.
    """
    lines: list[str] = ["Intensity features:"]
    per_label = image_features.get("per_label") or {}
    if not image_features.get("available", False) or not per_label:
        lines.append("  (unavailable)")
        lines.append("")
        return lines

    header = (
        f"  {'Label':>6}  {'Mean':>10}  {'Median':>10}  {'Std':>10}  "
        f"{'Min':>10}  {'Max':>10}  {'Entropy':>8}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for key in sorted(per_label, key=lambda k: int(k)):
        entry = per_label[key]
        first_order = entry.get("first_order", {})
        lines.append(
            f"  {entry.get('label', key):>6}  "
            f"{_fmt_or_na(first_order.get('mean')):>10}  "
            f"{_fmt_or_na(first_order.get('median')):>10}  "
            f"{_fmt_or_na(first_order.get('std')):>10}  "
            f"{_fmt_or_na(first_order.get('min')):>10}  "
            f"{_fmt_or_na(first_order.get('max')):>10}  "
            f"{_fmt_or_na(first_order.get('entropy')):>8}"
        )
    lines.append("")
    return lines


def render_feature_table(
    features_block: dict,
    image_features: "dict | None" = None,
) -> str:
    """Render a :func:`segfacet.feature_report.build_features_block` block as text.

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
        :func:`~segfacet.feature_report.build_features_block` (or parsed from a
        serialised report's ``features`` key).
    image_features:
        Optional Stage 8 ``image_features`` block (item 061), as produced by
        :func:`~segfacet.feature_report.build_image_features_block` (or parsed
        from a serialised report's ``image_features`` key). When non-``None``,
        an "Intensity features:" section is appended after the existing
        sections, listing each present label (ascending) with its
        mean/median/std/min/max/entropy, formatted null-safely (``None``
        statistics render as ``(n/a)``; an unavailable/empty block renders a
        single ``(unavailable)`` line). When ``None`` (default), no section is
        appended and the output is byte-identical to the pre-item render.

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
            f"{'Volume(mm3)':>12}  {'Comps':>6}  {'frag_idx':>8}  Centroid(mm)"
        )
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for key in sorted(per_label, key=lambda k: int(k)):
            entry = per_label[key]
            geom = entry.get("geometry", {})
            comps = entry.get("components", {})
            centroid_mm = entry.get("centroid", {}).get("centroid_mm", [])
            centroid_txt = ", ".join(_fmt_num(v) for v in centroid_mm)
            frag_idx = comps.get("fragmentation_index")
            frag_txt = _fmt_num(frag_idx) if frag_idx is not None else "?"
            lines.append(
                f"  {entry.get('label', key):>6}  "
                f"{str(entry.get('level_name', '?')):<6}  "
                f"{_fmt_num(geom.get('voxel_count', 0)):>8}  "
                f"{_fmt_num(geom.get('physical_volume_mm3', 0)):>12}  "
                f"{_fmt_num(comps.get('component_count', 0)):>6}  "
                f"{frag_txt:>8}  "
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

    # ------------------------------------------------------------------ #
    # Intensity features (item 061) — only rendered when explicitly
    # supplied, so the omitted-image_features case is byte-for-byte the
    # pre-item render.
    # ------------------------------------------------------------------ #
    if image_features is not None:
        lines.extend(_render_image_features_section(image_features))

    return "\n".join(lines)
