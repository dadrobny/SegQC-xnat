"""Tests for the Stage-7 evaluation report (JSON + human) and calibrated-
config recording (item 056 -- rendering item 054's ``CohortMetrics`` and item
055's ``CalibrationResult`` into a versioned, schema-validated JSON report, a
stdlib-only plain-text rendering, and a byte-reproducible calibrated-config
writer).

Covers all seventeen Acceptance Criteria plus adversarial and edge-case
inputs. ``segqc.eval.report`` does not exist yet at the time this file is
written; its names are imported **locally inside each test function**
(mirroring ``tests/test_054_metrics.py`` / ``tests/test_055_calibrate.py``'s
treatment of their then-new modules) so the file can still be collected
before the module is implemented. Names from the already-merged
``segqc.eval.harness``/``segqc.eval.metrics``/``segqc.eval.calibrate`` and
``segqc.config`` modules (items 053/054/055/005) are imported at the top of
the file as usual.

Every ``CohortMetrics`` fixture is a **hand-built** cohort assembled entirely
in memory via the ``_outcome``/``_case``/``_cohort`` factories (identical to
``tests/test_054_metrics.py``'s own factories) fed through the real
``compute_cohort_metrics`` -- no pipeline, no rule evaluation, no label-map
or file I/O. Every ``CalibrationResult`` fixture is likewise hand-built (one
``CandidateResult`` wrapping a real ``CohortMetrics``), following
``tests/test_055_calibrate.py``'s own hand-built-``CohortMetrics`` technique
for objective-level tests, since this module only needs a well-formed
``CalibrationResult`` shape -- not a real grid sweep.

Calls to ``build_evaluation_report``/``render_evaluation_report`` pass
``provenance``/``calibration`` as keyword arguments throughout, which is
compatible regardless of whether the implementation makes ``provenance``
positional-or-keyword or keyword-only (both spec sections in item 056 use
slightly different notations for the same signature).

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services, no wall clock).
"""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest

from segqc.config import default_config, default_config_path, load_config
from segqc.eval.calibrate import (
    CalibrationObjective,
    CalibrationResult,
    CandidateResult,
    ThresholdAxis,
)
from segqc.eval.feature_match import FeatureMatchResult
from segqc.eval.harness import CaseEvaluation, CohortEvaluation
from segqc.eval.metrics import CohortMetrics, compute_cohort_metrics
from segqc.eval.outcome import CaseOutcome, Outcome
from segqc.eval.overlap import OverlapResult
from segqc.io import SegQCInputError


# =========================================================================== #
# Fixture factories (mirrors tests/test_054_metrics.py / test_055_calibrate.py)
# =========================================================================== #


def _outcome(**kwargs) -> CaseOutcome:
    """Build a CaseOutcome with every field defaulted (a clean TN), overridable
    by keyword -- identical to test_054/test_055's own factory."""
    expected_failure = kwargs.get("expected_failure", False)
    actual_flagged = kwargs.get("actual_flagged", False)
    fields = dict(
        outcome=Outcome.from_flags(expected_failure, actual_flagged),
        expected_verdict="fail" if expected_failure else "pass",
        actual_verdict="fail" if actual_flagged else "pass",
        expected_failure=expected_failure,
        actual_flagged=actual_flagged,
        caught=(actual_flagged if expected_failure else None),
        failure_mode=None,
        failure_mode_name=None,
        expected_rule_ids=(),
        expected_labels=(),
        fired_rule_ids=(),
        designated_rule_fired=False,
        caught_by_designated_rule=False,
    )
    fields.update(kwargs)
    return CaseOutcome(**fields)


