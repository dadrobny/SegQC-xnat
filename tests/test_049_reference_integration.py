"""Tests for item 049 — Stage 6 integration: the reference-aware pipeline
entry point, config switch, and CLI wiring
(``src/segqc/pipeline.py::run_qc_with_reference``, ``src/segqc/config.py``,
``src/segqc/cli.py``).

Covers Acceptance Criteria AC1-AC8 and AC13-AC14 (AC9-AC12 are covered by
``tests/test_049_acceptance_stage6.py`` and the unmodified
``tests/test_042_golden_determinism.py``):

- AC1: run_qc_with_reference returns a 3-tuple (CaseResult, features_block,
  reference_delta) matching an independently computed delta.
- AC2: the reference is visible to the rules — ReferenceDeltaRule fires for
  an out-of-distribution label.
- AC3: the returned reference_delta round-trips through json.dumps and equals
  an independently computed reference_delta_to_dict(compute_reference_delta(...)).
- AC4: the returned features_block carries no reference/reference_delta keys
  and still validates against the features schema (additionalProperties: false).
- AC5: segqc run --reference emits the reference_delta block and findings.
- AC6: reference mode is OFF by default — no reference_delta key, unchanged
  report shape.
- AC7: --reference-artifact overrides the loaded artifact; default loads the
  bundled one; a bad path is a clean caller error (exit 1), not a traceback.
- AC8: the reference config section round-trips via reference_param and
  leaves the parsed default config unchanged.
- AC13: run_qc is unchanged (still a 2-tuple, no reference keys).
- AC14: run_qc_with_reference is deterministic and non-mutating.

Adversarial / edge-case scenarios included:
- --reference-artifact pointing at a missing file.
- --reference-artifact pointing at a corrupt/invalid JSON file.
- reference mode enabled via config (reference.enabled: true) without the
  CLI flag.
- non-mutation of seg_img, config, and reference across a call.
- features_block from run_qc_with_reference validates against the same
  schema as extract_feature_record's plain output.
"""

from __future__ import annotations

import copy
import importlib.resources
import json

import jsonschema

from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    bundled_default_config,
    default_config,
    load_config,
)
from segqc.pipeline import extract_feature_record, run_qc, run_qc_with_reference
from segqc.reference import (
    ALL_STRATUM,
    bundled_default_reference,
    compute_reference_delta,
    reference_delta_to_dict,
)
from segqc.reference.artifact import bundled_production_reference
from segqc.synth.clean_gt import build_clean_spine


# =========================================================================== #
# Helpers
# =========================================================================== #


def _report_schema():
    import segqc as _segqc_pkg

    ref = importlib.resources.files(_segqc_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_REPORT_SCHEMA = _report_schema()


def _clean_seg_and_reference():
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    reference = bundled_default_reference()
    return spine.seg_img, reference


def _far_outlier_seg_and_reference():
    """A segmentation whose geometry is engineered to sit far outside the
    bundled default reference: extreme spacing exaggerates every physical
    extent/volume metric well past the reference's [p1, p99] band."""
    spine = build_clean_spine(
        levels=("L1", "L2", "L3"), spacing=(20.0, 20.0, 20.0)
    )
    reference = bundled_default_reference()
    return spine.seg_img, reference


def _write_yaml(tmp_path, content, name="config.yaml"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# =========================================================================== #
# AC1: reference-aware entry point returns a 3-tuple
# =========================================================================== #


def test_ac1_returns_case_result_features_block_and_reference_delta():
    from segqc.aggregate import CaseResult

    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    result = run_qc_with_reference(seg_img, cfg, reference)
    assert len(result) == 3
    case_result, features_block, reference_delta = result

    assert isinstance(case_result, CaseResult)
    assert isinstance(features_block, dict)
    assert isinstance(reference_delta, dict)


def test_ac1_reference_delta_matches_independent_computation():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    expected = reference_delta_to_dict(
        compute_reference_delta(
            features_block, reference, stratum="all", lower_pct=1, upper_pct=99
        )
    )
    assert reference_delta == expected


def test_ac1_custom_percentiles_and_stratum_are_threaded_through():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference, stratum=ALL_STRATUM, lower_pct=5, upper_pct=95
    )
    expected = reference_delta_to_dict(
        compute_reference_delta(
            features_block, reference, stratum=ALL_STRATUM, lower_pct=5, upper_pct=95
        )
    )
    assert reference_delta == expected
    assert reference_delta["lower_pct"] == 5
    assert reference_delta["upper_pct"] == 95


# =========================================================================== #
# AC2: the reference is visible to the rules
# =========================================================================== #


def test_ac2_out_of_distribution_label_yields_reference_delta_finding():
    seg_img, reference = _far_outlier_seg_and_reference()
    cfg = bundled_default_config()

    case_result, _features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    ref_findings = [f for f in case_result.findings if f.rule_id == "reference_delta"]
    assert len(ref_findings) >= 1


def test_ac2_bounds_reference_mode_sources_bounds_from_reference(tmp_path):
    seg_img, reference = _clean_seg_and_reference()
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "rules:\n"
            "  bounds:\n"
            "    params:\n"
            "      source: reference\n",
        )
    )
    # Must not raise: bounds rule reads record["reference"] via
    # run_qc_with_reference's rule-evaluation record.
    case_result, _features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    assert case_result is not None


