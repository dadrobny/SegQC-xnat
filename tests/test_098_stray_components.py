"""Tests for item 098 -- promoting stray-component metrics to first-class
``components`` fields (``stray_component_count``, ``stray_component_sizes``,
``stray_volume_mm3``, ``stray_volume_fraction``).

Covers Acceptance Criteria AC1-AC19:

- AC1:  ``ComponentsInfo`` carries the four new fields, appended after
        ``small_fragments``, and is still ``frozen=True``.
- AC2:  ``stray_component_sizes == component_sizes[1:]`` (no aliasing), swept
        over every label of every ``tests/corpus`` case.
- AC3:  ``stray_component_count == component_count - 1 ==
        len(stray_component_sizes)``, same sweep.
- AC4:  ``stray_volume_mm3 == sum(component_volumes_mm3[1:])`` (1e-9 abs tol).
- AC5:  ``stray_volume_fraction + largest_component_fraction == 1.0`` (1e-12
        abs tol), and bounded ``[0, 1]``.
- AC6:  a single-component label reports the stray-population zero case,
        with ``stray_volume_mm3`` a ``float`` 0.0.
- AC7:  hand-computed values on a multi-component, anisotropic-spacing fixture.
- AC8:  ``components_to_dict`` emits exactly the ten keys, with a
        non-aliasing shallow copy of ``stray_component_sizes``.
- AC9:  the report schema admits and requires the four new fields.
- AC10: the fragmentation rule reads ``stray_component_sizes`` rather than
        recomputing it -- a deliberately disagreeing value changes the
        outcome.
- AC11: a legacy (six-key) components dict falls back to
        ``component_sizes[1:]`` -- unchanged rule behaviour.
- AC12: hand-set island findings match a frozen pre-refactor snapshot across
        all nine ``tests/corpus`` cases under ``bundled_default_config()``.
- AC13: the reference-derived branch's excess-``component_count`` finding
        matches a frozen pre-refactor snapshot.
- AC14: every committed golden's per-label ``components`` block carries the
        four new keys and the whole file still validates.
- AC15: the goldens' ``verdict``/``findings`` are unchanged (frozen snapshot).
- AC16: intra-run determinism (``write_goldens`` into two dirs) and
        ``reports_close`` against the committed goldens still hold.
- AC17: the reference vocabulary (``INGESTED_MORPHOLOGY_FEATURES``) is
        unaffected; no ``stray_*`` key appears in a morphology-delta output.
- AC18: ``reference_verse_v1.json`` is byte-untouched (pinned sha256) and
        still loads/scores a case.
- AC19: (docstring corrections -- not independently unit-tested; verified by
        code review per the item's Testing Strategy.)

Adversarial / edge-case scenarios included:
- Empty stray population (single-component label).
- Many equal-sized components (tie-break determinism, count==4, fraction==0.8).
- Stray components that outweigh the dominant one (fraction > 0.5).
- Immutability: two ``compute_components`` calls on the same image agree and
  never mutate ``seg_img``; ``run_rules`` never mutates the record.
- ``components_to_dict`` round-trips through ``json.dumps``/``json.loads``
  with plain ``float``/``int`` leaves (no ``numpy`` scalar types).
- The AC10/AC11 boundary: an explicitly empty ``stray_component_sizes=[]``
  is honoured (no island finding), not treated as absent.
"""

from __future__ import annotations

import copy
import json

import jsonschema
import numpy as np
import nibabel as nib
import pytest

import segfacet.heuristics.fragmentation  # noqa: F401 -- triggers FragmentationRule registration
import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from synthetic import LABEL_DTYPE, affine_from_spacing, make_labelmap

from segfacet.config import HeuristicConfig, bundled_default_config, default_config
from segfacet.features.components import ComponentsInfo, compute_components
from segfacet.feature_report import components_to_dict
from segfacet.heuristics import run_rules
from segfacet.pipeline import extract_feature_record
from segfacet.reference import (
    ALL_STRATUM,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
    bundled_default_reference,
    bundled_production_reference,
    bundled_production_reference_path,
)
from segfacet.reference.delta import compute_morphology_reference_delta
from segfacet.reference.ingest import INGESTED_MORPHOLOGY_FEATURES
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import GOLDEN_DIR, load_golden, write_goldens, reports_close
from segfacet.synth.regression import loaded_seg_image


# =========================================================================== #
# Helpers
# =========================================================================== #


def _config(min_fragment_voxels: int = 0) -> HeuristicConfig:
    return HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=0,
        min_label_count=0,
        min_fragment_voxels=min_fragment_voxels,
    )


def _compact_label_img():
    """A single connected 4x4x4 block (label 1), one component."""
    return make_labelmap((10, 10, 10), {1: ((3, 7), (3, 7), (3, 7))})


