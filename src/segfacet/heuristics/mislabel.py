"""Mislabel / misalignment rule (item 033).

Implements a **mislabel / misalignment rule** targeting two related §6 failure
modes:

- **Mode 1 — label not aligned with the vertebra it names (misalignment).**
  Detector A flags a vertebra whose centroid is a large outlier from the
  fitted spinal curve, via the per-vertebra perpendicular spline offset
  (``stage3.per_label_offsets[*].offset_mm``, item 018).
- **Mode 4 — semantic mislabelling / wrong vertebra identification.**
  Detector B flags a vertebra whose physical position is inconsistent with
  its anatomical label's expected ordering relative to neighbours, via the
  monotonic-progression metric
  (``stage3.monotonic_consistency.non_monotonic_pairs``, item 020).

It consumes three already-serialised sub-blocks of the per-case feature
record — ``stage3.per_label_offsets`` (item 018), ``stage3.
monotonic_consistency`` (item 020), and ``per_label`` (item 016) — and never
recomputes any geometry, offset, spline, or ordering itself.

Design decisions (recorded per item 033 spec):
- Two independent, config-gated detectors, combined with OR: a record may
  produce findings from either or both.
- Detector A fires on ``offset_mm >= max_offset_mm`` (default ``13.0``,
  inclusive) and is label-attributed (single offending label).
- Detector A never fires on a **terminal** entry (``is_terminal`` truthy,
  item 123) -- an entry with no ``is_terminal`` key, or one carrying
  ``None``, is interior and still fires. See "Threshold calibration
  (item 123)" below for why, and ``features/spline_offset.py``'s "Terminal-
  vertebra exclusion" section for the mechanism. Detector B (ordering) is
  unaffected -- it does not read per-vertebra offsets at all.
- Detector A reads ``dx_mm``/``dy_mm``/``dz_mm`` when all three are present
  and finite (item 120), naming the dominant displacement direction as one
  of ``"left-right"``, ``"anterior-posterior"`` or ``"cranio-caudal"`` --
  the largest of ``|dx_mm|``, ``|dy_mm|``, ``|dz_mm|``, ties broken
  x -> y -> z. This reading rests on the RAS axis contract stated in
  ``features/spline_offset.py``'s module docstring: array axis 0 is
  left-right, axis 1 anterior-posterior, axis 2 cranio-caudal, because
  ``io.load_volume`` reorients every volume to ``("R", "A", "S")`` and
  ``centroid_mm`` carries no affine of its own. An entry missing any
  component, or carrying a non-finite one, omits the direction clause
  entirely rather than guessing or raising.
- Detector B fires on each ``non_monotonic_pairs`` entry, resolving both
  level names to integer labels via ``per_label``; an unresolvable name is
  omitted from ``labels`` but still named in the ``reason``.
- Offset findings are emitted first (ascending label), then order findings
  (ascending ``(level_a, level_b)`` name-pair order); both detectors re-sort
  defensively so output never depends on the input list order.
- Unrecognised severity string raises ValueError before any per-record
  processing.
- The caller's record is never mutated.

Threshold calibration (item 123, recalibrated 2026-08-29)
-----------------------------------------------------------
``_DEFAULT_MAX_OFFSET_MM`` is derived (``scripts/rebuild_verse_reference.py
::derive_max_offset_mm``) from the real, 80-subject VerSe19 training cohort's
committed ``reference_verse_v1.json``: the smallest multiple of ``0.5`` mm
strictly above ``P``, floored at ``6.0`` mm, where ``P`` is the maximum
``spline_offset_mm`` ``p99`` over levels with at least 10 **interior**
(non-terminal, see below) occurrences. The measured ceiling is
``P = 12.91`` mm at level ``T10``, giving ``_DEFAULT_MAX_OFFSET_MM = 13.0``.

**Terminal vertebrae are excluded from this measurement and from Detector A
itself** (item 123, human decision 2026-08-29): the first calibration run
measured `P = 21.209` mm at `L5`, driven entirely by the held-out
estimator's terminal-extrapolation artefact (`features/spline_offset.py`'s
"Terminal-vertebra exclusion" section) rather than real anatomy -- `L5`'s
*interior* offset never exceeds `1.00` mm in the same cohort. Excluding
terminal entries from both the reference distribution
(`reference/ingest.py`) and Detector A brought the measurement back inside
the approved corpus window.

Corpus margins (from `tests/corpus/manifest.json`'s nine cases, each measured
via a freshly built `build_report_for_case` report -- item 126 retired the
committed corpus-golden snapshots these margins used to cite),
all measured on **interior** entries only:
- `mode4_relabel_swap`'s largest interior reading (label 23 / L4) is
  `2.510990` mm and must **not** fire -- the non-firing ceiling. (Its larger
  `5.143859` mm reading, label 20, is that case's cranial-terminal vertebra
  and is excluded from consideration entirely.)
- `mode6_crop_at_border`'s firing reading is `17.507445` mm and **must**
  fire -- so ``_DEFAULT_MAX_OFFSET_MM`` sits in `(2.510990, 17.507445]`
  (`13.0` qualifies).
- `mode1_displace`'s firing reading is `18.718604` mm and **must** fire.

Distribution calibrated against: `src/segfacet/reference/reference_verse_v1.json`.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule
from segfacet.verdict import Severity

__all__ = ["MislabelRule"]


# --------------------------------------------------------------------------- #
# Reason tag constants — stable, testable start-of-reason markers
# --------------------------------------------------------------------------- #

_MISALIGN_TAG = "Vertebra misaligned from spinal curve:"
_MISLABEL_TAG = "Vertebra ordering inconsistent with label:"

_DEFAULT_MAX_OFFSET_MM = 13.0


# --------------------------------------------------------------------------- #
# Severity helper (mirrors bounds.py / sequence.py / border.py / overlap.py)
# --------------------------------------------------------------------------- #

_LABEL_TO_SEVERITY: Dict[str, Severity] = {sev.label: sev for sev in Severity}


def _severity_from_param(label: str) -> Severity:
    """Map a severity label string to its Severity member.

    Raises
    ------
    ValueError
        If *label* is not a recognised Severity label string.
    """
    sev = _LABEL_TO_SEVERITY.get(label)
    if sev is None:
        known = list(_LABEL_TO_SEVERITY.keys())
        raise ValueError(
            f"Unknown severity label {label!r} in mislabel rule config. "
            f"Known labels: {known}."
        )
    return sev


def _label_for_level(per_label: dict, level_name: str) -> Optional[int]:
    """Locate the integer label for *level_name* by scanning ``per_label``.

    ``per_label`` is keyed by integer label, not level name, so a direct key
    lookup is not possible (mirrors sequence.py's ``_label_for_level``).
    Returns ``None`` if no entry matches or *per_label* is not a mapping.
    """
    if not isinstance(per_label, dict):
        return None
    for entry in per_label.values():
        if isinstance(entry, dict) and entry.get("level_name") == level_name:
            return int(entry["label"])
    return None


# --------------------------------------------------------------------------- #
# MislabelRule
# --------------------------------------------------------------------------- #


@register_rule
class MislabelRule(Rule):
    """Mislabel / misalignment rule (item 033).

    Runs two independent, config-gated detectors and returns their combined
    findings: spline-offset outliers (Detector A, §6 mode 1) first in
    ascending label order, then monotonic-progression inconsistencies
    (Detector B, §6 mode 4) in ascending name-pair order.
    """

    rule_id = "mislabel"

    # §6 modes 1, 4 (item 136): DisplacePerturbation designates mode 1,
    # RelabelSwapPerturbation designates mode 4
    # (src/segfacet/synth/identity_ordering_alignment.py), both via
    # Expectation(..., expected_rule_ids={"mislabel"}).
    mode_declaration = RuleModeDeclaration(modes=(1, 4), evidence=("corpus",))

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate mislabel / misalignment signals for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads
            ``record["stage3"]["per_label_offsets"]``,
            ``record["stage3"]["monotonic_consistency"]``, and
            ``record["per_label"]``.
        config:
            HeuristicConfig instance. Reads ``rules.mislabel.params``.

        Returns
        -------
        list[Finding]
            Zero or more findings: offset findings first (ascending label),
            then order findings (ascending name-pair order).

        Raises
        ------
        ValueError
            If ``rules.mislabel.params.severity`` is an unrecognised string
            (raised before any per-record processing, AC16).
        """
        # Read severity once up-front; raises immediately on a bad string.
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        max_offset = float(
            config.rule_param(
                self.rule_id, "max_offset_mm", default=_DEFAULT_MAX_OFFSET_MM
            )
        )
        flag_offset = bool(
            config.rule_param(self.rule_id, "flag_offset_outliers", default=True)
        )
        flag_order = bool(
            config.rule_param(
                self.rule_id, "flag_order_inconsistency", default=True
            )
        )

        stage3 = record.get("stage3")
        if not isinstance(stage3, dict):
            stage3 = {}

        offset_findings: List[Finding] = []
        order_findings: List[Finding] = []

        if flag_offset:
            offset_findings = self._detect_offset_outliers(
                stage3, severity, max_offset
            )

        if flag_order:
            order_findings = self._detect_order_inconsistency(
                stage3, record, severity
            )

        return offset_findings + order_findings

    @staticmethod
    def _dominant_direction(entry: dict) -> Optional[str]:
        """Return the dominant displacement direction name for *entry*, or
        ``None`` when any of ``dx_mm``/``dy_mm``/``dz_mm`` is missing or
        non-finite (item 120, AC14/AC15).

        Selected as the largest of ``|dx_mm|``, ``|dy_mm|``, ``|dz_mm|``,
        ties broken x -> y -> z (left-right -> anterior-posterior ->
        cranio-caudal), per the RAS axis contract in
        ``features/spline_offset.py``.
        """
        components = []
        for key, name in (
            ("dx_mm", "left-right"),
            ("dy_mm", "anterior-posterior"),
            ("dz_mm", "cranio-caudal"),
        ):
            if key not in entry:
                return None
            try:
                value = float(entry[key])
            except (TypeError, ValueError):
                return None
            if not math.isfinite(value):
                return None
            components.append((abs(value), name))

        # Stable sort by descending magnitude keeps x -> y -> z tie order
        # (the insertion order above) for equal magnitudes.
        best = max(components, key=lambda c: c[0])
        return best[1]

    @staticmethod
    def _detect_offset_outliers(
        stage3: dict, severity: Severity, max_offset: float
    ) -> List[Finding]:
        """Detector A: spline-offset outliers (misalignment, §6 mode 1)."""
        offsets = stage3.get("per_label_offsets")
        if not isinstance(offsets, list):
            return []

        normalised = []
        for entry in offsets:
            if not isinstance(entry, dict) or "label" not in entry:
                continue
            if entry.get("is_terminal"):
                # A terminal (sequence-first/last) entry's held-out offset
                # extrapolates past the end of the estimator's own parameter
                # domain rather than measuring a genuine displacement -- item
                # 123, see this module's docstring. A missing key or `None`
                # is falsy and therefore interior, unchanged from before.
                continue
            try:
                label = int(entry["label"])
            except (TypeError, ValueError):
                continue
            offset = float(entry.get("offset_mm", 0.0) or 0.0)
            name = entry.get("level_name")
            direction = MislabelRule._dominant_direction(entry)
            normalised.append((label, name, offset, direction))

        normalised.sort(key=lambda t: t[0])

        findings: List[Finding] = []
        for label, name, offset, direction in normalised:
            if offset >= max_offset:
                direction_clause = f", predominantly {direction}" if direction else ""
                findings.append(
                    Finding(
                        rule_id="mislabel",
                        severity=severity,
                        reason=(
                            f"{_MISALIGN_TAG} label {label} ({name}) centroid "
                            f"lies {offset:.1f} mm off the fitted spinal curve"
                            f"{direction_clause} "
                            f"(threshold {max_offset:.1f} mm)."
                        ),
                        labels=frozenset({label}),
                    )
                )
        return findings

    @staticmethod
    def _detect_order_inconsistency(
        stage3: dict, record: dict, severity: Severity
    ) -> List[Finding]:
        """Detector B: monotonic-progression inconsistency (mislabelling,
        §6 mode 4)."""
        mono = stage3.get("monotonic_consistency")
        if not isinstance(mono, dict):
            mono = {}

        pairs = mono.get("non_monotonic_pairs")
        if not isinstance(pairs, list):
            return []

        per_label = record.get("per_label")
        if not isinstance(per_label, dict):
            per_label = {}

        normalised = []
        for pair in pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            level_a, level_b = pair[0], pair[1]
            la = _label_for_level(per_label, level_a)
            lb = _label_for_level(per_label, level_b)
            normalised.append((level_a, level_b, la, lb))

        normalised.sort(key=lambda t: (t[0], t[1]))

        findings: List[Finding] = []
        for level_a, level_b, la, lb in normalised:
            findings.append(
                Finding(
                    rule_id="mislabel",
                    severity=severity,
                    reason=(
                        f"{_MISLABEL_TAG} labels {la} ({level_a}) and "
                        f"{lb} ({level_b}) are out of expected order along "
                        f"the spine (spline parameter does not advance)."
                    ),
                    labels=frozenset(
                        {x for x in (la, lb) if x is not None}
                    ),
                )
            )
        return findings