def _case(outcome_kwargs, dice=None, divergence=None, case_id="c") -> CaseEvaluation:
    """Build one CaseEvaluation: a CaseOutcome from ``outcome_kwargs``, an
    optional OverlapResult (``dice``), and an optional FeatureMatchResult
    (``case_divergence=divergence``) -- identical to test_054's factory."""
    outcome = _outcome(**outcome_kwargs)

    overlap = None
    if dice is not None:
        overlap = OverlapResult(
            per_label=(),
            mean_dice=dice,
            volume_weighted_dice=dice,
            mean_jaccard=None,
            n_matched=1,
            n_unmatched=0,
        )

    feature_match = None
    if divergence is not None:
        feature_match = FeatureMatchResult(
            per_label=(),
            case_divergence=divergence,
            mean_centroid_distance_mm=None,
            n_matched=1,
            n_unmatched=0,
        )

    candidate_present = dice is not None or divergence is not None
    return CaseEvaluation(
        case_id=case_id,
        outcome=outcome,
        overlap=overlap,
        feature_match=feature_match,
        candidate_present=candidate_present,
        subject="candidate" if candidate_present else "gt",
        metadata=None,
    )


def _cohort(cases) -> CohortEvaluation:
    return CohortEvaluation(cases=tuple(cases))


def _basic_cases():
    """A small, non-degenerate cohort: 1 TN, 1 FP, 1 TP of mode 1 -- FPR ==
    0.5, overall sensitivity == 1.0, one per-mode entry (sensitivity 1.0),
    and a defined (non-None, non-zero-variance) dice_vs_flag correlation."""
    return [
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=0.9,
            divergence=0.1,
            case_id="tn0",
        ),
        _case(
            {"expected_failure": False, "actual_flagged": True},
            dice=0.3,
            divergence=0.8,
            case_id="fp0",
        ),
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 1,
                "failure_mode_name": "mode-one",
                "caught": True,
                "caught_by_designated_rule": True,
            },
            dice=0.2,
            divergence=0.9,
            case_id="tp0",
        ),
    ]


def _basic_metrics() -> CohortMetrics:
    return compute_cohort_metrics(_cohort(_basic_cases()))


def _none_sentinel_cases():
    """A cohort with only expected-failure records, both at identical DICE ->
    false_positive_rate is None (no expected-pass cases) AND dice_vs_flag's
    coefficient is None (zero x-variance), exercising both item-054 sentinels
    item 056's renderer must handle (AC11)."""
    return [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 2,
                "failure_mode_name": "mode-two",
                "caught": True,
                "caught_by_designated_rule": True,
            },
            dice=0.5,
            case_id="tp0",
        ),
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 2,
                "failure_mode_name": "mode-two",
                "caught": True,
                "caught_by_designated_rule": True,
            },
            dice=0.5,
            case_id="tp1",
        ),
    ]


def _provenance(metrics, config, build_date="2026-07-11", cohort_id="cohort-a"):
    from segqc.eval.report import EvaluationProvenance

    return EvaluationProvenance(
        cohort_id=cohort_id,
        cohort_size=metrics.n_cases,
        config_version=config.schema_version,
        build_date=build_date,
    )


def _calibration_result(metrics, assignment=None, feasible=True) -> CalibrationResult:
    """A minimal, well-formed CalibrationResult wrapping a real CohortMetrics
    as the (only) candidate's/best's metrics -- built by hand rather than via
    a real calibrate_thresholds sweep, since this module only needs a
    well-formed shape (mirrors test_055's hand-built-CohortMetrics objective
    tests)."""
    assignment = dict(assignment) if assignment is not None else {"k": 2.5}
    score = metrics.false_positive_rate if metrics.false_positive_rate is not None else 0.0
    candidate = CandidateResult(
        assignment=assignment,
        metrics=metrics,
        feasible=feasible,
        score=score,
        grid_index=0,
    )
    return CalibrationResult(
        candidates=(candidate,),
        best=(candidate if feasible else None),
        feasible=feasible,
        status=("ok" if feasible else "no-feasible-setting"),
        objective=CalibrationObjective(),
        n_candidates=1,
    )


def _appears_numeric(text: str, value) -> bool:
    """True if *value* (a float or None) is reproduced somewhere in *text*,
    tolerant of fraction vs percentage formatting at several precisions.
    ``None`` is expected to render as the literal ``"n/a"``."""
    if value is None:
        return "n/a" in text
    candidates = set()
    for ndigits in (0, 1, 2, 3, 4):
        candidates.add(f"{value:.{ndigits}f}")
        candidates.add(f"{value * 100:.{ndigits}f}")
    return any(candidate in text for candidate in candidates)


