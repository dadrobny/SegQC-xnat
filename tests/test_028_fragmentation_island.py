"""Tests for item 028 — connected-components fragmentation / island rule.

Covers all 18 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:   FragmentationRule registers under rule_id == "fragmentation"; discoverable.
- AC2:   No finding for a single-component label (component_count == 1).
- AC3:   Fragmentation finding fires when fragmentation_index < fragmentation_index_threshold.
- AC4:   Index exactly equal to the threshold does not fire (inclusive convention).
- AC5:   Index above the threshold does not fire.
- AC6:   Rogue-island finding fires when a non-dominant component is strictly below island_min_voxels.
- AC7:   No island finding when all non-dominant components are >= island_min_voxels.
- AC8:   Non-dominant component exactly equal to island_min_voxels does not fire (inclusive).
- AC9:   fragmentation_index_threshold is config-driven: raising fires; lowering passes.
- AC10:  island_min_voxels is config-driven: raising fires; lowering passes.
- AC11:  Shipped hand-set defaults apply when no config is supplied.
- AC12:  Every finding names exactly the offending label (frozenset of one integer).
- AC13:  Every finding's reason reports component_count, component_sizes, fragmentation_index.
- AC14:  Default severity is Severity.FLAG; params.severity config overrides it.
- AC15:  An unrecognised severity string raises ValueError.
- AC16:  Rule is deterministic; fragmentation finding precedes island finding within a label;
         multi-label findings are ordered ascending by label integer.
- AC17:  evaluate returns [] and does not raise when per_label is empty/absent, or a per-label
         entry is missing its components sub-dict or key fields.
- AC18:  evaluate does not mutate the input record (verified by deep-equality).

Adversarial / edge-case scenarios included:
- A label triggering BOTH fragmentation and island yields two findings in fixed order.
- Threshold boundary: index == threshold no fire (AC4); island size == island_min_voxels
  no fire (AC8); inclusive convention consistent with item 027.
- Config raise/lower for fragmentation_index_threshold flips outcome (AC9).
- Config raise/lower for island_min_voxels flips outcome (AC10).
- Severity override to FAIL and PASS (AC14).
- Unrecognised severity raises ValueError with non-empty message (AC15).
- Determinism: two run_rules calls return equal lists in same order (AC16).
- Multi-label + multi-kind ordering: label 3 before label 22, frag before island (AC16).
- components sub-dict missing fragmentation_index key — graceful skip (AC17).
- components sub-dict with component_sizes == [] — no crash (AC17).
- components value that is not a mapping — skipped gracefully (AC17).
- largest_component_fraction used as fallback when fragmentation_index absent (spec step 2).
- Many tiny islands → exactly one island finding summarising all of them.
- No mutation of nested dicts and lists (AC18).
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segqc.heuristics.fragmentation  # noqa: F401 — triggers FragmentationRule registration
from segqc.heuristics import Finding, Rule, get_rule, iter_rules, run_rules
from segqc.heuristics.rule import _RULES
from segqc.verdict import Severity
from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    default_config,
    load_config,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _make_components(
    component_count: int,
    component_sizes: list,
    fragmentation_index: float | None = None,
) -> dict:
    """Build a minimal components sub-dict matching the components_to_dict shape.

    fragmentation_index defaults to dominant/total if not supplied.
    """
    total = sum(component_sizes) if component_sizes else 1
    dominant = component_sizes[0] if component_sizes else 0
    fi = fragmentation_index if fragmentation_index is not None else (
        dominant / total if total else 1.0
    )
    return {
        "component_count": component_count,
        "component_sizes": list(component_sizes),
        "component_volumes_mm3": [float(s) for s in component_sizes],
        "largest_component_fraction": fi,
        "fragmentation_index": fi,
        "small_fragments": [],
    }


def _make_label_entry(label: int, level_name: str, components: dict | None = None) -> dict:
    """Build a minimal per_label entry, optionally including a components sub-dict."""
    entry: dict = {"label": label, "level_name": level_name}
    if components is not None:
        entry["components"] = components
    return entry


def _make_record(*entries: dict) -> dict:
    """Build a feature record whose per_label is keyed by each entry's label int."""
    return {
        "per_label": {e["label"]: e for e in entries},
        "relationships": {},
        "overlaps": {},
    }


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    """Write *content* to a YAML file under *tmp_path* and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _frag_yaml_header() -> str:
    """Return a YAML preamble placing the cursor inside fragmentation params."""
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  fragmentation:\n"
        "    params:\n"
    )


def _frag_findings(findings):
    """Filter to only fragmentation-rule findings."""
    return [f for f in findings if f.rule_id == "fragmentation"]


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'fragmentation') and restore after.

    The module-level import registers FragmentationRule at collection time; this
    snapshot captures that state so tests cannot bleed into one another.
    """
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: FragmentationRule registers under rule_id == "fragmentation"
# =========================================================================== #


