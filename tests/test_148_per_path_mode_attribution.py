"""Tests for item 148 -- per-path §6 mode attribution, so the catalogue stops
painting bookkeeping paths with modes they cannot evidence.

Item 136's mode attribution was rule-granular: every leaf path a declaring
rule consumes inherited that rule's *whole* mode tuple. This item gives each
rule's ``RuleModeDeclaration`` a declared per-path classification
(``segfacet.heuristics.rule.ConsumedPath``, ``PATH_ROLES ==
("signal", "bookkeeping", "not-read")``) of every leaf path it consumes, and
``segfacet.catalogue.build_catalogue`` gates a rule's mode contribution to a
path on that path being classified ``"signal"`` for that rule. The catalogue
renders the classification (``CatalogueEntry.mode_roles``, two new
``mode_evidence`` tags) rather than silently dropping it, and
``segfacet.catalogue.path_classification_conflicts()`` is the new
conformance checker.

AC -> test map (one focused test per AC, in AC order):

- AC1:  test_ac1_consumed_path_fields_and_path_roles_vocabulary,
        test_ac1_reexported_from_heuristics_package_and_rule_all
- AC2:  test_ac2_field_set_and_default_and_backward_compatible_construction
- AC3:  test_ac3_ill_formed_classification_rejected_naming_field_and_path
        (parametrized over the full malformed-shape table)
- AC4:  test_ac4_every_declaring_rule_classifies_exactly_what_it_consumes
- AC5:  test_ac5_unclassified_consumed_path_is_reported_naming_both
- AC6:  test_ac6_extra_classified_path_and_both_directions_reported_at_once
- AC7:  test_ac7_not_read_cannot_hide_an_observed_path
- AC8:  test_ac8_failure_modes_equal_anchor_union_signal_gated_terms
- AC9:  test_ac9_mode_roles_rendered_in_json_and_markdown
- AC10: test_ac10_evidence_gains_bookkeeping_and_not_read_tags_correctly
- AC11: test_ac11_three_bookkeeping_paths_empty_signal_path_still_shows
- AC12: test_ac12_every_mode_keeps_a_signal_path
- AC13: test_ac13_classification_moves_attribution_columns_and_nothing_else
- AC14: test_ac14_artifacts_byte_identical_run_to_run_and_match_committed
- AC15: test_ac15_schema_version_and_status_report_loader
- AC16: test_ac16_seam_stays_metadata_where_rules_fire
- AC17: test_ac17_threshold_constants_hold_pre_item_values (parametrized),
        test_ac17_no_rule_evaluate_body_references_declaration_symbols
- AC18: test_ac18_traceability_untouched_and_paths_derived_from_consuming_rules
- AC19: test_ac19_realised_universe_unchanged_and_item104_reports_no_drift
- AC20: test_ac20_both_conformance_checkers_stay_clean
- AC21: test_ac21_aide_check_reports_no_error_and_no_new_warning_class,
        test_ac21_aide_check_exits_zero

Adversarial / edge cases beyond the AC3 malformed-shape table: a duplicate
path; a ``not-read`` pair with an empty reason; a ``consumed_paths`` given as
a bare ``list``; a ``signal`` path declared with ``modes=()``; a role
differing from a ``PATH_ROLES`` member by case alone (``"Signal"``); a
``not-read`` pair on a path with mechanism-A ``"observed"`` evidence (AC7);
determinism of two ``build_catalogue()`` calls; immutability of a live
declaration's ``consumed_paths`` and non-mutation by ``build_catalogue``; an
entry with no consuming rules carries ``mode_roles == ()`` and none of the
four rule-sourced evidence tags; a stub rule with ``modes`` set and
``consumed_paths`` empty is reported and contributes no mode.

Fixtures and cost: ``shipped_catalogue`` is the one module-scoped,
unpatched ``build_catalogue(strict=True)`` call every AC that only reads the
shipped tree shares; AC5/AC6/AC7's monkeypatch scenarios and AC13's
all-``signal`` rebuild each patch a fresh, function-scoped ``monkeypatch``
so no scenario's declaration mutation can leak into another test.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from run_process import run_utf8

_REPO_ROOT = Path(__file__).resolve().parent.parent

_COMMITTED_CATALOGUE_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_COMMITTED_CATALOGUE_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"
_COMMITTED_TRACEABILITY_JSON = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
_COMMITTED_TRACEABILITY_MD = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"
_INTENSITY_MANIFEST_PATH = _REPO_ROOT / "tests" / "corpus" / "intensity" / "manifest.json"
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"
_ASR_MODULE_PATH = _REPO_ROOT / "scripts" / "aide_status_report.py"
_TEST_104_PATH = _REPO_ROOT / "tests" / "test_104_feature_catalogue_drift.py"

_CANONICAL_TAG_ORDER = (
    "per_mode_metric",
    "rule_mode_map",
    "rule_declaration",
    "rule_mode_less",
    "rule_bookkeeping",
    "rule_not_read",
)


# =========================================================================== #
# House fixtures / helpers
# =========================================================================== #


@pytest.fixture(scope="module")
def shipped_catalogue():
    """The one expensive, unpatched ``build_catalogue(strict=True)`` call
    every AC that only reads the shipped tree shares."""
    import segfacet.catalogue as catalogue

    cat = catalogue.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"
    return cat


def _entry(cat, path):
    for entry in cat.entries:
        if entry.path == path:
            return entry
    raise AssertionError(f"no catalogue entry for path {path!r}")


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (house pattern from
    ``test_136``/``test_137``/``test_146``), so a stub rule registered for an
    adversarial case cannot leak into another test."""
    from segfacet.heuristics.rule import _RULES

    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


