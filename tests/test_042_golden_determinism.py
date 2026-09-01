"""Tests for item 042 — golden-file JSON report snapshots & determinism
harness over the committed synthetic corpus (item 040).

Covers Acceptance Criteria AC1-AC16:

- AC1-AC3 (Group A, report construction mirrors ``segfacet run``): every case's
  freshly-built report validates against the v0 schema; the pinned/fixed
  fields (``case_id``, ``schema_version``, ``config_version``) are correct;
  the report carries the full ``features``/``findings`` shape matching a
  direct ``run_qc`` call.
- AC4-AC5 (Group B, determinism): two successive builds of the same case are
  byte-identical canonical JSON; the canonical form is a fixed point under
  parse-then-recanonicalise.
- AC6-AC8 (Group C, golden corpus completeness/storage/validity): exactly one
  golden per manifest case_id; every committed golden parses and validates;
  every golden's embedded ``case_id`` matches its filename stem.
- AC9 (Group D): the freshly-built report matches the committed golden within
  numeric tolerance for every case (``check_case_golden`` is True) -- relaxed
  from raw byte-identity to a numeric-tolerance comparison so it holds across
  platforms (item 078); the same-platform byte determinism stays strict in
  AC4/AC5/AC12.
- AC10-AC11 (Group E, volatile-field seam): an explicit ``volatile_pointers``
  normalises a synthetic differing field; the real v0 report is already free
  of the documented volatile-key denylist and ``VOLATILE_POINTERS == ()``.
- AC12-AC15 (Group F, one-command update path & the harness bites): ``main``
  regenerates matching goldens into a fresh directory; ``write_goldens``
  reproduces the committed goldens within numeric tolerance (item 078); a
  missing golden raises ``FileNotFoundError``; a mutated golden fails the
  comparison.
- Item 078 (Group H): ``reports_close`` compares two parsed reports with
  numeric tolerance on numeric leaves and exact equality on
  structure/strings/bools/ordering.
- AC16 (Group G): every ``reconstructed_record`` case's committed golden is a
  known pipeline-blind snapshot (``verdict == "pass"``, no golden finding's
  ``rule_id`` is in ``expected_rule_ids``).

Adversarial / edge-case scenarios included:
- ``canonical_json`` is a byte-for-byte no-op under the production default
  ``volatile_pointers=()``.
- ``canonical_json`` sorts keys regardless of input dict-construction order
  (a hand-permuted copy canonicalises identically to the original).
- The ``mode5_remove_level`` golden (case-level finding, empty ``labels``)
  canonicalises and validates without crashing on the empty list.
- A malformed (invalid-JSON) golden file is caught by ``json.loads`` raising
  ``json.JSONDecodeError`` rather than silently passing.
- ``write_goldens`` into an already-populated directory reproduces
  byte-identical files (idempotent regeneration).
- The reconstructed-record goldens' "no designated finding" fact is checked
  genuinely (each such golden actually carries at least the case's expected
  labels' *other*, non-designated content or an empty findings list -- not
  merely an accidentally-empty findings list): the check inspects
  ``rule_id``s explicitly rather than asserting ``findings == []``.
- ``clean_control``'s golden has ``verdict == "pass"`` and ``findings ==
  []`` (positive control's report is snapshot-locked too).
"""

from __future__ import annotations

import copy
import importlib.resources
import json

import jsonschema
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from segfacet.config import bundled_default_config
from segfacet.pipeline import run_qc
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import (
    VOLATILE_POINTERS,
    VOLATILE_SENTINEL,
    build_report_for_case,
    canonical_json,
    check_case_golden,
    main,
    reports_close,
    write_goldens,
)
from segfacet.synth.regression import loaded_seg_image

# =========================================================================== #
# Manifest-driven fixtures
# =========================================================================== #

_MANIFEST = load_manifest()
_CASES = _MANIFEST["cases"]
_COMMITTED_CASE_IDS = {c["case_id"] for c in _CASES}
_RECONSTRUCTED_CASES = [c for c in _CASES if c["detection"] == "reconstructed_record"]

_VOLATILE_KEY_DENYLIST = {
    "timestamp",
    "generated_at",
    "created",
    "date",
    "datetime",
    "path",
    "abspath",
    "tool_version",
    "hostname",
    "user",
}