def _multi_component_anisotropic_img():
    """Label 1: a 27-voxel dominant body plus two known, separated stray
    pieces (6 voxels, 4 voxels), under non-isotropic spacing (0.5, 1.0, 3.0)
    -- voxel volume 1.5 mm^3, chosen so a wrong voxel_volume route would not
    silently agree with the correct one.

    Component sizes sorted descending: [27, 6, 4]. Total 37 voxels.
    """
    data = np.zeros((14, 14, 14), dtype=LABEL_DTYPE)
    data[1:4, 1:4, 1:4] = 1  # dominant body: 3*3*3 = 27 voxels
    data[6:8, 6:8, 6:7] = 1  # stray piece: 2*2*1 = 4 voxels
    data[9:12, 1:3, 9:10] = 1  # stray piece: 3*2*1 = 6 voxels
    return nib.Nifti1Image(data, affine_from_spacing((0.5, 1.0, 3.0)))


def _all_corpus_components(config: HeuristicConfig | None = None):
    """Yield ComponentsInfo for every label of every committed corpus case."""
    cfg = config or _config()
    manifest = load_manifest()
    for case in manifest["cases"]:
        seg_img = loaded_seg_image(case)
        labels = sorted(
            int(v) for v in np.unique(np.asanyarray(seg_img.dataobj)) if v != 0
        )
        for label in labels:
            yield case["case_id"], label, compute_components(seg_img, label, cfg)


def _make_legacy_components(component_count: int, component_sizes: list) -> dict:
    """A pre-098 (six-key) components sub-dict -- no stray_* keys at all."""
    total = sum(component_sizes) if component_sizes else 1
    dominant = component_sizes[0] if component_sizes else 0
    fi = dominant / total if total else 1.0
    return {
        "component_count": component_count,
        "component_sizes": list(component_sizes),
        "component_volumes_mm3": [float(s) for s in component_sizes],
        "largest_component_fraction": fi,
        "fragmentation_index": fi,
        "small_fragments": [],
    }


def _make_098_components(
    component_count: int,
    component_sizes: list,
    stray_component_sizes: list,
) -> dict:
    """A post-098 (ten-key) components sub-dict with an explicit,
    possibly-disagreeing stray_component_sizes value."""
    d = _make_legacy_components(component_count, component_sizes)
    d["stray_component_count"] = len(stray_component_sizes)
    d["stray_component_sizes"] = list(stray_component_sizes)
    d["stray_volume_mm3"] = float(sum(stray_component_sizes))
    total = sum(component_sizes) if component_sizes else 1
    dominant_fraction = (component_sizes[0] / total) if component_sizes else 1.0
    d["stray_volume_fraction"] = 1.0 - dominant_fraction
    return d


def _make_record(label: int, level_name: str, components: dict) -> dict:
    return {
        "per_label": {label: {"label": label, "level_name": level_name, "components": components}},
        "relationships": {},
        "overlaps": {},
    }


def _frag_findings(findings):
    return [f for f in findings if f.rule_id == "fragmentation"]