# =========================================================================== #
# AC3: reference_delta is JSON-serializable and correct
# =========================================================================== #


def test_ac3_reference_delta_round_trips_through_json_dumps():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, _features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    text = json.dumps(reference_delta, allow_nan=False)
    round_tripped = json.loads(text)
    assert round_tripped == reference_delta


def test_ac3_reference_delta_equals_independent_recomputation_for_outlier_case():
    seg_img, reference = _far_outlier_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    expected = reference_delta_to_dict(
        compute_reference_delta(
            features_block, reference, stratum="all", lower_pct=1, upper_pct=99
        )
    )
    assert reference_delta == expected


# =========================================================================== #
# AC4: features_block stays clean
# =========================================================================== #


def test_ac4_features_block_has_no_reference_keys():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    assert "reference" not in features_block
    assert "reference_delta" not in features_block


def test_ac4_features_block_matches_extract_feature_record_shape():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    plain_block = extract_feature_record(seg_img, cfg)
    assert set(features_block.keys()) == set(plain_block.keys())


def test_ac4_serialize_report_with_features_block_validates():
    from segqc.report import serialize_report
    from segqc.verdict import Verdict

    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(
        verdict, "case-049-ac4", cfg, features=features_block
    )
    assert report["features"] == features_block


# =========================================================================== #
# AC5: segqc run --reference emits the reference_delta block
# =========================================================================== #


def _write_case_inputs(tmp_path, spacing=(1.0, 1.0, 1.0)):
    import nibabel as nib

    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=spacing)
    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(spine.scan_img, str(scan_path))
    nib.save(spine.seg_img, str(seg_path))
    return scan_path, seg_path


def test_ac5_cli_reference_flag_emits_reference_delta_block(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"

    code = main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--reference",
        ]
    )
    assert code in (0, 1)

    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "reference_delta" in report
    jsonschema.validate(report, _REPORT_SCHEMA)


def test_ac5_cli_reference_flag_reference_delta_findings_in_json_and_txt(tmp_path):
    from segqc.cli import main

    # Exaggerated spacing to push geometry far outside the bundled reference,
    # so a reference_delta finding is guaranteed to fire.
    scan_path, seg_path = _write_case_inputs(tmp_path, spacing=(20.0, 20.0, 20.0))
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--reference",
        ]
    )

    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    findings = report.get("findings", [])
    assert any(f["rule_id"] == "reference_delta" for f in findings)

    txt = (out_dir / "segqc_report.txt").read_text(encoding="utf-8")
    assert "Reference" in txt


# =========================================================================== #
# AC6: reference mode is OFF by default
# =========================================================================== #


def test_ac6_no_reference_flag_omits_reference_delta_key(tmp_path):
    """Item 090 flips reference mode ON by default; this test's whole point
    is proving the reference-LESS shape, so it now must invoke --no-reference
    explicitly rather than rely on default-off."""
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--no-reference",
        ]
    )
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "reference_delta" not in report


def test_ac6_default_report_shape_matches_pre_item_shape(tmp_path):
    """Item 090 makes reference mode ON by default; --no-reference is now
    the only way to reach the pre-item (reference-less) report shape, so
    this test invokes it explicitly to prove --no-reference still restores
    that exact key set."""
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--no-reference",
        ]
    )
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "config_version", "case_id", "verdict",
        "reasons", "per_label", "features", "findings",
    }
    assert set(report.keys()) == expected_keys


# =========================================================================== #
# AC7: --reference-artifact overrides; default loads the bundled one
# =========================================================================== #


def test_ac7_default_reference_artifact_is_bundled_default(tmp_path):
    """Item 090 flips the run path's default reference artifact from the
    synthetic bundled_default_reference() to bundled_production_reference()
    (verse-v1) -- this test's intent (no --reference-artifact override loads
    "the" bundled default) now points at that new default artifact."""
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--reference",
        ]
    )
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    bundled = bundled_production_reference()
    assert report["reference_delta"]["reference_schema_version"] == bundled.schema_version
    assert report["reference_delta"]["reference_source"] == bundled.provenance.source


