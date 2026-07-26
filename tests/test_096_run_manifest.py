"""Tests for the run-manifest provenance record (item 096): a shared
``RunManifest`` dataclass carried by both ``segfacet run`` and
``segfacet evaluate``, following the existing ``EvaluationProvenance``
(item 056) / optional-block (item 009) precedents.

Covers all seven Acceptance Criteria plus the adversarial/edge cases the
item spec's Testing Strategy names: a falsy-but-meaningful ``--seed 0``, an
explicitly-empty ``--postproc-toggles '{}'``, a malformed/non-object
``--postproc-toggles``, and missing-package version resolution returning
``None`` without raising (each of numpy/tptbox/segfacet tested missing in
isolation via an injected resolver).

``segfacet.run_manifest`` does not exist yet at the time this file is
written; its names are imported **locally inside each test function**
(mirroring ``tests/test_056_eval_report.py``'s treatment of its then-new
module) so this file can still be collected before the module is
implemented.

Per the item's Assumptions, ``build_run_manifest`` accepts an injectable
``_version_resolver`` callable (``Sequence[str] -> Dict[str, Optional[str]]``)
so AC6's byte-reproducibility claim -- and the "missing package" adversarial
cases -- do not depend on whatever numpy/TPTBox happen to be installed in
the test environment.

All tests are deterministic, CPU-only, and portable (no network, no
absolute paths, no wall clock).
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from segfacet.cli import main


# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _fake_resolver(versions):
    """Return a ``_version_resolver``-shaped callable that ignores its
    ``package_names`` argument and returns a fixed dict -- lets AC2/AC6/
    adversarial tests assert exact ``resolved_versions`` output independent
    of the real environment."""

    def _resolve(package_names):
        return dict(versions)

    return _resolve


def _run(args, capsys):
    """Invoke ``main(args)`` and return ``(exit_code, stdout, stderr)``."""
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _report_schema():
    import importlib.resources as pkg_resources

    import segfacet

    ref = pkg_resources.files(segfacet).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _eval_report_schema():
    import importlib.resources as pkg_resources

    import segfacet.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("eval_report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


# =========================================================================== #
# AC1: RunManifest is a frozen, JSON-serialisable dataclass
# =========================================================================== #


def test_ac1_run_manifest_all_fields_populated_to_dict():
    """AC1: every field populated -> to_dict() reproduces all seven keys with
    the given values."""
    from segfacet.run_manifest import RunManifest

    manifest = RunManifest(
        segmenter_version="1.2.3",
        segmenter_sha="abc123",
        weights_hash="deadbeef",
        seed=42,
        dataset_id="verse-2020",
        postproc_toggles={"largest_component_only": True},
        resolved_versions={"numpy": "1.26.4", "tptbox": None, "segfacet": "0.0.1"},
    )
    d = manifest.to_dict()

    assert d == {
        "segmenter_version": "1.2.3",
        "segmenter_sha": "abc123",
        "weights_hash": "deadbeef",
        "seed": 42,
        "dataset_id": "verse-2020",
        "postproc_toggles": {"largest_component_only": True},
        "resolved_versions": {"numpy": "1.26.4", "tptbox": None, "segfacet": "0.0.1"},
    }


def test_ac1_run_manifest_all_optional_fields_none_to_dict():
    """AC1: every optional field None -> to_dict() still has every key present
    with None values (never omits a key based on value)."""
    from segfacet.run_manifest import RunManifest

    manifest = RunManifest(
        segmenter_version=None,
        segmenter_sha=None,
        weights_hash=None,
        seed=None,
        dataset_id=None,
        postproc_toggles=None,
        resolved_versions={"numpy": None, "tptbox": None, "segfacet": None},
    )
    d = manifest.to_dict()

    assert set(d.keys()) == {
        "segmenter_version",
        "segmenter_sha",
        "weights_hash",
        "seed",
        "dataset_id",
        "postproc_toggles",
        "resolved_versions",
    }
    assert d["segmenter_version"] is None
    assert d["segmenter_sha"] is None
    assert d["weights_hash"] is None
    assert d["seed"] is None
    assert d["dataset_id"] is None
    assert d["postproc_toggles"] is None


def test_ac1_run_manifest_is_frozen():
    """AC1: RunManifest instances are frozen -- attribute assignment raises."""
    from segfacet.run_manifest import RunManifest

    manifest = RunManifest(
        segmenter_version="1.0",
        segmenter_sha=None,
        weights_hash=None,
        seed=None,
        dataset_id=None,
        postproc_toggles=None,
        resolved_versions={},
    )
    with pytest.raises((AttributeError, TypeError)):
        manifest.segmenter_version = "2.0"


def test_ac1_to_dict_is_json_serialisable():
    """AC1: to_dict()'s output round-trips through json.dumps/json.loads."""
    from segfacet.run_manifest import RunManifest

    manifest = RunManifest(
        segmenter_version="1.0",
        segmenter_sha="sha",
        weights_hash="hash",
        seed=7,
        dataset_id="ds",
        postproc_toggles={"a": [1, 2], "b": None},
        resolved_versions={"numpy": "1.26.4"},
    )
    text = json.dumps(manifest.to_dict())
    assert json.loads(text) == manifest.to_dict()