def _report_schema():
    import importlib.resources
    import segfacet as _segfacet_pkg

    ref = importlib.resources.files(_segfacet_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _components_schema():
    return _report_schema()["definitions"]["components"]


def _well_formed_components_instance() -> dict:
    """A ten-key components dict expected to validate against the post-098
    schema."""
    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    return components_to_dict(info)


# =========================================================================== #
# AC1: ComponentsInfo carries four new stray fields; still frozen
# =========================================================================== #


def test_ac1_componentsinfo_has_four_new_fields():
    """AC1: ComponentsInfo declares the four new fields."""
    import dataclasses

    names = {f.name for f in dataclasses.fields(ComponentsInfo)}
    assert {
        "stray_component_count",
        "stray_component_sizes",
        "stray_volume_mm3",
        "stray_volume_fraction",
    } <= names


def test_ac1_existing_five_fields_still_present_and_ordered_first():
    """AC1: the five pre-098 fields are unchanged and still come first."""
    import dataclasses

    names = [f.name for f in dataclasses.fields(ComponentsInfo)]
    assert names[:5] == [
        "component_count",
        "component_sizes",
        "component_volumes_mm3",
        "largest_component_fraction",
        "small_fragments",
    ]


def test_ac1_computed_info_carries_correct_types():
    """AC1: compute_components populates the four fields with the right types."""
    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    assert isinstance(info.stray_component_count, int)
    assert isinstance(info.stray_component_sizes, list)
    assert isinstance(info.stray_volume_mm3, float)
    assert isinstance(info.stray_volume_fraction, float)


def test_ac1_componentsinfo_is_still_frozen():
    """AC1: ComponentsInfo remains an immutable (frozen) dataclass."""
    import dataclasses

    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.stray_component_count = 99  # type: ignore[misc]


# =========================================================================== #
# AC2: stray_component_sizes == component_sizes[1:], no aliasing
# =========================================================================== #


def test_ac2_stray_sizes_equals_tail_of_component_sizes_across_corpus():
    """AC2: over every label of every corpus case, stray_component_sizes ==
    component_sizes[1:] (same values, same order)."""
    swept = False
    for _case_id, _label, info in _all_corpus_components():
        swept = True
        assert info.stray_component_sizes == info.component_sizes[1:]
    assert swept, "expected at least one corpus label to be swept"


def test_ac2_stray_sizes_does_not_alias_component_sizes():
    """AC2: the returned stray_component_sizes list is not the same object
    as component_sizes."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.stray_component_sizes is not info.component_sizes


def test_ac2_hand_fixture_stray_sizes():
    """AC2: on the hand-built fixture, stray_component_sizes == [6, 4]."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.component_sizes == [27, 6, 4]
    assert info.stray_component_sizes == [6, 4]


# =========================================================================== #
# AC3: stray_component_count is the non-dominant component count
# =========================================================================== #


def test_ac3_stray_count_matches_across_corpus():
    """AC3: stray_component_count == component_count - 1 ==
    len(stray_component_sizes), swept over every label of every corpus case."""
    swept = False
    for _case_id, _label, info in _all_corpus_components():
        swept = True
        assert info.stray_component_count == info.component_count - 1
        assert info.stray_component_count == len(info.stray_component_sizes)
    assert swept


def test_ac3_hand_fixture_stray_count():
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.stray_component_count == 2


# =========================================================================== #
# AC4: stray_volume_mm3 is the summed volume of the stray components
# =========================================================================== #


def test_ac4_stray_volume_matches_summed_component_volumes_across_corpus():
    """AC4: stray_volume_mm3 == sum(component_volumes_mm3[1:]) within 1e-9
    absolute tolerance, swept over the corpus."""
    swept = False
    for _case_id, _label, info in _all_corpus_components():
        swept = True
        expected = sum(info.component_volumes_mm3[1:])
        assert info.stray_volume_mm3 == pytest.approx(expected, abs=1e-9)
    assert swept


def test_ac4_hand_fixture_stray_volume_mm3():
    """AC4: on the hand fixture (voxel volume 1.5 mm^3), stray_volume_mm3 ==
    (6 + 4) * 1.5 == 15.0."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.component_volumes_mm3 == pytest.approx([40.5, 9.0, 6.0])
    assert info.stray_volume_mm3 == pytest.approx(15.0, abs=1e-9)


# =========================================================================== #
# AC5: stray_volume_fraction is the complement of largest_component_fraction
# =========================================================================== #


def test_ac5_fraction_complement_holds_across_corpus():
    """AC5: stray_volume_fraction + largest_component_fraction == 1.0 within
    1e-12 absolute tolerance, and stray_volume_fraction is in [0, 1], swept
    over the corpus."""
    swept = False
    for _case_id, _label, info in _all_corpus_components():
        swept = True
        assert info.stray_volume_fraction + info.largest_component_fraction == pytest.approx(
            1.0, abs=1e-12
        )
        assert 0.0 <= info.stray_volume_fraction <= 1.0
    assert swept


def test_ac5_hand_fixture_fraction():
    """AC5: on the hand fixture, stray_volume_fraction == 1 - 27/37 == 10/37."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.largest_component_fraction == pytest.approx(27 / 37)
    assert info.stray_volume_fraction == pytest.approx(10 / 37)
    assert info.stray_volume_fraction + info.largest_component_fraction == pytest.approx(
        1.0, abs=1e-12
    )


# =========================================================================== #
# AC6: a single-component label reports an empty stray population
# =========================================================================== #


def test_ac6_single_component_stray_count_is_zero():
    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.stray_component_count == 0


def test_ac6_single_component_stray_sizes_is_empty_list():
    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.stray_component_sizes == []


def test_ac6_single_component_stray_volume_is_float_zero():
    """AC6: stray_volume_mm3 is 0.0 (a float, not the int 0)."""
    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.stray_volume_mm3 == 0.0
    assert isinstance(info.stray_volume_mm3, float)
    assert not isinstance(info.stray_volume_mm3, bool)


def test_ac6_single_component_stray_fraction_is_zero():
    seg = _compact_label_img()
    info = compute_components(seg, label=1, config=_config())
    assert info.stray_volume_fraction == 0.0


# =========================================================================== #
# AC7: hand-computed values on the multi-component anisotropic fixture
# =========================================================================== #


def test_ac7_all_four_fields_match_hand_computation():
    """AC7: on a fixture with a known dominant body (27 vox) plus two known
    stray pieces (6, 4 vox) under (0.5, 1.0, 3.0) mm spacing (voxel volume
    1.5 mm^3), all four stray fields equal the values computed by hand from
    the fixture's construction."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())

    assert info.component_count == 3
    assert info.component_sizes == [27, 6, 4]
    assert info.stray_component_count == 2
    assert info.stray_component_sizes == [6, 4]
    assert info.stray_volume_mm3 == pytest.approx(15.0, abs=1e-9)  # (6+4)*1.5
    assert info.stray_volume_fraction == pytest.approx(10 / 37)


# =========================================================================== #
# AC8: components_to_dict emits the four new keys, non-aliasing
# =========================================================================== #


def test_ac8_dict_key_set_is_exactly_six_plus_four():
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    expected_keys = {
        "component_count",
        "component_sizes",
        "component_volumes_mm3",
        "largest_component_fraction",
        "small_fragments",
        "fragmentation_index",
        "stray_component_count",
        "stray_component_sizes",
        "stray_volume_mm3",
        "stray_volume_fraction",
    }
    assert set(d.keys()) == expected_keys


def test_ac8_dict_values_equal_dataclass_values():
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert d["stray_component_count"] == info.stray_component_count
    assert d["stray_component_sizes"] == info.stray_component_sizes
    assert d["stray_volume_mm3"] == pytest.approx(info.stray_volume_mm3)
    assert d["stray_volume_fraction"] == pytest.approx(info.stray_volume_fraction)


def test_ac8_dict_stray_sizes_list_does_not_alias_dataclass_list():
    """AC8: mutating the returned dict's stray_component_sizes list leaves
    info.stray_component_sizes unchanged."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    original = list(info.stray_component_sizes)
    d["stray_component_sizes"].append(999999)
    assert info.stray_component_sizes == original


# =========================================================================== #
# AC9: the report schema admits and requires the four new fields
# =========================================================================== #


def test_ac9_well_formed_components_block_validates():
    """AC9: a fully-populated components block validates against the schema."""
    jsonschema.validate(_well_formed_components_instance(), _components_schema())


@pytest.mark.parametrize(
    "missing_key",
    [
        "stray_component_count",
        "stray_component_sizes",
        "stray_volume_mm3",
        "stray_volume_fraction",
    ],
)
def test_ac9_missing_new_required_key_fails_validation(missing_key):
    """AC9: removing any one of the four new required keys fails validation."""
    instance = _well_formed_components_instance()
    del instance[missing_key]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, _components_schema())