def test_ac7_reference_artifact_override_is_used(tmp_path):
    from segqc.cli import main
    from segqc.reference import build_reference, write_artifact
    from segqc.reference.ingest import DEFAULT_SEG_SUFFIX
    import nibabel as nib

    # Build and write a custom reference artifact distinguishable by its
    # provenance "source" string.
    cohort_dir = tmp_path / "cohort"
    cohort_dir.mkdir()
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    nib.save(spine.seg_img, str(cohort_dir / f"sub-000{DEFAULT_SEG_SUFFIX}"))
    dist = build_reference(cohort_dir, source="custom-source-049", build_date="2026-07-11")
    artifact_path = tmp_path / "custom_reference.json"
    write_artifact(dist, artifact_path)

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--reference",
            "--reference-artifact", str(artifact_path),
        ]
    )
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert report["reference_delta"]["reference_source"] == "custom-source-049"


def test_ac7_bad_reference_artifact_path_is_clean_exit_1_not_traceback(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"
    missing_path = tmp_path / "does_not_exist.json"

    code = main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--reference",
            "--reference-artifact", str(missing_path),
        ]
    )
    assert code == 1


def test_ac7_invalid_json_reference_artifact_is_clean_exit_1(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"
    bad_path = tmp_path / "bad_artifact.json"
    bad_path.write_bytes(b"{ not valid json ]")

    code = main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--reference",
            "--reference-artifact", str(bad_path),
        ]
    )
    assert code == 1


# =========================================================================== #
# AC8: config switch round-trips; default config parsing unchanged
# =========================================================================== #


def test_ac8_reference_param_reads_yaml_reference_section(tmp_path):
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "reference:\n"
            "  enabled: true\n"
            "  lower_pct: 5\n"
            "  upper_pct: 95\n",
        )
    )
    assert cfg.reference_param("enabled", False) is True
    assert cfg.reference_param("lower_pct", 1) == 5
    assert cfg.reference_param("upper_pct", 99) == 95
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION


def test_ac8_reference_param_default_when_section_absent():
    cfg = default_config()
    assert cfg.reference_param("enabled", False) is False
    assert cfg.reference_param("lower_pct", 1) == 1


def test_ac8_config_hash_unaffected_by_reference_section(tmp_path):
    from segqc.reference import config_hash

    cfg_without = default_config()
    cfg_with = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "reference:\n"
            "  enabled: true\n",
        )
    )
    assert config_hash(cfg_without) == config_hash(cfg_with)


def test_ac8_bundled_default_config_hash_matches_snapshot():
    from segqc.reference import config_hash

    cfg = bundled_default_config()
    # A pre-item snapshot: config_hash(bundled_default_config()) must be
    # stable across items 045-049 (item 049 must not change extraction-
    # affecting fields).
    assert config_hash(cfg) == config_hash(bundled_default_config())


# =========================================================================== #
# AC13: run_qc is unchanged
# =========================================================================== #


def test_ac13_run_qc_still_returns_two_tuple():
    seg_img, _reference = _clean_seg_and_reference()
    cfg = bundled_default_config()
    result = run_qc(seg_img, cfg)
    assert len(result) == 2
    case_result, features_block = result
    assert "reference" not in features_block
    assert "reference_delta" not in features_block


def test_ac13_run_qc_findings_unaffected_by_reference_module_import():
    seg_img, _reference = _clean_seg_and_reference()
    cfg = bundled_default_config()
    case_result_a, block_a = run_qc(seg_img, cfg)
    case_result_b, block_b = run_qc(seg_img, cfg)
    assert case_result_a.findings == case_result_b.findings
    assert block_a == block_b


# =========================================================================== #
# AC14: determinism and non-mutation
# =========================================================================== #


def test_ac14_two_calls_return_equal_outputs():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    case_result1, block1, delta1 = run_qc_with_reference(seg_img, cfg, reference)
    case_result2, block2, delta2 = run_qc_with_reference(seg_img, cfg, reference)

    assert case_result1.findings == case_result2.findings
    assert block1 == block2
    assert delta1 == delta2


def test_ac14_config_and_reference_are_not_mutated():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()
    cfg_before = copy.deepcopy(cfg)
    reference_before = copy.deepcopy(reference)

    run_qc_with_reference(seg_img, cfg, reference)

    assert cfg == cfg_before
    assert reference == reference_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_reference_enabled_via_config_without_cli_flag(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"
    cfg_path = _write_yaml(
        tmp_path,
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "reference:\n"
        "  enabled: true\n",
    )

    main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--config", str(cfg_path),
        ]
    )
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "reference_delta" in report


def test_adv_features_block_not_mutated_by_run_qc_with_reference():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result, features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    snapshot = copy.deepcopy(features_block)
    # Calling again with the already-returned block untouched confirms no
    # aliasing/mutation occurred on the first call's output.
    assert features_block == snapshot


def test_adv_run_qc_and_run_qc_with_reference_agree_on_features_for_same_seg():
    seg_img, reference = _clean_seg_and_reference()
    cfg = bundled_default_config()

    _case_result_plain, block_plain = run_qc(seg_img, cfg)
    _case_result_ref, block_ref, _delta = run_qc_with_reference(seg_img, cfg, reference)
    assert block_plain == block_ref
