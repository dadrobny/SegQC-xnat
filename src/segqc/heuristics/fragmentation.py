"""Connected-components fragmentation / rogue-island rule (item 028; item 090
adds the reference-derived path).

Implements two §6 failure-mode checks off the same topology data:

- **Fragmentation (§6 mode 2)** — a label whose fragmentation index (= largest
  connected component / total volume) falls strictly below a threshold is
  judged to have split into comparable pieces.
- **Rogue islands / excess fragments (§6 mode 3)** — a label with too many
  disconnected pieces is judged to have small disconnected fragments attached
  to a dominant body.

**Two sources for the thresholds (item 090), mirroring ``bounds.py``'s item
048 design exactly:**

- ``source: hand-set`` (item 028's original behaviour) — the fixed
  ``fragmentation_index_threshold`` / ``island_min_voxels`` constants below,
  compared against every label regardless of level.
- ``source: reference`` (item 090, code-side **default**) — per-level
  tolerances derived from the already-loaded ``ReferenceDistribution`` at
  ``record["reference"]`` (:func:`reference_fragmentation_for_level`):
  the index check compares against the level's ``largest_component_fraction``
  lower percentile (a *floor*), and the island check is re-expressed as an
  excess-``component_count`` ceiling check against the level's
  ``component_count`` upper percentile -- **bypassing** (not ANDing) the
  absolute ``island_min_voxels`` floor for a level the reference covers,
  because the reference carries no per-island voxel distribution to re-derive
  a voxel floor from. A level absent from the reference (or missing one of
  the two tracked stats) falls back to the hand-set check for that metric --
  never crashes (item 048 AC5/AC9 parity).

Design decisions (recorded per item 028 spec, extended by item 090):
- One rule, two finding kinds, one ``rule_id == "fragmentation"``.  Both checks
  derive from the same ``components`` sub-dict; they share a rule and are
  distinguished by a stable tag at the start of the ``reason`` string.
- Inclusive thresholds consistent with item 027: strictly ``<``/``>`` fires,
  ``==`` passes (both hand-set and reference mode).
- Fixed within-label order: fragmentation finding is appended before the island
  /excess finding so multi-kind output is deterministic (AC16 / item 090 AC17).
- ``component_sizes[0]`` is the dominant body; only ``[1:]`` are island
  candidates (hand-set path only), making a single-component label trivially
  island-free (AC2).
- ``fragmentation_index`` is the primary key; ``largest_component_fraction`` is
  the fallback alias (AC17 / spec step 2).
- Does not rely on ``components.small_fragments`` -- that list is recomputed
  from ``component_sizes`` using the rule's own ``island_min_voxels`` param
  (hand-set path only).
- Unrecognised severity string raises ValueError immediately (AC15). An
  unrecognised ``source``, or a ``reference_lower_pct``/``reference_upper_pct``
  absent from ``reference.percentiles``, also raises ValueError, before/at
  per-label processing (item 090, mirroring bounds AC10/AC11).
- Shipped hand-set defaults (0.75 / 50) are unchanged fallback placeholders.
- The caller's record, its attached ``reference``, and ``config`` are never
  mutated (AC18 / item 090 AC17).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from segqc.heuristics.finding import Finding
from segqc.heuristics.rule import Rule, register_rule
from segqc.verdict import Severity

if TYPE_CHECKING:  # pragma: no cover - type-only import, no runtime dependency
    from segqc.reference.schema import ReferenceDistribution

__all__ = [
    "FragmentationRule",
    "DEFAULT_FRAGMENTATION_INDEX_THRESHOLD",
    "DEFAULT_ISLAND_MIN_VOXELS",
    "DEFAULT_SOURCE",
    "DEFAULT_REFERENCE_LOWER_PCT",
    "DEFAULT_REFERENCE_UPPER_PCT",
    "DEFAULT_REFERENCE_STRATUM",
    "reference_fragmentation_for_level",
]


# --------------------------------------------------------------------------- #
# Shipped hand-set default constants
# --------------------------------------------------------------------------- #
# Fallback placeholders: the hand-set fragmentation_index_threshold / island
# floor used for a level the reference does not cover (or when
# source: hand-set is configured explicitly).

DEFAULT_FRAGMENTATION_INDEX_THRESHOLD: float = 0.75
"""Fire when fragmentation_index is strictly below this value (label split)."""

DEFAULT_ISLAND_MIN_VOXELS: int = 50
"""Non-dominant component strictly below this many voxels is a rogue island."""


# --------------------------------------------------------------------------- #
# Reference-derived source switch (item 090, mirroring bounds.py item 048)
# --------------------------------------------------------------------------- #

#: Recognised ``rules.fragmentation.params.source`` values.
_SOURCE_HAND_SET = "hand-set"
_SOURCE_REFERENCE = "reference"
_VALID_SOURCES = frozenset({_SOURCE_HAND_SET, _SOURCE_REFERENCE})

#: Code-side default source (item 090): the shipped default is reference-
#: derived when a covering reference is attached, falling back to hand-set
#: per-level/per-metric otherwise. ``default_config.yaml`` documents this as
#: a COMMENT only -- the parsed config dict (and hence ``config_hash``) is
#: unaffected.
DEFAULT_SOURCE = _SOURCE_REFERENCE

#: Default percentile pair and stratum for reference mode (matches
#: ``segqc.heuristics.bounds``'s item 048 convention and
#: ``segqc.reference.schema.ALL_STRATUM``).
DEFAULT_REFERENCE_LOWER_PCT = 1
DEFAULT_REFERENCE_UPPER_PCT = 99
DEFAULT_REFERENCE_STRATUM = "all"


def reference_fragmentation_for_level(
    reference: "ReferenceDistribution",
    level_name: str,
    *,
    lower_pct: int,
    upper_pct: int,
    stratum: str = DEFAULT_REFERENCE_STRATUM,
) -> Optional[Dict[str, float]]:
    """Derive reference-mode fragmentation tolerances for *level_name* (item 090).

    Reads the level/stratum's stored ``largest_component_fraction`` (index
    floor) and ``component_count`` (excess-fragment ceiling) ``FeatureStats``
    from *reference* and returns:

    ``{"fragmentation_index_threshold": <lcf.percentiles[f"p{lower_pct}"]>,
       "max_component_count": <cc.percentiles[f"p{upper_pct}"]>}``

    Parameters
    ----------
    reference:
        The already-loaded ``ReferenceDistribution`` (attribute access only;
        no file I/O, no wall clock).
    level_name:
        The anatomical level to look up (e.g. ``"L3"``).
    lower_pct, upper_pct:
        The percentile pair to use. Must both be present in
        ``reference.percentiles``.
    stratum:
        The stratum to look up (default ``"all"``).

    Returns
    -------
    dict[str, float] | None
        A dict carrying whichever of the two keys the level/stratum's
        ``feature_stats`` track (possibly partial, one key), or ``None`` when
        *level_name* (or *stratum* for that level) is absent from
        *reference*, or when the covered level tracks **neither** stat.

    Raises
    ------
    ValueError
        If ``lower_pct`` or ``upper_pct`` is not one of ``reference.percentiles``.

    Pure: never mutates *reference*; reads no file or clock.
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

    result: Dict[str, float] = {}
    lcf_stats = level_dist.feature_stats.get("largest_component_fraction")
    if lcf_stats is not None:
        result["fragmentation_index_threshold"] = lcf_stats.percentiles[f"p{lower_pct}"]
    cc_stats = level_dist.feature_stats.get("component_count")
    if cc_stats is not None:
        result["max_component_count"] = cc_stats.percentiles[f"p{upper_pct}"]

    if not result:
        return None
    return result


