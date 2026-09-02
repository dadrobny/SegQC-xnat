"""Tests for item 136 -- declare each rule's targeted §6 failure mode(s)
(``segfacet.heuristics.rule.RuleModeDeclaration`` and the third
``mode_evidence`` source it gives ``segfacet.catalogue``).

Covers Acceptance Criteria AC1-AC14:

- AC1:  ``RuleModeDeclaration`` is a frozen dataclass with ``modes``,
        ``evidence``, ``mode_less_reason``, ``pending_reason`` (each defaulting
        to empty), re-exported from ``segfacet.heuristics`` alongside
        ``declaration_for`` / ``iter_rule_declarations``.
- AC2:  every ill-formed construction shape raises ``ValueError`` naming the
        offending field.
- AC3:  the seam is total over the shipped registry -- ten rules, every one
        carrying a ``RuleModeDeclaration`` instance.
- AC4:  the six corroborated rules declare exactly the corpus-designated
        modes, tagged ``"corpus"``.
- AC5:  the four contested rules are ``pending``, naming item 137.
- AC6:  declarations and the corpus-derived map agree on this tree.
- AC7:  a corpus-designated mode a rule fails to declare is reported.
- AC8:  a declared mode no corpus case supports is reported.
- AC9:  an undeclared registered rule registers cleanly and is reported.
- AC10: this item moves no attribution (declared ⊆ corpus-derived).
- AC11: the catalogue gains ``"rule_declaration"`` as a third evidence tag,
        ordered last.
- AC12: ``failure_modes`` is unchanged by the new source.
- AC13: both committed catalogue artifacts regenerate byte-identically.
- AC14: the seam is metadata only -- ``run_rules`` is unaffected.

Adversarial / edge-case scenarios included: the full ill-formed-construction
table (all-empty, multi-state, unordered/duplicate/out-of-range/non-int
modes, empty/non-string evidence elements); a ``"corpus"``-tagged declaration
carrying an extra free-form evidence tag still binds the declared->corpus
direction; an entry with no consuming rules gains no ``"rule_declaration"``
tag; an anchor path whose consuming rules declare no modes keeps
``("per_mode_metric",)`` unchanged; the exact expected-artifact-movement
counts from the item spec (32 / 18 / 86 / 2); determinism of
``rule_declaration_conflicts()`` and ``build_catalogue()``; a live
declaration object cannot be mutated in place; ``declaration_for`` on an
unknown id returns ``None``.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import segfacet.heuristics as heuristics_pkg
import segfacet.heuristics.rule as rule_mod
from segfacet.heuristics.rule import Rule, _RULES, iter_rules, register_rule
from segfacet.heuristics.runner import run_rules
from segfacet.config import bundled_default_config
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import build_clean_spine


def _catalogue():
    """Local import of ``segfacet.catalogue`` (mirrors
    ``tests/test_103_feature_catalogue.py``'s ``_catalogue()``), so this file
    still collects even though ``scan_synth_rule_mode_map`` /
    ``rule_declaration_conflicts`` are new names this item adds."""
    import segfacet.catalogue as catalogue

    return catalogue


_REPO_ROOT = Path(__file__).resolve().parents[1]

_CORROBORATED = {
    "border": (6,),
    "coverage": (5,),
    "fragmentation": (2, 3),
    "mislabel": (1, 4),
    "overlap": (8,),
    "sequence": (7,),
}
_CONTESTED = ("bounds", "intensity", "reference_delta", "intensity_reference_delta")


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (the house pattern in
    ``tests/test_026_rule_engine_core.py``) so a stub rule registered for
    AC9's adversarial coverage cannot leak into another test's clean-tree
    assertions (Testing Strategy: "Registry isolation")."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


def _fixed_record():
    config = bundled_default_config()
    clean = build_clean_spine()
    return extract_feature_record(clean.seg_img, config), config


# =========================================================================== #
# AC1: RuleModeDeclaration exists, is frozen, and is re-exported
# =========================================================================== #


def test_ac1_is_frozen_dataclass():
    assert dataclasses.is_dataclass(rule_mod.RuleModeDeclaration)
    assert rule_mod.RuleModeDeclaration.__dataclass_params__.frozen is True


def test_ac1_field_names():
    names = {f.name for f in dataclasses.fields(rule_mod.RuleModeDeclaration)}
    assert names == {"modes", "evidence", "mode_less_reason", "pending_reason"}


def test_ac1_unset_fields_default_empty():
    decl = rule_mod.RuleModeDeclaration(mode_less_reason="rationale")
    assert decl.modes == ()
    assert decl.evidence == ()
    assert decl.pending_reason == ""


def test_ac1_frozen_instance_rejects_attribute_assignment():
    decl = rule_mod.RuleModeDeclaration(mode_less_reason="rationale")
    with pytest.raises(dataclasses.FrozenInstanceError):
        decl.modes = (1,)  # type: ignore[misc]


def test_ac1_reexported_from_heuristics_package():
    for name in ("RuleModeDeclaration", "declaration_for", "iter_rule_declarations"):
        assert hasattr(heuristics_pkg, name), name
        assert name in heuristics_pkg.__all__, name
    assert heuristics_pkg.RuleModeDeclaration is rule_mod.RuleModeDeclaration


def test_ac1_iter_rule_declarations_ascending_by_rule_id():
    pairs = list(rule_mod.iter_rule_declarations())
    assert len(pairs) == 10
    ids = [rule_id for rule_id, _decl in pairs]
    assert ids == sorted(ids)


def test_ac1_declaration_for_accepts_rule_instance_and_id():
    border_rule = _RULES["border"]
    assert rule_mod.declaration_for(border_rule) == border_rule.mode_declaration
    assert rule_mod.declaration_for("border") == border_rule.mode_declaration


# =========================================================================== #
# AC2: a silent or malformed declaration cannot be constructed
# =========================================================================== #

_INVALID_CONSTRUCTIONS = [
    pytest.param({}, ("modes", "mode_less_reason", "pending_reason"), id="all_four_empty"),
    pytest.param(
        {"modes": (2,), "evidence": ("x",), "mode_less_reason": "r"},
        ("modes", "mode_less_reason"),
        id="modes_and_mode_less_reason",
    ),
    pytest.param(
        {"modes": (2,), "evidence": ("x",), "pending_reason": "r"},
        ("modes", "pending_reason"),
        id="modes_and_pending_reason",
    ),
    pytest.param(
        {"mode_less_reason": "r", "pending_reason": "r2"},
        ("mode_less_reason", "pending_reason"),
        id="mode_less_reason_and_pending_reason",
    ),
    pytest.param({"modes": (2,), "evidence": ()}, ("evidence",), id="modes_with_empty_evidence"),
    pytest.param({"modes": (2, 1), "evidence": ("x",)}, ("modes",), id="modes_not_ascending"),
    pytest.param({"modes": (2, 2), "evidence": ("x",)}, ("modes",), id="modes_duplicate"),
    pytest.param({"modes": (0,), "evidence": ("x",)}, ("modes",), id="modes_zero"),
    pytest.param({"modes": (-1,), "evidence": ("x",)}, ("modes",), id="modes_negative"),
    pytest.param({"modes": (True,), "evidence": ("x",)}, ("modes",), id="modes_bool"),
    pytest.param({"modes": ("2",), "evidence": ("x",)}, ("modes",), id="modes_string"),
    pytest.param({"modes": (2,), "evidence": ("",)}, ("evidence",), id="evidence_empty_string"),
    pytest.param({"modes": (2,), "evidence": (1,)}, ("evidence",), id="evidence_non_string"),
]


@pytest.mark.parametrize("kwargs, expected_field_names", _INVALID_CONSTRUCTIONS)
def test_ac2_ill_formed_declaration_raises_naming_field(kwargs, expected_field_names):
    with pytest.raises(ValueError) as excinfo:
        rule_mod.RuleModeDeclaration(**kwargs)
    message = str(excinfo.value)
    assert message.strip()
    assert any(name in message for name in expected_field_names), message


# =========================================================================== #
# AC3: the seam is total over the shipped registry
# =========================================================================== #


def test_ac3_ten_rules_registered():
    assert len(list(iter_rules())) == 10


def test_ac3_every_registered_rule_has_a_declaration_instance():
    for rule in iter_rules():
        decl = rule.mode_declaration
        assert decl is not None, rule.rule_id
        assert isinstance(decl, rule_mod.RuleModeDeclaration), rule.rule_id


def test_ac3_no_rule_inherits_the_abc_none_default():
    # The ABC itself still defaults to None (A3: no hard gate at registration);
    # every concrete, registered rule must override it.
    assert Rule.mode_declaration is None
    for rule in iter_rules():
        assert rule.mode_declaration is not None, rule.rule_id
        assert type(rule).mode_declaration is not None, rule.rule_id


# =========================================================================== #
# AC4: the six corroborated rules declare exactly the corpus-designated modes
# =========================================================================== #


@pytest.mark.parametrize("rule_id, modes", sorted(_CORROBORATED.items()))
def test_ac4_corroborated_rule_declares_corpus_modes(rule_id, modes):
    decl = _RULES[rule_id].mode_declaration
    assert decl.modes == modes
    assert "corpus" in decl.evidence
    assert decl.mode_less_reason == ""
    assert decl.pending_reason == ""


def test_ac4_corroborated_modes_match_measured_corpus_map():
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    for rule_id, modes in _CORROBORATED.items():
        assert corpus_map.get(rule_id) == modes, rule_id


# =========================================================================== #
# AC5: the four contested rules are pending, not pre-empted
# =========================================================================== #


@pytest.mark.parametrize("rule_id", sorted(_CONTESTED))
def test_ac5_contested_rule_is_pending_naming_item_137(rule_id):
    decl = _RULES[rule_id].mode_declaration
    assert decl.modes == ()
    assert decl.mode_less_reason == ""
    assert decl.pending_reason != ""
    assert "137" in decl.pending_reason


# =========================================================================== #
# AC6: declarations and the corpus-derived map agree on this tree
# =========================================================================== #


def test_ac6_rule_declaration_conflicts_empty_on_this_tree():
    catalogue = _catalogue()
    assert catalogue.rule_declaration_conflicts() == ()


def test_ac6_every_corpus_designated_mode_is_in_the_declaration():
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    assert corpus_map, "expected a non-empty corpus-derived rule->mode map"
    for rule_id, modes in corpus_map.items():
        decl = rule_mod.declaration_for(rule_id)
        assert decl is not None, rule_id
        for mode in modes:
            assert mode in decl.modes, (rule_id, mode)


# =========================================================================== #
# AC7: a corpus-designated mode a rule fails to declare is reported
# =========================================================================== #


def test_ac7_dropped_corpus_mode_is_reported_naming_both(monkeypatch):
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    rule_id, modes = next((rid, m) for rid, m in corpus_map.items() if m)
    dropped_mode = modes[0]

    rule = _RULES[rule_id]
    replacement = rule_mod.RuleModeDeclaration(
        mode_less_reason="AC7 adversarial: deliberately drops a corpus-designated mode"
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.rule_declaration_conflicts()
    assert conflicts, "expected at least one conflict"
    assert any(rule_id in msg and str(dropped_mode) in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC8: a declared mode no corpus case supports is reported
# =========================================================================== #


def test_ac8_surplus_declared_mode_is_reported_naming_both(monkeypatch):
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    rule_id = "sequence"
    corpus_modes = set(corpus_map.get(rule_id, ()))
    surplus_mode = next(m for m in range(1, 9) if m not in corpus_modes)
    new_modes = tuple(sorted(corpus_modes | {surplus_mode}))

    rule = _RULES[rule_id]
    replacement = rule_mod.RuleModeDeclaration(modes=new_modes, evidence=("corpus",))
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.rule_declaration_conflicts()
    assert conflicts, "expected at least one conflict"
    assert any(rule_id in msg and str(surplus_mode) in msg for msg in conflicts), conflicts


def test_adv_corpus_tag_plus_other_tag_still_binds_ac8_direction(monkeypatch):
    """A2: "corpus" plus another free-form tag still binds the declared ->
    corpus direction -- the reserved tag need not be the only one."""
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    rule_id = "sequence"
    corpus_modes = set(corpus_map.get(rule_id, ()))
    surplus_mode = next(m for m in range(1, 9) if m not in corpus_modes)
    new_modes = tuple(sorted(corpus_modes | {surplus_mode}))

    rule = _RULES[rule_id]
    replacement = rule_mod.RuleModeDeclaration(
        modes=new_modes, evidence=("corpus", "analytic-note")
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.rule_declaration_conflicts()
    assert any(rule_id in msg and str(surplus_mode) in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC9: a registered rule with no declaration registers without error and is
# reported by the checker
# =========================================================================== #


def test_ac9_registered_rule_with_no_declaration_registers_cleanly(isolated_registry):
    class _NoDeclarationRule(Rule):
        rule_id = "__item136_no_declaration__"

        def evaluate(self, record, config):
            return []

    register_rule(_NoDeclarationRule)  # must not raise
    assert "__item136_no_declaration__" in _RULES


def test_ac9_declaration_for_returns_none_for_undeclared_rule(isolated_registry):
    class _NoDeclarationRule(Rule):
        rule_id = "__item136_no_declaration__"

        def evaluate(self, record, config):
            return []

    register_rule(_NoDeclarationRule)
    assert rule_mod.declaration_for("__item136_no_declaration__") is None


def test_ac9_checker_reports_the_undeclared_rule(isolated_registry):
    class _NoDeclarationRule(Rule):
        rule_id = "__item136_no_declaration__"

        def evaluate(self, record, config):
            return []

    register_rule(_NoDeclarationRule)
    catalogue = _catalogue()
    conflicts = catalogue.rule_declaration_conflicts()
    assert any("__item136_no_declaration__" in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC10: this item moves no attribution
# =========================================================================== #


def test_ac10_declared_modes_subset_of_corpus_map_for_every_rule():
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    for rule in iter_rules():
        decl = rule.mode_declaration
        allowed = set(corpus_map.get(rule.rule_id, ()))
        assert set(decl.modes) <= allowed, (rule.rule_id, decl.modes, allowed)


# =========================================================================== #
# AC11: the catalogue gains the declaration as a third evidence source
# =========================================================================== #


def test_ac11_rule_declaration_tag_present_iff_declared_modes_contributed():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    for entry in cat.entries:
        has_declared_modes = any(
            (decl := rule_mod.declaration_for(rid)) is not None and decl.modes
            for rid in entry.consuming_rules
        )
        assert ("rule_declaration" in entry.mode_evidence) == has_declared_modes, entry.path


def test_ac11_rule_declaration_tag_is_last_when_present():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    tagged = [e for e in cat.entries if "rule_declaration" in e.mode_evidence]
    assert tagged, "expected at least one entry tagged with rule_declaration"
    for entry in tagged:
        assert entry.mode_evidence[-1] == "rule_declaration", entry.mode_evidence


def test_adv_entry_with_no_consuming_rules_has_no_rule_declaration_tag():
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    candidates = [e for e in cat.entries if not e.consuming_rules]
    assert candidates, "expected at least one entry with no consuming_rules"
    for entry in candidates:
        assert "rule_declaration" not in entry.mode_evidence, entry.path


def test_adv_anchor_path_without_declared_rule_modes_keeps_per_mode_metric_only():
    catalogue = _catalogue()
    import segfacet.feature_docs as feature_docs_module

    cat = catalogue.build_catalogue(strict=True)
    anchor_paths = {p for paths in feature_docs_module.MODE_ANCHOR_PATHS.values() for p in paths}
    entries_by_path = {e.path: e for e in cat.entries}

    checked = False
    for path in anchor_paths:
        entry = entries_by_path.get(path)
        if entry is None:
            continue
        has_declared_modes = any(
            (decl := rule_mod.declaration_for(rid)) is not None and decl.modes
            for rid in entry.consuming_rules
        )
        if not has_declared_modes:
            checked = True
            assert "per_mode_metric" in entry.mode_evidence, entry.path
            assert "rule_declaration" not in entry.mode_evidence, entry.path
    assert checked, "expected at least one anchor path whose consuming rules declare no modes"


# =========================================================================== #
# AC12: the failure_modes column is unchanged by the new source
# =========================================================================== #


def test_ac12_failure_modes_recomputed_independently_matches():
    catalogue = _catalogue()
    import segfacet.feature_docs as feature_docs_module

    cat = catalogue.build_catalogue(strict=True)
    corpus_map = catalogue.scan_synth_rule_mode_map()

    anchor_modes_by_path = {}
    for mode, paths in feature_docs_module.MODE_ANCHOR_PATHS.items():
        for path in paths:
            anchor_modes_by_path.setdefault(path, set()).add(mode)

    assert cat.entries, "expected a non-empty catalogue"
    for entry in cat.entries:
        anchor_modes = anchor_modes_by_path.get(entry.path, set())
        corpus_rule_modes: set = set()
        for rule_id in entry.consuming_rules:
            corpus_rule_modes.update(corpus_map.get(rule_id, ()))
        expected = tuple(sorted(anchor_modes | corpus_rule_modes))
        assert entry.failure_modes == expected, entry.path


# =========================================================================== #
# AC13: both committed catalogue artifacts regenerate byte-identically
# =========================================================================== #


def test_ac13_catalogue_artifacts_regenerate_byte_identically(tmp_path):
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


def test_adv_expected_artifact_movement_counts_from_spec():
    """Directly checks the item's own "Expected artifact movement" figures
    (measured on the committed catalogue, 2026-09-02): of 138 entries, 32
    gain "rule_declaration", 18 stay ("rule_unmapped",), 86 stay empty, and 2
    stay ("per_mode_metric",)."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    entries = cat.entries
    assert len(entries) == 138

    gained_rule_declaration = sum(1 for e in entries if "rule_declaration" in e.mode_evidence)
    stayed_rule_unmapped = sum(1 for e in entries if e.mode_evidence == ("rule_unmapped",))
    stayed_empty = sum(1 for e in entries if e.mode_evidence == ())
    stayed_per_mode_metric_only = sum(1 for e in entries if e.mode_evidence == ("per_mode_metric",))

    assert gained_rule_declaration == 32
    assert stayed_rule_unmapped == 18
    assert stayed_empty == 86
    assert stayed_per_mode_metric_only == 2


# =========================================================================== #
# AC14: the seam is metadata only
# =========================================================================== #


def test_ac14_replacing_one_rules_declaration_leaves_run_rules_unchanged(monkeypatch):
    record, config = _fixed_record()
    before = run_rules(record, config)
    assert isinstance(before, list)

    rule = _RULES["border"]
    replacement = rule_mod.RuleModeDeclaration(
        mode_less_reason="AC14 adversarial replacement -- must not affect evaluate()"
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    after = run_rules(record, config)
    assert after == before


def test_ac14_replacing_every_rules_declaration_leaves_run_rules_unchanged(monkeypatch):
    record, config = _fixed_record()
    before = run_rules(record, config)

    for rule in iter_rules():
        monkeypatch.setattr(
            rule,
            "mode_declaration",
            rule_mod.RuleModeDeclaration(
                mode_less_reason="AC14 adversarial replacement across every rule"
            ),
        )

    after = run_rules(record, config)
    assert after == before


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


def test_adv_live_declaration_object_cannot_be_mutated_in_place():
    decl = _RULES["border"].mode_declaration
    with pytest.raises(dataclasses.FrozenInstanceError):
        decl.modes = (99,)  # type: ignore[misc]


def test_adv_declaration_for_unknown_rule_id_returns_none():
    assert rule_mod.declaration_for("__totally_unknown_rule_id_item136__") is None
