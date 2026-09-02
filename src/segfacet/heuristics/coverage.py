"""Incomplete-coverage / missing-level rule (item 029).

Implements a **coverage rule family** targeting §6 failure mode 5 — *not all
vertebrae in the image are segmented*. It runs up to three independent checks
off the pre-computed ``relationships`` (item 014) and per-label ``geometry``
(item 011) sub-blocks, distinguished by a stable tag at the start of each
finding's ``reason`` string:

1. **Missing interior level(s)** *(always active)* — a level absent from
   *within* the observed present-label span is bracketed above and below by
   segmented vertebrae, so the field-of-view (FOV) demonstrably covers it: an
   interior gap is always a genuine failure and is never border-suppressed.
   Reads ``relationships.missing_levels`` directly (item 014 already restricts
   it to interior gaps) rather than re-deriving it.

2. **Incomplete coverage vs an expected span** *(opt-in via
   ``expected_levels``)* — flags configured expected levels absent *beyond* the
   present span's ends. This check is **FOV-aware** (item 089, default
   ``border_aware: true``): it resolves the covered span through the shared
   :func:`segfacet.heuristics.fov.derive_fov_coverage` helper — a span end that is
   *truncated* (its extremal vertebra touches the corresponding cranio-caudal
   image face, item 011) means the FOV was cropped there, so nothing beyond it
   is flagged; a *non-truncated* end has headroom, so only the single
   immediately-adjacent canonical level beyond it is flagged (the conservative
   floor — see item 089's Assumptions). ``border_aware: false`` reverts to the
   legacy behaviour — flag every absent expected level beyond a span end,
   regardless of truncation.

3. **Below an expected count** *(opt-in via ``expected_count``)* — a raw, non-
   border-aware hard minimum on the number of recognised present levels (Use
   Case C dataset curation).

Design decisions (recorded per item 029 spec; item 089 amendments noted):
- One rule, three finding kinds, one ``rule_id == "coverage"``; a case can emit
  up to three findings in the fixed order missing-interior -> incomplete-span
  -> count-shortfall (AC14).
- Missing-level findings are **case-level**: an absent vertebra has no integer
  segmentation label, so ``labels == frozenset()`` and the offending level
  names are carried in the ``reason`` string.
- Both opt-in checks default to disabled (``expected_levels: []``,
  ``expected_count: None``); the rule ships no hand-set numeric thresholds.
- A span-end level's border flags are looked up (via the shared
  ``segfacet.heuristics.fov`` helper, item 089) by matching ``level_name`` in
  ``record["per_label"]``; if absent, treated as **not** touching the border
  (the conservative choice — surfaces a possible miss rather than hiding it).
- Unrecognised severity string raises ValueError before any per-record
  processing (AC13).
- The caller's record is never mutated (AC16).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.fov import derive_fov_coverage
from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule
from segfacet.labels import CANONICAL_ORDER
from segfacet.verdict import Severity

__all__ = ["CoverageRule", "DEFAULT_BORDER_AWARE"]


# --------------------------------------------------------------------------- #
# Canonical-rank map — built once at import for O(1) ordering / comparisons
# --------------------------------------------------------------------------- #

_CANONICAL_RANK: Dict[str, int] = {name: i for i, name in enumerate(CANONICAL_ORDER)}


# --------------------------------------------------------------------------- #
# Reason tag constants — stable, testable start-of-reason markers
# --------------------------------------------------------------------------- #

_MISSING_INTERIOR_TAG = "Missing interior level(s):"
_INCOMPLETE_SPAN_TAG = "Incomplete coverage (span):"
_COUNT_SHORTFALL_TAG = "Below expected count:"

# No shipped numeric thresholds — coverage is structural; opt-in checks
# default to disabled.
DEFAULT_BORDER_AWARE: bool = True


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
            f"Unknown severity label {label!r} in coverage rule config. "
            f"Known labels: {known}."
        )
    return sev


def _canonical_sort(names) -> List[str]:
    """Return *names* sorted by canonical anatomical rank (unknowns last)."""
    return sorted(names, key=lambda n: _CANONICAL_RANK.get(n, len(CANONICAL_ORDER)))


# --------------------------------------------------------------------------- #
# CoverageRule
# --------------------------------------------------------------------------- #


@register_rule
class CoverageRule(Rule):
    """Incomplete-coverage / missing-level rule (item 029).

    For each case the rule performs up to three independent checks, described
    in the module docstring, and returns their findings in the fixed order
    missing-interior -> incomplete-span -> count-shortfall.
    """

    rule_id = "coverage"

    # §6 mode 5 (item 136): RemoveLevelPerturbation
    # (src/segfacet/synth/coverage_border_overlap.py) designates "coverage"
    # for mode 5 via its Expectation(failure_mode=5, expected_rule_ids={"coverage"}).
    mode_declaration = RuleModeDeclaration(modes=(5,), evidence=("corpus",))

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate the coverage checks for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads ``record["relationships"]``
            and ``record["per_label"]``.
        config:
            HeuristicConfig instance. Reads ``rules.coverage.params``.

        Returns
        -------
        list[Finding]
            Zero to three findings, in the fixed check order.

        Raises
        ------
        ValueError
            If ``rules.coverage.params.severity`` is an unrecognised string
            (raised before any per-record processing, AC13).
        """
        # Read severity once up-front; raises immediately on a bad string (AC13).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        # Read the opt-in params once.
        expected_levels_raw = config.rule_param(
            self.rule_id, "expected_levels", default=[]
        )
        expected_count = config.rule_param(
            self.rule_id, "expected_count", default=None
        )
        border_aware: bool = config.rule_param(
            self.rule_id, "border_aware", default=DEFAULT_BORDER_AWARE
        )

        findings: List[Finding] = []

        rel = record.get("relationships")
        if not isinstance(rel, dict):
            # Absent / None / not-a-mapping relationships (AC15) — tolerate.
            return findings

        present_levels: List[str] = list(rel.get("present_levels") or [])
        missing_levels: List[str] = list(rel.get("missing_levels") or [])
        per_label: dict = record.get("per_label") or {}

        # ------------------------------------------------------------------- #
        # Check 1 — missing interior level(s) (always active, never border-
        # suppressed: interior by construction).
        # ------------------------------------------------------------------- #
        if missing_levels:
            ordered_missing = _canonical_sort(missing_levels)
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=severity,
                    reason=(
                        f"{_MISSING_INTERIOR_TAG} "
                        f"{', '.join(ordered_missing)} absent within the "
                        f"observed present-level span."
                    ),
                    labels=frozenset(),
                )
            )

        # ------------------------------------------------------------------- #
        # Check 2 — expected span (opt-in; border-aware).
        # ------------------------------------------------------------------- #
        expected_levels = [
            name for name in (expected_levels_raw or []) if name in _CANONICAL_RANK
        ]
        if expected_levels and present_levels:
            expected_ordered = _canonical_sort(set(expected_levels))
            present_set = set(present_levels)
            top_rank = _CANONICAL_RANK.get(present_levels[0], -1)
            bottom_rank = _CANONICAL_RANK.get(present_levels[-1], -1)

            # The FOV-covered-span descriptor (item 089) — the single shared
            # source both this rule and `border` resolve the covered span
            # through, so they can never disagree about where it ends.
            fov = derive_fov_coverage(record)

            beyond_end_absent: List[str] = []
            for name in expected_ordered:
                if name in present_set:
                    continue
                rank = _CANONICAL_RANK[name]
                if top_rank != -1 and rank < top_rank:
                    # Beyond the superior end.
                    if border_aware:
                        # FOV-aware (item 089): truncated -> outside the
                        # covered FOV, never flagged; non-truncated -> only
                        # the single immediately-adjacent level is inside the
                        # covered FOV (the conservative floor — AC9/AC10).
                        if fov.superior_truncated:
                            continue
                        if rank != fov.superior_adjacent_rank:
                            continue
                    beyond_end_absent.append(name)
                elif bottom_rank != -1 and rank > bottom_rank:
                    # Beyond the inferior end — symmetric.
                    if border_aware:
                        if fov.inferior_truncated:
                            continue
                        if rank != fov.inferior_adjacent_rank:
                            continue
                    beyond_end_absent.append(name)
                # Levels ranked strictly between top_rank and bottom_rank are
                # interior — already reported (or would be) by check 1; excluded
                # here to avoid double-flagging.

            if beyond_end_absent:
                ordered_absent = _canonical_sort(beyond_end_absent)
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_INCOMPLETE_SPAN_TAG} expected level(s) "
                            f"{', '.join(ordered_absent)} absent beyond the "
                            f"present span."
                        ),
                        labels=frozenset(),
                    )
                )

        # ------------------------------------------------------------------- #
        # Check 3 — expected count (opt-in; not border-aware).
        # ------------------------------------------------------------------- #
        if expected_count is not None:
            present_count = len(present_levels)
            minimum = int(expected_count)
            if present_count < minimum:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_COUNT_SHORTFALL_TAG} present count "
                            f"{present_count} is below expected minimum "
                            f"{minimum}."
                        ),
                        labels=frozenset(),
                    )
                )

        return findings


def _find_entry_by_level_name(per_label: dict, level_name: str) -> Optional[dict]:
    """Locate a ``per_label`` entry whose ``level_name`` matches *level_name*.

    Returns ``None`` if no entry matches or *per_label* is not a mapping, so
    the caller treats an absent span-end entry as not touching the border
    (the conservative choice — AC15 tolerance, per the spec's pinned lookup).
    """
    if not isinstance(per_label, dict):
        return None
    for entry in per_label.values():
        if isinstance(entry, dict) and entry.get("level_name") == level_name:
            return entry
    return None
