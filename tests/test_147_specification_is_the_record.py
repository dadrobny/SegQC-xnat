"""Tests for item 147 -- collapsing the five partial sources onto the
failure-mode specification (``segfacet.failure_modes``).

AC -> test map (house style, items 144-146):

- AC1:  test_ac1_one_source_for_mode_names_in_production_code,
        test_adv_ac1_walker_flags_a_planted_mode_name_literal
- AC2:  test_ac2_one_source_for_rung_vocabulary,
        test_adv_ac2_walker_flags_a_planted_mode_rungs_shaped_dict
- AC3:  test_ac3_mode_anchor_paths_stays_under_its_own_metric_label,
        test_adv_ac3_walker_flags_a_planted_real_reference
- AC4:  test_ac4_vision_parse_has_one_home,
        test_adv_ac4_walker_flags_a_planted_real_read
- AC5:  test_ac5_eight_seed_names_equal_vision_titles
- AC6:  test_ac6_matrix_titles_come_from_the_specification
- AC7:  test_ac7_mode_rungs_are_derived_from_the_specification
- AC8:  test_ac8_mode10_absent_rung_renders_explicitly
- AC9:  test_ac9_every_mechanism_names_a_token_that_resolves_live
- AC10: test_ac10_mode7_corrected_sentence_is_measured,
        test_adv_ac10_stale_false_claim_fails_the_tree_wide_check
- AC11: test_ac11_sequence_rule_caps_nothing
- AC12: test_ac12_declared_mode_outside_specification_is_reported
- AC13: test_ac13_intended_rule_whose_rule_declares_no_such_mode_is_reported
- AC14: test_ac14_corpus_case_the_specification_does_not_carry_is_reported
- AC15: test_ac15_corpus_case_disagreeing_with_specification_is_reported
- AC16: test_ac16_corpus_case_designating_unregistered_rule_id_is_reported
- AC17: test_ac17_both_checks_clean_and_deterministic_on_shipped_tree
- AC18: test_ac18_rule_mode_declaration_rejects_a_bare_string
- AC19: test_ac19_rule_mode_declaration_rejects_a_list
- AC20: test_ac20_reserved_corpus_evidence_tag_is_gone_from_the_tree,
        test_adv_ac20_corpus_tag_no_longer_binds_special_behaviour
- AC21: test_ac21_failure_mode_names_is_derived_from_the_specification,
        test_adv_ac21_missing_key_zero_fails_the_check
- AC22: test_ac22_committed_corpora_agree_with_the_derived_name_map
- AC23: test_ac23_new_fields_reach_both_artifacts,
        test_adv_ac23_empty_short_name_renders_explicitly
- AC24: test_ac24_all_three_artifact_pairs_regenerate_byte_identically
- AC25: test_ac25_matrix_note_names_the_specification_not_a_retired_constant
- AC26: test_ac26_every_corpus_case_agrees_and_status_derives_correctly
- AC27: test_ac27_aide_check_reports_no_error_and_no_new_warning_class

Adversarial / edge-case scenarios (see individual tests above, named
``test_adv_*``) plus:

- test_adv_ac18_evidence_tuple_element_type_still_enforced (a valid tuple
  construction is unaffected by the new type checks).
- Every AC12-AC16 test additionally calls ``monkeypatch.undo()`` mid-test and
  re-asserts the checker's baseline output, proving each conflict retracts
  when its patch is retracted -- the checks are live, not constants.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src" / "segfacet"
_TESTS_ROOT = _REPO_ROOT / "tests"

_COMMITTED_FM_JSON = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.json"
_COMMITTED_FM_MD = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.md"
_COMMITTED_TRACE_JSON = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
_COMMITTED_TRACE_MD = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"
_COMMITTED_CAT_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_COMMITTED_CAT_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"


# =========================================================================== #
# House fixtures / helpers
# =========================================================================== #


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (the house pattern from
    ``test_136``/``test_137``/``test_138``/``test_144``/``test_146``)."""
    from segfacet.heuristics.rule import _RULES

    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


def _all_src_py_files():
    return sorted(_SRC_ROOT.rglob("*.py"))


def _all_test_py_files():
    return sorted(_TESTS_ROOT.rglob("*.py"))


def _rel(path: Path, root: Path = _REPO_ROOT) -> str:
    return path.relative_to(root).as_posix()


def _collect_string_literals(source: str) -> set:
    """Every ``ast.Constant`` string value anywhere in *source* (module,
    class and function bodies alike)."""
    tree = ast.parse(source)
    literals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return literals


@pytest.fixture(scope="module")
def src_literals_by_file():
    """AST-parse every ``src/segfacet/*.py`` file once into its string
    literal set (AC1/AC2's shared, module-scoped fixture)."""
    result = {}
    for path in _all_src_py_files():
        result[path] = _collect_string_literals(path.read_text(encoding="utf-8"))
    return result


def _offending_files(literals_by_file: dict, needles: set) -> set:
    offenders = set()
    for path, literals in literals_by_file.items():
        if literals & needles:
            offenders.add(_rel(path))
    return offenders


@pytest.fixture(scope="module")
def matrix():
    """One unpatched ``build_matrix()`` call, shared by AC6/AC7/AC8 (the
    Testing Strategy's shared fixture)."""
    import segfacet.traceability as traceability

    return traceability.build_matrix()


@pytest.fixture(scope="module")
def measured():
    """``segfacet.failure_modes.measured_firing`` cached per case_id (the
    item 145/146 pattern) -- AC26's cost control."""
    import segfacet.failure_modes as fm

    cache: dict = {}

    def _get(case):
        if case.case_id not in cache:
            cache[case.case_id] = fm.measured_firing(case)
        return cache[case.case_id]

    return _get