def _status_report_module():
    """Load ``scripts/aide_status_report.py`` in isolation. The script uses
    ``from __future__ import annotations``, so its dataclasses resolve
    string annotations through ``sys.modules`` at class-definition time --
    without registering the module there first, that lookup finds nothing
    and ``dataclasses`` raises. Mirror the model at
    ``tests/test_103_feature_catalogue.py``'s module-scoped ``asr`` fixture
    (register before ``exec_module``), and remove the registration
    afterwards so nothing leaks into later tests."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("aide_status_report_148", _ASR_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _test104_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_test_104_for_148", _TEST_104_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _aide_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_aide_cli_148", _AIDE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# =========================================================================== #
# AC1: ConsumedPath / PATH_ROLES exist and are re-exported
# =========================================================================== #


def test_ac1_consumed_path_fields_and_path_roles_vocabulary():
    from segfacet.heuristics.rule import ConsumedPath, PATH_ROLES

    assert PATH_ROLES == ("signal", "bookkeeping", "not-read")

    assert dataclasses.is_dataclass(ConsumedPath)
    assert ConsumedPath.__dataclass_params__.frozen is True
    field_names = {f.name for f in dataclasses.fields(ConsumedPath)}
    assert field_names == {"path", "role", "reason"}


def test_ac1_reexported_from_heuristics_package_and_rule_all():
    import segfacet.heuristics as heuristics_pkg
    import segfacet.heuristics.rule as rule_mod

    for name in ("ConsumedPath", "PATH_ROLES"):
        assert name in rule_mod.__all__, name
        assert hasattr(heuristics_pkg, name), name
        assert name in heuristics_pkg.__all__, name
    assert heuristics_pkg.ConsumedPath is rule_mod.ConsumedPath
    assert heuristics_pkg.PATH_ROLES is rule_mod.PATH_ROLES


# =========================================================================== #
# AC2: RuleModeDeclaration carries consumed_paths additively
# =========================================================================== #


def test_ac2_field_set_and_default_and_backward_compatible_construction():
    from segfacet.heuristics.rule import RuleModeDeclaration

    names = {f.name for f in dataclasses.fields(RuleModeDeclaration)}
    assert names == {"modes", "evidence", "mode_less_reason", "pending_reason", "consumed_paths"}

    # Every existing standalone construction shape still constructs, and
    # defaults consumed_paths to ().
    decl_modes = RuleModeDeclaration(modes=(1,), evidence=("x",))
    assert decl_modes.consumed_paths == ()

    decl_mode_less = RuleModeDeclaration(mode_less_reason="rationale")
    assert decl_mode_less.consumed_paths == ()

    decl_pending = RuleModeDeclaration(pending_reason="deferred to item N")
    assert decl_pending.consumed_paths == ()


# =========================================================================== #
# AC3: an ill-formed classification is rejected at construction
# =========================================================================== #


def _cp(path, role, reason=""):
    from segfacet.heuristics.rule import ConsumedPath

    return ConsumedPath(path=path, role=role, reason=reason)


_AC3_INVALID_CONSTRUCTIONS = [
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths="per_label.a.b"),
        None,
        id="consumed_paths_bare_str",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=[_cp("per_label.a.b", "signal")]),
        "per_label.a.b",
        id="consumed_paths_list",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=("not_a_consumed_path_item148",)),
        "not_a_consumed_path_item148",
        id="element_not_consumed_path",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=(_cp("", "signal"),)),
        None,
        id="empty_path",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=(_cp("aa.bb", "signals"),)),
        "aa.bb",
        id="role_typo",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=(_cp("aa.bb", "Signal"),)),
        "aa.bb",
        id="role_case_mismatch",
    ),
    pytest.param(
        dict(
            modes=(1,),
            evidence=("ev",),
            consumed_paths=(_cp("aa.bb", "signal"), _cp("aa.bb", "bookkeeping", "why")),
        ),
        "aa.bb",
        id="duplicated_path",
    ),
    pytest.param(
        dict(
            modes=(1,),
            evidence=("ev",),
            consumed_paths=(_cp("zz.top", "signal"), _cp("aa.bb", "signal")),
        ),
        "aa.bb",
        id="non_ascending_order",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=(_cp("aa.bb", "bookkeeping", ""),)),
        "aa.bb",
        id="bookkeeping_empty_reason",
    ),
    pytest.param(
        dict(modes=(1,), evidence=("ev",), consumed_paths=(_cp("aa.bb", "not-read", ""),)),
        "aa.bb",
        id="not_read_empty_reason",
    ),
    pytest.param(
        dict(mode_less_reason="rationale", consumed_paths=(_cp("aa.bb", "signal"),)),
        "aa.bb",
        id="signal_on_mode_less_declaration",
    ),
]


@pytest.mark.parametrize("kwargs, expected_path", _AC3_INVALID_CONSTRUCTIONS)
def test_ac3_ill_formed_classification_rejected_naming_field_and_path(kwargs, expected_path):
    from segfacet.heuristics.rule import RuleModeDeclaration

    with pytest.raises(ValueError) as excinfo:
        RuleModeDeclaration(**kwargs)
    message = str(excinfo.value)
    assert message.strip()
    assert "consumed_paths" in message, message
    if expected_path is not None:
        assert expected_path in message, message


# =========================================================================== #
# AC4: every declaring rule classifies exactly what it consumes
# =========================================================================== #


def test_ac4_every_declaring_rule_classifies_exactly_what_it_consumes(shipped_catalogue):
    from segfacet.heuristics.rule import iter_rule_declarations

    cat = shipped_catalogue
    reach_by_rule = {}
    for entry in cat.entries:
        for rule_id in entry.consuming_rules:
            reach_by_rule.setdefault(rule_id, set()).add(entry.path)

    checked = 0
    for rule_id, decl in iter_rule_declarations():
        assert decl is not None, rule_id
        declared_paths = {cp.path for cp in decl.consumed_paths}
        consumed_paths = reach_by_rule.get(rule_id, set())
        assert declared_paths == consumed_paths, (
            rule_id,
            "unclassified:",
            consumed_paths - declared_paths,
            "surplus:",
            declared_paths - consumed_paths,
        )
        checked += 1
    assert checked == 10


# =========================================================================== #
# AC5: an unclassified consumed path is reported, naming both
# =========================================================================== #


def test_ac5_unclassified_consumed_path_is_reported_naming_both(monkeypatch, shipped_catalogue):
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import _RULES

    assert catalogue.path_classification_conflicts() == ()

    rule_id = "border"
    rule = _RULES[rule_id]
    decl = rule.mode_declaration
    assert decl.consumed_paths, "adversarial precondition: expected >=1 consumed path"
    dropped = decl.consumed_paths[0]
    remaining = decl.consumed_paths[1:]
    replacement = dataclasses.replace(decl, consumed_paths=remaining)
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.path_classification_conflicts()
    assert conflicts, "expected >=1 conflict"
    assert any(rule_id in msg and dropped.path in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC6: a classified path the rule does not consume is reported, naming both
# =========================================================================== #


def test_ac6_extra_classified_path_and_both_directions_reported_at_once(
    monkeypatch, shipped_catalogue
):
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import ConsumedPath, _RULES

    rule_id = "sequence"
    rule = _RULES[rule_id]
    decl = rule.mode_declaration
    assert decl.consumed_paths, "adversarial precondition: expected >=1 consumed path"

    cat = shipped_catalogue
    other_paths = {e.path for e in cat.entries if rule_id not in e.consuming_rules}
    assert other_paths, "adversarial precondition: expected an unconsumed path"
    extra_path = sorted(other_paths)[0]

    dropped = decl.consumed_paths[0]
    remaining = tuple(cp for cp in decl.consumed_paths if cp.path != dropped.path)
    injected = ConsumedPath(path=extra_path, role="bookkeeping", reason="AC6 adversarial probe")
    new_paths = tuple(sorted(remaining + (injected,), key=lambda cp: cp.path))
    replacement = dataclasses.replace(decl, consumed_paths=new_paths)
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.path_classification_conflicts()
    assert conflicts, "expected >=1 conflict"
    assert any(rule_id in msg and extra_path in msg for msg in conflicts), (
        "surplus direction not reported",
        conflicts,
    )
    assert any(rule_id in msg and dropped.path in msg for msg in conflicts), (
        "missing direction not reported",
        conflicts,
    )


# =========================================================================== #
# AC7: not-read cannot hide a path the rule demonstrably reads
# =========================================================================== #


def test_ac7_not_read_cannot_hide_an_observed_path(monkeypatch, shipped_catalogue):
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import ConsumedPath, _RULES

    assert catalogue.path_classification_conflicts() == ()

    cat = shipped_catalogue
    target = None
    for entry in cat.entries:
        evidence_by_rule = {}
        for rid, ev in entry.rule_evidence:
            evidence_by_rule.setdefault(rid, set()).add(ev)
        for rule_id in entry.consuming_rules:
            if "observed" not in evidence_by_rule.get(rule_id, set()):
                continue
            decl = _RULES[rule_id].mode_declaration
            cp = next((c for c in decl.consumed_paths if c.path == entry.path), None)
            if cp is not None and cp.role in ("signal", "bookkeeping"):
                target = (rule_id, entry.path)
                break
        if target is not None:
            break
    assert target is not None, "adversarial precondition: expected >=1 observed, non-not-read pair"
    rule_id, path = target

    rule = _RULES[rule_id]
    decl = rule.mode_declaration
    new_cp = ConsumedPath(path=path, role="not-read", reason="AC7 adversarial probe")
    new_paths = tuple(
        sorted(
            (cp if cp.path != path else new_cp for cp in decl.consumed_paths),
            key=lambda cp: cp.path,
        )
    )
    replacement = dataclasses.replace(decl, consumed_paths=new_paths)
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.path_classification_conflicts()
    assert conflicts, "expected >=1 conflict"
    assert any(rule_id in msg and path in msg for msg in conflicts), conflicts


# =========================================================================== #
# AC8: only signal paths inherit a rule's modes
# =========================================================================== #


def test_ac8_failure_modes_equal_anchor_union_signal_gated_terms(shipped_catalogue):
    import segfacet.catalogue as catalogue
    import segfacet.feature_docs as feature_docs
    from segfacet.heuristics.rule import declaration_for

    cat = shipped_catalogue
    corpus_map = catalogue.scan_synth_rule_mode_map()

    anchor_modes_by_path = {}
    for mode, paths in feature_docs.MODE_ANCHOR_PATHS.items():
        for path in paths:
            anchor_modes_by_path.setdefault(path, set()).add(mode)

    checked = 0
    for entry in cat.entries:
        role_by_rule = dict(entry.mode_roles)
        anchor_modes = anchor_modes_by_path.get(entry.path, set())
        signal_modes: set = set()
        for rule_id in entry.consuming_rules:
            if role_by_rule.get(rule_id) != "signal":
                continue
            signal_modes.update(corpus_map.get(rule_id, ()))
            decl = declaration_for(rule_id)
            if decl is not None:
                signal_modes.update(decl.modes)
        expected = tuple(sorted(anchor_modes | signal_modes))
        assert entry.failure_modes == expected, entry.path
        checked += 1
    assert checked == len(cat.entries)


# =========================================================================== #
# AC9: the classification is rendered, not merely applied
# =========================================================================== #


def _md_header_and_rows(md):
    lines = [line for line in md.splitlines() if line.strip().startswith("|")]
    header_cells = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")] for line in lines[2:]
    ]
    return header_cells, rows


def test_ac9_mode_roles_rendered_in_json_and_markdown(shipped_catalogue):
    import segfacet.catalogue as catalogue

    cat = shipped_catalogue

    checked = 0
    for entry in cat.entries:
        assert isinstance(entry.mode_roles, tuple), entry.path
        rule_ids = [rid for rid, _role in entry.mode_roles]
        assert rule_ids == sorted(rule_ids), entry.path
        assert {rid for rid, _role in entry.mode_roles} == set(entry.consuming_rules), entry.path
        checked += 1
    assert checked == len(cat.entries)

    as_dict = catalogue.catalogue_to_dict(cat)
    entry_dicts = [e for group in as_dict["groups"] for e in group["entries"]]
    assert entry_dicts, "expected non-empty serialised entries"
    entries_by_path = {e.path: e for e in cat.entries}
    for e_dict in entry_dicts:
        assert "mode_roles" in e_dict, e_dict["path"]
        expected = [list(pair) for pair in entries_by_path[e_dict["path"]].mode_roles]
        assert e_dict["mode_roles"] == expected, e_dict["path"]

    md = catalogue.render_markdown(cat)
    header_cells, rows = _md_header_and_rows(md)
    assert "§6 mode role(s)" in header_cells, header_cells
    role_col = header_cells.index("§6 mode role(s)")
    path_col = header_cells.index("path")

    # A path shared between an analytic "bookkeeping" declarer
    # (reference_delta) and a mechanism-B-only "not-read" declarer
    # (intensity_reference_delta): item 148's Description/Implementation
    # Steps table.
    known_path = "reference_delta.lower_pct"
    entry = _entry(cat, known_path)
    assert entry.mode_roles, "adversarial precondition: expected >=1 role on this path"
    row = next((r for r in rows if r[path_col] == known_path), None)
    assert row is not None, known_path
    role_cell = row[role_col]
    for rule_id, role in entry.mode_roles:
        assert f"{rule_id}: {role}" in role_cell, (known_path, rule_id, role, role_cell)


# =========================================================================== #
# AC10: the evidence column stays complete
# =========================================================================== #


def test_ac10_evidence_gains_bookkeeping_and_not_read_tags_correctly(shipped_catalogue):
    cat = shipped_catalogue
    checked_bookkeeping = 0
    checked_not_read = 0
    for entry in cat.entries:
        roles = {role for _rid, role in entry.mode_roles}
        has_bookkeeping = "bookkeeping" in roles
        has_not_read = "not-read" in roles
        assert ("rule_bookkeeping" in entry.mode_evidence) == has_bookkeeping, entry.path
        assert ("rule_not_read" in entry.mode_evidence) == has_not_read, entry.path
        if has_bookkeeping:
            checked_bookkeeping += 1
        if has_not_read:
            checked_not_read += 1

        if entry.mode_evidence == ("rule_unmapped",):
            continue
        positions = [_CANONICAL_TAG_ORDER.index(tag) for tag in entry.mode_evidence]
        assert positions == sorted(positions), (entry.path, entry.mode_evidence)
        assert len(set(entry.mode_evidence)) == len(entry.mode_evidence), entry.path

    assert checked_bookkeeping > 0, "expected >=1 entry tagged rule_bookkeeping"
    assert checked_not_read > 0, "expected >=1 entry tagged rule_not_read"


# =========================================================================== #
# AC11: the three named bookkeeping paths are no longer painted
# =========================================================================== #


def test_ac11_three_bookkeeping_paths_empty_signal_path_still_shows(shipped_catalogue):
    cat = shipped_catalogue
    for path in (
        "reference_delta.lower_pct",
        "reference_delta.{label}.label",
        "reference_delta.{label}.level_name",
    ):
        entry = _entry(cat, path)
        assert entry.failure_modes == (), path

    robust_z_path = "reference_delta.{label}.features.physical_volume_mm3.robust_z"
    entry = _entry(cat, robust_z_path)
    assert entry.failure_modes == (1, 2), robust_z_path


# =========================================================================== #
# AC12: every mode keeps a signal path
# =========================================================================== #


def test_ac12_every_mode_keeps_a_signal_path(shipped_catalogue):
    cat = shipped_catalogue
    paths_by_mode: dict = {}
    for entry in cat.entries:
        for mode in entry.failure_modes:
            paths_by_mode.setdefault(mode, set()).add(entry.path)

    mode9_paths = paths_by_mode.get(9, set())
    assert mode9_paths == {
        "image_features.per_label.{label}.first_order.median",
        "image_features.per_label.{label}.first_order.std",
    }, mode9_paths

    for mode in range(1, 9):
        assert paths_by_mode.get(mode), mode


# =========================================================================== #
# AC13: the classification moves the attribution columns and nothing else
# =========================================================================== #


def test_ac13_classification_moves_attribution_columns_and_nothing_else(
    monkeypatch, shipped_catalogue
):
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import ConsumedPath, _RULES

    cat0 = shipped_catalogue

    reach_by_rule: dict = {}
    for entry in cat0.entries:
        for rule_id in entry.consuming_rules:
            reach_by_rule.setdefault(rule_id, set()).add(entry.path)

    patched = 0
    for rule_id, rule in _RULES.items():
        decl = rule.mode_declaration
        if decl is None:
            continue
        reach = sorted(reach_by_rule.get(rule_id, ()))
        if not reach:
            continue
        all_signal = tuple(ConsumedPath(path=p, role="signal", reason="") for p in reach)
        replacement = dataclasses.replace(decl, consumed_paths=all_signal)
        monkeypatch.setattr(rule, "mode_declaration", replacement)
        patched += 1
    assert patched > 0, "adversarial precondition: expected >=1 patched declaration"

    cat1 = catalogue.build_catalogue(strict=True)

    assert len(cat0.groups) == len(cat1.groups)
    for g0, g1 in zip(cat0.groups, cat1.groups):
        assert g0.title == g1.title
        assert g0.stage_label == g1.stage_label
        assert g0.module == g1.module
        assert g0.intro == g1.intro
    assert cat0.note == cat1.note

    d0 = catalogue.catalogue_to_dict(cat0)
    d1 = catalogue.catalogue_to_dict(cat1)
    assert d0["observed_summary"] == d1["observed_summary"]

    assert [e.path for e in cat0.entries] == [e.path for e in cat1.entries]

    attribution_fields = {"failure_modes", "mode_evidence", "mode_roles"}
    field_names = [
        f.name for f in dataclasses.fields(catalogue.CatalogueEntry) if f.name not in attribution_fields
    ]
    assert field_names, "expected >=1 non-attribution field to compare"

    any_diff = False
    for e0, e1 in zip(cat0.entries, cat1.entries):
        for name in field_names:
            assert getattr(e0, name) == getattr(e1, name), (e0.path, name)
        if (e0.failure_modes, e0.mode_evidence, e0.mode_roles) != (
            e1.failure_modes,
            e1.mode_evidence,
            e1.mode_roles,
        ):
            any_diff = True
    assert any_diff, "expected at least one entry's attribution columns to differ"


# =========================================================================== #
# AC14: both artifacts stay byte-reproducible and match their committed copies
# =========================================================================== #


def test_ac14_artifacts_byte_identical_run_to_run_and_match_committed(tmp_path):
    import segfacet.catalogue as catalogue
    from segfacet.synth.golden import assert_matches_committed_artifact

    json_a, md_a = tmp_path / "a.json", tmp_path / "a.md"
    json_b, md_b = tmp_path / "b.json", tmp_path / "b.md"
    catalogue.main(["--json", str(json_a), "--md", str(md_a)])
    catalogue.main(["--json", str(json_b), "--md", str(md_b)])

    fresh_json_bytes = json_a.read_bytes()
    fresh_md_bytes = md_a.read_bytes()
    assert fresh_json_bytes, "regenerated JSON must not be empty"
    assert fresh_md_bytes, "regenerated Markdown must not be empty"
    assert fresh_json_bytes == json_b.read_bytes()
    assert fresh_md_bytes == md_b.read_bytes()

    assert_matches_committed_artifact(json_a, _COMMITTED_CATALOGUE_JSON)

    committed_md_bytes = _COMMITTED_CATALOGUE_MD.read_bytes()
    assert committed_md_bytes, "expected a non-empty committed catalogue markdown"
    assert fresh_md_bytes == committed_md_bytes


# =========================================================================== #
# AC15: the schema version moves with the shape, and its one consumer follows
# =========================================================================== #


def test_ac15_schema_version_and_status_report_loader():
    import segfacet.catalogue as catalogue

    assert catalogue.SCHEMA_VERSION == "1.2"

    committed = json.loads(_COMMITTED_CATALOGUE_JSON.read_text(encoding="utf-8"))
    assert committed.get("schema_version") == "1.2"

    asr = _status_report_module()
    groups = asr.load_feature_catalog(_COMMITTED_CATALOGUE_JSON)
    assert isinstance(groups, tuple)
    assert groups, "expected a non-empty tuple of FeatureGroupSpec"
    for group in groups:
        assert isinstance(group, asr.FeatureGroupSpec)


# =========================================================================== #
# AC16: the seam stays metadata -- proved where the rules fire
# =========================================================================== #


_AC16_CASES = (
    ("mode6_crop_at_border", "geo", ("border",)),
    ("mode1_displace", "geo", ("mislabel",)),
    ("mode2_fragment", "geo", ("fragmentation",)),
    ("mode5_remove_level", "geo", ("coverage",)),
    ("mode7_sequence_break", "geo", ("sequence",)),
    ("mode8_force_overlap", "overlap", ("overlap",)),
    ("clean_hu", "intensity", ("bounds", "reference_delta", "intensity_reference_delta")),
    ("implausible_metal", "intensity", ("intensity",)),
)


def _overlap_reconstructed_record(case, config):
    """Rebuild the mode-8 reconstructed ``{"overlaps": [...]}`` record, the
    same technique ``synth.regression._recon_overlap_mask_stack`` uses, so it
    can be fed to ``run_rules`` directly (that helper evaluates
    ``OverlapRule`` alone, not the full runner)."""
    import numpy as np

    from segfacet.features.overlap import detect_overlaps
    from segfacet.feature_report import overlap_to_dict
    from segfacet.synth.clean_gt import build_clean_spine
    from segfacet.synth.regression import loaded_seg_image

    seg_img = loaded_seg_image(case)
    target = case["perturbation_params"]["target_label"]
    neighbour = case["perturbation_params"]["neighbour_label"]
    clean = build_clean_spine(**case["base"])
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    data = np.asanyarray(seg_img.dataobj)
    stack = np.stack([data == target, clean_data == neighbour])
    pairs = detect_overlaps(stack, np.array([target, neighbour]))
    return {"overlaps": [overlap_to_dict(pair) for pair in pairs]}


def _ac16_findings(case_key, kind, geo_by_id, intensity_by_id, config, reference):
    from segfacet.heuristics.runner import run_rules
    from segfacet.synth.regression import intensity_pipeline_findings, pipeline_findings

    if kind == "geo":
        return list(pipeline_findings(geo_by_id[case_key], config))
    if kind == "intensity":
        return list(
            intensity_pipeline_findings(intensity_by_id[case_key], config, reference=reference)
        )
    if kind == "overlap":
        record = _overlap_reconstructed_record(geo_by_id[case_key], config)
        return list(run_rules(record, config))
    raise AssertionError(kind)  # pragma: no cover -- closed vocabulary above


def test_ac16_seam_stays_metadata_where_rules_fire(monkeypatch):
    from segfacet.config import bundled_default_config
    from segfacet.heuristics.rule import RuleModeDeclaration, _RULES, iter_rules
    from segfacet.reference.artifact import bundled_default_reference
    from segfacet.synth.corpus import load_manifest

    geo_by_id = {c["case_id"]: c for c in load_manifest()["cases"]}
    intensity_manifest = json.loads(_INTENSITY_MANIFEST_PATH.read_text(encoding="utf-8"))
    intensity_by_id = {c["case_id"]: c for c in intensity_manifest["cases"]}
    reference = bundled_default_reference()
    config = bundled_default_config()

    def _tupled(findings):
        return tuple((f.rule_id, f.severity.label, tuple(f.labels), f.reason) for f in findings)

    baseline = {}
    for case_key, kind, expected_rule_ids in _AC16_CASES:
        findings = _ac16_findings(case_key, kind, geo_by_id, intensity_by_id, config, reference)
        tupled = _tupled(findings)
        assert tupled, (case_key, "expected >=1 finding to drive the invariance check")
        fired = {rid for rid, _sev, _labels, _reason in tupled}
        for rule_id in expected_rule_ids:
            assert rule_id in fired, (case_key, rule_id, fired)
        baseline[case_key] = tupled

    covered_rule_ids = {rid for _ck, _kind, rids in _AC16_CASES for rid in rids}
    all_rule_ids = {r.rule_id for r in iter_rules()}
    assert covered_rule_ids == all_rule_ids, (covered_rule_ids, all_rule_ids)

    for rule_id, rule in _RULES.items():
        decl = rule.mode_declaration
        if decl is None:
            continue
        replacement = RuleModeDeclaration(
            mode_less_reason=f"AC16 adversarial replacement for {rule_id!r} -- must not affect evaluate()"
        )
        monkeypatch.setattr(rule, "mode_declaration", replacement)

    for case_key, kind, _expected in _AC16_CASES:
        findings = _ac16_findings(case_key, kind, geo_by_id, intensity_by_id, config, reference)
        after = _tupled(findings)
        assert after == baseline[case_key], (case_key, baseline[case_key], after)


# =========================================================================== #
# AC17: no rule behaviour changed
# =========================================================================== #


_EXPECTED_THRESHOLD_CONSTANTS = {
    "border": {},
    "bounds": {
        "DEFAULT_SOURCE": "reference",
        "DEFAULT_REFERENCE_LOWER_PCT": 1,
        "DEFAULT_REFERENCE_UPPER_PCT": 99,
        "DEFAULT_REFERENCE_STRATUM": "all",
        "DEFAULT_BOUNDS": {
            "cervical": {
                "min_volume_mm3": 3000.0,
                "max_volume_mm3": 35000.0,
                "min_extent_x_mm": 10.0,
                "max_extent_x_mm": 80.0,
                "min_extent_y_mm": 10.0,
                "max_extent_y_mm": 80.0,
                "min_extent_z_mm": 5.0,
                "max_extent_z_mm": 60.0,
            },
            "thoracic": {
                "min_volume_mm3": 5000.0,
                "max_volume_mm3": 70000.0,
                "min_extent_x_mm": 15.0,
                "max_extent_x_mm": 100.0,
                "min_extent_y_mm": 15.0,
                "max_extent_y_mm": 100.0,
                "min_extent_z_mm": 8.0,
                "max_extent_z_mm": 80.0,
            },
            "lumbar": {
                "min_volume_mm3": 8000.0,
                "max_volume_mm3": 120000.0,
                "min_extent_x_mm": 20.0,
                "max_extent_x_mm": 120.0,
                "min_extent_y_mm": 20.0,
                "max_extent_y_mm": 120.0,
                "min_extent_z_mm": 15.0,
                "max_extent_z_mm": 100.0,
            },
        },
    },
    "coverage": {"DEFAULT_BORDER_AWARE": True},
    "fragmentation": {
        "DEFAULT_FRAGMENTATION_INDEX_THRESHOLD": 0.75,
        "DEFAULT_ISLAND_MIN_VOXELS": 50,
        "DEFAULT_SOURCE": "reference",
        "DEFAULT_REFERENCE_LOWER_PCT": 1,
        "DEFAULT_REFERENCE_UPPER_PCT": 99,
        "DEFAULT_REFERENCE_STRATUM": "all",
    },
    "intensity": {
        "DEFAULT_MIN_PLAUSIBLE_HU": 100.0,
        "DEFAULT_MAX_PLAUSIBLE_HU": 2000.0,
        "DEFAULT_MAX_DEGENERATE_STD": 1.0,
    },
    "intensity_reference_delta": {
        "DEFAULT_MAX_ROBUST_Z": 3.5,
        "DEFAULT_MAX_DISTRIBUTION_DISTANCE": 3.0,
    },
    "mislabel": {"_DEFAULT_MAX_OFFSET_MM": 13.0},
    "overlap": {"_DEFAULT_MIN_OVERLAP_VOXELS": 1},
    "reference_delta": {
        "DEFAULT_MAX_ROBUST_Z": 3.5,
        "DEFAULT_MAX_DISTRIBUTION_DISTANCE": 3.0,
    },
    "sequence": {},
}

_RULE_MODULE_NAMES = tuple(sorted(_EXPECTED_THRESHOLD_CONSTANTS))


@pytest.mark.parametrize("module_name", _RULE_MODULE_NAMES)
def test_ac17_threshold_constants_hold_pre_item_values(module_name):
    import importlib

    module = importlib.import_module(f"segfacet.heuristics.{module_name}")
    for name, expected in _EXPECTED_THRESHOLD_CONSTANTS[module_name].items():
        assert getattr(module, name) == expected, (module_name, name)


def test_ac17_no_rule_evaluate_body_references_declaration_symbols():
    banned = {"mode_declaration", "consumed_paths", "ConsumedPath"}
    checked = 0
    for module_name in _RULE_MODULE_NAMES:
        path = _REPO_ROOT / "src" / "segfacet" / "heuristics" / f"{module_name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "evaluate":
                names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
                offenders = (names | attrs) & banned
                assert not offenders, (module_name, offenders)
                checked += 1
    assert checked == 10


# =========================================================================== #
# AC18: the traceability matrix is untouched
# =========================================================================== #


def test_ac18_traceability_untouched_and_paths_derived_from_consuming_rules(
    tmp_path, shipped_catalogue
):
    import segfacet.traceability as traceability

    json_dest = tmp_path / "traceability_matrix.generated.json"
    md_dest = tmp_path / "traceability_matrix.generated.md"
    traceability.main(["--json", str(json_dest), "--md", str(md_dest)])

    fresh_json_bytes = json_dest.read_bytes()
    assert fresh_json_bytes, "expected a non-empty traceability JSON"
    fresh_payload = json.loads(fresh_json_bytes.decode("utf-8"))
    committed_bytes = _COMMITTED_TRACEABILITY_JSON.read_bytes()
    assert committed_bytes, "expected a non-empty committed traceability JSON"
    committed_payload = json.loads(committed_bytes.decode("utf-8"))
    assert fresh_payload == committed_payload

    fresh_md_bytes = md_dest.read_bytes()
    assert fresh_md_bytes, "expected a non-empty traceability markdown"
    committed_md_bytes = _COMMITTED_TRACEABILITY_MD.read_bytes()
    assert committed_md_bytes, "expected a non-empty committed traceability markdown"
    assert fresh_md_bytes.decode("utf-8") == committed_md_bytes.decode("utf-8")

    matrix = traceability.build_matrix()
    cat = shipped_catalogue
    checked = 0
    for rr in matrix.rules:
        expected_paths = tuple(sorted(e.path for e in cat.entries if rr.rule_id in e.consuming_rules))
        assert rr.feature_paths == expected_paths, rr.rule_id
        checked += 1
    assert checked == 10


# =========================================================================== #
# AC19: the realised path universe is unchanged and item 104 still passes
# =========================================================================== #


def test_ac19_realised_universe_unchanged_and_item104_reports_no_drift(shipped_catalogue):
    cat = shipped_catalogue
    assert len(cat.entries) == 138

    committed = json.loads(_COMMITTED_CATALOGUE_JSON.read_text(encoding="utf-8"))
    committed_paths = {e["path"] for group in committed["groups"] for e in group["entries"]}
    assert committed_paths, "expected a non-empty committed path set"
    fresh_paths = {e.path for e in cat.entries}
    assert fresh_paths == committed_paths

    t104 = _test104_module()
    realised = t104.covered_paths()
    documented = t104.documented_paths()
    assert realised, "expected a non-empty realised path set"
    assert documented, "expected a non-empty documented path set"
    assert realised - documented == set(), "direction1: undocumented realised path"
    assert documented - realised == set(), "direction2: no-longer-produced documented path"

    committed_doc = t104.load_committed_catalogue()
    entries = t104.iter_committed_entries(committed_doc)
    committed_all_paths = frozenset(e["path"] for e in entries)
    committed_record_paths = frozenset(e["path"] for e in entries if e.get("origin") == "record")
    assert committed_all_paths, "expected a non-empty committed artifact path set"
    assert realised - committed_all_paths == set(), "direction3: stale artifact path"
    assert committed_record_paths - realised == set(), "direction4: orphaned record-tier path"


# =========================================================================== #
# AC20: the two existing conformance checkers stay clean
# =========================================================================== #


def test_ac20_both_conformance_checkers_stay_clean():
    import segfacet.catalogue as catalogue
    import segfacet.failure_modes as fm

    assert catalogue.rule_declaration_conflicts() == ()
    assert fm.specification_conflicts() == ()


# =========================================================================== #
# AC21: the loop's own lint is unmoved
# =========================================================================== #

_BRANCH_STATE_WARNING_PREFIXES = ("stale claim branch", "unrecognised branch")

_BASELINE_WARNING_CLASSES = (
    "assumptions-block",
    "awaiting-a-decision",
    "branch-state",
    "retracted-criterion",
)


def _classify_warning(message: str) -> str:
    import re

    if message.startswith(_BRANCH_STATE_WARNING_PREFIXES):
        return "branch-state"
    if re.search(r"criterion \d+ was retracted on \d{4}-\d{2}-\d{2}", message):
        return "retracted-criterion"
    if "assumptions" in message.lower():
        return "assumptions-block"
    if "awaiting a decision" in message.lower():
        return "awaiting-a-decision"
    return "unclassified"


_WRITTEN_PATHS = (
    "src/segfacet/heuristics/rule.py",
    "src/segfacet/heuristics/__init__.py",
    "src/segfacet/heuristics/border.py",
    "src/segfacet/heuristics/bounds.py",
    "src/segfacet/heuristics/coverage.py",
    "src/segfacet/heuristics/fragmentation.py",
    "src/segfacet/heuristics/intensity.py",
    "src/segfacet/heuristics/intensity_reference_delta.py",
    "src/segfacet/heuristics/mislabel.py",
    "src/segfacet/heuristics/overlap.py",
    "src/segfacet/heuristics/reference_delta.py",
    "src/segfacet/heuristics/sequence.py",
    "src/segfacet/catalogue.py",
    "scripts/aide_status_report.py",
    "docs/aide/feature_catalogue.generated.json",
    "docs/aide/feature_catalogue.generated.md",
)


def test_ac21_aide_check_reports_no_error_and_no_new_warning_class():
    aide = _aide_module()
    errors, warnings = aide.run_checks(_REPO_ROOT, aide.load_config(_REPO_ROOT))
    assert errors == [], errors
    assert warnings, "run_checks returned no warnings at all -- expected the baseline"

    classes = {_classify_warning(w) for w in warnings}
    assert classes <= set(_BASELINE_WARNING_CLASSES), (
        f"aide check reports a warning class outside the recorded baseline: "
        f"{classes - set(_BASELINE_WARNING_CLASSES)}"
    )

    for warning in warnings:
        assert "insights.md" not in warning, warning
        assert ".gitattributes" not in warning, warning
        for written_path in _WRITTEN_PATHS:
            assert written_path not in warning, (written_path, warning)


def test_ac21_aide_check_exits_zero():
    result = run_utf8([sys.executable, str(_AIDE_SCRIPT), "check"], cwd=_REPO_ROOT, timeout=180)
    assert result.returncode == 0, result.stderr


def test_adv_unclassified_warning_would_be_caught():
    """The classifier must be able to detect a new class -- otherwise the
    AC21 check above passes on anything."""
    assert _classify_warning("a brand new kind of warning nobody has seen") == "unclassified"


# =========================================================================== #
# Adversarial / edge cases beyond the AC3 malformed-shape table
# =========================================================================== #


def test_adv_build_catalogue_twice_equal_attribution_fields():
    import segfacet.catalogue as catalogue

    cat1 = catalogue.build_catalogue(strict=True)
    cat2 = catalogue.build_catalogue(strict=True)
    assert len(cat1.entries) == len(cat2.entries)
    checked = 0
    for e1, e2 in zip(cat1.entries, cat2.entries):
        assert e1.path == e2.path
        assert e1.mode_roles == e2.mode_roles
        assert e1.mode_evidence == e2.mode_evidence
        assert e1.failure_modes == e2.failure_modes
        checked += 1
    assert checked == len(cat1.entries)


def test_adv_consumed_paths_field_is_immutable_and_build_catalogue_does_not_mutate_declarations():
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import _RULES

    decl = _RULES["border"].mode_declaration
    with pytest.raises(dataclasses.FrozenInstanceError):
        decl.consumed_paths = ()  # type: ignore[misc]

    before = {rule_id: rule.mode_declaration for rule_id, rule in _RULES.items()}
    catalogue.build_catalogue(strict=True)
    after = {rule_id: rule.mode_declaration for rule_id, rule in _RULES.items()}
    assert before == after
    for rule_id in before:
        assert before[rule_id] is after[rule_id], rule_id


def test_adv_entry_with_no_consuming_rules_has_no_roles_or_rule_sourced_tags():
    import segfacet.catalogue as catalogue

    cat = catalogue.build_catalogue(strict=True)
    candidates = [e for e in cat.entries if not e.consuming_rules]
    assert candidates, "expected >=1 entry with no consuming_rules"
    for entry in candidates:
        assert entry.mode_roles == (), entry.path
        for tag in ("rule_declaration", "rule_mode_less", "rule_bookkeeping", "rule_not_read"):
            assert tag not in entry.mode_evidence, (entry.path, tag)


def test_adv_stub_rule_modes_set_consumed_paths_empty_reported_and_contributes_nothing(
    isolated_registry,
):
    import segfacet.catalogue as catalogue
    from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule

    class _StubRule(Rule):
        rule_id = "__item148_stub_modes_no_consumed_paths__"
        mode_declaration = RuleModeDeclaration(modes=(1,), evidence=("adversarial",))

        def evaluate(self, record, config):
            return []

    register_rule(_StubRule)

    conflicts = catalogue.path_classification_conflicts()
    assert any(_StubRule.rule_id in msg for msg in conflicts), conflicts

    cat = catalogue.build_catalogue(strict=True)
    for entry in cat.entries:
        assert _StubRule.rule_id not in dict(entry.mode_roles), entry.path