# =========================================================================== #
# AC2: resolved_versions is auto-populated, not caller-supplied
# =========================================================================== #


def test_ac2_build_run_manifest_no_args_returns_none():
    """AC2: build_run_manifest() with no caller-supplied fields at all
    returns None, not a manifest with all fields empty."""
    from segfacet.run_manifest import build_run_manifest

    assert build_run_manifest() is None


def test_ac2_build_run_manifest_one_field_returns_manifest_with_resolved_versions():
    """AC2: one caller-supplied field plus an injected resolver -> a populated
    RunManifest whose resolved_versions matches the injected resolver exactly,
    including a None entry for a "not installed" package."""
    from segfacet.run_manifest import build_run_manifest

    fixed = {"numpy": "1.26.4", "tptbox": None, "segfacet": "0.0.1"}
    manifest = build_run_manifest(
        segmenter_version="1.2.3", _version_resolver=_fake_resolver(fixed)
    )

    assert manifest is not None
    assert manifest.segmenter_version == "1.2.3"
    assert manifest.resolved_versions == fixed


def test_ac2_build_run_manifest_all_none_explicit_returns_none():
    """AC2: calling build_run_manifest with every caller-supplied field
    explicitly passed as None returns None (same as omitting them)."""
    from segfacet.run_manifest import build_run_manifest

    manifest = build_run_manifest(
        segmenter_version=None,
        segmenter_sha=None,
        weights_hash=None,
        seed=None,
        dataset_id=None,
        postproc_toggles=None,
    )
    assert manifest is None


# =========================================================================== #
# AC3: segfacet run accepts the new flags, emits run_manifest only when
# populated
# =========================================================================== #


def test_ac3_run_no_manifest_flags_no_run_manifest_key(labelled_blocks_files, tmp_path, capsys):
    """AC3: no manifest flags -> the JSON report has no 'run_manifest' key."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, _err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert code in (0, 1)
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" not in data


def test_ac3_run_one_manifest_flag_key_present_rest_null(labelled_blocks_files, tmp_path, capsys):
    """AC3: one manifest flag given -> 'run_manifest' key present, unset
    fields null, resolved_versions populated."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, _err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference",
         "--dataset-id", "verse-2020"],
        capsys,
    )
    assert code in (0, 1)
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" in data
    rm = data["run_manifest"]
    assert rm["dataset_id"] == "verse-2020"
    assert rm["segmenter_version"] is None
    assert rm["segmenter_sha"] is None
    assert rm["weights_hash"] is None
    assert rm["seed"] is None
    assert rm["postproc_toggles"] is None
    assert isinstance(rm["resolved_versions"], dict)