def test_ac1_fragmentation_rule_is_in_registry():
    """AC1: get_rule('fragmentation') returns a Rule instance without raising."""
    rule = get_rule("fragmentation")
    assert rule.rule_id == "fragmentation"


def test_ac1_fragmentation_appears_in_iter_rules():
    """AC1: iter_rules() yields at least one rule with rule_id == 'fragmentation'."""
    assert any(r.rule_id == "fragmentation" for r in iter_rules())


def test_ac1_fragmentation_rule_is_rule_subclass():
    """AC1: The registered FragmentationRule is a subclass of segqc.heuristics.Rule."""
    assert isinstance(get_rule("fragmentation"), Rule)


# =========================================================================== #
# AC2: No finding for a single-component label
# =========================================================================== #


def test_ac2_single_component_no_finding():
    """AC2: A label with component_count == 1 produces no finding of either kind."""
    comp = _make_components(component_count=1, component_sizes=[1000])
    record = _make_record(_make_label_entry(3, "L1", components=comp))
    findings = _frag_findings(run_rules(record, default_config()))
    assert findings == [], f"Single-component label should produce no finding; got {findings}"


def test_ac2_single_component_index_one_no_finding():
    """AC2: fragmentation_index == 1.0 never triggers either finding kind."""
    comp = _make_components(
        component_count=1, component_sizes=[500], fragmentation_index=1.0
    )
    record = _make_record(_make_label_entry(10, "T5", components=comp))
    assert _frag_findings(run_rules(record, default_config())) == []


# =========================================================================== #
# AC3: Fragmentation finding fires when index is strictly below the threshold
# =========================================================================== #


def test_ac3_split_halves_fires_fragmentation_finding():
    """AC3: Two equal halves (index 0.5) fire a Fragmentation: finding under 0.75 threshold."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, default_config()))
    frag = [f for f in findings if f.reason.startswith("Fragmentation:")]
    assert frag, "Expected a fragmentation finding for index 0.5 < default 0.75"


def test_ac3_fragmentation_finding_rule_id_is_fragmentation():
    """AC3: The fragmentation finding carries rule_id == 'fragmentation'."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag
    assert all(f.rule_id == "fragmentation" for f in frag)


def test_ac3_fragmentation_finding_labels_is_correct_frozenset():
    """AC3: The fragmentation finding has labels == frozenset({that_label})."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag
    assert all(f.labels == frozenset({22}) for f in frag)


# =========================================================================== #
# AC4: Fragmentation index exactly equal to threshold does not fire
# =========================================================================== #


def test_ac4_index_equal_threshold_no_fragmentation_finding(tmp_path):
    """AC4: fragmentation_index == threshold does not fire (inclusive threshold)."""
    threshold = 0.75
    content = (
        _frag_yaml_header()
        + f"      fragmentation_index_threshold: {threshold}\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2,
        component_sizes=[750, 250],
        fragmentation_index=threshold,
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag == [], f"index == threshold ({threshold}) must not fire; got {frag}"


# =========================================================================== #
# AC5: Fragmentation index above threshold does not fire
# =========================================================================== #


def test_ac5_index_above_threshold_no_fragmentation_finding(tmp_path):
    """AC5: fragmentation_index strictly above threshold does not fire."""
    threshold = 0.75
    content = (
        _frag_yaml_header()
        + f"      fragmentation_index_threshold: {threshold}\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[900, 100], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag == [], "index 0.9 > threshold 0.75 must not fire"


# =========================================================================== #
# AC6: Rogue-island finding fires for dominant body plus tiny component
# =========================================================================== #


def test_ac6_tiny_island_fires_rogue_island_finding(tmp_path):
    """AC6: Non-dominant component strictly below island_min_voxels fires an island finding."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # dominant 900 + tiny island 10 < 50 → island fires; index 0.9 > 0.75 → no fragmentation
    comp = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island, "Expected island finding for non-dominant 10 < 50"