def _load_eval_schema() -> dict:
    import importlib.resources as pkg_resources

    import segqc.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("eval_report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


# =========================================================================== #
# AC1: a versioned evaluation-report schema ships as package data
# =========================================================================== #


def test_ac1_schema_loadable_via_importlib_resources_with_version_and_required_keys():
    """AC1: eval_report_schema_v0.json lives alongside segqc.eval, loads via
    importlib.resources, declares schema_version const '0.1', and requires
    schema_version/provenance/metrics."""
    schema = _load_eval_schema()

    assert schema["properties"]["schema_version"]["const"] == "0.1"
    assert set(schema["required"]) >= {"schema_version", "provenance", "metrics"}


def test_ac1_public_names_reexported_from_eval_package():
    """AC1 (Implementation Step 9): the module's public names, including the
    EVAL_REPORT_SCHEMA_VERSION constant, are re-exported from segqc.eval."""
    from segqc.eval import (  # noqa: F401
        EVAL_REPORT_SCHEMA_VERSION,
        EvaluationProvenance,
        build_evaluation_report,
        record_calibrated_config,
        render_evaluation_report,
        serialize_evaluation_report_json,
        write_evaluation_report,
    )
    from segqc.eval.report import build_evaluation_report as direct

    assert EVAL_REPORT_SCHEMA_VERSION == "0.1"
    assert build_evaluation_report is direct


# =========================================================================== #
# AC2: build_evaluation_report bundles metrics + provenance into a schema-
# valid dict
# =========================================================================== #


def test_ac2_build_evaluation_report_bundles_metrics_and_provenance():
    """AC2: schema_version == '0.1', a provenance block, metrics ==
    metrics.to_dict(), and no raise (validated inside the call)."""
    from segqc.eval.report import build_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)

    report = build_evaluation_report(metrics, provenance=provenance)

    assert report["schema_version"] == "0.1"
    assert isinstance(report["provenance"], dict)
    assert report["metrics"] == metrics.to_dict()


# =========================================================================== #
# AC3: the calibration block is optional
# =========================================================================== #


def test_ac3_calibration_block_present_when_supplied_absent_when_omitted():
    """AC3: with a CalibrationResult -> 'calibration' key present; with
    calibration=None (the default) -> no 'calibration' key; both validate."""
    from segqc.eval.report import build_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    calibration = _calibration_result(metrics, assignment={"k": 2.5})

    with_calibration = build_evaluation_report(
        metrics, provenance=provenance, calibration=calibration
    )
    without_calibration = build_evaluation_report(metrics, provenance=provenance)

    assert "calibration" in with_calibration
    assert "calibration" not in without_calibration


# =========================================================================== #
# AC4: provenance is captured and cohort size is consistent
# =========================================================================== #


def test_ac4_provenance_cohort_size_and_config_version_consistent():
    """AC4: provenance carries cohort_id/cohort_size/config_version/build_date;
    cohort_size == metrics.n_cases; config_version == config.schema_version."""
    from segqc.eval.report import build_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config, cohort_id="cohort-verse-mini")

    report = build_evaluation_report(metrics, provenance=provenance)

    prov = report["provenance"]
    assert prov["cohort_id"] == "cohort-verse-mini"
    assert prov["cohort_size"] == metrics.n_cases == 3
    assert prov["config_version"] == config.schema_version
    assert prov["build_date"] == "2026-07-11"


# =========================================================================== #
# AC5: build_date is caller-supplied, never wall-clock
# =========================================================================== #


def test_ac5_identical_inputs_yield_equal_build_date_and_equal_reports():
    """AC5: two builds with the same inputs (same build_date) yield equal
    provenance.build_date and equal reports overall."""
    from segqc.eval.report import build_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config, build_date="2020-01-01")

    report_a = build_evaluation_report(metrics, provenance=provenance)
    report_b = build_evaluation_report(metrics, provenance=provenance)

    assert report_a["provenance"]["build_date"] == "2020-01-01"
    assert report_a == report_b


