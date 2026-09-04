"""Tests for item 137 -- disposition the four §6-mode-less rules (``bounds``,
``reference_delta`` -> analytic modes 1 and 2; ``intensity``,
``intensity_reference_delta`` -> mode-less, with the catalogue-gap finding
captured) and the new ``"rule_mode_less"`` ``mode_evidence`` tag that closes
Stage 19's G8 "statused but mode-unmapped" bucket honestly.

Post-merge correction (2026-09-02, commit b1c593c): AC2/AC3 below and their
tests originally pinned ``reference_delta`` at ``modes == (2,)`` on an
evidence sentence that falsely claimed the committed reference artifact
carries only ``physical_volume_mm3``. Measured directly, it carries 21
per-label features, and ``compute_reference_delta`` scores every one it
tracks -- including ``spline_offset_mm``, mode 1's own anchor feature
(``feature_docs.MODE_ANCHOR_PATHS[1]``). The rule now declares
``modes=(1, 2)``; the tests below assert that corrected shape, and a new
adversarial test ties the declaration to the tracked-feature vocabulary
itself so a re-narrowing to ``(2,)`` fails here even with nothing else
changed.

Covers Acceptance Criteria AC1-AC18:

- AC1:  every one of the ten registered rules carries a declaration with
        ``pending_reason == ""`` -- nothing ships pending.
- AC2:  ``bounds`` declares exactly ``(2,)``, analytic.
- AC3:  ``reference_delta`` declares exactly ``(1, 2)``, analytic (corrected
        2026-09-02, commit b1c593c -- originally ``(2,)`` on a false
        evidence claim; see the module note above).
- AC4:  both analytic declarations are analytic (``"analytic" in evidence``,
        ``"corpus" not in evidence``) and name the mechanism (>= 40 chars).
- AC5:  ``intensity`` / ``intensity_reference_delta`` are mode-less, not
        pending.
- AC6:  both mode-less reasons are substantive (>= 120 chars, contain "§6").
- AC7:  ``intensity``'s reason cites the corpus manifest path.
- AC8:  the cited manifest evidence actually holds (no ``failure_mode`` key,
        exactly the four named cases).
- AC9:  declarations and the corpus-derived map still agree
        (``rule_declaration_conflicts() == ()``).
- AC10: ``mode_evidence`` carries ``"rule_mode_less"`` iff a consuming rule
        declares a non-empty ``mode_less_reason``.
- AC11: ``mode_evidence`` is a subsequence of the canonical four-tag order
        (or exactly ``("rule_unmapped",)``).
- AC12: nothing on this tree still reports ``rule_unmapped``.
- AC13: every entry consumed by ``bounds``/``reference_delta`` carries mode 2
        in ``failure_modes``.
- AC14: every intensity-only, non-anchor entry is honestly mode-less
        (``failure_modes == ()``, ``mode_evidence == ("rule_mode_less",)``).
- AC15: both committed catalogue artifacts regenerate byte-identically,
        ``schema_version`` still ``"1.1"``.
- AC16: the catalogue-gap finding is captured durably in the insight inbox
        (or one of its archives).
- AC17: §6 stays at exactly eight numbered modes; ``MODE_ANCHOR_PATHS``'s key
        set is still ``{1, ..., 8}``.
- AC18: the disposition is metadata only -- replacing any of the four
        declarations leaves ``run_rules`` unchanged.

Adversarial / edge-case scenarios included: ``rule_unmapped`` narrowed but
still reachable (an undeclared stub rule, and a declaration monkeypatched
back to ``pending``); a future corpus case still binds an analytic
declaration (the escape-hatch guard); an analytic declaration claiming a
mode outside the specification is still rejected by
``catalogue.rule_declaration_conflicts()`` -- reconciled by item 147
(2026-09-04), which retires the reserved ``"corpus"`` evidence tag and the
declared -> corpus direction this scenario originally (also) exercised
through the same checker; the measured
artifact-movement counts from the item spec, including the corrected
mode-1-carrying-entry count; determinism of ``build_catalogue()`` and
``rule_declaration_conflicts()``; frozen-instance immutability; an entry
with no ``consuming_rules`` gains neither ``"rule_declaration"`` nor
``"rule_mode_less"``; an entry consumed by both an analytic declarer and a
mode-less declarer carries both tags in canonical order and keeps the
declarer's own declared modes in ``failure_modes``; the ``per_label``
container keeps its corpus-derived modes and gains ``"rule_mode_less"``
last; the insights search globs the archive files too; ``reference_delta``'s
declared modes are tied to its own tracked-feature vocabulary, not just
pinned by value, so a re-narrowing to ``(2,)`` is caught structurally.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections import Counter
from pathlib import Path

import pytest

import segfacet.heuristics.rule as rule_mod
from segfacet.heuristics.rule import Rule, _RULES, iter_rules, register_rule
from segfacet.heuristics.runner import run_rules
from segfacet.config import bundled_default_config
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import build_clean_spine


def _catalogue():
    """Local import of ``segfacet.catalogue`` (mirrors
    ``tests/test_136_rule_mode_declarations.py``'s ``_catalogue()``)."""
    import segfacet.catalogue as catalogue

    return catalogue


_REPO_ROOT = Path(__file__).resolve().parents[1]

_ANALYTIC_RULES = ("bounds", "reference_delta")
# bounds declares mode 2 alone; reference_delta declares modes 1 and 2
# (corrected 2026-09-02, commit b1c593c -- see the module note above).
_ANALYTIC_DECLARED_MODES = {"bounds": (2,), "reference_delta": (1, 2)}
# Item 146 (2026-09-03): no rule ships mode-less any more -- intensity /
# intensity_reference_delta move from mode-less to declaring §6 mode 9 -- so
# this roll call becomes empty rather than removed (its consumers below are
# rescoped, not deleted). _INTENSITY_RULES names the same two rules under
# their post-item disposition, for the tests that need to select on them.
_MODE_LESS = ()
_INTENSITY_RULES = ("intensity", "intensity_reference_delta")
_DISPOSITIONED = _ANALYTIC_RULES + _MODE_LESS

_CANONICAL_TAG_ORDER = (
    "per_mode_metric",
    "rule_mode_map",
    "rule_declaration",
    "rule_mode_less",
)


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (house pattern from
    ``tests/test_026_rule_engine_core.py`` / ``test_136``), so a stub rule
    registered for an adversarial case cannot leak into another test."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


def _fixed_record():
    config = bundled_default_config()
    clean = build_clean_spine()
    return extract_feature_record(clean.seg_img, config), config


# =========================================================================== #
# AC1: no shipped rule is undeclared or still pending
# =========================================================================== #


def test_ac1_all_ten_rules_declared_and_not_pending():
    rules = list(iter_rules())
    assert len(rules) == 10
    for rule in rules:
        decl = rule.mode_declaration
        assert decl is not None, rule.rule_id
        assert isinstance(decl, rule_mod.RuleModeDeclaration), rule.rule_id
        assert decl.pending_reason == "", rule.rule_id


# =========================================================================== #
# AC2 / AC3: bounds declares exactly mode 2; reference_delta declares modes
# 1 and 2 (corrected 2026-09-02, commit b1c593c)
# =========================================================================== #


@pytest.mark.parametrize("rule_id, expected_modes", sorted(_ANALYTIC_DECLARED_MODES.items()))
def test_ac2_ac3_analytic_rule_declares_its_expected_modes(rule_id, expected_modes):
    decl = _RULES[rule_id].mode_declaration
    assert decl.modes == expected_modes, rule_id
    assert decl.mode_less_reason == ""
    assert decl.pending_reason == ""


def test_adv_reference_delta_declared_modes_cover_every_tracked_mode_anchor_feature():
    """The defect this corrects (commit b1c593c) was an evidence sentence's
    false factual claim about the committed reference artifact going
    unchecked -- AC4 only pinned ``len(evidence) >= 40``, never its content.
    This test instead ties ``reference_delta``'s declared modes to what
    ``compute_reference_delta`` demonstrably reads, independent of prose: for
    every feature name in ``reference.delta.INGESTED_FEATURES`` (the
    vocabulary ``_case_features_for_label`` actually scores), map it onto the
    record leaf path it is read from and, wherever that path is a §6
    mode-anchor path (``feature_docs.MODE_ANCHOR_PATHS``), require the rule's
    declared modes to include that mode. ``spline_offset_mm`` is read from
    ``stage3.per_label_offsets[].offset_mm``, exactly mode 1's own anchor
    path, so this fails the moment ``reference_delta``'s declaration is
    re-narrowed to ``(2,)`` -- the original, false-premised shape -- even
    though nothing else in this module or the rule's code changed."""
    import segfacet.feature_docs as feature_docs_module
    import segfacet.reference.delta as delta_module

    tracked = delta_module.INGESTED_FEATURES
    assert tracked, "expected a non-empty reference_delta tracked-feature vocabulary"

    # The record leaf path each tracked feature name is read from -- mirrors
    # _case_features_for_label's two read paths (reference/delta.py): the
    # per-label geometry sub-block, keyed by name, and the one Stage 3
    # exception (the spline offset lives in a different sub-block entirely).
    feature_record_path = {
        name: "per_label.{label}.geometry." + name for name in tracked if name != "spline_offset_mm"
    }
    feature_record_path["spline_offset_mm"] = "stage3.per_label_offsets[].offset_mm"
    assert set(feature_record_path) == set(tracked)

    anchor_modes_by_path: dict = {}
    for mode, paths in feature_docs_module.MODE_ANCHOR_PATHS.items():
        for path in paths:
            anchor_modes_by_path.setdefault(path, set()).add(mode)

    required_modes: set = set()
    for feature_name in tracked:
        required_modes |= anchor_modes_by_path.get(feature_record_path[feature_name], set())

    assert required_modes, (
        "expected at least one reference_delta-tracked feature to map onto "
        "a §6 mode anchor path"
    )
    assert 1 in required_modes, required_modes  # spline_offset_mm -> mode 1

    decl = _RULES["reference_delta"].mode_declaration
    assert required_modes <= set(decl.modes), (required_modes, decl.modes)


# =========================================================================== #
# AC4: both analytic declarations are analytic, not corpus-corroborated
# =========================================================================== #


@pytest.mark.parametrize("rule_id", sorted(_ANALYTIC_RULES))
def test_ac4_analytic_declaration_is_analytic_with_named_mechanism(rule_id):
    decl = _RULES[rule_id].mode_declaration
    assert "analytic" in decl.evidence
    assert "corpus" not in decl.evidence
    mechanism_elements = [e for e in decl.evidence if e != "analytic"]
    assert any(len(e) >= 40 for e in mechanism_elements), decl.evidence


def test_adv_analytic_declaration_claiming_an_unlisted_mode_is_rejected(monkeypatch):
    """Reconciled (item 147, 2026-09-04): the retired branch this test
    exercised (``catalogue.rule_declaration_conflicts()``'s declared ->
    corpus direction, gated on the now-retired ``"corpus"`` evidence tag)
    is deleted outright, not hardened -- retagging bounds as corpus-backed
    is no longer rejected by anything (AC20: the tag is inert). What
    survives this test's intent -- that an over-claimed mode on an
    analytic declaration is still reported, not silently accepted -- is
    the checker's other, untouched direction: a declared mode outside
    ``segfacet.failure_modes.SPECIFICATION``'s key set is still reported by
    ``rule_declaration_conflicts()`` regardless of evidence tag (AC12's
    shape)."""
    catalogue = _catalogue()
    rule = _RULES["bounds"]
    replacement = rule_mod.RuleModeDeclaration(
        modes=(999,), evidence=("analytic", "test-evidence-item147")
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.rule_declaration_conflicts()
    assert any("bounds" in msg and "999" in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC5: intensity / intensity_reference_delta are mode-less, not pending
# =========================================================================== #


@pytest.mark.parametrize("rule_id", sorted(_INTENSITY_RULES))
def test_ac5_mode_less_rule_declares_no_modes_not_pending(rule_id):
    """Rescoped (item 146, 2026-09-03): the two intensity rules move from
    mode-less to declaring §6 mode 9 -- restated as "dispositioned, not
    pending, and now declares mode 9" (item 146 AC9)."""
    decl = _RULES[rule_id].mode_declaration
    assert decl.modes == (9,)
    assert decl.pending_reason == ""
    assert decl.mode_less_reason == ""


# =========================================================================== #
# AC6: both mode-less reasons are substantive
# =========================================================================== #


@pytest.mark.parametrize("rule_id", sorted(_INTENSITY_RULES))
def test_ac6_mode_less_reason_is_substantive(rule_id):
    """Rescoped (item 146, 2026-09-03): mode_less_reason is now "" for both
    intensity rules; the substantive claim moves to the declaration's
    evidence tuple (item 146 AC9/AC10)."""
    decl = _RULES[rule_id].mode_declaration
    assert decl.mode_less_reason == ""
    evidence_text = " ".join(decl.evidence)
    assert len(evidence_text) >= 40, (rule_id, decl.evidence)


# =========================================================================== #
# AC7: intensity's reason cites the corpus that exercises it
# =========================================================================== #


def test_ac7_intensity_reason_cites_corpus_manifest_path():
    """Rescoped (item 146, 2026-09-03): mode_less_reason is now ""; the
    corpus-manifest citation moves to the declaration's evidence tuple
    (item 146 AC10)."""
    decl = _RULES["intensity"].mode_declaration
    assert decl.mode_less_reason == ""
    assert any("tests/corpus/intensity/manifest.json" in e for e in decl.evidence), decl.evidence


# =========================================================================== #
# AC8: the evidence AC7 cites actually holds
# =========================================================================== #


def test_ac8_intensity_manifest_has_no_failure_mode_field_and_named_cases():
    """Rescoped (item 146, 2026-09-03): item 146 AC22 adds `failure_mode` to
    every case, directly inverting the original claim; restated as "every
    case carries failure_mode, and the four case ids are unchanged"."""
    manifest_path = _REPO_ROOT / "tests" / "corpus" / "intensity" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty intensity corpus manifest"

    case_ids = {c["case_id"] for c in cases}
    assert case_ids == {
        "clean_hu",
        "implausible_metal",
        "implausible_soft_tissue",
        "degenerate_uniform",
    }
    for case in cases:
        assert "failure_mode" in case, case["case_id"]


# =========================================================================== #
# AC9: declarations and the corpus-derived map still agree
# =========================================================================== #


def test_ac9_rule_declaration_conflicts_empty_on_this_tree():
    catalogue = _catalogue()
    assert catalogue.rule_declaration_conflicts() == ()


def test_ac9_analytic_modes_are_within_the_mode_anchor_key_set():
    import segfacet.feature_docs as feature_docs_module

    anchor_modes = set(feature_docs_module.MODE_ANCHOR_PATHS.keys())
    for rule_id in _ANALYTIC_RULES:
        decl = _RULES[rule_id].mode_declaration
        assert set(decl.modes) <= anchor_modes, rule_id


def test_adv_future_corpus_case_still_binds_analytic_declaration(monkeypatch):
    """The analytic route must not become an escape hatch from the corpus ->
    declaration direction: if a future corpus case designates bounds for a
    mode it has not declared, the checker must still say so."""
    catalogue = _catalogue()
    real_scan = catalogue._scan_synth_rule_mode_map

    def _patched_scan():
        mapping = dict(real_scan())
        mapping["bounds"] = tuple(sorted(set(mapping.get("bounds", ())) | {5}))
        return mapping

    monkeypatch.setattr(catalogue, "_scan_synth_rule_mode_map", _patched_scan)

    conflicts = catalogue.rule_declaration_conflicts()
    assert any("bounds" in msg and "5" in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC10: the catalogue records a mode-less consuming rule as its own tag
# =========================================================================== #


def test_ac10_rule_mode_less_tag_present_iff_mode_less_consuming_rule():
    """Rescoped (item 146, 2026-09-03): no rule ships mode-less any more, so
    the `iff` half's positive branch cannot be exercised on this tree;
    restated to the liveness half only -- the tag is derived correctly
    (never present) rather than asserting a positive example exists."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    checked = False
    for entry in cat.entries:
        has_mode_less_rule = any(
            (decl := rule_mod.declaration_for(rid)) is not None and decl.mode_less_reason
            for rid in entry.consuming_rules
        )
        has_tag = "rule_mode_less" in entry.mode_evidence
        assert has_tag == has_mode_less_rule, entry.path
        assert has_mode_less_rule is False, entry.path
        checked = True
    assert checked, "expected a non-empty catalogue to check"


def test_adv_entry_with_no_consuming_rules_has_neither_declaration_tag():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    candidates = [e for e in cat.entries if not e.consuming_rules]
    assert candidates, "expected at least one entry with no consuming_rules"
    for entry in candidates:
        assert "rule_declaration" not in entry.mode_evidence, entry.path
        assert "rule_mode_less" not in entry.mode_evidence, entry.path


def test_adv_shared_reference_delta_and_intensity_entry_carries_declaration_tag():
    """Rescoped (item 146, 2026-09-03): the two intensity rules no longer
    ship mode-less -- they now declare mode 9 -- so no entry can carry both
    'rule_declaration' and 'rule_mode_less' any more. The reference_delta.*
    entry previously shared between the analytic reference_delta declarer
    and a mode-less intensity rule is now shared between two declaring
    rules, and carries a single 'rule_declaration' tag plus the union of
    both rules' declared modes: (1, 2, 9) -- reference_delta's own (1, 2)
    plus mode 9. Item 148 narrows this rule-granular bookkeeping; until then
    every path either rule reaches carries every mode either declares (the
    item 146 spec's stated, temporary state)."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)

    candidates = [
        e
        for e in cat.entries
        if e.path.startswith("reference_delta.")
        and set(e.consuming_rules) & set(_ANALYTIC_RULES)
        and set(e.consuming_rules) & set(_INTENSITY_RULES)
    ]
    assert candidates, (
        "expected at least one reference_delta.* entry shared between an "
        "analytic and an intensity (mode-9-declaring) rule"
    )
    for entry in candidates:
        assert "rule_declaration" in entry.mode_evidence, entry.path
        assert "rule_mode_less" not in entry.mode_evidence, entry.path
        assert entry.failure_modes == (1, 2, 9), entry.path


def test_adv_per_label_container_keeps_corpus_modes_and_gains_declaration_last():
    """Rescoped (item 146, 2026-09-03): the intensity rules now declare mode
    9 rather than shipping mode-less, so the per_label container entry can
    no longer carry 'rule_mode_less' -- but the same rules still reach the
    same underlying per-label paths, so the container still aggregates a
    'rule_declaration' tag from them, appended last (the aggregation order
    this container's construction has always used)."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    entry = next((e for e in cat.entries if e.path == "per_label"), None)
    assert entry is not None, "expected a per_label container entry"
    assert entry.failure_modes, "expected per_label to still carry corpus-derived modes"
    assert "rule_mode_less" not in entry.mode_evidence, entry.mode_evidence
    assert "rule_declaration" in entry.mode_evidence
    assert entry.mode_evidence[-1] == "rule_declaration", entry.mode_evidence


# =========================================================================== #
# AC11: mode_evidence keeps a canonical order
# =========================================================================== #


def test_ac11_mode_evidence_is_canonical_subsequence_or_unmapped():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    for entry in cat.entries:
        evidence = entry.mode_evidence
        if evidence == ("rule_unmapped",):
            continue
        positions = [_CANONICAL_TAG_ORDER.index(tag) for tag in evidence]
        assert positions == sorted(positions), (entry.path, evidence)
        assert len(set(evidence)) == len(evidence), (entry.path, evidence)


# =========================================================================== #
# AC12: nothing on this tree still reports rule_unmapped
# =========================================================================== #


def test_ac12_no_entry_reports_rule_unmapped_on_this_tree():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    offenders = [e.path for e in cat.entries if "rule_unmapped" in e.mode_evidence]
    assert offenders == []


# =========================================================================== #
# AC13: the declared mode reaches the failure_modes column
# =========================================================================== #


def test_ac13_bounds_or_reference_delta_consumers_carry_mode_two():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    candidates = [
        e for e in cat.entries if set(e.consuming_rules) & set(_ANALYTIC_RULES)
    ]
    assert candidates, "expected at least one entry consumed by bounds/reference_delta"
    for entry in candidates:
        assert 2 in entry.failure_modes, entry.path


# =========================================================================== #
# AC14: intensity-only paths are honestly mode-less, not unmapped
# =========================================================================== #


def test_ac14_intensity_only_non_anchor_entries_are_honestly_mode_less():
    """Rescoped (item 146, 2026-09-03): the honesty claim survives in a new
    form -- an intensity-only, non-anchor entry now carries failure_modes ==
    (9,) and a 'rule_declaration' tag, which is *more* honest than the
    previous mode-less disposition, not less."""
    catalogue = _catalogue()
    import segfacet.feature_docs as feature_docs_module

    cat = catalogue.build_catalogue(strict=True)
    anchor_paths = {p for paths in feature_docs_module.MODE_ANCHOR_PATHS.values() for p in paths}
    candidates = [
        e
        for e in cat.entries
        if e.consuming_rules
        and set(e.consuming_rules) <= set(_INTENSITY_RULES)
        and e.path not in anchor_paths
    ]
    assert candidates, "expected at least one intensity-only, non-anchor entry"
    for entry in candidates:
        assert entry.failure_modes == (9,), entry.path
        assert entry.mode_evidence == ("rule_declaration",), entry.path


# =========================================================================== #
# AC15: both committed catalogue artifacts regenerate byte-identically
# =========================================================================== #


def test_ac15_catalogue_artifacts_regenerate_byte_identically(tmp_path):
    catalogue = _catalogue()
    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

    fresh_json_bytes = json_dest.read_bytes()
    fresh_md_bytes = md_dest.read_bytes()
    assert fresh_json_bytes, "regenerated JSON must not be empty"
    assert fresh_md_bytes, "regenerated Markdown must not be empty"

    assert fresh_json_bytes == committed_json.read_bytes()
    assert fresh_md_bytes == committed_md.read_bytes()

    payload = json.loads(fresh_json_bytes)
    assert payload["schema_version"] == "1.1"


def test_adv_measured_artifact_movement_counts_from_spec():
    """Rescoped (item 146, 2026-09-03): the two intensity rules move from
    mode-less to declaring mode 9, so every entry the pre-item distribution
    tagged 'rule_mode_less' loses that tag and gains 'rule_declaration'
    (folding into whichever combination it already carried); no entry is
    added or removed, and mode1_count/mode2_count are untouched because
    bounds/reference_delta's own declared modes are unchanged. Derived
    arithmetically from the pre-item committed distribution (this test's own
    original figures, above in git history) and item 146's re-declaration --
    the same "simulated against the committed catalogue with the proposed
    declarations in place" style the pre-item docstring used, re-measured
    2026-09-03:
      ("rule_mode_less",): 4              -> folds into ("rule_declaration",)
      ("rule_declaration", "rule_mode_less"): 7 -> folds into ("rule_declaration",)
      ("rule_mode_map", "rule_declaration", "rule_mode_less"): 1
          -> folds into ("rule_mode_map", "rule_declaration")
    giving ("rule_declaration",): 7 + 4 + 7 = 18 and
    ("rule_mode_map", "rule_declaration"): 25 + 1 = 26; the other three
    combinations (unreached by either intensity rule) are untouched."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    entries = cat.entries
    assert len(entries) == 138

    mode2_count = sum(1 for e in entries if 2 in e.failure_modes)
    assert mode2_count == 21

    mode1_count = sum(1 for e in entries if 1 in e.failure_modes)
    assert mode1_count == 19

    mode9_count = sum(1 for e in entries if 9 in e.failure_modes)
    assert mode9_count == 12

    distribution = Counter(e.mode_evidence for e in entries)
    expected = {
        (): 86,
        ("rule_mode_map", "rule_declaration"): 26,
        ("rule_declaration",): 18,
        ("per_mode_metric", "rule_mode_map", "rule_declaration"): 6,
        ("per_mode_metric",): 2,
    }
    for key, count in expected.items():
        assert distribution.get(key, 0) == count, (key, distribution)
    assert distribution.get(("rule_unmapped",), 0) == 0
    assert distribution.get(("rule_mode_less",), 0) == 0
    assert distribution.get(("rule_declaration", "rule_mode_less"), 0) == 0
    assert distribution.get(("rule_mode_map", "rule_declaration", "rule_mode_less"), 0) == 0
    assert sum(distribution.values()) == 138


# =========================================================================== #
# AC16: the catalogue-gap finding is captured durably
# =========================================================================== #


_GAP_LINE_RE = re.compile(r"^- \[[ x]\] gap ")


def test_ac16_catalogue_gap_finding_captured_in_inbox_or_archive():
    docs_dir = _REPO_ROOT / "docs" / "aide"
    candidate_files = [docs_dir / "insights.md"]
    archive_dir = docs_dir / "insights"
    if archive_dir.is_dir():
        candidate_files.extend(sorted(archive_dir.glob("archive-*.md")))
    assert candidate_files, "expected at least the live insight inbox to exist"

    matches = []
    for path in candidate_files:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not _GAP_LINE_RE.match(line):
                continue
            if "intensity" in line and "§6" in line and "item 137" in line:
                matches.append(line)

    assert matches, "expected a captured gap line naming intensity, §6 and item 137"
    for line in matches:
        assert re.search(r"\d{4}-\d{2}-\d{2}", line), line


# =========================================================================== #
# AC17: §6 was recorded against, not grown
# =========================================================================== #


def test_ac17_vision_section_six_still_has_exactly_eight_modes():
    vision_path = _REPO_ROOT / "docs" / "aide" / "vision.md"
    text = vision_path.read_text(encoding="utf-8")

    section_match = re.search(
        r"^## 6\. Segmentation Failure Modes[^\n]*\n(.*?)(?=^## \d|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert section_match is not None, "expected a '## 6. Segmentation Failure Modes' section"
    section_text = section_match.group(1)

    numbered_headings = re.findall(r"^\d+\.\s+\S", section_text, flags=re.MULTILINE)
    assert len(numbered_headings) == 8, numbered_headings


def test_ac17_mode_anchor_paths_key_set_still_one_through_eight():
    import segfacet.feature_docs as feature_docs_module

    assert set(feature_docs_module.MODE_ANCHOR_PATHS.keys()) == set(range(1, 9))


# =========================================================================== #
# AC18: the disposition is metadata only
# =========================================================================== #


@pytest.mark.parametrize("rule_id", sorted(_DISPOSITIONED))
def test_ac18_replacing_a_dispositioned_rules_declaration_leaves_run_rules_unchanged(
    rule_id, monkeypatch
):
    record, config = _fixed_record()
    before = run_rules(record, config)
    assert isinstance(before, list)

    rule = _RULES[rule_id]
    replacement = rule_mod.RuleModeDeclaration(
        mode_less_reason="AC18 adversarial replacement -- must not affect evaluate()"
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    after = run_rules(record, config)
    assert after == before


def test_ac18_replacing_all_four_dispositioned_declarations_leaves_run_rules_unchanged(
    monkeypatch,
):
    record, config = _fixed_record()
    before = run_rules(record, config)

    for rule_id in _DISPOSITIONED:
        monkeypatch.setattr(
            _RULES[rule_id],
            "mode_declaration",
            rule_mod.RuleModeDeclaration(modes=(1,), evidence=("adversarial replacement",)),
        )

    after = run_rules(record, config)
    assert after == before


# =========================================================================== #
# Adversarial: rule_unmapped is narrowed, not removed (A5)
# =========================================================================== #


def test_adv_undeclared_stub_rule_is_reported_by_conflicts_checker(isolated_registry):
    class _NoDeclarationRule(Rule):
        rule_id = "__item137_no_declaration__"

        def evaluate(self, record, config):
            return []

    register_rule(_NoDeclarationRule)  # must not raise
    catalogue = _catalogue()
    conflicts = catalogue.rule_declaration_conflicts()
    assert any("__item137_no_declaration__" in msg for msg in conflicts), conflicts


def test_adv_pending_declaration_reintroduces_rule_unmapped(monkeypatch):
    """Monkeypatching a registered rule's declaration back to pending must
    still surface ("rule_unmapped",) for a path consumed only by it -- the
    branch items 138/139 rely on stays reachable and loud."""
    catalogue = _catalogue()
    import segfacet.feature_docs as feature_docs_module

    rule_id = "intensity"
    rule = _RULES[rule_id]
    replacement = rule_mod.RuleModeDeclaration(
        pending_reason="adversarial: re-pending for test_adv_pending_declaration_reintroduces_rule_unmapped"
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    cat = catalogue.build_catalogue(strict=True)
    anchor_paths = {p for paths in feature_docs_module.MODE_ANCHOR_PATHS.values() for p in paths}
    candidates = [
        e
        for e in cat.entries
        if e.consuming_rules
        and set(e.consuming_rules) <= {rule_id}
        and e.path not in anchor_paths
    ]
    assert candidates, "expected at least one entry consumed only by intensity"
    for entry in candidates:
        assert entry.mode_evidence == ("rule_unmapped",), entry.path


# =========================================================================== #
# Adversarial / edge cases -- determinism and immutability
# =========================================================================== #


def test_adv_rule_declaration_conflicts_deterministic():
    catalogue = _catalogue()
    first = catalogue.rule_declaration_conflicts()
    second = catalogue.rule_declaration_conflicts()
    assert first == second


def test_adv_build_catalogue_mode_evidence_deterministic():
    catalogue = _catalogue()
    first = catalogue.build_catalogue()
    second = catalogue.build_catalogue()
    assert len(first.entries) == len(second.entries)
    for e1, e2 in zip(first.entries, second.entries):
        assert e1.path == e2.path
        assert e1.mode_evidence == e2.mode_evidence
        assert e1.failure_modes == e2.failure_modes


def test_adv_dispositioned_declarations_are_frozen():
    for rule_id in _DISPOSITIONED:
        decl = _RULES[rule_id].mode_declaration
        with pytest.raises(dataclasses.FrozenInstanceError):
            decl.modes = (99,)  # type: ignore[misc]