def test_ac3_run_all_manifest_flags_fully_populated(labelled_blocks_files, tmp_path, capsys):
    """AC3: all manifest flags given -> 'run_manifest' fully populated."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, _err = _run(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--no-reference",
            "--segmenter-version", "1.2.3",
            "--segmenter-sha", "abc123",
            "--weights-hash", "deadbeef",
            "--seed", "42",
            "--dataset-id", "verse-2020",
            "--postproc-toggles", '{"largest_component_only": true}',
        ],
        capsys,
    )
    assert code in (0, 1)
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    rm = data["run_manifest"]
    assert rm["segmenter_version"] == "1.2.3"
    assert rm["segmenter_sha"] == "abc123"
    assert rm["weights_hash"] == "deadbeef"
    assert rm["seed"] == 42
    assert rm["dataset_id"] == "verse-2020"
    assert rm["postproc_toggles"] == {"largest_component_only": True}


def test_ac3_run_malformed_postproc_toggles_json_exits_one(labelled_blocks_files, tmp_path, capsys):
    """AC3: malformed --postproc-toggles JSON exits 1 with a clean 'Error:'
    message, not a raw traceback."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--postproc-toggles", "{not valid json"],
        capsys,
    )
    assert code == 1
    assert "Error:" in err
    assert "Traceback" not in err


# =========================================================================== #
# AC4: segfacet evaluate accepts the same flags with the same behaviour
# =========================================================================== #


def _small_manifest(tmp_path):
    """Build a minimal one-case evaluation-cohort manifest reusing the
    committed Stage-5 corpus fixture, mirroring test_057_evaluate_cli.py's
    own helper."""
    import shutil

    from segfacet.synth.corpus import CORPUS_DIR

    dst = tmp_path / "fixtures"
    if not dst.exists():
        shutil.copytree(CORPUS_DIR / "fixtures", dst)

    manifest = {
        "manifest_version": 1,
        "cases": [
            {
                "case_id": "clean",
                "gt": "fixtures/clean_control_seg.nii.gz",
                "candidate": "fixtures/clean_control_seg.nii.gz",
                "expected": {"expected_verdict": "pass"},
            },
        ],
    }
    path = tmp_path / "cohort.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def test_ac4_evaluate_no_manifest_flags_no_run_manifest_key(tmp_path, capsys):
    """AC4: 'segfacet evaluate' with no manifest flags omits 'run_manifest'
    from the evaluation report."""
    manifest_path = _small_manifest(tmp_path)
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["evaluate", "--cohort", str(manifest_path), "--out", str(out_dir),
         "--build-date", "2026-01-01"],
        capsys,
    )
    assert code == 0, f"stderr: {err}"
    with (out_dir / "eval_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" not in data


def test_ac4_evaluate_all_manifest_flags_fully_populated(tmp_path, capsys):
    """AC4: 'segfacet evaluate' with all manifest flags emits one cohort-level
    'run_manifest' block, fully populated, in the evaluation report."""
    manifest_path = _small_manifest(tmp_path)
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        [
            "evaluate", "--cohort", str(manifest_path), "--out", str(out_dir),
            "--build-date", "2026-01-01",
            "--segmenter-version", "1.2.3",
            "--segmenter-sha", "abc123",
            "--weights-hash", "deadbeef",
            "--seed", "42",
            "--dataset-id", "verse-2020",
            "--postproc-toggles", '{"largest_component_only": true}',
        ],
        capsys,
    )
    assert code == 0, f"stderr: {err}"
    with (out_dir / "eval_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" in data
    rm = data["run_manifest"]
    assert rm["segmenter_version"] == "1.2.3"
    assert rm["seed"] == 42
    assert rm["postproc_toggles"] == {"largest_component_only": True}


def test_ac4_evaluate_malformed_postproc_toggles_json_exits_one(tmp_path, capsys):
    """AC4: malformed --postproc-toggles JSON on 'segfacet evaluate' exits 1
    with a clean 'Error:' message, mirroring the 'run' subcommand."""
    manifest_path = _small_manifest(tmp_path)
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["evaluate", "--cohort", str(manifest_path), "--out", str(out_dir),
         "--build-date", "2026-01-01", "--postproc-toggles", "[1, 2"],
        capsys,
    )
    assert code == 1
    assert "Error:" in err
    assert "Traceback" not in err


# =========================================================================== #
# AC5: both report schemas validate the new optional block
# =========================================================================== #


