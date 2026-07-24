"""Tests for item 089 — FOV-aware ``coverage`` and ``border`` rules.

Covers all 17 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:  ``derive_fov_coverage`` reports the covered-span ends and their
        truncation.
- AC2:  A span end sitting inside the volume is reported not-truncated.
- AC3:  The helper is conservative on a degenerate record.
- AC4:  The helper is pure and deterministic.
- AC5:  A genuinely missing interior level still fires (coverage).
- AC6:  An interior gap is never FOV-suppressed, even beside a clipped end.
- AC7:  A clean partial-FOV scan fires no coverage finding (default config).
- AC8:  An out-of-FOV expected level beyond a truncated end is not flagged.
- AC9:  An expected level immediately beyond a non-truncated end IS flagged.
- AC10: Expected levels far beyond a non-truncated end are not flagged.
- AC11: ``border_aware: false`` reverts to legacy behaviour.
- AC12: A clean partial-FOV scan fires no border finding (default config).
- AC13: An in-plane touch on a terminal vertebra still fires.
- AC14: An interior vertebra touching a cranio-caudal face still fires.
- AC15: ``border`` and ``coverage`` agree on the covered-span ends.
- AC16: The default path is behaviour-preserving — Stage-5 goldens are
        unaffected for ``coverage`` / ``border`` findings.
- AC17: Neither rule mutates the record and both stay deterministic.

Adversarial / edge-case scenarios included:
- Single-present-level record (has_span still derivable; no crash).
- Span end whose geometry/level_name is missing from per_label (conservative
  not-truncated).
- expected_levels containing the adjacent level on both a truncated and a
  non-truncated end in one record (only the non-truncated end fires).
- A transitional level (T13/L6) as the immediately-adjacent beyond-end
  canonical neighbour (no crash).
- ``border_aware: false`` with a non-truncated end (legacy flags all).
- Severity override / unrecognised-severity ``ValueError`` regression for
  both rules.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segfacet.heuristics.border  # noqa: F401 -- triggers BorderRule registration
import segfacet.heuristics.coverage  # noqa: F401 -- triggers CoverageRule registration
from segfacet.heuristics import run_rules
from segfacet.heuristics.fov import derive_fov_coverage
from segfacet.heuristics.rule import _RULES
from segfacet.config import (
    SUPPORTED_SCHEMA_VERSION,
    default_config,
    load_config,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

_ALL_FACES = (
    "touches_superior",
    "touches_inferior",
    "touches_left",
    "touches_right",
    "touches_anterior",
    "touches_posterior",
)


def _geometry(touched_faces=()) -> dict:
    """Six touches_* flags, defaulting False except the named *touched_faces*."""
    return {face: (face in touched_faces) for face in _ALL_FACES}


def _entry(label: int, level_name: str, touched_faces=()) -> dict:
    """Build a minimal per_label entry carrying label/level_name/geometry."""
    return {
        "label": label,
        "level_name": level_name,
        "geometry": _geometry(touched_faces),
    }


def _record(present_levels: list, missing_levels: list = (), entries: list = ()) -> dict:
    """Assemble a minimal build_features_block-shaped record: relationships
    carries present_levels/missing_levels (item 014 shape), per_label is
    keyed by each entry's integer label (item 016 shape)."""
    return {
        "relationships": {
            "present_levels": list(present_levels),
            "missing_levels": list(missing_levels),
            "is_continuous": len(missing_levels) == 0,
            "out_of_order_labels": [],
        },
        "per_label": {e["label"]: e for e in entries},
        "overlaps": {},
    }


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _coverage_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  coverage:\n"
        "    params:\n"
    )


def _levels_yaml_list(levels: list, indent: str = "      ") -> str:
    lines = [f"{indent}expected_levels:\n"]
    for lvl in levels:
        lines.append(f"{indent}  - {lvl}\n")
    return "".join(lines)


def _cov_findings(findings):
    return [f for f in findings if f.rule_id == "coverage"]


def _border_findings(findings):
    return [f for f in findings if f.rule_id == "border"]


def _by_tag(findings, tag: str):
    return [f for f in findings if f.reason.startswith(tag)]


