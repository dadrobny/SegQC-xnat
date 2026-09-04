"""Level-aware min/max bounds rule for the heuristic rule engine (item 027).

Implements the first concrete rule family: per-label physical volume and extent
(x/y/z) compared against hand-set bounds that differ by vertebra level group
(cervical / thoracic / lumbar).

Design decisions (recorded per item 027 spec):
- One Finding per (label, metric) violation for maximal explainability.
- Bounds are inclusive: a value exactly equal to min or max does NOT fire;
  only strictly ``< min`` or ``> max`` raises a Finding.
- Default severity is Severity.FLAG (``"flagged-for-review"``); override via
  ``rules.bounds.params.severity`` in the config.
- An unrecognised severity string raises ValueError immediately — the raises
  path is pinned and tested in AC adversarial suite.
- Level-group resolution builds _LEVEL_GROUP from CANONICAL_ORDER so it stays
  in sync with the label convention without duplication.
- Shipped DEFAULT_BOUNDS are wide-but-finite placeholders; Stage 6 (item 006)
  will supersede them with VerSe-derived distributions.
- Missing geometry keys are silently skipped (not crashed) so partially-
  populated records remain safe to evaluate.
- The caller's record is never mutated.
- Targets §6 mode 2 (over-/under-segmentation), declared on analytic grounds
  (item 137) -- see ``BoundsRule.mode_declaration``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.rule import (
    ConsumedPath,
    Rule,
    RuleModeDeclaration,
    register_rule,
)
from segfacet.labels import CANONICAL_ORDER
from segfacet.verdict import Severity

if TYPE_CHECKING:  # pragma: no cover - type-only import, no runtime dependency
    from segfacet.reference.schema import ReferenceDistribution

__all__ = ["BoundsRule", "DEFAULT_BOUNDS", "reference_bounds_for_level", "DEFAULT_SOURCE"]


# --------------------------------------------------------------------------- #
# Level-group resolution
# --------------------------------------------------------------------------- #

# Derive the level_name → group map from CANONICAL_ORDER by name prefix so it
# stays in step with the label convention. Only C+digit / T / L prefixes match
# a branch below, so S1-S6 (no branch matches "S") and Cocc (starts with "C"
# but its second character is not a digit, so it fails the cervical branch's
# isdigit() guard) fall through unclassified and are omitted from the map —
# intentionally unbounded. That isdigit() guard is the one subtle thing
# keeping Cocc out of the cervical group; dropping it would silently
# reclassify Cocc as cervical.
_LEVEL_GROUP: Dict[str, str] = {}
for _name in CANONICAL_ORDER:
    if _name.startswith("C") and len(_name) > 1 and _name[1].isdigit():
        _LEVEL_GROUP[_name] = "cervical"
    elif _name.startswith("T"):
        _LEVEL_GROUP[_name] = "thoracic"
    elif _name.startswith("L"):
        _LEVEL_GROUP[_name] = "lumbar"
    # S1-S6, Cocc → match no branch above (see comment) → unbounded; omitted


def _level_group(level_name: str) -> Optional[str]:
    """Return the bounds group for *level_name*, or None for unbounded labels.

    Returns ``None`` for ``S1``-``S6``, ``Cocc``, ``unknown``, and any custom
    or unrecognised level name — these are silently skipped by the rule
    (AC11).
    """
    return _LEVEL_GROUP.get(level_name)


# --------------------------------------------------------------------------- #
# Shipped hand-set defaults
# --------------------------------------------------------------------------- #
# Conservative placeholder ranges: wide enough that anatomically plausible
# vertebrae pass, tight enough that gross fusions/fragments fail.
# Units: mm3 for volume, mm for each extent axis.
#
# Rationale for the ranges (based on published vertebra morphometry):
#   Cervical (C1-C7): smallest bodies; total bounding-box volume roughly
#       3 000–35 000 mm3; extents 10–80 mm per axis.
#   Thoracic (T1-T13): medium bodies; 5 000–70 000 mm3; extents 15–100 mm.
#   Lumbar (L1-L6): largest bodies; 8 000–120 000 mm3; extents 20–120 mm.
#
# These will be superseded by reference-derived bounds in Stage 6 / item 006.
DEFAULT_BOUNDS: Dict[str, Dict[str, float]] = {
    "cervical": {
        "min_volume_mm3": 3_000.0,
        "max_volume_mm3": 35_000.0,
        "min_extent_x_mm": 10.0,
        "max_extent_x_mm": 80.0,
        "min_extent_y_mm": 10.0,
        "max_extent_y_mm": 80.0,
        "min_extent_z_mm": 5.0,
        "max_extent_z_mm": 60.0,
    },
    "thoracic": {
        "min_volume_mm3": 5_000.0,
        "max_volume_mm3": 70_000.0,
        "min_extent_x_mm": 15.0,
        "max_extent_x_mm": 100.0,
        "min_extent_y_mm": 15.0,
        "max_extent_y_mm": 100.0,
        "min_extent_z_mm": 8.0,
        "max_extent_z_mm": 80.0,
    },
    "lumbar": {
        "min_volume_mm3": 8_000.0,
        "max_volume_mm3": 120_000.0,
        "min_extent_x_mm": 20.0,
        "max_extent_x_mm": 120.0,
        "min_extent_y_mm": 20.0,
        "max_extent_y_mm": 120.0,
        "min_extent_z_mm": 15.0,
        "max_extent_z_mm": 100.0,
    },
}


# --------------------------------------------------------------------------- #
# Metric definitions — determines fixed output order within a label (AC13)
# --------------------------------------------------------------------------- #
# Each tuple: (geometry_field, min_key, max_key, human_name_for_reason)
# This order is the stable, documented metric order for all bounds findings.
_METRICS: List[Tuple[str, str, str, str]] = [
    ("physical_volume_mm3", "min_volume_mm3", "max_volume_mm3", "volume (mm3)"),
    ("extent_x_mm", "min_extent_x_mm", "max_extent_x_mm", "extent_x (mm)"),
    ("extent_y_mm", "min_extent_y_mm", "max_extent_y_mm", "extent_y (mm)"),
    ("extent_z_mm", "min_extent_z_mm", "max_extent_z_mm", "extent_z (mm)"),
]

# Feature name -> (min_key, max_key), kept in step with _METRICS (item 048
# step 1). Used by reference_bounds_for_level to derive a bounds-dict from a
# ReferenceDistribution's stored percentiles.
_FEATURE_BOUNDS_KEYS: Dict[str, Tuple[str, str]] = {
    field_name: (min_key, max_key) for field_name, min_key, max_key, _ in _METRICS
}


# --------------------------------------------------------------------------- #
# Reference-derived bounds switch (item 048)
# --------------------------------------------------------------------------- #

#: Recognised ``rules.bounds.params.source`` values.
_SOURCE_HAND_SET = "hand-set"
_SOURCE_REFERENCE = "reference"
_VALID_SOURCES = frozenset({_SOURCE_HAND_SET, _SOURCE_REFERENCE})

#: Default percentile pair and stratum for reference mode (matches
#: segfacet.reference.delta.DEFAULT_LOWER_PCT/DEFAULT_UPPER_PCT and
#: segfacet.reference.schema.ALL_STRATUM).
DEFAULT_REFERENCE_LOWER_PCT = 1
DEFAULT_REFERENCE_UPPER_PCT = 99
DEFAULT_REFERENCE_STRATUM = "all"

#: Code-side default ``source`` (item 090): flips from ``"hand-set"`` (item
#: 048's original default) to ``"reference"`` -- the shipped default now
#: sources bounds from a covering reference when one is attached, falling
#: back to the hand-set group bounds for uncovered levels/metrics or when no
#: reference is attached at all (item 048 AC9). ``default_config.yaml``
#: documents this as a COMMENT only, so the parsed config dict (and hence
#: ``config_hash``) is unaffected -- the flip lives in code (item 090
#: Assumptions).
DEFAULT_SOURCE = _SOURCE_REFERENCE


def reference_bounds_for_level(
    reference: "ReferenceDistribution",
    level_name: str,
    *,
    lower_pct: int,
    upper_pct: int,
    stratum: str = DEFAULT_REFERENCE_STRATUM,
) -> Optional[Dict[str, float]]:
    """Derive a bounds-dict for *level_name* from *reference* (item 048).

    For each of the four bounds features present in the level/stratum's
    ``feature_stats``, reads ``percentiles[f"p{lower_pct}"]`` /
    ``percentiles[f"p{upper_pct}"]`` into the matching ``min_*``/``max_*``
    keys (see ``_FEATURE_BOUNDS_KEYS``). The result may be partial when the
    level's reference lacks stats for some tracked metric.

    Parameters
    ----------
    reference:
        The already-loaded ``ReferenceDistribution`` (attribute access only;
        no file I/O, no import of ``segfacet.reference`` at runtime).
    level_name:
        The anatomical level to look up (e.g. ``"L3"``).
    lower_pct, upper_pct:
        The percentile pair to use as the effective min/max. Must both be
        present in ``reference.percentiles``.
    stratum:
        The stratum to look up (default ``"all"``).

    Returns
    -------
    dict[str, float] | None
        The bounds-dict for a covered level (possibly partial), or ``None``
        when *level_name* (or *stratum* for that level) is absent from
        *reference*.

    Raises
    ------
    ValueError
        If ``lower_pct`` or ``upper_pct`` is not one of ``reference.percentiles``.
    """
    if lower_pct not in reference.percentiles:
        raise ValueError(
            f"lower_pct={lower_pct!r} is not in "
            f"reference.percentiles={reference.percentiles!r}"
        )
    if upper_pct not in reference.percentiles:
        raise ValueError(
            f"upper_pct={upper_pct!r} is not in "
            f"reference.percentiles={reference.percentiles!r}"
        )

    level_strata = reference.levels.get(level_name)
    if level_strata is None:
        return None
    level_dist = level_strata.get(stratum)
    if level_dist is None:
        return None

    bounds: Dict[str, float] = {}
    for field_name, (min_key, max_key) in _FEATURE_BOUNDS_KEYS.items():
        stats = level_dist.feature_stats.get(field_name)
        if stats is None:
            continue
        bounds[min_key] = stats.percentiles[f"p{lower_pct}"]
        bounds[max_key] = stats.percentiles[f"p{upper_pct}"]
    return bounds


# --------------------------------------------------------------------------- #
# Severity helper
# --------------------------------------------------------------------------- #

# Mirror the _LABEL_TO_SEVERITY pattern used in finding.py; built once at
# import time from the Severity enum so it stays in sync automatically.
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
            f"Unknown severity label {label!r} in bounds rule config. "
            f"Known labels: {known}."
        )
    return sev


# --------------------------------------------------------------------------- #
# BoundsRule
# --------------------------------------------------------------------------- #


@register_rule
class BoundsRule(Rule):
    """Level-aware min/max bounds rule over physical volume and extent (item 027).

    For each vertebra label present in the feature record the rule:

    1. Resolves the anatomical level group (cervical / thoracic / lumbar) from
       ``level_name`` by name prefix; labels that match no prefix (``S1``-``S6``,
       ``Cocc``, ``unknown``, custom) are unbounded and silently skipped.
    2. Reads per-group bounds from config, falling back to DEFAULT_BOUNDS per
       key (partial config overrides are supported).
    3. Compares ``physical_volume_mm3`` and ``extent_{x,y,z}_mm`` against
       inclusive ``[min, max]`` bounds; strictly ``< min`` or ``> max`` fires.
    4. Emits one Finding per violated metric per label.

    Findings are ordered ascending by integer label, then by the fixed metric
    order defined in ``_METRICS`` (volume → extent_x → extent_y → extent_z).
    """

    rule_id = "bounds"

    # §6 disposition (item 137): declares mode 2 (over-/under-segmentation)
    # on analytic grounds -- no committed corpus case designates "bounds" for
    # any mode, so evidence carries "analytic" plus the mechanism sentence,
    # never "corpus". Modes 3, 5 and 6 were considered and rejected: mode 5
    # is structurally out of reach (evaluate() iterates labels *present* in
    # per_label and can never observe an absent one -- coverage owns mode 5);
    # mode 3 is a component-count signal, not a magnitude one (fragmentation
    # owns it); mode 6 is detected by its own designated feature/rule
    # (border), and declaring it here would overstate this rule's coverage.
    # See item 137 Assumptions A2.
    mode_declaration = RuleModeDeclaration(
        modes=(2,),
        evidence=(
            "analytic",
            "per-label physical volume and x/y/z extent are compared against "
            "level-aware plausible ranges: a fused pair of vertebrae reads "
            "over the maximum and an under-segmented or partially-labelled "
            "vertebra reads under the minimum, which is §6 mode 2's own "
            "definition (over-/under-segmentation).",
        ),
        consumed_paths=(
            ConsumedPath(
                path="per_label",
                role="bookkeeping",
                reason=(
                    "container: iterated to reach each label's geometry "
                    "block"
                ),
            ),
            ConsumedPath(
                path="per_label.{label}.geometry.extent_x_mm",
                role="signal",
            ),
            ConsumedPath(
                path="per_label.{label}.geometry.extent_y_mm",
                role="signal",
            ),
            ConsumedPath(
                path="per_label.{label}.geometry.extent_z_mm",
                role="signal",
            ),
            ConsumedPath(
                path="per_label.{label}.geometry.physical_volume_mm3",
                role="signal",
            ),
            ConsumedPath(
                path="per_label.{label}.level_name",
                role="bookkeeping",
                reason=(
                    "gate: selects the level's expected band (or reference "
                    "stratum); the deviation is carried by the geometry "
                    "values"
                ),
            ),
        ),
    )

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate bounds for every label in *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only).  Reads ``record["per_label"]``.
        config:
            HeuristicConfig instance.  Reads ``rules.bounds.params``.

        Returns
        -------
        list[Finding]
            One finding per (label, metric) violation, empty when all labels
            are within bounds.

        Raises
        ------
        ValueError
            If ``rules.bounds.params.severity`` is an unrecognised string, if
            ``rules.bounds.params.source`` is neither ``"hand-set"`` nor
            ``"reference"`` (item 048), or — in reference mode — if a
            configured percentile is not one of ``reference.percentiles``
            (item 048).
        """
        # Read severity once (raises ValueError for an unrecognised label).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        # Read the bounds-source switch (item 048). Validated up-front, before
        # any per-label processing, even for an empty per_label (AC10).
        source: str = config.rule_param(
            self.rule_id, "source", default=DEFAULT_SOURCE
        )
        if source not in _VALID_SOURCES:
            raise ValueError(
                f"Unknown bounds source {source!r} in bounds rule config. "
                f"Known sources: {sorted(_VALID_SOURCES)}."
            )

        reference: Optional["ReferenceDistribution"] = None
        lower_pct = upper_pct = None
        stratum = DEFAULT_REFERENCE_STRATUM
        if source == _SOURCE_REFERENCE:
            lower_pct = int(config.rule_param(
                self.rule_id, "reference_lower_pct",
                default=DEFAULT_REFERENCE_LOWER_PCT,
            ))
            upper_pct = int(config.rule_param(
                self.rule_id, "reference_upper_pct",
                default=DEFAULT_REFERENCE_UPPER_PCT,
            ))
            stratum = config.rule_param(
                self.rule_id, "reference_stratum",
                default=DEFAULT_REFERENCE_STRATUM,
            )
            reference = record.get("reference")

        findings: List[Finding] = []
        per_label = record.get("per_label", {})

        # Iterate in ascending integer-label order for determinism (AC13).
        for label_key in sorted(per_label.keys(), key=int):
            entry = per_label[label_key]
            level_name: str = entry.get("level_name", "unknown")
            group = _level_group(level_name)
            if group is None:
                # Unbounded (S1-S6, Cocc, unknown, custom) — skip (AC11).
                continue

            # Merge config group dict over defaults per key; config wins where
            # present, defaults fill the rest (supports partial overrides, AC7).
            group_defaults = DEFAULT_BOUNDS[group]
            config_group: dict = config.rule_param(self.rule_id, group, default={})
            bounds = {**group_defaults, **config_group}

            # Reference mode: merge reference-derived bounds *over* the
            # hand-set bounds so covered metrics use reference values and any
            # metric/level the reference lacks falls back to hand-set
            # (per-metric/per-level fallback, item 048 AC5/AC12).
            reference_bounds: Dict[str, float] = {}
            if reference is not None:
                derived = reference_bounds_for_level(
                    reference, level_name,
                    lower_pct=lower_pct, upper_pct=upper_pct, stratum=stratum,
                )
                if derived is not None:
                    reference_bounds = derived
                    bounds = {**bounds, **reference_bounds}

            geometry: dict = entry.get("geometry", {})
            label_int = int(label_key)

            for field_name, min_key, max_key, human_name in _METRICS:
                if field_name not in geometry:
                    # Missing key — skip gracefully rather than crashing (AC14).
                    continue

                value: float = geometry[field_name]
                lo: float = bounds[min_key]
                hi: float = bounds[max_key]
                from_reference = min_key in reference_bounds

                # Inclusive bounds: strictly < min or > max fires (AC adv).
                if value < lo:
                    if from_reference:
                        reason = (
                            f"Label {label_int} ({level_name}): "
                            f"{human_name} = {value:.6g} is below "
                            f"reference minimum {lo:.6g} (p{lower_pct}) "
                            f"for level {level_name}"
                        )
                    else:
                        reason = (
                            f"Label {label_int} ({level_name}): "
                            f"{human_name} = {value:.6g} is below "
                            f"minimum {lo:.6g} for {group} group"
                        )
                    findings.append(Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=reason,
                        labels=frozenset({label_int}),
                    ))
                elif value > hi:
                    if from_reference:
                        reason = (
                            f"Label {label_int} ({level_name}): "
                            f"{human_name} = {value:.6g} exceeds "
                            f"reference maximum {hi:.6g} (p{upper_pct}) "
                            f"for level {level_name}"
                        )
                    else:
                        reason = (
                            f"Label {label_int} ({level_name}): "
                            f"{human_name} = {value:.6g} exceeds "
                            f"maximum {hi:.6g} for {group} group"
                        )
                    findings.append(Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=reason,
                        labels=frozenset({label_int}),
                    ))

        return findings