def test_ac6_island_finding_rule_id_is_fragmentation(tmp_path):
    """AC6: The island finding also carries rule_id == 'fragmentation'."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island
    assert all(f.rule_id == "fragmentation" for f in island)


def test_ac6_island_finding_labels_is_correct_frozenset(tmp_path):
    """AC6: The island finding has labels == frozenset({that_label})."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(7, "T3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island
    assert all(f.labels == frozenset({7}) for f in island)


# =========================================================================== #
# AC7: No island finding when all non-dominant components >= island_min_voxels
# =========================================================================== #


def test_ac7_large_pieces_no_island_finding(tmp_path):
    """AC7: Non-dominant components all >= island_min_voxels produce no island finding."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # all non-dominant >= 50
    comp = _make_components(
        component_count=3,
        component_sizes=[500, 200, 100],
        fragmentation_index=0.5,
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island == [], "All non-dominant >= island_min should produce no island finding"


def test_ac7_no_island_finding_independent_of_fragmentation(tmp_path):
    """AC7: Island absence is independent of fragmentation — fragmentation may still fire."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # Two equal 500-voxel halves: fragmentation fires (0.5 < 0.75), island does not (500 >= 50)
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    frag = [f for f in findings if f.reason.startswith("Fragmentation:")]
    island = [f for f in findings if f.reason.startswith("Rogue island(s):")]
    assert frag, "Two equal halves (0.5 < 0.75) should fire fragmentation"
    assert island == [], "Two 500-voxel pieces (>= 50) should not fire island"


# =========================================================================== #
# AC8: Non-dominant component exactly equal to island_min_voxels does not fire
# =========================================================================== #


def test_ac8_island_size_equal_threshold_no_island_finding(tmp_path):
    """AC8: Non-dominant component exactly equal to island_min_voxels does not fire."""
    island_min = 50
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + f"      island_min_voxels: {island_min}\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2,
        component_sizes=[900, island_min],
        fragmentation_index=0.9,
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island == [], (
        f"Non-dominant size == {island_min} (equal to threshold) must not fire"
    )


# =========================================================================== #
# AC9: fragmentation_index_threshold is config-driven
# =========================================================================== #


def test_ac9_raising_threshold_causes_label_to_fire(tmp_path):
    """AC9: Raising threshold above index converts a pass to a fire."""
    # index 0.8 > default 0.75 → no fire with defaults
    comp = _make_components(
        component_count=2, component_sizes=[800, 200], fragmentation_index=0.8
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))

    default_frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert default_frag == [], "Index 0.8 should not fire with default threshold 0.75"

    # Raise threshold to 0.9: 0.8 < 0.9 → should fire
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.9\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    high_frag = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Fragmentation:")
    ]
    assert high_frag, "Index 0.8 should fire with raised threshold 0.9"


def test_ac9_lowering_threshold_prevents_firing(tmp_path):
    """AC9: Lowering threshold below index converts a fire to a pass."""
    # index 0.5 < default 0.75 → fires with defaults
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))

    default_frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert default_frag, "Index 0.5 should fire with default threshold 0.75"

    # Lower threshold to 0.3: 0.5 > 0.3 → should not fire
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.3\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    low_frag = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Fragmentation:")
    ]
    assert low_frag == [], "Index 0.5 should not fire with lowered threshold 0.3"


# =========================================================================== #
# AC10: island_min_voxels is config-driven
# =========================================================================== #


def test_ac10_raising_island_min_causes_label_to_fire(tmp_path):
    """AC10: Raising island_min_voxels above a non-dominant component size causes it to fire."""
    # island 60 >= default 50 → no fire with defaults
    comp = _make_components(
        component_count=2, component_sizes=[900, 60], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))

    default_island = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert default_island == [], "Island 60 >= default 50 should not fire"

    # Raise island_min to 100: 60 < 100 → should fire
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 100\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    high_island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert high_island, "Island 60 < raised threshold 100 should fire"


def test_ac10_lowering_island_min_prevents_firing(tmp_path):
    """AC10: Lowering island_min_voxels below component size prevents firing."""
    # island 30 < default 50 → fires with defaults
    comp = _make_components(
        component_count=2, component_sizes=[900, 30], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))

    default_island = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert default_island, "Island 30 < default 50 should fire"

    # Lower island_min to 10: 30 >= 10 → should not fire
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 10\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    low_island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert low_island == [], "Island 30 >= lowered threshold 10 should not fire"