_VALID_RUN_MANIFEST = {
    "segmenter_version": "1.2.3",
    "segmenter_sha": "abc123",
    "weights_hash": "deadbeef",
    "seed": 42,
    "dataset_id": "verse-2020",
    "postproc_toggles": {"a": True},
    "resolved_versions": {"numpy": "1.26.4", "tptbox": None, "segfacet": "0.0.1"},
}


def test_ac5_report_schema_accepts_well_formed_run_manifest():
    """AC5: a well-formed 'run_manifest' block on a v0 JSON report validates
    cleanly against report_schema_v0.json."""
    from segfacet.config import HeuristicConfig
    from segfacet.report import serialize_report
    from segfacet.verdict import Verdict

    schema = _report_schema()
    cfg = HeuristicConfig(schema_version="0.1", min_foreground_voxels=0, min_label_count=0)
    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(verdict, "c", cfg)
    report["run_manifest"] = _VALID_RUN_MANIFEST
    jsonschema.validate(report, schema)


def test_ac5_report_schema_rejects_malformed_run_manifest_seed_type():
    """AC5: a report whose run_manifest.seed is a string (not an int/null)
    fails jsonschema.validate -- proving the schema is actually enforced."""
    from segfacet.config import HeuristicConfig
    from segfacet.report import serialize_report
    from segfacet.verdict import Verdict

    schema = _report_schema()
    cfg = HeuristicConfig(schema_version="0.1", min_foreground_voxels=0, min_label_count=0)
    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(verdict, "c", cfg)
    bad = dict(_VALID_RUN_MANIFEST)
    bad["seed"] = "not-an-int"
    report["run_manifest"] = bad
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac5_report_schema_run_manifest_not_required():
    """AC5: 'run_manifest' is not in report_schema_v0.json's required list --
    a report omitting it entirely still validates."""
    schema = _report_schema()
    assert "run_manifest" not in schema.get("required", [])


def test_ac5_eval_report_schema_accepts_well_formed_run_manifest():
    """AC5: a well-formed 'run_manifest' block on an evaluation report
    validates cleanly against eval_report_schema_v0.json."""
    from segfacet.config import default_config
    from segfacet.eval.metrics import compute_cohort_metrics
    from segfacet.eval.harness import CohortEvaluation
    from segfacet.eval.report import EvaluationProvenance, build_evaluation_report

    schema = _eval_report_schema()
    metrics = compute_cohort_metrics(CohortEvaluation(cases=()))
    config = default_config()
    provenance = EvaluationProvenance(
        cohort_id="c", cohort_size=0, config_version=config.schema_version,
        build_date="2026-01-01",
    )
    report = build_evaluation_report(metrics, provenance=provenance)
    report["run_manifest"] = _VALID_RUN_MANIFEST
    jsonschema.validate(report, schema)


def test_ac5_eval_report_schema_rejects_malformed_run_manifest_seed_type():
    """AC5: an evaluation report whose run_manifest.seed is a string fails
    jsonschema.validate."""
    from segfacet.config import default_config
    from segfacet.eval.metrics import compute_cohort_metrics
    from segfacet.eval.harness import CohortEvaluation
    from segfacet.eval.report import EvaluationProvenance, build_evaluation_report

    schema = _eval_report_schema()
    metrics = compute_cohort_metrics(CohortEvaluation(cases=()))
    config = default_config()
    provenance = EvaluationProvenance(
        cohort_id="c", cohort_size=0, config_version=config.schema_version,
        build_date="2026-01-01",
    )
    report = build_evaluation_report(metrics, provenance=provenance)
    bad = dict(_VALID_RUN_MANIFEST)
    bad["seed"] = "not-an-int"
    report["run_manifest"] = bad
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac5_eval_report_schema_run_manifest_not_required():
    """AC5: 'run_manifest' is not in eval_report_schema_v0.json's required
    list."""
    schema = _eval_report_schema()
    assert "run_manifest" not in schema.get("required", [])


# =========================================================================== #
# AC6: byte-reproducible serialisation
# =========================================================================== #


