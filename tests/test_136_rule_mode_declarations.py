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
        modes, with non-empty free-form evidence -- reconciled by item 147,
        which retires the reserved ``"corpus"`` evidence tag (evidence is
        provenance prose now, not a validated membership test).
- AC5:  the four contested rules are declared, not pending -- reconciled by
        item 137, which dispositioned all four (two analytic mode-2, two
        mode-less); see the reconciliation notes on the affected tests below.
- AC6:  declarations and the corpus-derived map agree on this tree.
- AC7:  a corpus-designated mode a rule fails to declare is reported.
- AC8:  a declared mode no corpus case supports is reported -- reconciled by
        item 147 onto the surviving surplus-mode direction, against
        ``segfacet.failure_modes.SPECIFICATION``'s key set (the retired
        ``"corpus"``-tagged declaration -> corpus branch was the old one).
- AC9:  an undeclared registered rule registers cleanly and is reported.
- AC10: this item moves no attribution for the six corpus-corroborated rules
        (declared ⊆ corpus-derived) -- reconciled by item 137 to that
        narrower claim, since its two analytic declarations deliberately
        attribute mode 2 with no corpus case behind them (A6).
- AC11: the catalogue gains ``"rule_declaration"`` as a third evidence tag --
        reconciled by item 137 to a canonical-order subsequence check, since
        its new ``"rule_mode_less"`` tag now sorts after ``"rule_declaration"``
        rather than ``"rule_declaration"`` always being last (A4).
- AC12: ``failure_modes`` is unchanged by the new source -- reconciled by
        item 137 to include declared modes as a third term in the
        independent recomputation, since its two analytic declarations now
        contribute mode 2 on their own.
- AC13: both committed catalogue artifacts regenerate byte-identically.
- AC14: the seam is metadata only -- ``run_rules`` is unaffected.

Adversarial / edge-case scenarios included: the full ill-formed-construction
table (all-empty, multi-state, unordered/duplicate/out-of-range/non-int
modes, empty/non-string evidence elements); an entry with no consuming rules
gains no ``"rule_declaration"``
tag; an anchor path whose consuming rules declare no modes keeps
``("per_mode_metric",)`` unchanged; the expected-artifact-movement counts,
reconciled for item 137 (0 ``rule_unmapped``, 86 empty); determinism of
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
    """Reconciled (item 148, 2026-09-04): ``RuleModeDeclaration`` gains
    ``consumed_paths`` (the per-path signal/bookkeeping/not-read
    classification), additively -- see
    ``tests/test_148_per_path_mode_attribution.py``'s own AC2."""
    names = {f.name for f in dataclasses.fields(rule_mod.RuleModeDeclaration)}
    assert names == {
        "modes",
        "evidence",
        "mode_less_reason",
        "pending_reason",
        "consumed_paths",
    }


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
    """Reconciled (item 147, 2026-09-04): the reserved ``"corpus"`` evidence
    tag is retired -- each corroborated rule's evidence is now free-form
    provenance naming the manifest/case, asserted here as non-empty rather
    than matched against the retired literal."""
    decl = _RULES[rule_id].mode_declaration
    assert decl.modes == modes
    assert decl.evidence, (rule_id, decl.evidence)
    assert decl.mode_less_reason == ""
    assert decl.pending_reason == ""


def test_ac4_corroborated_modes_match_measured_corpus_map():
    catalogue = _catalogue()
    corpus_map = catalogue.scan_synth_rule_mode_map()
    for rule_id, modes in _CORROBORATED.items():
        assert corpus_map.get(rule_id) == modes, rule_id


# =========================================================================== #
# AC5: the four contested rules are dispositioned, not pending
#
# Reconciled for item 137 (Testing Strategy: "existing tests to reconcile"):
# item 136 shipped these four as ``pending``, naming item 137 as the carrier
# of their disposition; item 137 fulfilled that by declaring each one --
# ``bounds`` and ``reference_delta`` analytic mode 2, ``intensity`` and
# ``intensity_reference_delta`` mode-less with a recorded reason. This test
# keeps the roll call of the four (AC1's "no rule ships pending" invariant)
# but asserts the post-137 shape: none of the four is pending any more, and
# each realises exactly one of the two non-pending states. The full content
# of each disposition (which modes, which reason, evidence quality) is
# item 137's own test module (``tests/test_137_mode_less_rule_disposition.py``).
# =========================================================================== #


@pytest.mark.parametrize("rule_id", sorted(_CONTESTED))
def test_ac5_contested_rule_is_dispositioned_not_pending(rule_id):
    decl = _RULES[rule_id].mode_declaration
    assert decl.pending_reason == "", rule_id
    assert bool(decl.modes) != bool(decl.mode_less_reason), rule_id


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
# AC8: a declared mode the specification does not list is reported
# =========================================================================== #