def test_ac9_extra_unknown_key_still_fails_validation():
    """AC9: additionalProperties: false survived -- an unknown extra key
    still fails."""
    instance = _well_formed_components_instance()
    instance["totally_unknown_key"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, _components_schema())


def test_ac9_schema_types_are_as_specified():
    """AC9: the schema types the four fields as integer / array-of-integer /
    number / number bounded [0, 1]."""
    props = _components_schema()["properties"]
    assert props["stray_component_count"]["type"] == "integer"
    assert props["stray_component_sizes"]["type"] == "array"
    assert props["stray_component_sizes"]["items"]["type"] == "integer"
    assert props["stray_volume_mm3"]["type"] == "number"
    assert props["stray_volume_fraction"]["type"] == "number"
    assert props["stray_volume_fraction"]["minimum"] == 0
    assert props["stray_volume_fraction"]["maximum"] == 1


def test_ac9_all_four_fields_are_required():
    required = _components_schema()["required"]
    for key in (
        "stray_component_count",
        "stray_component_sizes",
        "stray_volume_mm3",
        "stray_volume_fraction",
    ):
        assert key in required


# =========================================================================== #
# AC10: the fragmentation rule reads stray_component_sizes, not sizes[1:]
# =========================================================================== #


def test_ac10_disagreeing_stray_sizes_fires_from_named_field(tmp_path):
    """AC10: component_sizes=[1000, 500] (no island by the old recomputation
    route) but stray_component_sizes=[5] (an island by the new named-field
    route) -- the island finding fires, proving the rule reads the field."""
    comp = _make_098_components(
        component_count=2, component_sizes=[1000, 500], stray_component_sizes=[5]
    )
    record = _make_record(22, "L3", comp)

    from segfacet.config import SUPPORTED_SCHEMA_VERSION, load_config

    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n  fragmentation:\n    params:\n"
        "      fragmentation_index_threshold: 0.0\n"
        "      island_min_voxels: 50\n"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")
    cfg = load_config(config_path)

    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island, "Expected the island finding to fire via stray_component_sizes=[5]"
    assert "[5]" in island[0].reason


def test_ac10_recomputation_from_sizes_would_not_have_fired():
    """AC10 (contrast check): component_sizes[1:] == [500], which is >=
    island_min_voxels=50 and would NOT fire under the old recomputation
    route -- proving the disagreement is genuine."""
    assert [500][0] >= 50  # sanity: the old route's candidate is not tiny


# =========================================================================== #
# AC11: a legacy six-key components dict behaves exactly as today
# =========================================================================== #


def test_ac11_legacy_six_key_dict_still_fires_island_via_fallback():
    """AC11: a components dict carrying only the six pre-098 keys still
    fires the island finding by falling back to component_sizes[1:]."""
    comp = _make_legacy_components(component_count=2, component_sizes=[900, 10])
    assert "stray_component_sizes" not in comp
    record = _make_record(22, "L3", comp)
    island = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island, "Legacy six-key dict must still fire via the sizes[1:] fallback"
    assert "10" in island[0].reason


def test_ac11_legacy_six_key_dict_no_island_when_all_large():
    """AC11: a legacy dict with no tiny non-dominant component still produces
    no island finding (fallback path, not just the fire path)."""
    comp = _make_legacy_components(component_count=2, component_sizes=[500, 500])
    record = _make_record(22, "L3", comp)
    island = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island == []


