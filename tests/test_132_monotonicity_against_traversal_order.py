"""Tests for item 132 -- judge monotonicity against a traversal-ordered
reference fit so mode 4 fires.

``compute_monotonic_consistency`` used to judge each centroid's closest-point
spline parameter against the very curve fitted through the ordering under
test, so a pure ordering defect (two adjacent levels swapped) could never
fail the check -- the curve simply doubled back and followed the swap. This
item judges ``u`` against a curve fitted in the centroids' **geometric
traversal order** (S coordinate, in the supplied sequence's own net-advance
direction) instead: when that traversal order already is the supplied
order, nothing changes (no second fit, bit-identical ``u_values``); when it
differs, one reference refit is made and the swapped levels read out of
order.

Covers AC1-AC32. AC22 and AC29 are recomputed from the live cohort/catalogue
rather than transcribed constants; AC12 falls back to a source-level AST
check per the item spec's Testing Strategy note (see Decisions log below --
a stable equal-``u`` geometric fixture proved fragile to construct without
executing code). AC32 (``docs/aide/progress.md`` untouched by this item) is
a diff-shape claim about the item's own change, not a content assertion a
unit test can usefully make, and is left to `aide scope` / the validator.

**Designated regression test for AC31** (fails before the fix -- the pin
this item most directly overturns):
``test_ac1_mode4_relabel_swap_is_non_monotonic_through_shipped_record_builder``.
Pre-fix, ``compute_monotonic_consistency`` judges against the in-sample fit
alone and this reads ``is_monotonic is True``; post-fix, against the
traversal-ordered reference curve, it reads ``False``.

Adversarial and edge cases: a forward swap and a reversed-copy swap (AC6, in
both directions); a swap at the very first pair and at the very last pair;
a genuinely caudally-advancing sequence with a swap; an exact S tie (AC11);
a two-level (n==2) minimum in both directions; ``n < 2`` still raises
``ValueError``; the fit-count spy (AC7's zero-extra-fits / one-extra-fit);
a doubly-swapped seven-level sequence naming both pairs; a scoliotic
(large transverse excursion, strictly monotonic S) shape triggering no
refit; determinism on both the identity and refit paths; immutability of
the input centroid sequence and the supplied ``SplineFit``; determinism of
``run_qc`` on the mode-4 fixture across two calls; AC18's manifest
byte-identity via two fresh regenerations; AC19's fixture byte-identity
against the committed corpus.

The manifest (``tests/corpus/manifest.json``) and the generated feature
catalogue (``docs/aide/feature_catalogue.generated.{json,md}``) are
allowlisted byte-exact committed-artifact families (item 127's
``tests/committed_artifact_guard.py``; see also ``test_040``'s AC16 and
``test_131``'s AC15) -- every byte-for-byte comparison below against those
two families reuses that existing allowlist coverage rather than adding a
new one. Item 127's tolerant helper
(``segfacet.synth.golden.assert_matches_committed_artifact``) is reserved
for a fresh-vs-committed comparison carrying float noise; nothing this item
touches introduces one (Assumptions), so it is not invoked here.
"""

from __future__ import annotations

import ast
import inspect
import json
import subprocess
from pathlib import Path
from typing import List, Tuple

import pytest

from segfacet.config import bundled_default_config
from segfacet.feature_docs import FEATURE_DOCS, STATUS_OVERRIDES
from segfacet.features.centroids import LabelCentroid
from segfacet.features.consistency import compute_monotonic_consistency
from segfacet.features.spline import fit_centroid_spline
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.synth.corpus import CASE_RECIPE, load_manifest
from segfacet.synth.regression import loaded_seg_image
from segfacet.verdict import Severity

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CATALOGUE_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_CATALOGUE_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"
_GOLDEN_DECISION_TABLE = _REPO_ROOT / "docs" / "aide" / "golden-decision-table.md"