# --------------------------------------------------------------------------- #
# Reason tag constants — stable, testable start-of-reason markers
# --------------------------------------------------------------------------- #

_FRAGMENTATION_TAG = "Fragmentation:"
_ISLAND_TAG = "Rogue island(s):"


# --------------------------------------------------------------------------- #
# Severity helper
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
            f"Unknown severity label {label!r} in fragmentation rule config. "
            f"Known labels: {known}."
        )
    return sev


# --------------------------------------------------------------------------- #
# FragmentationRule
# --------------------------------------------------------------------------- #


@register_rule
class FragmentationRule(Rule):
    """Connected-components fragmentation / rogue-island rule (item 028;
    reference-derived path added by item 090).

    For each vertebra label present in the feature record the rule:

    1. Reads the label's pre-computed ``components`` sub-dict.
    2. **Fragmentation check** -- if ``fragmentation_index`` (alias
       ``largest_component_fraction``) is strictly below the effective index
       threshold, emits one fragmentation ``Finding`` with reason starting
       with ``"Fragmentation:"``. In reference mode with a covering reference,
       the effective threshold is the level's ``largest_component_fraction``
       ``p{lower_pct}``; otherwise (or for an uncovered level/metric) it is
       the hand-set ``fragmentation_index_threshold``.
    3. **Island / excess-fragment check** -- in hand-set mode (or for a level
       the reference does not cover for ``component_count``), considers
       ``component_sizes[1:]`` (non-dominant components); if any is strictly
       below ``island_min_voxels``, emits one rogue-island ``Finding``. In
       reference mode for a covered level, this check is instead an excess-
       ``component_count`` ceiling: if ``components.component_count`` is
       strictly above the level's ``component_count`` ``p{upper_pct}``, emits
       one excess-fragment ``Finding`` -- **bypassing** the absolute
       ``island_min_voxels`` floor for that covered level.

    Both finding kinds carry ``rule_id == "fragmentation"`` and the same
    per-label ``severity``.  Within a single label the fragmentation finding is
    always emitted before the island/excess finding (AC16 / item 090 AC17).
    Labels are iterated in ascending integer order for determinism.
    """

    rule_id = "fragmentation"

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate fragmentation and island/excess checks for every label in
        *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only).  Reads ``record["per_label"]``
            and, in reference mode, ``record["reference"]``.
        config:
            HeuristicConfig instance.  Reads ``rules.fragmentation.params``.

        Returns
        -------
        list[Finding]
            Zero or more findings; empty when all labels are healthy.

        Raises
        ------
        ValueError
            If ``rules.fragmentation.params.severity`` is an unrecognised
            string (AC15), if ``rules.fragmentation.params.source`` is
            neither ``"hand-set"`` nor ``"reference"`` (item 090), or -- in
            reference mode -- if a configured percentile is not one of
            ``reference.percentiles`` (item 090). All raised before/at
            per-label processing.
        """
        # Read severity once up-front; raises immediately on a bad string (AC15).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        # Read the two hand-set thresholds once (also the reference-mode
        # per-metric fallback values).
        frag_threshold: float = config.rule_param(
            self.rule_id,
            "fragmentation_index_threshold",
            default=DEFAULT_FRAGMENTATION_INDEX_THRESHOLD,
        )
        island_min: int = config.rule_param(
            self.rule_id,
            "island_min_voxels",
            default=DEFAULT_ISLAND_MIN_VOXELS,
        )

        # Read the source switch (item 090). Validated up-front, before any
        # per-label processing, even for an empty per_label (mirrors bounds
        # AC10).
        source: str = config.rule_param(
            self.rule_id, "source", default=DEFAULT_SOURCE
        )
        if source not in _VALID_SOURCES:
            raise ValueError(
                f"Unknown fragmentation source {source!r} in fragmentation "
                f"rule config. Known sources: {sorted(_VALID_SOURCES)}."
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

        # Ascending integer-label order for determinism (AC16 / item 090 AC17).
        for label_key in sorted(per_label.keys(), key=int):
            entry = per_label[label_key]
            label_int = int(label_key)
            level_name: str = entry.get("level_name", "unknown")

            # Read components; skip gracefully if absent or not a mapping (AC17).
            comp = entry.get("components")
            if not isinstance(comp, dict):
                continue

            # Reference-derived tolerances for this label's level, or None
            # when reference mode is off, no reference is attached, or the
            # level/stratum is uncovered (per-metric/per-level fallback).
            ref_tolerances: Optional[Dict[str, float]] = None
            if reference is not None:
                ref_tolerances = reference_fragmentation_for_level(
                    reference, level_name,
                    lower_pct=lower_pct, upper_pct=upper_pct, stratum=stratum,
                )

            # ----------------------------------------------------------------- #
            # Fragmentation check (§6 mode 2)
            # ----------------------------------------------------------------- #
            # Primary key: fragmentation_index; fallback: largest_component_fraction.
            index = comp.get("fragmentation_index") or comp.get(
                "largest_component_fraction"
            )

            index_threshold = frag_threshold
            index_from_reference = False
            if ref_tolerances is not None and "fragmentation_index_threshold" in ref_tolerances:
                index_threshold = ref_tolerances["fragmentation_index_threshold"]
                index_from_reference = True

            if index is not None and index < index_threshold:
                component_count = comp.get("component_count", "?")
                component_sizes = comp.get("component_sizes", [])
                if index_from_reference:
                    reason = (
                        f"{_FRAGMENTATION_TAG} Label {label_int} ({level_name}): "
                        f"fragmentation_index={index:.6g} is below reference "
                        f"floor {index_threshold:.6g} (p{lower_pct}) for level "
                        f"{level_name}. component_count={component_count}, "
                        f"component_sizes={component_sizes!r}"
                    )
                else:
                    reason = (
                        f"{_FRAGMENTATION_TAG} Label {label_int}: "
                        f"fragmentation_index={index:.6g} is strictly below "
                        f"threshold {index_threshold:.6g}. "
                        f"component_count={component_count}, "
                        f"component_sizes={component_sizes!r}"
                    )
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=reason,
                        labels=frozenset({label_int}),
                    )
                )

            # ----------------------------------------------------------------- #
            # Island / excess-fragment check (§6 mode 3)
            # ----------------------------------------------------------------- #
            sizes: list = comp.get("component_sizes") or []
            component_count_val = comp.get("component_count")

            if ref_tolerances is not None and "max_component_count" in ref_tolerances:
                # Reference-covered level: excess-component_count ceiling
                # check REPLACES (not ANDs) the hand-set island_min_voxels
                # floor -- the reference carries no per-island voxel
                # distribution to re-derive a voxel floor from (item 090).
                max_component_count = ref_tolerances["max_component_count"]
                if component_count_val is not None and component_count_val > max_component_count:
                    index_for_reason = comp.get("fragmentation_index") or comp.get(
                        "largest_component_fraction"
                    )
                    findings.append(
                        Finding(
                            rule_id=self.rule_id,
                            severity=severity,
                            reason=(
                                f"{_ISLAND_TAG} Label {label_int} ({level_name}): "
                                f"component_count={component_count_val} exceeds "
                                f"reference maximum {max_component_count:.6g} "
                                f"(p{upper_pct}) for level {level_name}. "
                                f"component_sizes={sizes!r}, "
                                f"fragmentation_index={index_for_reason}"
                            ),
                            labels=frozenset({label_int}),
                        )
                    )
            else:
                # Hand-set fallback: absolute island_min_voxels floor over
                # non-dominant components. Only sizes[1:] are island
                # candidates; a single-component label trivially passes.
                non_dominant = sizes[1:]
                tiny_islands = [s for s in non_dominant if s < island_min]
                if tiny_islands:
                    index_for_reason = (
                        comp.get("fragmentation_index")
                        or comp.get("largest_component_fraction")
                    )
                    findings.append(
                        Finding(
                            rule_id=self.rule_id,
                            severity=severity,
                            reason=(
                                f"{_ISLAND_TAG} Label {label_int}: "
                                f"{len(tiny_islands)} non-dominant component(s) "
                                f"strictly below island_min_voxels={island_min}. "
                                f"Tiny island sizes: {tiny_islands!r}. "
                                f"component_count={component_count_val if component_count_val is not None else '?'}, "
                                f"component_sizes={sizes!r}, "
                                f"fragmentation_index={index_for_reason}"
                            ),
                            labels=frozenset({label_int}),
                        )
                    )

        return findings
