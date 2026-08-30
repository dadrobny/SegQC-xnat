"""Tests for item 125 -- Stage 28 validation: the in-suite assertable subset.

Item 125 closes Stage 28 by replaying its use cases end-to-end (gate/decision
reproduction, CLI replays, sweeps, real-VerSe scoliosis measurement, a
fresh-clone byte-reproducibility run, ...). Per the item spec's Testing
Strategy, most of that is a *replay* obligation discharged and recorded in
this item's Decisions log and ``progress.md`` -- not something a pytest module
can assert. This module covers only the subset that *can* be asserted
in-suite:

- AC1:  the spinal-curve-model human gate row parses as ``Approved`` with a
        date, a non-empty decision cell, and names item 119 in ``Blocks``.
- AC4:  ``features/spline.py``'s default smoothing is scale-free (a function
        of point count, not a literal mm^2 constant) and its default
        parameterisation is chord-length, not the cranio-caudal coordinate.
- AC7:  ``mode4_relabel_swap``'s ``is_monotonic``/``non_monotonic_pairs`` are
        pinned to the value MEASURED on this checkout -- ``True`` / ``()`` --
        not the ``False`` the stage's own acceptance criterion wanted. Its
        manifest ``detection`` is confirmed still ``reconstructed_record``.
- AC9:  ``mode1_displace``'s maximum offset exceeds, and ``clean_control``'s
        stays below, the shipped ``mislabel.max_offset_mm`` threshold, by a
        floor margin (not an equality) so float noise cannot fail it.
- AC12: both reference artifacts' ``spline_offset_mm`` statistics clear a
        generous non-degeneracy floor, and ``reference_verse_v1.json``
        records the 80-subject cohort.
- AC15: the manifest's pipeline-detected mode count (excluding the mode-0
        clean control) is 6, agreeing with ``test_040``'s
        ``_PIPELINE_ONLY_MODES``/``_RECONSTRUCTED_MODES`` and ``test_057``'s
        ``_PIPELINE_DETECTABLE_MODES``.
- AC16: ``mode6_crop_at_border`` fires both ``border`` and ``mislabel``
        through plain ``run_qc``, while its manifest ``expected_rule_ids`` is
        ``["border"]`` alone -- the discrepancy asserted as a recorded fact.
- AC17: every Stage 28 acceptance box is ticked-and-annotated or
        unticked-and-reasoned (the tick-implies-evidence biconditional item
        106 established). Expected to FAIL until the builder adds the
        annotations.
- AC19: ``aide.py``'s own ``stray_icon_warnings`` reports nothing new in
        ``docs/aide/progress.md``.

Cohort-gated (skip cleanly, never fail/pass silently, when
``SEGFACET_VERSE_COHORT`` is unset, points at a nonexistent path, or an empty
directory -- the ``_real_verse_root`` + ``requires_real_verse`` pattern
already used by ``tests/test_088_stage13_acceptance.py``,
``tests/test_091_stage14_acceptance.py`` and
``tests/test_118_curve_formulation_decision.py``):

- AC10: the decision document's selection rule
        (``coronal_deviation_mm >= SCOLIOSIS_THRESHOLD_MM``) over the real
        cohort selects the documented count (17 of 80 discovered).
- AC11: every selected scoliotic case is run through the shipped pipeline
        with the shipped config; whichever subjects (if any) fire a
        ``mislabel`` finding are recorded as a tracked fact, and any finding
        that does fire is a genuine over-threshold offset (never a
        spuriously-fired rule) -- the *exact* flagged set, if non-empty, is
        this item's own Decisions-log measurement to add, not invented here.

AC2, AC3, AC5, AC6, AC8, AC13, AC14, AC18, AC20 are replays with no stable
in-suite shape and are intentionally not covered here -- they belong to this
item's Decisions log and the Validation section, not to a test module.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Optional

import nibabel as nib
import pytest

from segfacet.config import bundled_default_config
from segfacet.features.centroids import LabelCentroid
from segfacet.features.spline import fit_centroid_spline
from segfacet.io import load_case
from segfacet.pipeline import run_qc
from segfacet.synth.corpus import CORPUS_DIR, load_manifest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_DOCS_AIDE_DIR = _REPO_ROOT / "docs" / "aide"
_PROGRESS_PATH = _DOCS_AIDE_DIR / "progress.md"
_SPLINE_PATH = _REPO_ROOT / "src" / "segfacet" / "features" / "spline.py"
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"
_COMPARE_SCRIPT_PATH = _REPO_ROOT / "scripts" / "compare_curve_candidates.py"
_REFERENCE_VERSE_PATH = (
    _REPO_ROOT / "src" / "segfacet" / "reference" / "reference_verse_v1.json"
)
_REFERENCE_DEFAULT_PATH = (
    _REPO_ROOT / "src" / "segfacet" / "reference" / "reference_default.json"
)

#: The pre-123 noise floor for spline_offset_mm was ~2.9e-05 mm (item 125
#: spec Description). A generous floor two orders of magnitude above it still
#: clears real spread while never mistaking float noise for it.
_NON_DEGENERACY_FLOOR_MM = 1.0e-3


def _read_progress() -> str:
    return _PROGRESS_PATH.read_text(encoding="utf-8")


def _read_manifest() -> dict:
    return load_manifest()


def _manifest_case(case_id: str) -> dict:
    for case in _read_manifest()["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _resolve_fixture(case: dict, key: str) -> Path:
    return CORPUS_DIR / case[key]


def _loaded_seg_img(case_id: str):
    """A fresh nib.Nifti1Image built from the Stage-0-loaded seg's data/affine
    for the named manifest case -- mirrors test_040's ``_seg_nifti_from_case``
    so run_qc exercises exactly the loader's own output."""
    case = _manifest_case(case_id)
    loaded = load_case(_resolve_fixture(case, "scan_fixture"), _resolve_fixture(case, "seg_fixture"))
    seg = loaded.seg
    return nib.Nifti1Image(seg.data, seg.affine, dtype=seg.data.dtype)