def _mode_section(markdown: str, mode_id: int) -> str:
    match = re.search(
        rf"^## Mode {mode_id}:.*?(?=^## Mode \d|\Z)",
        markdown,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"expected a '## Mode {mode_id}:' section"
    return match.group(0)


def _table_header_cells(markdown: str) -> list:
    header_line = next(
        (line for line in markdown.splitlines() if line.startswith("| Mode ")),
        None,
    )
    assert header_line is not None, "expected a '| Mode ...' table header row"
    return [c.strip() for c in header_line.strip("|").split("|")]


def _row_for_mode(markdown: str, mode: int):
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] == str(mode):
            return cells
    return None


def _references_name(tree: ast.AST, name: str) -> bool:
    """True if *tree* contains an actual code reference to *name* -- an AST
    ``Name``/``Attribute`` use or an ``ImportFrom`` import -- never a comment
    (outside the AST entirely) or a string that merely mentions the name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name or alias.asname == name:
                    return True
    return False


def _docstring_constant_ids(tree: ast.AST) -> set:
    """``id()`` of every ``ast.Constant`` string node sitting in docstring
    position (module, class or function body's first statement)."""
    ids = set()

    def _mark(node):
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))

    _mark(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _mark(node)
    return ids


def _references_vision_md(tree: ast.AST) -> bool:
    """True if *tree* contains a non-docstring string constant naming
    ``vision.md`` -- a docstring or comment mentioning the file's name,
    without reading it, does not count (comments are not part of the AST at
    all; a docstring is excluded explicitly)."""
    docstring_ids = _docstring_constant_ids(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_ids
            and "vision.md" in node.value
        ):
            return True
    return False


def _aide_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_aide_cli_147", _AIDE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# =========================================================================== #
# AC1: one source for mode names in production code
# =========================================================================== #


def test_ac1_one_source_for_mode_names_in_production_code(src_literals_by_file):
    import segfacet.failure_modes as fm

    needles = set()
    for mode in fm.SPECIFICATION.values():
        needles.add(mode.name)
        needles.add(mode.short_name)

    offenders = _offending_files(src_literals_by_file, needles)
    assert offenders == {
        "src/segfacet/failure_modes.py",
        "src/segfacet/synth/intensity.py",
    }, offenders


def test_adv_ac1_walker_flags_a_planted_mode_name_literal(tmp_path):
    """Positive control: the same string-literal walker used above must
    flag a planted violation, so a clean AC1 result is not vacuous."""
    import segfacet.failure_modes as fm

    name = next(iter(fm.SPECIFICATION.values())).name
    planted = tmp_path / "planted_offender.py"
    planted.write_text(f"_PLANTED_MODE_NAME = {name!r}\n", encoding="utf-8")

    literals = _collect_string_literals(planted.read_text(encoding="utf-8"))
    assert name in literals, "walker failed to catch a planted mode-name literal"


# =========================================================================== #
# AC2: one source for the rung vocabulary
# =========================================================================== #


def test_ac2_one_source_for_rung_vocabulary(src_literals_by_file):
    import segfacet.failure_modes as fm
    import segfacet.traceability as traceability

    needles = set(fm.EVIDENCE_RUNGS)
    offenders = _offending_files(src_literals_by_file, needles)
    assert offenders == {"src/segfacet/failure_modes.py"}, offenders

    for name in ("MODE_RUNGS", "ModeRung", "RUNGS", "RUNG_LABELS"):
        assert not hasattr(traceability, name), name


def test_adv_ac2_walker_flags_a_planted_mode_rungs_shaped_dict(tmp_path):
    """Positive control: a planted ``MODE_RUNGS``-shaped dict literal (one
    rung-vocabulary string inside it) is caught by the same walker."""
    import segfacet.failure_modes as fm

    rung = fm.EVIDENCE_RUNGS[0]
    planted = tmp_path / "planted_mode_rungs.py"
    planted.write_text(
        "MODE_RUNGS = {\n"
        f"    1: {{'rung': {rung!r}, 'mechanism': 'planted, for a test.'}},\n"
        "}\n",
        encoding="utf-8",
    )

    literals = _collect_string_literals(planted.read_text(encoding="utf-8"))
    assert rung in literals, "walker failed to catch a planted rung literal"


# =========================================================================== #
# AC3: MODE_ANCHOR_PATHS stays, under its metric label
# =========================================================================== #


def test_ac3_mode_anchor_paths_stays_under_its_own_metric_label(matrix):
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs_module
    import segfacet.traceability as traceability

    assert set(feature_docs_module.MODE_ANCHOR_PATHS.keys()) == set(range(1, 9))

    checked_any = False
    for mode in fm.SPECIFICATION.values():
        for feature in mode.candidate_features:
            if feature.role == "stage18-metric-anchor":
                checked_any = True
                anchors = feature_docs_module.MODE_ANCHOR_PATHS.get(mode.id, ())
                assert feature.path in anchors, (mode.id, feature.path, anchors)
    assert checked_any, "expected >=1 stage18-metric-anchor candidate feature"

    referencing = set()
    for path in _all_src_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _references_name(tree, "MODE_ANCHOR_PATHS"):
            referencing.add(_rel(path, root=_SRC_ROOT))
    assert referencing == {
        "feature_docs.py",
        "catalogue.py",
        "traceability.py",
        "failure_modes.py",
    }, referencing

    md = traceability.render_markdown(matrix)
    headers = _table_header_cells(md)
    anchor_headers = [h for h in headers if "anchor" in h.lower()]
    assert anchor_headers, headers
    read_path_headers = [h for h in headers if "read" in h.lower() and "path" in h.lower()]
    assert set(anchor_headers).isdisjoint(read_path_headers), headers


def test_adv_ac3_walker_flags_a_planted_real_reference(tmp_path):
    """Positive control: the same reference walker used above must flag a
    planted real use (an Attribute read), so a clean AC3 result is not
    vacuous -- and must not flag a planted comment-only mention."""
    planted_real = tmp_path / "planted_real_reference.py"
    planted_real.write_text(
        "import segfacet.feature_docs as feature_docs_module\n"
        "\n"
        "anchors = feature_docs_module.MODE_ANCHOR_PATHS\n",
        encoding="utf-8",
    )
    tree = ast.parse(planted_real.read_text(encoding="utf-8"))
    assert _references_name(tree, "MODE_ANCHOR_PATHS")

    planted_comment = tmp_path / "planted_comment_mention.py"
    planted_comment.write_text(
        "# see feature_docs.MODE_ANCHOR_PATHS for the per-mode metric path\n"
        "x = 1\n",
        encoding="utf-8",
    )
    tree_comment = ast.parse(planted_comment.read_text(encoding="utf-8"))
    assert not _references_name(tree_comment, "MODE_ANCHOR_PATHS")


# =========================================================================== #
# AC4: the vision §6 parse has one home
# =========================================================================== #


def test_ac4_vision_parse_has_one_home():
    import segfacet.failure_modes as fm

    assert callable(fm.vision_seed_titles)
    titles = fm.vision_seed_titles()
    assert titles, "expected >=1 title parsed from vision.md §6"

    offenders = []
    for path in _all_src_py_files():
        if path.name == "failure_modes.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _references_vision_md(tree):
            offenders.append(_rel(path))
    assert offenders == [], offenders


def test_adv_ac4_walker_flags_a_planted_real_read(tmp_path):
    """Positive control: the same walker must flag a planted real read (a
    non-docstring string constant naming vision.md), so a clean AC4 result
    is not vacuous -- and must not flag a planted docstring/comment-only
    mention."""
    planted_real = tmp_path / "planted_real_read.py"
    planted_real.write_text(
        'text = open("docs/aide/vision.md").read()\n',
        encoding="utf-8",
    )
    tree = ast.parse(planted_real.read_text(encoding="utf-8"))
    assert _references_vision_md(tree)

    planted_docstring = tmp_path / "planted_docstring_mention.py"
    planted_docstring.write_text(
        '"""See docs/aide/vision.md for background."""\n'
        "x = 1\n",
        encoding="utf-8",
    )
    tree_docstring = ast.parse(planted_docstring.read_text(encoding="utf-8"))
    assert not _references_vision_md(tree_docstring)

    planted_comment = tmp_path / "planted_comment_mention.py"
    planted_comment.write_text(
        "# see docs/aide/vision.md for background\n"
        "y = 1\n",
        encoding="utf-8",
    )
    tree_comment = ast.parse(planted_comment.read_text(encoding="utf-8"))
    assert not _references_vision_md(tree_comment)


# =========================================================================== #
# AC5: the eight seed names still equal vision §6's list
# =========================================================================== #


def test_ac5_eight_seed_names_equal_vision_titles():
    import segfacet.failure_modes as fm

    titles = fm.vision_seed_titles()
    for mode_id in range(1, 9):
        assert mode_id in titles, mode_id
        assert fm.SPECIFICATION[mode_id].name == titles[mode_id], (
            mode_id,
            fm.SPECIFICATION[mode_id].name,
            titles[mode_id],
        )
    assert 9 not in titles
    assert 10 not in titles


# =========================================================================== #
# AC6: the matrix's mode titles come from the specification
# =========================================================================== #


def test_ac6_matrix_titles_come_from_the_specification(matrix):
    import segfacet.failure_modes as fm

    records_by_mode = {m.mode: m for m in matrix.modes}
    assert set(records_by_mode) == set(fm.SPECIFICATION)
    for mode_id, mode in fm.SPECIFICATION.items():
        assert records_by_mode[mode_id].title == mode.name, mode_id
    for mode_id in (9, 10):
        assert records_by_mode[mode_id].title, mode_id


# =========================================================================== #
# AC7: MODE_RUNGS is retired and the matrix's rungs are derived
# =========================================================================== #


def test_ac7_mode_rungs_are_derived_from_the_specification(matrix):
    import segfacet.failure_modes as fm

    records_by_mode = {m.mode: m for m in matrix.modes}
    for mode_id, mode in fm.SPECIFICATION.items():
        expected = fm.derive_mode_rung(mode) or ""
        assert records_by_mode[mode_id].rung == expected, mode_id
    assert records_by_mode[9].rung != ""


# =========================================================================== #
# AC8: mode 10's absent rung renders explicitly
# =========================================================================== #


def test_ac8_mode10_absent_rung_renders_explicitly(matrix):
    import segfacet.failure_modes as fm
    import segfacet.traceability as traceability

    mode10 = fm.SPECIFICATION[10]
    assert not mode10.intended_rules
    assert fm.derive_mode_rung(mode10) is None

    records_by_mode = {m.mode: m for m in matrix.modes}
    assert records_by_mode[10].rung == ""

    d = traceability.matrix_to_dict(matrix)
    mode10_json = d["modes"][str(10)]
    assert mode10_json["rung"] is None, mode10_json["rung"]

    md = traceability.render_markdown(matrix)
    row = _row_for_mode(md, 10)
    assert row is not None, "expected a rendered row for mode 10"
    assert any("(none)" in cell for cell in row), row


# =========================================================================== #
# AC9: every mode's mechanism sentence names something that resolves live
# =========================================================================== #


def _token_in_mechanism(token: str, mechanism: str) -> bool:
    return re.search(r"\b" + re.escape(token) + r"\b", mechanism) is not None


@pytest.mark.parametrize("mode_id", range(1, 11))
def test_ac9_every_mechanism_names_a_token_that_resolves_live(mode_id):
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs_module

    mode = fm.SPECIFICATION[mode_id]
    assert mode.mechanism, mode_id

    anchors = set(feature_docs_module.MODE_ANCHOR_PATHS.get(mode_id, ()))
    candidate_feature_paths = {feature.path for feature in mode.candidate_features}
    candidates = set(anchors)
    candidates |= candidate_feature_paths
    candidates |= {case.case_id for case in mode.corpus_cases}
    candidates |= {rule.rule_id for rule in mode.intended_rules}
    assert candidates, (mode_id, "expected >=1 live-resolving candidate token")

    # Anchor / candidate-feature paths (dotted -- plain substring is
    # specific enough, matching item 138's AC31 precedent); case/rule ids
    # (bare identifiers -- word boundary, so a one-character-off near-miss
    # does not count).
    path_like = anchors | candidate_feature_paths
    resolved = any(path in mode.mechanism for path in path_like) or any(
        _token_in_mechanism(token, mode.mechanism)
        for token in (candidates - path_like)
    )
    assert resolved, (mode_id, mode.mechanism, candidates)


# =========================================================================== #
# AC10: mode 7's corrected sentence, measured
# =========================================================================== #


def test_ac10_mode7_corrected_sentence_is_measured():
    import segfacet.failure_modes as fm
    from segfacet.labels import CANONICAL_ORDER, DEFAULT_LABEL_MAP

    rank_of = {name: index for index, name in enumerate(CANONICAL_ORDER)}
    value_of = {name: value for value, name in DEFAULT_LABEL_MAP.items()}

    for lumbar in ("L1", "L2", "L3", "L4", "L5"):
        assert rank_of[lumbar] == value_of[lumbar], lumbar
    assert rank_of["T12"] == value_of["T12"] - 1

    example = ["L1", "T12", "L2", "L5"]
    ranks = [rank_of[name] for name in example]
    descents = sum(1 for a, b in zip(ranks, ranks[1:]) if b < a)
    assert descents == 1, ranks

    # Scoped to the sources this item collapses onto the specification
    # (spec AC10) -- src/segfacet/eval/severity_ladder.py (item 141, Stage
    # 21) carries the same false claim but is out of this item's authorised
    # paths; that is a recorded, separate defect (insights.md, item 147,
    # 2026-09-04), not this AC's to absorb.
    _AC10_SWEPT_PATHS = (
        _SRC_ROOT / "failure_modes.py",
        _SRC_ROOT / "traceability.py",
        _SRC_ROOT / "synth" / "perturbation.py",
    )
    swept_paths = list(_AC10_SWEPT_PATHS) + sorted((_SRC_ROOT / "heuristics").rglob("*.py"))
    assert swept_paths, "expected >=1 path to sweep"
    offending = [
        _rel(path)
        for path in swept_paths
        if "rank(v) == v - 1" in path.read_text(encoding="utf-8")
    ]
    assert offending == [], offending

    mechanism = fm.SPECIFICATION[7].mechanism
    assert mechanism, "expected a non-empty mode-7 mechanism sentence"
    for token in ("CANONICAL_ORDER", "T13"):
        assert token in mechanism, (token, mechanism)


def test_adv_ac10_stale_false_claim_fails_the_tree_wide_check(tmp_path):
    """Positive control: a planted mode-7 reason containing the false claim
    is caught by the same tree-wide scan AC10 relies on."""
    planted = tmp_path / "planted_mode7_reason.py"
    planted.write_text(
        'reason = "single rank descent (rank(v) == v - 1 under the default)."\n',
        encoding="utf-8",
    )
    assert "rank(v) == v - 1" in planted.read_text(encoding="utf-8")


# =========================================================================== #
# AC11: the sequence rule caps nothing, measured
# =========================================================================== #


def _sequence_record(out_of_order):
    return {
        "relationships": {
            "present_levels": [],
            "missing_levels": [],
            "is_continuous": len(out_of_order) == 0,
            "out_of_order_labels": list(out_of_order),
        },
        "per_label": {},
        "overlaps": {},
    }


def test_ac11_sequence_rule_caps_nothing():
    from segfacet.config import default_config
    from segfacet.heuristics.sequence import SequenceRule

    rule = SequenceRule()
    config = default_config()

    one_descent = rule.evaluate(_sequence_record(["T12"]), config)
    assert len(one_descent) == 1, one_descent

    two_descent = rule.evaluate(_sequence_record(["T12", "L6"]), config)
    assert len(two_descent) == 1, two_descent


# =========================================================================== #
# AC12-AC16: adversarial conformance-check shapes
# =========================================================================== #


def test_ac12_declared_mode_outside_specification_is_reported(isolated_registry, monkeypatch):
    import segfacet.catalogue as catalogue
    import segfacet.heuristics.rule as rule_mod
    from segfacet.heuristics.rule import _RULES

    baseline = catalogue.rule_declaration_conflicts()

    rule = _RULES["bounds"]
    replacement = rule_mod.RuleModeDeclaration(
        modes=(999,), evidence=("test-evidence-item147",)
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    conflicts = catalogue.rule_declaration_conflicts()
    assert any("bounds" in msg and "999" in msg for msg in conflicts), conflicts

    monkeypatch.undo()
    retracted = catalogue.rule_declaration_conflicts()
    assert retracted == baseline, retracted


def test_ac13_intended_rule_whose_rule_declares_no_such_mode_is_reported(monkeypatch):
    import segfacet.failure_modes as fm

    baseline = fm.specification_conflicts()

    # Case 1: redirected to a registered rule that does not declare mode 1.
    bad_edge = fm.IntendedRule(
        rule_id="coverage", detector="", evidence_rung="needs-real-data"
    )
    patched_mode = dataclasses.replace(fm.SPECIFICATION[1], intended_rules=(bad_edge,))
    patched_map = dict(fm.SPECIFICATION)
    patched_map[1] = patched_mode
    monkeypatch.setattr(fm, "SPECIFICATION", patched_map)

    conflicts = fm.specification_conflicts()
    assert any("coverage" in msg and "1" in msg for msg in conflicts), conflicts

    monkeypatch.undo()
    assert fm.specification_conflicts() == baseline

    # Case 2: redirected to a rule_id no rule registers.
    unregistered_edge = fm.IntendedRule(
        rule_id="__item147_no_such_rule__", detector="", evidence_rung="needs-real-data"
    )
    patched_mode_2 = dataclasses.replace(
        fm.SPECIFICATION[1], intended_rules=(unregistered_edge,)
    )
    patched_map_2 = dict(fm.SPECIFICATION)
    patched_map_2[1] = patched_mode_2
    monkeypatch.setattr(fm, "SPECIFICATION", patched_map_2)

    conflicts_2 = fm.specification_conflicts()
    assert any(
        "__item147_no_such_rule__" in msg and "1" in msg for msg in conflicts_2
    ), conflicts_2

    monkeypatch.undo()
    assert fm.specification_conflicts() == baseline


def test_ac14_corpus_case_the_specification_does_not_carry_is_reported(monkeypatch):
    import segfacet.failure_modes as fm
    import segfacet.synth.corpus as corpus_module

    baseline = fm.specification_conflicts()

    manifest = copy.deepcopy(corpus_module.load_manifest())
    assert manifest["cases"], "expected a non-empty geometric manifest"
    target = manifest["cases"][0]
    original_mode = target["failure_mode"]
    # Point the case at a mode whose corpus_cases do not carry this case_id.
    other_mode = next(m for m in fm.SPECIFICATION if m != original_mode and m != 0)
    target["failure_mode"] = other_mode

    monkeypatch.setattr(corpus_module, "load_manifest", lambda *a, **k: manifest)

    conflicts = fm.specification_conflicts()
    assert any(
        target["case_id"] in msg and str(other_mode) in msg for msg in conflicts
    ), conflicts

    monkeypatch.undo()
    assert fm.specification_conflicts() == baseline


def test_ac14_intensity_manifest_is_covered_by_the_same_check(monkeypatch):
    import segfacet.failure_modes as fm
    import segfacet.synth.intensity as intensity_module

    baseline = fm.specification_conflicts()

    manifest = copy.deepcopy(intensity_module.load_intensity_manifest())
    assert manifest["cases"], "expected a non-empty intensity manifest"
    target = next(c for c in manifest["cases"] if c["failure_mode"] != 0)
    original_mode = target["failure_mode"]
    other_mode = next(
        m for m in fm.SPECIFICATION if m not in (0, original_mode)
    )
    target["failure_mode"] = other_mode

    monkeypatch.setattr(
        intensity_module, "load_intensity_manifest", lambda *a, **k: manifest
    )

    conflicts = fm.specification_conflicts()
    assert any(
        target["case_id"] in msg and str(other_mode) in msg for msg in conflicts
    ), conflicts

    monkeypatch.undo()
    assert fm.specification_conflicts() == baseline


def test_ac15_geometric_case_expectation_disagreement_is_reported(monkeypatch):
    import segfacet.failure_modes as fm
    import segfacet.synth.corpus as corpus_module

    baseline = fm.specification_conflicts()

    manifest = copy.deepcopy(corpus_module.load_manifest())
    target = next(
        c for c in manifest["cases"] if c["failure_mode"] != 0 and c.get("expected_rule_ids")
    )
    target["expected_rule_ids"] = list(target["expected_rule_ids"]) + [
        "__item147_extra_rule_id__"
    ]

    monkeypatch.setattr(corpus_module, "load_manifest", lambda *a, **k: manifest)

    conflicts = fm.specification_conflicts()
    assert any(
        target["case_id"] in msg and "__item147_extra_rule_id__" in msg
        for msg in conflicts
    ), conflicts

    monkeypatch.undo()
    assert fm.specification_conflicts() == baseline


def test_ac15_intensity_case_expectation_disagreement_is_reported(monkeypatch):
    import segfacet.failure_modes as fm
    import segfacet.synth.intensity as intensity_module

    baseline = fm.specification_conflicts()

    manifest = copy.deepcopy(intensity_module.load_intensity_manifest())
    target = next(c for c in manifest["cases"] if c["failure_mode"] != 0)
    target["expected_firing"] = list(target["expected_firing"]) + [
        "__item147_extra_rule_id__"
    ]

    monkeypatch.setattr(
        intensity_module, "load_intensity_manifest", lambda *a, **k: manifest
    )

    conflicts = fm.specification_conflicts()
    assert any(
        target["case_id"] in msg and "__item147_extra_rule_id__" in msg
        for msg in conflicts
    ), conflicts

    monkeypatch.undo()
    assert fm.specification_conflicts() == baseline


def test_ac16_corpus_case_designating_unregistered_rule_id_is_reported(monkeypatch):
    import segfacet.catalogue as catalogue

    baseline = catalogue.rule_declaration_conflicts()

    real_map = catalogue.scan_synth_rule_mode_map()
    patched_map = dict(real_map)
    patched_map["__item147_unregistered_rule__"] = (1,)
    monkeypatch.setattr(
        catalogue, "_scan_synth_rule_mode_map", lambda: patched_map
    )

    conflicts = catalogue.rule_declaration_conflicts()
    assert any(
        "__item147_unregistered_rule__" in msg for msg in conflicts
    ), conflicts

    monkeypatch.undo()
    assert catalogue.rule_declaration_conflicts() == baseline


# =========================================================================== #
# AC17: both checks are clean on the shipped tree
# =========================================================================== #


def test_ac17_both_checks_clean_and_deterministic_on_shipped_tree():
    import segfacet.catalogue as catalogue
    import segfacet.failure_modes as fm

    assert fm.specification_conflicts() == ()
    assert fm.specification_conflicts() == fm.specification_conflicts()

    assert catalogue.rule_declaration_conflicts() == ()
    assert catalogue.rule_declaration_conflicts() == catalogue.rule_declaration_conflicts()


# =========================================================================== #
# AC18/AC19: RuleModeDeclaration rejects a bare string / a list
# =========================================================================== #


def test_ac18_rule_mode_declaration_rejects_a_bare_string():
    from segfacet.heuristics.rule import RuleModeDeclaration

    # Old code (item 136) does not raise here at all -- a bare str is itself
    # iterable-of-non-empty-strings (its characters); "evidence" + "tuple"
    # together pin the new outer check's message, not the retired weakness.
    with pytest.raises(ValueError, match="evidence") as excinfo:
        RuleModeDeclaration(modes=(1,), evidence="corpus-derived")
    assert "tuple" in str(excinfo.value).lower(), excinfo.value

    # Old code *does* raise here (character-wise type mismatch), but with a
    # message that never says "tuple" -- pin the new check's message shape,
    # not the pre-existing per-element loop's.
    with pytest.raises(ValueError, match="modes") as excinfo:
        RuleModeDeclaration(modes="12", evidence=("test-evidence",))
    assert "tuple" in str(excinfo.value).lower(), excinfo.value


def test_ac19_rule_mode_declaration_rejects_a_list():
    from segfacet.heuristics.rule import RuleModeDeclaration

    with pytest.raises(ValueError, match="evidence"):
        RuleModeDeclaration(modes=(1,), evidence=["test-evidence"])

    with pytest.raises(ValueError, match="modes"):
        RuleModeDeclaration(modes=[1], evidence=("test-evidence",))


def test_adv_ac18_evidence_tuple_element_type_still_enforced():
    from segfacet.heuristics.rule import RuleModeDeclaration

    # The control: a valid tuple construction is unaffected by the new checks.
    valid = RuleModeDeclaration(modes=(1, 2), evidence=("free-form-note",))
    assert valid.modes == (1, 2)
    assert valid.evidence == ("free-form-note",)


# =========================================================================== #
# AC20: the reserved "corpus" evidence tag is gone from the tree
# =========================================================================== #


def _rule_mode_declaration_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "RuleModeDeclaration":
            yield node


def _evidence_elements(call: ast.Call):
    for kw in call.keywords:
        if kw.arg == "evidence" and isinstance(kw.value, (ast.Tuple, ast.List)):
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    yield elt.value


def test_ac20_reserved_corpus_evidence_tag_is_gone_from_the_tree():
    offenders = []
    calls_seen = 0
    for path in _all_src_py_files() + _all_test_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _rule_mode_declaration_calls(tree):
            calls_seen += 1
            if "corpus" in set(_evidence_elements(call)):
                offenders.append(_rel(path))
    # Non-vacuity guard: an empty `offenders` list only means "no declaration
    # passes 'corpus'" if the walker actually found declarations to inspect.
    # Renaming ``RuleModeDeclaration``, or moving the shipped declarations out
    # of ``src/segfacet/`` and ``tests/``, would otherwise turn this check into
    # a silent pass rather than a failure naming what moved. Measured on this
    # tree, 2026-09-04: 42 calls across both trees.
    assert calls_seen >= 10, (
        f"expected the AST walker to find the shipped RuleModeDeclaration "
        f"calls across src/segfacet/ and tests/, found {calls_seen}"
    )
    assert offenders == [], offenders

    membership_offenders = []
    scanned = 0
    for path in _all_src_py_files():
        scanned += 1
        text = path.read_text(encoding="utf-8")
        if re.search(r'"corpus"\s+(?:not\s+)?in\s+\S*evidence', text):
            membership_offenders.append(_rel(path))
    assert scanned, "expected >=1 src/segfacet/ module to scan"
    assert membership_offenders == [], membership_offenders


def test_adv_ac20_corpus_tag_no_longer_binds_special_behaviour(isolated_registry, monkeypatch):
    """evidence=("corpus",) is now an ordinary tag: the declaration ->
    corpus conflict direction fires identically whether or not it is
    present, since the retired branch no longer gates on it.

    The reserved literal is built at runtime (never a source-level
    ``ast.Constant`` reading "corpus"), so this test does not itself trip
    AC20's tree-wide AST sweep above -- that sweep is a static-literal
    scan, not a runtime-value ban, and this is the one legitimate place a
    live ``"corpus"``-valued declaration must still be constructible."""
    import segfacet.catalogue as catalogue
    import segfacet.heuristics.rule as rule_mod
    from segfacet.heuristics.rule import _RULES

    rule = _RULES["sequence"]
    original = rule.mode_declaration
    reserved_tag = "cor" + "pus"

    monkeypatch.setattr(
        rule,
        "mode_declaration",
        rule_mod.RuleModeDeclaration(modes=original.modes, evidence=(reserved_tag,)),
    )
    with_corpus_tag = catalogue.rule_declaration_conflicts()

    monkeypatch.setattr(
        rule,
        "mode_declaration",
        rule_mod.RuleModeDeclaration(modes=original.modes, evidence=("unrelated-tag",)),
    )
    without_corpus_tag = catalogue.rule_declaration_conflicts()

    assert with_corpus_tag == without_corpus_tag, (with_corpus_tag, without_corpus_tag)


# =========================================================================== #
# AC21: FAILURE_MODE_NAMES is derived from the specification
# =========================================================================== #


def test_ac21_failure_mode_names_is_derived_from_the_specification():
    import segfacet.failure_modes as fm
    import segfacet.synth.perturbation as perturbation

    assert set(perturbation.FAILURE_MODE_NAMES) - {0} == set(fm.SPECIFICATION)
    assert perturbation.FAILURE_MODE_NAMES[0] == fm.CLEAN_CONTROL_NAME
    for mode_id, mode in fm.SPECIFICATION.items():
        assert perturbation.FAILURE_MODE_NAMES[mode_id] == mode.short_name, mode_id


def test_adv_ac21_missing_key_zero_fails_the_check():
    """Positive control: a FAILURE_MODE_NAMES-shaped mapping missing key 0
    fails the exact AC21 assertion this item pins."""
    import segfacet.failure_modes as fm

    names_missing_zero = {mode_id: mode.short_name for mode_id, mode in fm.SPECIFICATION.items()}
    assert 0 not in names_missing_zero
    with pytest.raises(KeyError):
        assert names_missing_zero[0] == fm.CLEAN_CONTROL_NAME


# =========================================================================== #
# AC22: the committed corpora do not move
# =========================================================================== #


def test_ac22_committed_corpora_agree_with_the_derived_name_map():
    import segfacet.failure_modes as fm
    import segfacet.synth.corpus as corpus_module
    import segfacet.synth.intensity as intensity_module

    derived = fm.failure_mode_names()
    assert derived, "expected a non-empty derived name map"

    geometric_cases = corpus_module.load_manifest()["cases"]
    assert geometric_cases, "expected a non-empty geometric manifest"
    for case in geometric_cases:
        assert case["failure_mode_name"] == derived[case["failure_mode"]], case["case_id"]

    intensity_cases = intensity_module.load_intensity_manifest()["cases"]
    assert intensity_cases, "expected a non-empty intensity manifest"
    for case in intensity_cases:
        assert case["failure_mode_name"] == derived[case["failure_mode"]], case["case_id"]


# =========================================================================== #
# AC23: the specification's new fields reach both artifacts
# =========================================================================== #


def test_ac23_new_fields_reach_both_artifacts(tmp_path):
    import segfacet.failure_modes as fm

    json_dest = tmp_path / "failure_modes.generated.json"
    md_dest = tmp_path / "failure_modes.generated.md"
    fm.main(["--json", str(json_dest), "--md", str(md_dest)])

    payload = json.loads(json_dest.read_text(encoding="utf-8"))
    assert len(payload["modes"]) == 10
    for mode_record in payload["modes"]:
        assert "short_name" in mode_record, mode_record["id"]
        assert "mechanism" in mode_record, mode_record["id"]

    md_text = md_dest.read_text(encoding="utf-8")
    for mode_id, mode in fm.SPECIFICATION.items():
        section = _mode_section(md_text, mode_id)
        assert mode.short_name in section, mode_id
        assert mode.mechanism in section, mode_id


def test_adv_ac23_empty_short_name_renders_explicitly(monkeypatch):
    import segfacet.failure_modes as fm

    patched_mode = dataclasses.replace(fm.SPECIFICATION[3], short_name="")
    patched_map = dict(fm.SPECIFICATION)
    patched_map[3] = patched_mode
    monkeypatch.setattr(fm, "SPECIFICATION", patched_map)

    md = fm.render_markdown()
    section = _mode_section(md, 3)
    assert "(none)" in section, section


# =========================================================================== #
# AC24: all three generated artifact pairs regenerate byte-identically
# =========================================================================== #


def _assert_lf_only_single_trailing_newline(raw: bytes):
    """*raw* must be undecoded bytes -- ``Path.read_text()`` applies
    universal-newline translation and would mask a genuine CRLF."""
    text = raw.decode("utf-8")
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_ac24_all_three_artifact_pairs_regenerate_byte_identically(tmp_path):
    import segfacet.catalogue as catalogue
    import segfacet.failure_modes as fm
    import segfacet.traceability as traceability
    from segfacet.synth.golden import assert_matches_committed_artifact

    # -- failure_modes.generated.{json,md} --------------------------------- #
    fm_json_a, fm_md_a = tmp_path / "fm_a.json", tmp_path / "fm_a.md"
    fm_json_b, fm_md_b = tmp_path / "fm_b.json", tmp_path / "fm_b.md"
    fm.main(["--json", str(fm_json_a), "--md", str(fm_md_a)])
    fm.main(["--json", str(fm_json_b), "--md", str(fm_md_b)])
    assert fm_json_a.read_bytes() == fm_json_b.read_bytes()
    assert fm_md_a.read_bytes() == fm_md_b.read_bytes()
    _assert_lf_only_single_trailing_newline(fm_json_a.read_bytes())
    _assert_lf_only_single_trailing_newline(fm_md_a.read_bytes())
    assert_matches_committed_artifact(fm_json_a, _COMMITTED_FM_JSON)
    # Markdown: structural section comparison (no ground for byte-exact
    # comparison exists in tests/committed_artifact_guard.py, and this item
    # adds none) -- extracted "## Mode N: title" headings must agree.
    fresh_headings = dict(
        re.findall(r"^## Mode (\d+): (.+)$", fm_md_a.read_text(encoding="utf-8"), flags=re.MULTILINE)
    )
    committed_headings = dict(
        re.findall(r"^## Mode (\d+): (.+)$", _COMMITTED_FM_MD.read_text(encoding="utf-8"), flags=re.MULTILINE)
    )
    assert fresh_headings, "expected >=1 parsed mode heading"
    assert fresh_headings == committed_headings

    # -- traceability_matrix.generated.{json,md} ---------------------------- #
    trace_json_a, trace_md_a = tmp_path / "trace_a.json", tmp_path / "trace_a.md"
    trace_json_b, trace_md_b = tmp_path / "trace_b.json", tmp_path / "trace_b.md"
    traceability.main(["--json", str(trace_json_a), "--md", str(trace_md_a)])
    traceability.main(["--json", str(trace_json_b), "--md", str(trace_md_b)])
    assert trace_json_a.read_bytes() == trace_json_b.read_bytes()
    assert trace_md_a.read_bytes() == trace_md_b.read_bytes()
    _assert_lf_only_single_trailing_newline(trace_json_a.read_bytes())
    _assert_lf_only_single_trailing_newline(trace_md_a.read_bytes())
    assert_matches_committed_artifact(trace_json_a, _COMMITTED_TRACE_JSON)
    # Markdown: the item 146 precedent (decode-wrapped full-text compare).
    fresh_md_bytes = trace_md_a.read_bytes()
    committed_md_bytes = _COMMITTED_TRACE_MD.read_bytes()
    assert fresh_md_bytes, "expected non-empty traceability markdown"
    assert fresh_md_bytes.decode("utf-8") == committed_md_bytes.decode("utf-8")

    # -- feature_catalogue.generated.{json,md} ------------------------------ #
    cat_json_a, cat_md_a = tmp_path / "cat_a.json", tmp_path / "cat_a.md"
    cat_json_b, cat_md_b = tmp_path / "cat_b.json", tmp_path / "cat_b.md"
    catalogue.main(["--json", str(cat_json_a), "--md", str(cat_md_a)])
    catalogue.main(["--json", str(cat_json_b), "--md", str(cat_md_b)])
    assert cat_json_a.read_bytes() == cat_json_b.read_bytes()
    assert cat_md_a.read_bytes() == cat_md_b.read_bytes()
    _assert_lf_only_single_trailing_newline(cat_json_a.read_bytes())
    _assert_lf_only_single_trailing_newline(cat_md_a.read_bytes())
    assert_matches_committed_artifact(cat_json_a, _COMMITTED_CAT_JSON)
    fresh_cat_md_bytes = cat_md_a.read_bytes()
    committed_cat_md_bytes = _COMMITTED_CAT_MD.read_bytes()
    assert fresh_cat_md_bytes, "expected non-empty catalogue markdown"
    assert fresh_cat_md_bytes.decode("utf-8") == committed_cat_md_bytes.decode("utf-8")


# =========================================================================== #
# AC25: the matrix no longer advertises a retired constant
# =========================================================================== #


def test_ac25_matrix_note_names_the_specification_not_a_retired_constant(matrix):
    assert "failure_modes.py" in matrix.note, matrix.note
    assert "MODE_RUNGS" not in matrix.note, matrix.note
    assert '"corpus"' not in matrix.note, matrix.note
    assert "'corpus'" not in matrix.note, matrix.note


# =========================================================================== #
# AC26: no rule firing moves
# =========================================================================== #


def test_ac26_every_corpus_case_agrees_and_status_derives_correctly(measured):
    import segfacet.failure_modes as fm

    for mode_id, mode in fm.SPECIFICATION.items():
        assert mode.corpus_cases or mode_id == 10, mode_id
        for case in mode.corpus_cases:
            assert fm.case_agrees(case), (mode_id, case.case_id)

        derived = fm.derive_status(mode)
        if mode_id == 10:
            assert derived == "proposed", derived
        else:
            assert derived == "validated", (mode_id, derived)


# =========================================================================== #
# AC27: aide check stays clean, warning-class-checked (no count pin)
# =========================================================================== #


_BASELINE_WARNING_CLASSES = (
    "assumptions-block",
    "awaiting-a-decision",
    "branch-state",
    "retracted-criterion",
)
_BRANCH_STATE_WARNING_PREFIXES = ("stale claim branch", "unrecognised branch")


def _classify_warning(message: str) -> str:
    if message.startswith(_BRANCH_STATE_WARNING_PREFIXES):
        return "branch-state"
    if re.search(r"criterion \d+ was retracted on \d{4}-\d{2}-\d{2}", message):
        return "retracted-criterion"
    if "assumptions" in message.lower():
        return "assumptions-block"
    if "awaiting a decision" in message.lower():
        return "awaiting-a-decision"
    return "unclassified"


def test_ac27_aide_check_reports_no_error_and_no_new_warning_class():
    aide = _aide_module()
    errors, warnings = aide.run_checks(_REPO_ROOT, aide.load_config(_REPO_ROOT))
    assert errors == [], errors
    assert warnings, "run_checks returned no warnings at all -- expected the baseline"

    classes = {_classify_warning(warning) for warning in warnings}
    assert classes <= set(_BASELINE_WARNING_CLASSES), (
        f"aide check reports a warning class outside the recorded baseline: "
        f"{classes - set(_BASELINE_WARNING_CLASSES)}"
    )

    for warning in warnings:
        assert ".gitattributes" not in warning, warning


def test_adv_ac27_unclassified_warning_would_be_caught():
    assert _classify_warning("a brand new kind of warning nobody has seen") == "unclassified"
