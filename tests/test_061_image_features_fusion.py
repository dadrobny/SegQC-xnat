"""Tests for item 061 -- fusing intensity features into the JSON report &
per-case feature table (``src/segqc/feature_report.py``: ``label_intensity_to_dict``
/ ``build_image_features_block``; ``src/segqc/report.py``:
``serialize_report``/``serialize_report_json`` gain ``image_features``;
``src/segqc/human_report.py``: ``render_feature_table`` gains ``image_features``).

Covers Acceptance Criteria AC1-AC13:

- AC1: build_image_features_block produces a well-formed block.
- AC2: per-label first_order mirrors LabelIntensity field-for-field.
- AC3: None statistics serialise to JSON null, never NaN.
- AC4: the optional extended seam folds radiomics features in.
- AC5: block-level provenance echoes the arguments.
- AC6: available=False yields the unavailable sentinel block.
- AC7: assembly is deterministic, ordered, and non-mutating.
- AC8: serialize_report gains an optional image_features parameter.
- AC9: omitting image_features preserves the prior report shape.
- AC10: the schema validates a well-formed block and rejects a malformed one.
- AC11: serialize_report_json forwards image_features and round-trips.
- AC12: render_feature_table renders an intensity section when given a block,
  and is unchanged when not.
- AC13: the rendered intensity section is null-safe and deterministic.

Adversarial / edge-case scenarios included:
- Empty intensity mapping.
- Mixed populated + sentinel labels.
- extended for a label absent from intensity is ignored.
- Non-mutation via deep-copy comparison.
- Back-compat omission across features/findings/reference_delta combinations.
- Schema round-trip (null statistic still validates; unknown key rejected;
  missing required field rejected).
- Render back-compat byte-identity and sentinel/unavailable placeholder text.
"""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest

from segqc.config import bundled_default_config
from segqc.feature_report import (
    IMAGE_FEATURES_VERSION,
    build_image_features_block,
    label_intensity_to_dict,
)
from segqc.features.intensity import LabelIntensity
from segqc.human_report import render_feature_table
from segqc.report import serialize_report, serialize_report_json
from segqc.verdict import Verdict


# =========================================================================== #
# Hand-built LabelIntensity fixtures
# =========================================================================== #

_STAT_FIELDS = (
    "mean", "median", "std", "min", "max",
    "p05", "p25", "p50", "p75", "p95", "range", "iqr", "entropy",
)

LI_20 = LabelIntensity(
    voxel_count=512, n_nonfinite_excluded=0,
    mean=210.5, median=208.0, std=33.1, min=120.0, max=305.0,
    p05=150.0, p25=188.0, p50=208.0, p75=233.0, p95=280.0,
    range=185.0, iqr=45.0, entropy=3.42,
)

LI_21 = LabelIntensity(
    voxel_count=256, n_nonfinite_excluded=2,
    mean=190.0, median=189.0, std=25.0, min=100.0, max=280.0,
    p05=140.0, p25=170.0, p50=189.0, p75=210.0, p95=260.0,
    range=180.0, iqr=40.0, entropy=3.1,
)

SENTINEL = LabelIntensity(
    voxel_count=0, n_nonfinite_excluded=5,
    mean=None, median=None, std=None, min=None, max=None,
    p05=None, p25=None, p50=None, p75=None, p95=None,
    range=None, iqr=None, entropy=None,
)


def _verdict():
    return Verdict.build(reasons=[], per_label={})


# =========================================================================== #
# AC1: build_image_features_block produces a well-formed block
# =========================================================================== #


def test_ac1_well_formed_block_with_two_populated_labels():
    block = build_image_features_block({20: LI_20, 21: LI_21})
    assert block["image_features_version"] == IMAGE_FEATURES_VERSION
    assert IMAGE_FEATURES_VERSION == "1.0"
    assert block["available"] is True
    assert block["radiomics_available"] is False
    assert block["backend"] == "builtin"
    assert set(block["per_label"].keys()) == {"20", "21"}
    assert len(block["per_label"]) == 2


# =========================================================================== #
# AC2: per-label first_order mirrors LabelIntensity field-for-field
# =========================================================================== #