# =========================================================================== #
# AC11: Shipped hand-set defaults apply when no config is supplied
# =========================================================================== #


def test_ac11_defaults_fire_fragmented_label():
    """AC11: With default_config(), a split-halves label (index 0.5) fires a fragmentation finding."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag, "Index 0.5 should fire under shipped default threshold 0.75"


def test_ac11_defaults_pass_intact_single_body_label():
    """AC11: With default_config(), a single-body label (index 1.0) produces no finding."""
    comp = _make_components(
        component_count=1, component_sizes=[1000], fragmentation_index=1.0
    )
    record = _make_record(_make_label_entry(5, "T1", components=comp))
    assert _frag_findings(run_rules(record, default_config())) == []


# =========================================================================== #
# AC12: Each finding names exactly the offending label
# =========================================================================== #


def test_ac12_fragmentation_finding_labels_is_single_label():
    """AC12: Fragmentation finding has labels == frozenset({offending_label})."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(13, "T7", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag
    for f in frag:
        assert len(f.labels) == 1
        assert f.labels == frozenset({13})


def test_ac12_island_finding_labels_is_single_label(tmp_path):
    """AC12: Island finding has labels == frozenset({offending_label})."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(17, "T11", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island
    for f in island:
        assert len(f.labels) == 1
        assert f.labels == frozenset({17})


def test_ac12_no_multi_label_findings():
    """AC12: No finding has more than one label (no case-level or multi-label findings)."""
    comp1 = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    comp2 = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(
        _make_label_entry(3, "C3", components=comp1),
        _make_label_entry(22, "L3", components=comp2),
    )
    findings = _frag_findings(run_rules(record, default_config()))
    assert all(len(f.labels) == 1 for f in findings), (
        "All findings must name exactly one label"
    )


# =========================================================================== #
# AC13: Each finding's reason reports component_count, sizes, and index
# =========================================================================== #


def test_ac13_fragmentation_reason_contains_component_count():
    """AC13: The fragmentation finding reason contains the component_count value."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag
    assert "2" in frag[0].reason, (
        f"component_count (2) not found in reason: {frag[0].reason!r}"
    )