def test_ac8_surplus_declared_mode_is_reported_naming_both(monkeypatch):
    """Reconciled (item 147, 2026-09-04). This test used to add a mode the
    **corpus map** does not designate and rely on the ``"corpus"``-tagged
    declaration -> corpus branch of ``rule_declaration_conflicts()`` to
    report it. Item 147 retires both the reserved tag and that branch (the
    claim they stood for is data now -- the per-edge ``evidence_rung`` in
    ``segfacet.failure_modes.SPECIFICATION``), so the surplus-mode direction
    that survives is against the **specification's key set**: a rule
    declaring a mode the specification does not list is still reported,
    naming both the rule_id and the mode. Same force, live source. The
    complementary "an intended rule declares no such mode" direction is
    item 147's own
    ``tests/test_147_specification_is_the_record.py::test_ac13_...``.
    """
    import segfacet.failure_modes as fm

    catalogue = _catalogue()
    rule_id = "sequence"
    declared_modes = set(_RULES[rule_id].mode_declaration.modes)
    surplus_mode = next(m for m in range(1, 1000) if m not in set(fm.SPECIFICATION))
    new_modes = tuple(sorted(declared_modes | {surplus_mode}))

    rule = _RULES[rule_id]
    replacement = rule_mod.RuleModeDeclaration(
        modes=new_modes, evidence=("test-evidence-item147",)
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.rule_declaration_conflicts()
    assert conflicts, "expected at least one conflict"
    assert any(rule_id in msg and str(surplus_mode) in msg for msg in conflicts), conflicts


# Reconciled (item 147, 2026-09-04): `test_adv_corpus_tag_plus_other_tag_still_
# binds_ac8_direction` was removed here. It exercised the declared -> corpus
# direction gated on `if "corpus" in decl.evidence:` in
# `catalogue.rule_declaration_conflicts()` -- item 147 step 8 deletes that
# branch outright (the reserved "corpus" tag is retired, not hardened), so
# the direction it proved ("corpus" plus another tag still binds) no longer
# exists to prove. Its force is carried forward by item 147's own
# `test_ac13_intended_rule_whose_rule_declares_no_such_mode_is_reported`
# (`tests/test_147_specification_is_the_record.py`), which is the surviving
# check that an over-claimed mode is still reported, now from the
# specification side.


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
#
# Reconciled for item 137 (Testing Strategy: "existing tests to reconcile",
# A6): the blanket "declared modes subset of corpus map, for every rule"
# claim stopped holding by design once item 137 landed two analytic
# declarations (``bounds``, ``reference_delta``) that deliberately attribute
# mode 2 with no corpus case behind them. What still holds -- and is item
# 136's actual claim, since every rule it dispositioned declared exactly the
# corpus-designated modes -- is containment for declarations tagged
# ``"corpus"`` specifically. Item 137's own analytic-vs-corpus distinction is
# tested in ``tests/test_137_mode_less_rule_disposition.py``.
#
# Reconciled again for item 147 (2026-09-04): the reserved ``"corpus"``
# evidence tag itself is retired -- no shipped declaration carries it any
# more (AC20), so ``test_ac10_corpus_tagged_declared_modes_subset_of_corpus_
# map``'s ``checked`` guard would find zero corpus-tagged declarations and
# fail on its own vacuity check, not on a real regression. Removed here;
# item 146's `_CORROBORATED` containment claim (every corroborated rule
# declares exactly the corpus-designated modes) is still exercised by
# ``test_ac4_corroborated_modes_match_measured_corpus_map`` above, which
# never depended on the tag.
# =========================================================================== #


# =========================================================================== #
# AC11: the catalogue gains the declaration as a third evidence source
# =========================================================================== #


def test_ac11_rule_declaration_tag_present_iff_declared_modes_contributed():
    """Reconciled (item 148, 2026-09-04): "contributed" now means "through a
    ``signal``-classified path" -- a rule declaring modes still leaves no
    ``rule_declaration`` tag on a path it only reaches ``bookkeeping`` or
    ``not-read``."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    for entry in cat.entries:
        role_by_rule = dict(entry.mode_roles)
        has_declared_modes = any(
            role_by_rule.get(rid) == "signal"
            and (decl := rule_mod.declaration_for(rid)) is not None
            and decl.modes
            for rid in entry.consuming_rules
        )
        assert ("rule_declaration" in entry.mode_evidence) == has_declared_modes, entry.path


def test_ac11_mode_evidence_is_canonical_order_subsequence():
    """Reconciled for item 137 (Testing Strategy: "existing tests to
    reconcile", A4): "rule_declaration is always last when present" stopped
    holding by design once item 137 added a fourth evidence tag,
    "rule_mode_less", which sorts *after* "rule_declaration" in the
    canonical order (a declared mode-less consuming rule is itself a further
    disposition, layered on top of any declared-mode attribution). The
    invariant that still holds -- and is the one item 137's own AC11 states
    -- is that mode_evidence is always a subsequence of the canonical
    tag order (per_mode_metric, rule_mode_map, rule_declaration,
    rule_mode_less), or exactly ("rule_unmapped",).

    Reconciled again (item 148, 2026-09-04): the canonical order grows two
    more tags, "rule_bookkeeping" and "rule_not_read", appended last -- the
    per-path classification's own evidence sources, layered on top of
    whichever mode-level tags already applied."""
    catalogue = _catalogue()
    canonical_order = (
        "per_mode_metric",
        "rule_mode_map",
        "rule_declaration",
        "rule_mode_less",
        "rule_bookkeeping",
        "rule_not_read",
    )
    cat = catalogue.build_catalogue(strict=True)
    tagged = [e for e in cat.entries if "rule_declaration" in e.mode_evidence]
    assert tagged, "expected at least one entry tagged with rule_declaration"
    for entry in tagged:
        positions = [canonical_order.index(tag) for tag in entry.mode_evidence]
        assert positions == sorted(positions), entry.mode_evidence


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
    """Reconciled for item 137 (Testing Strategy: "existing tests to
    reconcile"): the independent recomputation now includes each entry's
    declared-mode contribution (``RuleModeDeclaration.modes``) as a third
    term alongside the anchor-path and corpus-derived-map terms, since
    item 137's two analytic declarations (``bounds``, ``reference_delta``)
    contribute mode 2 to ``failure_modes`` with no corpus case behind them
    (A6) -- the two-term recomputation from item 136 under-counts those
    paths after this item.

    Reconciled again (item 148, 2026-09-04): a rule's corpus-derived and
    declared modes now reach ``failure_modes`` only through a path this rule
    classifies ``"signal"`` (``CatalogueEntry.mode_roles``) -- the per-path
    role gate this item adds. A ``bookkeeping``/``not-read`` path no longer
    inherits its consuming rule's whole mode tuple."""
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
        role_by_rule = dict(entry.mode_roles)
        anchor_modes = anchor_modes_by_path.get(entry.path, set())
        corpus_rule_modes: set = set()
        declared_rule_modes: set = set()
        for rule_id in entry.consuming_rules:
            if role_by_rule.get(rule_id) != "signal":
                continue
            corpus_rule_modes.update(corpus_map.get(rule_id, ()))
            decl = rule_mod.declaration_for(rule_id)
            if decl is not None:
                declared_rule_modes.update(decl.modes)
        expected = tuple(sorted(anchor_modes | corpus_rule_modes | declared_rule_modes))
        assert entry.failure_modes == expected, entry.path


# =========================================================================== #
# AC13: both committed catalogue artifacts regenerate byte-identically
# =========================================================================== #


def test_ac13_catalogue_artifacts_regenerate_byte_identically(tmp_path):
    """Reconciled (item 148, 2026-09-04): ``schema_version`` moves
    ``"1.1"`` -> ``"1.2"`` with the ``mode_roles`` shape."""
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
    assert payload["schema_version"] == "1.2"


def test_adv_expected_artifact_movement_counts_from_spec():
    """Directly checks the item's own "Expected artifact movement" figures
    (measured on the committed catalogue, 2026-09-02): of 138 entries, 32
    gain "rule_declaration", 18 stay ("rule_unmapped",), 86 stay empty, and 2
    stay ("per_mode_metric",).

    Superseded for item 137 (Testing Strategy: "existing tests to
    reconcile"): item 137's own disposition of the four rules this item left
    pending moves the distribution again -- 19 entries move mode_evidence and
    0 remain ("rule_unmapped",) (measured 2026-09-02, item 137's "Expected
    artifact movement"). Both measurements are of the same artifact at two
    points in its history; this test now pins item 137's figures, which
    supersede item 136's above.

    Reconciled again (item 148, 2026-09-04): the per-path classification
    moves 25 of 138 entries' ``failure_modes``/``mode_evidence`` (item 148's
    A5), but neither of the two figures this test still pins: the 86-entry
    ``()`` bucket and the 0-entry ``("rule_unmapped",)`` bucket are untouched
    by that movement (measured against item 148's own regenerated artifact) --
    this test re-verifies both hold, it does not re-measure them."""
    catalogue = _catalogue()
    cat = catalogue.build_catalogue(strict=True)
    entries = cat.entries
    assert len(entries) == 138

    stayed_rule_unmapped = sum(1 for e in entries if e.mode_evidence == ("rule_unmapped",))
    stayed_empty = sum(1 for e in entries if e.mode_evidence == ())

    assert stayed_rule_unmapped == 0
    assert stayed_empty == 86


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