def test_ac2_first_order_mirrors_label_intensity_field_for_field():
    block = build_image_features_block({20: LI_20})
    entry = block["per_label"]["20"]
    assert entry["label"] == 20
    first_order = entry["first_order"]
    assert set(first_order.keys()) == {"voxel_count", "n_nonfinite_excluded"} | set(_STAT_FIELDS)
    assert first_order["voxel_count"] == LI_20.voxel_count
    assert first_order["n_nonfinite_excluded"] == LI_20.n_nonfinite_excluded
    for field_name in _STAT_FIELDS:
        assert first_order[field_name] == getattr(LI_20, field_name), field_name


def test_ac2_label_intensity_to_dict_matches_dataclass():
    d = label_intensity_to_dict(LI_20)
    assert d["voxel_count"] == LI_20.voxel_count
    assert d["n_nonfinite_excluded"] == LI_20.n_nonfinite_excluded
    for field_name in _STAT_FIELDS:
        assert d[field_name] == getattr(LI_20, field_name), field_name


# =========================================================================== #
# AC3: None statistics serialise to JSON null, never NaN
# =========================================================================== #


def test_ac3_sentinel_statistics_are_none_not_nan():
    block = build_image_features_block({99: SENTINEL})
    first_order = block["per_label"]["99"]["first_order"]
    for field_name in _STAT_FIELDS:
        assert first_order[field_name] is None, field_name
    assert isinstance(first_order["voxel_count"], int)
    assert isinstance(first_order["n_nonfinite_excluded"], int)
    text = json.dumps(block, allow_nan=False)  # must not raise
    assert "NaN" not in text
    assert "Infinity" not in text


# =========================================================================== #
# AC4: the optional extended seam folds radiomics features in
# =========================================================================== #


def test_ac4_extended_seam_places_mapping_under_label():
    block = build_image_features_block(
        {20: LI_20, 21: LI_21},
        extended={20: {"original_glcm_Contrast": 1.5}},
    )
    assert block["per_label"]["20"]["extended"] == {"original_glcm_Contrast": 1.5}
    # Present in intensity but absent from extended -> empty dict.
    assert block["per_label"]["21"]["extended"] == {}


def test_ac4_extended_none_default_yields_empty_dicts_for_every_entry():
    block = build_image_features_block({20: LI_20, 21: LI_21})
    assert block["per_label"]["20"]["extended"] == {}
    assert block["per_label"]["21"]["extended"] == {}


# =========================================================================== #
# AC5: block-level provenance echoes the arguments
# =========================================================================== #


def test_ac5_provenance_echoes_backend_and_radiomics_available():
    block = build_image_features_block(
        {20: LI_20}, backend="pyradiomics", radiomics_available=True,
    )
    assert block["backend"] == "pyradiomics"
    assert block["radiomics_available"] is True


def test_ac5_provenance_defaults_are_builtin_and_false():
    block = build_image_features_block({20: LI_20})
    assert block["backend"] == "builtin"
    assert block["radiomics_available"] is False


# =========================================================================== #
# AC6: available=False yields the unavailable sentinel block
# =========================================================================== #


def test_ac6_available_false_yields_empty_per_label_sentinel():
    block = build_image_features_block({20: LI_20}, available=False)
    assert block["available"] is False
    assert block["per_label"] == {}


def test_ac6_unavailable_sentinel_block_validates_against_schema():
    block = build_image_features_block({20: LI_20}, available=False)
    verdict = _verdict()
    report = serialize_report(
        verdict, "case-061-unavailable", bundled_default_config(),
        image_features=block,
    )  # must not raise (schema-validated inside serialize_report)
    assert report["image_features"]["available"] is False


# =========================================================================== #
# AC7: assembly is deterministic, ordered, and non-mutating
# =========================================================================== #


def test_ac7_deterministic_equal_dicts_and_byte_identical_json():
    intensity = {21: LI_21, 20: LI_20}
    block1 = build_image_features_block(intensity)
    block2 = build_image_features_block(intensity)
    assert block1 == block2
    assert json.dumps(block1, sort_keys=True) == json.dumps(block2, sort_keys=True)


def test_ac7_per_label_ascending_regardless_of_input_order():
    intensity = {21: LI_21, 20: LI_20}
    block = build_image_features_block(intensity)
    assert list(block["per_label"].keys()) == ["20", "21"]


def test_ac7_inputs_are_not_mutated():
    intensity = {21: LI_21, 20: LI_20}
    extended = {20: {"original_glcm_Contrast": 1.5}}
    intensity_before = copy.deepcopy(intensity)
    extended_before = copy.deepcopy(extended)
    build_image_features_block(intensity, extended=extended)
    assert intensity == intensity_before
    assert extended == extended_before