def test_ac11_legacy_dict_findings_identical_to_hand_set_module_baseline():
    """AC11: the legacy shape reproduces the same finding shape (rule_id,
    severity, labels, reason) that test_028's pre-098 helper produces for an
    identical fixture -- proving the fallback is behaviour-preserving."""
    comp = _make_legacy_components(component_count=2, component_sizes=[900, 10])
    record = _make_record(17, "T11", comp)
    findings = _frag_findings(run_rules(record, default_config()))
    island = [f for f in findings if f.reason.startswith("Rogue island(s):")]
    assert len(island) == 1
    f = island[0]
    assert f.rule_id == "fragmentation"
    assert f.severity.label == "flagged-for-review"
    assert f.labels == frozenset({17})
    assert f.reason == (
        "Rogue island(s): Label 17: 1 non-dominant component(s) strictly "
        "below island_min_voxels=50. Tiny island sizes: [10]. "
        "component_count=2, component_sizes=[900, 10], "
        "fragmentation_index=0.989010989010989"
    )


# =========================================================================== #
# Adversarial: AC10/AC11 boundary -- explicit empty stray list is honoured
# =========================================================================== #


def test_adv_explicit_empty_stray_sizes_is_honoured_not_treated_as_absent():
    """Adversarial (AC10/AC11 boundary): stray_component_sizes=[] present and
    empty, with component_sizes=[1000, 5] (which WOULD fire via the legacy
    fallback) -- the explicitly-empty named population wins: no island
    finding fires."""
    comp = _make_098_components(
        component_count=2, component_sizes=[1000, 5], stray_component_sizes=[]
    )
    record = _make_record(22, "L3", comp)
    island = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island == [], (
        "An explicitly empty stray_component_sizes must be honoured (no "
        "island), not treated as absent-and-falling-back to sizes[1:] "
        "(which would fire on the tiny size 5)"
    )


# =========================================================================== #
# AC12: hand-set island findings are byte-identical across the corpus
# (frozen pre-refactor snapshot -- captured from the unmodified code before
# item 098's builder touches anything)
# =========================================================================== #

_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS = {
    "clean_control": [],
    "mode1_displace": [],
    "mode2_fragment": [
        {
            "rule_id": "fragmentation",
            "severity": "flagged-for-review",
            "labels": [22],
            "reason": (
                "Fragmentation: Label 22: fragmentation_index=0.5 is "
                "strictly below threshold 0.75. component_count=2, "
                "component_sizes=[9000, 9000]"
            ),
        }
    ],
    "mode3_inject_islands": [
        {
            "rule_id": "fragmentation",
            "severity": "flagged-for-review",
            "labels": [22],
            "reason": (
                "Rogue island(s): Label 22: 1 non-dominant component(s) "
                "strictly below island_min_voxels=50. Tiny island sizes: "
                "[27]. component_count=2, component_sizes=[18750, 27], "
                "fragmentation_index=0.9985620706183096"
            ),
        }
    ],
    "mode4_relabel_swap": [],
    "mode5_remove_level": [],
    "mode6_crop_at_border": [],
    "mode7_sequence_break": [],
    "mode8_force_overlap": [],
}


@pytest.mark.parametrize(
    "case_id", sorted(_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS.keys())
)
def test_ac12_hand_set_fragmentation_findings_match_frozen_snapshot(case_id):
    """AC12: for every corpus case under bundled_default_config() (no
    reference attached -> hand-set branch), the fragmentation findings match
    the frozen pre-098 snapshot exactly (rule_id, severity, sorted labels,
    character-for-character reason)."""
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == case_id)
    seg_img = loaded_seg_image(case)
    from segfacet.pipeline import run_qc

    case_result, _block = run_qc(seg_img, bundled_default_config())
    got = [
        {
            "rule_id": f.rule_id,
            "severity": f.severity.label,
            "labels": sorted(f.labels),
            "reason": f.reason,
        }
        for f in case_result.findings
        if f.rule_id == "fragmentation"
    ]
    assert got == _PRE_098_HAND_SET_FRAGMENTATION_FINDINGS[case_id]


# =========================================================================== #
# AC13: the reference-derived branch is untouched (frozen pre-refactor
# snapshot, mirroring tests/test_090_reference_derived_defaults.py's fixture
# style)
# =========================================================================== #


def _level_distribution(level_name: str, stratum: str, feature_stats: dict) -> LevelDistribution:
    return LevelDistribution(
        level_name=level_name, stratum=stratum, record_count=10, feature_stats=feature_stats,
    )


def _reference(levels: dict, percentiles=(1, 5, 25, 50, 75, 95, 99)) -> ReferenceDistribution:
    provenance = Provenance(
        source="unit-test", config_hash="deadbeef", build_date="2026-07-11", size_proxy_name=None,
    )
    return ReferenceDistribution(
        schema_version="1.2",
        provenance=provenance,
        features=("largest_component_fraction", "component_count"),
        percentiles=tuple(percentiles),
        subject_count=10,
        strata=(ALL_STRATUM,),
        levels=levels,
    )


def _feature_stats(p1, p5, p25, p50, p75, p95, p99, count=10, std=1.0) -> FeatureStats:
    return FeatureStats(
        count=count, mean=float(p50), std=float(std), min=float(p1), max=float(p99),
        percentiles={
            "p1": float(p1), "p5": float(p5), "p25": float(p25), "p50": float(p50),
            "p75": float(p75), "p95": float(p95), "p99": float(p99),
        },
    )