def test_ac5_module_source_reads_no_wall_clock():
    """AC5: segqc.eval.report never calls date.today()/datetime.now()."""
    import inspect

    import segqc.eval.report as report_mod

    source = inspect.getsource(report_mod)
    assert "date.today(" not in source
    assert "datetime.now(" not in source


# =========================================================================== #
# AC6: the report exposes the three headline metrics
# =========================================================================== #


def test_ac6_headline_metrics_reachable_and_equal_cohort_metrics_fields():
    """AC6: FPR, per-mode sensitivity, and DICE-vs-flag correlation are
    reachable under 'metrics' and equal the CohortMetrics fields."""
    from segqc.eval.report import build_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)

    report = build_evaluation_report(metrics, provenance=provenance)

    assert report["metrics"]["false_positive_rate"] == metrics.false_positive_rate
    assert (
        report["metrics"]["per_mode"][0]["sensitivity"] == metrics.per_mode[0].sensitivity
    )
    assert (
        report["metrics"]["dice_vs_flag"]["coefficient"] == metrics.dice_vs_flag.coefficient
    )


# =========================================================================== #
# AC7: the report exposes the chosen thresholds when calibrated
# =========================================================================== #


def test_ac7_calibration_block_exposes_best_assignment_metrics_and_status():
    """AC7: a feasible CalibrationResult's chosen assignment, achieved
    metrics, and status == 'ok' all surface under 'calibration'."""
    from segqc.eval.report import build_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    calibration = _calibration_result(
        metrics, assignment={"reference_delta.max_robust_z": 3.0}
    )

    report = build_evaluation_report(
        metrics, provenance=provenance, calibration=calibration
    )

    cal_block = report["calibration"]
    assert cal_block["status"] == "ok"
    assert cal_block["best"]["assignment"] == {"reference_delta.max_robust_z": 3.0}
    assert cal_block["best"]["metrics"] == metrics.to_dict()


# =========================================================================== #
# AC8: schema validation rejects a malformed report
# =========================================================================== #


@pytest.mark.parametrize("required_field", ["schema_version", "provenance", "metrics"])
def test_ac8_schema_validation_rejects_report_missing_a_required_key(required_field):
    """AC8: deleting a required top-level key from a built report dict and
    re-validating raises jsonschema.ValidationError."""
    from segqc.eval.report import build_evaluation_report

    schema = _load_eval_schema()
    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    report = build_evaluation_report(metrics, provenance=provenance)
    del report[required_field]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


# =========================================================================== #
# AC9: JSON serialisation is deterministic / byte-reproducible
# =========================================================================== #


def test_ac9_serialize_json_repeated_calls_produce_identical_text():
    """AC9: serialize_evaluation_report_json is deterministic across calls."""
    from segqc.eval.report import build_evaluation_report, serialize_evaluation_report_json

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    report = build_evaluation_report(metrics, provenance=provenance)

    text_a = serialize_evaluation_report_json(report)
    text_b = serialize_evaluation_report_json(report)

    assert text_a == text_b
    assert isinstance(text_a, str)


def test_ac9_written_artifact_has_single_trailing_newline_and_round_trips(tmp_path):
    """AC9: the written JSON artifact ends in exactly one '\\n' and round-trips
    through json.loads back to the built dict."""
    from segqc.eval.report import build_evaluation_report, write_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    report = build_evaluation_report(metrics, provenance=provenance)

    out_path = write_evaluation_report(report, tmp_path / "report.json")
    raw = out_path.read_bytes()
    text = raw.decode("utf-8")

    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert json.loads(text) == report


def test_ac9_two_writes_of_the_same_report_are_byte_identical(tmp_path):
    """AC9: writing the same report to two distinct paths yields byte-
    identical files."""
    from segqc.eval.report import build_evaluation_report, write_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    report = build_evaluation_report(metrics, provenance=provenance)

    path_a = write_evaluation_report(report, tmp_path / "a.json")
    path_b = write_evaluation_report(report, tmp_path / "b.json")

    assert path_a.read_bytes() == path_b.read_bytes()


