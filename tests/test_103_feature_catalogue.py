"""Tests for item 103 -- generated feature & rule catalogue
(``segfacet.catalogue`` + ``segfacet.feature_docs``), plus the status report's
switch from the hand-typed ``FEATURE_CATALOG`` literal to loading the
generated JSON (``scripts/aide_status_report.py``).

Covers Acceptance Criteria AC1-AC25:

- AC1:  ``segfacet.catalogue``'s public surface (``__all__``: ``CatalogueError``,
        ``FeatureDocMissing``, ``CatalogueEntry``, ``CatalogueGroup``,
        ``FeatureCatalogue``, ``normalise_leaf_path``, ``iter_leaf_paths``,
        ``iter_driver_records``, ``build_catalogue``, ``catalogue_to_dict``,
        ``render_markdown``); the three dataclasses are frozen.
- AC2:  ``segfacet.feature_docs`` is pure stdlib data (``FeatureDoc``,
        ``FEATURE_DOCS``, ``BLOCK_OWNERS``, ``PATH_ALIASES``,
        ``MODE_ANCHOR_PATHS``, ``STATUS_OVERRIDES``); its imports are stdlib
        only (AST-scanned), no ``segfacet``.
- AC3:  ``normalise_leaf_path`` collapses list indices / ``per_label.<int>`` /
        ``extended.<anything>`` / ``reference_delta.per_label.<int>``, is
        idempotent, and never returns a bare-integer segment.
- AC4:  ``iter_leaf_paths`` on ``clean_control``'s realised record yields the
        five named canonical paths, no bare-integer segment, and exactly 67
        members.
- AC5:  ``iter_driver_records`` is in-package (no ``tests/`` literal),
        deterministic, and its union realises a non-empty ``overlaps``, a
        ``stage3`` block, and a degenerate (no-``stage3``) record.
- AC6:  coverage is exact and duplicate-free both directions against the
        driver-record union ``U``.
- AC7:  every entry's ``status`` is one of the fixed vocabulary.
- AC8:  ``status == "unwired"`` iff no consuming rule and no other consumer
        and no override.
- AC9:  the non-invasiveness triple: trace proxy is a ``dict`` subclass, a
        deep-copied snapshot survives tracing, and ``run_rules`` agrees
        traced vs. plain across all nine corpus records.
- AC10: dynamic attribution reproduces the measured rule<->feature reads for
        six named paths.
- AC11: ``overlaps[].overlap_voxels`` carries ``"overlap"`` regardless of
        evidence tag.
- AC12: every rule attribution carries a valid evidence tag; the
        ``rule_evidence`` rule-id set equals ``consuming_rules``.
- AC13: the rule->mode map is derived from ``synth/`` (checked via its
        effect on ``failure_modes``) and ``catalogue.py``'s source contains
        no hand-typed rule-id->mode dict literal.
- AC14: every ``MODE_ANCHOR_PATHS`` path anchors modes 1-8 with
        ``"per_mode_metric"`` evidence.
- AC15: an unmapped-rule-only, non-anchor entry gets an honest empty mode
        list with ``mode_evidence == ("rule_unmapped",)`` -- reconciled for
        item 137, whose disposition of the four rules this test originally
        exercised (``bounds``, ``intensity``, ``reference_delta``,
        ``intensity_reference_delta``) leaves none of them unmapped; see the
        reconciled test's own docstring.
- AC16: an undocumented realised path raises ``FeatureDocMissing`` (strict)
        naming the path, and degrades to ``documented=False`` (non-strict).
- AC17: a stale ``FEATURE_DOCS`` key raises ``CatalogueError`` naming it; on
        the committed tree ``FEATURE_DOCS``'s keys equal ``U`` exactly.
- AC18: serialisation is deterministic, byte-reproducible, and carries no
        timestamp/hostname/absolute path/dependency-version string.
- AC19: regenerating from the tree reproduces the two committed generated
        documents byte-identically, and two same-session regenerations agree.
- AC20: ``.gitattributes`` LF-pins both generated documents.
- AC21: the status-report script no longer defines ``FEATURE_CATALOG`` /
        ``UNWIRED_EXTRACTORS``, defines ``load_feature_catalog``, and its
        stdlib-only import contract holds.
- AC22: the rendered feature section keeps its markup shape (``<section
        id="features"``, one ``.feature-group`` per group, etc.).
- AC23: a missing/corrupt catalogue JSON degrades to an empty tuple and a
        placeholder section; ``render_html`` never raises.
- AC24: ``render_markdown`` emits exactly the nine queue-mandated columns,
        one row per entry, in the catalogue's own order.
- AC25: the scope fence holds -- the untouched files/packages are
        byte-identical to their pre-103 state.

Adversarial / edge-case scenarios included: ``iter_leaf_paths({})``; a 0-label
record's ``relationships is None``; a deeply-nested empty dict beside an empty
list; a level-name *value* that looks like an integer (never normalised); a
rule that raises mid-trace (build continues); an ambiguous static name
resolving to >1 path (``static-ambiguous`` on every candidate); idempotence of
``build_catalogue()`` across two calls with no input mutation; the
status-report loader given a missing file, a directory, truncated JSON, and an
unknown schema version.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator

from segfacet.config import bundled_default_config
from segfacet.heuristics.rule import Rule, _RULES, iter_rules
from segfacet.heuristics.runner import run_rules
from segfacet.pipeline import extract_feature_record
from segfacet.synth.corpus import load_manifest
from segfacet.synth.regression import loaded_seg_image

try:
    stdlib_module_names = sys.stdlib_module_names  # Python >= 3.10
except AttributeError:  # pragma: no cover - only on Python 3.9
    stdlib_module_names = None

_KNOWN_THIRD_PARTY = {"numpy", "scipy", "nibabel", "radiomics", "cupy", "pytest"}


def _catalogue():
    """Local import of ``segfacet.catalogue`` (kept out of the module-level
    import block, mirroring ``tests/test_099_per_mode_metrics.py``'s
    ``_per_mode()`` convention) so this file still collects before item 103's
    builder step lands the module."""
    import segfacet.catalogue as catalogue

    return catalogue


def _feature_docs():
    import segfacet.feature_docs as feature_docs

    return feature_docs


# =========================================================================== #
# Shared fixtures (Testing Strategy: module-scoped, built once)
# =========================================================================== #

_REPO_ROOT = Path(__file__).resolve().parents[1]

_MANIFEST = load_manifest()
_CASES = {c["case_id"]: c for c in _MANIFEST["cases"]}
_CASE_IDS = sorted(_CASES)
_CONFIG = bundled_default_config()
_CORPUS_RECORDS = {
    cid: extract_feature_record(loaded_seg_image(case), _CONFIG)
    for cid, case in _CASES.items()
}


@pytest.fixture(scope="module")
def catalogue_module():
    return _catalogue()


@pytest.fixture(scope="module")
def feature_docs_module():
    return _feature_docs()


@pytest.fixture(scope="module")
def driver_records(catalogue_module):
    return dict(catalogue_module.iter_driver_records())


@pytest.fixture(scope="module")
def leaf_union(catalogue_module, driver_records):
    union = set()
    for record in driver_records.values():
        union |= catalogue_module.iter_leaf_paths(record)
    return union


@pytest.fixture(scope="module")
def full_catalogue(catalogue_module):
    return catalogue_module.build_catalogue()


def _entry(cat, path):
    for entry in cat.entries:
        if entry.path == path:
            return entry
    raise AssertionError(f"no catalogue entry for path {path!r}")


# =========================================================================== #
# AC1: the generator module and its public surface exist
# =========================================================================== #


def test_ac1_public_surface_exported(catalogue_module):
    expected = {
        "CatalogueError",
        "FeatureDocMissing",
        "CatalogueEntry",
        "CatalogueGroup",
        "FeatureCatalogue",
        "normalise_leaf_path",
        "iter_leaf_paths",
        "iter_driver_records",
        "build_catalogue",
        "catalogue_to_dict",
        "render_markdown",
    }
    assert expected.issubset(set(catalogue_module.__all__))
    for name in expected:
        assert hasattr(catalogue_module, name), name


def test_ac1_feature_doc_missing_is_catalogue_error_subclass(catalogue_module):
    assert issubclass(catalogue_module.FeatureDocMissing, catalogue_module.CatalogueError)
    assert issubclass(catalogue_module.CatalogueError, Exception)


@pytest.mark.parametrize(
    "name", ["CatalogueEntry", "CatalogueGroup", "FeatureCatalogue"]
)
def test_ac1_dataclasses_are_frozen(catalogue_module, name):
    cls = getattr(catalogue_module, name)
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


# =========================================================================== #
# AC2: the authored-data module exists and is pure data
# =========================================================================== #


def test_ac2_feature_docs_public_surface(feature_docs_module):
    for name in (
        "FeatureDoc",
        "FEATURE_DOCS",
        "BLOCK_OWNERS",
        "PATH_ALIASES",
        "MODE_ANCHOR_PATHS",
        "STATUS_OVERRIDES",
    ):
        assert hasattr(feature_docs_module, name), name
    assert name in dir(feature_docs_module)


def test_ac2_feature_doc_is_frozen_dataclass_with_four_fields(feature_docs_module):
    cls = feature_docs_module.FeatureDoc
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True
    field_names = {f.name for f in dataclasses.fields(cls)}
    assert field_names == {"measures", "computation", "units", "scale_sensitivity"}


def test_ac2_feature_docs_module_imports_nothing_non_stdlib(feature_docs_module):
    source = Path(feature_docs_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                top_level_names.add(node.module.split(".")[0])

    assert "segfacet" not in top_level_names
    for name in top_level_names:
        if name == "__future__":
            continue
        if stdlib_module_names is not None:
            assert name in stdlib_module_names, name
        else:  # pragma: no cover - Python 3.9 fallback
            assert name not in _KNOWN_THIRD_PARTY, name


# =========================================================================== #
# AC3: normalise_leaf_path is a pure, idempotent normaliser
# =========================================================================== #


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("per_label.7.geometry.touches_superior", "per_label.{label}.geometry.touches_superior"),
        (
            "image_features.per_label.12.mean_intensity",
            "image_features.per_label.{label}.mean_intensity",
        ),
        ("extended.original_firstorder_Mean", "extended.{radiomic}"),
        ("extended.anything_at_all_123", "extended.{radiomic}"),
        (
            "reference_delta.per_label.9.distribution_distance",
            "reference_delta.{label}.distribution_distance",
        ),
        ("overlaps.2.overlap_voxels", "overlaps[].overlap_voxels"),
    ],
)
def test_ac3_normalise_leaf_path_collapses(catalogue_module, raw, expected):
    assert catalogue_module.normalise_leaf_path(raw) == expected


@pytest.mark.parametrize(
    "path",
    [
        "per_label.{label}.geometry.touches_superior",
        "relationships.out_of_order_labels[]",
        "stage3.per_label_offsets[].offset_mm",
        "features_version",
        "extended.{radiomic}",
        "overlaps[].overlap_voxels",
        "per_label.3.components.fragmentation_index",
    ],
)
def test_ac3_normalise_leaf_path_idempotent(catalogue_module, path):
    once = catalogue_module.normalise_leaf_path(path)
    twice = catalogue_module.normalise_leaf_path(once)
    assert once == twice


@pytest.mark.parametrize(
    "path",
    [
        "per_label.4.geometry.touches_superior",
        "reference_delta.per_label.11.features.spline_offset_mm",
        "overlaps.0.overlap_voxels",
    ],
)
def test_ac3_no_bare_integer_segment_remains(catalogue_module, path):
    normalised = catalogue_module.normalise_leaf_path(path)
    for segment in re.split(r"[.\[\]]+", normalised):
        assert not re.fullmatch(r"\d+", segment), normalised


# =========================================================================== #
# AC4: iter_leaf_paths walks a record to normalised leaf paths
# =========================================================================== #


def test_ac4_clean_control_leaf_paths(catalogue_module):
    record = _CORPUS_RECORDS["clean_control"]
    paths = catalogue_module.iter_leaf_paths(record)

    for expected in (
        "per_label.{label}.geometry.touches_superior",
        "per_label.{label}.components.fragmentation_index",
        "relationships.out_of_order_labels[]",
        "stage3.per_label_offsets[].offset_mm",
        "features_version",
    ):
        assert expected in paths, expected

    for path in paths:
        for segment in re.split(r"[.\[\]]+", path):
            assert not re.fullmatch(r"\d+", segment), path

    # 93 -> 94: item 123 (docs/aide/items/123-recalibrate-and-regenerate-
    # downstream-artifacts.md, AC48) adds one leaf path,
    # stage3.per_label_offsets[].is_terminal.
    assert len(paths) == 94


def test_ac4_empty_list_yields_container_bracket_path(catalogue_module):
    record = {"relationships": {"out_of_order_labels": []}}
    paths = catalogue_module.iter_leaf_paths(record)
    assert "relationships.out_of_order_labels[]" in paths


# =========================================================================== #
# AC5: the driver-record set is in-package, deterministic and block-complete
# =========================================================================== #


def test_ac5_source_has_no_tests_dir_literal(catalogue_module):
    import inspect

    source = inspect.getsource(catalogue_module.iter_driver_records)
    assert "tests/" not in source


def test_ac5_deterministic_across_calls(catalogue_module):
    first = dict(catalogue_module.iter_driver_records())
    second = dict(catalogue_module.iter_driver_records())
    assert first.keys() == second.keys()
    assert first == second


def test_ac5_union_has_nonempty_overlaps_pair(catalogue_module, driver_records, leaf_union):
    assert "overlaps[].overlap_voxels" in leaf_union
    assert any(record.get("overlaps") for record in driver_records.values())


def test_ac5_union_has_a_stage3_record(driver_records):
    assert any("stage3" in record for record in driver_records.values())


def test_ac5_union_has_a_degenerate_record(driver_records):
    assert any("stage3" not in record for record in driver_records.values())


# =========================================================================== #
# AC6: coverage is exact and duplicate-free, in both directions
# =========================================================================== #


def test_ac6_record_origin_entries_match_union_exactly(full_catalogue, leaf_union):
    record_entries = [e for e in full_catalogue.entries if e.origin == "record"]
    record_paths = {e.path for e in record_entries}
    assert record_paths == leaf_union
    assert len(record_entries) == len(record_paths)  # each exactly once


def test_ac6_no_two_entries_share_a_path(full_catalogue):
    paths = [e.path for e in full_catalogue.entries]
    assert len(paths) == len(set(paths))


# =========================================================================== #
# AC7: every entry carries a non-empty status from the fixed vocabulary
# =========================================================================== #


def test_ac7_every_status_in_fixed_vocabulary(full_catalogue):
    allowed = {"keep", "retune", "retire", "unwired"}
    for entry in full_catalogue.entries:
        assert entry.status in allowed, (entry.path, entry.status)


# =========================================================================== #
# AC8: unwired means the check found nothing, in both directions
# =========================================================================== #


def test_ac8_unwired_iff_no_consumers_and_no_override(full_catalogue, feature_docs_module):
    overridden_paths = set(feature_docs_module.STATUS_OVERRIDES)
    for entry in full_catalogue.entries:
        no_consumers = not entry.consuming_rules and not entry.consumers
        expected_unwired = no_consumers and entry.path not in overridden_paths
        assert (entry.status == "unwired") == expected_unwired, entry.path


def test_ac8_nonempty_consuming_rules_never_unwired(full_catalogue):
    for entry in full_catalogue.entries:
        if entry.consuming_rules:
            assert entry.status != "unwired", entry.path


# =========================================================================== #
# AC9: the tracer is non-invasive
# =========================================================================== #


def test_ac9_trace_proxy_is_dict_subclass(catalogue_module, driver_records):
    record = next(iter(driver_records.values()))
    captured = {}

    def _capture(traced):
        captured["proxy"] = traced
        return None

    catalogue_module.trace_record_access(record, _capture)
    assert isinstance(captured["proxy"], dict)


def test_ac9_deepcopy_snapshot_survives_tracing(catalogue_module, driver_records):
    record = next(iter(driver_records.values()))
    snapshot = copy.deepcopy(record)

    def _run_all_rules(traced):
        for rule in iter_rules():
            try:
                rule.evaluate(traced, _CONFIG)
            except Exception:
                pass
        return None

    catalogue_module.trace_record_access(record, _run_all_rules)
    assert record == snapshot


@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_ac9_traced_run_rules_matches_plain(catalogue_module, case_id):
    # trace_record_access(record, callable) returns the accumulated sink of
    # reached paths, not callable's return value (Implementation Step 5), so
    # the traced findings are captured via closure instead.
    plain = _CORPUS_RECORDS[case_id]
    captured = {}

    def _run(traced):
        captured["findings"] = run_rules(traced, _CONFIG)
        return None

    catalogue_module.trace_record_access(plain, _run)
    plain_findings = run_rules(plain, _CONFIG)
    assert captured["findings"] == plain_findings


# =========================================================================== #
# AC10: dynamic attribution reproduces the measured rule<->feature reads
# =========================================================================== #


@pytest.mark.parametrize(
    "path, rule_id",
    [
        ("per_label.{label}.components.fragmentation_index", "fragmentation"),
        ("per_label.{label}.geometry.touches_inferior", "border"),
        ("per_label.{label}.geometry.touches_superior", "border"),
        ("per_label.{label}.geometry.touches_left", "border"),
        ("per_label.{label}.geometry.touches_right", "border"),
        ("per_label.{label}.geometry.touches_anterior", "border"),
        ("per_label.{label}.geometry.touches_posterior", "border"),
        ("relationships.out_of_order_labels[]", "sequence"),
        ("relationships.missing_levels[]", "coverage"),
        ("stage3.per_label_offsets[].offset_mm", "mislabel"),
        ("per_label.{label}.geometry.physical_volume_mm3", "bounds"),
    ],
)
def test_ac10_observed_rule_attribution(full_catalogue, path, rule_id):
    entry = _entry(full_catalogue, path)
    assert rule_id in entry.consuming_rules, (path, entry.consuming_rules)
    evidence_for_rule = {ev for rid, ev in entry.rule_evidence if rid == rule_id}
    assert "observed" in evidence_for_rule, (path, entry.rule_evidence)


# =========================================================================== #
# AC11: the static scan adds branches the drivers never execute
# =========================================================================== #


def test_ac11_overlap_voxels_attributed_to_overlap_rule(full_catalogue):
    entry = _entry(full_catalogue, "overlaps[].overlap_voxels")
    assert "overlap" in entry.consuming_rules


# =========================================================================== #
# AC12: every rule attribution carries an evidence tag
# =========================================================================== #


def test_ac12_rule_evidence_tags_and_rule_id_sets(full_catalogue):
    allowed = {"observed", "static", "static-ambiguous"}
    for entry in full_catalogue.entries:
        rule_ids_in_evidence = set()
        for rule_id, evidence in entry.rule_evidence:
            assert evidence in allowed, (entry.path, evidence)
            rule_ids_in_evidence.add(rule_id)
        assert rule_ids_in_evidence == set(entry.consuming_rules), entry.path


# =========================================================================== #
# AC13: the rule->mode map is derived from synth/, not hand-typed
# =========================================================================== #


_RULE_MODE_MAP = {
    "mislabel": (1, 4),
    "fragmentation": (2, 3),
    "coverage": (5,),
    "border": (6,),
    "sequence": (7,),
    "overlap": (8,),
}


@pytest.mark.parametrize("rule_id, modes", sorted(_RULE_MODE_MAP.items()))
def test_ac13_rule_mode_map_effect_on_failure_modes(
    full_catalogue, feature_docs_module, rule_id, modes
):
    anchor_paths = {
        p for paths in feature_docs_module.MODE_ANCHOR_PATHS.values() for p in paths
    }
    matches = [
        e
        for e in full_catalogue.entries
        if set(e.consuming_rules) == {rule_id} and e.path not in anchor_paths
    ]
    assert matches, f"expected a non-anchor entry consumed only by {rule_id!r}"
    for entry in matches:
        assert set(entry.failure_modes) == set(modes), entry.path


def test_ac13_no_hand_typed_rule_mode_dict_in_catalogue_source(catalogue_module):
    source = Path(catalogue_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    rule_ids = set(_RULE_MODE_MAP)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {
                k.value
                for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            assert not rule_ids.issubset(keys), (
                "catalogue.py appears to contain a hand-typed rule-id -> mode "
                "dict literal"
            )


# =========================================================================== #
# AC14: item 099's per-mode metrics anchor all eight modes
# =========================================================================== #


def test_ac14_mode_anchor_paths_key_set_is_one_to_eight(feature_docs_module):
    assert set(feature_docs_module.MODE_ANCHOR_PATHS.keys()) == set(range(1, 9))
    for mode, paths in feature_docs_module.MODE_ANCHOR_PATHS.items():
        assert len(paths) >= 1, mode


def test_ac14_every_anchor_path_present_with_per_mode_metric_evidence(
    full_catalogue, feature_docs_module
):
    for mode, paths in feature_docs_module.MODE_ANCHOR_PATHS.items():
        for path in paths:
            entry = _entry(full_catalogue, path)
            assert mode in entry.failure_modes, (path, mode, entry.failure_modes)
            assert "per_mode_metric" in entry.mode_evidence, (path, entry.mode_evidence)


# =========================================================================== #
# AC15: an unmapped rule yields an honest empty mode list
# =========================================================================== #


def test_ac15_declared_mode_less_rule_only_entry_is_honestly_mode_less(
    full_catalogue, feature_docs_module
):
    """Reconciled for item 137 (Testing Strategy: "existing tests to
    reconcile"): the four rules this test originally called "unmapped" --
    ``bounds``, ``intensity``, ``reference_delta``,
    ``intensity_reference_delta`` -- are item 137's to disposition, and none
    of them is unmapped on this tree any more. ``bounds`` and
    ``reference_delta`` now declare §6 mode 2 analytically; ``intensity`` and
    ``intensity_reference_delta`` now declare themselves mode-less with a
    recorded reason. An entry consumed only by the mode-less pair is honestly
    reported as ``("rule_mode_less",)``, not ``("rule_unmapped",)`` -- the
    AC15 honesty claim survives the disposition, restated for the state that
    now exists. What ``mode_evidence == ("rule_unmapped",)`` means after
    item 137 -- a consuming rule with no declaration at all -- is exercised
    by ``tests/test_137_mode_less_rule_disposition.py``'s adversarial stub
    -rule test, since no such rule ships on this tree (item 137 AC1)."""
    mode_less_rules = {"intensity", "intensity_reference_delta"}
    anchor_paths = {
        p for paths in feature_docs_module.MODE_ANCHOR_PATHS.values() for p in paths
    }
    candidates = [
        e
        for e in full_catalogue.entries
        if e.consuming_rules
        and set(e.consuming_rules) <= mode_less_rules
        and e.path not in anchor_paths
    ]
    assert candidates, "expected at least one mode-less-rule-only, non-anchor entry"
    for entry in candidates:
        assert entry.failure_modes == ()
        assert entry.mode_evidence == ("rule_mode_less",), entry.path


# =========================================================================== #
# AC16: an undocumented realised path fails generation loudly (strict) or is
# surfaced (non-strict)
# =========================================================================== #


_INJECTED_FIELD = "__injected_undocumented_field_item103__"


def _driver_records_with_injected_field(catalogue_module):
    real = catalogue_module.iter_driver_records

    def _fake():
        first = True
        for driver_id, record in real():
            if first:
                record = dict(copy.deepcopy(record))
                record[_INJECTED_FIELD] = 1.0
                first = False
            yield driver_id, record

    return _fake


def test_ac16_strict_raises_feature_doc_missing_naming_the_path(
    catalogue_module, monkeypatch
):
    monkeypatch.setattr(
        catalogue_module,
        "iter_driver_records",
        _driver_records_with_injected_field(catalogue_module),
    )
    with pytest.raises(catalogue_module.FeatureDocMissing) as excinfo:
        catalogue_module.build_catalogue(strict=True)
    assert _INJECTED_FIELD in str(excinfo.value)


def test_ac16_non_strict_surfaces_undocumented_entry(catalogue_module, monkeypatch):
    monkeypatch.setattr(
        catalogue_module,
        "iter_driver_records",
        _driver_records_with_injected_field(catalogue_module),
    )
    cat = catalogue_module.build_catalogue(strict=False)
    entry = _entry(cat, _INJECTED_FIELD)
    assert entry.documented is False
    assert entry.measures == ""
    assert entry.computation == ""
    assert entry.units == ""
    assert entry.scale_sensitivity == ""


# =========================================================================== #
# AC17: a stale annotation is caught too
# =========================================================================== #


_STALE_KEY = "this.path.does.not.exist.anywhere.item103"


def _patch_feature_docs(catalogue_module, feature_docs_module, monkeypatch, new_mapping):
    if hasattr(catalogue_module, "FEATURE_DOCS"):
        monkeypatch.setattr(catalogue_module, "FEATURE_DOCS", new_mapping)
    monkeypatch.setattr(feature_docs_module, "FEATURE_DOCS", new_mapping)


def test_ac17_strict_raises_catalogue_error_naming_stale_key(
    catalogue_module, feature_docs_module, monkeypatch
):
    stale_doc = feature_docs_module.FeatureDoc(
        measures="stale", computation="stale", units="", scale_sensitivity="dimensionless"
    )
    new_mapping = dict(feature_docs_module.FEATURE_DOCS)
    new_mapping[_STALE_KEY] = stale_doc
    _patch_feature_docs(catalogue_module, feature_docs_module, monkeypatch, new_mapping)

    with pytest.raises(catalogue_module.CatalogueError) as excinfo:
        catalogue_module.build_catalogue(strict=True)
    assert _STALE_KEY in str(excinfo.value)


def test_ac17_committed_feature_docs_keys_equal_union_exactly(
    catalogue_module, feature_docs_module, leaf_union
):
    assert set(feature_docs_module.FEATURE_DOCS.keys()) == leaf_union
    cat = catalogue_module.build_catalogue(strict=True)
    assert isinstance(cat, catalogue_module.FeatureCatalogue)


# =========================================================================== #
# AC18: serialisation is deterministic and byte-reproducible
# =========================================================================== #


def _assert_no_timestamps_hosts_or_absolute_paths(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key not in ("generated_at", "timestamp")
            _assert_no_timestamps_hosts_or_absolute_paths(value)
    elif isinstance(obj, list):
        for value in obj:
            _assert_no_timestamps_hosts_or_absolute_paths(value)
    elif isinstance(obj, str):
        assert not obj.startswith("/"), obj
        assert "\\" not in obj, obj


def test_ac18_json_dict_has_no_timestamp_host_or_absolute_path(catalogue_module, full_catalogue):
    as_dict = catalogue_module.catalogue_to_dict(full_catalogue)
    _assert_no_timestamps_hosts_or_absolute_paths(as_dict)


def test_ac18_catalogue_to_dict_byte_reproducible_within_session(
    catalogue_module, full_catalogue
):
    def _bytes():
        text = json.dumps(
            catalogue_module.catalogue_to_dict(full_catalogue), indent=2, sort_keys=True
        ) + "\n"
        return text.encode("utf-8")

    assert _bytes() == _bytes()


def test_ac18_render_markdown_byte_reproducible_within_session(catalogue_module, full_catalogue):
    first = catalogue_module.render_markdown(full_catalogue).encode("utf-8")
    second = catalogue_module.render_markdown(full_catalogue).encode("utf-8")
    assert first == second


# =========================================================================== #
# AC19: the committed generated documents match a fresh regeneration
# =========================================================================== #


def test_ac19_committed_docs_match_fresh_regeneration(catalogue_module, tmp_path):
    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue_module.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

    assert json_dest.read_bytes() == committed_json.read_bytes()
    assert md_dest.read_bytes() == committed_md.read_bytes()


def test_ac19_regenerate_twice_in_one_session_byte_identical(catalogue_module, tmp_path):
    dest1_json = tmp_path / "run1.json"
    dest1_md = tmp_path / "run1.md"
    dest2_json = tmp_path / "run2.json"
    dest2_md = tmp_path / "run2.md"

    catalogue_module.main(["--json", str(dest1_json), "--md", str(dest1_md)])
    catalogue_module.main(["--json", str(dest2_json), "--md", str(dest2_md)])

    assert dest1_json.read_bytes() == dest2_json.read_bytes()
    assert dest1_md.read_bytes() == dest2_md.read_bytes()


# =========================================================================== #
# AC20: the generated documents are LF-pinned
# =========================================================================== #


def test_ac20_gitattributes_pins_both_generated_documents():
    text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "docs/aide/feature_catalogue.generated.json text eol=lf" in text
    assert "docs/aide/feature_catalogue.generated.md text eol=lf" in text


# =========================================================================== #
# AC21: the status report is fed by the generated JSON, not by literals
# =========================================================================== #

_ASR_MODULE_PATH = _REPO_ROOT / "scripts" / "aide_status_report.py"


@pytest.fixture(scope="module")
def asr():
    spec = importlib.util.spec_from_file_location("aide_status_report_103", _ASR_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_ac21_feature_catalog_and_unwired_extractors_absent(asr):
    source = _ASR_MODULE_PATH.read_text(encoding="utf-8")
    assert "FEATURE_CATALOG =" not in source
    assert "FEATURE_CATALOG:" not in source
    assert "UNWIRED_EXTRACTORS" not in source
    assert "FEATURE_CATALOG" not in dir(asr)
    assert "UNWIRED_EXTRACTORS" not in dir(asr)


def test_ac21_load_feature_catalog_defined(asr):
    assert hasattr(asr, "load_feature_catalog")
    assert callable(asr.load_feature_catalog)


def test_ac21_stdlib_only_imports_still_hold(asr):
    source = _ASR_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                top_level_names.add(node.module.split(".")[0])
    assert "segfacet" not in top_level_names


# =========================================================================== #
# AC22: the rendered section keeps the same markup shape
# =========================================================================== #


def test_ac22_rendered_section_markup_shape(asr):
    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    groups = asr.load_feature_catalog(committed_json)
    assert isinstance(groups, tuple)
    assert groups, "expected at least one feature group from the committed catalogue"
    for group in groups:
        assert isinstance(group, asr.FeatureGroupSpec)

    section = asr._render_feature_catalog_section(groups)

    assert '<section id="features"' in section
    assert section.count('<div class="feature-group">') == len(groups)
    assert section.count('<span class="b-pill">') >= len(groups)
    assert '<p class="note"><code>' in section
    total_items = sum(len(g.items) for g in groups)
    assert section.count('<details class="fold mini">') == total_items
    assert '<p class="feature-detail">' in section


def test_ac22_no_pre_103_css_class_removed(asr):
    for selector in (".b-pill", ".feature-group", "p.feature-detail"):
        assert selector in asr._CSS, selector


# =========================================================================== #
# AC23: a missing or corrupt catalogue degrades gracefully
# =========================================================================== #


def test_ac23_load_feature_catalog_missing_file_returns_empty_tuple(asr, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert asr.load_feature_catalog(missing) == ()


def test_ac23_load_feature_catalog_corrupt_json_returns_empty_tuple(asr, tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{this is not valid json", encoding="utf-8")
    assert asr.load_feature_catalog(corrupt) == ()


def test_ac23_render_section_placeholder_for_empty_groups(asr):
    section = asr._render_feature_catalog_section(())
    assert "feature_catalogue.generated.json" in section
    assert "segfacet.catalogue" in section or "python -m segfacet.catalogue" in section


def test_ac23_render_html_with_minimal_model_does_not_raise(asr):
    model = asr.ReportModel(generated_at="now")
    doc = asr.render_html(model)
    assert "<!DOCTYPE html>" in doc


# =========================================================================== #
# AC24: the Markdown document carries every queue-mandated column
# =========================================================================== #

_MD_COLUMNS = (
    "path",
    "module / item",
    "measures",
    "computation",
    "units",
    "scale sensitivity",
    "§6 mode(s)",
    "consuming rules",
    "status",
)


def test_ac24_markdown_has_exact_columns_and_row_count(catalogue_module, full_catalogue):
    md = catalogue_module.render_markdown(full_catalogue)
    lines = md.splitlines()

    table_rows = [l for l in lines if l.strip().startswith("|")]
    assert table_rows, "expected a Markdown table"
    header = table_rows[0]
    for column in _MD_COLUMNS:
        assert column in header, column

    # header + separator row + one row per entry
    assert len(table_rows) - 2 == len(full_catalogue.entries)
    assert str(len(full_catalogue.entries)) in md


def test_ac24_markdown_rows_are_in_catalogue_order(catalogue_module, full_catalogue):
    md = catalogue_module.render_markdown(full_catalogue)
    lines = [l for l in md.splitlines() if l.strip().startswith("|")]
    # Drop the header and the "---" separator row.
    body_rows = [l for l in lines[2:]]
    row_paths = [l.split("|")[1].strip() for l in body_rows]
    expected_paths = [e.path for e in full_catalogue.entries]
    assert row_paths == expected_paths


# =========================================================================== #
# AC25: (byte-hash scope fences formerly here were removed by item 107; see
# docs/aide/items/107-retire-byte-hash-scope-fences.md. Diff-time scope is
# now checked by `aide scope` (.aide/scripts/aide.py) on the branch.)
# =========================================================================== #


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_iter_leaf_paths_empty_record(catalogue_module):
    assert catalogue_module.iter_leaf_paths({}) == set()


def test_adv_iter_leaf_paths_zero_label_record_relationships_none(catalogue_module):
    record = _CORPUS_RECORDS.get("clean_control")
    zero_label = dict(record)
    zero_label["per_label"] = {}
    zero_label["relationships"] = None
    zero_label.pop("stage3", None)
    paths = catalogue_module.iter_leaf_paths(zero_label)
    assert "relationships" in paths
    for path in paths:
        assert not path.startswith("relationships.")


def test_adv_deeply_nested_empty_dict_beside_empty_list_are_distinct(catalogue_module):
    record = {
        "block": {
            "nested": {},
            "siblings": [],
        }
    }
    paths = catalogue_module.iter_leaf_paths(record)
    assert "block.nested" in paths
    assert "block.siblings[]" in paths
    assert paths == {"block.nested", "block.siblings[]"}


def test_adv_normalise_leaf_path_never_touches_values_only_keys(catalogue_module):
    # A level_name whose *value* looks like an integer must not be confused
    # with an integer *key* segment -- normalise_leaf_path only ever sees the
    # path string, never the value, so this is really about not
    # over-matching digit-looking text embedded in a legitimate key name.
    path = "per_label.3.level_name"
    normalised = catalogue_module.normalise_leaf_path(path)
    assert normalised == "per_label.{label}.level_name"


def test_adv_raising_rule_during_trace_does_not_abort_build(catalogue_module, monkeypatch):
    class _AlwaysRaisesRule(Rule):
        rule_id = "__item103_always_raises__"

        def evaluate(self, record, config):
            raise RuntimeError("deliberate failure for AC-adjacent adversarial coverage")

    snapshot = dict(_RULES)
    _RULES[_AlwaysRaisesRule.rule_id] = _AlwaysRaisesRule()
    try:
        cat = catalogue_module.build_catalogue()
        assert isinstance(cat, catalogue_module.FeatureCatalogue)
        assert len(cat.entries) > 0
    finally:
        _RULES.clear()
        _RULES.update(snapshot)


def test_adv_build_catalogue_idempotent_and_pure(catalogue_module, feature_docs_module):
    docs_snapshot = copy.deepcopy(dict(feature_docs_module.FEATURE_DOCS))

    first = catalogue_module.build_catalogue()
    second = catalogue_module.build_catalogue()

    assert first == second
    assert catalogue_module.catalogue_to_dict(first) == catalogue_module.catalogue_to_dict(second)
    assert dict(feature_docs_module.FEATURE_DOCS) == docs_snapshot


def test_adv_ambiguous_static_name_tagged_on_every_candidate(full_catalogue):
    # A last-path-segment name shared by multiple catalogue paths (e.g.
    # "label", "level_name") is exactly the case mechanism B's name matching
    # is ambiguous over. Group entries by last segment; if a (rule_id,
    # "static-ambiguous") pair appears for one member of a group, it must
    # appear for every member of that same group -- no silent single-winner
    # pick.
    from collections import defaultdict

    by_last_segment = defaultdict(list)
    for entry in full_catalogue.entries:
        last_segment = entry.path.rstrip("[]").rsplit(".", 1)[-1]
        by_last_segment[last_segment].append(entry)

    for group in by_last_segment.values():
        if len(group) < 2:
            continue
        ambiguous_rule_ids = {
            rule_id
            for entry in group
            for rule_id, evidence in entry.rule_evidence
            if evidence == "static-ambiguous"
        }
        for rule_id in ambiguous_rule_ids:
            for entry in group:
                assert (rule_id, "static-ambiguous") in entry.rule_evidence, (
                    entry.path,
                    rule_id,
                )


def test_adv_status_report_loader_directory_returns_empty_tuple(asr, tmp_path):
    a_directory = tmp_path / "a_directory_not_a_file"
    a_directory.mkdir()
    assert asr.load_feature_catalog(a_directory) == ()


def test_adv_status_report_loader_truncated_json_returns_empty_tuple(asr, tmp_path):
    truncated = tmp_path / "truncated.json"
    truncated.write_text('{"groups": [{"title": "X"', encoding="utf-8")
    assert asr.load_feature_catalog(truncated) == ()


def test_adv_status_report_loader_unknown_schema_version_returns_empty_tuple(asr, tmp_path):
    unknown_version = tmp_path / "unknown_version.json"
    unknown_version.write_text(
        json.dumps({"schema_version": "not-a-real-version-999", "groups": []}),
        encoding="utf-8",
    )
    assert asr.load_feature_catalog(unknown_version) == ()
