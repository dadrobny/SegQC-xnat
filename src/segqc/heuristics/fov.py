"""Shared field-of-view (FOV) covered-span derivation (item 089).

A single pure abstraction so ``coverage`` (item 029) and ``border`` (item 031)
agree on exactly one field-of-view-covered vertebra span, rather than each
rule re-deriving (and potentially disagreeing on) it independently. Real
spine CT scans are legitimately partial (cervical-only, lumbar-only,
mid-thoracic, ...); a vertebra level lying beyond the scanned FOV is not a
missing level, and the topmost/bottommost segmented vertebra abutting the FOV
boundary is not a border defect.

The covered span is ``[present_levels[0] .. present_levels[-1]]``
(``relationships.present_levels``, item 014, canonical head-to-tail order —
item 004's :data:`segqc.labels.CANONICAL_ORDER`). A span end is **truncated**
when its extremal segmented vertebra's geometry touches the corresponding
cranio-caudal image face (``touches_superior`` / ``touches_inferior``, item
011's fixed cranio-caudal = ``x``-axis convention) — an *exact* border-contact
flag, not a voxel-margin proximity (the record carries no image shape to
compute a margin against; see item 089's Assumptions).

This module registers no rule (mirrors no ``Rule`` subclass, no
``register_rule`` call) — it is a plain, pure, non-mutating helper that
``coverage.py`` and ``border.py`` import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from segqc.labels import CANONICAL_ORDER

__all__ = ["FovCoverage", "derive_fov_coverage"]


# --------------------------------------------------------------------------- #
# Canonical-rank map — built once at import for O(1) ordering / comparisons
# (mirrors coverage.py's own map; duplicated deliberately so this module has
# no import-order dependency on coverage.py).
# --------------------------------------------------------------------------- #

_CANONICAL_RANK: Dict[str, int] = {name: i for i, name in enumerate(CANONICAL_ORDER)}


@dataclass(frozen=True)
class FovCoverage:
    """Descriptor of the FOV-covered vertebra span for one case record.

    Attributes
    ----------
    superior_end_level:
        ``relationships.present_levels[0]`` (most-superior present level), or
        ``None`` if no span is determinable (:attr:`has_span` is ``False``).
    inferior_end_level:
        ``relationships.present_levels[-1]`` (most-inferior present level), or
        ``None`` if no span is determinable.
    superior_truncated:
        ``True`` iff the superior end's geometry touches the superior
        cranio-caudal face (``touches_superior``) — the FOV is cropped through
        it. ``False`` (never raising) if the end level has no matching
        ``per_label`` entry — the conservative choice.
    inferior_truncated:
        Symmetric with :attr:`superior_truncated`, for ``touches_inferior``.
    has_span:
        ``True`` iff ``present_levels`` is non-empty (a covered span is
        determinable at all).
    """

    superior_end_level: Optional[str]
    inferior_end_level: Optional[str]
    superior_truncated: bool
    inferior_truncated: bool
    has_span: bool

    @property
    def superior_rank(self) -> Optional[int]:
        """Canonical rank of :attr:`superior_end_level`, or ``None``."""
        if self.superior_end_level is None:
            return None
        return _CANONICAL_RANK.get(self.superior_end_level)

    @property
    def inferior_rank(self) -> Optional[int]:
        """Canonical rank of :attr:`inferior_end_level`, or ``None``."""
        if self.inferior_end_level is None:
            return None
        return _CANONICAL_RANK.get(self.inferior_end_level)

    @property
    def superior_adjacent_rank(self) -> Optional[int]:
        """The one-canonical-step-more-superior rank beyond the superior end.

        ``None`` when the superior end's own rank is unknown/undeterminable or
        already at the head of :data:`CANONICAL_ORDER` (rank 0 — no level is
        further superior).
        """
        rank = self.superior_rank
        if rank is None or rank <= 0:
            return None
        return rank - 1

    @property
    def inferior_adjacent_rank(self) -> Optional[int]:
        """The one-canonical-step-more-inferior rank beyond the inferior end.

        ``None`` when the inferior end's own rank is unknown/undeterminable or
        already at the tail of :data:`CANONICAL_ORDER`.
        """
        rank = self.inferior_rank
        if rank is None or rank >= len(CANONICAL_ORDER) - 1:
            return None
        return rank + 1

    def is_beyond_superior(self, rank: int) -> bool:
        """``True`` iff *rank* lies beyond (more superior than) the span's
        superior end."""
        top_rank = self.superior_rank
        return top_rank is not None and rank < top_rank

    def is_beyond_inferior(self, rank: int) -> bool:
        """``True`` iff *rank* lies beyond (more inferior than) the span's
        inferior end."""
        bottom_rank = self.inferior_rank
        return bottom_rank is not None and rank > bottom_rank


_NOT_DETERMINABLE = FovCoverage(
    superior_end_level=None,
    inferior_end_level=None,
    superior_truncated=False,
    inferior_truncated=False,
    has_span=False,
)


def _find_entry_by_level_name(per_label: dict, level_name: str) -> Optional[dict]:
    """Locate a ``per_label`` entry whose ``level_name`` matches *level_name*.

    Returns ``None`` if no entry matches or *per_label* is not a mapping —
    the caller treats a missing span-end entry as not touching the border
    (conservative: surfaces a possible miss / clip rather than hiding it).
    Mirrors ``coverage.py``'s (item 029) lookup convention: ``per_label`` is
    keyed by integer label, not level name, so it must be scanned.
    """
    if not isinstance(per_label, dict):
        return None
    for entry in per_label.values():
        if isinstance(entry, dict) and entry.get("level_name") == level_name:
            return entry
    return None


def derive_fov_coverage(record: dict) -> FovCoverage:
    """Derive the FOV-covered vertebra span for *record*.

    Parameters
    ----------
    record:
        Per-case feature dict (read-only, never mutated). Reads
        ``record["relationships"]["present_levels"]`` (item 014) and
        ``record["per_label"]`` (item 016) to locate each span end's
        ``geometry.touches_superior`` / ``touches_inferior`` (item 011).

    Returns
    -------
    FovCoverage
        The covered-span descriptor. Conservative and never raising on a
        degenerate record: absent/``None``/non-mapping ``relationships``, an
        empty ``present_levels``, or a missing span-end ``per_label`` entry
        all yield ``has_span == False`` (or, for a missing entry only, that
        end's ``*_truncated == False``) rather than raising.
    """
    rel = record.get("relationships")
    if not isinstance(rel, dict):
        return _NOT_DETERMINABLE

    present_levels = list(rel.get("present_levels") or [])
    if not present_levels:
        return _NOT_DETERMINABLE

    superior_end_level = present_levels[0]
    inferior_end_level = present_levels[-1]

    per_label = record.get("per_label") or {}
    superior_entry = _find_entry_by_level_name(per_label, superior_end_level)
    inferior_entry = _find_entry_by_level_name(per_label, inferior_end_level)

    superior_truncated = bool(
        (superior_entry or {}).get("geometry", {}).get("touches_superior", False)
    )
    inferior_truncated = bool(
        (inferior_entry or {}).get("geometry", {}).get("touches_inferior", False)
    )

    return FovCoverage(
        superior_end_level=superior_end_level,
        inferior_end_level=inferior_end_level,
        superior_truncated=superior_truncated,
        inferior_truncated=inferior_truncated,
        has_span=True,
    )