# =========================================================================== #
# Fixture builders -- copied (not imported), per this repo's module-
# independence convention for item tests.
# =========================================================================== #


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _clean_ascending(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """n centroids on the S axis, ascending, labelled L1..Ln -- already in
    traversal order."""
    return [
        _centroid(f"L{i + 1}", (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _swap(centroids: List[LabelCentroid], i: int, j: int) -> List[LabelCentroid]:
    seq = list(centroids)
    seq[i], seq[j] = seq[j], seq[i]
    return seq


def _manifest_case(case_id: str) -> dict:
    for case in load_manifest()["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _record(case_id: str) -> dict:
    seg_img = loaded_seg_image(_manifest_case(case_id))
    return extract_feature_record(seg_img, bundled_default_config())


def _run_qc_case(case_id: str):
    seg_img = loaded_seg_image(_manifest_case(case_id))
    return run_qc(seg_img, bundled_default_config())


def _patched_consistency_fit_counter(monkeypatch):
    """Patch ``segfacet.features.consistency.fit_centroid_spline`` with a
    wrapper that records (args, kwargs) and delegates to the real function
    -- item spec Testing Strategy's AC7/AC10 note. This is the module-level
    import step 2 requires, so it is also the correct patch point."""
    import segfacet.features.consistency as consistency_mod

    calls: List[Tuple[tuple, dict]] = []
    real_fit = consistency_mod.fit_centroid_spline

    def recording_fit(*args, **kwargs):
        calls.append((args, kwargs))
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(consistency_mod, "fit_centroid_spline", recording_fit)
    return calls


# =========================================================================== #
# AC1/AC2: mode 4 is non-monotonic through the shipped record builder, and
# the swapped pair is named. AC31's designated regression test.
# =========================================================================== #


def test_ac1_mode4_relabel_swap_is_non_monotonic_through_shipped_record_builder():
    """Designated AC31 regression test (see module docstring): pre-fix,
    compute_monotonic_consistency judges against the in-sample fit alone
    and this reads True; post-fix, against the traversal-ordered reference
    curve, it reads False."""
    record = _record("mode4_relabel_swap")
    mono = record["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is False


def test_ac2_mode4_relabel_swap_non_monotonic_pairs_names_l2_l3():
    record = _record("mode4_relabel_swap")
    mono = record["stage3"]["monotonic_consistency"]
    assert mono["non_monotonic_pairs"] == [["L2", "L3"]]


# =========================================================================== #
# AC3: the clean control stays monotonic
# =========================================================================== #


def test_ac3_clean_control_stays_monotonic():
    record = _record("clean_control")
    mono = record["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is True
    assert mono["non_monotonic_pairs"] == []


# =========================================================================== #
# AC4: no clean case's u_values move
# =========================================================================== #

_PRE_ITEM_U_VALUES = {
    "clean_control": [0.000050774, 0.250363632, 0.500000000, 0.749636368, 0.999949226],
    "mode1_displace": [0.000000561, 0.234074709, 0.500000025, 0.765925291, 0.999999440],
    "mode2_fragment": [0.000050774, 0.250363632, 0.500000000, 0.749636368, 0.999949226],
    "mode3_inject_islands": [0.000049227, 0.250369752, 0.500000000, 0.749630248, 0.999950773],
    "mode5_remove_level": [0.000000561, 0.250621894, 0.749378106, 0.999999440],
    "mode6_crop_at_border": [0.000000561, 0.237035382, 0.500000024, 0.762964618, 0.999999440],
    "mode7_sequence_break": [0.000050774, 0.250363632, 0.500000000, 0.749636368, 0.999949226],
    "mode8_force_overlap": [0.000061555, 0.165598814, 0.437861146, 0.718006432, 0.999999440],
}


@pytest.mark.parametrize("case_id", sorted(_PRE_ITEM_U_VALUES))
def test_ac4_no_clean_case_u_values_move(case_id):
    record = _record(case_id)
    actual = record["stage3"]["monotonic_consistency"]["u_values"]
    expected = _PRE_ITEM_U_VALUES[case_id]
    assert actual == pytest.approx(expected, abs=1e-9), (
        f"{case_id}: u_values moved -- {actual} != {expected}"
    )


def test_ac4_pre_item_table_covers_every_non_mode4_manifest_case():
    manifest = load_manifest()
    case_ids = {c["case_id"] for c in manifest["cases"]} - {"mode4_relabel_swap"}
    assert set(_PRE_ITEM_U_VALUES) == case_ids


# =========================================================================== #
# AC5: traversal order is the S order in the sequence's own direction
# =========================================================================== #


def test_ac5_forward_traversal_direction_not_a_defect():
    centroids = _clean_ascending()
    fit = fit_centroid_spline(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert result.is_monotonic is True


def test_ac5_reversed_traversal_direction_not_a_defect():
    """A caudal-first traversal, paired with its OWN fit, is not a defect."""
    centroids = list(reversed(_clean_ascending()))
    fit = fit_centroid_spline(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert result.is_monotonic is True


# =========================================================================== #
# AC6: a swap is detected regardless of traversal direction
# =========================================================================== #


def test_ac6_forward_swap_detected_pair_named_l3_l2():
    """Forward case: the pair appears in the SUPPLIED sequence's order,
    measured (L3, L2) -- see module docstring's worked example."""
    swapped = _swap(_clean_ascending(), 1, 2)
    fit = fit_centroid_spline(swapped)
    result = compute_monotonic_consistency(swapped, fit)
    assert result.is_monotonic is False
    assert len(result.non_monotonic_pairs) == 1
    assert frozenset(result.non_monotonic_pairs[0]) == {"L2", "L3"}
    assert result.non_monotonic_pairs[0] == ("L3", "L2")


def test_ac6_reversed_swap_detected_pair_named_l2_l3():
    """Reversed copy of the swapped sequence, paired with its OWN fit,
    names the same two levels in the opposite order: (L2, L3)."""
    swapped = _swap(_clean_ascending(), 1, 2)
    reversed_swapped = list(reversed(swapped))
    fit = fit_centroid_spline(reversed_swapped)
    result = compute_monotonic_consistency(reversed_swapped, fit)
    assert result.is_monotonic is False
    assert len(result.non_monotonic_pairs) == 1
    assert frozenset(result.non_monotonic_pairs[0]) == {"L2", "L3"}
    assert result.non_monotonic_pairs[0] == ("L2", "L3")


# =========================================================================== #
# AC7: an already-ordered sequence makes no second fit; an out-of-order one
# makes exactly one
# =========================================================================== #


def test_ac7_in_order_sequence_zero_refits(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    centroids = _clean_ascending()
    fit = fit_centroid_spline(centroids)
    compute_monotonic_consistency(centroids, fit)
    assert len(calls) == 0


def test_ac7_out_of_order_sequence_exactly_one_refit(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    swapped = _swap(_clean_ascending(), 1, 2)
    fit = fit_centroid_spline(swapped)
    compute_monotonic_consistency(swapped, fit)
    assert len(calls) == 1


# =========================================================================== #
# AC8/AC9: item 130's per-case fit count and closest_u agreement survive
# for in-order input (delegated -- these modules pass UNEDITED)
# =========================================================================== #


def test_ac8_item_130_fit_call_counts_reproduced_unedited(monkeypatch):
    import test_130_one_closest_point_search as t130

    t130.test_ac18_five_level_spine_fits_exactly_six_times(monkeypatch)
    t130.test_ac18_three_level_map_fits_exactly_once(monkeypatch)


def test_ac9_item_130_closest_u_agreement_reproduced_unedited():
    import test_130_one_closest_point_search as t130

    t130.test_ac20_monotonic_and_offset_closest_u_agree_clean()
    t130.test_ac20_monotonic_and_offset_closest_u_agree_displaced()


# =========================================================================== #
# AC10: the reference refit inherits the supplied fit's degree/smoothing
# =========================================================================== #


def test_ac10_refit_inherits_supplied_fit_degree_and_smoothing(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    centroids = _clean_ascending()
    fit = fit_centroid_spline(centroids, degree=2, smoothing=3.0)
    swapped = _swap(centroids, 1, 2)

    compute_monotonic_consistency(swapped, fit)

    assert len(calls) == 1
    _args, kwargs = calls[0]
    assert kwargs.get("degree") == fit.degree == 2
    assert kwargs.get("smoothing") == fit.smoothing == 3.0


# =========================================================================== #
# AC11: an exact S tie does not by itself flag a pair or trigger a refit
# =========================================================================== #


def test_ac11_exact_s_tie_no_refit_still_monotonic(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0), label=1),
        _centroid("L2", (0.0, 0.0, 10.0), label=2),
        _centroid("L3", (5.0, 0.0, 10.0), label=3),
        _centroid("L4", (0.0, 0.0, 20.0), label=4),
        _centroid("L5", (0.0, 0.0, 30.0), label=5),
    ]
    fit = fit_centroid_spline(centroids)

    result = compute_monotonic_consistency(centroids, fit)

    assert len(calls) == 0, "an exact S tie (stable sort keeps input order) must not trigger a refit"
    assert result.is_monotonic is True
    assert result.non_monotonic_pairs == ()


# =========================================================================== #
# AC12: the monotonicity criterion is unchanged (u[i] >= u[i+1], strict >=,
# no tolerance) -- source-level AST fallback (Decisions log)
# =========================================================================== #


def test_ac12_pair_loop_still_uses_gte_not_strict_gt():
    import segfacet.features.consistency as consistency_mod

    source = inspect.getsource(consistency_mod.compute_monotonic_consistency)
    tree = ast.parse(source)

    gte_compares = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.GtE) for op in node.ops)
    ]
    assert gte_compares, (
        "expected a `>=` comparison in compute_monotonic_consistency's pair "
        "loop -- equal u values must still count as a violation"
    )

    gt_compares = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.Gt) for op in node.ops)
    ]
    assert not gt_compares, (
        f"found a strict `>` comparison in compute_monotonic_consistency -- "
        f"this would introduce a tolerance band the item spec's Assumptions "
        f"rules out: {[ast.dump(n) for n in gt_compares]}"
    )


# =========================================================================== #
# AC13/AC14: mode 4 fires mislabel through plain run_qc, verdict
# flagged-for-review
# =========================================================================== #


def test_ac13_mode4_fires_exactly_one_mislabel_finding_on_21_22():
    case_result, _block = _run_qc_case("mode4_relabel_swap")
    assert len(case_result.findings) == 1
    finding = case_result.findings[0]
    assert finding.rule_id == "mislabel"
    assert finding.labels == frozenset({21, 22})
    assert finding.severity is Severity.FLAG
    assert finding.reason.startswith("Vertebra ordering inconsistent with label:")


def test_ac14_mode4_verdict_is_flagged_for_review():
    case_result, _block = _run_qc_case("mode4_relabel_swap")
    assert case_result.verdict.overall.label == "flagged-for-review"


# =========================================================================== #
# AC15: the corpus generator classifies mode 4 as pipeline-detected
# =========================================================================== #


def test_ac15_case_recipe_mode4_is_pipeline_no_reconstruction():
    entry = next(e for e in CASE_RECIPE if e.case_id == "mode4_relabel_swap")
    assert entry.detection == "pipeline"
    assert entry.reconstruction is None


# =========================================================================== #
# AC16/AC17: the committed manifest records the new classification and an
# honest detail string
# =========================================================================== #


def test_ac16_committed_manifest_mode4_is_pipeline_no_reconstruction():
    case = _manifest_case("mode4_relabel_swap")
    assert case["detection"] == "pipeline"
    assert case.get("reconstruction") is None


def test_ac17_committed_manifest_mode4_detail_names_mislabel_not_pipeline_miss():
    case = _manifest_case("mode4_relabel_swap")
    detail = case["detail"]
    assert "Not surfaced by plain run_qc" not in detail
    assert "reconstructed" not in detail
    assert "mislabel" in detail.lower()


# =========================================================================== #
# AC18: the manifest regenerates byte-identically and matches the committed
# file (allowlisted byte-exact family -- see module docstring)
# =========================================================================== #


def test_ac18_manifest_regenerates_byte_identically(tmp_path):
    from segfacet.synth.corpus import MANIFEST_PATH, write_corpus

    dest1 = tmp_path / "run1"
    dest2 = tmp_path / "run2"
    manifest1 = write_corpus(dest1)
    manifest2 = write_corpus(dest2)

    assert manifest1.read_bytes() == manifest2.read_bytes()
    assert manifest1.read_bytes() == MANIFEST_PATH.read_bytes()


# =========================================================================== #
# AC19: the corpus .nii.gz fixtures do not move (allowlisted byte-exact
# family -- see module docstring)
# =========================================================================== #


def test_ac19_fixtures_regenerate_byte_identically(tmp_path):
    from segfacet.synth.corpus import CORPUS_DIR, FIXTURES_DIRNAME, write_corpus

    dest = tmp_path / "run"
    write_corpus(dest)

    fresh_fixtures = sorted((dest / FIXTURES_DIRNAME).glob("*.nii.gz"))
    assert fresh_fixtures, "expected at least one regenerated .nii.gz fixture"
    for fresh in fresh_fixtures:
        committed = CORPUS_DIR / FIXTURES_DIRNAME / fresh.name
        assert fresh.read_bytes() == committed.read_bytes(), fresh.name


# =========================================================================== #
# AC20: the detection partition is reconciled (test_040)
# =========================================================================== #


def test_ac20_test_040_detection_partition_reconciled():
    import test_040_synthetic_corpus as t040

    assert t040._RECONSTRUCTED_MODES == {8}
    assert t040._PIPELINE_ONLY_MODES == {0, 1, 2, 3, 4, 5, 6, 7}
    t040.test_ac8_modes_4_8_reconstructed_record_rest_pipeline()


# =========================================================================== #
# AC21/AC22: mode 4 claimed caught at full sensitivity; honest overall 7/8
# (test_057)
# =========================================================================== #


def test_ac21_test_057_mode4_claimed_caught_at_full_sensitivity():
    import test_057_acceptance_stage7 as t057

    assert 4 in t057._PIPELINE_DETECTABLE_MODES
    assert t057._RECONSTRUCTED_RECORD_MODES == (8,)
    t057.test_ac9_pipeline_detectable_mode_sensitivity_is_one(4)


def test_ac22_overall_corpus_sensitivity_is_seven_of_eight():
    import test_057_acceptance_stage7 as t057

    metrics = t057._corpus_cohort_metrics()
    assert metrics.sensitivity == pytest.approx(7.0 / 8.0)


# =========================================================================== #
# AC23-AC27: reconciled existing-test pins (delegated to the flipped tests)
# =========================================================================== #


def test_ac23_item_125_mode4_pin_flipped():
    import test_125_stage28_validation as t125

    t125.test_ac7_mode4_relabel_swap_is_monotonic_pinned_true()
    t125.test_ac7_mode4_manifest_detection_still_reconstructed_record()


def test_ac24_item_039_mode4_pin_flipped():
    import test_039_identity_ordering_alignment_perturbations as t039

    t039.test_ac11_relabel_swap_run_qc_does_not_surface_swap()


def test_ac25_item_129_pre_findings_baseline_reconciled():
    import test_129_coincident_centroids_and_held_out_floor as t129

    assert t129._PRE_129_FINDINGS["mode4_relabel_swap"] == {("mislabel", (21, 22))}
    t129.test_ac29_no_corpus_case_changes_findings()


def test_ac26_item_098_shared_golden_constant_reconciled():
    import test_098_stray_components as t098

    expected = t098._PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode4_relabel_swap"]
    assert expected["verdict"] == "flagged-for-review"
    assert len(expected["findings"]) == 1
    assert expected["findings"][0]["rule_id"] == "mislabel"
    t098.test_ac15_golden_verdict_and_findings_unchanged("mode4_relabel_swap")


def test_ac27_item_123_detector_a_claim_preserved():
    import test_123_recalibrate_and_regenerate as t123

    t123.test_ac15_mode4_relabel_swap_fires_no_offset_misalignment_finding()


# =========================================================================== #
# AC28: the catalogue text tells the truth about the reference curve
# =========================================================================== #


@pytest.mark.parametrize(
    "path",
    [
        "stage3.monotonic_consistency.is_monotonic",
        "stage3.monotonic_consistency.non_monotonic_pairs[]",
        "stage3.monotonic_consistency.u_values[]",
    ],
)
def test_ac28_computation_strings_state_traversal_ordered_curve(path):
    doc = FEATURE_DOCS[path]
    assert "traversal" in doc.computation.lower(), (
        f"{path}: computation text does not name the traversal-ordered "
        f"reference curve: {doc.computation!r}"
    )


def test_ac28_catalogue_regenerates_byte_identically(tmp_path):
    """Byte-exact fresh-vs-committed comparison, legitimate under item 127's
    committed-artifact guard: both docs/aide/feature_catalogue.generated.*
    carry an allowlist entry (test_040's AC16, test_131's AC15). This item
    adds no new allowlist entry (Assumptions)."""
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert json_dest.read_bytes() == _CATALOGUE_JSON.read_bytes()
    assert md_dest.read_bytes() == _CATALOGUE_MD.read_bytes()


# =========================================================================== #
# AC29: the catalogue's measured content does not move
# =========================================================================== #

_PRE_ITEM_OBSERVED_SUMMARY = {
    "constant-synthetic": 4,
    "degenerate": 0,
    "non-numeric": 39,
    "placeholder": 12,
    "unobserved": 0,
    "varies": 83,
}


def test_ac29_catalogue_measured_content_unchanged(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])
    fresh = json.loads(json_dest.read_text(encoding="utf-8"))

    entries_by_path = {e["path"]: e for g in fresh["groups"] for e in g["entries"]}
    leaf_count = sum(len(g["entries"]) for g in fresh["groups"])

    assert leaf_count == 138, f"leaf-path count {leaf_count} != pre-item 138"
    assert fresh["observed_summary"] == _PRE_ITEM_OBSERVED_SUMMARY

    is_mono = entries_by_path["stage3.monotonic_consistency.is_monotonic"]
    assert is_mono["status"] == "retune"
    assert is_mono["observed"]["verdict"] == "non-numeric"

    pairs_entry = entries_by_path["stage3.monotonic_consistency.non_monotonic_pairs[]"]
    assert pairs_entry["status"] == "keep"
    assert pairs_entry["observed"]["verdict"] == "non-numeric"

    u_entry = entries_by_path["stage3.monotonic_consistency.u_values[]"]
    assert u_entry["status"] == "retune"
    assert u_entry["observed"]["verdict"] == "varies"
    corpus_obs = u_entry["observed"]["corpus"]
    assert corpus_obs["count"] == 24
    assert corpus_obs["minimum"] == pytest.approx(5.6119e-07, abs=1e-11)
    assert corpus_obs["maximum"] == pytest.approx(0.999999, abs=1e-6)
    assert corpus_obs["span"] == pytest.approx(0.999999, abs=1e-6)


# =========================================================================== #
# AC30: signed text (STATUS_OVERRIDES, golden-decision-table.md) is
# untouched
# =========================================================================== #

_PRE_ITEM_STATUS_OVERRIDES = {
    "stage3.monotonic_consistency.is_monotonic": (
        "retune",
        "Should be wired into the sequence rule directly; "
        "sequence-related checks should typically verify order along the "
        "spline parameter, not only label order.",
    ),
    "stage3.monotonic_consistency.u_values[]": (
        "retune",
        "Suspected to already be computed internally to produce "
        "non_monotonic_pairs[]; should be exposed and reused as the "
        "actual intermediate rather than silently recomputed.",
    ),
}


def test_ac30_status_overrides_byte_identical():
    for path, expected in _PRE_ITEM_STATUS_OVERRIDES.items():
        assert path in STATUS_OVERRIDES, f"STATUS_OVERRIDES missing {path!r}"
        assert STATUS_OVERRIDES[path] == expected, (
            f"STATUS_OVERRIDES[{path!r}] changed: {STATUS_OVERRIDES[path]!r} "
            f"!= {expected!r}"
        )


def test_ac30_golden_decision_table_untouched_vs_base():
    """AC30: item 132's diff against its recorded base carries no change to
    ``docs/aide/golden-decision-table.md`` -- the item's Description
    explicitly leaves this document untouched. Uses ``git diff`` against the
    recorded base rather than a hardcoded sha256 fence: the committed-artifact
    guard (item 127) flags a raw fresh-vs-committed byte/hash comparison, and
    this document is deliberately excluded from its allowlist (it is
    read-only prose, never regenerated) -- see
    ``tests/committed_artifact_guard.py``'s module docstring and
    ``test_126``'s ``test_ac22_guard_module_absent_from_this_items_diff`` for
    the same idiom.
    """
    result = None
    for base_ref in ("origin/aide/queue-018", "aide/queue-018"):
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD", "--"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            break
    if result is None or result.returncode != 0:
        pytest.skip(
            f"git diff against the recorded base is unavailable: "
            f"{result.stderr if result else 'no ref resolved'}"
        )
    changed = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    assert "docs/aide/golden-decision-table.md" not in changed, (
        "docs/aide/golden-decision-table.md appears in this item's diff, but "
        "AC30 requires it stay untouched"
    )


# =========================================================================== #
# Adversarial: a swap at the very first pair, and at the very last pair
# =========================================================================== #


def test_adv_first_pair_swap_detected():
    swapped = _swap(_clean_ascending(), 0, 1)
    fit = fit_centroid_spline(swapped)
    result = compute_monotonic_consistency(swapped, fit)
    assert result.is_monotonic is False
    assert frozenset(result.non_monotonic_pairs[0]) == {"L1", "L2"}


def test_adv_last_pair_swap_detected():
    centroids = _clean_ascending(5)
    swapped = _swap(centroids, 3, 4)
    fit = fit_centroid_spline(swapped)
    result = compute_monotonic_consistency(swapped, fit)
    assert result.is_monotonic is False
    assert frozenset(result.non_monotonic_pairs[-1]) == {"L4", "L5"}


# =========================================================================== #
# Adversarial: a genuinely caudally-advancing sequence with a swap
# =========================================================================== #


def _caudal_advancing(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """Ascending labels, DESCENDING S -- the real-VerSe19 convention (net
    advance negative)."""
    return [
        _centroid(f"L{i + 1}", (0.0, 0.0, float(n - 1 - i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def test_adv_caudally_advancing_sequence_swap_still_detected():
    centroids = _caudal_advancing()
    net = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
    assert net < 0.0, "fixture must genuinely advance caudally"

    swapped = _swap(centroids, 1, 2)
    fit = fit_centroid_spline(swapped)
    result = compute_monotonic_consistency(swapped, fit)
    assert result.is_monotonic is False
    assert frozenset(result.non_monotonic_pairs[0]) == {"L2", "L3"}


def test_adv_caudally_advancing_clean_sequence_stays_monotonic():
    centroids = _caudal_advancing()
    fit = fit_centroid_spline(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert result.is_monotonic is True


# =========================================================================== #
# Adversarial: two centroids only (n == 2, both orderings trivial traversal)
# =========================================================================== #


def test_adv_two_centroids_forward_trivial_traversal_no_refit(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    centroids = _clean_ascending(2)
    fit = fit_centroid_spline(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(calls) == 0
    assert result.is_monotonic is True


def test_adv_two_centroids_reversed_trivial_traversal_no_refit(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    centroids = list(reversed(_clean_ascending(2)))
    fit = fit_centroid_spline(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(calls) == 0
    assert result.is_monotonic is True


# =========================================================================== #
# Adversarial: n < 2 still raises ValueError (unchanged contract)
# =========================================================================== #


def test_adv_fewer_than_two_centroids_still_raises_value_error():
    centroids = _clean_ascending(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError):
        compute_monotonic_consistency(centroids[:1], fit)
    with pytest.raises(ValueError):
        compute_monotonic_consistency([], fit)


# =========================================================================== #
# Adversarial: a doubly-swapped seven-level sequence names both pairs
# =========================================================================== #


def test_adv_doubly_swapped_seven_level_names_both_pairs():
    """Two disjoint adjacent swaps (positions 0/1 and 4/5) in a seven-level
    spine -- measured (("L2", "L1"), ("L6", "L5")), per the item spec's
    Testing Strategy adversarial note."""
    base = _clean_ascending(7)
    swapped = _swap(base, 0, 1)
    swapped = _swap(swapped, 4, 5)
    fit = fit_centroid_spline(swapped)

    result = compute_monotonic_consistency(swapped, fit)

    assert result.is_monotonic is False
    assert result.non_monotonic_pairs == (("L2", "L1"), ("L6", "L5"))


# =========================================================================== #
# Adversarial: a scoliotic (large transverse excursion, strictly increasing
# S) shape triggers no refit and stays monotonic
# =========================================================================== #


def test_adv_scoliotic_shape_strictly_monotonic_s_no_refit(monkeypatch):
    calls = _patched_consistency_fit_counter(monkeypatch)
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0), label=1),
        _centroid("L2", (40.0, 0.0, 10.0), label=2),
        _centroid("L3", (60.0, 0.0, 20.0), label=3),
        _centroid("L4", (40.0, 0.0, 30.0), label=4),
        _centroid("L5", (-40.0, 0.0, 40.0), label=5),
    ]
    fit = fit_centroid_spline(centroids)

    result = compute_monotonic_consistency(centroids, fit)

    assert len(calls) == 0
    assert result.is_monotonic is True


# =========================================================================== #
# Adversarial: determinism on both the identity and refit paths
# =========================================================================== #


def test_adv_determinism_identity_path():
    centroids = _clean_ascending()
    fit = fit_centroid_spline(centroids)
    result_a = compute_monotonic_consistency(centroids, fit)
    result_b = compute_monotonic_consistency(centroids, fit)
    assert result_a == result_b


def test_adv_determinism_refit_path():
    swapped = _swap(_clean_ascending(), 1, 2)
    fit = fit_centroid_spline(swapped)
    result_a = compute_monotonic_consistency(swapped, fit)
    result_b = compute_monotonic_consistency(swapped, fit)
    assert result_a == result_b


# =========================================================================== #
# Adversarial: immutability -- input centroids and the supplied SplineFit
# are not mutated
# =========================================================================== #


def test_adv_centroids_and_fit_not_mutated():
    swapped = _swap(_clean_ascending(), 1, 2)
    fit = fit_centroid_spline(swapped)
    centroids_before = list(swapped)
    fit_u_before = tuple(fit.u)

    compute_monotonic_consistency(swapped, fit)

    assert swapped == centroids_before
    assert fit.u == fit_u_before


# =========================================================================== #
# Adversarial: run_qc on mode4_relabel_swap twice is deterministic
# (findings and monotonicity block)
# =========================================================================== #


def test_adv_run_qc_mode4_relabel_swap_deterministic_across_two_calls():
    case_result_a, block_a = _run_qc_case("mode4_relabel_swap")
    case_result_b, block_b = _run_qc_case("mode4_relabel_swap")

    assert block_a["stage3"]["monotonic_consistency"] == block_b["stage3"]["monotonic_consistency"]

    pairs_a = {(f.rule_id, tuple(sorted(f.labels))) for f in case_result_a.findings}
    pairs_b = {(f.rule_id, tuple(sorted(f.labels))) for f in case_result_b.findings}
    assert pairs_a == pairs_b
    assert case_result_a.verdict.overall.label == case_result_b.verdict.overall.label
