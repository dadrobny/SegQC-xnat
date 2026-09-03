"""Tests for item 145 -- authoring vision.md section 6's eight hypothesised
failure modes into item 144's specification module (``segfacet.failure_modes``)
and regenerating ``docs/aide/failure_modes.generated.{json,md}``.

Covers Acceptance Criteria AC1-AC24 per the item spec's Testing Strategy, plus
the listed adversarial / edge cases. Every factual AC recomputes its fact from
the primary source -- the live rule registry, ``MODE_ANCHOR_PATHS``, the
parsed ``vision.md``, or a fresh drive of the committed corpus fixtures --
and compares; none is met by a length floor, a token-presence check alone, or
a flag derived from the declarations themselves.

Corpus-driven tests (AC8-AC18, AC20, AC21) share two module-scoped fixtures
(``corpus``, ``measured``) that each drive a committed case through the
pipeline / ``measured_firing`` at most once and cache the result by
``case_id`` -- the expensive part of this module.

AC23 -- ``docs/aide/failure_modes.generated.{json,md}`` carry no
``tests/committed_artifact_guard.py`` ``ALLOWLIST`` ground yet (item 149 adds
the ``no-float-leaf`` ground), so the fresh-vs-committed comparison here goes
through ``json.loads()``/``specification_to_dict()`` and a plain
``render_markdown()`` string equality rather than a ``read_bytes()``
comparison of the two committed paths, which would need an ``ALLOWLIST``
entry this item does not add. The byte-exact comparison stays run-to-run only
(two ``tmp_path`` renders), matching item 144's own AC18 pattern.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

from run_process import run_utf8

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMMITTED_JSON = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.json"
_COMMITTED_MD = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.md"
_MANIFEST_PATH = _REPO_ROOT / "tests" / "corpus" / "manifest.json"
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"

_EXPECTED_MODE_IDS = (1, 2, 3, 4, 5, 6, 7, 8)

_TOUCH_FACES = (
    "touches_superior",
    "touches_inferior",
    "touches_left",
    "touches_right",
    "touches_anterior",
    "touches_posterior",
)


# =========================================================================== #
# House fixtures / helpers
# =========================================================================== #


def _manifest_cases() -> list:
    payload = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty corpus manifest"
    return cases


def _manifest_case(case_id: str) -> dict:
    for case in _manifest_cases():
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


@pytest.fixture(scope="module")
def corpus():
    """One measurement pass per committed corpus case: a callable
    ``get(case_id) -> (detection, findings, record)``, each case_id computed
    at most once and cached for the whole module (Testing Strategy)."""
    from segfacet.config import bundled_default_config
    from segfacet.pipeline import extract_feature_record
    from segfacet.synth.regression import (
        loaded_seg_image,
        pipeline_findings,
        reconstructed_findings,
    )

    config = bundled_default_config()
    cache: dict = {}

    def _get(case_id: str):
        if case_id in cache:
            return cache[case_id]
        case = _manifest_case(case_id)
        detection = case["detection"]
        record = extract_feature_record(loaded_seg_image(case), config)
        if detection == "pipeline":
            findings = tuple(pipeline_findings(case, config))
        elif detection == "reconstructed_record":
            findings = tuple(reconstructed_findings(case, config))
        else:
            raise AssertionError(
                f"unrecognised detection {detection!r} for case_id={case_id!r}"
            )
        cache[case_id] = (detection, findings, record)
        return cache[case_id]

    return _get


@pytest.fixture(scope="module")
def measured():
    """``segfacet.failure_modes.measured_firing`` cached per case_id (Testing
    Strategy) -- the real, public production function under test."""
    import segfacet.failure_modes as fm

    cache: dict = {}

    def _get(case):
        if case.case_id not in cache:
            cache[case.case_id] = fm.measured_firing(case)
        return cache[case.case_id]

    return _get


def _mode(fm, mode_id: int):
    mode = next((m for m in fm.iter_modes() if m.id == mode_id), None)
    assert mode is not None, mode_id
    return mode


def _case(mode, case_id: str):
    case = next((c for c in mode.corpus_cases if c.case_id == case_id), None)
    assert case is not None, (mode.id, case_id)
    return case


def _pick_mode_with_unique_strongest_edge(fm):
    """The first shipped mode whose derived rung comes from exactly one
    strongest edge -- picked live, never hardcoded to a particular mode id
    (AC7's precondition)."""
    for mode in fm.iter_modes():
        if not mode.intended_rules:
            continue
        strengths = [fm.EVIDENCE_RUNGS.index(e.evidence_rung) for e in mode.intended_rules]
        if strengths.count(min(strengths)) == 1:
            return mode
    return None


# =========================================================================== #
# AC1: all eight modes are present
# =========================================================================== #


def test_ac1_all_eight_modes_present():
    import segfacet.failure_modes as fm

    ids = tuple(mode.id for mode in fm.iter_modes())
    assert ids == _EXPECTED_MODE_IDS


# =========================================================================== #
# AC2: every schema field is populated for every one of the eight
# =========================================================================== #


@pytest.mark.parametrize("mode_id", _EXPECTED_MODE_IDS)
def test_ac2_every_field_populated(mode_id):
    import segfacet.failure_modes as fm

    mode = _mode(fm, mode_id)
    for field in dataclasses.fields(mode):
        value = getattr(mode, field.name)
        assert value not in ("", (), None), (mode_id, field.name)
    assert mode.candidate_features
    assert mode.intended_rules
    assert mode.corpus_cases


# =========================================================================== #
# AC3: names equal vision.md section 6's list, derived from the document
# =========================================================================== #


def test_ac3_names_match_vision_section_six_parsed_titles():
    import segfacet.failure_modes as fm
    import segfacet.traceability as traceability

    titles = traceability._vision_mode_titles()
    assert titles, "expected >=1 title parsed from vision.md section 6"
    for mode in fm.iter_modes():
        assert mode.id in titles, mode.id
        assert mode.name == titles[mode.id], (mode.id, mode.name, titles[mode.id])


# =========================================================================== #
# AC4: the Stage-18 metric anchor path is carried, and only as that
# =========================================================================== #


@pytest.mark.parametrize("mode_id", _EXPECTED_MODE_IDS)
def test_ac4_stage18_anchor_paths_carried_and_only_that(mode_id):
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs

    mode = _mode(fm, mode_id)
    anchor_paths = {
        feature.path
        for feature in mode.candidate_features
        if feature.role == "stage18-metric-anchor"
    }
    assert anchor_paths == set(feature_docs.MODE_ANCHOR_PATHS[mode_id])


# =========================================================================== #
# AC5: the edge set equals what the live registry declares
# =========================================================================== #


@pytest.mark.parametrize("mode_id", _EXPECTED_MODE_IDS)
def test_ac5_edge_set_equals_live_registry_declared_set(mode_id):
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import iter_rule_declarations

    mode = _mode(fm, mode_id)
    declared = {
        rule_id
        for rule_id, declaration in iter_rule_declarations()
        if declaration is not None and mode_id in declaration.modes
    }
    assert declared, f"expected >=1 registered rule to declare mode {mode_id}"
    edge_ids = {edge.rule_id for edge in mode.intended_rules}
    assert edge_ids == declared, (mode_id, edge_ids, declared)


def test_ac5_mode6_edge_set_is_exactly_border():
    import segfacet.failure_modes as fm

    mode = _mode(fm, 6)
    edge_ids = {edge.rule_id for edge in mode.intended_rules}
    assert edge_ids == {"border"}
    assert "mislabel" not in edge_ids


# =========================================================================== #
# AC6: every mode's rung is the strongest of its own edges
# =========================================================================== #


@pytest.mark.parametrize("mode_id", _EXPECTED_MODE_IDS)
def test_ac6_mode_rung_is_the_strongest_of_its_own_edges(mode_id):
    import segfacet.failure_modes as fm

    mode = _mode(fm, mode_id)
    strongest = min(
        (edge.evidence_rung for edge in mode.intended_rules),
        key=lambda rung: fm.EVIDENCE_RUNGS.index(rung),
    )
    assert fm.derive_mode_rung(mode) == strongest


# =========================================================================== #
# AC7: a deliberately weakened edge rung changes the derived mode rung
# =========================================================================== #


def test_ac7_weakening_the_single_strongest_edge_changes_derived_rung():
    import segfacet.failure_modes as fm

    mode = _pick_mode_with_unique_strongest_edge(fm)
    assert mode is not None, "expected >=1 shipped mode with a unique strongest edge"
    before = fm.derive_mode_rung(mode)

    edges = mode.intended_rules
    strengths = [fm.EVIDENCE_RUNGS.index(e.evidence_rung) for e in edges]
    strongest_index = strengths.index(min(strengths))
    weaker_rung = fm.EVIDENCE_RUNGS[strengths[strongest_index] + 1]

    weakened_edges = tuple(
        dataclasses.replace(edge, evidence_rung=weaker_rung) if i == strongest_index else edge
        for i, edge in enumerate(edges)
    )
    weakened_copy = dataclasses.replace(mode, intended_rules=weakened_edges)

    after = fm.derive_mode_rung(weakened_copy)
    assert after != before, (before, after)
    assert after == weaker_rung

    # The shipped SPECIFICATION entry itself is never mutated.
    shipped_again = fm.SPECIFICATION[mode.id]
    assert fm.derive_mode_rung(shipped_again) == before


# =========================================================================== #
# AC8: every synthetic-demonstrable edge is actually demonstrated
# =========================================================================== #


def test_ac8_every_synthetic_demonstrable_edge_is_demonstrated(measured):
    import segfacet.failure_modes as fm

    checked = False
    for mode in fm.iter_modes():
        pipeline_cases = [
            case
            for case in mode.corpus_cases
            if _manifest_case(case.case_id)["detection"] == "pipeline"
        ]
        for edge in mode.intended_rules:
            if edge.evidence_rung != "synthetic-demonstrable":
                continue
            checked = True
            fired = set()
            for case in pipeline_cases:
                fired |= set(measured(case))
            assert edge.rule_id in fired, (mode.id, edge.rule_id, fired)
    assert checked, "expected >=1 synthetic-demonstrable edge in the specification"


# =========================================================================== #
# AC9: the three analytic-only edges are needs-real-data and undemonstrated
# =========================================================================== #


def test_ac9_the_three_analytic_only_edges_are_needs_real_data_and_undemonstrated(measured):
    import segfacet.failure_modes as fm

    targets = {(1, "reference_delta"), (2, "reference_delta"), (2, "bounds")}
    seen = set()
    for mode in fm.iter_modes():
        for edge in mode.intended_rules:
            key = (mode.id, edge.rule_id)
            if key not in targets:
                continue
            seen.add(key)
            assert edge.evidence_rung == "needs-real-data", key
            fired = set()
            for case in mode.corpus_cases:
                fired |= set(measured(case))
            assert edge.rule_id not in fired, (key, fired)
    assert seen == targets, seen


# =========================================================================== #
# AC10a/AC10b: mode 7's divergence -- needs-real-data rung, pipeline-fires
# =========================================================================== #


def test_ac10a_mode7_rung_needs_real_data_while_its_case_measurably_fires(measured):
    import segfacet.failure_modes as fm

    mode = _mode(fm, 7)
    sequence_edges = [edge for edge in mode.intended_rules if edge.rule_id == "sequence"]
    assert len(sequence_edges) == 1, mode.intended_rules
    assert sequence_edges[0].evidence_rung == "needs-real-data"
    assert fm.derive_mode_rung(mode) == "needs-real-data"

    case = _case(mode, "mode7_sequence_break")
    assert "sequence" in measured(case)


def test_ac10b_mode7_records_the_single_rank_descent_cap():
    import segfacet.failure_modes as fm

    mode = _mode(fm, 7)
    case = _case(mode, "mode7_sequence_break")
    assert case.reason.strip()
    assert "rank(v)" in case.reason, case.reason
    assert ("v - 1" in case.reason) or ("v-1" in case.reason), case.reason
    lowered = case.reason.lower()
    for token in ("l1", "t12", "l2", "l5"):
        assert token in lowered, (token, case.reason)


# =========================================================================== #
# AC11/AC12: mode 8's structural unobservability holds live
# =========================================================================== #


def test_ac11_mode8_structural_unobservability_holds_live():
    import segfacet.failure_modes as fm
    from segfacet.synth.regression import pipeline_findings, reconstructed_findings

    mode = _mode(fm, 8)
    assert fm.derive_mode_rung(mode) == "structurally-unobservable"

    case = _manifest_case("mode8_force_overlap")
    assert case["detection"] == "reconstructed_record"

    plain = pipeline_findings(case)
    assert not any(f.rule_id == "overlap" for f in plain), plain

    reconstructed = reconstructed_findings(case)
    assert reconstructed, "expected >=1 finding from the reconstructed record"
    reconstructed_ids = tuple(sorted({f.rule_id for f in reconstructed}))
    assert reconstructed_ids == ("overlap",), reconstructed_ids


def test_ac12_mode8_records_the_single_channel_mechanism():
    import segfacet.failure_modes as fm

    mode = _mode(fm, 8)
    case = _case(mode, "mode8_force_overlap")
    assert case.reason.strip()
    lowered = case.reason.lower()
    assert "single" in lowered and "channel" in lowered, case.reason
    assert "voxel" in lowered, case.reason
    assert "one label" in lowered or "exactly one" in lowered, case.reason
    assert "overlap" in lowered, case.reason


# =========================================================================== #
# AC13: every expected firing set equals a fresh measurement
# =========================================================================== #


def test_ac13_every_expected_firing_equals_fresh_measurement_and_all_validated(measured):
    import segfacet.failure_modes as fm

    checked_cases = 0
    for mode in fm.iter_modes():
        assert mode.corpus_cases, mode.id
        for case in mode.corpus_cases:
            checked_cases += 1
            got = set(measured(case))
            assert got, (mode.id, case.case_id)
            assert set(case.expected_firing) == got, (mode.id, case.case_id, got)
            assert fm.case_agrees(case) is True, (mode.id, case.case_id)
        assert fm.derive_status(mode) == "validated", mode.id
    assert checked_cases >= 8, checked_cases


# =========================================================================== #
# AC14: mode6_crop_at_border expects {border, mislabel} with a reason
# =========================================================================== #


def test_ac14_mode6_case_expects_border_and_mislabel_with_reason():
    import segfacet.failure_modes as fm

    mode = _mode(fm, 6)
    case = _case(mode, "mode6_crop_at_border")
    assert case.expected_firing == ("border", "mislabel")
    assert case.reason.strip()
    lowered = case.reason.lower()
    assert "crop" in lowered or "border" in lowered, case.reason
    assert "centroid" in lowered, case.reason
    assert "curve" in lowered or "spline" in lowered, case.reason
    assert "mislabel" not in {edge.rule_id for edge in mode.intended_rules}


# =========================================================================== #
# AC15: mode 6's displacement is a fresh measurement, not a transcription
# =========================================================================== #


def test_ac15_mode6_displacement_is_a_fresh_measurement(corpus):
    import segfacet.failure_modes as fm

    mode = _mode(fm, 6)
    case = _case(mode, "mode6_crop_at_border")

    _detection, findings, record = corpus("mode6_crop_at_border")
    border_findings = [f for f in findings if f.rule_id == "border"]
    assert border_findings, "expected >=1 border finding on mode6_crop_at_border"
    labels = set()
    for finding in border_findings:
        labels |= set(finding.labels)
    assert len(labels) == 1, labels
    label = next(iter(labels))

    stage3 = record.get("stage3")
    assert stage3, "expected a non-empty stage3 block on a multi-label fixture"
    offsets = stage3.get("per_label_offsets")
    assert offsets, "expected a non-empty stage3.per_label_offsets[] block"
    matching = [o for o in offsets if o["label"] == label and not o.get("is_terminal")]
    assert matching, (label, offsets)
    measured_offset = matching[0]["offset_mm"]

    matches = re.findall(r"(\d+\.\d+)\s*mm", case.reason)
    assert matches, case.reason
    values = [float(m) for m in matches]
    assert any(abs(v - measured_offset) <= 0.05 for v in values), (
        values,
        measured_offset,
        case.reason,
    )


# =========================================================================== #
# AC16: the mode-1 / mode-6 discriminator holds on the corpus
# =========================================================================== #


def test_ac16_mode1_mode6_discriminator_holds_on_corpus(corpus):
    _detection6, _findings6, mode6_record = corpus("mode6_crop_at_border")
    mode6_touches = any(
        entry["geometry"][face]
        for entry in mode6_record["per_label"].values()
        for face in _TOUCH_FACES
    )
    assert mode6_touches is True

    _detection1, _findings1, mode1_record = corpus("mode1_displace")
    mode1_touches = any(
        entry["geometry"][face]
        for entry in mode1_record["per_label"].values()
        for face in _TOUCH_FACES
    )
    assert mode1_touches is False


# =========================================================================== #
# AC17: the mode-2 / mode-3 discriminator holds on the corpus
# =========================================================================== #


def test_ac17_mode2_mode3_discriminator_holds_on_corpus(corpus):
    mode3_case = _manifest_case("mode3_inject_islands")
    mode3_labels = mode3_case["expected_labels"]
    assert mode3_labels, mode3_case
    mode3_label = str(mode3_labels[0])
    _detection3, _findings3, mode3_record = corpus("mode3_inject_islands")
    fraction3 = mode3_record["per_label"][mode3_label]["components"]["largest_component_fraction"]
    assert fraction3 >= 0.9, fraction3

    mode2_case = _manifest_case("mode2_fragment")
    mode2_labels = mode2_case["expected_labels"]
    assert mode2_labels, mode2_case
    mode2_label = str(mode2_labels[0])
    _detection2, _findings2, mode2_record = corpus("mode2_fragment")
    fraction2 = mode2_record["per_label"][mode2_label]["components"]["largest_component_fraction"]
    assert fraction2 <= 0.6, fraction2


# =========================================================================== #
# AC18: the mode-1 / mode-4 discriminator holds on the corpus
# =========================================================================== #


def test_ac18_mode1_mode4_discriminator_leading_tags_differ(corpus):
    from segfacet.heuristics.mislabel import _MISALIGN_TAG, _MISLABEL_TAG

    assert _MISALIGN_TAG != _MISLABEL_TAG

    _detection1, findings1, _record1 = corpus("mode1_displace")
    mode1_mislabel = [f for f in findings1 if f.rule_id == "mislabel"]
    assert mode1_mislabel, "expected mislabel to fire on mode1_displace"

    _detection4, findings4, _record4 = corpus("mode4_relabel_swap")
    mode4_mislabel = [f for f in findings4 if f.rule_id == "mislabel"]
    assert mode4_mislabel, "expected mislabel to fire on mode4_relabel_swap"

    assert any(f.reason.startswith(_MISALIGN_TAG) for f in mode1_mislabel), [
        f.reason for f in mode1_mislabel
    ]
    assert any(f.reason.startswith(_MISLABEL_TAG) for f in mode4_mislabel), [
        f.reason for f in mode4_mislabel
    ]
    assert not any(f.reason.startswith(_MISLABEL_TAG) for f in mode1_mislabel), [
        f.reason for f in mode1_mislabel
    ]
    assert not any(f.reason.startswith(_MISALIGN_TAG) for f in mode4_mislabel), [
        f.reason for f in mode4_mislabel
    ]


# =========================================================================== #
# AC19: every discriminator names at least one sibling mode
# =========================================================================== #


def test_ac19_every_discriminator_names_a_sibling_mode():
    import segfacet.failure_modes as fm

    all_ids = {mode.id for mode in fm.iter_modes()}
    assert all_ids, "expected >=1 mode"
    for mode in fm.iter_modes():
        tokens = {int(t) for t in re.findall(r"\d+", mode.discriminator)}
        siblings = tokens & (all_ids - {mode.id})
        assert siblings, (mode.id, mode.discriminator)


@pytest.mark.parametrize(
    "mode_id, sibling_id",
    [(1, 4), (2, 3), (3, 2), (4, 1), (6, 1)],
)
def test_ac19_named_discriminator_pairs(mode_id, sibling_id):
    import segfacet.failure_modes as fm

    mode = _mode(fm, mode_id)
    tokens = {int(t) for t in re.findall(r"\d+", mode.discriminator)}
    assert sibling_id in tokens, (mode_id, mode.discriminator)


# =========================================================================== #
# AC20: detector names the detector that actually fired
# =========================================================================== #


def test_ac20_detector_names_the_detector_that_actually_fired(corpus):
    import segfacet.failure_modes as fm

    checked_fired = 0
    checked_unfired = 0
    for mode in fm.iter_modes():
        fired_findings = []
        for case in mode.corpus_cases:
            _detection, findings, _record = corpus(case.case_id)
            fired_findings.extend(findings)
        fired_rule_ids = {f.rule_id for f in fired_findings}
        for edge in mode.intended_rules:
            if edge.rule_id in fired_rule_ids:
                checked_fired += 1
                assert edge.detector, (mode.id, edge.rule_id)
                matching = [f for f in fired_findings if f.rule_id == edge.rule_id]
                assert any(f.reason.startswith(edge.detector) for f in matching), (
                    mode.id,
                    edge.rule_id,
                    edge.detector,
                    [f.reason for f in matching],
                )
            else:
                checked_unfired += 1
                assert edge.detector == "", (mode.id, edge.rule_id, edge.detector)
    assert checked_fired, "expected >=1 edge whose rule_id fired on its own mode's case"
    assert checked_unfired, "expected >=1 analytic-only edge that fired nothing"


# =========================================================================== #
# AC21: severity is grounded in what the mode's case measurably produces
# =========================================================================== #


def test_ac21_severity_grounded_in_a_measured_finding(corpus):
    import segfacet.failure_modes as fm

    for mode in fm.iter_modes():
        rule_ids = {edge.rule_id for edge in mode.intended_rules}
        severities = set()
        for case in mode.corpus_cases:
            _detection, findings, _record = corpus(case.case_id)
            severities |= {f.severity.label for f in findings if f.rule_id in rule_ids}
        assert severities, mode.id
        assert mode.severity in severities, (mode.id, mode.severity, severities)


# =========================================================================== #
# AC22: implemented derives on "a registered rule whose modes contains id"
# =========================================================================== #


@pytest.mark.parametrize("mode_id", _EXPECTED_MODE_IDS)
def test_ac22_implemented_derives_on_registered_rule_containment(mode_id):
    import segfacet.failure_modes as fm

    mode = _mode(fm, mode_id)
    probe = dataclasses.replace(mode, corpus_cases=())
    assert fm.derive_status(probe) == "implemented"


# =========================================================================== #
# AC23: both generated artifacts carry the eight modes and are
# byte-reproducible (run-to-run); fresh matches committed structurally
# =========================================================================== #


def test_ac23_regeneration_is_byte_reproducible_run_to_run(tmp_path):
    import segfacet.failure_modes as fm

    json_a, md_a = tmp_path / "a.json", tmp_path / "a.md"
    json_b, md_b = tmp_path / "b.json", tmp_path / "b.md"

    fm.main(["--json", str(json_a), "--md", str(md_a)])
    fm.main(["--json", str(json_b), "--md", str(md_b)])

    bytes_a_json, bytes_b_json = json_a.read_bytes(), json_b.read_bytes()
    bytes_a_md, bytes_b_md = md_a.read_bytes(), md_b.read_bytes()
    assert bytes_a_json, "expected non-empty JSON"
    assert bytes_a_md, "expected non-empty markdown"
    assert bytes_a_json == bytes_b_json
    assert bytes_a_md == bytes_b_md


def test_ac23_fresh_matches_committed_structurally_and_carries_all_eight_ids():
    """No ``committed_artifact_guard.py`` ALLOWLIST ground exists yet for
    these two paths (item 149 adds ``no-float-leaf``), so this compares
    fresh-vs-committed structurally rather than via ``read_bytes()``."""
    import segfacet.failure_modes as fm

    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    assert committed_payload, "expected a non-empty committed JSON payload"
    fresh_payload = fm.specification_to_dict()
    normalised_fresh = json.loads(json.dumps(fresh_payload, sort_keys=True))
    assert normalised_fresh == committed_payload

    committed_ids = {mode_record["id"] for mode_record in committed_payload["modes"]}
    assert committed_ids == set(_EXPECTED_MODE_IDS), committed_ids

    committed_md = _COMMITTED_MD.read_text(encoding="utf-8")
    assert committed_md.strip(), "expected non-empty committed markdown"
    fresh_md = fm.render_markdown()
    assert fresh_md == committed_md
    for mode_id in _EXPECTED_MODE_IDS:
        assert f"Mode {mode_id}:" in fresh_md, mode_id


# =========================================================================== #
# AC24: aide check stays at the baseline warning count
# =========================================================================== #


def test_ac24_aide_check_stays_at_baseline_warning_count():
    result = run_utf8(
        [sys.executable, str(_AIDE_SCRIPT), "check"],
        cwd=_REPO_ROOT,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout, "expected stdout from `aide check`"

    lines = result.stdout.splitlines()
    warning_lines = [line for line in lines if line.startswith("warning:")]
    assert warning_lines, "expected >=1 pinned baseline warning"
    for line in warning_lines:
        assert "insights.md" not in line, line
        assert ".gitattributes" not in line, line

    ok_lines = [line for line in lines if line.startswith("aide check: OK")]
    assert ok_lines, result.stdout
    match = re.search(r"OK \((\d+) warning", ok_lines[0])
    assert match, ok_lines[0]
    assert int(match.group(1)) == 7, ok_lines[0]
    assert int(match.group(1)) == len(warning_lines)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_mode6_case_missing_mislabel_drops_status_to_implemented(measured):
    import segfacet.failure_modes as fm

    mode = _mode(fm, 6)
    case = _case(mode, "mode6_crop_at_border")
    assert "mislabel" in measured(case), (
        "adversarial precondition: mode6_crop_at_border must actually fire mislabel too"
    )

    narrowed_case = dataclasses.replace(case, expected_firing=("border",))
    probe = dataclasses.replace(mode, corpus_cases=(narrowed_case,))
    assert fm.derive_status(probe) == "implemented"

    # The shipped mode itself is untouched.
    assert fm.derive_status(fm.SPECIFICATION[6]) == "validated"


def test_adv_intended_rule_for_a_rule_not_declaring_the_mode_fails_ac5_check():
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import iter_rule_declarations

    mode = fm.SPECIFICATION[1]
    live_declared = {
        rule_id
        for rule_id, declaration in iter_rule_declarations()
        if declaration is not None and 1 in declaration.modes
    }
    assert "border" not in live_declared, "adversarial precondition: 'border' must not declare mode 1"

    bad_edge = fm.IntendedRule(rule_id="border", detector="", evidence_rung="needs-real-data")
    bad_mode = dataclasses.replace(mode, intended_rules=mode.intended_rules + (bad_edge,))
    bad_edge_ids = {edge.rule_id for edge in bad_mode.intended_rules}
    assert bad_edge_ids != live_declared, (bad_edge_ids, live_declared)


def test_adv_discriminator_naming_no_sibling_fails_ac19_check():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[1]
    all_ids = {m.id for m in fm.iter_modes()}
    bad_mode = dataclasses.replace(mode, discriminator="Names no other mode at all.")
    tokens = {int(t) for t in re.findall(r"\d+", bad_mode.discriminator)}
    siblings = tokens & (all_ids - {bad_mode.id})
    assert not siblings, siblings


def test_adv_all_expected_firing_tuples_are_ascending():
    import segfacet.failure_modes as fm

    checked = 0
    for mode in fm.iter_modes():
        for case in mode.corpus_cases:
            checked += 1
            assert case.expected_firing == tuple(sorted(case.expected_firing)), (
                mode.id,
                case.case_id,
                case.expected_firing,
            )
    assert checked >= 8, checked


def test_adv_all_eight_modes_have_a_registered_declaring_rule_under_containment():
    """Negative control for AC22's containment reading: shows the live
    registry actually declares each of the eight ids somewhere (i.e. AC22's
    quantifier is not vacuous)."""
    from segfacet.heuristics.rule import iter_rule_declarations

    declared_ids: set = set()
    for _rule_id, declaration in iter_rule_declarations():
        if declaration is not None:
            declared_ids |= set(declaration.modes)
    for mode_id in _EXPECTED_MODE_IDS:
        assert mode_id in declared_ids, (mode_id, sorted(declared_ids))
