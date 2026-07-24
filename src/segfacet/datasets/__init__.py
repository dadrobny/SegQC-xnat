"""segfacet.datasets — dataset-agnostic ``Cohort``/``Case`` interface + declarative
per-dataset adapters (Stage 13, item 086).

Why this exists
---------------
The pipeline's original cohort ingestion
(:func:`segfacet.reference.ingest.ingest_cohort`) is **flat, non-recursive, and
hardcodes a ``<id>_scan.nii.gz`` sibling**, so a nested/varied real dataset —
e.g. VerSe's ``derivatives/sub-verseNNN/…_seg-vert_msk.nii.gz`` masks with
``rawdata/…_ct.nii.gz`` scans — cannot be read without manual copy/symlink
staging. This module removes that friction: a small, declarative **descriptor**
per dataset plus a **resolver** that materialises a dataset-agnostic
:class:`Cohort` of :class:`Case`s.

The framework ↔ adapter boundary
--------------------------------
The framework stays **dataset-agnostic**: its operations consume only a
:class:`Cohort` (an ordered, deterministic collection of :class:`Case`s).
Everything dataset-specific — folder structure, filename conventions, label
mapping, and *how a subset of cases is selected* — lives in the descriptor here.
A train/val/test "split" is just **one kind of subset** an adapter can produce;
the framework must not expect pre-split datasets (another dataset might select a
subset via a CSV / id-list / glob). Held-out evaluation = "ask the adapter for
two disjoint subsets"; the framework only ever sees two plain cohorts.

Scope (item 086)
----------------
This module provides **only** the interface + descriptor schema + resolver.
Wiring the resolver into ``ingest_cohort`` / the evaluate-manifest builder and
the CLI (``--dataset-schema`` / ``--data-root`` / ``--subset``) is item 087; the
committed VerSe19 descriptor + Stage-13 acceptance is item 088. It reads no
scan/segmentation *voxels* (only the filesystem layout) and mutates nothing.
"""

from __future__ import annotations

import csv
import fnmatch
import glob
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from segfacet.labels import LabelConvention

__all__ = [
    "ROLE_GT",
    "ROLE_CANDIDATE",
    "DatasetSchemaError",
    "Case",
    "Cohort",
    "DatasetDescriptor",
    "resolve",
    "load_descriptor",
    "bundled_descriptor_path",
]


def bundled_descriptor_path(name: str) -> "Path":
    """Return the path to a descriptor shipped as package data under
    ``segfacet/datasets/`` (e.g. ``"verse19.yaml"``).

    Raises :class:`DatasetSchemaError` if no such bundled descriptor exists.
    """
    from pathlib import Path as _Path

    p = _Path(__file__).resolve().parent / name
    if not p.is_file():
        raise DatasetSchemaError(f"no bundled dataset descriptor named {name!r}")
    return p

#: The two roles a resolved segmentation can play. ``gt`` = ground truth that
#: *grounds* the reference/heuristics (plane 2); ``candidate`` = an automatic
#: segmentation being *judged against* the reference (plane 3).
ROLE_GT = "gt"
ROLE_CANDIDATE = "candidate"
_VALID_ROLES = frozenset({ROLE_GT, ROLE_CANDIDATE})

#: Named label conventions a descriptor may request. Only the shipped default
#: (TotalSegmentator / VerSe numbering) is built in; a dataset with its own
#: label scheme is a future extension (a descriptor-level ``{value: name}`` map).
_NAMED_CONVENTIONS = {
    "default": LabelConvention.default,
    "verse": LabelConvention.default,
    "totalsegmentator": LabelConvention.default,
}


class DatasetSchemaError(Exception):
    """Raised for a malformed dataset descriptor or an unresolvable request
    (unknown subset, invalid role, un-extractable ``case_id``, …).

    A single, actionable exception type so callers catch one error for every
    descriptor/resolution problem, never a bare ``KeyError``/``re.error``.
    """