def test_ac6_two_identical_build_run_manifest_calls_are_to_dict_equal():
    """AC6: two build_run_manifest calls with identical arguments (including
    a fixed injected resolver) produce to_dict()-equal output, run twice to
    rule out hidden nondeterminism (e.g. dict-ordering)."""
    from segfacet.run_manifest import build_run_manifest

    fixed = {"numpy": "1.26.4", "tptbox": "0.5.0", "segfacet": "0.0.1"}
    kwargs = dict(
        segmenter_version="1.2.3",
        segmenter_sha="abc123",
        weights_hash="deadbeef",
        seed=42,
        dataset_id="verse-2020",
        postproc_toggles={"a": True, "b": [1, 2, 3]},
        _version_resolver=_fake_resolver(fixed),
    )
    m1 = build_run_manifest(**kwargs)
    m2 = build_run_manifest(**kwargs)
    assert m1.to_dict() == m2.to_dict()

    # Run a second time to rule out any hidden nondeterminism.
    m3 = build_run_manifest(**kwargs)
    assert m1.to_dict() == m3.to_dict() == m2.to_dict()


def test_ac6_serialize_report_json_stays_byte_reproducible_with_run_manifest():
    """AC6: serialize_report_json's sorted-key writer stays byte-reproducible
    with a run_manifest block present."""
    from segfacet.config import HeuristicConfig
    from segfacet.report import serialize_report_json
    from segfacet.verdict import Verdict

    cfg = HeuristicConfig(schema_version="0.1", min_foreground_voxels=0, min_label_count=0)
    verdict = Verdict.build(reasons=[], per_label={})
    s1 = serialize_report_json(verdict, "c", cfg, run_manifest=_VALID_RUN_MANIFEST)
    s2 = serialize_report_json(verdict, "c", cfg, run_manifest=_VALID_RUN_MANIFEST)
    assert s1 == s2


# =========================================================================== #
# AC7: omission is silent and clean, not a stub
# =========================================================================== #