def _case(case_id):
    for c in _CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _case_id(case):
    return case["case_id"]


def _report_schema():
    import segfacet as _segfacet_pkg

    ref = importlib.resources.files(_segfacet_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_SCHEMA = _report_schema()


def _fresh_report(case_id: str) -> dict:
    """build_report_for_case(case) for the named manifest case_id (item 126
    replacement: reads no committed golden -- the committed corpus-golden
    snapshot store this used to read was retired, see
    docs/aide/golden-decision-table.md's "## Retirement execution log")."""
    return build_report_for_case(_case(case_id))


def _walk_keys(obj):
    """Yield every dict key at any nesting depth of *obj*."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


# =========================================================================== #
# A. Report construction mirrors segfacet run (AC1-AC3)
# =========================================================================== #


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac1_every_case_report_validates_against_schema(case):
    """AC1: build_report_for_case(case) returns a dict that validates against
    report_schema_v0.json without raising."""
    report = build_report_for_case(case)
    jsonschema.validate(report, _SCHEMA)


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac2_fixed_fields_are_correct(case):
    """AC2: case_id, schema_version, and config_version are the pinned
    values for every case."""
    report = build_report_for_case(case)
    assert report["case_id"] == case["case_id"]
    assert report["schema_version"] == "0.1"
    assert report["config_version"] == bundled_default_config().schema_version


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac3_report_carries_full_features_and_findings_shape(case):
    """AC3: the report has a features dict with features_version, and its
    findings equal [f.to_dict() for f in run_qc(...).findings]."""
    report = build_report_for_case(case)
    assert "features" in report
    assert isinstance(report["features"], dict)
    assert "features_version" in report["features"]

    assert "findings" in report
    seg_img = loaded_seg_image(case)
    case_result, _block = run_qc(seg_img, bundled_default_config())
    expected_findings = [f.to_dict() for f in case_result.findings]
    assert report["findings"] == expected_findings


# =========================================================================== #
# B. Determinism (AC4-AC5)
# =========================================================================== #


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac4_two_successive_runs_are_byte_identical(case):
    """AC4: canonical_json(build_report_for_case(case)) is stable across two
    independent invocations."""
    first = canonical_json(build_report_for_case(case))
    second = canonical_json(build_report_for_case(case))
    assert first == second


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac5_canonical_form_is_a_fixed_point(case):
    """AC5: parsing then re-canonicalising canonical_json's output is a
    no-op -- keys are sorted and the text round-trips exactly."""
    report = build_report_for_case(case)
    text = canonical_json(report)
    reparsed = json.loads(text)
    assert canonical_json(report) == canonical_json(reparsed)


# =========================================================================== #
# C. Golden corpus completeness, storage & validity (AC6-AC8)
# =========================================================================== #


def test_ac6_exactly_one_golden_per_manifest_case_no_more_no_fewer(tmp_path):
    """AC6 (item 126 replacement): the set of *.json filename stems written
    by write_goldens(tmp_path) equals the set of committed case_ids -- nine
    files, no orphan and no missing golden. The committed corpus-golden
    snapshot store this used to check was retired; the harness
    (write_goldens) survives and is exercised here against a fresh
    caller-supplied directory instead."""
    out_dir = tmp_path / "regen_ac6"
    write_goldens(out_dir)
    golden_stems = {p.stem for p in out_dir.glob("*.json")}
    assert golden_stems == _COMMITTED_CASE_IDS
    assert len(golden_stems) == 9


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac7_every_committed_golden_is_valid_json_and_validates(case):
    """AC7 (item 126 replacement ii): build_report_for_case(case) validates
    against the report schema for every manifest case -- reads no committed
    corpus-golden snapshot file. json.loads/json.dumps round-trip proves
    the report is itself valid JSON (a dict returned in-process is already a
    Python object, so the round-trip is what stands in for "parses via
    json.loads" now that there is no file to parse)."""
    report = build_report_for_case(case)
    parsed = json.loads(json.dumps(report))
    jsonschema.validate(parsed, _SCHEMA)


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac8_committed_golden_case_id_matches_filename(case, tmp_path):
    """AC8 (item 126 replacement): re-pointed at a regeneration --
    write_goldens(tmp_path) writes ``<case_id>.json`` whose embedded
    ``case_id`` equals the filename stem, for every manifest case."""
    out_dir = tmp_path / f"regen_ac8_{case['case_id']}"
    write_goldens(out_dir)
    stem = case["case_id"]
    written = json.loads((out_dir / f"{stem}.json").read_text(encoding="utf-8"))
    assert written["case_id"] == stem
    assert stem in _COMMITTED_CASE_IDS


# =========================================================================== #
# D. (item 126: the committed-golden comparison this section held, AC9, was
# discharged -- its subject, the committed golden corpus, was retired. See
# docs/aide/golden-decision-table.md's "## Retirement execution log".)
# =========================================================================== #
# E. Volatile-field canonicalisation seam (AC10-AC11)
# =========================================================================== #


def test_ac10_canonical_json_normalises_given_pointers():
    """AC10: with an explicit volatile_pointers=(("generated_at",),), two
    reports differing only in "generated_at" canonicalise identically, and
    the normalised value is VOLATILE_SENTINEL."""
    report_a = {"case_id": "x", "generated_at": "2026-01-01T00:00:00Z"}
    report_b = {"case_id": "x", "generated_at": "2099-12-31T23:59:59Z"}
    pointers = (("generated_at",),)

    text_a = canonical_json(report_a, volatile_pointers=pointers)
    text_b = canonical_json(report_b, volatile_pointers=pointers)
    assert text_a == text_b
    assert json.loads(text_a)["generated_at"] == VOLATILE_SENTINEL


def test_ac11_v0_report_is_already_volatile_field_free():
    """AC11: VOLATILE_POINTERS == (), and no key in the documented volatile
    denylist appears at any nesting depth of any case's real report."""
    assert VOLATILE_POINTERS == ()
    for case in _CASES:
        report = build_report_for_case(case)
        keys = set(_walk_keys(report))
        offending = keys & _VOLATILE_KEY_DENYLIST
        assert not offending, f"case {case['case_id']!r} report has volatile-looking key(s) {offending!r}"


# =========================================================================== #
# F. One-command update path & the harness bites (AC12-AC15)
# =========================================================================== #


def test_ac12_main_regenerates_matching_goldens(tmp_path):
    """AC12: main(["--out", str(tmp)]) returns 0, writes one <case_id>.json
    per manifest case, and every written file's bytes equal
    canonical_json(build_report_for_case(case)) for its case."""
    out_dir = tmp_path / "regen_main"
    rc = main(["--out", str(out_dir)])
    assert rc == 0

    for case in _CASES:
        written = out_dir / f"{case['case_id']}.json"
        assert written.exists(), case["case_id"]
        expected = canonical_json(build_report_for_case(case)).encode("utf-8")
        assert written.read_bytes() == expected, case["case_id"]


def test_ac14_missing_golden_fails_loudly(tmp_path):
    """AC14: check_case_golden(case, golden_dir=tmp) raises
    FileNotFoundError for a case whose golden is absent from tmp."""
    case = _case("clean_control")
    empty_dir = tmp_path / "empty_golden_dir"
    empty_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        check_case_golden(case, golden_dir=empty_dir)


def test_ac15_mutated_golden_is_caught(tmp_path):
    """AC15: check_case_golden(case, golden_dir=tmp) returns False for a
    case whose golden file (a mutated copy in tmp) has been altered."""
    case = _case("clean_control")
    dest = tmp_path / "mutated_golden_dir"
    write_goldens(dest)

    target = dest / f"{case['case_id']}.json"
    original = target.read_text(encoding="utf-8")
    mutated = original.replace('"verdict": "pass"', '"verdict": "fail"')
    assert mutated != original, "mutation had no effect -- fixture assumption invalid"
    target.write_text(mutated, encoding="utf-8")

    assert check_case_golden(case, golden_dir=dest) is False


# =========================================================================== #
# G. The reconstructed goldens are known pipeline-blind snapshots (AC16)
# =========================================================================== #


@pytest.mark.parametrize("case", _RECONSTRUCTED_CASES, ids=_case_id)
def test_ac16_reconstructed_golden_is_pipeline_blind(case):
    """AC16 (item 126 replacement): for every detection ==
    "reconstructed_record" case, its freshly built report has verdict ==
    "pass" and no finding's rule_id is in case["expected_rule_ids"] --
    re-pointed at fresh output; the committed golden this used to read was
    retired."""
    assert _RECONSTRUCTED_CASES  # sanity: modes 1, 4, 8
    report = _fresh_report(case["case_id"])
    assert report["verdict"] == "pass"

    expected_rule_ids = set(case["expected_rule_ids"])
    fired_designated_rule_ids = {
        f["rule_id"] for f in report.get("findings", []) if f["rule_id"] in expected_rule_ids
    }
    assert fired_designated_rule_ids == set(), (
        f"case {case['case_id']!r} fresh report unexpectedly carries a "
        f"designated finding {fired_designated_rule_ids!r} -- it should be "
        "pipeline-blind"
    )


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_adv_canonical_json_is_a_noop_under_default_volatile_pointers(case):
    """Adversarial: with the production default volatile_pointers=(), the
    report is left byte-for-byte untouched relative to plain
    json.dumps(sort_keys=True, indent=2, ensure_ascii=False) + "\\n"."""
    report = build_report_for_case(case)
    expected = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert canonical_json(report) == expected
    assert canonical_json(report, volatile_pointers=()) == expected


def test_adv_mode5_remove_level_golden_canonicalises_without_crashing_on_empty_labels():
    """Adversarial (item 126 replacement): the freshly built mode5_remove_level
    report (case-level finding, labels == []) canonicalises and validates
    without crashing on an empty label list."""
    case = _case("mode5_remove_level")
    report = _fresh_report(case["case_id"])
    jsonschema.validate(report, _SCHEMA)

    case_level_findings = [f for f in report.get("findings", []) if f["labels"] == []]
    assert case_level_findings, "expected at least one case-level (labels == []) finding"

    # Round-trips through canonical_json without error even though a
    # findings entry carries an empty labels list.
    text = canonical_json(report)
    assert json.loads(text) == report


def test_adv_reordered_top_level_keys_canonicalise_identically():
    """Adversarial: a hand-permuted copy of a report (same content, keys
    inserted in a different order) canonicalises to the same bytes as the
    original -- sorted-key robustness."""
    case = _case("clean_control")
    report = build_report_for_case(case)

    permuted = {}
    for key in reversed(list(report.keys())):
        permuted[key] = report[key]
    assert list(permuted.keys()) != list(report.keys())  # sanity: order differs

    assert canonical_json(report) == canonical_json(permuted)


def test_adv_write_goldens_idempotent_over_existing_directory(tmp_path):
    """Adversarial: re-running write_goldens over an already-populated
    directory reproduces byte-identical files -- the update path is safe to
    re-run."""
    dest = tmp_path / "idempotent"
    write_goldens(dest)
    first = {p.name: p.read_bytes() for p in dest.glob("*.json")}

    write_goldens(dest)
    second = {p.name: p.read_bytes() for p in dest.glob("*.json")}

    assert first == second


def test_adv_malformed_golden_json_is_caught_not_silently_accepted(tmp_path):
    """Adversarial: a golden file containing invalid JSON is caught by
    json.loads raising JSONDecodeError -- a corrupted golden must fail
    loudly, never silently parse as something else."""
    bad_dir = tmp_path / "malformed"
    bad_dir.mkdir()
    bad_path = bad_dir / "clean_control.json"
    bad_path.write_text("{ this is not valid json ]", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        json.loads(bad_path.read_text(encoding="utf-8"))


def test_adv_clean_control_golden_passes_with_no_findings():
    """Adversarial (item 126 replacement): clean_control's freshly built
    report has verdict == "pass" and findings == [] -- the positive
    control's report shape is still pinned, just against fresh output
    instead of a committed snapshot."""
    case = _case("clean_control")
    assert case["failure_mode"] == 0
    report = _fresh_report(case["case_id"])
    assert report["verdict"] == "pass"
    assert report["findings"] == []


def test_adv_reconstructed_golden_blindness_is_checked_via_rule_ids_not_empty_findings():
    """Adversarial (item 126 replacement): AC16's "no designated finding"
    fact is verified by explicit rule_id inspection, not merely by an
    accidentally-empty findings list -- a reconstructed case whose fresh
    report happens to carry unrelated (non-designated) findings would still
    correctly pass."""
    for case in _RECONSTRUCTED_CASES:
        report = _fresh_report(case["case_id"])
        expected_rule_ids = set(case["expected_rule_ids"])
        all_rule_ids = {f["rule_id"] for f in report.get("findings", [])}
        # The check must be about rule_id membership, not about the list
        # being empty -- assert the discriminator explicitly rather than
        # via report["findings"] == [].
        assert not (all_rule_ids & expected_rule_ids)


# =========================================================================== #
# H. reports_close numeric-tolerance comparator (item 078, AC1-AC4)
# =========================================================================== #


def test_ac1_reports_close_deep_structural_equal_is_true():
    """Item 078 AC1: reports_close returns True for two structurally-equal
    nested reports (dicts, lists, mixed leaf types)."""
    a = {"x": [1, 2.0, "s", True, None], "y": {"z": 3.5}}
    b = {"x": [1, 2.0, "s", True, None], "y": {"z": 3.5}}
    assert reports_close(a, b) is True


def test_ac2_reports_close_float_within_tolerance_is_true():
    """Item 078 AC2: two reports whose only difference is a sub-tolerance
    float delta (a last-ULP-style difference) compare equal."""
    a = {"centroid_mm": [106.9841827768014, 35.47483623582042, 27.0]}
    b = {"centroid_mm": [106.98418277680141, 35.474836235820421, 27.0]}
    assert reports_close(a, b) is True


def test_ac2_reports_close_near_zero_uses_abs_tol():
    """Item 078 AC2: values near zero (e.g. total_curvature_deg ~ 1e-14)
    compare equal via the absolute tolerance, where relative tolerance alone
    would not."""
    a = {"total_curvature_deg": 7.105427357601002e-14}
    b = {"total_curvature_deg": 0.0}
    assert reports_close(a, b) is True


def test_ac3_reports_close_float_beyond_tolerance_is_false():
    """Item 078 AC3: a genuine numeric difference (a centroid off by 0.5)
    returns False -- the tolerance does not blunt real feature changes."""
    a = {"centroid_mm": [107.0]}
    b = {"centroid_mm": [107.5]}
    assert reports_close(a, b) is False


def test_ac4_reports_close_string_difference_is_false():
    """Item 078 AC4: a differing string leaf (verdict) is caught exactly."""
    assert reports_close({"verdict": "pass"}, {"verdict": "fail"}) is False


def test_ac4_reports_close_bool_is_not_a_number():
    """Item 078 AC4: booleans are compared by identity, never as numbers --
    True must not be treated as close to 1.0 (bool is an int subclass)."""
    assert reports_close({"flag": True}, {"flag": 1}) is False
    assert reports_close({"flag": True}, {"flag": 1.0}) is False
    assert reports_close({"flag": False}, {"flag": 0}) is False
    assert reports_close({"flag": True}, {"flag": True}) is True


def test_ac4_reports_close_missing_or_extra_key_is_false():
    """Item 078 AC4: differing dict key sets (a missing or extra key) return
    False."""
    assert reports_close({"a": 1, "b": 2}, {"a": 1}) is False
    assert reports_close({"a": 1}, {"a": 1, "b": 2}) is False


def test_ac4_reports_close_list_length_and_order_are_exact():
    """Item 078 AC4: list comparison is length- and order-sensitive (a
    reordered or shorter list is not close)."""
    assert reports_close([1, 2, 3], [1, 2]) is False
    assert reports_close([1, 2, 3], [3, 2, 1]) is False
    assert reports_close([1, 2, 3], [1, 2, 3]) is True


def test_ac4_reports_close_int_float_equal_value_is_true():
    """Item 078 AC4 (edge): an int and a float of equal value compare close
    (e.g. a voxel_count serialised as 5 vs 5.0) -- both are numbers, neither
    is a bool."""
    assert reports_close({"n": 5}, {"n": 5.0}) is True
