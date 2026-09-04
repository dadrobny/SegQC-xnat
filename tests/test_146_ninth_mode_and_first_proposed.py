"""Tests for item 146 -- the ninth mode enters the failure-mode specification
through the lifecycle items 144/145 established, and the catalogue's first
``proposed`` entry (mode 10, the collapsed/duplicated-label-set mode).

Three deliverables, one seam: (1) mode 9 (implausible tissue under a label),
whose ``intensity`` / ``intensity_reference_delta`` rule declarations move
from mode-less to declaring mode 9; (2) the intensity sibling of
``synth/regression.py::pipeline_findings`` (``loaded_intensity_case`` /
``intensity_pipeline_findings``), and ``measured_firing``'s new corpus
dispatch that routes through it; (3) mode 10, the first ``proposed`` (never
implemented) specification entry, and the rendering/conformance-check support
an unimplemented mode needs.

AC -> test map (one focused test per AC, in AC order; AC1-AC8 the ninth mode
itself, AC9-AC13 the two rule declarations, AC14-AC18 the public intensity
harness, AC19-AC21 the ``measured_firing`` dispatch, AC22-AC26 the intensity
manifest, AC27-AC31 the first ``proposed`` entry, AC32-AC36 artifacts and the
record):

- AC1:  test_ac1_mode9_present_with_every_schema_field
- AC2:  test_ac2_definition_states_modality_and_three_subshapes
- AC3:  test_ac3_discriminator_names_a_sibling_mode_derived_live
- AC4:  test_ac4_mode9_candidate_features_are_hypothesised,
        test_ac4_mode9_anchor_role_candidate_rejected_naming_mode_and_anchor_paths
- AC5:  test_ac5_mode9_edge_set_equals_live_registry_declared_set
- AC6:  test_ac6_mode9_edge_rungs_match_a_fresh_measurement
- AC7:  test_ac7_mode9_derives_validated_from_live_state,
        test_ac7_narrowed_expected_firing_drops_status_to_implemented
- AC8:  test_ac8_mode9_rung_is_derived_from_its_edges,
        test_ac8_weakened_strongest_edge_derives_weaker_rung
- AC9:  test_ac9_both_intensity_rules_declare_mode9
- AC10: test_ac10_neither_declaration_binds_reserved_corpus_tag
- AC11: test_ac11_declaration_specification_check_is_clean_both_directions
- AC12: test_ac12_mode_absent_from_specification_is_still_reported
- AC13: test_ac13_threshold_constants_hold_pre_item_values,
        test_ac13_replacing_declaration_leaves_run_rules_output_unchanged
- AC14: test_ac14_harness_symbols_defined_and_exported,
        test_ac14_loaded_intensity_case_signature,
        test_ac14_intensity_pipeline_findings_signature,
        test_ac14_loaded_intensity_case_returns_seg_and_scan_images
- AC15: test_ac15_harness_composes_documented_public_path
- AC16: test_ac16_harness_measures_every_intensity_case
- AC17: test_ac17_harness_is_deterministic_and_non_mutating
- AC18: test_ac18_exactly_one_intensity_composition_in_production,
        test_ac18_traceability_module_references_run_qc_with_intensity_nowhere
- AC19: test_ac19_geometric_corpus_case_dispatches_through_geometric_manifest,
        test_ac19_intensity_corpus_case_dispatches_through_intensity_manifest,
        test_ac19_unrecognised_corpus_raises_naming_case_and_corpus
- AC20: test_ac20_mode9_cases_measure_to_expected_sets
- AC21: test_ac21_geometric_dispatch_is_unchanged_for_seed_modes
- AC22: test_ac22_every_intensity_case_carries_the_new_fields
- AC23: test_ac23_clean_case_carries_mode_zero,
        test_ac23_implausible_cases_carry_mode_nine
- AC24: test_ac24_every_cases_expected_firing_equals_fresh_measurement
- AC25: test_ac25_generator_writes_new_fields_byte_reproducibly,
        test_ac25_committed_manifest_is_lf_bytes_with_one_trailing_newline,
        test_ac25_gitattributes_still_pins_intensity_manifest_eol_lf
- AC26: test_ac26_manifest_version_unchanged
- AC27: test_ac27_mode10_present_as_unimplemented_entry
- AC28: test_ac28_mode10_status_and_rung_are_derived_not_authored
- AC29: test_ac29_mode10_empty_sections_render_as_none,
        test_ac29_probe_mode_with_empty_candidate_features_renders_none,
        test_ac29_no_heading_immediately_followed_by_blank_then_heading
- AC30: test_ac30_proposed_entry_acquiring_a_declaring_rule_is_reported
- AC31: test_ac31_specified_entry_deriving_further_is_not_reported
- AC32: test_ac32_specification_artifacts_regenerate_byte_identically_run_to_run,
        test_ac32_fresh_matches_committed_and_is_lf_with_one_trailing_newline
- AC33: test_ac33_downstream_artifacts_regenerate_byte_identically_run_to_run,
        test_ac33_feature_catalogue_matches_committed_via_tolerance_helper,
        test_ac33_traceability_matrix_matches_committed_structurally
- AC34: test_ac34_mode9_catalogue_attribution_equals_declaring_rules_reach
- AC35: test_ac35_module_docstring_records_the_change_with_resolvable_paths
- AC36: test_ac36_aide_check_reports_no_error_and_no_new_warning_class,
        test_ac36_no_warning_names_a_path_this_item_writes

Adversarial / edge cases beyond the one-per-AC set are grouped at the bottom,
in the item spec's Testing Strategy order.

Fixtures and cost (Testing Strategy): ``measured`` wraps
``failure_modes.measured_firing`` and ``intensity_corpus`` wraps
``intensity_pipeline_findings``, each a module-scoped cache keyed by
``case_id`` -- ``run_qc_with_intensity`` over four cases is the expensive part
of this module, so nothing may call it per-parametrisation without the cache.

AC32/AC33's fresh-vs-committed comparisons: no ``committed_artifact_guard.py``
``ALLOWLIST`` ground exists yet for ``failure_modes.generated.*`` or
``traceability_matrix.generated.*`` (item 149 is where a ``no-float-leaf``
ground would be added), so -- mirroring test_144/145's own precedent -- those
four comparisons go through ``json.loads()``/a live rebuild and a plain
markdown string equality rather than a raw ``read_bytes()`` comparison of the
two committed paths. ``feature_catalogue.generated.json`` already carries an
``emission-clamped`` ground, so its comparison goes through
``segfacet.synth.golden.assert_matches_committed_artifact`` instead; its
``.md`` counterpart is allowlisted too, so a direct byte comparison is used
for it, matching ``tests/test_103_feature_catalogue.py``'s own pattern.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

from run_process import run_utf8

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"

_COMMITTED_FM_JSON = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.json"
_COMMITTED_FM_MD = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.md"
_COMMITTED_CATALOGUE_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_COMMITTED_CATALOGUE_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"
_COMMITTED_TRACEABILITY_JSON = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
_COMMITTED_TRACEABILITY_MD = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"
_INTENSITY_MANIFEST_PATH = _REPO_ROOT / "tests" / "corpus" / "intensity" / "manifest.json"

_INTENSITY_CASE_IDS = (
    "clean_hu",
    "implausible_metal",
    "implausible_soft_tissue",
    "degenerate_uniform",
)


# =========================================================================== #
# House fixtures / helpers
# =========================================================================== #


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (the house pattern from
    ``test_144``/``test_137``/``test_138``), so a stub rule registered for an
    adversarial case cannot leak into another test."""
    from segfacet.heuristics.rule import _RULES

    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