# =========================================================================== #
# AC10: a human-readable rendering reproduces the same numbers
# =========================================================================== #


def test_ac10_human_rendering_reproduces_same_numbers_and_no_raw_internals():
    """AC10: the rendered text reproduces FPR/per-mode sensitivity/DICE-vs-
    flag correlation and the chosen assignment, and contains no raw class
    names/dataclass reprs/enum reprs."""
    from segqc.eval.report import render_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    calibration = _calibration_result(
        metrics, assignment={"reference_delta.max_robust_z": 3.0}
    )

    text = render_evaluation_report(
        metrics, provenance=provenance, calibration=calibration
    )

    assert isinstance(text, str)
    assert len(text) > 0
    assert _appears_numeric(text, metrics.false_positive_rate)
    assert _appears_numeric(text, metrics.per_mode[0].sensitivity)
    assert _appears_numeric(text, metrics.dice_vs_flag.coefficient)
    assert "reference_delta.max_robust_z" in text

    for forbidden in (
        "CohortMetrics(",
        "PerModeSensitivity(",
        "CorrelationResult(",
        "Outcome.",
        "frozenset",
        "object at 0x",
    ):
        assert forbidden not in text


# =========================================================================== #
# AC11: the human renderer handles None metric sentinels
# =========================================================================== #


def test_ac11_none_metric_sentinels_render_as_na_not_none_string():
    """AC11: a None FPR and a None correlation coefficient render as 'n/a',
    never the literal string 'None', and no raise."""
    from segqc.eval.report import render_evaluation_report

    metrics = compute_cohort_metrics(_cohort(_none_sentinel_cases()))
    assert metrics.false_positive_rate is None
    assert metrics.dice_vs_flag.coefficient is None

    config = default_config()
    provenance = _provenance(metrics, config)

    text = render_evaluation_report(metrics, provenance=provenance)

    assert "n/a" in text
    assert "None" not in text


# =========================================================================== #
# AC12: recording writes calibrated thresholds into a config that round-trips
# =========================================================================== #


def test_ac12_record_calibrated_config_round_trips_through_load_config(tmp_path):
    """AC12: load_config(path) yields a config whose swept param equals the
    chosen value and whose other fields equal base_config's."""
    from segqc.eval.report import record_calibrated_config

    base_config = default_config()
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5, 3.5)
    )
    metrics = _basic_metrics()
    calibration = _calibration_result(metrics, assignment={"k": 2.5})

    out_path = record_calibrated_config(
        base_config, calibration, (axis,), tmp_path / "calibrated.yaml"
    )
    loaded = load_config(out_path)

    assert loaded.rule_param("reference_delta", "max_robust_z", None) == 2.5
    assert loaded.schema_version == base_config.schema_version
    assert loaded.min_foreground_voxels == base_config.min_foreground_voxels
    assert loaded.min_label_count == base_config.min_label_count
    assert loaded.min_fragment_voxels == base_config.min_fragment_voxels
    assert loaded.verdict == base_config.verdict
    assert loaded.reference == base_config.reference


# =========================================================================== #
# AC13: recording is byte-reproducible
# =========================================================================== #


def test_ac13_recording_to_two_paths_is_byte_identical(tmp_path):
    """AC13: writing the same calibrated config to two paths yields byte-
    identical files ending in '\\n'."""
    from segqc.eval.report import record_calibrated_config

    base_config = default_config()
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5, 3.5)
    )
    metrics = _basic_metrics()
    calibration = _calibration_result(metrics, assignment={"k": 2.5})

    path_a = record_calibrated_config(base_config, calibration, (axis,), tmp_path / "a.yaml")
    path_b = record_calibrated_config(base_config, calibration, (axis,), tmp_path / "b.yaml")

    bytes_a = path_a.read_bytes()
    assert bytes_a == path_b.read_bytes()
    assert bytes_a.endswith(b"\n")
    assert not bytes_a.endswith(b"\n\n")


# =========================================================================== #
# AC14: recording does not mutate inputs and does not touch shipped artifacts
# =========================================================================== #


