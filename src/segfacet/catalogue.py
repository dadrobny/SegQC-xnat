"""Generated feature & rule catalogue (item 103; Stage 19).

The single shared generator behind two committed artifacts
(``docs/aide/feature_catalogue.generated.json`` / ``.md``) and the HTML status
report's Feature Catalogue section (``scripts/aide_status_report.py``). It
replaces the hand-typed ``FEATURE_CATALOG`` literal that used to live in the
status-report script with a catalogue built from the *realised* record shape
plus **code-derived** rule/mode attribution, joined with authored prose from
:mod:`segfacet.feature_docs`.

Four derivation mechanisms, each carrying its own evidence tag
--------------------------------------------------------------
- **A. Dynamic access trace** (``observed``) — wrap a realised driver record in
  a non-invasive ``dict``-subclass proxy (:func:`trace_record_access`) that
  records every leaf path actually read, then run every registered rule
  (:func:`segfacet.heuristics.rule.iter_rules`) over the traced record.
- **B. Static AST scan of ``heuristics/*.py``** (``static``) — string
  constants used as a subscript key or as ``.get(...)``'s first positional
  argument in *each rule's own module file*, matched to catalogue paths by
  last path segment -- but **only when that last segment names exactly one**
  leaf path (item 110, AC11b). Catches branches the driver set never realises
  (e.g. ``overlaps[].overlap_voxels`` when the driver set happens not to
  populate it). A name shared by >1 leaf path's last segment (e.g. ``label``,
  ``level_name``, ``mean``, ``median``, ``std``) carries no positional
  information tying it to a specific block, so it contributes no evidence for
  *any* of its candidates rather than guessing "keep" for all of them
  (the pre-item-110 behaviour, tagged ``static-ambiguous``, produced exactly
  this false-positive shape whenever an unrelated block reused a generic key
  name).
- **C. Static AST scan of ``synth/*.py``** — ``rule_id -> §6 mode(s)``, read
  off every ``Expectation(failure_mode=N, ..., expected_rule_ids=frozenset(
  {...}))`` call's literal keyword pairs. No hand-typed rule-id -> mode
  dictionary exists anywhere in this module's source (drift guard, AC13).
  Exposed publicly as :func:`scan_synth_rule_mode_map`.
- **D. Non-rule consumers** (``observed`` / ``vocabulary``) — the same trace
  proxy run through ``eval.per_mode.compute_per_mode_metrics`` and
  ``human_report.render_feature_table``, plus the declared feature-name
  vocabularies (``reference.delta.MORPHOLOGY_FEATURES``,
  ``reference.ingest.INGESTED_FEATURES``, ``eval.feature_match.
  TRACKED_FEATURES``) matched by last path segment via
  :data:`segfacet.feature_docs.PATH_ALIASES`.

A third source of ``mode_evidence`` (item 136) sits alongside C: each
registered rule's own class-attribute ``RuleModeDeclaration``
(:mod:`segfacet.heuristics.rule`) states the §6 mode(s) it targets (or that
it targets none, or that its disposition is pending). ``mode_evidence`` gains
the tag ``"rule_declaration"`` (ordered last) when at least one of an
entry's ``consuming_rules`` carries a declaration with non-empty ``modes``.
Because this item's declared modes are always a subset of mechanism C's
corpus-derived map (:func:`segfacet.catalogue.rule_declaration_conflicts`
enforces agreement), the declaration source contributes no mode
``failure_modes`` would not already carry from C. Disagreement between the
declaration and the corpus-derived map — in *either* direction — is reported
by :func:`rule_declaration_conflicts`, never silently resolved here.

``consuming_rules = A ∪ B``. ``failure_modes`` = (item-099 mode anchors) ∪
(modes of ``consuming_rules`` under C) ∪ (modes of ``consuming_rules``
declared per rule, item 136 — a subset of the C term on this tree).
``status`` = an authored :data:`segfacet.feature_docs.STATUS_OVERRIDES`
entry if present, else ``"keep"`` when A ∪ B ∪ D is non-empty, else
**``"unwired"``**.

Two tiers, one ``origin``
--------------------------
Every catalogued path is realised by :func:`iter_driver_records` — the
"record"-tier drivers (built from :mod:`segfacet.synth` +
:func:`segfacet.pipeline.extract_feature_record`) and two "augmented" drivers
(``image_features`` / ``reference_delta``, built through the existing
converters over hand-constructed placeholder dataclass instances — no
PyRadiomics, no reference artifact, no scan). Both tiers flow through the
*same* :func:`iter_leaf_paths` walk and therefore the same ``origin ==
"record"`` classification (see the item's Decisions log for why a second
``origin`` value is not introduced: nothing downstream needs to distinguish
them and doing so would break the driver-union coverage equality, AC6).

Determinism contract
---------------------
:func:`build_catalogue` never mutates any input; two calls return equal
catalogues. :func:`catalogue_to_dict` / :func:`render_markdown` are pure
functions of the catalogue and are byte-reproducible within one session.
Heavy imports (NumPy/SciPy/NiBabel, via ``segfacet.pipeline``/
``segfacet.synth``) are deferred into function bodies, per ``cli.py``'s house
style, so ``import segfacet.catalogue`` alone stays cheap.

Scope fence
-----------
This module does **not** change any extractor, rule, threshold, schema,
report, or CLI behaviour. It touches no file under ``src/segfacet/
features/**``, ``heuristics/**``, ``eval/**``, ``synth/**``, ``reference/**``,
and none of ``pipeline.py``, ``feature_report.py``, ``cli.py``,
``report_schema_v0.json`` (AC25). It is not the drift test (item 104 — this
module only exposes the two shared primitives, :func:`iter_leaf_paths` and
:func:`iter_driver_records`, that test needs) and not the golden-file decision
table (item 105).

Public API
----------
``CatalogueError``, ``FeatureDocMissing`` (subclass)
    Raised by :func:`build_catalogue` in strict mode.
``CatalogueEntry``, ``CatalogueGroup``, ``FeatureCatalogue``
    Frozen dataclasses making up the catalogue.
``normalise_leaf_path(path) -> str``
    Pure, idempotent leaf-path normaliser (schema granularity).
``iter_leaf_paths(record) -> set[str]``
    Walk a record to its normalised leaf-path set.
``iter_driver_records() -> Iterator[tuple[str, dict]]``
    The deterministic, in-package driver-record set.
``trace_record_access(record, callable) -> set[str]``
    Non-invasive dynamic-access tracer (mechanism A's primitive).
``build_catalogue(*, strict=True, reference=None) -> FeatureCatalogue``
    Assemble the full catalogue. ``reference`` (item 124) steers the
    observed-range reference population; see :mod:`segfacet.observed_range`.
``catalogue_to_dict(cat) -> dict``, ``render_markdown(cat) -> str``
    Deterministic serialisers.
``main(argv=None) -> int``
    ``python -m segfacet.catalogue [--json PATH] [--md PATH] [--reference PATH]``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import cycle
    from segfacet.observed_range import ObservedRange

__all__ = [
    "CatalogueError",
    "FeatureDocMissing",
    "CatalogueEntry",
    "CatalogueGroup",
    "FeatureCatalogue",
    "normalise_leaf_path",
    "iter_leaf_paths",
    "iter_driver_records",
    "trace_record_access",
    "build_catalogue",
    "catalogue_to_dict",
    "render_markdown",
    "scan_synth_rule_mode_map",
    "rule_declaration_conflicts",
    "main",
]

SCHEMA_VERSION = "1.1"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JSON_PATH = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_DEFAULT_MD_PATH = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

_CATALOGUE_NOTE = (
    "Generated by `python -m segfacet.catalogue` (item 103). Do not hand-edit "
    "this document -- edit `src/segfacet/feature_docs.py` (prose / owners / "
    "mode anchors / status overrides) and regenerate. `record[\"reference\"]` "
    "is deliberately excluded: the `bounds` and `fragmentation` rules read it, "
    "but it is a `ReferenceDistribution` object handle, not serialised feature "
    "data with a leaf path. Item 124's `observed` block reports each numeric "
    "path's observed range across two independent populations -- the "
    "in-package synthetic driver corpus (never flags a feature dead) and the "
    "committed real-GT reference distribution (the only population that can "
    "produce the `\"degenerate\"` verdict) -- but only the 21 of 99 numeric "
    "paths the reference vocabulary covers can ever read `\"degenerate\"`; "
    "the rest get their numbers reported and no verdict stronger than "
    "`\"constant-synthetic\"`."
)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class CatalogueError(Exception):
    """Base error for a catalogue that fails to build in strict mode."""


class FeatureDocMissing(CatalogueError):
    """A realised leaf path has no ``feature_docs.FEATURE_DOCS`` entry."""


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CatalogueEntry:
    """One catalogued feature: a normalised leaf path plus its provenance."""

    path: str
    group_title: str
    stage_label: str
    module: str
    measures: str
    computation: str
    units: str
    scale_sensitivity: str
    documented: bool
    origin: str
    consuming_rules: Tuple[str, ...]
    rule_evidence: Tuple[Tuple[str, str], ...]
    consumers: Tuple[str, ...]
    failure_modes: Tuple[int, ...]
    mode_evidence: Tuple[str, ...]
    status: str
    observed: "ObservedRange"


@dataclass(frozen=True)
class CatalogueGroup:
    """A ``BLOCK_OWNERS`` group: a title/stage/module plus its entries."""

    title: str
    stage_label: str
    module: str
    intro: str
    entries: Tuple[CatalogueEntry, ...]


@dataclass(frozen=True)
class FeatureCatalogue:
    """The whole generated catalogue: groups, plus a flattened entry list."""

    schema_version: str
    note: str
    groups: Tuple[CatalogueGroup, ...]
    entries: Tuple[CatalogueEntry, ...]


# =========================================================================== #
# Step 3: the normaliser and walker
# =========================================================================== #


def normalise_leaf_path(path: str) -> str:
    """Collapse *path* to its schema-granularity, normalised form.

    Idempotent: ``normalise_leaf_path(normalise_leaf_path(p)) ==
    normalise_leaf_path(p)`` for every input. Collapses (a) every list index to
    ``[]``, (b) an integer ``per_label`` key to ``{label}`` (both
    ``per_label.<int>`` and nested, e.g. ``image_features.per_label.<int>``),
    (c) an ``extended.<anything>`` key to ``extended.{radiomic}`` (an
    unbounded PyRadiomics-derived vocabulary), (d) a
    ``reference_delta.per_label.<int>`` key to ``reference_delta.{label}``.
    Values are never inspected -- only path segments are ever touched.
    """
    segments = path.split(".")

    # (c) extended.<anything> -> extended.{radiomic}: truncate at the first
    # "extended" segment, regardless of anything beyond it.
    if "extended" in segments:
        idx = segments.index("extended")
        segments = segments[: idx + 1] + ["{radiomic}"]

    # (d) reference_delta.per_label.<int> -> reference_delta.{label}
    collapsed: List[str] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        if (
            seg == "reference_delta"
            and i + 2 < len(segments)
            and segments[i + 1] == "per_label"
            and segments[i + 2].isdigit()
        ):
            collapsed.append("reference_delta")
            collapsed.append("{label}")
            i += 3
            continue
        collapsed.append(seg)
        i += 1
    segments = collapsed

    # (b) per_label.<int> -> per_label.{label} (any remaining occurrence).
    collapsed = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        if seg == "per_label" and i + 1 < len(segments) and segments[i + 1].isdigit():
            collapsed.append("per_label")
            collapsed.append("{label}")
            i += 2
            continue
        collapsed.append(seg)
        i += 1
    segments = collapsed

    # (a) any remaining bare-integer segment is a generic list index -> merge
    # into the preceding segment as "prev[]".
    collapsed = []
    for seg in segments:
        if seg.isdigit() and collapsed:
            collapsed[-1] = collapsed[-1] + "[]"
        else:
            collapsed.append(seg)
    segments = collapsed

    return ".".join(segments)


def _walk_leaf_paths(value: Any, path: str, sink: Set[str]) -> None:
    if isinstance(value, dict):
        if not value:
            if path:
                sink.add(path)
            return
        for key, sub in value.items():
            sub_path = f"{path}.{key}" if path else str(key)
            _walk_leaf_paths(sub, sub_path, sink)
        return

    if isinstance(value, list):
        if value and all(isinstance(el, dict) for el in value):
            container_path = f"{path}[]" if path else "[]"
            for el in value:
                _walk_leaf_paths(el, container_path, sink)
            return
        # Empty list, or a scalar (non-dict-element) list -> a single leaf.
        sink.add(f"{path}[]" if path else "[]")
        return

    # Scalar leaf (str / int / float / bool / None).
    if path:
        sink.add(path)


def iter_leaf_paths(record: Mapping[str, Any]) -> Set[str]:
    """Walk *record* to its set of normalised, schema-granularity leaf paths.

    A scalar list yields ``container[]``; a list of dicts recurses into each
    element under the shared ``container[]`` path; an empty dict or empty list
    still yields a leaf (never silently dropped). Pure -- never mutates
    *record*.
    """
    sink: Set[str] = set()
    _walk_leaf_paths(dict(record) if record else {}, "", sink)
    return {normalise_leaf_path(p) for p in sink}


def _last_segment(path: str) -> str:
    tail = path.rsplit(".", 1)[-1]
    return tail[:-2] if tail.endswith("[]") else tail


# =========================================================================== #
# Step 4: the driver-record set
# =========================================================================== #


def iter_driver_records() -> Iterator[Tuple[str, dict]]:
    """Yield ``(driver_id, record)`` pairs realising every catalogued block.

    Built **only** from :mod:`segfacet.synth` and :mod:`segfacet.pipeline`
    (this function's source names no path under the tests directory) so item
    104's drift test never needs a second, drifting copy of the driver set.
    Deterministic: two calls yield equal records. The union of the yielded
    records' leaf paths realises at least one non-empty ``overlaps`` element,
    one record with a ``stage3`` block, and one degenerate (0/1-label, hence
    no ``stage3``) record.
    """
    import numpy as np
    import nibabel as nib

    from segfacet.config import bundled_default_config
    from segfacet.feature_report import build_image_features_block
    from segfacet.features.intensity import LabelIntensity
    from segfacet.features.overlap import detect_overlaps
    from segfacet.pipeline import extract_feature_record
    from segfacet.reference.delta import (
        FeatureDelta,
        LabelDelta,
        ReferenceDelta,
        reference_delta_to_dict,
    )
    from segfacet.synth.clean_gt import build_clean_spine
    from segfacet.synth.perturbation import get_perturbation

    config = bundled_default_config()

    clean = build_clean_spine()
    clean_record = extract_feature_record(clean.seg_img, config)
    yield "clean", clean_record

    zero_data = np.zeros(clean.shape, dtype=np.uint16)
    zero_img = nib.Nifti1Image(zero_data, clean.seg_img.affine)
    yield "zero_label", extract_feature_record(zero_img, config)

    single = build_clean_spine(levels=("L3",))
    yield "single_label", extract_feature_record(single.seg_img, config)

    # A deliberate non-empty overlaps block: reuse the clean record's other
    # blocks verbatim, replacing only "overlaps" with a real
    # detect_overlaps() result over a two-channel stack sharing every voxel
    # of the first label (the technique synth/regression.py's
    # _recon_overlap_mask_stack uses, built here instead of reaching outside
    # this package).
    data = np.asanyarray(clean.seg_img.dataobj)
    label_a, label_b = clean.labels[0], clean.labels[1]
    mask_a = data == label_a
    stack = np.stack([mask_a, np.array(mask_a, copy=True)], axis=0)
    overlap_pairs = detect_overlaps(stack, np.array([label_a, label_b]))
    overlaps_record = dict(clean_record)
    overlaps_record["overlaps"] = [
        {
            "label_a": p.label_a,
            "label_b": p.label_b,
            "name_a": p.name_a,
            "name_b": p.name_b,
            "overlap_voxels": p.overlap_voxels,
        }
        for p in overlap_pairs
    ]
    yield "overlaps", overlaps_record

    fragment_cls = get_perturbation("fragment")
    fragmented_img, _ = fragment_cls().apply(clean.seg_img, seed=0)
    yield "fragmented", extract_feature_record(fragmented_img, config)

    remove_level_cls = get_perturbation("remove_level")
    missing_img, _ = remove_level_cls().apply(clean.seg_img, seed=0)
    yield "missing_level", extract_feature_record(missing_img, config)

    sequence_break_cls = get_perturbation("sequence_break")
    seqbreak_img, _ = sequence_break_cls().apply(clean.seg_img, seed=0)
    yield "sequence_break", extract_feature_record(seqbreak_img, config)

    # Two augmented drivers, realised through the existing converters over
    # hand-constructed placeholder dataclass instances -- no PyRadiomics, no
    # reference artifact, no scan, fully deterministic (item 103 Assumptions
    # "Two tiers").
    placeholder_intensity = LabelIntensity(
        voxel_count=100,
        n_nonfinite_excluded=0,
        mean=500.0,
        median=480.0,
        std=50.0,
        min=100.0,
        max=900.0,
        p05=200.0,
        p25=400.0,
        p50=480.0,
        p75=600.0,
        p95=800.0,
        range=800.0,
        iqr=200.0,
        entropy=3.5,
    )
    image_features_block = build_image_features_block(
        intensity={label_a: placeholder_intensity},
        extended={label_a: {"original_firstorder_Mean": 480.0}},
        backend="builtin",
        radiomics_available=False,
    )
    yield "image_features", {"image_features": image_features_block}

    placeholder_feature_delta = FeatureDelta(
        feature="physical_volume_mm3",
        value=18750.0,
        z_score=0.1,
        robust_z=0.2,
        percentile_rank=55.0,
        out_of_range=False,
    )
    placeholder_label_delta = LabelDelta(
        label=label_a,
        level_name="L1",
        stratum="all",
        available=True,
        features=(placeholder_feature_delta,),
        distribution_distance=0.2,
        out_of_range_features=(),
    )
    placeholder_reference_delta = ReferenceDelta(
        reference_delta_version="1.0",
        reference_schema_version="1.0",
        reference_source="synthetic-placeholder",
        stratum="all",
        lower_pct=1,
        upper_pct=99,
        per_label={label_a: placeholder_label_delta},
    )
    yield "reference_delta", {
        "reference_delta": reference_delta_to_dict(placeholder_reference_delta)
    }


# =========================================================================== #
# Step 5: the trace proxy (mechanism A)
# =========================================================================== #


class _TracedDict(dict):
    """A ``dict`` subclass that records every leaf path actually read.

    Retrieving a nested dict or a list-of-dicts returns a further-wrapped
    proxy and records nothing; retrieving a scalar records its normalised
    path; retrieving any other list (empty, or of non-dict elements) records
    ``path[]``. Never writes back into the wrapped mapping.
    """

    def __init__(self, data: Mapping[str, Any], path: str, sink: Set[str]):
        super().__init__(data)
        self._path = path
        self._sink = sink

    def _child_path(self, key: Any) -> str:
        return f"{self._path}.{key}" if self._path else str(key)

    def _wrap(self, key: Any, value: Any) -> Any:
        child_path = self._child_path(key)
        if isinstance(value, dict):
            return _TracedDict(value, child_path, self._sink)
        if isinstance(value, list):
            if value and all(isinstance(el, dict) for el in value):
                return _TracedList(value, f"{child_path}[]", self._sink)
            self._sink.add(normalise_leaf_path(f"{child_path}[]"))
            return value
        self._sink.add(normalise_leaf_path(child_path))
        return value

    def __getitem__(self, key: Any) -> Any:
        value = dict.__getitem__(self, key)
        return self._wrap(key, value)

    def get(self, key: Any, default: Any = None) -> Any:
        if not dict.__contains__(self, key):
            return default
        return self[key]

    def items(self):
        return [(k, self[k]) for k in dict.keys(self)]

    def values(self):
        return [self[k] for k in dict.keys(self)]


class _TracedList(list):
    """A ``list`` subclass wrapping a list-of-dicts under one shared path."""

    def __init__(self, data: Sequence[Any], path: str, sink: Set[str]):
        super().__init__(data)
        self._path = path
        self._sink = sink

    def _wrap(self, item: Any) -> Any:
        if isinstance(item, dict):
            return _TracedDict(item, self._path, self._sink)
        return item

    def __iter__(self):
        for item in list.__iter__(self):
            yield self._wrap(item)

    def __getitem__(self, index):
        item = list.__getitem__(self, index)
        if isinstance(index, slice):
            return [self._wrap(el) for el in item]
        return self._wrap(item)


def trace_record_access(record: Mapping[str, Any], fn) -> Set[str]:
    """Call ``fn(traced_record)`` and return the set of leaf paths it read.

    *record* is never mutated -- ``_TracedDict``/``_TracedList`` always
    construct fresh wrapper objects around shallow-copied contents.
    """
    sink: Set[str] = set()
    traced = _TracedDict(record, "", sink)
    fn(traced)
    return sink


# =========================================================================== #
# Step 6: the static scanners (mechanisms B and C)
# =========================================================================== #


def _scan_literal_string_keys(source: str) -> Set[str]:
    """String constants used as a ``Subscript`` slice or as ``.get(...)``'s
    first positional argument, anywhere in *source*."""
    import ast

    tree = ast.parse(source)
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            slice_node = node.slice
            if slice_node.__class__.__name__ == "Index":  # pragma: no cover - py3.8
                slice_node = slice_node.value  # type: ignore[attr-defined]
            if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                found.add(slice_node.value)
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.add(node.args[0].value)
    return found


def _rule_module_literal_keys(rule) -> Set[str]:
    import sys

    module = sys.modules[type(rule).__module__]
    source = Path(module.__file__).read_text(encoding="utf-8")
    return _scan_literal_string_keys(source)


def _extract_frozenset_string_elements(node) -> List[str]:
    import ast

    if not isinstance(node, ast.Call):
        return []
    func = node.func
    if not (isinstance(func, ast.Name) and func.id == "frozenset"):
        return []
    if not node.args:
        return []
    set_node = node.args[0]
    elts = getattr(set_node, "elts", None)
    if elts is None:
        return []
    return [
        elt.value for elt in elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    ]


def _scan_synth_rule_mode_map() -> Dict[str, Tuple[int, ...]]:
    """``rule_id -> §6 mode(s)``, read from every ``Expectation(...)`` call's
    literal ``failure_mode=``/``expected_rule_ids=`` keyword pair across
    ``src/segfacet/synth/*.py``. No rule-id -> mode mapping is hand-typed
    anywhere in this module's source (AC13's drift guard)."""
    import ast
    import segfacet.synth as synth_pkg

    synth_dir = Path(synth_pkg.__file__).resolve().parent

    accum: Dict[str, Set[int]] = defaultdict(set)
    for path in sorted(synth_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "Expectation":
                continue
            mode: Optional[int] = None
            rule_ids: List[str] = []
            for kw in node.keywords:
                if kw.arg == "failure_mode" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, int):
                        mode = kw.value.value
                elif kw.arg == "expected_rule_ids":
                    rule_ids = _extract_frozenset_string_elements(kw.value)
            if mode is None or not rule_ids:
                continue
            for rule_id in rule_ids:
                accum[rule_id].add(mode)

    return {rule_id: tuple(sorted(modes)) for rule_id, modes in accum.items()}


def scan_synth_rule_mode_map() -> Dict[str, Tuple[int, ...]]:
    """Public name for :func:`_scan_synth_rule_mode_map` (item 136).

    ``rule_id -> §6 mode(s)``, read from every ``Expectation(...)`` call's
    literal ``failure_mode=``/``expected_rule_ids=`` keyword pair across
    ``src/segfacet/synth/*.py`` -- the corpus-derived side of the
    declaration <-> corpus agreement checked by
    :func:`rule_declaration_conflicts`.
    """
    return _scan_synth_rule_mode_map()


# =========================================================================== #
# Step 7: mechanism D -- non-rule consumers
# =========================================================================== #


def _mechanism_d_consumers(
    driver_records: Sequence[Tuple[str, dict]], path_aliases: Mapping[str, str], leaf_union: Set[str]
) -> Dict[str, Set[str]]:
    from segfacet.eval.feature_match import TRACKED_FEATURES
    from segfacet.eval.per_mode import compute_per_mode_metrics
    from segfacet.human_report import render_feature_table
    from segfacet.reference.delta import MORPHOLOGY_FEATURES
    from segfacet.reference.ingest import INGESTED_FEATURES

    consumers: Dict[str, Set[str]] = defaultdict(set)

    for _driver_id, record in driver_records:
        for callable_name, fn in (
            ("compute_per_mode_metrics", lambda traced: compute_per_mode_metrics(traced)),
            ("render_feature_table", lambda traced: render_feature_table(traced)),
        ):
            try:
                sink = trace_record_access(record, fn)
            except Exception:
                continue
            for path in sink:
                consumers[path].add(callable_name)

    by_last_segment: Dict[str, List[str]] = defaultdict(list)
    for path in leaf_union:
        by_last_segment[_last_segment(path)].append(path)

    vocab_names = set(MORPHOLOGY_FEATURES) | set(INGESTED_FEATURES) | set(TRACKED_FEATURES)
    for name in vocab_names:
        target_paths: List[str]
        alias_path = path_aliases.get(name)
        if alias_path is not None and alias_path in leaf_union:
            target_paths = [alias_path]
        else:
            target_paths = by_last_segment.get(name, [])
        for path in target_paths:
            consumers[path].add("vocabulary")

    return consumers


# =========================================================================== #
# Step 8: build_catalogue
# =========================================================================== #


def _group_for_path(path: str, block_owners: Sequence[Tuple[str, str, str, str]]) -> Tuple[str, str, str]:
    """Longest-prefix match of *path* against ``BLOCK_OWNERS`` rows."""
    best: Optional[Tuple[str, str, str, str]] = None
    for row in block_owners:
        prefix = row[0]
        if prefix == "" or path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "["):
            if best is None or len(prefix) > len(best[0]):
                best = row
    if best is None:
        return ("Uncategorised", "", "")
    return (best[1], best[2], best[3])


def build_catalogue(*, strict: bool = True, reference: Any = None) -> FeatureCatalogue:
    """Assemble the full :class:`FeatureCatalogue` (AC6-AC17).

    Never mutates any input. Two calls return equal catalogues.

    Parameters
    ----------
    reference:
        The reference population for item 124's ``observed`` block: ``None``
        (the bundled production reference), a ``ReferenceDistribution``
        instance, or a path to a reference artifact on disk. A missing or
        unparseable artifact degrades every entry's ``observed.reference`` to
        ``covered=False`` rather than raising.

    Raises
    ------
    FeatureDocMissing
        In strict mode, if a realised leaf path has no
        ``feature_docs.FEATURE_DOCS`` entry.
    CatalogueError
        In strict mode, if a ``feature_docs.FEATURE_DOCS`` key matches no
        realised leaf path.
    """
    from segfacet import feature_docs as _feature_docs_module
    from segfacet.config import bundled_default_config
    from segfacet.heuristics.rule import iter_rule_declarations, iter_rules
    from segfacet.observed_range import build_observed_ranges

    config = bundled_default_config()

    driver_records = list(iter_driver_records())
    observed_ranges = build_observed_ranges(driver_records=driver_records, reference=reference)

    leaf_union: Set[str] = set()
    for _driver_id, record in driver_records:
        leaf_union |= iter_leaf_paths(record)

    # Mechanism A: dynamic access trace.
    attributions: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    rules = list(iter_rules())
    for _driver_id, record in driver_records:
        for rule in rules:
            def _runner(traced, _rule=rule):
                try:
                    _rule.evaluate(traced, config)
                except Exception:
                    pass
                return None

            sink = trace_record_access(record, _runner)
            for path in sink:
                attributions[path][rule.rule_id].add("observed")

    # Mechanism B: static AST scan of each rule's own module file.
    by_last_segment: Dict[str, List[str]] = defaultdict(list)
    for path in leaf_union:
        by_last_segment[_last_segment(path)].append(path)

    for rule in rules:
        try:
            literal_keys = _rule_module_literal_keys(rule)
        except Exception:
            # A rule registered from a module with no readable source (e.g.
            # a rule class defined ad hoc in a test/adversarial context) --
            # mechanism B simply contributes nothing for it, never aborting
            # the build.
            continue
        for name in literal_keys:
            candidates = by_last_segment.get(name)
            if not candidates:
                continue
            if len(candidates) > 1:
                # Item 110 (AC11b): a name shared by >1 leaf path's last
                # segment (e.g. "label", "level_name", "mean", "median",
                # "std") is exactly the case this scan cannot disambiguate --
                # it has no notion of *which* block the literal key was read
                # from, only that the bare string appears somewhere in the
                # rule's module. Silently guessing "keep" for every candidate
                # (the pre-fix behaviour, tagged "static-ambiguous") produced
                # false positives whenever an unrelated block happened to
                # reuse a generic key name. Contribute no mechanism-B
                # evidence for an ambiguous name at all; an unambiguous
                # last-segment match (below) or another mechanism (A/D) still
                # attributes it correctly.
                continue
            for path in candidates:
                attributions[path][rule.rule_id].add("static")

    # Mechanism C: rule_id -> §6 mode(s), from synth/*.py's Expectation(...).
    rule_mode_map = _scan_synth_rule_mode_map()

    # Declaration source (item 136): rule_id -> declared §6 mode(s), read
    # from each rule's own class-attribute RuleModeDeclaration.
    declared_modes_by_rule: Dict[str, Tuple[int, ...]] = {
        rule_id: decl.modes
        for rule_id, decl in iter_rule_declarations()
        if decl is not None and decl.modes
    }

    # Mechanism D: non-rule consumers.
    consumers_map = _mechanism_d_consumers(
        driver_records, _feature_docs_module.PATH_ALIASES, leaf_union
    )

    feature_docs = _feature_docs_module.FEATURE_DOCS
    mode_anchor_paths = _feature_docs_module.MODE_ANCHOR_PATHS
    status_overrides = _feature_docs_module.STATUS_OVERRIDES
    block_owners = _feature_docs_module.BLOCK_OWNERS
    group_intros = _feature_docs_module.GROUP_INTROS

    anchor_modes_by_path: Dict[str, Set[int]] = defaultdict(set)
    for mode, paths in mode_anchor_paths.items():
        for path in paths:
            anchor_modes_by_path[path].add(mode)

    if strict:
        undocumented = sorted(p for p in leaf_union if p not in feature_docs)
        if undocumented:
            raise FeatureDocMissing(
                "build_catalogue(strict=True): the following realised leaf "
                f"path(s) have no segfacet.feature_docs.FEATURE_DOCS entry: "
                f"{undocumented!r}."
            )
        stale = sorted(k for k in feature_docs if k not in leaf_union)
        if stale:
            raise CatalogueError(
                "build_catalogue(strict=True): the following "
                f"segfacet.feature_docs.FEATURE_DOCS key(s) match no realised "
                f"leaf path: {stale!r}."
            )

    entries_by_group: Dict[Tuple[str, str, str], List[CatalogueEntry]] = defaultdict(list)
    group_order: List[Tuple[str, str, str]] = []

    for path in sorted(leaf_union):
        doc = feature_docs.get(path)
        documented = doc is not None
        measures = doc.measures if doc is not None else ""
        computation = doc.computation if doc is not None else ""
        units = doc.units if doc is not None else ""
        scale_sensitivity = doc.scale_sensitivity if doc is not None else ""

        rule_ids = tuple(sorted(attributions.get(path, {}).keys()))
        rule_evidence = tuple(
            (rule_id, evidence)
            for rule_id in rule_ids
            for evidence in sorted(attributions[path][rule_id])
        )
        consumers = tuple(sorted(consumers_map.get(path, set())))

        anchor_modes = anchor_modes_by_path.get(path, set())
        mapped_rule_modes: Set[int] = set()
        declared_rule_modes: Set[int] = set()
        had_unmapped_rule = False
        for rule_id in rule_ids:
            modes_for_rule = rule_mode_map.get(rule_id)
            declared_for_rule = declared_modes_by_rule.get(rule_id)
            if modes_for_rule:
                mapped_rule_modes.update(modes_for_rule)
            if declared_for_rule:
                declared_rule_modes.update(declared_for_rule)
            if not modes_for_rule and not declared_for_rule:
                had_unmapped_rule = True

        all_modes = anchor_modes | mapped_rule_modes | declared_rule_modes
        mode_evidence_parts: List[str] = []
        if anchor_modes:
            mode_evidence_parts.append("per_mode_metric")
        if mapped_rule_modes:
            mode_evidence_parts.append("rule_mode_map")
        if declared_rule_modes:
            mode_evidence_parts.append("rule_declaration")

        if all_modes:
            failure_modes = tuple(sorted(all_modes))
            mode_evidence = tuple(mode_evidence_parts)
        elif rule_ids and had_unmapped_rule:
            failure_modes = ()
            mode_evidence = ("rule_unmapped",)
        else:
            failure_modes = ()
            mode_evidence = ()

        override = status_overrides.get(path)
        if override is not None:
            status = override[0]
        elif rule_ids or consumers:
            status = "keep"
        else:
            status = "unwired"

        group_title, stage_label, module = _group_for_path(path, block_owners)
        group_key = (group_title, stage_label, module)
        if group_key not in entries_by_group:
            group_order.append(group_key)

        entries_by_group[group_key].append(
            CatalogueEntry(
                path=path,
                group_title=group_title,
                stage_label=stage_label,
                module=module,
                measures=measures,
                computation=computation,
                units=units,
                scale_sensitivity=scale_sensitivity,
                documented=documented,
                origin="record",
                consuming_rules=rule_ids,
                rule_evidence=rule_evidence,
                consumers=consumers,
                failure_modes=failure_modes,
                mode_evidence=mode_evidence,
                status=status,
                observed=observed_ranges[path],
            )
        )

    # Groups in BLOCK_OWNERS order (falling back to first-seen order for any
    # path that matched no row -- "Uncategorised", never dropped).
    owner_order = [(row[1], row[2], row[3]) for row in block_owners]
    ordered_group_keys: List[Tuple[str, str, str]] = []
    for k in owner_order:
        if k in entries_by_group and k not in ordered_group_keys:
            ordered_group_keys.append(k)
    for k in group_order:
        if k not in ordered_group_keys:
            ordered_group_keys.append(k)

    groups: List[CatalogueGroup] = []
    all_entries: List[CatalogueEntry] = []
    for group_key in ordered_group_keys:
        title, stage_label, module = group_key
        entries = tuple(sorted(entries_by_group[group_key], key=lambda e: e.path))
        groups.append(
            CatalogueGroup(
                title=title,
                stage_label=stage_label,
                module=module,
                intro=group_intros.get(title, ""),
                entries=entries,
            )
        )
        all_entries.extend(entries)

    return FeatureCatalogue(
        schema_version=SCHEMA_VERSION,
        note=_CATALOGUE_NOTE,
        groups=tuple(groups),
        entries=tuple(all_entries),
    )


# =========================================================================== #
# Step 8b: rule <-> mode declaration/corpus agreement checker (item 136)
# =========================================================================== #


def rule_declaration_conflicts() -> Tuple[str, ...]:
    """Report every disagreement between each rule's ``RuleModeDeclaration``
    and the corpus-derived ``rule_id -> §6 mode(s)`` map (item 136).

    Returns a sorted tuple of human-readable messages, empty when the two
    sources agree. Reports, for the shipped registry:

    - a registered rule with no declaration at all (naming its ``rule_id``);
    - a corpus-designated ``(rule_id, mode)`` pair the rule's declaration does
      not carry in ``modes`` (naming both);
    - a ``"corpus"``-tagged declaration carrying a mode no committed corpus
      case designates for that rule (naming both);
    - a declared mode outside :data:`segfacet.feature_docs.MODE_ANCHOR_PATHS`'s
      key set -- the in-code §6 mode catalogue (A5) -- (naming both).

    Pure: never mutates the registry, never raises for a missing declaration
    (A3 -- absence is reported, not rejected).
    """
    from segfacet import feature_docs as _feature_docs_module
    from segfacet.heuristics.rule import iter_rule_declarations

    known_modes = set(_feature_docs_module.MODE_ANCHOR_PATHS.keys())
    corpus_map = _scan_synth_rule_mode_map()

    messages: List[str] = []
    for rule_id, decl in iter_rule_declarations():
        if decl is None:
            messages.append(
                f"rule {rule_id!r} has no RuleModeDeclaration (mode_declaration is None)."
            )
            continue

        corpus_modes = set(corpus_map.get(rule_id, ()))
        declared_modes = set(decl.modes)

        for mode in sorted(corpus_modes - declared_modes):
            messages.append(
                f"rule {rule_id!r}: corpus designates §6 mode {mode} but the "
                f"declaration does not include it (declared modes: {sorted(declared_modes)!r})."
            )

        if "corpus" in decl.evidence:
            for mode in sorted(declared_modes - corpus_modes):
                messages.append(
                    f"rule {rule_id!r}: declaration claims §6 mode {mode} tagged "
                    f"'corpus' but no committed corpus case designates it "
                    f"(corpus modes: {sorted(corpus_modes)!r})."
                )

        for mode in sorted(declared_modes - known_modes):
            messages.append(
                f"rule {rule_id!r}: declared §6 mode {mode} is outside "
                f"MODE_ANCHOR_PATHS's key set {sorted(known_modes)!r}."
            )

    return tuple(sorted(messages))


# =========================================================================== #
# Step 9: serialisation
# =========================================================================== #


def _quantise(v: Optional[float]) -> Optional[float]:
    """Six-significant-digit quantisation (AC15): the value it would
    round-trip to at six significant digits. ``None`` passes through
    unchanged (AC4's null, never ``0``)."""
    return None if v is None else float(f"{v:.6g}")


def _population_range_to_dict(pop: Any) -> dict:
    # emission_range clamps a covered-but-not-informative population's
    # numeric fields to 0.0 (item 124 post-merge fix, 2026-08-30): a
    # sub-floor measurement is numerical noise whose exact bits are
    # platform-dependent, and this document is compared byte-exactly. See
    # segfacet.observed_range's module docstring, "Sub-floor noise is
    # clamped to 0.0 at emission". Classification already happened on the
    # raw, unclamped value (build_observed_ranges._derive_verdict) -- this
    # clamp only affects what gets written here.
    from segfacet.observed_range import emission_range

    minimum, maximum, span, magnitude = emission_range(pop)
    return {
        "population": pop.population,
        "source": list(pop.source),
        "covered": pop.covered,
        "count": pop.count,
        "minimum": _quantise(minimum),
        "maximum": _quantise(maximum),
        "span": _quantise(span),
        "magnitude": _quantise(magnitude),
        "informative": pop.informative,
    }


def _observed_range_to_dict(observed: Any) -> dict:
    return {
        "numeric": observed.numeric,
        "verdict": observed.verdict,
        "corpus": _population_range_to_dict(observed.corpus),
        "reference": _population_range_to_dict(observed.reference),
    }


_VERDICT_VOCABULARY = (
    "varies",
    "degenerate",
    "constant-synthetic",
    "placeholder",
    "non-numeric",
    "unobserved",
)


def catalogue_to_dict(cat: FeatureCatalogue) -> dict:
    """A deterministic, JSON-ready dict for *cat*. No timestamp, hostname,
    absolute path, or dependency-version string."""
    observed_summary = {verdict: 0 for verdict in _VERDICT_VOCABULARY}
    for entry in cat.entries:
        observed_summary[entry.observed.verdict] += 1

    return {
        "schema_version": cat.schema_version,
        "note": cat.note,
        "observed_summary": observed_summary,
        "groups": [
            {
                "title": g.title,
                "stage": g.stage_label,
                "module": g.module,
                "intro": g.intro,
                "entries": [
                    {
                        "path": e.path,
                        "measures": e.measures,
                        "computation": e.computation,
                        "units": e.units,
                        "scale_sensitivity": e.scale_sensitivity,
                        "documented": e.documented,
                        "origin": e.origin,
                        "consuming_rules": list(e.consuming_rules),
                        "rule_evidence": [list(pair) for pair in e.rule_evidence],
                        "consumers": list(e.consumers),
                        "failure_modes": list(e.failure_modes),
                        "mode_evidence": list(e.mode_evidence),
                        "status": e.status,
                        "observed": _observed_range_to_dict(e.observed),
                    }
                    for e in g.entries
                ],
            }
            for g in cat.groups
        ],
    }


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _fmt_population(pop: Any) -> str:
    # See _population_range_to_dict: emission_range clamps sub-floor noise
    # to 0.0 so the Markdown table's "observed range" cell agrees with the
    # JSON's clamped values instead of embedding platform-dependent noise
    # digits into a byte-compared document.
    from segfacet.observed_range import emission_range

    minimum, maximum, _span, _magnitude = emission_range(pop)
    if minimum is None:
        return "\u2014"
    minimum = _quantise(minimum)
    maximum = _quantise(maximum)
    return f"{minimum:.6g}\u2013{maximum:.6g}"


def _fmt_observed_range(observed: Any) -> str:
    return f"corpus {_fmt_population(observed.corpus)} \u00b7 ref {_fmt_population(observed.reference)}"


def render_markdown(cat: FeatureCatalogue) -> str:
    """Render *cat* as a single Markdown table, one row per entry, in the
    catalogue's own deterministic order."""
    lines = [
        f"# Feature & Rule Catalogue ({len(cat.entries)} entries)",
        "",
        _md_escape(cat.note),
        "",
        "| path | module / item | measures | computation | units | "
        "scale sensitivity | observed range | observed verdict | "
        "\u00a76 mode(s) | consuming rules | status |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for e in cat.entries:
        module_item = f"{e.stage_label} \u00b7 {e.module}" if e.stage_label else e.module
        modes = ", ".join(str(m) for m in e.failure_modes)
        rules = ", ".join(e.consuming_rules)
        cells = [
            e.path,
            _md_escape(module_item),
            _md_escape(e.measures),
            _md_escape(e.computation),
            _md_escape(e.units),
            _md_escape(e.scale_sensitivity),
            _md_escape(_fmt_observed_range(e.observed)),
            e.observed.verdict,
            modes,
            rules,
            e.status,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# =========================================================================== #
# __main__
# =========================================================================== #


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Regenerate the generated feature & rule catalogue (item 103)."
    )
    parser.add_argument("--json", type=Path, default=_DEFAULT_JSON_PATH)
    parser.add_argument("--md", type=Path, default=_DEFAULT_MD_PATH)
    parser.add_argument(
        "--reference",
        type=Path,
        default=None,
        help=(
            "Path to a reference-distribution artifact to build the "
            "observed-range reference population from (item 124). Defaults "
            "to the bundled production reference."
        ),
    )
    args = parser.parse_args(argv)

    cat = build_catalogue(strict=True, reference=args.reference)

    json_text = json.dumps(catalogue_to_dict(cat), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    md_text = render_markdown(cat)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_bytes(json_text.encode("utf-8"))
    args.md.write_bytes(md_text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