# --------------------------------------------------------------------------- #
# Framework-facing data model (dataset-agnostic)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Case:
    """One resolved case the framework can consume, free of any dataset layout.

    Attributes
    ----------
    case_id:
        Stable identifier extracted per the descriptor (e.g. ``sub-verse004`` or,
        for a split subject, ``sub-verse004_split-verse123``). Unique within a
        :class:`Cohort`.
    seg_path:
        Absolute path to this case's segmentation label map (NIfTI).
    scan_path:
        Absolute path to the matching intensity scan, or ``None`` when the
        descriptor declares no scan or none is found on disk.
    role:
        ``"gt"`` or ``"candidate"`` — see :data:`ROLE_GT` / :data:`ROLE_CANDIDATE`.
    label_convention:
        The resolved :class:`~segfacet.labels.LabelConvention` for normalising this
        case's integer labels to anatomical names.
    metadata:
        Optional free-form mapping (e.g. the subset name, named regex groups).
    """

    case_id: str
    seg_path: str
    scan_path: Optional[str]
    role: str
    label_convention: LabelConvention
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Cohort:
    """An ordered, deterministic collection of :class:`Case`s.

    The single interface the framework's ``run`` / ``build-reference`` /
    ``evaluate`` operations consume. Iterable and sized; ``cases`` is sorted by
    ``case_id`` so ingestion/aggregation are reproducible.
    """

    cases: Tuple[Case, ...]
    name: Optional[str] = None  # e.g. the subset this cohort was resolved for

    def __iter__(self):
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)

    @property
    def case_ids(self) -> Tuple[str, ...]:
        return tuple(c.case_id for c in self.cases)


# --------------------------------------------------------------------------- #
# Declarative descriptor
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DatasetDescriptor:
    """A declarative, per-dataset adapter mapping an on-disk dataset onto the
    :class:`Cohort`/:class:`Case` interface.

    Fields
    ------
    data_root:
        Base directory the dataset lives under. May be overridden at
        :func:`resolve` time (so one committed descriptor works across machines).
        In YAML, write Windows paths with **forward slashes** (``C:/data/VerSe``)
        or in single quotes: a *double-quoted* native path (``"C:\\data\\VerSe"``)
        is parsed for backslash escapes (``\\U`` -> unicode escape, ``\\t`` -> tab)
        and fails to load. ``Path``/``glob`` accept forward slashes on Windows.
    seg:
        A glob (relative to the resolved root, ``**`` supported) matching every
        segmentation label map, e.g. ``derivatives/sub-*/**/*_seg-vert_msk.nii.gz``.
    case_id:
        A regular expression applied to each seg match's **path relative to the
        resolved root** (posix separators) carrying a named group ``id`` whose
        capture is the case id, e.g.
        ``r"(?P<id>sub-verse\\d+(?:_split-verse\\d+)?)_seg-vert_msk\\.nii\\.gz$"``.
        Any additional named groups are exposed for ``scan`` templating and in
        ``Case.metadata``.
    scan:
        Optional template (relative to the resolved root) for the matching scan,
        with ``{id}`` and any named ``case_id`` groups substituted; ``*``/``?``
        globs are allowed and the first existing match is used. ``None``/absent →
        seg-only (``Case.scan_path is None``).
    label_convention:
        Name of a built-in convention (:data:`_NAMED_CONVENTIONS`); defaults to
        ``"default"``.
    role:
        ``"gt"`` (default) or ``"candidate"`` — may be overridden at resolve time.
    subsets:
        Optional mapping ``name -> selector``. A selector is a dict with exactly
        one of: ``{"root": "<subdir>"}`` (resolve under a sibling/child dir — how
        VerSe's train/val/test folders are modelled), ``{"ids": [...]}`` (keep
        those case ids), ``{"csv": "<path>", "column": "<col>"}`` (case ids from a
        CSV column; path relative to the descriptor's own dir), or
        ``{"glob": "<pat>"}`` (keep case ids matching an fnmatch pattern).
    descriptor_dir:
        Directory the descriptor was loaded from (for resolving relative CSV
        selector paths); ``None`` for an in-memory descriptor.
    """

    data_root: str
    seg: str
    case_id: str
    scan: Optional[str] = None
    label_convention: str = "default"
    role: str = ROLE_GT
    subsets: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    descriptor_dir: Optional[str] = None

    def __post_init__(self):
        if not self.data_root or not str(self.data_root).strip():
            raise DatasetSchemaError("descriptor 'data_root' must be a non-empty path")
        if not self.seg or not str(self.seg).strip():
            raise DatasetSchemaError("descriptor 'seg' glob must be non-empty")
        if self.role not in _VALID_ROLES:
            raise DatasetSchemaError(
                f"descriptor 'role' must be one of {sorted(_VALID_ROLES)}, got {self.role!r}"
            )
        if self.label_convention not in _NAMED_CONVENTIONS:
            raise DatasetSchemaError(
                f"unknown label_convention {self.label_convention!r}; "
                f"known: {sorted(_NAMED_CONVENTIONS)}"
            )
        try:
            compiled = re.compile(self.case_id)
        except re.error as exc:
            raise DatasetSchemaError(f"descriptor 'case_id' is not a valid regex: {exc}") from exc
        if "id" not in compiled.groupindex:
            raise DatasetSchemaError(
                "descriptor 'case_id' regex must contain a named group '(?P<id>...)'"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, descriptor_dir: Optional[str] = None) -> "DatasetDescriptor":
        if not isinstance(data, Mapping):
            raise DatasetSchemaError(
                f"descriptor must be a mapping, got {type(data).__name__!r}"
            )
        known = {"data_root", "seg", "case_id", "scan", "label_convention", "role", "subsets"}
        unknown = set(data) - known
        if unknown:
            raise DatasetSchemaError(f"descriptor has unknown key(s): {sorted(unknown)}")
        missing = {"data_root", "seg", "case_id"} - set(data)
        if missing:
            raise DatasetSchemaError(f"descriptor missing required key(s): {sorted(missing)}")
        return cls(
            data_root=str(data["data_root"]),
            seg=str(data["seg"]),
            case_id=str(data["case_id"]),
            scan=(str(data["scan"]) if data.get("scan") is not None else None),
            label_convention=str(data.get("label_convention", "default")),
            role=str(data.get("role", ROLE_GT)),
            subsets=dict(data.get("subsets") or {}),
            descriptor_dir=descriptor_dir,
        )