# =========================================================================== #
# AC8: serialize_report gains an optional image_features parameter
# =========================================================================== #


def test_ac8_serialize_report_embeds_block_verbatim_under_top_level_key():
    block = build_image_features_block({20: LI_20})
    verdict = _verdict()
    report = serialize_report(
        verdict, "case-061", bundled_default_config(), image_features=block,
    )  # must not raise
    assert report["image_features"] == block


# =========================================================================== #
# AC9: omitting image_features preserves the prior report shape
# =========================================================================== #


def test_ac9_default_omits_image_features_key():
    verdict = _verdict()
    report = serialize_report(verdict, "case-061-omit", bundled_default_config())
    assert "image_features" not in report
    assert report["schema_version"] == "0.1"


def test_ac9_report_with_only_other_optional_blocks_omits_image_features():
    verdict = _verdict()
    features_block = {
        "features_version": "0.1", "per_label": {}, "overlaps": [], "relationships": None,
    }
    report = serialize_report(
        verdict, "case-061-others", bundled_default_config(),
        features=features_block, findings=[], reference_delta=None,
    )
    assert "image_features" not in report


def test_ac9_omission_is_deep_equal_to_call_without_the_parameter():
    verdict = _verdict()
    config = bundled_default_config()
    report_no_kw = serialize_report(verdict, "case-061-eq", config)
    report_explicit_none = serialize_report(
        verdict, "case-061-eq", config, image_features=None,
    )
    assert report_no_kw == report_explicit_none


# =========================================================================== #
# AC10: the schema validates a well-formed block and rejects a malformed one
# =========================================================================== #


def test_ac10_well_formed_block_validates_in_report():
    block = build_image_features_block({20: LI_20})
    verdict = _verdict()
    serialize_report(
        verdict, "case-061-schema-ok", bundled_default_config(), image_features=block,
    )  # must not raise


def test_ac10_unknown_top_level_key_is_rejected():
    block = build_image_features_block({20: LI_20})
    block["bogus"] = 1
    verdict = _verdict()
    with pytest.raises(jsonschema.ValidationError):
        serialize_report(
            verdict, "case-061-bogus", bundled_default_config(), image_features=block,
        )


def test_ac10_missing_required_first_order_field_is_rejected():
    block = build_image_features_block({20: LI_20})
    del block["per_label"]["20"]["first_order"]["mean"]
    verdict = _verdict()
    with pytest.raises(jsonschema.ValidationError):
        serialize_report(
            verdict, "case-061-missing-field", bundled_default_config(), image_features=block,
        )


# =========================================================================== #
# AC11: serialize_report_json forwards image_features and round-trips
# =========================================================================== #


def test_ac11_serialize_report_json_round_trips_equal_to_dict_form():
    block = build_image_features_block({20: LI_20, 99: SENTINEL})
    verdict = _verdict()
    config = bundled_default_config()
    text = serialize_report_json(
        verdict, "case-061-json", config, image_features=block,
    )
    parsed = json.loads(text)  # must not raise
    expected = serialize_report(
        verdict, "case-061-json", config, image_features=block,
    )
    assert parsed == expected
    assert "NaN" not in text
    assert "Infinity" not in text


# =========================================================================== #
# AC12: render_feature_table renders an intensity section / is unchanged
# =========================================================================== #


def _features_block():
    return {
        "features_version": "0.1",
        "per_label": {
            "20": {
                "label": 20, "level_name": "L1",
                "geometry": {
                    "voxel_count": 100, "physical_volume_mm3": 500.0,
                    "extent_x_mm": 1, "extent_y_mm": 1, "extent_z_mm": 1,
                    "bbox_voxel": {}, "bbox_physical": {},
                    "touches_inferior": False, "touches_superior": False,
                    "touches_left": False, "touches_right": False,
                    "touches_anterior": False, "touches_posterior": False,
                },
                "components": {
                    "component_count": 1, "component_sizes": [100],
                    "component_volumes_mm3": [500.0],
                    "largest_component_fraction": 1.0, "small_fragments": [],
                    "fragmentation_index": 1.0,
                },
                "centroid": {"centroid_voxel": [1, 2, 3], "centroid_mm": [1.0, 2.0, 3.0]},
            },
        },
        "overlaps": [],
        "relationships": None,
    }