def test_ac13_reference_derived_excess_finding_matches_frozen_snapshot():
    """AC13: a record with an attached reference covering L3's
    component_count produces an excess-component_count finding whose reason
    is character-for-character identical to a frozen pre-098 snapshot, and
    the island_min_voxels floor is bypassed (9 components, several tiny, but
    the fire condition is component_count > p99, not the voxel floor)."""
    l3_lcf = _feature_stats(0.55, 0.62, 0.75, 0.85, 0.92, 0.98, 1.0)
    l3_cc = _feature_stats(1.0, 1.0, 1.0, 2.0, 3.0, 6.0, 7.0)
    reference = _reference(
        {"L3": {ALL_STRATUM: _level_distribution(
            "L3", ALL_STRATUM,
            {"largest_component_fraction": l3_lcf, "component_count": l3_cc},
        )}}
    )
    sizes = [900, 20, 20, 20, 20, 20, 20, 20, 20]
    comp = {
        "component_count": 9,
        "component_sizes": sizes,
        "component_volumes_mm3": [float(s) for s in sizes],
        "largest_component_fraction": 900 / 1060,
        "fragmentation_index": 900 / 1060,
        "small_fragments": [],
    }
    record = {
        "per_label": {22: {"label": 22, "level_name": "L3", "components": comp}},
        "relationships": {},
        "overlaps": {},
        "reference": reference,
    }
    findings = _frag_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "fragmentation"
    assert f.severity.label == "flagged-for-review"
    assert sorted(f.labels) == [22]
    assert f.reason == (
        "Rogue island(s): Label 22 (L3): component_count=9 exceeds "
        "reference maximum 7 (p99) for level L3. "
        "component_sizes=[900, 20, 20, 20, 20, 20, 20, 20, 20], "
        "fragmentation_index=0.8490566037735849"
    )


# =========================================================================== #
# AC14: every committed golden carries the four new keys and validates
# =========================================================================== #


def test_ac14_every_golden_components_block_has_four_new_keys():
    """AC14: every per-label components block in every committed golden
    carries the four new keys (post-regeneration)."""
    manifest = load_manifest()
    for case in manifest["cases"]:
        golden = load_golden(case["case_id"])
        per_label = golden.get("features", {}).get("per_label", {})
        assert per_label, f"case {case['case_id']!r} has no per_label entries"
        for label_key, entry in per_label.items():
            comp = entry.get("components")
            if comp is None:
                continue
            for key in (
                "stray_component_count",
                "stray_component_sizes",
                "stray_volume_mm3",
                "stray_volume_fraction",
            ):
                assert key in comp, (
                    f"case {case['case_id']!r} label {label_key!r} components "
                    f"block missing {key!r}"
                )


def test_ac14_every_golden_still_validates_against_schema():
    schema = _report_schema()
    manifest = load_manifest()
    for case in manifest["cases"]:
        golden = load_golden(case["case_id"])
        jsonschema.validate(golden, schema)


# =========================================================================== #
# AC15: the goldens' verdicts and findings are unchanged
# (frozen pre-098 snapshot)
# =========================================================================== #

_PRE_098_GOLDEN_VERDICT_AND_FINDINGS = {
    "clean_control": {"verdict": "pass", "findings": []},
    "mode1_displace": {"verdict": "pass", "findings": []},
    "mode2_fragment": {
        "verdict": "flagged-for-review",
        "findings": [
            {
                "rule_id": "fragmentation",
                "severity": "flagged-for-review",
                "labels": [22],
                "reason": (
                    "Fragmentation: Label 22: fragmentation_index=0.5 is "
                    "strictly below threshold 0.75. component_count=2, "
                    "component_sizes=[9000, 9000]"
                ),
            }
        ],
    },
    "mode3_inject_islands": {
        "verdict": "flagged-for-review",
        "findings": [
            {
                "rule_id": "fragmentation",
                "severity": "flagged-for-review",
                "labels": [22],
                "reason": (
                    "Rogue island(s): Label 22: 1 non-dominant component(s) "
                    "strictly below island_min_voxels=50. Tiny island sizes: "
                    "[27]. component_count=2, component_sizes=[18750, 27], "
                    "fragmentation_index=0.9985620706183096"
                ),
            }
        ],
    },
    "mode4_relabel_swap": {"verdict": "pass", "findings": []},
    "mode5_remove_level": {
        "verdict": "flagged-for-review",
        "findings": [
            {
                "rule_id": "coverage",
                "severity": "flagged-for-review",
                "labels": [],
                "reason": (
                    "Missing interior level(s): L3 absent within the "
                    "observed present-level span."
                ),
            }
        ],
    },
    "mode6_crop_at_border": {
        "verdict": "flagged-for-review",
        "findings": [
            {
                "rule_id": "border",
                "severity": "flagged-for-review",
                "labels": [22],
                "reason": (
                    "Partial vertebra clipped by FOV: label 22 (L3) touches "
                    "image face(s): anterior."
                ),
            }
        ],
    },
    "mode7_sequence_break": {
        "verdict": "flagged-for-review",
        "findings": [
            {
                "rule_id": "sequence",
                "severity": "flagged-for-review",
                "labels": [28],
                "reason": "Non-continuous label sequence: T13 out of anatomical order.",
            }
        ],
    },
    "mode8_force_overlap": {"verdict": "pass", "findings": []},
}


