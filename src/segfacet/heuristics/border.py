"""Border-partial-vertebra rule (item 031).

Implements a **border-partial-vertebra rule** targeting §6 failure mode 6 — a
partial vertebra at the image border whose appearance is truncated by the
field of view (FOV). It consumes the pre-computed per-label image-border-
contact flags (item 011, exposed under each ``per_label`` entry's ``geometry``
sub-block, via ``geometry_to_dict``, item 016) and, for terminal-position
classification, ``relationships.present_levels`` (item 014). It does not
recompute geometry, border flags, or relationships.

Design decisions (recorded per item 031 spec):
- Cranio-caudal (``touches_superior`` / ``touches_inferior``) is the FOV-end
  axis; the other four faces (``touches_left`` / ``touches_right`` /
  ``touches_anterior`` / ``touches_posterior``) are in-plane and always
  abnormal when touched.
- An expected FOV-end truncation — a touch on only the cranio-caudal end
  face(s), consistent with the vertebra being the terminal one at that end of
  the present-level span — is **suppressed by default** (mirrors item 029's
  border-suppression precedent). ``report_expected_ends`` (default ``False``)
  surfaces it instead, at a separate ``end_severity`` (default ``pass``).
- Anything else (any in-plane touch, or a cranio-caudal end touch on a
  mid-spine or opposite-end vertebra) is an unexpected clip and always emits
  a finding at the configured ``severity`` (default ``flagged-for-review``).
- Findings are **label-attributed** (non-empty ``labels``): a border-touching
  vertebra is present and carries a real integer label, in contrast to item
  029's case-level missing-level findings.
- One finding per offending label, emitted in ascending integer-label order.
- Terminal position is decided from ``relationships.present_levels``, sourced
  via the shared ``segfacet.heuristics.fov.derive_fov_coverage`` helper (item
  089) so ``border`` and ``coverage`` resolve the same covered-span ends and
  can never disagree; when unavailable (``relationships`` None/absent or
  ``present_levels`` empty) a border-touching label is classified
  **unexpected** (surfaced, not hidden).
- Unrecognised severity string raises ValueError before any per-record
  processing; ``end_severity`` is validated only when ``report_expected_ends``
  is true.
- The caller's record is never mutated.
"""

from __future__ import annotations

from typing import Dict, List

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.fov import derive_fov_coverage
from segfacet.heuristics.rule import Rule, register_rule
from segfacet.verdict import Severity

__all__ = ["BorderRule"]


# --------------------------------------------------------------------------- #
# Face groupings — fixed iteration order for the reason face list
# --------------------------------------------------------------------------- #

_END_FACES = ("touches_superior", "touches_inferior")
_IN_PLANE_FACES = (
    "touches_left",
    "touches_right",
    "touches_anterior",
    "touches_posterior",
)
_ALL_FACES = _END_FACES + _IN_PLANE_FACES

_UNEXPECTED_CLIP_TAG = "Partial vertebra clipped by FOV:"
_EXPECTED_END_TAG = "Partial vertebra at FOV end (expected):"


# --------------------------------------------------------------------------- #
# Severity helper (mirrors bounds.py / coverage.py / sequence.py)
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
            f"Unknown severity label {label!r} in border rule config. "
            f"Known labels: {known}."
        )
    return sev


def _sort_key(item):
    """Sort per_label items by ascending integer label (key, falling back to
    the entry's own ``label`` field)."""
    key, entry = item
    try:
        return int(key)
    except (TypeError, ValueError):
        return int(entry.get("label", 0))


# --------------------------------------------------------------------------- #
# BorderRule
# --------------------------------------------------------------------------- #


@register_rule
class BorderRule(Rule):
    """Border-partial-vertebra rule (item 031).

    Emits at most one label-attributed finding per border-touching label,
    classifying each as an expected FOV-end truncation (suppressed by
    default) or an unexpected clip (always flagged).
    """

    rule_id = "border"

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate border contact for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads ``record["per_label"]``
            and ``record["relationships"]``.
        config:
            HeuristicConfig instance. Reads ``rules.border.params``.

        Returns
        -------
        list[Finding]
            Zero or more findings, one per offending label, in ascending
            integer-label order.

        Raises
        ------
        ValueError
            If ``rules.border.params.severity`` is an unrecognised string
            (raised before any per-record processing, AC12).
        """
        # Read severity once up-front; raises immediately on a bad string.
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        report_expected_ends: bool = bool(
            config.rule_param(self.rule_id, "report_expected_ends", default=False)
        )

        findings: List[Finding] = []

        per_label = record.get("per_label") or {}
        if not isinstance(per_label, dict) or not per_label:
            return findings

        # The FOV-covered-span descriptor (item 089) — the single shared
        # source both this rule and `coverage` resolve the covered span
        # through, so terminal-end classification can never disagree between
        # the two rules (AC15).
        fov = derive_fov_coverage(record)
        superior_end = fov.superior_end_level
        inferior_end = fov.inferior_end_level

        end_severity = None  # resolved lazily, only if report_expected_ends

        for key, entry in sorted(per_label.items(), key=_sort_key):
            if not isinstance(entry, dict):
                continue
            geom = entry.get("geometry") or {}
            touched = [f for f in _ALL_FACES if bool(geom.get(f))]
            if not touched:
                continue  # interior — AC2

            level_name = entry.get("level_name")
            is_sup_end = level_name is not None and level_name == superior_end
            is_inf_end = level_name is not None and level_name == inferior_end

            in_plane = any(f in _IN_PLANE_FACES for f in touched)
            expected = (
                not in_plane
                and ("touches_superior" not in touched or is_sup_end)
                and ("touches_inferior" not in touched or is_inf_end)
            )

            label_int = int(entry.get("label", key))
            faces_text = ", ".join(f.removeprefix("touches_") for f in touched)

            if not expected:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_UNEXPECTED_CLIP_TAG} label {label_int} "
                            f"({level_name}) touches image face(s): "
                            f"{faces_text}."
                        ),
                        labels=frozenset({label_int}),
                    )
                )
            elif report_expected_ends:
                if end_severity is None:
                    end_sev_label: str = config.rule_param(
                        self.rule_id, "end_severity", default="pass"
                    )
                    end_severity = _severity_from_param(end_sev_label)
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=end_severity,
                        reason=(
                            f"{_EXPECTED_END_TAG} label {label_int} "
                            f"({level_name}) touches image face(s): "
                            f"{faces_text}."
                        ),
                        labels=frozenset({label_int}),
                    )
                )

        return findings