def test_ac12_render_with_block_includes_per_case_intensity_section():
    fb = _features_block()
    block = build_image_features_block({20: LI_20, 21: LI_21})
    text = render_feature_table(fb, image_features=block)
    assert "20" in text
    assert "21" in text
    assert _fmt(LI_20.mean) in text
    assert _fmt(LI_20.median) in text
    assert _fmt(LI_20.std) in text
    assert _fmt(LI_20.min) in text
    assert _fmt(LI_20.max) in text
    assert _fmt(LI_20.entropy) in text


def _fmt(value):
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}"


def test_ac12_render_without_image_features_is_byte_identical_to_prior_render():
    fb = _features_block()
    without_kw = render_feature_table(fb)
    with_explicit_none = render_feature_table(fb, image_features=None)
    assert without_kw == with_explicit_none
    # Sanity: the plain features-table sections are still present.
    assert "Per-label features:" in without_kw
    assert "Overlaps:" in without_kw
    assert "Relationships:" in without_kw
    assert "Intensity" not in without_kw


# =========================================================================== #
# AC13: rendered intensity section is null-safe and deterministic
# =========================================================================== #


def test_ac13_sentinel_label_renders_placeholder_not_none_or_nan():
    fb = _features_block()
    block = build_image_features_block({20: SENTINEL})
    text = render_feature_table(fb, image_features=block)
    assert "None" not in text
    assert "nan" not in text.lower()
    assert "n/a" in text.lower() or "(n/a)" in text


def test_ac13_unavailable_block_renders_explicit_placeholder_line():
    fb = _features_block()
    block = build_image_features_block({20: LI_20}, available=False)
    text = render_feature_table(fb, image_features=block)
    lowered = text.lower()
    assert "(unavailable)" in lowered or "(none)" in lowered
    assert "None" not in text
    assert "nan" not in lowered


def test_ac13_no_raw_python_internals_leak_and_labels_ascending():
    fb = _features_block()
    block = build_image_features_block({21: LI_21, 20: LI_20})
    text = render_feature_table(fb, image_features=block)
    for forbidden in ("frozenset(", "LabelIntensity", "tuple(", "<class"):
        assert forbidden not in text
    idx20 = text.index("20")
    idx21 = text.index("21")
    assert idx20 < idx21


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_intensity_mapping_yields_available_true_empty_per_label():
    block = build_image_features_block({})
    assert block["available"] is True
    assert block["per_label"] == {}
    json.dumps(block, allow_nan=False)  # must not raise


def test_adv_mixed_populated_and_sentinel_labels_serialise_and_order_correctly():
    block = build_image_features_block({20: LI_20, 99: SENTINEL})
    text = json.dumps(block, allow_nan=False)  # must not raise
    assert "NaN" not in text
    assert set(block["per_label"].keys()) == {"20", "99"}
    assert list(block["per_label"].keys()) == ["20", "99"]


def test_adv_extended_for_label_absent_from_intensity_is_ignored():
    block = build_image_features_block(
        {20: LI_20}, extended={20: {"a": 1.0}, 999: {"b": 2.0}},
    )
    assert set(block["per_label"].keys()) == {"20"}
    assert block["per_label"]["20"]["extended"] == {"a": 1.0}


def test_adv_extended_dict_is_shallow_copied_not_aliased():
    ext = {20: {"a": 1.0}}
    block = build_image_features_block({20: LI_20}, extended=ext)
    block["per_label"]["20"]["extended"]["a"] = 999.0
    assert ext[20]["a"] == 1.0


def test_adv_schema_round_trip_survives_json_dumps_loads_with_null_statistic():
    block = build_image_features_block({99: SENTINEL})
    round_tripped = json.loads(json.dumps(block))
    assert round_tripped == block
    assert round_tripped["per_label"]["99"]["first_order"]["mean"] is None

    verdict = _verdict()
    report = serialize_report(
        verdict, "case-061-roundtrip", bundled_default_config(), image_features=block,
    )  # must not raise -- null statistic still validates
    assert report["image_features"]["per_label"]["99"]["first_order"]["mean"] is None


def test_adv_back_compat_report_deep_equal_across_features_findings_combos():
    verdict = _verdict()
    config = bundled_default_config()
    fb = _features_block()
    r1 = serialize_report(verdict, "case-061-combo", config, features=fb)
    r2 = serialize_report(verdict, "case-061-combo", config, features=fb, image_features=None)
    assert r1 == r2
    assert "image_features" not in r1