#: Case whose finding ``reason`` text names an anatomical face
#: (``crop_at_border``'s ``border`` finding). Item 116 makes both
#: ``compute_label_geometry`` and the synth face resolver derive that name
#: from the volume's affine rather than a hardcoded axis index, so the exact
#: face word is a property of the (unchanged) affine-derived contract, not of
#: this frozen pre-098 snapshot -- compare structure (rule_id/severity/
#: labels) for it and leave free-text reason pinning to the face-aware
#: assertions in tests/test_108_affine_faces.py and
#: tests/test_116_ras_native_corpus.py. Every other case's reason text is
#: unaffected by the item 116 migration and stays pinned exactly.
_FACE_NAME_SENSITIVE_CASES = frozenset({"mode6_crop_at_border"})


def _finding_summary(f, *, include_reason: bool) -> dict:
    summary = {
        "rule_id": f["rule_id"],
        "severity": f["severity"],
        "labels": sorted(f["labels"]),
    }
    if include_reason:
        summary["reason"] = f["reason"]
    return summary


@pytest.mark.parametrize(
    "case_id", sorted(_PRE_098_GOLDEN_VERDICT_AND_FINDINGS.keys())
)
def test_ac15_golden_verdict_and_findings_unchanged(case_id):
    """AC15: the regenerated golden's top-level verdict and findings array
    (length, order, rule_id/severity/labels, and -- except for the one
    face-name-sensitive case, item 116 -- reason) are identical to the
    pre-098 committed golden's -- only the features block grew."""
    golden = load_golden(case_id)
    expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS[case_id]
    assert golden["verdict"] == expected["verdict"]

    include_reason = case_id not in _FACE_NAME_SENSITIVE_CASES
    got_findings = [_finding_summary(f, include_reason=include_reason) for f in golden["findings"]]
    expected_findings = [
        _finding_summary(f, include_reason=include_reason) for f in expected["findings"]
    ]
    assert got_findings == expected_findings


# =========================================================================== #
# AC16: intra-run determinism and reports_close still hold
# =========================================================================== #


def test_ac16_write_goldens_intra_run_determinism(tmp_path):
    """AC16: write_goldens into two fresh directories within one session
    produces byte-identical files for all nine cases."""
    dest1 = tmp_path / "dest1"
    dest2 = tmp_path / "dest2"
    write_goldens(dest1)
    write_goldens(dest2)

    manifest = load_manifest()
    for case in manifest["cases"]:
        name = f"{case['case_id']}.json"
        assert (dest1 / name).read_bytes() == (dest2 / name).read_bytes()


def test_ac16_write_goldens_matches_committed_within_tolerance(tmp_path):
    """AC16: reports_close(fresh, committed) is true for each case."""
    dest = tmp_path / "fresh"
    write_goldens(dest)

    manifest = load_manifest()
    for case in manifest["cases"]:
        fresh = json.loads((dest / f"{case['case_id']}.json").read_text(encoding="utf-8"))
        committed = json.loads(
            (GOLDEN_DIR / f"{case['case_id']}.json").read_text(encoding="utf-8")
        )
        assert reports_close(fresh, committed), case["case_id"]


# =========================================================================== #
# AC17: the reference vocabulary is fenced off
# =========================================================================== #


def test_ac17_ingested_morphology_features_unchanged():
    """AC17: INGESTED_MORPHOLOGY_FEATURES is unchanged; no stray_* name
    appears in it."""
    assert INGESTED_MORPHOLOGY_FEATURES == (
        "largest_component_fraction",
        "component_count",
        "eigenvalue_ratio",
    )
    assert not any(name.startswith("stray_") for name in INGESTED_MORPHOLOGY_FEATURES)


def test_ac17_morphology_delta_output_has_no_stray_keys():
    """AC17: compute_morphology_reference_delta over a features block whose
    components blocks carry the four new fields produces feature deltas for
    only the three ingested morphology names -- no stray_* key anywhere in
    the output."""
    from segfacet.synth.clean_gt import build_clean_spine

    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    config = bundled_default_config()
    block = extract_feature_record(spine.seg_img, config)

    # Sanity: the (post-098) components blocks do carry the new fields.
    any_stray_present = any(
        "stray_component_sizes" in entry.get("components", {})
        for entry in block["per_label"].values()
    )
    assert any_stray_present, "fixture expected at least one components block with stray_* fields"

    reference = bundled_default_reference()
    delta = compute_morphology_reference_delta(block, reference)

    for label_delta in delta.per_label.values():
        for fd in label_delta.features:
            assert not fd.feature.startswith("stray_"), (
                f"unexpected stray_* feature in morphology delta output: {fd.feature!r}"
            )
            assert fd.feature in INGESTED_MORPHOLOGY_FEATURES