def _run_qc(case_id: str):
    case_result, block = run_qc(_loaded_seg_img(case_id), bundled_default_config())
    return case_result, block


def _max_offset_mm(block: dict) -> float:
    offsets = block["stage3"]["per_label_offsets"]
    assert offsets, "expected at least one per-label offset entry"
    values = [o["offset_mm"] for o in offsets]
    assert values, "expected at least one offset_mm value"
    return max(values)


def _aide_module():
    spec = importlib.util.spec_from_file_location("_aide_cli_125", _AIDE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _centroid(level_name: str, mm: tuple, label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int) -> list:
    levels = [f"L{i}" for i in range(n)]
    return [_centroid(levels[i], (0.0, 0.0, float(i) * 10.0), label=i + 1) for i in range(n)]


# =========================================================================== #
# AC1: the gate row parses as Approved, with a date, a decision cell, and 119
# in Blocks.
# =========================================================================== #

_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _table_row(text: str, needle: str) -> str:
    for line in text.splitlines():
        if line.startswith("|") and needle in line:
            return line
    raise AssertionError(f"no table row containing {needle!r} found in progress.md")


def _row_cells(row_line: str) -> list:
    stripped = row_line.strip()
    assert stripped.startswith("|") and stripped.endswith("|"), row_line
    return [c.strip() for c in stripped[1:-1].split("|")]


def _gate_row_is_approved_with_date(cells: list) -> bool:
    status_cell = cells[2]
    return status_cell.startswith("✅ Approved") and bool(_DATE_RE.search(status_cell))


def test_ac1_gate_row_status_approved_with_date():
    row = _table_row(_read_progress(), "Spinal curve model")
    cells = _row_cells(row)
    assert len(cells) == 4, cells
    assert _gate_row_is_approved_with_date(cells), cells[2]


def test_ac1_gate_row_names_119_in_blocks():
    row = _table_row(_read_progress(), "Spinal curve model")
    cells = _row_cells(row)
    blocks_cell = cells[1]
    assert "119" in blocks_cell, blocks_cell


def test_ac1_gate_row_decision_cell_nonempty():
    row = _table_row(_read_progress(), "Spinal curve model")
    cells = _row_cells(row)
    decision_cell = cells[3]
    assert decision_cell.strip(), "expected a non-empty decision/evidence cell"


def test_adv_gate_row_awaiting_status_fails_ac1_check():
    """Adversarial (spec-named): a gate row whose status cell is
    '⏳ Awaiting' must fail the AC1 approved-with-date check."""
    synthetic_row = "| Some gate | 119 | ⏳ Awaiting | Some decision text |"
    cells = _row_cells(synthetic_row)
    assert not _gate_row_is_approved_with_date(cells)


# =========================================================================== #
# AC4: the shipped fit is the decided fit -- no s=0 default, scale-free
# smoothing, chord-length parameterisation.
# =========================================================================== #

_SCALE_FREE_DEFAULT_RE = re.compile(
    r"s\s*=\s*float\(n_points\)\s+if\s+smoothing\s+is\s+None\s+else\s+float\(smoothing\)"
)
_BARE_NUMERIC_DEFAULT_RE = re.compile(
    r"s\s*=\s*[0-9][0-9.]*\s+if\s+smoothing\s+is\s+None"
)
_LITERAL_S_KWARG_RE = re.compile(r'"s"\s*:\s*[0-9][0-9.]*\s*[,}]')


def _default_smoothing_is_scale_free(source: str) -> bool:
    """True iff *source* resolves its default smoothing factor as a function
    of the point count (``float(n_points)``), not a bare numeric literal, and
    never passes a hardcoded numeric literal as the ``"s"`` make_splprep
    kwarg."""
    if not _SCALE_FREE_DEFAULT_RE.search(source):
        return False
    if _BARE_NUMERIC_DEFAULT_RE.search(source):
        return False
    if _LITERAL_S_KWARG_RE.search(source):
        return False
    return True


def test_ac4_spline_source_default_smoothing_is_scale_free():
    source = _SPLINE_PATH.read_text(encoding="utf-8")
    assert _default_smoothing_is_scale_free(source)


def test_ac4_spline_source_has_no_s_equals_zero_default():
    source = _SPLINE_PATH.read_text(encoding="utf-8")
    # s=0 is a legitimate *explicit* override (an interpolating baseline the
    # comparison script opts into) but must never be the unconditional
    # default resolution.
    assert "s = 0 if smoothing is None" not in source
    assert "s = 0.0 if smoothing is None" not in source


def test_ac4_default_smoothing_scales_with_point_count_not_a_constant():
    fit_5 = fit_centroid_spline(_straight_spine(5))
    fit_9 = fit_centroid_spline(_straight_spine(9))
    assert fit_5.smoothing == pytest.approx(5.0)
    assert fit_9.smoothing == pytest.approx(9.0)
    assert fit_5.smoothing != fit_9.smoothing


def test_ac4_default_parameterisation_is_chord_length_not_cranio_caudal():
    """Four centroids whose z-coordinate (cranio-caudal) is evenly spaced but
    whose chord length is not (a large lateral jump between points 1 and 2):
    a cranio-caudal parameterisation would give evenly-spaced u values
    (0, 1/3, 2/3, 1); the decided chord-length parameterisation must not."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0), label=1),
        _centroid("L2", (0.0, 0.0, 1.0), label=2),
        _centroid("L3", (10.0, 0.0, 2.0), label=3),
        _centroid("L4", (10.0, 0.0, 3.0), label=4),
    ]
    fit = fit_centroid_spline(centroids, smoothing=0.0)
    u = fit.u
    assert len(u) == 4
    cranio_caudal_u = (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)
    # A genuinely chord-length parameterisation must diverge sharply from the
    # evenly-spaced cranio-caudal values at the interior points (a large
    # lateral jump inflates the chord length between points 1 and 2, pushing
    # u[1] well below 1/3 and u[2] well above 2/3).
    assert abs(u[1] - cranio_caudal_u[1]) > 0.1, (u, cranio_caudal_u)
    assert abs(u[2] - cranio_caudal_u[2]) > 0.1, (u, cranio_caudal_u)


def test_adv_synthetic_bare_s_zero_default_fails_the_scale_free_check():
    """Adversarial (spec-named): a synthetic reintroduction of an
    interpolating ``s=0`` (or a bare ``s=1.0``) default must fail the AC4
    scale-free checker."""
    regressed_zero = (
        "    s = 0 if smoothing is None else float(smoothing)\n"
        '    make_splprep_kwargs = {"k": effective_degree, "s": s}\n'
    )
    assert not _default_smoothing_is_scale_free(regressed_zero)

    regressed_one = (
        "    s = 1.0 if smoothing is None else float(smoothing)\n"
        '    make_splprep_kwargs = {"k": effective_degree, "s": s}\n'
    )
    assert not _default_smoothing_is_scale_free(regressed_one)

    regressed_literal_kwarg = (
        "    s = float(n_points) if smoothing is None else float(smoothing)\n"
        '    make_splprep_kwargs = {"k": effective_degree, "s": 15.0}\n'
    )
    assert not _default_smoothing_is_scale_free(regressed_literal_kwarg)


# =========================================================================== #
# AC7: mode 4's monotonicity is measured and pinned, not assumed.
# =========================================================================== #


def test_ac7_mode4_relabel_swap_is_monotonic_pinned_true():
    """Pin on the OBSERVATION, not the wish: the stage's own acceptance
    criterion wanted ``is_monotonic is False`` on this case (a smoothed fit
    detecting the swap). Measured 2026-08-30 through plain run_qc it is
    ``True`` with zero non-monotonic pairs -- this test records that reality
    so a later, silent change to it is visible rather than swallowed. If this
    ever starts failing because ``is_monotonic`` became ``False``, that is
    GOOD news for Stage 28's acceptance -- update the pin, don't just widen
    it."""
    _case_result, block = _run_qc("mode4_relabel_swap")
    mono = block["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is True
    # non_monotonic_pairs is serialised as a list of two-element lists
    # (feature_report.monotonic_consistency_to_dict), not a tuple.
    assert mono["non_monotonic_pairs"] == []


def test_ac7_mode4_manifest_detection_still_reconstructed_record():
    case = _manifest_case("mode4_relabel_swap")
    assert case["detection"] == "reconstructed_record"


def test_ac7_mode4_run_qc_is_deterministic_across_two_calls():
    """Adversarial (spec-named): two run_qc calls on the same fixture return
    equal offsets and equal monotonicity."""
    _cr1, block1 = _run_qc("mode4_relabel_swap")
    _cr2, block2 = _run_qc("mode4_relabel_swap")
    assert block1["stage3"]["monotonic_consistency"] == block2["stage3"]["monotonic_consistency"]
    assert _max_offset_mm(block1) == pytest.approx(_max_offset_mm(block2))


# =========================================================================== #
# AC9: a displaced vertebra separates from clean by a stated (floor) margin.
# =========================================================================== #


def test_ac9_mode1_displace_exceeds_threshold_and_clean_control_stays_below():
    config = bundled_default_config()
    max_offset_mm = config.rule_param("mislabel", "max_offset_mm", default=None)
    assert max_offset_mm is not None, "expected a shipped mislabel.max_offset_mm"

    _cr_mode1, block_mode1 = _run_qc("mode1_displace")
    _cr_clean, block_clean = _run_qc("clean_control")

    mode1_max = _max_offset_mm(block_mode1)
    clean_max = _max_offset_mm(block_clean)

    assert mode1_max > max_offset_mm
    assert clean_max < max_offset_mm
    # A floor, not an equality -- measured 2026-08-30 as 18.7186 vs 0.6733 mm
    # (a ~18 mm margin); a floor two orders of magnitude smaller than that
    # still proves genuine separation without breaking on ordinary float
    # noise or a later re-tune of the smoothing parameter.
    assert (mode1_max - clean_max) > 5.0


def test_ac9_clean_control_fires_no_mislabel_finding():
    case_result, _block = _run_qc("clean_control")
    assert not any(f.rule_id == "mislabel" for f in case_result.findings)


# =========================================================================== #
# AC12: both reference artifacts derive from real GT and carry real spread.
# =========================================================================== #


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _spline_offset_stats(reference: dict):
    """Yield every level's ``spline_offset_mm`` stats block across all
    recorded strata."""
    for level_name, strata in reference["levels"].items():
        for stratum_name, entry in strata.items():
            stats = entry.get("feature_stats", {}).get("spline_offset_mm")
            if stats is not None:
                yield level_name, stratum_name, stats


def test_ac12_reference_verse_v1_subject_count_is_80():
    reference = _load_json(_REFERENCE_VERSE_PATH)
    assert reference["subject_count"] == 80


def test_ac12_reference_verse_v1_spline_offset_mm_clears_non_degeneracy_floor():
    reference = _load_json(_REFERENCE_VERSE_PATH)
    stats_blocks = list(_spline_offset_stats(reference))
    assert stats_blocks, "expected at least one spline_offset_mm stats block"
    for level_name, stratum_name, stats in stats_blocks:
        assert stats["mean"] > _NON_DEGENERACY_FLOOR_MM, (level_name, stratum_name, stats)
        assert stats["max"] >= stats["mean"], (level_name, stratum_name, stats)


def test_ac12_reference_default_spline_offset_mm_clears_non_degeneracy_floor():
    reference = _load_json(_REFERENCE_DEFAULT_PATH)
    stats_blocks = list(_spline_offset_stats(reference))
    assert stats_blocks, "expected at least one spline_offset_mm stats block"
    for level_name, stratum_name, stats in stats_blocks:
        assert stats["mean"] > _NON_DEGENERACY_FLOOR_MM, (level_name, stratum_name, stats)


# =========================================================================== #
# AC15: the before/after detection count -- 6 of 8 modes pipeline-detected
# excluding the mode-0 clean control -- agrees with test_040/test_057.
# =========================================================================== #


def _pipeline_detected_modes_excluding_clean_control() -> set:
    manifest = _read_manifest()
    return {
        c["failure_mode"]
        for c in manifest["cases"]
        if c["detection"] == "pipeline" and c["failure_mode"] != 0
    }


def test_ac15_manifest_pipeline_detected_mode_count_is_six():
    modes = _pipeline_detected_modes_excluding_clean_control()
    assert len(modes) == 6, modes
    assert modes == {1, 2, 3, 5, 6, 7}


def test_ac15_agrees_with_test_040_mode_sets():
    import test_040_synthetic_corpus as t040

    manifest_pipeline_modes = _pipeline_detected_modes_excluding_clean_control()
    assert manifest_pipeline_modes == t040._PIPELINE_ONLY_MODES - {0}
    manifest_reconstructed_modes = {
        c["failure_mode"]
        for c in _read_manifest()["cases"]
        if c["detection"] == "reconstructed_record"
    }
    assert manifest_reconstructed_modes == t040._RECONSTRUCTED_MODES


def test_ac15_agrees_with_test_057_pipeline_detectable_modes():
    import test_057_acceptance_stage7 as t057

    manifest_pipeline_modes = _pipeline_detected_modes_excluding_clean_control()
    assert manifest_pipeline_modes == set(t057._PIPELINE_DETECTABLE_MODES)


# =========================================================================== #
# AC16: the mode-6 co-firing is recorded, not fixed.
# =========================================================================== #


def test_ac16_mode6_fires_both_border_and_mislabel():
    case_result, _block = _run_qc("mode6_crop_at_border")
    rule_ids = {f.rule_id for f in case_result.findings}
    assert "border" in rule_ids, rule_ids
    assert "mislabel" in rule_ids, rule_ids


def test_ac16_mode6_manifest_expected_rule_ids_is_border_alone():
    case = _manifest_case("mode6_crop_at_border")
    assert case["expected_rule_ids"] == ["border"]


# =========================================================================== #
# AC17: Stage 28's acceptance is ticked honestly (tick-implies-evidence).
# =========================================================================== #

_CHECKBOX_RE = re.compile(r"^-\s*\[([ xX])\]\s?")
_EVIDENCE_NOTE_RE = re.compile(r"\*\(.*?\)\*", re.DOTALL)


def _stage28_section(text: str) -> str:
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## Stage 28"):
            start = i
        elif start is not None and line.startswith("## Stage ") and i > start:
            end = i
            break
    if start is None:
        raise AssertionError("no '## Stage 28' heading found in progress.md")
    return "\n".join(lines[start:end])


def _acceptance_items(section: str) -> list:
    """Every checkbox item under '**Acceptance.**', including wrapped
    continuation lines (item 106's ``_acceptance_items`` convention)."""
    lines = section.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "**Acceptance.**")
    except StopIteration:
        raise AssertionError(
            "no '**Acceptance.**' heading found under the Stage-28 section of progress.md"
        )
    items: list = []
    current: list = []
    seen_item = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if _CHECKBOX_RE.match(stripped):
            if current:
                items.append("\n".join(current))
            current = [line]
            seen_item = True
            continue
        if stripped == "" or stripped == "---":
            if current:
                items.append("\n".join(current))
                current = []
            if seen_item:
                break
            continue
        if current:
            current.append(line)
    if current:
        items.append("\n".join(current))
    return items


def _has_annotation(item_text: str) -> bool:
    return bool(_EVIDENCE_NOTE_RE.search(item_text))


def _biconditional_violations(section: str) -> list:
    violations = []
    for item in _acceptance_items(section):
        if not _has_annotation(item):
            violations.append(item.splitlines()[0].strip())
    return violations


def test_ac17_stage28_has_five_acceptance_boxes():
    section = _stage28_section(_read_progress())
    items = _acceptance_items(section)
    assert len(items) == 5, items


def test_ac17_every_stage28_box_ticked_implies_evidence_or_unticked_implies_reason():
    """AC17: expected to FAIL until every box carries an evidence/reason
    annotation -- at spec time only the second box (the 1.0 mm bound, which
    carries an unrelated historical note on why the bound was raised) has a
    trailing ``*(...)*``; the other four have none."""
    section = _stage28_section(_read_progress())
    violations = _biconditional_violations(section)
    assert violations == [], (
        f"Stage 28 acceptance box(es) with no evidence/reason annotation: {violations}"
    )


def test_adv_stage28_ticked_box_with_no_annotation_is_flagged():
    synthetic_section = (
        "## Stage 28 — Spinal Curve Model: Formulation, Offset & Orientation (G2, G7) — 🚧\n\n"
        "**Acceptance.**\n\n"
        "- [x] A clean GT spine stays within a 1.0 mm pass-through bound.\n"
    )
    violations = _biconditional_violations(synthetic_section)
    assert violations, "expected the annotation-less ticked box to be flagged"


def test_adv_stage28_unticked_box_with_reason_is_not_flagged():
    synthetic_section = (
        "## Stage 28 — Spinal Curve Model: Formulation, Offset & Orientation (G2, G7) — 🚧\n\n"
        "**Acceptance.**\n\n"
        "- [ ] A clean GT spine stays within a 1.0 mm pass-through bound. "
        "*(Unticked: not verified in this environment.)*\n"
    )
    violations = _biconditional_violations(synthetic_section)
    assert violations == []


# =========================================================================== #
# AC19: `aide check`'s stray-icon lint reports nothing new.
# =========================================================================== #


def test_ac19_no_stray_status_icon_warnings_in_docs_aide():
    aide = _aide_module()
    warnings = aide.stray_icon_warnings(_DOCS_AIDE_DIR)
    assert warnings == [], warnings


# =========================================================================== #
# AC10/AC11 (cohort-gated): real VerSe scoliosis selection and G3 measurement.
# =========================================================================== #


def real_verse_cohort_dir() -> Optional[Path]:
    """The real VerSe19 root from ``SEGFACET_VERSE_COHORT`` iff set AND a
    directory, else ``None`` -- byte-for-byte the items 084/088/091/118
    contract."""
    raw = os.environ.get("SEGFACET_VERSE_COHORT")
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.is_dir() else None


requires_verse = pytest.mark.skipif(
    real_verse_cohort_dir() is None,
    reason="real VerSe19 cohort not mounted (set SEGFACET_VERSE_COHORT to the VerSe19 root)",
)


def _load_compare_script():
    spec = importlib.util.spec_from_file_location(
        "compare_curve_candidates_125", _COMPARE_SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _selected_scoliotic_masks(mod, root: Path):
    mask_paths, discovery_reason = mod._discover_verse_masks(root)
    assert discovery_reason is None, discovery_reason
    assert mask_paths, "expected at least one discovered VerSe mask"
    selected = []
    for mask_path in mask_paths:
        centroids = mod._load_verse_case_centroids(mask_path)
        if centroids is None:
            continue
        if mod._coronal_deviation_mm(centroids) >= mod.SCOLIOSIS_THRESHOLD_MM:
            selected.append(mask_path)
    return mask_paths, selected


@requires_verse
def test_ac10_scoliotic_selection_reproduces_documented_count():
    root = real_verse_cohort_dir()
    mod = _load_compare_script()
    all_masks, selected = _selected_scoliotic_masks(mod, root)
    assert len(all_masks) == 80, len(all_masks)
    assert len(selected) == 17, [mod._case_stem(p) for p in selected]


@requires_verse
def test_ac11_scoliotic_cases_mislabel_flagging_is_measured_and_recorded():
    root = real_verse_cohort_dir()
    mod = _load_compare_script()
    _all_masks, selected = _selected_scoliotic_masks(mod, root)
    assert selected, "expected at least one selected scoliotic case"

    config = bundled_default_config()
    max_offset_mm = config.rule_param("mislabel", "max_offset_mm", default=None)
    assert max_offset_mm is not None

    flagged = {}
    for mask_path in selected:
        seg_img = nib.load(str(mask_path))
        case_result, block = run_qc(seg_img, config)
        mislabel_findings = [f for f in case_result.findings if f.rule_id == "mislabel"]
        if mislabel_findings:
            flagged[mod._case_stem(mask_path)] = _max_offset_mm(block)

    # Whichever shape this measures, it must never be a silently wrong shape:
    # every case actually flagged must genuinely clear the shipped threshold
    # (the rule cannot have fired below it) -- recorded here as a tracked
    # fact per AC11, not remedied. If this is non-empty on a given run, the
    # exact flagged-subject set becomes this item's own Decisions-log
    # measurement.
    for case_id, observed_max in flagged.items():
        assert observed_max > max_offset_mm, (case_id, observed_max, max_offset_mm)


# =========================================================================== #
# Adversarial: cohort-gated tests skip cleanly, never fail/pass, for an
# unset, nonexistent, or empty-directory SEGFACET_VERSE_COHORT; env hygiene
# is restored after monkeypatching (test_091/test_118's convention).
# =========================================================================== #


def test_adv_verse_cohort_dir_none_when_env_unset(monkeypatch):
    monkeypatch.delenv("SEGFACET_VERSE_COHORT", raising=False)
    assert real_verse_cohort_dir() is None


def test_adv_verse_cohort_dir_none_when_env_points_at_nonexistent_path(monkeypatch, tmp_path):
    nonexistent = tmp_path / "does-not-exist"
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(nonexistent))
    assert real_verse_cohort_dir() is None


def test_adv_verse_cohort_dir_present_for_an_existing_empty_directory(monkeypatch, tmp_path):
    """An empty (but existing) directory is a real directory as far as
    ``real_verse_cohort_dir`` is concerned -- ``_discover_verse_masks``
    (exercised only inside the ``requires_verse``-gated tests above) is what
    turns 'exists but holds no masks' into a clean skip/None, not this
    helper. This pins that division of responsibility."""
    empty_dir = tmp_path / "empty-cohort"
    empty_dir.mkdir()
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(empty_dir))
    assert real_verse_cohort_dir() == empty_dir


def test_adv_verse_cohort_env_hygiene_restored_after_monkeypatch(monkeypatch, tmp_path):
    baseline = os.environ.get("SEGFACET_VERSE_COHORT")
    with monkeypatch.context() as m:
        m.setenv("SEGFACET_VERSE_COHORT", str(tmp_path))
        assert os.environ.get("SEGFACET_VERSE_COHORT") == str(tmp_path)
    # Outside the context manager, the monkeypatch is undone -- the variable
    # is restored to exactly its pre-test value, not merely "not tmp_path".
    assert os.environ.get("SEGFACET_VERSE_COHORT") == baseline