_INTERIOR_TAG = "Missing interior level(s):"
_SPAN_TAG = "Incomplete coverage (span):"
_UNEXPECTED_CLIP_TAG = "Partial vertebra clipped by FOV:"


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'coverage' and 'border')
    and restore after -- mirrors items 029/031."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: derive_fov_coverage reports the covered-span ends and their truncation
# =========================================================================== #


def test_ac1_derive_fov_coverage_reports_ends_and_truncation():
    """AC1: present_levels == ['T5', 'T6', 'T7'] with T5 touching superior and
    T7 touching inferior yields a fully-truncated descriptor naming both ends."""
    entries = [
        _entry(1, "T5", touched_faces=("touches_superior",)),
        _entry(2, "T6"),
        _entry(3, "T7", touched_faces=("touches_inferior",)),
    ]
    record = _record(["T5", "T6", "T7"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.superior_end_level == "T5"
    assert fov.inferior_end_level == "T7"
    assert fov.superior_truncated is True
    assert fov.inferior_truncated is True
    assert fov.has_span is True


# =========================================================================== #
# AC2: A span end sitting inside the volume is reported not-truncated
# =========================================================================== #


def test_ac2_non_truncated_end_reported_false():
    """AC2: T5 not touching superior (headroom above) while T7 touches
    inferior yields superior_truncated == False, inferior_truncated == True."""
    entries = [
        _entry(1, "T5"),
        _entry(2, "T6"),
        _entry(3, "T7", touched_faces=("touches_inferior",)),
    ]
    record = _record(["T5", "T6", "T7"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.superior_truncated is False
    assert fov.inferior_truncated is True


# =========================================================================== #
# AC3: The helper is conservative on a degenerate record
# =========================================================================== #


def test_ac3_relationships_none_conservative_no_raise():
    """AC3: relationships None yields has_span False, both flags False."""
    record = {"relationships": None, "per_label": {}, "overlaps": {}}
    fov = derive_fov_coverage(record)
    assert fov.has_span is False
    assert fov.superior_truncated is False
    assert fov.inferior_truncated is False


def test_ac3_relationships_absent_conservative_no_raise():
    """AC3: record with no 'relationships' key at all."""
    record = {"per_label": {}, "overlaps": {}}
    fov = derive_fov_coverage(record)
    assert fov.has_span is False
    assert fov.superior_truncated is False
    assert fov.inferior_truncated is False


def test_ac3_present_levels_empty_conservative_no_raise():
    """AC3: present_levels == [] yields has_span False."""
    record = _record([], [], [])
    fov = derive_fov_coverage(record)
    assert fov.has_span is False
    assert fov.superior_truncated is False
    assert fov.inferior_truncated is False


def test_ac3_empty_per_label_conservative_no_raise():
    """AC3: an empty per_label with a non-empty present span does not crash
    and both flags default to not-truncated."""
    record = {
        "relationships": {"present_levels": ["L1", "L2"], "missing_levels": []},
        "per_label": {},
        "overlaps": {},
    }
    fov = derive_fov_coverage(record)
    assert fov.superior_end_level == "L1"
    assert fov.inferior_end_level == "L2"
    assert fov.superior_truncated is False
    assert fov.inferior_truncated is False


def test_ac3_missing_span_end_entry_conservative_not_truncated():
    """AC3: a span-end level with no matching per_label entry (name mismatch)
    yields *_truncated == False -- conservative, surfaces rather than hides."""
    entries = [_entry(1, "SOME_OTHER_LEVEL", touched_faces=("touches_superior",))]
    record = _record(["L1", "L2"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.superior_truncated is False
    assert fov.inferior_truncated is False


# =========================================================================== #
# AC4: The helper is pure and deterministic
# =========================================================================== #


def test_ac4_two_calls_return_equal_descriptors():
    """AC4: Two calls on the same record return equal descriptors."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(3, "L3", touched_faces=("touches_inferior",)),
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    fov1 = derive_fov_coverage(record)
    fov2 = derive_fov_coverage(record)
    assert fov1 == fov2


def test_ac4_record_unmutated_by_helper():
    """AC4: A deep before/after comparison shows the record is unmutated."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(3, "L3", touched_faces=("touches_inferior",)),
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    record_before = copy.deepcopy(record)
    derive_fov_coverage(record)
    assert record == record_before


# =========================================================================== #
# AC5: A genuinely missing interior level still fires (§6 mode 5 unchanged)
# =========================================================================== #


def test_ac5_interior_gap_fires_exactly_one_finding():
    """AC5: missing_levels == ['L3'] (interior gap) emits exactly one
    missing-interior Finding naming L3, case-level labels."""
    entries = [
        _entry(1, "L1"),
        _entry(2, "L2"),
        _entry(4, "L4"),
        _entry(5, "L5"),
    ]
    record = _record(["L1", "L2", "L4", "L5"], ["L3"], entries)
    interior = _by_tag(_cov_findings(run_rules(record, default_config())), _INTERIOR_TAG)
    assert len(interior) == 1
    assert interior[0].rule_id == "coverage"
    assert "L3" in interior[0].reason
    assert interior[0].labels == frozenset()


# =========================================================================== #
# AC6: An interior gap is never FOV-suppressed, even beside a clipped end
# =========================================================================== #


def test_ac6_interior_gap_beside_truncated_end_still_fires():
    """AC6: An interior gap whose superior-most present level touches the
    superior border still fires -- FOV logic never suppresses interior gaps."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(4, "L4"),
    ]
    record = _record(["L1", "L2", "L4"], ["L3"], entries)
    interior = _by_tag(_cov_findings(run_rules(record, default_config())), _INTERIOR_TAG)
    assert len(interior) == 1
    assert "L3" in interior[0].reason


# =========================================================================== #
# AC7: A clean partial-FOV scan fires no coverage finding (default config)
# =========================================================================== #


@pytest.mark.parametrize(
    "present_levels,superior_truncated,inferior_truncated",
    [
        (["C1", "C2", "C3", "C4", "C5", "C6", "C7"], True, False),
        (["L1", "L2", "L3", "L4", "L5"], False, True),
        (["T5", "T6", "T7", "T8", "T9"], True, True),
    ],
    ids=["cervical_only", "lumbar_only", "mid_thoracic"],
)
def test_ac7_clean_partial_fov_scan_no_coverage_finding(
    present_levels, superior_truncated, inferior_truncated
):
    """AC7: A contiguous partial-FOV present span with missing_levels == []
    and the extremal present levels touching their FOV-end faces fires no
    coverage finding under default_config()."""
    entries = []
    for i, level in enumerate(present_levels):
        touched = []
        if i == 0 and superior_truncated:
            touched.append("touches_superior")
        if i == len(present_levels) - 1 and inferior_truncated:
            touched.append("touches_inferior")
        entries.append(_entry(i + 1, level, touched_faces=tuple(touched)))
    record = _record(present_levels, [], entries)
    findings = _cov_findings(run_rules(record, default_config()))
    assert findings == [], f"Clean partial-FOV scan should fire nothing; got {findings}"


# =========================================================================== #
# AC8: An out-of-FOV expected level beyond a truncated end is not flagged
# =========================================================================== #


def test_ac8_beyond_truncated_end_not_flagged(tmp_path):
    """AC8: expected_levels extends beyond the present span (present L1..L5,
    expected T12..L5) with the superior end truncated -- no incomplete-span
    finding for the out-of-FOV levels."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(3, "L3"),
        _entry(4, "L4"),
        _entry(5, "L5"),
    ]
    record = _record(["L1", "L2", "L3", "L4", "L5"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["T12", "T13", "L1", "L2", "L3", "L4", "L5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert span == [], f"Beyond a truncated end nothing should fire; got {span}"


# =========================================================================== #
# AC9: An expected level immediately beyond a non-truncated end IS flagged
# =========================================================================== #


def test_ac9_adjacent_beyond_non_truncated_end_flagged(tmp_path):
    """AC9: Same expected_levels as AC8/AC10 but the superior end is NOT
    truncated (headroom) -- the immediately-adjacent absent expected level
    (T13) is flagged."""
    entries = [
        _entry(1, "L1"),  # not touching superior -- headroom above
        _entry(2, "L2"),
        _entry(3, "L3"),
        _entry(4, "L4"),
        _entry(5, "L5"),
    ]
    record = _record(["L1", "L2", "L3", "L4", "L5"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["T11", "T12", "T13", "L1", "L2", "L3", "L4", "L5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert len(span) == 1
    assert "T13" in span[0].reason


# =========================================================================== #
# AC10: Expected levels far beyond a non-truncated end are not flagged
# =========================================================================== #


def test_ac10_far_beyond_non_truncated_end_not_flagged(tmp_path):
    """AC10: In the AC9 configuration, T11/T12 (more than one canonical step
    beyond the non-truncated end) are NOT flagged -- only T13 fires."""
    entries = [
        _entry(1, "L1"),
        _entry(2, "L2"),
        _entry(3, "L3"),
        _entry(4, "L4"),
        _entry(5, "L5"),
    ]
    record = _record(["L1", "L2", "L3", "L4", "L5"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["T11", "T12", "T13", "L1", "L2", "L3", "L4", "L5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert len(span) == 1
    assert "T11" not in span[0].reason
    assert "T12" not in span[0].reason


# =========================================================================== #
# AC11: border_aware: false reverts the expected-sequence check to legacy
# =========================================================================== #


def test_ac11_border_aware_false_flags_all_beyond_truncated_end(tmp_path):
    """AC11: With border_aware: false and expected_levels extending beyond a
    TRUNCATED span end (AC8's record), all absent expected levels beyond the
    span end are flagged regardless of truncation."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(3, "L3"),
        _entry(4, "L4"),
        _entry(5, "L5"),
    ]
    record = _record(["L1", "L2", "L3", "L4", "L5"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["T12", "T13", "L1", "L2", "L3", "L4", "L5"])
        + "      border_aware: false\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert len(span) == 1
    assert "T12" in span[0].reason and "T13" in span[0].reason


# =========================================================================== #
# AC12: A clean partial-FOV scan fires no border finding (default config)
# =========================================================================== #


def test_ac12_clean_partial_fov_scan_no_border_finding():
    """AC12: Terminal present vertebrae touching only their covered-span-end
    faces yield no border finding under default_config()."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(3, "L3", touched_faces=("touches_inferior",)),
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert findings == [], f"Clean partial-FOV scan should fire no border finding; got {findings}"


# =========================================================================== #
# AC13: An in-plane touch on a terminal vertebra still fires
# =========================================================================== #


def test_ac13_terminal_in_plane_touch_still_fires():
    """AC13: The superior-most present level touching both touches_superior
    and touches_left (a lateral clip at the covered-span end) still emits
    exactly one border finding."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior", "touches_left")),
        _entry(2, "L2"),
        _entry(3, "L3"),
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({1})


# =========================================================================== #
# AC14: An interior vertebra touching a cranio-caudal face still fires
# =========================================================================== #


def test_ac14_interior_vertebra_cranio_caudal_touch_still_fires():
    """AC14: A vertebra that is neither present_levels[0] nor [-1] touching
    touches_superior still emits exactly one border finding."""
    entries = [
        _entry(1, "L1"),
        _entry(2, "L2", touched_faces=("touches_superior",)),
        _entry(3, "L3"),
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({2})
    assert findings[0].reason.startswith(_UNEXPECTED_CLIP_TAG)


# =========================================================================== #
# AC15: border and coverage agree on the covered-span ends
# =========================================================================== #


def test_ac15_border_and_coverage_agree_on_covered_span_ends():
    """AC15: For one partial-FOV record, the terminal vertebra border
    suppresses as an expected covered-span-end truncation is the same level
    derive_fov_coverage reports as the truncated superior_end_level."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),
        _entry(2, "L2"),
        _entry(3, "L3"),
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.superior_end_level == "L1"
    assert fov.superior_truncated is True

    findings = _border_findings(run_rules(record, default_config()))
    flagged_labels = {label for f in findings for label in f.labels}
    # The vertebra border treats as the (truncated) superior covered-span end
    # is label 1 (level_name L1) -- suppressed, not flagged.
    assert 1 not in flagged_labels


# =========================================================================== #
# AC16: The default path is behaviour-preserving -- Stage-5 goldens unaffected
# =========================================================================== #


def test_ac16_committed_corpus_coverage_and_border_findings_unchanged():
    """AC16: For every committed Stage-5 corpus case, the freshly-computed
    coverage / border findings under default_config() equal the committed
    golden's coverage / border findings -- the FOV-restriction does not alter
    output on any existing corpus fixture (default-config goldens don't
    exercise partial-FOV inputs or an active expected_levels)."""
    import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.golden import build_report_for_case, load_golden

    manifest = load_manifest()
    cases = manifest["cases"]
    assert cases, "committed manifest must be non-empty for this check to be meaningful"

    def _rule_findings(report: dict) -> list:
        return [
            f
            for f in report.get("findings", [])
            if f.get("rule_id") in ("coverage", "border")
        ]

    for case in cases:
        fresh_report = build_report_for_case(case)
        golden_report = load_golden(case["case_id"])
        fresh = _rule_findings(fresh_report)
        golden = _rule_findings(golden_report)
        assert fresh == golden, (
            f"coverage/border findings changed for case {case['case_id']!r}:\n"
            f"fresh={fresh}\ngolden={golden}"
        )


# =========================================================================== #
# AC17: Neither rule mutates the record and both stay deterministic
# =========================================================================== #


def test_ac17_coverage_and_border_do_not_mutate_record(tmp_path):
    """AC17: run_rules leaves the entire record unchanged under deep equality
    for a record that fires both coverage and border findings."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_left",)),
        _entry(2, "L2"),
        _entry(4, "L4"),
    ]
    record = _record(["L1", "L2", "L4"], ["L3"], entries)
    content = _coverage_yaml_header() + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
    cfg = load_config(_write_yaml(tmp_path, content))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before


def test_ac17_two_runs_return_equal_finding_lists():
    """AC17: Two successive run_rules calls return equal finding lists in the
    same order for a record firing both rules."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_left",)),
        _entry(2, "L2"),
        _entry(4, "L4"),
    ]
    record = _record(["L1", "L2", "L4"], ["L3"], entries)
    cfg = default_config()
    run1 = run_rules(record, cfg)
    run2 = run_rules(record, cfg)
    assert run1 == run2


# =========================================================================== #
# Adversarial / additional edge cases
# =========================================================================== #


def test_adv_single_present_level_has_span_both_ends_same_level():
    """Adversarial: A single-present-level record -- has_span is still
    derivable (both ends the same level); no crash."""
    entries = [_entry(1, "L3")]
    record = _record(["L3"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.has_span is True
    assert fov.superior_end_level == "L3"
    assert fov.inferior_end_level == "L3"


def test_adv_single_present_level_coverage_border_no_crash_no_finding():
    """Adversarial: A single-present-level record does not crash either rule
    and fires no finding without an active expected sequence / no touches."""
    entries = [_entry(1, "L3")]
    record = _record(["L3"], [], entries)
    findings = run_rules(record, default_config())
    assert _cov_findings(findings) == []
    assert _border_findings(findings) == []


def test_adv_missing_span_end_geometry_coverage_does_not_suppress(tmp_path):
    """Adversarial: The span-end level's geometry/level_name is missing from
    per_label -- treated as not-truncated (conservative), so coverage does
    NOT suppress an absent adjacent expected level beyond that end."""
    entries = [
        _entry(1, "SOME_OTHER_NAME"),  # does not match "L1"
        _entry(2, "L2"),
    ]
    record = _record(["L1", "L2"], [], entries)
    content = _coverage_yaml_header() + _levels_yaml_list(["T13", "L1", "L2"])
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert len(span) == 1
    assert "T13" in span[0].reason


def test_adv_missing_span_end_geometry_border_surfaces_no_crash():
    """Adversarial: An entry present in per_label but with no geometry
    sub-block contributes no border finding and does not crash (mirrors item
    031's AC15 conservative branch through the shared helper)."""
    record = {
        "per_label": {1: {"label": 1, "level_name": "L1"}},
        "relationships": {"present_levels": ["L1"]},
        "overlaps": {},
    }
    findings = _border_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_expected_levels_adjacent_on_both_ends_only_non_truncated_fires(tmp_path):
    """Adversarial: expected_levels contains the adjacent level on BOTH a
    truncated (superior) and a non-truncated (inferior) end in one record --
    only the non-truncated end's adjacent level (L6) fires."""
    entries = [
        _entry(1, "L1", touched_faces=("touches_superior",)),  # truncated
        _entry(2, "L2"),
        _entry(3, "L3"),
        _entry(4, "L4"),
        _entry(5, "L5"),  # not touching inferior -- headroom below
    ]
    record = _record(["L1", "L2", "L3", "L4", "L5"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["T13", "L1", "L2", "L3", "L4", "L5", "L6"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert len(span) == 1
    assert "L6" in span[0].reason
    assert "T13" not in span[0].reason


def test_adv_transitional_level_as_adjacent_neighbour_no_crash():
    """Adversarial: A transitional level (T13) as the immediately-adjacent
    beyond-end canonical neighbour of a present L1..L2 span does not crash
    the rank comparison."""
    entries = [
        _entry(1, "L1"),
        _entry(2, "L2"),
    ]
    record = _record(["L1", "L2"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.has_span is True
    assert fov.superior_end_level == "L1"


def test_adv_border_aware_false_flags_all_beyond_non_truncated_end(tmp_path):
    """Adversarial: border_aware: false with a NON-truncated end flags all
    beyond-end absent expected levels, complementing AC11's truncated-end
    case."""
    entries = [
        _entry(1, "L1"),
        _entry(2, "L2"),
        _entry(3, "L3"),
        _entry(4, "L4"),
        _entry(5, "L5"),
    ]
    record = _record(["L1", "L2", "L3", "L4", "L5"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["T11", "T12", "T13", "L1", "L2", "L3", "L4", "L5"])
        + "      border_aware: false\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(_cov_findings(run_rules(record, cfg)), _SPAN_TAG)
    assert len(span) == 1
    assert "T11" in span[0].reason and "T12" in span[0].reason and "T13" in span[0].reason


def test_adv_coverage_severity_override_still_applies(tmp_path):
    """Adversarial regression: severity override still applies to coverage
    findings after the FOV refactor (item 029's contract)."""
    entries = [_entry(1, "L1"), _entry(2, "L2"), _entry(4, "L4")]
    record = _record(["L1", "L2", "L4"], ["L3"], entries)
    content = _coverage_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    from segfacet.verdict import Severity

    findings = _cov_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.FAIL for f in findings)


def test_adv_coverage_unrecognised_severity_raises_value_error(tmp_path):
    """Adversarial regression: an unrecognised severity string still raises
    ValueError for coverage after the FOV refactor."""
    entries = [_entry(1, "L1")]
    record = _record(["L1"], [], entries)
    content = _coverage_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_adv_border_severity_override_still_applies(tmp_path):
    """Adversarial regression: severity override still applies to border
    findings after the FOV refactor (item 031's contract)."""
    entries = [_entry(1, "L1", touched_faces=("touches_left",))]
    record = _record(["L1"], [], entries)
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  border:\n"
        "    params:\n"
        "      severity: fail\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    from segfacet.verdict import Severity

    findings = _border_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.FAIL for f in findings)


def test_adv_border_unrecognised_severity_raises_value_error(tmp_path):
    """Adversarial regression: an unrecognised severity string still raises
    ValueError for border after the FOV refactor."""
    entries = [_entry(1, "L1", touched_faces=("touches_left",))]
    record = _record(["L1"], [], entries)
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  border:\n"
        "    params:\n"
        "      severity: not_a_real_severity\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_adv_fov_helper_conflicting_evidence_touch_without_span_end_role():
    """Adversarial: a level exactly at a covered-span end that touches a face
    unrelated to its own end (inferior end level touching touches_superior,
    not touches_inferior) is reported not-truncated on its OWN axis --
    conflicting/irrelevant touch evidence does not leak across axes."""
    entries = [
        _entry(1, "L1"),
        _entry(2, "L2"),
        _entry(3, "L3", touched_faces=("touches_superior",)),  # wrong axis for inferior end
    ]
    record = _record(["L1", "L2", "L3"], [], entries)
    fov = derive_fov_coverage(record)
    assert fov.inferior_end_level == "L3"
    assert fov.inferior_truncated is False