def test_ac7_no_manifest_flags_no_run_manifest_key_never_null_or_empty(labelled_blocks_files, tmp_path, capsys):
    """AC7: zero manifest flags -> no 'run_manifest' key at all -- not
    'run_manifest': null and not 'run_manifest': {}."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, _err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert code in (0, 1)
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" not in data
    assert data.get("run_manifest", "__absent__") == "__absent__"


def test_ac7_existing_golden_regression_fixture_unaffected(labelled_blocks_files, tmp_path, capsys):
    """AC7: an existing fixture invocation (identical to test_cli_run.py's
    test_run_json_inventory_matches_fixture) that doesn't pass the new flags
    produces the same shape as before item 096 -- same verdict, same
    findings, still no run_manifest key."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, _err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert code == 0
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["verdict"] == "flagged-for-review"
    assert data["case_id"] == "scan"
    assert "run_manifest" not in data


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_seed_zero_is_falsy_but_populates_manifest(labelled_blocks_files, tmp_path, capsys):
    """--seed 0 is falsy but meaningful -- must still populate the manifest
    (guards against an `if seed:` vs `if seed is not None:` off-by-bug)."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference", "--seed", "0"],
        capsys,
    )
    assert code in (0, 1), f"stderr: {err}"
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" in data
    assert data["run_manifest"]["seed"] == 0


def test_adv_build_run_manifest_seed_zero_returns_manifest_not_none():
    """Direct-API counterpart: build_run_manifest(seed=0) must not be treated
    as "no fields given"."""
    from segfacet.run_manifest import build_run_manifest

    manifest = build_run_manifest(seed=0, _version_resolver=_fake_resolver({}))
    assert manifest is not None
    assert manifest.seed == 0


def test_adv_postproc_toggles_explicit_empty_object_triggers_manifest(labelled_blocks_files, tmp_path, capsys):
    """--postproc-toggles '{}' (an explicitly empty-but-present JSON object)
    still counts as "a flag was given" and triggers manifest emission,
    distinguishing "flag omitted" from "flag given an empty value"."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference", "--postproc-toggles", "{}"],
        capsys,
    )
    assert code in (0, 1), f"stderr: {err}"
    with (out_dir / "segfacet_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "run_manifest" in data
    assert data["run_manifest"]["postproc_toggles"] == {}


def test_adv_build_run_manifest_postproc_toggles_empty_dict_returns_manifest():
    """Direct-API counterpart: build_run_manifest(postproc_toggles={}) must
    not be treated as "no fields given"."""
    from segfacet.run_manifest import build_run_manifest

    manifest = build_run_manifest(postproc_toggles={}, _version_resolver=_fake_resolver({}))
    assert manifest is not None
    assert manifest.postproc_toggles == {}


@pytest.mark.parametrize("bad_json", ["[1, 2, 3]", "42", '"a string"', "true"])
def test_adv_postproc_toggles_non_object_json_rejected(labelled_blocks_files, tmp_path, capsys, bad_json):
    """--postproc-toggles given a JSON array or scalar (not an object) is
    rejected with a clean 'Error:' message and exit 1 -- the field's declared
    type is a mapping."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--postproc-toggles", bad_json],
        capsys,
    )
    assert code == 1
    assert "Error:" in err
    assert "Traceback" not in err


def test_adv_resolved_versions_missing_numpy_returns_none_in_isolation():
    """A resolved_versions lookup for numpy not on PYTHONPATH returns None
    for that entry without raising, with tptbox/segfacet still resolved."""
    from segfacet.run_manifest import build_run_manifest

    fixed = {"numpy": None, "tptbox": "0.5.0", "segfacet": "0.0.1"}
    manifest = build_run_manifest(
        segmenter_version="1.0", _version_resolver=_fake_resolver(fixed)
    )
    assert manifest.resolved_versions["numpy"] is None
    assert manifest.resolved_versions["tptbox"] == "0.5.0"
    assert manifest.resolved_versions["segfacet"] == "0.0.1"


def test_adv_resolved_versions_missing_tptbox_returns_none_in_isolation():
    """A resolved_versions lookup for tptbox not on PYTHONPATH returns None
    for that entry without raising, independent of the other two entries."""
    from segfacet.run_manifest import build_run_manifest

    fixed = {"numpy": "1.26.4", "tptbox": None, "segfacet": "0.0.1"}
    manifest = build_run_manifest(
        segmenter_version="1.0", _version_resolver=_fake_resolver(fixed)
    )
    assert manifest.resolved_versions["numpy"] == "1.26.4"
    assert manifest.resolved_versions["tptbox"] is None
    assert manifest.resolved_versions["segfacet"] == "0.0.1"


def test_adv_resolved_versions_missing_segfacet_metadata_returns_none_in_isolation():
    """A resolved_versions lookup for segfacet's own package metadata not
    being discoverable (e.g. an editable/uninstalled dev checkout) returns
    None for that entry without raising, independent of the other two."""
    from segfacet.run_manifest import build_run_manifest

    fixed = {"numpy": "1.26.4", "tptbox": "0.5.0", "segfacet": None}
    manifest = build_run_manifest(
        segmenter_version="1.0", _version_resolver=_fake_resolver(fixed)
    )
    assert manifest.resolved_versions["numpy"] == "1.26.4"
    assert manifest.resolved_versions["tptbox"] == "0.5.0"
    assert manifest.resolved_versions["segfacet"] is None


def test_adv_resolve_versions_real_lookup_never_raises_on_unknown_package():
    """The real (non-injected) version resolver never raises for a package
    name that cannot possibly be installed -- PackageNotFoundError is caught
    and translated to None."""
    from segfacet.run_manifest import _resolve_versions

    result = _resolve_versions(("definitely-not-a-real-package-xyz-000",))
    assert result == {"definitely-not-a-real-package-xyz-000": None}


def test_adv_build_run_manifest_default_resolver_never_raises():
    """build_run_manifest() with the real default resolver (no injection)
    never raises, even though numpy/tptbox may or may not be installed in
    this test environment."""
    from segfacet.run_manifest import build_run_manifest

    manifest = build_run_manifest(segmenter_version="1.0")
    assert manifest is not None
    assert set(manifest.resolved_versions.keys()) >= {"numpy", "tptbox", "segfacet"}
    for value in manifest.resolved_versions.values():
        assert value is None or isinstance(value, str)
