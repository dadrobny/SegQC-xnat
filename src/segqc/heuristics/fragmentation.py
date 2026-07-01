"""Connected-components fragmentation / rogue-island rule (item 028).

Implements two §6 failure-mode checks off the same topology data:

- **Fragmentation (§6 mode 2)** — a label whose fragmentation index (= largest
  connected component / total volume) falls strictly below a configurable
  threshold is judged to have split into comparable pieces.
- **Rogue islands (§6 mode 3)** — a label whose non-dominant components have
  any voxel count strictly below a configurable threshold is judged to have
  small disconnected fragments attached to a dominant body.

Design decisions (recorded per item 028 spec):
- One rule, two finding kinds, one ``rule_id == "fragmentation"``.  Both checks
  derive from the same ``components`` sub-dict; they share a rule and are
  distinguished by a stable tag at the start of the ``reason`` string.
- Inclusive thresholds consistent with item 027: strictly ``<`` fires, ``==``
  passes.
- Fixed within-label order: fragmentation finding is appended before the island
  finding so multi-kind output is deterministic (AC16).
- ``component_sizes[0]`` is the dominant body; only ``[1:]`` are island
  candidates, making a single-component label trivially island-free (AC2).
- ``fragmentation_index`` is the primary key; ``largest_component_fraction`` is
  the fallback alias (AC17 / spec step 2).
- Does not rely on ``components.small_fragments`` — that list is recomputed from
  ``component_sizes`` using the rule's own ``island_min_voxels`` param.
- Unrecognised severity string raises ValueError immediately (AC15).
- Shipped defaults (0.75 / 50) are hand-set placeholders superseded by Stage 6.
- The caller's record is never mutated (AC18).
"""

from __future__ import annotations

from typing import Dict, List

from segqc.heuristics.finding import Finding
from segqc.heuristics.rule import Rule, register_rule
from segqc.verdict import Severity

__all__ = ["FragmentationRule", "DEFAULT_FRAGMENTATION_INDEX_THRESHOLD", "DEFAULT_ISLAND_MIN_VOXELS"]


# --------------------------------------------------------------------------- #
# Shipped hand-set default constants
# --------------------------------------------------------------------------- #
# Placeholders superseded by VerSe-derived distributions in Stage 6 / item 006.

DEFAULT_FRAGMENTATION_INDEX_THRESHOLD: float = 0.75
"""Fire when fragmentation_index is strictly below this value (label split)."""

DEFAULT_ISLAND_MIN_VOXELS: int = 50
"""Non-dominant component strictly below this many voxels is a rogue island."""


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
    """Connected-components fragmentation / rogue-island rule (item 028).

    For each vertebra label present in the feature record the rule:

    1. Reads the label's pre-computed ``components`` sub-dict.
    2. **Fragmentation check** — if ``fragmentation_index`` (alias
       ``largest_component_fraction``) is strictly below
       ``fragmentation_index_threshold``, emits one fragmentation ``Finding``
       with reason starting with ``"Fragmentation:"``.
    3. **Island check** — considers ``component_sizes[1:]`` (non-dominant
       components); if any is strictly below ``island_min_voxels``, emits one
       rogue-island ``Finding`` with reason starting with ``"Rogue island(s):"``.

    Both finding kinds carry ``rule_id == "fragmentation"`` and the same
    per-label ``severity``.  Within a single label the fragmentation finding is
    always emitted before the island finding (AC16).  Labels are iterated in
    ascending integer order for determinism (AC16).
    """

    rule_id = "fragmentation"

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate fragmentation and island checks for every label in *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only).  Reads ``record["per_label"]``.
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
            string (raised before any per-label iteration, AC15).
        """
        # Read severity once up-front; raises immediately on a bad string (AC15).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        # Read the two thresholds once.
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

        findings: List[Finding] = []
        per_label = record.get("per_label", {})

        # Ascending integer-label order for determinism (AC16).
        for label_key in sorted(per_label.keys(), key=int):
            entry = per_label[label_key]
            label_int = int(label_key)

            # Read components; skip gracefully if absent or not a mapping (AC17).
            comp = entry.get("components")
            if not isinstance(comp, dict):
                continue

            # ----------------------------------------------------------------- #
            # Fragmentation check (§6 mode 2)
            # ----------------------------------------------------------------- #
            # Primary key: fragmentation_index; fallback: largest_component_fraction.
            index = comp.get("fragmentation_index") or comp.get(
                "largest_component_fraction"
            )
            if index is not None and index < frag_threshold:
                component_count = comp.get("component_count", "?")
                component_sizes = comp.get("component_sizes", [])
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_FRAGMENTATION_TAG} Label {label_int}: "
                            f"fragmentation_index={index:.6g} is strictly below "
                            f"threshold {frag_threshold:.6g}. "
                            f"component_count={component_count}, "
                            f"component_sizes={component_sizes!r}"
                        ),
                        labels=frozenset({label_int}),
                    )
                )

            # ----------------------------------------------------------------- #
            # Island check (§6 mode 3)
            # ----------------------------------------------------------------- #
            # Only non-dominant components (sizes[1:]) are island candidates.
            # A single-component label has empty sizes[1:] and trivially passes.
            sizes: list = comp.get("component_sizes") or []
            non_dominant = sizes[1:]
            tiny_islands = [s for s in non_dominant if s < island_min]
            if tiny_islands:
                component_count = comp.get("component_count", "?")
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
                            f"component_count={component_count}, "
                            f"component_sizes={sizes!r}, "
                            f"fragmentation_index={index_for_reason}"
                        ),
                        labels=frozenset({label_int}),
                    )
                )

        return findings