def test_ac14_recording_does_not_mutate_inputs_or_touch_shipped_default(tmp_path):
    """AC14: base_config/calibration_result/axes unchanged after the call;
    the bundled default_config.yaml is byte-unchanged."""
    from segqc.eval.report import record_calibrated_config

    base_config = default_config()
    base_before = copy.deepcopy(base_config)
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5, 3.5)
    )
    axes = (axis,)
    axes_before = copy.deepcopy(axes)
    metrics = _basic_metrics()
    calibration = _calibration_result(metrics, assignment={"k": 2.5})
    calibration_before = copy.deepcopy(calibration)

    shipped_path = default_config_path()
    shipped_before = shipped_path.read_bytes()

    record_calibrated_config(base_config, calibration, axes, tmp_path / "out.yaml")

    assert base_config == base_before
    assert axes == axes_before
    assert calibration == calibration_before
    assert shipped_path.read_bytes() == shipped_before


# =========================================================================== #
# AC15: "no feasible setting" is handled explicitly, not written blindly
# =========================================================================== #


def test_ac15_no_feasible_best_raises_segqc_input_error_and_writes_nothing(tmp_path):
    """AC15: calibration_result.best is None -> SegQCInputError, and no file
    is written at path."""
    from segqc.eval.report import record_calibrated_config

    base_config = default_config()
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5, 3.5)
    )
    metrics = _basic_metrics()
    infeasible = _calibration_result(metrics, assignment={"k": 2.5}, feasible=False)
    assert infeasible.best is None
    assert infeasible.status == "no-feasible-setting"

    out_path = tmp_path / "out.yaml"
    with pytest.raises(SegQCInputError):
        record_calibrated_config(base_config, infeasible, (axis,), out_path)

    assert not out_path.exists()


# =========================================================================== #
# AC16: the module edits no living documents
# =========================================================================== #


def test_ac16_module_source_has_no_progress_or_roadmap_references():
    """AC16: segqc.eval.report contains no reference to progress.md or
    roadmap.md."""
    import inspect

    import segqc.eval.report as report_mod

    source = inspect.getsource(report_mod)
    assert "progress.md" not in source
    assert "roadmap.md" not in source


def test_ac16_build_and_render_write_nothing_to_disk(tmp_path):
    """AC16: build_evaluation_report/render_evaluation_report perform no file
    I/O -- a tmp_path directory stays empty across both calls."""
    from segqc.eval.report import build_evaluation_report, render_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)

    build_evaluation_report(metrics, provenance=provenance)
    render_evaluation_report(metrics, provenance=provenance)

    assert list(tmp_path.iterdir()) == []


# =========================================================================== #
# AC17: any committed report/config fixture is LF-pinned
# =========================================================================== #