def load_descriptor(path: "str | os.PathLike") -> DatasetDescriptor:
    """Load a descriptor from a YAML or JSON file.

    Raises :class:`DatasetSchemaError` for a missing file, invalid YAML/JSON, or
    a malformed descriptor.
    """
    import yaml  # lazy: PyYAML is a core dep but only needed to load a file

    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DatasetSchemaError(f"dataset descriptor not found: {p}") from exc
    try:
        data = yaml.safe_load(raw)  # a superset of JSON
    except yaml.YAMLError as exc:
        raise DatasetSchemaError(f"dataset descriptor is not valid YAML/JSON: {p}\n{exc}") from exc
    return DatasetDescriptor.from_dict(data, descriptor_dir=str(p.resolve().parent))


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #


def _select_root(descriptor: DatasetDescriptor, base_root: Path, subset: Optional[str]) -> Tuple[Path, Optional[Mapping[str, Any]]]:
    """Return the (possibly subset-overridden) root and the residual case-id
    filter selector (``None`` when the subset only overrode the root)."""
    if subset is None:
        return base_root, None
    if subset not in descriptor.subsets:
        raise DatasetSchemaError(
            f"unknown subset {subset!r}; known: {sorted(descriptor.subsets)}"
        )
    selector = dict(descriptor.subsets[subset])
    if "root" in selector:
        return (base_root / str(selector["root"])), None
    return base_root, selector


def _case_id_filter(selector: Mapping[str, Any], descriptor: DatasetDescriptor) -> "set[str] | None":
    """Turn a residual subset selector (ids / csv / glob) into a predicate set of
    case ids, or ``None`` for a glob (handled by pattern match)."""
    if "ids" in selector:
        return {str(x) for x in selector["ids"]}
    if "csv" in selector:
        csv_path = Path(selector["csv"])
        if not csv_path.is_absolute() and descriptor.descriptor_dir:
            csv_path = Path(descriptor.descriptor_dir) / csv_path
        column = str(selector.get("column", "case_id"))
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None or column not in reader.fieldnames:
                    raise DatasetSchemaError(
                        f"subset CSV {csv_path} has no column {column!r} "
                        f"(columns: {reader.fieldnames})"
                    )
                return {row[column].strip() for row in reader if row.get(column, "").strip()}
        except FileNotFoundError as exc:
            raise DatasetSchemaError(f"subset CSV not found: {csv_path}") from exc
    return None  # glob handled separately