def test_ac13_fragmentation_reason_contains_component_sizes():
    """AC13: The fragmentation finding reason contains the component sizes."""
    comp = _make_components(
        component_count=2, component_sizes=[600, 400], fragmentation_index=0.6
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag
    reason = frag[0].reason
    assert "600" in reason or "400" in reason, (
        f"component_sizes ([600, 400]) not found in reason: {reason!r}"
    )


def test_ac13_fragmentation_reason_contains_fragmentation_index():
    """AC13: The fragmentation finding reason contains the fragmentation_index value."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    assert frag
    reason = frag[0].reason
    assert "0.5" in reason or "0.50" in reason, (
        f"fragmentation_index (0.5) not found in reason: {reason!r}"
    )


def test_ac13_reason_is_non_empty_string():
    """AC13: Every fragmentation finding has a non-empty reason string."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, default_config()))
    assert findings
    assert all(isinstance(f.reason, str) and f.reason.strip() for f in findings)


def test_ac13_island_reason_contains_component_info(tmp_path):
    """AC13: The island finding reason mentions component count, sizes, and index."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island
    reason = island[0].reason
    assert "2" in reason, f"component_count not found in reason: {reason!r}"
    assert "10" in reason, f"island size (10) not found in reason: {reason!r}"


# =========================================================================== #
# AC14: Default severity is FLAG; severity is config-driven
# =========================================================================== #


def test_ac14_default_severity_is_flag():
    """AC14: With no severity param, every finding has Severity.FLAG."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, default_config()))
    assert findings
    assert all(f.severity is Severity.FLAG for f in findings), (
        f"All findings should be Severity.FLAG by default; got {[f.severity for f in findings]}"
    )


def test_ac14_severity_param_fail_overrides_default(tmp_path):
    """AC14: With params.severity = 'fail', every finding has Severity.FAIL."""
    content = (
        _frag_yaml_header()
        + "      severity: fail\n"
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.FAIL for f in findings), (
        f"All findings should be Severity.FAIL; got {[f.severity for f in findings]}"
    )


def test_ac14_severity_param_pass_overrides_default(tmp_path):
    """AC14: With params.severity = 'pass', every finding has Severity.PASS."""
    content = (
        _frag_yaml_header()
        + "      severity: pass\n"
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.PASS for f in findings)


def test_ac14_island_finding_also_inherits_severity_override(tmp_path):
    """AC14: Severity override applies to island findings as well as fragmentation findings."""
    content = (
        _frag_yaml_header()
        + "      severity: fail\n"
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert island
    assert all(f.severity is Severity.FAIL for f in island)


# =========================================================================== #
# AC15: Unrecognised severity string raises ValueError
# =========================================================================== #


def test_ac15_unrecognised_severity_raises_value_error(tmp_path):
    """AC15: An unrecognised severity param string raises ValueError."""
    content = (
        _frag_yaml_header()
        + "      severity: xyz_not_a_severity\n"
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac15_value_error_raised_even_on_empty_per_label(tmp_path):
    """AC15: ValueError fires even for a record with no labels (severity parsed first)."""
    content = (
        _frag_yaml_header()
        + "      severity: garbage_severity\n"
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {"per_label": {}, "relationships": {}, "overlaps": {}}
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac15_value_error_has_non_empty_message(tmp_path):
    """AC15: The ValueError for a bad severity has a non-empty, readable message."""
    content = (
        _frag_yaml_header()
        + "      severity: xyz_not_a_severity\n"
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    with pytest.raises(ValueError) as exc_info:
        run_rules(record, cfg)
    assert str(exc_info.value).strip(), "ValueError must have a non-empty message"


# =========================================================================== #
# AC16: Deterministic with fixed output order
# =========================================================================== #


def test_ac16_two_runs_return_equal_lists():
    """AC16: Two successive run_rules calls on the same inputs return equal finding lists."""
    comp1 = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    comp2 = _make_components(
        component_count=2, component_sizes=[900, 10], fragmentation_index=0.9
    )
    record = _make_record(
        _make_label_entry(3, "C3", components=comp1),
        _make_label_entry(22, "L3", components=comp2),
    )
    cfg = default_config()
    run1 = _frag_findings(run_rules(record, cfg))
    run2 = _frag_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


def test_ac16_fragmentation_before_island_within_same_label(tmp_path):
    """AC16: When a label fires both kinds, fragmentation finding precedes island finding."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # index 0.5 < 0.75 (fragmentation) AND island 10 < 50 (island)
    comp = _make_components(
        component_count=2, component_sizes=[500, 10], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    frag = [f for f in findings if f.reason.startswith("Fragmentation:")]
    island = [f for f in findings if f.reason.startswith("Rogue island(s):")]
    assert frag, "Expected fragmentation finding"
    assert island, "Expected island finding"
    assert findings.index(frag[0]) < findings.index(island[0]), (
        "Fragmentation finding must precede island finding for the same label"
    )


def test_ac16_multi_label_findings_ordered_ascending_by_label():
    """AC16: Findings from label 3 precede findings from label 22 in output."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(
        _make_label_entry(22, "L3", components=comp),
        _make_label_entry(3, "C3", components=comp),
    )
    findings = _frag_findings(run_rules(record, default_config()))
    assert findings
    label_seq = [min(f.labels) for f in findings]
    pos_3 = [i for i, lbl in enumerate(label_seq) if lbl == 3]
    pos_22 = [i for i, lbl in enumerate(label_seq) if lbl == 22]
    if pos_3 and pos_22:
        assert max(pos_3) < min(pos_22), (
            f"Label 3 findings must precede label 22; order was {label_seq}"
        )


# =========================================================================== #
# AC17: Tolerates empty / absent / components-free records
# =========================================================================== #


def test_ac17_empty_per_label_returns_empty_list():
    """AC17: evaluate on per_label={} returns [] without raising."""
    record = {"per_label": {}, "relationships": {}, "overlaps": {}}
    assert _frag_findings(run_rules(record, default_config())) == []


def test_ac17_absent_per_label_returns_empty_list():
    """AC17: evaluate on a record with no 'per_label' key returns [] without raising."""
    record = {"relationships": {}, "overlaps": {}}
    assert _frag_findings(run_rules(record, default_config())) == []


def test_ac17_missing_components_subdict_skipped_gracefully():
    """AC17: A per-label entry without a 'components' key is skipped without crashing."""
    entry = {"label": 22, "level_name": "L3"}  # no 'components' key
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    result = _frag_findings(run_rules(record, default_config()))
    assert isinstance(result, list)


def test_ac17_missing_fragmentation_index_skipped_gracefully():
    """AC17: components dict missing both fragmentation_index and largest_component_fraction is skipped."""
    comp = {
        "component_count": 2,
        "component_sizes": [500, 500],
        "component_volumes_mm3": [500.0, 500.0],
        # both 'fragmentation_index' and 'largest_component_fraction' absent
        "small_fragments": [],
    }
    entry = {"label": 22, "level_name": "L3", "components": comp}
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    result = _frag_findings(run_rules(record, default_config()))
    assert isinstance(result, list)


def test_ac17_missing_component_sizes_handled_gracefully():
    """AC17: components dict missing 'component_sizes' is handled without crashing."""
    comp = {
        "component_count": 2,
        "component_volumes_mm3": [500.0, 500.0],
        "fragmentation_index": 0.5,
        "largest_component_fraction": 0.5,
        "small_fragments": [],
        # 'component_sizes' intentionally absent
    }
    entry = {"label": 22, "level_name": "L3", "components": comp}
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    result = _frag_findings(run_rules(record, default_config()))
    assert isinstance(result, list)


def test_ac17_components_not_a_mapping_skipped_gracefully():
    """AC17: A components value that is not a dict is skipped without crashing."""
    entry = {"label": 22, "level_name": "L3", "components": "not-a-dict"}
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    result = _frag_findings(run_rules(record, default_config()))
    assert isinstance(result, list)


def test_ac17_label_missing_components_does_not_suppress_other_labels():
    """AC17: Skipping a components-free label does not suppress evaluation of others."""
    comp_intact = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    entry_no_comp = {"label": 3, "level_name": "C3"}  # missing components
    entry_with_comp = _make_label_entry(22, "L3", components=comp_intact)
    record = {
        "per_label": {3: entry_no_comp, 22: entry_with_comp},
        "relationships": {},
        "overlaps": {},
    }
    findings = _frag_findings(run_rules(record, default_config()))
    label22 = [f for f in findings if 22 in f.labels]
    assert label22, "Label 22 with valid components should still fire"


# =========================================================================== #
# AC18: The rule does not mutate the input record
# =========================================================================== #


def test_ac18_evaluate_does_not_mutate_record():
    """AC18: evaluate leaves the entire record (per_label + components) unchanged."""
    comp = _make_components(
        component_count=2, component_sizes=[500, 500], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    record_before = copy.deepcopy(record)
    run_rules(record, default_config())
    assert record == record_before, "run_rules must not mutate the caller's record"


def test_ac18_component_sizes_list_not_mutated():
    """AC18: The component_sizes list inside the record is unchanged after evaluate."""
    sizes = [900, 30]
    comp = _make_components(component_count=2, component_sizes=sizes, fragmentation_index=0.9)
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    sizes_ref = list(record["per_label"][22]["components"]["component_sizes"])
    run_rules(record, default_config())
    assert record["per_label"][22]["components"]["component_sizes"] == sizes_ref, (
        "component_sizes list must not be mutated"
    )


# =========================================================================== #
# Adversarial: edge cases and combined scenarios
# =========================================================================== #


def test_adv_both_findings_fired_for_same_label_correct_count(tmp_path):
    """Adversarial: A label with low index AND tiny island yields exactly two findings."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # index 0.5 < 0.75 (fragmentation) AND island 10 < 50 (island)
    comp = _make_components(
        component_count=2, component_sizes=[500, 10], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    assert len(findings) == 2, (
        f"Expected exactly 2 findings (fragmentation + island); got {len(findings)}: {findings}"
    )
    assert findings[0].reason.startswith("Fragmentation:"), "First must be fragmentation"
    assert findings[1].reason.startswith("Rogue island(s):"), "Second must be island"


def test_adv_both_findings_name_same_label(tmp_path):
    """Adversarial: Both findings emitted for the same label carry that label's frozenset."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 10], fragmentation_index=0.5
    )
    record = _make_record(_make_label_entry(13, "T7", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    assert all(f.labels == frozenset({13}) for f in findings), (
        "Both findings should name label 13"
    )


def test_adv_index_at_threshold_with_tiny_island_fires_only_island(tmp_path):
    """Adversarial: index == threshold (no fragmentation) with tiny island still fires island only."""
    threshold = 0.75
    island_min = 50
    content = (
        _frag_yaml_header()
        + f"      fragmentation_index_threshold: {threshold}\n"
        + f"      island_min_voxels: {island_min}\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2,
        component_sizes=[750, 10],
        fragmentation_index=threshold,
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    findings = _frag_findings(run_rules(record, cfg))
    frag = [f for f in findings if f.reason.startswith("Fragmentation:")]
    island = [f for f in findings if f.reason.startswith("Rogue island(s):")]
    assert frag == [], f"index == threshold must not fire fragmentation; got {frag}"
    assert island, "Tiny island (10 < 50) should still fire island"


def test_adv_empty_component_sizes_no_crash():
    """Adversarial: component_sizes == [] in the components dict does not crash."""
    comp = {
        "component_count": 0,
        "component_sizes": [],
        "component_volumes_mm3": [],
        "largest_component_fraction": 1.0,
        "fragmentation_index": 1.0,
        "small_fragments": [],
    }
    entry = {"label": 22, "level_name": "L3", "components": comp}
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    result = _frag_findings(run_rules(record, default_config()))
    assert isinstance(result, list)


def test_adv_largest_component_fraction_used_as_fallback():
    """Adversarial: largest_component_fraction is the fallback when fragmentation_index is absent."""
    comp = {
        "component_count": 2,
        "component_sizes": [500, 500],
        "component_volumes_mm3": [500.0, 500.0],
        "largest_component_fraction": 0.5,  # should be used as fragmentation_index
        # 'fragmentation_index' intentionally absent
        "small_fragments": [],
    }
    entry = {"label": 22, "level_name": "L3", "components": comp}
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    frag = [
        f for f in _frag_findings(run_rules(record, default_config()))
        if f.reason.startswith("Fragmentation:")
    ]
    # 0.5 < default threshold 0.75 → should fire via fallback
    assert frag, "largest_component_fraction=0.5 should trigger fragmentation via fallback"


def test_adv_many_tiny_islands_yields_one_island_finding(tmp_path):
    """Adversarial: Many tiny non-dominant components yield exactly one island finding."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=6,
        component_sizes=[900, 5, 5, 5, 5, 5],
        fragmentation_index=0.9,
    )
    record = _make_record(_make_label_entry(22, "L3", components=comp))
    island = [
        f for f in _frag_findings(run_rules(record, cfg))
        if f.reason.startswith("Rogue island(s):")
    ]
    assert len(island) == 1, (
        f"Many tiny islands should yield exactly one island finding; got {len(island)}"
    )


def test_adv_multi_label_multi_kind_ordering(tmp_path):
    """Adversarial: Both labels fire both kinds; order is label3-frag, label3-island, label22-frag, label22-island."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 10], fragmentation_index=0.5
    )
    record = _make_record(
        _make_label_entry(3, "C3", components=comp),
        _make_label_entry(22, "L3", components=comp),
    )
    findings = _frag_findings(run_rules(record, cfg))
    assert len(findings) == 4, (
        f"Expected 4 findings (2 per label × 2 labels); got {len(findings)}: {findings}"
    )
    assert findings[0].labels == frozenset({3})
    assert findings[0].reason.startswith("Fragmentation:")
    assert findings[1].labels == frozenset({3})
    assert findings[1].reason.startswith("Rogue island(s):")
    assert findings[2].labels == frozenset({22})
    assert findings[2].reason.startswith("Fragmentation:")
    assert findings[3].labels == frozenset({22})
    assert findings[3].reason.startswith("Rogue island(s):")


def test_adv_determinism_multi_label_multi_kind(tmp_path):
    """Adversarial: Two run_rules calls on a multi-label/multi-kind record return identical lists."""
    content = (
        _frag_yaml_header()
        + "      fragmentation_index_threshold: 0.75\n"
        + "      island_min_voxels: 50\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    comp = _make_components(
        component_count=2, component_sizes=[500, 10], fragmentation_index=0.5
    )
    record = _make_record(
        _make_label_entry(3, "C3", components=comp),
        _make_label_entry(22, "L3", components=comp),
    )
    run1 = _frag_findings(run_rules(record, cfg))
    run2 = _frag_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"