@pytest.fixture(scope="module")
def measured():
    """``segfacet.failure_modes.measured_firing`` cached per case_id -- the
    real, public production function under test."""
    import segfacet.failure_modes as fm

    cache: dict = {}

    def _get(case):
        if case.case_id not in cache:
            cache[case.case_id] = fm.measured_firing(case)
        return cache[case.case_id]

    return _get


@pytest.fixture(scope="module")
def intensity_corpus():
    """``segfacet.synth.regression.intensity_pipeline_findings`` cached per
    case_id -- the expensive part of this module (four ``run_qc_with_intensity``
    drives)."""
    from segfacet.synth.regression import intensity_pipeline_findings

    cache: dict = {}

    def _get(case_id: str):
        if case_id not in cache:
            case = _intensity_manifest_case(case_id)
            cache[case_id] = tuple(intensity_pipeline_findings(case))
        return cache[case_id]

    return _get


def _intensity_manifest_cases() -> list:
    payload = json.loads(_INTENSITY_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty intensity corpus manifest"
    return cases


def _intensity_manifest_case(case_id: str) -> dict:
    for case in _intensity_manifest_cases():
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed intensity manifest")


def _fixed_record():
    """A fixed, real feature record + config pair -- mirrors
    ``test_137_mode_less_rule_disposition.py``'s ``_fixed_record()``."""
    from segfacet.config import bundled_default_config
    from segfacet.pipeline import extract_feature_record
    from segfacet.synth.clean_gt import build_clean_spine

    config = bundled_default_config()
    clean = build_clean_spine()
    return extract_feature_record(clean.seg_img, config), config


# =========================================================================== #
# AC1: mode 9 present with every schema field
# =========================================================================== #


def test_ac1_mode9_present_with_every_schema_field():
    from segfacet.verdict import Severity

    import segfacet.failure_modes as fm

    assert 9 in fm.SPECIFICATION
    mode = fm.SPECIFICATION[9]

    for field_info in dataclasses.fields(mode):
        value = getattr(mode, field_info.name)
        if field_info.name in ("candidate_features", "intended_rules", "corpus_cases"):
            assert value, (field_info.name, value)
            continue
        assert value not in ("", (), None), (field_info.name, value)

    assert mode.observability == "needs-paired-scan"
    assert mode.provenance == "hypothesised"
    accepted_severities = {s.label for s in Severity} - {"pass"}
    assert mode.severity in accepted_severities, (mode.severity, accepted_severities)
    assert mode.status == "specified"
    assert mode.status in fm.AUTHORED_STATUSES


# =========================================================================== #
# AC2: the definition names CT and all three sub-shapes
# =========================================================================== #


def test_ac2_definition_states_modality_and_three_subshapes():
    import segfacet.failure_modes as fm

    definition = fm.SPECIFICATION[9].definition
    assert "CT" in definition, definition
    lowered = definition.lower()
    assert "soft tissue" in lowered or "air" in lowered, definition
    assert "metal" in lowered or "implant" in lowered, definition
    assert "degenerate" in lowered or "uniform" in lowered, definition


# =========================================================================== #
# AC3: the discriminator names a sibling mode, derived from the shipped ids
# =========================================================================== #


def test_ac3_discriminator_names_a_sibling_mode_derived_live():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[9]
    all_ids = {m.id for m in fm.iter_modes()}
    tokens = {int(t) for t in re.findall(r"\d+", mode.discriminator)}
    siblings = tokens & (all_ids - {mode.id})
    assert siblings, mode.discriminator


# =========================================================================== #
# AC4: mode 9's candidate features are hypothesised; an anchor role rejected
# =========================================================================== #


def test_ac4_mode9_candidate_features_are_hypothesised():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[9]
    assert mode.candidate_features, "expected >=1 candidate feature on mode 9"
    for feature in mode.candidate_features:
        assert feature.role == "hypothesised", feature


def test_ac4_mode9_anchor_role_candidate_rejected_naming_mode_and_anchor_paths():
    import segfacet.failure_modes as fm

    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(
            id=9,
            name="probe",
            definition="probe definition",
            discriminator="probe discriminator naming mode 1",
            observability="needs-paired-scan",
            candidate_features=(
                fm.CandidateFeature(
                    path="image_features.per_label.median", role="stage18-metric-anchor"
                ),
            ),
            intended_rules=(),
            corpus_cases=(),
            severity="flagged-for-review",
            status="specified",
            provenance="hypothesised",
        )
    message = str(excinfo.value)
    assert "9" in message, message
    assert "MODE_ANCHOR_PATHS" in message, message


# =========================================================================== #
# AC5: mode 9's edge set equals the live registry's
# =========================================================================== #


def test_ac5_mode9_edge_set_equals_live_registry_declared_set():
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import iter_rule_declarations

    declared = {
        rule_id
        for rule_id, decl in iter_rule_declarations()
        if decl is not None and 9 in decl.modes
    }
    assert declared == {"intensity", "intensity_reference_delta"}, declared

    mode = fm.SPECIFICATION[9]
    edge_ids = {edge.rule_id for edge in mode.intended_rules}
    assert edge_ids == declared, (edge_ids, declared)


# =========================================================================== #
# AC6: each mode-9 edge's rung matches a fresh measurement
# =========================================================================== #


def test_ac6_mode9_edge_rungs_match_a_fresh_measurement(measured):
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[9]
    assert mode.corpus_cases, "expected >=1 corpus case on mode 9"

    fired_anywhere: set = set()
    for case in mode.corpus_cases:
        fired_anywhere |= set(measured(case))

    checked = 0
    for edge in mode.intended_rules:
        checked += 1
        if edge.rule_id in fired_anywhere:
            assert edge.evidence_rung == "synthetic-demonstrable", (edge, fired_anywhere)
        else:
            assert edge.evidence_rung == "needs-real-data", (edge, fired_anywhere)
    assert checked == 2, checked


# =========================================================================== #
# AC7: mode 9 derives validated from live state
# =========================================================================== #


def test_ac7_mode9_derives_validated_from_live_state():
    import segfacet.failure_modes as fm

    assert fm.derive_status(fm.SPECIFICATION[9]) == "validated"


def test_ac7_narrowed_expected_firing_drops_status_to_implemented(measured):
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[9]
    case = mode.corpus_cases[0]
    fired = set(measured(case))
    assert fired, "adversarial precondition: the case must fire something"

    disagreeing = tuple(sorted({"__item146_no_such_rule_ever_fires__"}))
    narrowed_case = dataclasses.replace(case, expected_firing=disagreeing)
    probe = dataclasses.replace(mode, corpus_cases=(narrowed_case,) + mode.corpus_cases[1:])

    assert fm.derive_status(probe) == "implemented"
    # The shipped SPECIFICATION entry itself is untouched.
    assert fm.derive_status(fm.SPECIFICATION[9]) == "validated"


# =========================================================================== #
# AC8: mode 9's rung is derived from its edges
# =========================================================================== #


def test_ac8_mode9_rung_is_derived_from_its_edges():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[9]
    strongest = min(
        (edge.evidence_rung for edge in mode.intended_rules),
        key=lambda rung: fm.EVIDENCE_RUNGS.index(rung),
    )
    assert fm.derive_mode_rung(mode) == strongest


def test_ac8_weakened_strongest_edge_derives_weaker_rung():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[9]
    before = fm.derive_mode_rung(mode)

    strengths = [fm.EVIDENCE_RUNGS.index(e.evidence_rung) for e in mode.intended_rules]
    strongest_index = strengths.index(min(strengths))
    weaker_rung = fm.EVIDENCE_RUNGS[strengths[strongest_index] + 1]

    weakened_edges = tuple(
        dataclasses.replace(edge, evidence_rung=weaker_rung) if i == strongest_index else edge
        for i, edge in enumerate(mode.intended_rules)
    )
    weakened_copy = dataclasses.replace(mode, intended_rules=weakened_edges)

    after = fm.derive_mode_rung(weakened_copy)
    assert after != before, (before, after)
    assert after == weaker_rung

    assert fm.derive_mode_rung(fm.SPECIFICATION[9]) == before


# =========================================================================== #
# AC9: both intensity rules declare mode 9
# =========================================================================== #


@pytest.mark.parametrize("rule_id", ["intensity", "intensity_reference_delta"])
def test_ac9_both_intensity_rules_declare_mode9(rule_id):
    from segfacet.heuristics.rule import _RULES

    decl = _RULES[rule_id].mode_declaration
    assert decl.modes == (9,), rule_id
    assert decl.mode_less_reason == "", rule_id
    assert decl.pending_reason == "", rule_id
    assert decl.evidence, rule_id
    for item in decl.evidence:
        assert isinstance(item, str) and item, (rule_id, decl.evidence)


# =========================================================================== #
# AC10: neither declaration binds the reserved geometric-corpus tag
# =========================================================================== #


@pytest.mark.parametrize("rule_id", ["intensity", "intensity_reference_delta"])
def test_ac10_neither_declaration_binds_reserved_corpus_tag(rule_id):
    from segfacet.heuristics.rule import _RULES

    decl = _RULES[rule_id].mode_declaration
    assert "corpus" not in decl.evidence, (rule_id, decl.evidence)
    assert any("tests/corpus/intensity/manifest.json" in e for e in decl.evidence), (
        rule_id,
        decl.evidence,
    )


# =========================================================================== #
# AC11: the declaration<->specification check is clean in both directions
# =========================================================================== #


def test_ac11_declaration_specification_check_is_clean_both_directions():
    import segfacet.catalogue as catalogue
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import iter_rule_declarations

    assert catalogue.rule_declaration_conflicts() == ()

    declared_by_rule = {}
    for rule_id, decl in iter_rule_declarations():
        if decl is None:
            continue
        declared_by_rule[rule_id] = set(decl.modes)
        for mode_id in decl.modes:
            assert mode_id in fm.SPECIFICATION, (rule_id, mode_id)

    checked = 0
    for mode in fm.iter_modes():
        for edge in mode.intended_rules:
            checked += 1
            assert edge.rule_id in declared_by_rule, (mode.id, edge.rule_id)
            assert mode.id in declared_by_rule[edge.rule_id], (mode.id, edge.rule_id)
    assert checked, "expected >=1 intended-rule edge to check"


# =========================================================================== #
# AC12: a mode absent from the specification is still reported
# =========================================================================== #


def test_ac12_mode_absent_from_specification_is_still_reported(isolated_registry):
    import segfacet.catalogue as catalogue
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs
    from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule

    uncatalogued_mode = 1
    while uncatalogued_mode in fm.SPECIFICATION or uncatalogued_mode in feature_docs.MODE_ANCHOR_PATHS:
        uncatalogued_mode += 1

    class _StubRule(Rule):
        rule_id = "__item146_ac12_stub__"
        mode_declaration = RuleModeDeclaration(
            modes=(uncatalogued_mode,), evidence=("analytic", "AC12 probe")
        )

        def evaluate(self, record, config):
            return []

    register_rule(_StubRule)

    conflicts = catalogue.rule_declaration_conflicts()
    matching = [
        msg
        for msg in conflicts
        if "__item146_ac12_stub__" in msg and str(uncatalogued_mode) in msg
    ]
    assert matching, conflicts
    for msg in matching:
        assert re.match(r"^rule '([^']+)': declared §6 mode \d+ is outside", msg), msg


# =========================================================================== #
# AC13: the intensity rules' behaviour is unchanged
# =========================================================================== #


def test_ac13_threshold_constants_hold_pre_item_values():
    import segfacet.heuristics.intensity as intensity_rule_module
    import segfacet.heuristics.intensity_reference_delta as ird_module

    assert intensity_rule_module.DEFAULT_MIN_PLAUSIBLE_HU == 100.0
    assert intensity_rule_module.DEFAULT_MAX_PLAUSIBLE_HU == 2000.0
    assert intensity_rule_module.DEFAULT_MAX_DEGENERATE_STD == 1.0
    assert ird_module.DEFAULT_MAX_ROBUST_Z == 3.5
    assert ird_module.DEFAULT_MAX_DISTRIBUTION_DISTANCE == 3.0


@pytest.mark.parametrize("rule_id", ["intensity", "intensity_reference_delta"])
def test_ac13_replacing_declaration_leaves_run_rules_output_unchanged(rule_id, monkeypatch):
    from segfacet.heuristics.rule import RuleModeDeclaration, _RULES
    from segfacet.heuristics.runner import run_rules

    record, config = _fixed_record()
    before = run_rules(record, config)
    assert isinstance(before, list)

    replacement = RuleModeDeclaration(
        mode_less_reason="AC13 adversarial replacement -- must not affect evaluate()"
    )
    monkeypatch.setattr(_RULES[rule_id], "mode_declaration", replacement)

    after = run_rules(record, config)
    assert after == before


# =========================================================================== #
# AC14: synth/regression.py exposes the intensity sibling
# =========================================================================== #


def test_ac14_harness_symbols_defined_and_exported():
    import segfacet.synth as synth
    import segfacet.synth.regression as regression

    for name in ("loaded_intensity_case", "intensity_pipeline_findings"):
        assert hasattr(regression, name), name
        assert name in regression.__all__, name
        assert hasattr(synth, name), name
        assert name in synth.__all__, name

    from segfacet.synth import intensity_pipeline_findings as reexported

    assert reexported is regression.intensity_pipeline_findings


def test_ac14_loaded_intensity_case_signature():
    import inspect

    from segfacet.synth.intensity import INTENSITY_CORPUS_DIR
    from segfacet.synth.regression import loaded_intensity_case

    sig = inspect.signature(loaded_intensity_case)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["case", "corpus_dir"]
    assert params[1].default == INTENSITY_CORPUS_DIR


def test_ac14_intensity_pipeline_findings_signature():
    import inspect

    from segfacet.synth.intensity import INTENSITY_CORPUS_DIR
    from segfacet.synth.regression import intensity_pipeline_findings

    sig = inspect.signature(intensity_pipeline_findings)
    params = sig.parameters
    assert list(params.keys()) == ["case", "config", "reference", "enable_pyradiomics", "corpus_dir"]
    assert params["config"].default is None
    assert params["reference"].default is None
    assert params["reference"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["enable_pyradiomics"].default is False
    assert params["enable_pyradiomics"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["corpus_dir"].default == INTENSITY_CORPUS_DIR
    assert params["corpus_dir"].kind == inspect.Parameter.KEYWORD_ONLY


def test_ac14_loaded_intensity_case_returns_seg_and_scan_images():
    import nibabel as nib

    from segfacet.synth.regression import loaded_intensity_case

    case = _intensity_manifest_case("clean_hu")
    seg_img, scan_img = loaded_intensity_case(case)
    assert isinstance(seg_img, nib.Nifti1Image)
    assert isinstance(scan_img, nib.Nifti1Image)


# =========================================================================== #
# AC15: the harness composes the documented public path
# =========================================================================== #


def test_ac15_harness_composes_documented_public_path(monkeypatch):
    import segfacet.synth.regression as regression

    case = _intensity_manifest_case("clean_hu")

    real_load_case = regression.load_case
    load_case_calls = []

    def _spy_load_case(scan_path, seg_path):
        load_case_calls.append((scan_path, seg_path))
        return real_load_case(scan_path, seg_path)

    monkeypatch.setattr(regression, "load_case", _spy_load_case)

    class _FakeCaseResult:
        findings = ()

    run_qc_calls = []

    def _fake_run_qc_with_intensity(seg_img, scan_img, config, **kwargs):
        run_qc_calls.append((seg_img, scan_img, config, kwargs))
        return (_FakeCaseResult(), {}, {}, None, None)

    monkeypatch.setattr(regression, "run_qc_with_intensity", _fake_run_qc_with_intensity)

    result = regression.intensity_pipeline_findings(case)

    assert result == ()
    assert len(run_qc_calls) == 1, run_qc_calls
    _seg_img, _scan_img, _config, kwargs = run_qc_calls[0]
    assert kwargs.get("reference") is None, kwargs
    assert kwargs.get("enable_pyradiomics") is False, kwargs
    assert len(load_case_calls) == 1, load_case_calls


# =========================================================================== #
# AC16: the harness measures every intensity case
# =========================================================================== #


@pytest.mark.parametrize("case_id", _INTENSITY_CASE_IDS)
def test_ac16_harness_measures_every_intensity_case(case_id, intensity_corpus):
    case = _intensity_manifest_case(case_id)
    findings = intensity_corpus(case_id)
    got = sorted({f.rule_id for f in findings})
    assert got == case["expected_firing"], (case_id, got, case["expected_firing"])


# =========================================================================== #
# AC17: the harness is deterministic and non-mutating
# =========================================================================== #


def test_ac17_harness_is_deterministic_and_non_mutating():
    from segfacet.synth.regression import intensity_pipeline_findings

    case = _intensity_manifest_case("implausible_metal")
    case_before = copy.deepcopy(case)

    findings_a = intensity_pipeline_findings(case)
    findings_b = intensity_pipeline_findings(case)

    def _tupled(findings):
        return tuple((f.rule_id, f.severity.label, tuple(f.labels)) for f in findings)

    tuple_a = _tupled(findings_a)
    tuple_b = _tupled(findings_b)
    assert tuple_a, "expected >=1 finding on implausible_metal"
    assert tuple_a == tuple_b
    assert case == case_before


# =========================================================================== #
# AC18: there is exactly one intensity composition in production
# =========================================================================== #


def test_ac18_exactly_one_intensity_composition_in_production():
    src_root = _REPO_ROOT / "src" / "segfacet"
    exempt = {
        (src_root / "synth" / "regression.py").resolve(),
        (src_root / "cli.py").resolve(),
    }
    offenders = []
    py_files = sorted(src_root.rglob("*.py"))
    assert py_files, "expected >=1 production module under src/segfacet"
    for path in py_files:
        resolved = path.resolve()
        if resolved in exempt:
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        all_names = names | attrs
        references_run_qc_with_intensity = "run_qc_with_intensity" in all_names
        references_case_load = "load_case" in all_names or "loaded_intensity_case" in all_names
        if references_run_qc_with_intensity and references_case_load:
            offenders.append(path.relative_to(_REPO_ROOT).as_posix())
    assert offenders == [], offenders


def test_ac18_traceability_module_references_run_qc_with_intensity_nowhere():
    text = (_REPO_ROOT / "src" / "segfacet" / "traceability.py").read_text(encoding="utf-8")
    assert "run_qc_with_intensity" not in text
    assert "intensity" not in text


# =========================================================================== #
# AC19: measured_firing dispatches on the corpus
# =========================================================================== #


def test_ac19_geometric_corpus_case_dispatches_through_geometric_manifest():
    import segfacet.failure_modes as fm

    case = fm.CorpusCaseExpectation(
        case_id="mode3_inject_islands",
        corpus="geometric",
        expected_firing=("fragmentation",),
        reason="AC19 dispatch probe",
    )
    assert set(fm.measured_firing(case)) == {"fragmentation"}


def test_ac19_intensity_corpus_case_dispatches_through_intensity_manifest():
    import segfacet.failure_modes as fm

    case = fm.CorpusCaseExpectation(
        case_id="implausible_metal",
        corpus="intensity",
        expected_firing=("intensity",),
        reason="AC19 dispatch probe",
    )
    got = set(fm.measured_firing(case))
    assert got, "expected >=1 finding on implausible_metal"


def test_ac19_unrecognised_corpus_raises_naming_case_and_corpus():
    import segfacet.failure_modes as fm

    case = fm.CorpusCaseExpectation(
        case_id="clean_hu",
        corpus="__nonexistent_corpus__",
        expected_firing=(),
        reason="AC19 adversarial probe",
    )
    with pytest.raises(ValueError) as excinfo:
        fm.measured_firing(case)
    message = str(excinfo.value)
    assert "clean_hu" in message, message
    assert "__nonexistent_corpus__" in message, message


# =========================================================================== #
# AC20: mode 9's cases measure to their expected sets
# =========================================================================== #


def test_ac20_mode9_cases_measure_to_expected_sets(measured):
    import segfacet.failure_modes as fm
    from segfacet.synth.regression import intensity_pipeline_findings

    mode = fm.SPECIFICATION[9]
    assert mode.corpus_cases, "expected >=1 corpus case on mode 9"
    for case in mode.corpus_cases:
        got = set(measured(case))
        assert got, (case.case_id, "expected >=1 measured rule_id")
        assert got == set(case.expected_firing), (case.case_id, got, case.expected_firing)
        assert fm.case_agrees(case) is True, case.case_id

        manifest_case = _intensity_manifest_case(case.case_id)
        findings = intensity_pipeline_findings(manifest_case)
        harness_ids = tuple(sorted({f.rule_id for f in findings}))
        assert fm.measured_firing(case) == harness_ids, case.case_id


# =========================================================================== #
# AC21: the geometric dispatch is unchanged
# =========================================================================== #


@pytest.mark.parametrize("mode_id", range(1, 9))
def test_ac21_geometric_dispatch_is_unchanged_for_seed_modes(mode_id):
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[mode_id]
    assert mode.corpus_cases, mode_id
    for case in mode.corpus_cases:
        assert fm.case_agrees(case) is True, (mode_id, case.case_id)
    assert fm.derive_status(mode) == "validated", mode_id


# =========================================================================== #
# AC22: every intensity case carries the new fields
# =========================================================================== #


@pytest.mark.parametrize("case_id", _INTENSITY_CASE_IDS)
def test_ac22_every_intensity_case_carries_the_new_fields(case_id):
    case = _intensity_manifest_case(case_id)

    assert isinstance(case["failure_mode"], int)
    assert not isinstance(case["failure_mode"], bool)

    assert isinstance(case["failure_mode_name"], str)
    assert case["failure_mode_name"]

    assert case["detection"] == "intensity_pipeline"

    expected_firing = case["expected_firing"]
    assert isinstance(expected_firing, list)
    for rule_id in expected_firing:
        assert isinstance(rule_id, str) and rule_id, (case_id, expected_firing)
    assert expected_firing == sorted(expected_firing), (case_id, expected_firing)
    assert len(expected_firing) == len(set(expected_firing)), (case_id, expected_firing)


# =========================================================================== #
# AC23: the failure-mode fields name the right mode
# =========================================================================== #


def test_ac23_clean_case_carries_mode_zero():
    import segfacet.synth.perturbation as perturbation

    case = _intensity_manifest_case("clean_hu")
    assert case["failure_mode"] == 0
    assert case["failure_mode_name"] == perturbation.FAILURE_MODE_NAMES[0]


@pytest.mark.parametrize(
    "case_id", ["implausible_metal", "implausible_soft_tissue", "degenerate_uniform"]
)
def test_ac23_implausible_cases_carry_mode_nine(case_id):
    import segfacet.failure_modes as fm

    case = _intensity_manifest_case(case_id)
    assert case["failure_mode"] == 9
    assert case["failure_mode_name"] == fm.SPECIFICATION[9].name


# =========================================================================== #
# AC24: every case's expected_firing equals a fresh measurement
# =========================================================================== #


@pytest.mark.parametrize("case_id", _INTENSITY_CASE_IDS)
def test_ac24_every_cases_expected_firing_equals_fresh_measurement(case_id, intensity_corpus):
    case = _intensity_manifest_case(case_id)
    findings = intensity_corpus(case_id)
    got = sorted({f.rule_id for f in findings})
    assert case["expected_firing"] == got, (case_id, case["expected_firing"], got)


# =========================================================================== #
# AC25: the generator writes the new fields byte-reproducibly
# =========================================================================== #


def test_ac25_generator_writes_new_fields_byte_reproducibly(tmp_path):
    from segfacet.synth.intensity import write_intensity_corpus

    manifest_path = write_intensity_corpus(tmp_path)
    fresh_bytes = manifest_path.read_bytes()
    committed_bytes = _INTENSITY_MANIFEST_PATH.read_bytes()
    assert fresh_bytes, "expected a non-empty regenerated manifest"
    assert fresh_bytes == committed_bytes


def test_ac25_committed_manifest_is_lf_bytes_with_one_trailing_newline():
    data = _INTENSITY_MANIFEST_PATH.read_bytes()
    assert data, "expected a non-empty committed manifest"
    assert b"\r" not in data
    assert data.endswith(b"\n")
    assert not data.endswith(b"\n\n")


def test_ac25_gitattributes_still_pins_intensity_manifest_eol_lf():
    gitattributes = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(
        r"tests/corpus/intensity/manifest\.json\s+text\s+eol=lf", gitattributes
    ), gitattributes


# =========================================================================== #
# AC26: the manifest version is unchanged
# =========================================================================== #


def test_ac26_manifest_version_unchanged():
    from segfacet.synth.intensity import INTENSITY_MANIFEST_VERSION

    assert INTENSITY_MANIFEST_VERSION == 1
    payload = json.loads(_INTENSITY_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["manifest_version"] == INTENSITY_MANIFEST_VERSION


# =========================================================================== #
# AC27: mode 10 is present as an unimplemented entry
# =========================================================================== #


def test_ac27_mode10_present_as_unimplemented_entry():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[10]
    assert mode.status == "proposed"
    assert mode.intended_rules == ()
    assert mode.corpus_cases == ()
    assert len(mode.candidate_features) == 1, mode.candidate_features
    feature = mode.candidate_features[0]
    assert feature.role == "hypothesised"
    assert feature.path == "stage3_unavailable.reason"

    lowered = mode.definition.lower()
    assert "centroid" in lowered, mode.definition
    assert "stage3" in mode.definition or "stage 3" in lowered, mode.definition
    assert (
        "short-circuit" in lowered or "short circuit" in lowered or "no finding" in lowered
    ), mode.definition

    all_ids = {m.id for m in fm.iter_modes()}
    tokens = {int(t) for t in re.findall(r"\d+", mode.discriminator)}
    siblings = tokens & (all_ids - {mode.id})
    assert siblings, mode.discriminator


# =========================================================================== #
# AC28: mode 10's status and rung are derived, not authored
# =========================================================================== #


def test_ac28_mode10_status_and_rung_are_derived_not_authored():
    import segfacet.failure_modes as fm

    mode = fm.SPECIFICATION[10]
    assert fm.derive_status(mode) == "proposed"
    assert fm.derive_mode_rung(mode) is None


# =========================================================================== #
# AC29: an empty section renders legibly, not as a hole
# =========================================================================== #


def test_ac29_mode10_empty_sections_render_as_none():
    import segfacet.failure_modes as fm

    md = fm.render_markdown()
    lines = md.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Mode 10:"))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## Mode ")), len(lines)
    )
    block = lines[start:end]

    intended_idx = block.index("Intended rules:")
    assert block[intended_idx + 1] == ""
    assert block[intended_idx + 2] == "- (none)", block

    corpus_idx = block.index("Corpus cases:")
    assert block[corpus_idx + 1] == ""
    assert block[corpus_idx + 2] == "- (none)", block


def test_ac29_probe_mode_with_empty_candidate_features_renders_none(monkeypatch):
    import segfacet.failure_modes as fm
    from types import MappingProxyType

    probe = dataclasses.replace(fm.SPECIFICATION[10], candidate_features=())
    monkeypatch.setattr(fm, "SPECIFICATION", MappingProxyType({10: probe}))

    md = fm.render_markdown()
    lines = md.splitlines()
    idx = lines.index("Candidate features:")
    assert lines[idx + 1] == ""
    assert lines[idx + 2] == "- (none)", lines


def test_ac29_no_heading_immediately_followed_by_blank_then_heading():
    import segfacet.failure_modes as fm

    md = fm.render_markdown()
    lines = md.splitlines()

    def _is_heading(line: str) -> bool:
        return line.startswith("#") or line in (
            "Candidate features:",
            "Intended rules:",
            "Corpus cases:",
        )

    for i in range(len(lines) - 2):
        if _is_heading(lines[i]) and lines[i + 1] == "" and _is_heading(lines[i + 2]):
            pytest.fail(
                f"heading at line {i} ({lines[i]!r}) is followed by a blank line and "
                f"another heading ({lines[i + 2]!r}) -- reads as a hole"
            )


# =========================================================================== #
# AC30: a proposed entry that acquires a declaring rule is reported
# =========================================================================== #


def test_ac30_proposed_entry_acquiring_a_declaring_rule_is_reported(isolated_registry):
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import _RULES, Rule, RuleModeDeclaration, register_rule

    before = fm.specification_conflicts()
    assert before == ()

    class _FakeMode10Detector(Rule):
        rule_id = "__item146_fake_mode10_detector__"
        mode_declaration = RuleModeDeclaration(modes=(10,), evidence=("analytic", "AC30 probe"))

        def evaluate(self, record, config):
            return []

    register_rule(_FakeMode10Detector)

    conflicts = fm.specification_conflicts()
    assert conflicts, "expected >=1 conflict once mode 10 acquires a declaring rule"
    assert any(
        "10" in msg and "proposed" in msg and "implemented" in msg for msg in conflicts
    ), conflicts

    # Retract the stub and confirm the conflict retracts with it -- the
    # transition is attributed to the stub in both directions, not to a
    # `specification_conflicts()` default-argument artefact.
    del _RULES[_FakeMode10Detector.rule_id]
    assert fm.specification_conflicts() == ()


# =========================================================================== #
# AC31: a specified entry that derives further is not reported
# =========================================================================== #


def test_ac31_specified_entry_deriving_further_is_not_reported():
    import segfacet.failure_modes as fm

    checked = 0
    for mode_id in range(1, 10):
        mode = fm.SPECIFICATION[mode_id]
        assert mode.status == "specified", mode_id
        derived = fm.derive_status(mode)
        assert derived in ("implemented", "validated"), (mode_id, derived)
        assert derived != mode.status, (mode_id, derived)
        checked += 1
    assert checked == 9, checked

    assert fm.specification_conflicts() == ()


# =========================================================================== #
# AC32: the specification artifacts regenerate byte-identically
# =========================================================================== #


def test_ac32_specification_artifacts_regenerate_byte_identically_run_to_run(tmp_path):
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


def test_ac32_fresh_matches_committed_and_is_lf_with_one_trailing_newline():
    import segfacet.failure_modes as fm

    committed_json_bytes = _COMMITTED_FM_JSON.read_bytes()
    assert committed_json_bytes, "expected a non-empty committed failure_modes JSON"
    assert b"\r" not in committed_json_bytes
    assert committed_json_bytes.endswith(b"\n")
    assert not committed_json_bytes.endswith(b"\n\n")

    committed_md_bytes = _COMMITTED_FM_MD.read_bytes()
    assert committed_md_bytes, "expected a non-empty committed failure_modes markdown"
    assert b"\r" not in committed_md_bytes
    assert committed_md_bytes.endswith(b"\n")
    assert not committed_md_bytes.endswith(b"\n\n")

    committed_payload = json.loads(committed_json_bytes.decode("utf-8"))
    fresh_payload = fm.specification_to_dict()
    normalised_fresh = json.loads(json.dumps(fresh_payload, sort_keys=True))
    assert normalised_fresh == committed_payload

    committed_ids = {mode_record["id"] for mode_record in committed_payload["modes"]}
    assert committed_ids == set(range(1, 11)), committed_ids

    committed_md = committed_md_bytes.decode("utf-8")
    assert committed_md.strip(), "expected non-empty committed markdown"
    fresh_md = fm.render_markdown()
    assert fresh_md == committed_md
    for mode_id in range(1, 11):
        assert f"Mode {mode_id}:" in fresh_md, mode_id


# =========================================================================== #
# AC33: the downstream artifacts regenerate byte-identically
# =========================================================================== #


def test_ac33_downstream_artifacts_regenerate_byte_identically_run_to_run(tmp_path):
    import segfacet.catalogue as catalogue
    import segfacet.traceability as traceability

    cat_json_a, cat_md_a = tmp_path / "cat_a.json", tmp_path / "cat_a.md"
    cat_json_b, cat_md_b = tmp_path / "cat_b.json", tmp_path / "cat_b.md"
    catalogue.main(["--json", str(cat_json_a), "--md", str(cat_md_a)])
    catalogue.main(["--json", str(cat_json_b), "--md", str(cat_md_b)])
    assert cat_json_a.read_bytes(), "expected non-empty catalogue JSON"
    assert cat_json_a.read_bytes() == cat_json_b.read_bytes()
    assert cat_md_a.read_bytes() == cat_md_b.read_bytes()

    trace_json_a, trace_md_a = tmp_path / "trace_a.json", tmp_path / "trace_a.md"
    trace_json_b, trace_md_b = tmp_path / "trace_b.json", tmp_path / "trace_b.md"
    traceability.main(["--json", str(trace_json_a), "--md", str(trace_md_a)])
    traceability.main(["--json", str(trace_json_b), "--md", str(trace_md_b)])
    assert trace_json_a.read_bytes(), "expected non-empty traceability JSON"
    assert trace_json_a.read_bytes() == trace_json_b.read_bytes()
    assert trace_md_a.read_bytes() == trace_md_b.read_bytes()


def test_ac33_feature_catalogue_matches_committed_via_tolerance_helper(tmp_path):
    import segfacet.catalogue as catalogue
    from segfacet.synth.golden import assert_matches_committed_artifact

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert_matches_committed_artifact(json_dest, _COMMITTED_CATALOGUE_JSON)

    fresh_md_bytes = md_dest.read_bytes()
    committed_md_bytes = _COMMITTED_CATALOGUE_MD.read_bytes()
    assert fresh_md_bytes, "expected non-empty catalogue markdown"
    assert fresh_md_bytes == committed_md_bytes


def test_ac33_traceability_matrix_matches_committed_structurally(tmp_path):
    import segfacet.traceability as traceability

    json_dest = tmp_path / "traceability_matrix.generated.json"
    md_dest = tmp_path / "traceability_matrix.generated.md"
    traceability.main(["--json", str(json_dest), "--md", str(md_dest)])

    fresh_bytes = json_dest.read_bytes()
    assert fresh_bytes, "expected non-empty traceability JSON"
    fresh_payload = json.loads(fresh_bytes.decode("utf-8"))
    committed_bytes = _COMMITTED_TRACEABILITY_JSON.read_bytes()
    assert committed_bytes, "expected a non-empty committed traceability JSON"
    committed_payload = json.loads(committed_bytes.decode("utf-8"))
    assert fresh_payload == committed_payload

    fresh_md_bytes = md_dest.read_bytes()
    committed_md_bytes = _COMMITTED_TRACEABILITY_MD.read_bytes()
    assert fresh_md_bytes, "expected non-empty traceability markdown"
    assert fresh_md_bytes.decode("utf-8") == committed_md_bytes.decode("utf-8")


# =========================================================================== #
# AC34: mode 9's catalogue attribution is exactly the declaring rules' reach
# =========================================================================== #


def test_ac34_mode9_catalogue_attribution_equals_declaring_rules_reach():
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import iter_rule_declarations

    mode9_declarers = {
        rule_id
        for rule_id, decl in iter_rule_declarations()
        if decl is not None and 9 in decl.modes
    }
    assert mode9_declarers == {"intensity", "intensity_reference_delta"}

    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    checked = 0
    for entry in cat.entries:
        has_mode9 = 9 in entry.failure_modes
        reached_by_declarer = bool(set(entry.consuming_rules) & mode9_declarers)
        assert has_mode9 == reached_by_declarer, entry.path
        checked += 1
    assert checked > 0


# =========================================================================== #
# AC35: the module records what had to change
# =========================================================================== #


def test_ac35_module_docstring_records_the_change_with_resolvable_paths():
    import segfacet.failure_modes as fm

    doc = fm.__doc__ or ""
    assert doc, "expected a non-empty module docstring"
    assert "item 146" in doc, doc
    assert re.search(r"2026-09-0\d", doc), doc

    paths = sorted(set(re.findall(r"src/segfacet/[\w./-]+\.py", doc)))
    assert paths, "expected >=1 src/segfacet/*.py path named in the docstring record"
    for rel_path in paths:
        assert (_REPO_ROOT / rel_path).is_file(), rel_path


# =========================================================================== #
# AC36: aide check is clean
#
# AC36 is worded as "exactly the seven baseline warnings of A10", and the
# count was 7 when this item merged (re-measured 2026-09-04 on
# `review/146-findings`: still 7). The count itself is not what the AC is
# about, and pinning it is the repo's number-one recurring defect class
# (`REVIEW.md`, "What Important means here": *a test asserting state the
# loop's own verbs are built to move ... `aide check`'s warning set*). Two of
# A10's seven are `human gate N ... is awaiting a decision`, which
# `aide gate approve` clears the moment a person decides -- so approving a
# gate would turn this test red for a correct action, and item 150 raising
# its own sign-off gate would turn it red for an eighth warning that is the
# stage working as designed. Branch-state warnings ("stale claim branch",
# emitted transiently *during* `aide merge`'s own post-merge re-test) move it
# in the other direction on any developer clone.
#
# What A10 actually claims -- "a new warning class is a finding, not a
# baseline update" -- is preserved by classifying each warning by shape and
# rejecting any class outside the recorded baseline, plus the item-specific
# negatives AC36 names by hand. This is the mechanism the sibling module
# `test_145_eight_hypothesised_modes.py::test_ac24_...` already uses for the
# identical AC, with the same reasoning recorded there.
#
# `run_checks` is called in-process rather than through a subprocess for the
# reason `test_114`'s `_aide_check_warnings` records: the subprocess form
# returned `proc.stdout is None` on the Windows CI runner despite
# `capture_output=True`, and structured `(errors, warnings)` needs no stdout,
# no encoding and no re-parse.
# =========================================================================== #

_BRANCH_STATE_WARNING_PREFIXES = ("stale claim branch", "unrecognised branch")

_BASELINE_WARNING_CLASSES = (
    "assumptions-block",
    "awaiting-a-decision",
    "branch-state",
    "retracted-criterion",
)


def _aide_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_aide_cli_146", _AIDE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _classify_warning(message: str) -> str:
    """Classify by *shape*, so a genuinely new instance of a tolerated class
    still classifies as that class while an unseen shape reports
    ``"unclassified"`` and fails the check."""
    if message.startswith(_BRANCH_STATE_WARNING_PREFIXES):
        return "branch-state"
    if re.search(r"criterion \d+ was retracted on \d{4}-\d{2}-\d{2}", message):
        return "retracted-criterion"
    if "assumptions" in message.lower():
        return "assumptions-block"
    if "awaiting a decision" in message.lower():
        return "awaiting-a-decision"
    return "unclassified"


def test_ac36_aide_check_reports_no_error_and_no_new_warning_class():
    aide = _aide_module()
    errors, warnings = aide.run_checks(_REPO_ROOT, aide.load_config(_REPO_ROOT))
    assert errors == [], errors
    # A plumbing failure must fail loudly, not pass an empty loop vacuously:
    # this repo always reports the baseline warnings.
    assert warnings, "run_checks returned no warnings at all -- expected the baseline"

    classes = {_classify_warning(warning) for warning in warnings}
    assert classes <= set(_BASELINE_WARNING_CLASSES), (
        f"aide check reports a warning class outside the recorded baseline: "
        f"{classes - set(_BASELINE_WARNING_CLASSES)}"
    )


def test_ac36_no_warning_names_a_path_this_item_writes():
    """The negatives AC36 names by hand: no `.gitattributes` lint for any
    path this item regenerated, no `insights.md` entry-shape warning, and no
    warning naming any file the item wrote."""
    aide = _aide_module()
    _errors, warnings = aide.run_checks(_REPO_ROOT, aide.load_config(_REPO_ROOT))
    written_paths = (
        "src/segfacet/failure_modes.py",
        "src/segfacet/synth/regression.py",
        "src/segfacet/synth/intensity.py",
        "src/segfacet/catalogue.py",
        "src/segfacet/heuristics/intensity.py",
        "src/segfacet/heuristics/intensity_reference_delta.py",
        "tests/corpus/intensity/manifest.json",
    )
    for warning in warnings:
        assert "insights.md" not in warning, warning
        assert ".gitattributes" not in warning, warning
        for written_path in written_paths:
            assert written_path not in warning, (written_path, warning)


def test_adv_unclassified_warning_would_be_caught():
    """The classifier must be able to detect a new class -- otherwise the
    AC36 check above passes on anything."""
    assert _classify_warning("a brand new kind of warning nobody has seen") == "unclassified"


def test_adv_aide_check_exits_zero():
    """The other half of AC36: `aide check` must still *exit 0*, which the
    in-process `run_checks` call above cannot observe."""
    result = run_utf8(
        [sys.executable, str(_AIDE_SCRIPT), "check"],
        cwd=_REPO_ROOT,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


@pytest.mark.parametrize("bad_corpus", ["", "Intensity", "Geometric", "intensity "])
def test_adv_dispatch_vocabulary_is_closed_and_exact(bad_corpus):
    import segfacet.failure_modes as fm

    case = fm.CorpusCaseExpectation(
        case_id="clean_hu",
        corpus=bad_corpus,
        expected_firing=(),
        reason="adversarial probe",
    )
    with pytest.raises(ValueError):
        fm.measured_firing(case)


def test_adv_intensity_case_id_not_in_manifest_raises_naming_case_and_manifest():
    import segfacet.failure_modes as fm

    case = fm.CorpusCaseExpectation(
        case_id="__nonexistent__",
        corpus="intensity",
        expected_firing=(),
        reason="adversarial probe",
    )
    with pytest.raises(ValueError) as excinfo:
        fm.measured_firing(case)
    message = str(excinfo.value)
    assert "__nonexistent__" in message, message


def test_adv_unrecognised_detection_in_intensity_manifest_raises_naming_case(monkeypatch):
    import segfacet.failure_modes as fm
    import segfacet.synth.intensity as intensity_module

    real_load = intensity_module.load_intensity_manifest

    def _patched(path=intensity_module.INTENSITY_MANIFEST_PATH):
        payload = real_load(path)
        payload = json.loads(json.dumps(payload))
        for case in payload["cases"]:
            if case["case_id"] == "clean_hu":
                case["detection"] = "__bogus_detection__"
        return payload

    monkeypatch.setattr(intensity_module, "load_intensity_manifest", _patched)

    case = fm.CorpusCaseExpectation(
        case_id="clean_hu",
        corpus="intensity",
        expected_firing=(),
        reason="adversarial probe",
    )
    with pytest.raises(ValueError) as excinfo:
        fm.measured_firing(case)
    assert "clean_hu" in str(excinfo.value)


def test_adv_mode9_corpus_case_bare_str_expected_firing_rejected():
    import segfacet.failure_modes as fm

    bad_case = fm.CorpusCaseExpectation(
        case_id="implausible_metal",
        corpus="intensity",
        expected_firing="intensity",  # bare str, not a tuple
        reason="adversarial: bare string expected_firing",
    )
    with pytest.raises(ValueError):
        fm.case_agrees(bad_case)

    mode9 = fm.SPECIFICATION[9]
    with pytest.raises(ValueError):
        dataclasses.replace(mode9, corpus_cases=(bad_case,))


def test_adv_mode10_with_intended_rules_is_legal_at_construction_but_flagged(isolated_registry):
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule

    mode10 = fm.SPECIFICATION[10]
    fake_edge = fm.IntendedRule(
        rule_id="__item146_adv_mode10_edge__", detector="", evidence_rung="needs-real-data"
    )
    contradictory = dataclasses.replace(mode10, intended_rules=(fake_edge,))  # must not raise
    assert contradictory.intended_rules == (fake_edge,)
    assert contradictory.status == "proposed"

    class _FakeMode10Detector(Rule):
        rule_id = "__item146_adv_mode10_edge__"
        mode_declaration = RuleModeDeclaration(
            modes=(10,), evidence=("analytic", "adversarial probe")
        )

        def evaluate(self, record, config):
            return []

    register_rule(_FakeMode10Detector)

    conflicts = fm.specification_conflicts((contradictory,))
    assert conflicts, "expected the proposed-drift check to fire"
    assert any("10" in msg for msg in conflicts), conflicts


def test_adv_render_markdown_twice_equal():
    import segfacet.failure_modes as fm

    assert fm.render_markdown() == fm.render_markdown()


def test_adv_specification_to_dict_twice_equal_and_mode10_lists_not_shared():
    import segfacet.failure_modes as fm

    first = fm.specification_to_dict()
    second = fm.specification_to_dict()
    assert first == second

    mode10_first = next(m for m in first["modes"] if m["id"] == 10)
    mode10_second = next(m for m in second["modes"] if m["id"] == 10)
    assert mode10_first["intended_rules"] == []
    assert mode10_first["intended_rules"] is not mode10_second["intended_rules"]
    mode10_first["intended_rules"].append({"sneaky": "mutation"})
    assert mode10_second["intended_rules"] == []


def test_adv_isolated_registry_fixture_restores_shipped_registry():
    """Exercises the same snapshot/restore mechanics AC12/AC30's
    ``isolated_registry`` fixture uses, directly, so the 'restored afterwards'
    half can be asserted within a single function body -- a fixture's
    teardown runs after the test that uses it returns, so it cannot be
    observed from inside that same test."""
    from segfacet.heuristics.rule import _RULES, Rule, RuleModeDeclaration, register_rule

    snapshot = dict(_RULES)
    try:

        class _TempRule(Rule):
            rule_id = "__item146_isolated_registry_probe__"
            mode_declaration = RuleModeDeclaration(
                mode_less_reason="adversarial probe, discarded"
            )

            def evaluate(self, record, config):
                return []

        register_rule(_TempRule)
        assert "__item146_isolated_registry_probe__" in _RULES
    finally:
        _RULES.clear()
        _RULES.update(snapshot)

    assert "__item146_isolated_registry_probe__" not in _RULES
    assert dict(_RULES) == snapshot


def test_adv_intensity_pipeline_findings_forwards_config(intensity_corpus):
    from segfacet.config import bundled_default_config
    from segfacet.synth.regression import intensity_pipeline_findings

    case = _intensity_manifest_case("implausible_metal")
    baseline = {f.rule_id for f in intensity_corpus("implausible_metal")}
    assert "intensity" in baseline, "adversarial precondition: intensity must fire on implausible_metal"

    config = bundled_default_config()
    disabled_config = dataclasses.replace(
        config, rules={**config.rules, "intensity": {"enabled": False}}
    )

    findings = intensity_pipeline_findings(case, disabled_config)
    got = {f.rule_id for f in findings}
    assert "intensity" not in got, got
    assert got == baseline - {"intensity"}, (got, baseline)


def test_adv_harness_two_calls_leave_committed_manifest_file_unchanged():
    from segfacet.synth.regression import intensity_pipeline_findings

    before = _INTENSITY_MANIFEST_PATH.read_bytes()
    case = _intensity_manifest_case("clean_hu")
    intensity_pipeline_findings(case)
    intensity_pipeline_findings(case)
    after = _INTENSITY_MANIFEST_PATH.read_bytes()
    assert before == after


# =========================================================================== #
# Review fixes (rank-3 per-item review of item 146, 2026-09-04)
# =========================================================================== #


@pytest.mark.parametrize("rule_id", ["intensity", "intensity_reference_delta"])
@pytest.mark.parametrize("case_id", ["implausible_metal", "degenerate_uniform"])
def test_review_declaration_replacement_invariant_on_a_case_the_rule_fires_on(
    rule_id, case_id, monkeypatch
):
    """AC13's ``run_rules``-invariance test drives ``_fixed_record()`` -- a
    clean spine with no ``image_features`` key at all -- on which
    ``run_rules`` returns ``[]`` and neither intensity rule can produce a
    finding (measured 2026-09-04: 0 findings, record keys are
    ``features_version``/``overlaps``/``per_label``/``relationships``/
    ``stage3``). ``after == before`` there is ``[] == []``: it would hold
    just as well if the declaration *did* reach ``evaluate``, so it cannot
    distinguish "the engine never reads the declaration" from "these two
    rules never fire on this record".

    This drives the same invariance claim through the item's own public
    intensity harness on a case where ``intensity`` demonstrably fires, and
    compares the full finding sequence (rule id, severity label, labels,
    reason) rather than a list identity -- so a declaration that reached
    any part of either rule's output would show up."""
    from segfacet.heuristics.rule import RuleModeDeclaration, _RULES
    from segfacet.synth.regression import intensity_pipeline_findings

    def _tupled(findings):
        return tuple(
            (f.rule_id, f.severity.label, tuple(f.labels), f.reason) for f in findings
        )

    case = _intensity_manifest_case(case_id)
    before = _tupled(intensity_pipeline_findings(case))
    assert before, (case_id, "expected >=1 finding to compare")
    assert any(entry[0] == "intensity" for entry in before), (case_id, before)

    replacement = RuleModeDeclaration(
        mode_less_reason=(
            "review-fix adversarial replacement -- must not affect evaluate()"
        )
    )
    monkeypatch.setattr(_RULES[rule_id], "mode_declaration", replacement)

    after = _tupled(intensity_pipeline_findings(case))
    assert after == before, (rule_id, case_id, before, after)


def test_review_derive_status_requires_a_declaring_rule_for_validated():
    """The declaring-rule precondition this item added to ``derive_status``
    (the item-145 review finding, ``docs/aide/insights.md`` 2026-09-03) had
    no test: every shipped mode that reaches the corpus-agreement clause is
    also declared, and ``test_144``'s
    ``test_adv_empty_corpus_cases_and_intended_rules_derives_specified_not_validated``
    empties the registry only for a mode with *no* corpus cases. Deleting
    the ``declared and`` guard therefore left the whole suite green.

    The state the guard is about is a mode whose corpus cases **agree** and
    which **no registered rule declares**. It is reachable without touching
    the registry, by giving the probe a mode id nothing declares while its
    case still names a rule that really fires: pre-fix this derived
    ``"validated"`` (the corpus-agreement clause was tested first), post-fix
    it derives the authored ``"specified"`` -- vision.md section 6's ladder
    is cumulative, so validated implies implemented."""
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import iter_rule_declarations

    undeclared_mode_id = 1
    declared_anywhere = {
        mode_id
        for _rule_id, decl in iter_rule_declarations()
        if decl is not None
        for mode_id in decl.modes
    }
    while undeclared_mode_id in declared_anywhere or undeclared_mode_id in fm.SPECIFICATION:
        undeclared_mode_id += 1
    assert fm._registry_declares(undeclared_mode_id) is False, undeclared_mode_id

    agreeing_case = fm.CorpusCaseExpectation(
        case_id="mode3_inject_islands",
        corpus="geometric",
        expected_firing=("fragmentation",),
        reason="review-fix probe: an agreeing case under an undeclared mode id",
    )
    assert fm.case_agrees(agreeing_case) is True

    probe = fm.ModeSpec(
        id=undeclared_mode_id,
        name="review-fix probe mode",
        definition="A probe mode no registered rule declares.",
        discriminator="Distinguishes from mode 3 by being a test probe.",
        observability="single-channel-observable",
        candidate_features=(fm.CandidateFeature(path="per_label", role="hypothesised"),),
        intended_rules=(),
        corpus_cases=(agreeing_case,),
        severity="flagged-for-review",
        status="specified",
        provenance="hypothesised",
    )

    assert fm.derive_status(probe) != "validated", fm.derive_status(probe)
    assert fm.derive_status(probe) == "specified", fm.derive_status(probe)

    # The shipped modes are unmoved by the guard: every one of them that
    # reaches the corpus-agreement clause is declared.
    assert fm.derive_status(fm.SPECIFICATION[3]) == "validated"
    assert fm.derive_status(fm.SPECIFICATION[9]) == "validated"