# =========================================================================== #
# AC18: reference_verse_v1.json is untouched
# =========================================================================== #

# Pinned pre-098 sha256 of the committed reference_verse_v1.json artifact.
_PRE_098_REFERENCE_VERSE_V1_SHA256 = (
    "978c63d0367d9dd018f472aaa034740d42a04c47b95ccf0501cc128ad0638826"
)


def test_ac18_reference_verse_v1_bytes_unchanged():
    """AC18: reference_verse_v1.json is byte-identical to its pre-098
    state (pinned sha256)."""
    import hashlib

    path = bundled_production_reference_path()
    assert path.name == "reference_verse_v1.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == _PRE_098_REFERENCE_VERSE_V1_SHA256


def test_ac18_reference_verse_v1_still_loads_and_scores_a_case():
    """AC18: the artifact still loads and scores a case without change."""
    from segfacet.pipeline import run_qc_with_reference

    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode6_crop_at_border")
    seg_img = loaded_seg_image(case)
    reference = bundled_production_reference()
    case_result, _block, _delta = run_qc_with_reference(
        seg_img, bundled_default_config(), reference
    )
    bounds_findings = [f for f in case_result.findings if f.rule_id == "bounds" and 22 in f.labels]
    assert len(bounds_findings) >= 1


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_many_equal_components_stray_fields_are_self_consistent():
    """Adversarial: five equal-sized (100-voxel) components -- the
    "dominant" one is component_sizes[0] by the existing descending sort even
    though the tie choice is arbitrary; stray fields stay self-consistent
    (count == 4, fraction == 0.8) and deterministic across repeated calls."""
    data = np.zeros((20, 20, 20), dtype=LABEL_DTYPE)
    # Five separated 100-voxel (5x5x4) blocks.
    boxes = [
        (0, 5, 0, 5, 0, 4),
        (0, 5, 0, 5, 8, 12),
        (0, 5, 8, 13, 0, 4),
        (8, 13, 0, 5, 0, 4),
        (0, 5, 8, 13, 8, 12),
    ]
    for (x0, x1, y0, y1, z0, z1) in boxes:
        data[x0:x1, y0:y1, z0:z1] = 1
    seg = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))

    info1 = compute_components(seg, label=1, config=_config())
    info2 = compute_components(seg, label=1, config=_config())

    assert info1.component_count == 5
    assert info1.stray_component_count == 4
    assert info1.stray_volume_fraction == pytest.approx(0.8)
    assert info1 == info2, "compute_components must be deterministic across repeated calls"


def test_adv_stray_components_can_outweigh_dominant_component():
    """Adversarial: a label whose stray components collectively dominate
    ([100, 90, 90]) still yields stray_volume_fraction > 0.5 and <= 1.0."""
    data = np.zeros((30, 30, 30), dtype=LABEL_DTYPE)
    data[0:5, 0:5, 0:4] = 1     # 5*5*4  = 100 voxels -- dominant (largest single)
    data[0:9, 10:15, 0:2] = 1   # 9*5*2  = 90 voxels
    data[0:9, 20:25, 0:2] = 1   # 9*5*2  = 90 voxels
    seg = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))

    info = compute_components(seg, label=1, config=_config())
    assert info.component_count == 3
    assert info.component_sizes == [100, 90, 90]
    assert info.stray_volume_fraction > 0.5
    assert info.stray_volume_fraction <= 1.0


def test_adv_compute_components_does_not_mutate_seg_img():
    """Adversarial: compute_components never mutates its seg_img input --
    two calls on the same image agree and the underlying array is untouched."""
    seg = _multi_component_anisotropic_img()
    before = np.array(seg.dataobj, copy=True)
    info1 = compute_components(seg, label=1, config=_config())
    after_first = np.array(seg.dataobj, copy=True)
    info2 = compute_components(seg, label=1, config=_config())
    after_second = np.array(seg.dataobj, copy=True)

    assert np.array_equal(before, after_first)
    assert np.array_equal(before, after_second)
    assert info1 == info2


def test_adv_run_rules_does_not_mutate_stray_fields_in_record():
    """Adversarial: run_rules never mutates the record's components sub-dict,
    including the new stray_* keys."""
    comp = _make_098_components(
        component_count=2, component_sizes=[900, 10], stray_component_sizes=[10]
    )
    record = _make_record(22, "L3", comp)
    record_before = copy.deepcopy(record)
    run_rules(record, default_config())
    assert record == record_before


def test_adv_components_to_dict_round_trips_through_json_with_plain_types():
    """Adversarial: components_to_dict's two new scalars are plain
    float/int (not numpy scalar types), so the dict round-trips cleanly
    through json.dumps/json.loads and stays canonical-JSON-safe."""
    seg = _multi_component_anisotropic_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)

    assert type(d["stray_component_count"]) is int
    assert type(d["stray_volume_mm3"]) is float
    assert type(d["stray_volume_fraction"]) is float
    assert all(type(s) is int for s in d["stray_component_sizes"])

    round_tripped = json.loads(json.dumps(d))
    assert round_tripped == d