def test_ac17_no_committed_golden_fixture_or_it_is_lf_pinned_in_gitattributes():
    """AC17: this suite commits no golden evaluation-report/config fixture
    (every artifact here is written under pytest's tmp_path); if a future
    change under tests/ introduces one for this item, it must be pinned
    'text eol=lf' in .gitattributes per the CLAUDE.md determinism gotcha."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    gitattributes_text = (repo_root / ".gitattributes").read_text(encoding="utf-8")

    candidate_dirs = [
        repo_root / "tests" / "fixtures" / "eval_report",
        repo_root / "tests" / "golden" / "eval_report",
        repo_root / "tests" / "corpus" / "golden" / "eval_report",
    ]
    for directory in candidate_dirs:
        if not directory.exists():
            continue
        for fixture_path in directory.rglob("*"):
            if fixture_path.is_file():
                rel = fixture_path.relative_to(repo_root).as_posix()
                assert rel in gitattributes_text or "eval_report" in gitattributes_text, (
                    f"Committed golden fixture {rel} must be LF-pinned in "
                    ".gitattributes"
                )


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_empty_cohort_builds_validates_renders_and_serialises(tmp_path):
    """An empty cohort (n_cases == 0, all-None sentinel metrics) still builds,
    validates, renders, and serialises without crashing."""
    from segqc.eval.report import (
        build_evaluation_report,
        render_evaluation_report,
        serialize_evaluation_report_json,
        write_evaluation_report,
    )

    metrics = compute_cohort_metrics(_cohort([]))
    config = default_config()
    provenance = _provenance(metrics, config)

    report = build_evaluation_report(metrics, provenance=provenance)  # must not raise
    text = render_evaluation_report(metrics, provenance=provenance)  # must not raise
    json_text = serialize_evaluation_report_json(report)
    written = write_evaluation_report(report, tmp_path / "empty.json")

    assert report["provenance"]["cohort_size"] == 0
    assert isinstance(text, str) and len(text) > 0
    assert json.loads(json_text) == report
    assert written.exists()


def test_adversarial_per_mode_zero_cases_renders_cleanly():
    """A requested per-mode entry with n_cases == 0 (sensitivity is None per
    item 054's sentinel) renders as 'n/a', not a crash or 'None'."""
    from segqc.eval.report import render_evaluation_report

    metrics = compute_cohort_metrics(_cohort([]), failure_modes=[9])
    assert metrics.per_mode[0].n_cases == 0
    assert metrics.per_mode[0].sensitivity is None

    config = default_config()
    provenance = _provenance(metrics, config)

    text = render_evaluation_report(metrics, provenance=provenance)

    assert "n/a" in text
    assert "None" not in text


def test_adversarial_report_without_calibration_renders_not_calibrated_marker():
    """A report built without a calibration argument still renders a
    calibration section reading something like '(not calibrated)'."""
    from segqc.eval.report import render_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)

    text = render_evaluation_report(metrics, provenance=provenance)

    assert "calibrat" in text.lower()


def test_adversarial_provenance_optional_fields_default_none_and_settable():
    """EvaluationProvenance's optional reference_schema_version/segqc_version
    default to None and are carried through to_dict() when supplied."""
    from segqc.eval.report import EvaluationProvenance

    minimal = EvaluationProvenance(
        cohort_id="c", cohort_size=0, config_version="0.1", build_date="2026-01-01"
    )
    assert minimal.reference_schema_version is None
    assert minimal.segqc_version is None
    assert minimal.to_dict()["cohort_id"] == "c"

    full = EvaluationProvenance(
        cohort_id="c",
        cohort_size=0,
        config_version="0.1",
        build_date="2026-01-01",
        reference_schema_version="0.2",
        segqc_version="1.2.3",
    )
    assert full.reference_schema_version == "0.2"
    assert full.segqc_version == "1.2.3"


def test_adversarial_write_evaluation_report_creates_parent_directories(tmp_path):
    """write_evaluation_report creates missing parent directories (mirrors
    segqc.reference.artifact.write_artifact)."""
    from segqc.eval.report import build_evaluation_report, write_evaluation_report

    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    report = build_evaluation_report(metrics, provenance=provenance)

    nested = tmp_path / "a" / "b" / "c" / "report.json"
    written = write_evaluation_report(report, nested)

    assert written.exists()
    assert written == nested


def test_adversarial_record_calibrated_config_creates_parent_directories(tmp_path):
    """record_calibrated_config creates missing parent directories for its
    output path."""
    from segqc.eval.report import record_calibrated_config

    base_config = default_config()
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5,)
    )
    metrics = _basic_metrics()
    calibration = _calibration_result(metrics, assignment={"k": 2.5})

    nested = tmp_path / "x" / "y" / "calibrated.yaml"
    out_path = record_calibrated_config(base_config, calibration, (axis,), nested)

    assert out_path.exists()
    assert out_path == nested


def test_adversarial_malformed_report_dict_wrong_type_rejected_by_schema():
    """A report dict whose 'metrics' value is the wrong JSON type (a string
    instead of an object) still fails validation against the bundled
    schema -- schema strictness is not limited to missing-key checks."""
    from segqc.eval.report import build_evaluation_report

    schema = _load_eval_schema()
    metrics = _basic_metrics()
    config = default_config()
    provenance = _provenance(metrics, config)
    report = build_evaluation_report(metrics, provenance=provenance)
    report["metrics"] = "not-an-object"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)