def resolve(
    descriptor: DatasetDescriptor,
    *,
    data_root: "Optional[str | os.PathLike]" = None,
    subset: Optional[str] = None,
    role: Optional[str] = None,
) -> Cohort:
    """Materialise a :class:`Cohort` from a descriptor.

    Parameters
    ----------
    descriptor:
        The dataset adapter.
    data_root:
        Override the descriptor's ``data_root`` (so one committed descriptor works
        across machines). The resolved paths in each :class:`Case` are absolute.
    subset:
        Name of a subset in ``descriptor.subsets`` to restrict to (a folder split,
        CSV, id-list, or glob). ``None`` = the whole dataset.
    role:
        Override the descriptor's ``role`` (``"gt"`` / ``"candidate"``).

    Returns
    -------
    Cohort
        Cases sorted by ``case_id`` (deterministic). Read-only; discovers files
        only, never reads voxels.

    Raises
    ------
    DatasetSchemaError
        For an unknown subset, invalid role, a ``case_id`` regex that fails to
        match a discovered seg file, or a duplicate ``case_id``.
    """
    effective_role = role if role is not None else descriptor.role
    if effective_role not in _VALID_ROLES:
        raise DatasetSchemaError(
            f"role must be one of {sorted(_VALID_ROLES)}, got {effective_role!r}"
        )
    convention = _NAMED_CONVENTIONS[descriptor.label_convention]()

    base_root = Path(data_root) if data_root is not None else Path(descriptor.data_root)
    root, residual_selector = _select_root(descriptor, base_root, subset)

    id_regex = re.compile(descriptor.case_id)
    seg_pattern = str(root / descriptor.seg)
    seg_matches = sorted(glob.glob(seg_pattern, recursive=True))

    id_filter = _case_id_filter(residual_selector, descriptor) if residual_selector else None
    glob_pat = residual_selector.get("glob") if residual_selector else None

    cases: List[Case] = []
    seen: Dict[str, str] = {}
    for seg_path in seg_matches:
        rel = Path(seg_path).relative_to(root).as_posix()
        m = id_regex.search(rel)
        if m is None:
            raise DatasetSchemaError(
                f"case_id regex {descriptor.case_id!r} did not match seg path {rel!r}"
            )
        case_id = m.group("id")
        groups = {k: v for k, v in m.groupdict().items() if v is not None}

        # Subset filtering (residual: ids / csv / glob).
        if id_filter is not None and case_id not in id_filter:
            continue
        if glob_pat is not None and not fnmatch.fnmatch(case_id, str(glob_pat)):
            continue

        if case_id in seen:
            raise DatasetSchemaError(
                f"duplicate case_id {case_id!r} from {seen[case_id]!r} and {rel!r}"
            )
        seen[case_id] = rel

        scan_path = _resolve_scan(descriptor, root, case_id, groups)
        cases.append(
            Case(
                case_id=case_id,
                seg_path=str(Path(seg_path).resolve()),
                scan_path=scan_path,
                role=effective_role,
                label_convention=convention,
                metadata={"subset": subset} if subset else {},
            )
        )

    cases.sort(key=lambda c: c.case_id)
    return Cohort(cases=tuple(cases), name=subset)


def _resolve_scan(
    descriptor: DatasetDescriptor,
    root: Path,
    case_id: str,
    groups: Mapping[str, str],
) -> Optional[str]:
    """Resolve a case's scan path from the descriptor's ``scan`` template, or
    ``None`` when no template is set or no file matches."""
    if not descriptor.scan:
        return None
    # Named case_id groups (which already include ``id``) plus the ``case_id``
    # alias -- build one field dict so ``id`` is never passed twice.
    fields = {**groups, "id": case_id, "case_id": case_id}
    try:
        rel = descriptor.scan.format(**fields)
    except KeyError as exc:
        raise DatasetSchemaError(
            f"scan template {descriptor.scan!r} references unknown field {exc}"
        ) from exc
    candidate = root / rel
    if any(ch in rel for ch in "*?["):
        matches = sorted(glob.glob(str(candidate), recursive=True))
        return str(Path(matches[0]).resolve()) if matches else None
    return str(candidate.resolve()) if candidate.exists() else None
