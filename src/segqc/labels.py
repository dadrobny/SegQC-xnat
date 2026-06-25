"""Label convention — integer labels <-> anatomical vertebrae (item 004).

This module is the **anatomy layer** over the loader's raw label inventory
(item 003). The loader exposes only integer label values and voxel counts
(``Case.label_inventory``, ``{label_value: voxel_count}``); this module maps
those integers to anatomical vertebra names (C1-C7, T1-T13, L1-L6, S, ...) and
back, and summarises a raw inventory into a human-meaningful form that separates
recognised vertebrae from unknown labels.

The convention is **tool-agnostic** (vision sections 4 and 5.1): the default is
the TotalSegmentator / VerSe vertebra numbering, but a caller can override it
with their own ``{value: name}`` mapping without code changes.

Scope (item 004): the name <-> value <-> ordinal convention plus an inventory
summariser. It makes **no** pass/fail judgement (verdicts are Stage 1/4), reads
**no** files (the on-disk heuristic-config schema is item 005), and does **not**
edit the CLI (item 006). It raises :class:`segqc.io.SegQCInputError` on a
malformed override so callers catch one input-error type for both load and
label-convention problems.

Public API
----------
``DEFAULT_LABEL_MAP`` : ``dict[int, str]``
    The default TotalSegmentator / VerSe value -> name table.
``CANONICAL_ORDER`` : ``tuple[str, ...]``
    Vertebra names in head-to-tail anatomical order.
``UNKNOWN`` : ``str``
    Sentinel name returned for an unmapped integer label.
``LabelConvention``
    Bidirectional, immutable label<->name convention (default or custom).
``InventorySummary``
    Result of :func:`summarise_inventory` — recognised vs unknown labels.
``summarise_inventory(inventory, convention=...) -> InventorySummary``
    Turn a raw ``{label: count}`` inventory into a named, ordered summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from .io import SegQCInputError

__all__ = [
    "DEFAULT_LABEL_MAP",
    "CANONICAL_ORDER",
    "UNKNOWN",
    "LabelConvention",
    "InventorySummary",
    "summarise_inventory",
]

# Sentinel name for an integer label with no mapping. ``name_of`` always returns
# a ``str`` (never ``None``), which keeps CLI/report formatting (item 006)
# simple; use :meth:`LabelConvention.is_known` for the boolean test.
UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Default TotalSegmentator / VerSe convention
# --------------------------------------------------------------------------- #
#
# The VerSe / TotalSegmentator vertebra numbering (Decision 2). The contiguous
# 1..26 block is the classic VerSe ordering; the two transitional vertebrae
# (T13, L6) occupy the high end of the range after the sacrum/coccyx, matching
# TotalSegmentator's published label scheme. Integer order therefore does *not*
# equal anatomical order (T13 sits between T12 and L1 anatomically but is value
# 28); ``CANONICAL_ORDER`` is the source of truth for anatomical ordering.
DEFAULT_LABEL_MAP: Dict[int, str] = {
    # Cervical C1-C7
    1: "C1",
    2: "C2",
    3: "C3",
    4: "C4",
    5: "C5",
    6: "C6",
    7: "C7",
    # Thoracic T1-T12
    8: "T1",
    9: "T2",
    10: "T3",
    11: "T4",
    12: "T5",
    13: "T6",
    14: "T7",
    15: "T8",
    16: "T9",
    17: "T10",
    18: "T11",
    19: "T12",
    # Lumbar L1-L5
    20: "L1",
    21: "L2",
    22: "L3",
    23: "L4",
    24: "L5",
    # Sacrum / coccyx
    25: "S",
    26: "Cocygis",
    # Transitional vertebrae (high end of the range)
    28: "T13",
    29: "L6",
}

# Head-to-tail anatomical order (Decision: integer order != anatomical order).
# The recognised entries of an :class:`InventorySummary` are presented in this
# order; later "missing level" / continuity logic (Stage 2/4) keys off it too.
CANONICAL_ORDER: Tuple[str, ...] = (
    "C1", "C2", "C3", "C4", "C5", "C6", "C7",
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12",
    "T13",
    "L1", "L2", "L3", "L4", "L5", "L6",
    "S", "Cocygis",
)

# Rank of each canonical name for O(1) ordering of summary entries. Names not in
# CANONICAL_ORDER (possible only via a custom override) sort after the canonical
# ones, then by name, so a custom convention never crashes the summariser.
_CANONICAL_RANK: Dict[str, int] = {name: i for i, name in enumerate(CANONICAL_ORDER)}


def _order_key(name: str) -> Tuple[int, str]:
    """Sort key placing canonical names in anatomical order, others after."""
    return (_CANONICAL_RANK.get(name, len(CANONICAL_ORDER)), name)


def _normalise_name(name: str) -> str:
    """Normalise a name for case-insensitive, whitespace-tolerant lookup."""
    return name.strip().upper()


# --------------------------------------------------------------------------- #
# LabelConvention
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LabelConvention:
    """An immutable, bidirectional integer-label <-> vertebra-name convention.

    Construct the shipped default with :meth:`default`, or a custom convention
    with :meth:`from_mapping`. Both lookup directions are total and
    side-effect-free: :meth:`name_of` returns :data:`UNKNOWN` for an unmapped
    integer (never raises, never guesses), and :meth:`value_of` returns ``None``
    for an unknown name. Construction is the only place this type raises — on a
    malformed override (duplicate names) it raises
    :class:`segqc.io.SegQCInputError`.

    Attributes
    ----------
    value_to_name:
        The authoritative ``{label_value: name}`` mapping. Names are stored
        verbatim (e.g. ``"C1"``, ``"S"``); lookups by name are normalised
        (case-insensitive, whitespace-stripped).
    """

    value_to_name: Mapping[int, str]
    # Reverse map keyed by the *normalised* name. Built in __post_init__ and set
    # via object.__setattr__ because the dataclass is frozen.
    _name_to_value: Mapping[str, int]

    # -- construction -------------------------------------------------------- #

    @classmethod
    def default(cls) -> "LabelConvention":
        """Return the default TotalSegmentator / VerSe convention."""
        return cls.from_mapping(DEFAULT_LABEL_MAP)

    @classmethod
    def from_mapping(cls, value_to_name: Mapping[int, str]) -> "LabelConvention":
        """Build a convention from a custom ``{label_value: name}`` mapping.

        The mapping is **authoritative** — it fully replaces the default rather
        than layering over it (Decision 5), so a segmenter with its own numbering
        can be described directly.

        Parameters
        ----------
        value_to_name:
            ``{label_value: anatomical_name}``. Values must be integers; names
            must be unique (a bijection) so the reverse lookup is unambiguous.

        Raises
        ------
        segqc.io.SegQCInputError
            If two values map to the same (normalised) name, or a key is not an
            integer.
        """
        frozen: Dict[int, str] = {}
        reverse: Dict[str, int] = {}
        for raw_value, raw_name in value_to_name.items():
            try:
                value = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise SegQCInputError(
                    f"Label convention keys must be integers; got {raw_value!r}."
                ) from exc
            name = str(raw_name)
            key = _normalise_name(name)
            if key in reverse:
                raise SegQCInputError(
                    "Duplicate vertebra name in label convention: "
                    f"{name!r} maps from both value {reverse[key]} and {value}."
                )
            frozen[value] = name
            reverse[key] = value
        # Frozen dataclass: assign the (immutable-by-convention) maps via the
        # base setattr. Wrap in dict() copies so external mutation can't leak in.
        return cls(value_to_name=dict(frozen), _name_to_value=dict(reverse))

    # -- lookups ------------------------------------------------------------- #

    def name_of(self, value: int) -> str:
        """Return the anatomical name for ``value``, or :data:`UNKNOWN`.

        Total and non-throwing: any integer (including negative, very large, or
        unmapped values) yields a ``str`` — the mapped name or ``UNKNOWN``.
        """
        return self.value_to_name.get(int(value), UNKNOWN)

    def value_of(self, name: str) -> Optional[int]:
        """Return the integer label for ``name``, or ``None`` if unknown.

        Lookup is case-insensitive and whitespace-tolerant (``" l1 "`` resolves
        to ``L1``). Returns ``None`` rather than raising for an unknown name
        (Decision 3) — symmetric with :meth:`name_of`'s ``UNKNOWN`` sentinel.
        """
        return self._name_to_value.get(_normalise_name(name))

    def is_known(self, value: int) -> bool:
        """Return ``True`` if ``value`` has a mapping in this convention."""
        return int(value) in self.value_to_name


# --------------------------------------------------------------------------- #
# Inventory summariser
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class InventorySummary:
    """A named, ordered summary of a raw label inventory.

    Attributes
    ----------
    recognised:
        ``(value, name, count)`` triples for labels mapped by the convention,
        ordered head-to-tail by :data:`CANONICAL_ORDER`.
    unknown:
        ``(value, count)`` pairs for labels with no mapping — surfaced
        explicitly, never dropped. Ordered by ascending label value.
    """

    recognised: List[Tuple[int, str, int]]
    unknown: List[Tuple[int, int]]

    @property
    def n_recognised(self) -> int:
        """Number of recognised (mapped) labels present."""
        return len(self.recognised)

    @property
    def n_unknown(self) -> int:
        """Number of unknown (unmapped) labels present."""
        return len(self.unknown)

    @property
    def present_levels(self) -> List[str]:
        """Anatomical names of the recognised labels, in anatomical order."""
        return [name for _value, name, _count in self.recognised]


def summarise_inventory(
    inventory: Mapping[int, int],
    convention: Optional[LabelConvention] = None,
) -> InventorySummary:
    """Summarise a raw ``{label: count}`` inventory using a label convention.

    Partitions the present labels into **recognised** (mapped to an anatomical
    name) and **unknown** (no mapping), attaches names and voxel counts, and
    orders recognised entries head-to-tail by :data:`CANONICAL_ORDER`. Unknown
    labels are surfaced in :attr:`InventorySummary.unknown` — never dropped and
    never raising — so out-of-range, negative, or unmapped integers are handled
    gracefully.

    Parameters
    ----------
    inventory:
        ``{label_value: voxel_count}`` over present labels, e.g. the loader's
        :attr:`segqc.io.Case.label_inventory`. An empty mapping yields empty
        recognised/unknown lists.
    convention:
        The :class:`LabelConvention` to name labels with. Defaults to the shipped
        TotalSegmentator / VerSe convention.

    Returns
    -------
    InventorySummary
    """
    if convention is None:
        convention = LabelConvention.default()

    recognised: List[Tuple[int, str, int]] = []
    unknown: List[Tuple[int, int]] = []
    for raw_value, raw_count in inventory.items():
        value = int(raw_value)
        count = int(raw_count)
        if convention.is_known(value):
            recognised.append((value, convention.name_of(value), count))
        else:
            unknown.append((value, count))

    recognised.sort(key=lambda triple: _order_key(triple[1]))
    unknown.sort(key=lambda pair: pair[0])
    return InventorySummary(recognised=recognised, unknown=unknown)