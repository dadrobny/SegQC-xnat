"""Tests for item 149 -- the traceability matrix becomes the conformance
report (``segfacet.traceability`` re-pointed at ``segfacet.failure_modes.
SPECIFICATION`` as its primary source, per corpus case across BOTH committed
corpora rather than the geometric one alone).

Covers Acceptance Criteria AC1-AC33 per the item spec's Testing Strategy:
one focused test per AC (several parametrised over the ten catalogued modes
or the two corpora), plus the listed adversarial/edge cases -- a
deliberately altered expected set (AC17, the headline check), an emptied
``corpus_cases`` (AC14), a dropped ``ConsumedPath`` (AC12), ``derive_status``/
``SPECIFICATION`` patched (AC4/AC30 no-cache proof), a re-narrowed rule
declaration (AC10/AC19), determinism/immutability (AC20/AC32), degenerate
rows (mode 10, AC7; mode 8, AC18), and the guard's non-vacuity proof (AC25).

Field-name note (same discipline as ``test_138_traceability_matrix.py``):
the item spec pins the JSON's *content* precisely per-AC but leaves several
container shapes unstated. ``_mode_records``/``_rule_records`` (copied, not
imported, per this repo's module-independence convention for item tests)
accept either a dict keyed by mode/rule id or a list of records. The field
*names* this module reads --  ``primary_source``, ``schema_version``,
``status``, ``authored_status``, ``edge_rungs``, ``rung``, ``anchor_paths``,
``read_paths``, ``granularity``, ``read_paths_qualifier``, ``rules``,
``cases``, ``pipeline_detected``, ``rule_attribution``,
``classification_conflicts``, ``corpus_designated_unregistered_rule_ids``,
``conformance`` (with ``cases``, ``agree_count``, ``disagree_count``,
``conformant``, ``disagreements``, ``unspecified_cases``, and per-case
``corpus``/``case_id``/``mode``/``expected_firing``/``measured_firing``/
``agrees``/``expected_source``) -- are this test module's own executable
statement of the contract, derived from the spec's prose and Implementation
Steps.

AC28/AC29 (call-count discipline, shared with test_138): no ``build_matrix()``
call sits in a test body anywhere in this module -- every call site is
inside a function decorated ``@pytest.fixture``. One module-scoped unpatched
``matrix``/``raw_matrix`` fixture pair (shared with the mechanism that also
proves no cache exists), and one function-scoped fixture per monkeypatch
group. This module also carries the one cross-module AST self-inspection
test (``test_ac28_...``) that checks *both* this module and
``test_138_traceability_matrix.py`` for a stray call site.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

_COMMITTED_JSON = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
_COMMITTED_MD = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"
_FM_COMMITTED_JSON = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.json"
_FM_COMMITTED_MD = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.md"
_GEOMETRIC_MANIFEST_PATH = _REPO_ROOT / "tests" / "corpus" / "manifest.json"
_INTENSITY_MANIFEST_PATH = _REPO_ROOT / "tests" / "corpus" / "intensity" / "manifest.json"
_TEST_138_PATH = _REPO_ROOT / "tests" / "test_138_traceability_matrix.py"

MODES = tuple(range(1, 11))

#: AC28/AC29: every ``build_matrix()`` call site in this module must sit
#: lexically inside a function decorated ``@pytest.fixture``, and the
#: AST-counted total must equal this constant and be ``<= 20``.
_BUILD_MATRIX_CALL_SITE_BUDGET = 11


# =========================================================================== #
# House helpers (copied, not imported, from test_138 -- module-independence
# convention for item tests, per test_143's own precedent)
# =========================================================================== #


def _mode_records(payload: dict) -> dict:
    modes = payload["modes"]
    if isinstance(modes, dict):
        return {int(k): v for k, v in modes.items()}
    return {int(r["mode"]): r for r in modes}


def _rule_records(payload: dict) -> dict:
    rules = payload["rules"]
    if isinstance(rules, dict):
        return dict(rules)
    return {r["rule_id"]: r for r in rules}


def _mode_record(payload: dict, mode: int) -> dict:
    records = _mode_records(payload)
    assert mode in records, (mode, sorted(records))
    return records[mode]


def _edge_rung_tuples(record: dict):
    """Normalise a mode record's ``edge_rungs`` to a list of
    ``(rule_id, detector, evidence_rung)`` tuples, accepting either a list
    of 3-element sequences or a list of dicts carrying those three keys."""
    entries = record["edge_rungs"]
    tuples = []
    for entry in entries:
        if isinstance(entry, dict):
            tuples.append((entry["rule_id"], entry["detector"], entry["evidence_rung"]))
        else:
            rule_id, detector, evidence_rung = entry
            tuples.append((rule_id, detector, evidence_rung))
    return tuples


def _geometric_manifest_cases() -> list:
    payload = json.loads(_GEOMETRIC_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty geometric corpus manifest"
    return cases


def _intensity_manifest_cases() -> list:
    payload = json.loads(_INTENSITY_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty intensity corpus manifest"
    return cases


def _all_manifest_case_keys() -> set:
    """``{(corpus, case_id)}`` across both committed corpora."""
    keys = {("geometric", c["case_id"]) for c in _geometric_manifest_cases()}
    keys |= {("intensity", c["case_id"]) for c in _intensity_manifest_cases()}
    return keys


def _patch_specification_mode(monkeypatch, failure_modes_module, mode: int, **replacements):
    """Copied from test_138's own helper (module-independence convention).
    Replace ``SPECIFICATION[mode]`` with a ``dataclasses.replace`` of its
    current entry carrying *replacements*, via ``monkeypatch.setattr`` on
    the whole mapping so ``build_matrix``'s live read picks it up regardless
    of ``MappingProxyType`` immutability."""
    original_map = failure_modes_module.SPECIFICATION
    original_entry = original_map[mode]
    patched_map = dict(original_map)
    patched_map[mode] = dataclasses.replace(original_entry, **replacements)
    monkeypatch.setattr(failure_modes_module, "SPECIFICATION", patched_map)


def _is_fixture_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr == "fixture"
    if isinstance(target, ast.Name):
        return target.id == "fixture"
    return False


def _is_build_matrix_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "build_matrix"
    if isinstance(func, ast.Name):
        return func.id == "build_matrix"
    return False


def _build_matrix_call_sites(tree: ast.Module):
    """Yield ``(lineno, enclosing_is_fixture)`` for every ``build_matrix()``
    call in *tree*, at any nesting depth -- shared logic with test_138's own
    copy (module-independence convention: copied, not imported)."""
    results = []

    def _walk(node, enclosing_is_fixture):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_fixture = any(_is_fixture_decorator(d) for d in child.decorator_list)
                _walk(child, is_fixture)
            else:
                if _is_build_matrix_call(child):
                    results.append((child.lineno, enclosing_is_fixture))
                _walk(child, enclosing_is_fixture)

    _walk(tree, False)
    return results


# =========================================================================== #
# build_matrix() call-site fixtures (AC28/AC29): one module-scoped unpatched
# fixture, and one function-scoped fixture per monkeypatch group. Never a
# cache inside the generator (AC30) -- each adversarial fixture below calls
# build_matrix() fresh.
# =========================================================================== #


@pytest.fixture(scope="module")
def raw_matrix():
    import segfacet.traceability as traceability

    return traceability.build_matrix()


@pytest.fixture(scope="module")
def matrix(raw_matrix):
    import segfacet.traceability as traceability

    return traceability.matrix_to_dict(raw_matrix)


@pytest.fixture
def matrix_mode3_expected_firing_altered(monkeypatch):
    """AC17's headline adversarial fixture: SPECIFICATION[3]'s sole corpus
    case (``mode3_inject_islands``) is patched to claim ``("coverage",)``
    instead of the live, measured ``("fragmentation",)``."""
    import segfacet.failure_modes as failure_modes_module
    import segfacet.traceability as traceability

    original_case = failure_modes_module.SPECIFICATION[3].corpus_cases[0]
    assert original_case.case_id == "mode3_inject_islands"
    altered_case = dataclasses.replace(original_case, expected_firing=("coverage",))
    _patch_specification_mode(monkeypatch, failure_modes_module, 3, corpus_cases=(altered_case,))
    return traceability.matrix_to_dict(traceability.build_matrix())


@pytest.fixture
def matrix_mode5_corpus_cases_emptied(monkeypatch):
    """AC14: mode 5's only corpus case (``mode5_remove_level``, a real
    manifest case with ``failure_mode == 5``) is orphaned by emptying the
    mode's own ``corpus_cases`` -- proving the enumeration is
    manifest-driven, not specification-driven."""
    import segfacet.failure_modes as failure_modes_module
    import segfacet.traceability as traceability

    _patch_specification_mode(monkeypatch, failure_modes_module, 5, corpus_cases=())
    return traceability.matrix_to_dict(traceability.build_matrix())


@pytest.fixture
def matrix_consumed_path_dropped(monkeypatch):
    """AC12: drop one ``ConsumedPath`` (the "signal" robust_z entry) from
    ``reference_delta``'s live declaration, so
    ``catalogue.path_classification_conflicts()`` reports a soundness
    disagreement naming the rule and the path."""
    from segfacet.heuristics.rule import _RULES
    import segfacet.heuristics.rule as rule_mod
    import segfacet.traceability as traceability

    rule = _RULES["reference_delta"]
    original_decl = rule.mode_declaration
    dropped_path = "reference_delta.{label}.features.physical_volume_mm3.robust_z"
    remaining = tuple(cp for cp in original_decl.consumed_paths if cp.path != dropped_path)
    assert len(remaining) == len(original_decl.consumed_paths) - 1, "fixture assumption violated"
    replacement = rule_mod.RuleModeDeclaration(
        modes=original_decl.modes, evidence=original_decl.evidence, consumed_paths=remaining
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)
    return traceability.matrix_to_dict(traceability.build_matrix())


@pytest.fixture
def matrix_derive_status_patched(monkeypatch):
    """AC4/AC30's no-cache proof: ``derive_status`` is overridden for mode 8
    only, so the matrix's rendered ``status`` must follow the live function,
    never a value baked in at import or cached across builds."""
    import segfacet.failure_modes as failure_modes_module
    import segfacet.traceability as traceability

    original = failure_modes_module.derive_status

    def _patched(mode_spec):
        if mode_spec.id == 8:
            return "implemented" if original(mode_spec) != "implemented" else "specified"
        return original(mode_spec)

    monkeypatch.setattr(failure_modes_module, "derive_status", _patched)
    return traceability.matrix_to_dict(traceability.build_matrix())


@pytest.fixture
def matrix_mode8_name_patched(monkeypatch):
    """AC4's title-follows-the-specification proof: SPECIFICATION[8].name is
    patched to a distinctive literal that cannot pre-exist in any committed
    artifact."""
    import segfacet.failure_modes as failure_modes_module
    import segfacet.traceability as traceability

    _patch_specification_mode(
        monkeypatch, failure_modes_module, 8, name="AC149-adversarial mode-8 title, on purpose, for a test"
    )
    return traceability.matrix_to_dict(traceability.build_matrix())


@pytest.fixture
def matrix_reference_delta_renarrowed(monkeypatch):
    """AC10/AC19: narrowing reference_delta back to modes=(2,) must shrink
    both mode 1's read_paths (AC10) and its rule_attribution (AC19), from
    the live declaration rather than any literal -- the same re-narrowing
    test_138's own AC32 adversarial fixture exercises, copied here
    (module-independence convention) because it demonstrates a different
    pair of claims."""
    from segfacet.heuristics.rule import _RULES
    import segfacet.heuristics.rule as rule_mod
    import segfacet.traceability as traceability

    rule = _RULES["reference_delta"]
    narrowed = rule_mod.RuleModeDeclaration(
        modes=(2,), evidence=("analytic", "AC149 adversarial: re-narrowed back to modes=(2,)")
    )
    monkeypatch.setattr(rule, "mode_declaration", narrowed)
    return traceability.matrix_to_dict(traceability.build_matrix())


@pytest.fixture
def two_builds_with_specification_patched_between(monkeypatch):
    """AC30: one unpatched build, then SPECIFICATION[8].name patched, then a
    second build -- both from a fresh ``build_matrix()`` call, proving no
    cache. Returns ``(d_before, d_after)``."""
    import segfacet.failure_modes as failure_modes_module
    import segfacet.traceability as traceability

    d_before = traceability.matrix_to_dict(traceability.build_matrix())
    _patch_specification_mode(
        monkeypatch,
        failure_modes_module,
        8,
        name="AC149-adversarial no-cache probe title, on purpose, for a test",
    )
    d_after = traceability.matrix_to_dict(traceability.build_matrix())
    return d_before, d_after


@pytest.fixture
def inertness_probe():
    """AC32's whole mechanism in one fixture: ``run_rules`` before and after
    two fresh, unpatched ``build_matrix()`` calls -- proving both inertness
    and determinism, still true now that the builder drives 13 corpus cases
    through the pipeline. Also used for the mutation-non-leak claim (via the
    two independently-built dicts)."""
    from segfacet.config import bundled_default_config
    from segfacet.heuristics.runner import run_rules
    from segfacet.pipeline import extract_feature_record
    from segfacet.synth.clean_gt import build_clean_spine
    import segfacet.traceability as traceability

    config = bundled_default_config()
    clean = build_clean_spine()
    record = extract_feature_record(clean.seg_img, config)

    before = run_rules(record, config)
    matrix_one = traceability.build_matrix()
    d1 = traceability.matrix_to_dict(matrix_one)
    after = run_rules(record, config)
    matrix_two = traceability.build_matrix()
    d2 = traceability.matrix_to_dict(matrix_two)
    return before, after, d1, d2


# =========================================================================== #
# AC1: the specification is named as the primary source
# =========================================================================== #


def test_ac1_primary_source_named_in_note_and_both_artifacts(matrix):
    import segfacet.traceability as traceability

    assert matrix["primary_source"] == "src/segfacet/failure_modes.py"
    assert "src/segfacet/failure_modes.py" in traceability._NOTE

    committed_json_text = _COMMITTED_JSON.read_text(encoding="utf-8")
    committed_md_text = _COMMITTED_MD.read_text(encoding="utf-8")
    assert "src/segfacet/failure_modes.py" in committed_json_text
    assert "src/segfacet/failure_modes.py" in committed_md_text


# =========================================================================== #
# AC2: the schema version is bumped
# =========================================================================== #


def test_ac2_schema_version_bumped_to_1_1(matrix):
    import segfacet.traceability as traceability

    assert traceability.SCHEMA_VERSION == "1.1"
    assert matrix["schema_version"] == "1.1"


# =========================================================================== #
# AC3: no retired rung constant is read by traceability.py
# =========================================================================== #


def test_ac3_no_retired_rung_constant_bound_at_module_level():
    source = (_REPO_ROOT / "src" / "segfacet" / "traceability.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    bound_names = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    bound_names.add(target.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            bound_names.add(stmt.target.id)

    forbidden = {"MODE_RUNGS", "ModeRung", "RUNGS", "RUNG_LABELS"}
    offenders = bound_names & forbidden
    assert offenders == set(), offenders


def test_ac3_no_int_keyed_dict_literal_carries_a_rung_string():
    import segfacet.failure_modes as failure_modes_module

    source = (_REPO_ROOT / "src" / "segfacet" / "traceability.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    rungs = set(failure_modes_module.EVIDENCE_RUNGS)
    assert rungs, "expected a non-empty rung vocabulary"

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, int)
                and not isinstance(key.value, bool)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value in rungs
            ):
                offenders.append((key.value, value.value))
    assert offenders == [], offenders


def test_ac3_retired_names_appear_only_in_comments():
    source = (_REPO_ROOT / "src" / "segfacet" / "traceability.py").read_text(encoding="utf-8")
    forbidden = ("MODE_RUNGS", "ModeRung", "RUNGS", "RUNG_LABELS")
    code_only_lines = [line.split("#", 1)[0] for line in source.splitlines()]
    code_text = "\n".join(code_only_lines)
    for name in forbidden:
        assert re.search(r"\b" + re.escape(name) + r"\b", code_text) is None, name


# =========================================================================== #
# AC4: every mode row carries its derived status
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac4_mode_status_equals_derive_status(mode, matrix):
    import segfacet.failure_modes as failure_modes_module

    record = _mode_record(matrix, mode)
    expected = failure_modes_module.derive_status(failure_modes_module.SPECIFICATION[mode])
    assert record["status"] == expected, mode
    assert record["status"] in failure_modes_module.STATUSES, record["status"]


def test_adv_ac4_ac30_derive_status_patched_changes_the_rendered_status(
    matrix, matrix_derive_status_patched
):
    before = _mode_record(matrix, 8)["status"]
    after = _mode_record(matrix_derive_status_patched, 8)["status"]
    assert after != before, (before, after)


def test_adv_ac4_specification_name_patched_changes_the_rendered_title(matrix, matrix_mode8_name_patched):
    before = _mode_record(matrix, 8)["title"]
    after = _mode_record(matrix_mode8_name_patched, 8)["title"]
    assert after != before, (before, after)
    assert after == "AC149-adversarial mode-8 title, on purpose, for a test"


# =========================================================================== #
# AC5: the authored status is rendered beside the derived one
# =========================================================================== #


def test_ac5_mode8_and_mode10_show_derived_and_authored_status_distinguishably(matrix):
    import segfacet.failure_modes as failure_modes_module

    mode8 = _mode_record(matrix, 8)
    mode10 = _mode_record(matrix, 10)
    assert mode8["authored_status"] == failure_modes_module.SPECIFICATION[8].status
    assert mode10["authored_status"] == failure_modes_module.SPECIFICATION[10].status
    assert mode10["authored_status"] == "proposed"
    # mode 10 is the catalogue's one non-derived-past-proposed entry: no
    # rule declares it, so status stays "proposed" too -- the two fields
    # happen to agree here, but they are still two independently-carried
    # fields (mode 8's pair, below, need not agree).
    assert mode10["status"] == mode10["authored_status"]
    for mode_record in (mode8, mode10):
        assert "status" in mode_record and "authored_status" in mode_record


# =========================================================================== #
# AC6: per-edge rungs are rendered per mode, matching the specification
# exactly
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac6_edge_rungs_equal_specification_intended_rules_exactly(mode, matrix):
    import segfacet.failure_modes as failure_modes_module

    record = _mode_record(matrix, mode)
    expected = [
        (rule.rule_id, rule.detector, rule.evidence_rung)
        for rule in failure_modes_module.SPECIFICATION[mode].intended_rules
    ]
    actual = _edge_rung_tuples(record)
    assert actual == expected, (mode, actual, expected)


# =========================================================================== #
# AC7: the derived mode rung stays a separate, explicit field
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac7_rung_field_equals_derive_mode_rung_or_none(mode, matrix):
    import segfacet.failure_modes as failure_modes_module

    record = _mode_record(matrix, mode)
    expected = failure_modes_module.derive_mode_rung(failure_modes_module.SPECIFICATION[mode]) or ""
    assert (record["rung"] or "") == expected, mode


def test_ac7_mode10_degenerate_row_renders_null_rung_and_empty_edges_without_raising(matrix):
    mode10 = _mode_record(matrix, 10)
    assert mode10["rung"] is None, mode10["rung"]
    assert mode10["edge_rungs"] == [], mode10["edge_rungs"]
    assert mode10["rules"] == [], mode10["rules"]


def test_ac7_committed_markdown_renders_mode10_rung_as_explicit_none():
    text = _COMMITTED_MD.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] == "10":
            assert "(none)" in line, line
            return
    raise AssertionError("expected a rendered mode-10 row in the committed markdown")


# =========================================================================== #
# AC8: the anchor column and the read-path column are separate and
# separately labelled
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac8_anchor_paths_and_read_paths_are_two_distinct_fields(mode, matrix):
    record = _mode_record(matrix, mode)
    assert "anchor_paths" in record
    assert "read_paths" in record
    assert "feature_paths" not in record, "the conflated union must be gone (AC8)"


def test_ac8_committed_markdown_carries_both_headers_verbatim():
    text = _COMMITTED_MD.read_text(encoding="utf-8")
    assert "Stage-18 metric anchor paths" in text
    assert "Rule signal read paths" in text
    assert "feature_paths" not in text


# =========================================================================== #
# AC9: a mode whose two columns differ renders both (modes 4 and 7)
# =========================================================================== #


def test_ac9_mode4_and_mode7_anchor_and_read_paths_differ(matrix):
    mode4 = _mode_record(matrix, 4)
    assert tuple(mode4["anchor_paths"]) == ("stage3.monotonic_consistency.is_monotonic",)
    assert "stage3.monotonic_consistency.non_monotonic_pairs[]" in mode4["read_paths"]
    assert "stage3.monotonic_consistency.is_monotonic" not in mode4["read_paths"]

    mode7 = _mode_record(matrix, 7)
    assert tuple(mode7["anchor_paths"]) == ("relationships.is_continuous",)
    assert tuple(mode7["read_paths"]) == ("relationships.out_of_order_labels[]",)


def test_ac9_committed_markdown_renders_both_cells_for_modes_4_and_7():
    lines = _COMMITTED_MD.read_text(encoding="utf-8").splitlines()
    for mode, anchor, read_path in (
        (4, "stage3.monotonic_consistency.is_monotonic", "stage3.monotonic_consistency.non_monotonic_pairs[]"),
        (7, "relationships.is_continuous", "relationships.out_of_order_labels[]"),
    ):
        row = None
        for line in lines:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0] == str(mode):
                row = line
                break
        assert row is not None, mode
        assert anchor in row, (mode, row)
        assert read_path in row, (mode, row)


# =========================================================================== #
# AC10: the read-path column is derived from signal-classified paths per
# rule
# =========================================================================== #


def test_ac10_mode1_read_paths_are_signal_classified_only(matrix):
    mode1 = _mode_record(matrix, 1)
    assert "reference_delta.{label}.features.physical_volume_mm3.robust_z" in mode1["read_paths"]
    assert "reference_delta.{label}.level_name" not in mode1["read_paths"]
    assert "reference_delta.lower_pct" not in mode1["read_paths"]


@pytest.mark.parametrize("mode", MODES)
def test_ac10_read_paths_equal_the_sorted_union_of_declaring_rules_signal_paths(mode, matrix):
    import segfacet.catalogue as catalogue_module

    record = _mode_record(matrix, mode)
    declared_rules = set(record["rules"])

    cat = catalogue_module.build_catalogue(strict=True)
    expected = set()
    for entry in cat.entries:
        for rule_id, role in entry.mode_roles:
            if rule_id in declared_rules and role == "signal":
                expected.add(entry.path)

    assert record["read_paths"] == sorted(expected), mode


def test_adv_ac10_renarrowed_reference_delta_shrinks_mode1_read_paths(
    matrix, matrix_reference_delta_renarrowed
):
    before = set(_mode_record(matrix, 1)["read_paths"])
    after = set(_mode_record(matrix_reference_delta_renarrowed, 1)["read_paths"])
    assert after < before, (before, after)
    assert "reference_delta.{label}.features.physical_volume_mm3.robust_z" not in after


# =========================================================================== #
# AC11: the granularity qualifier states signal-classification, not rule
# granularity, and never merges the anchor column in
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac11_granularity_is_signal_with_the_new_qualifier_text(mode, matrix):
    record = _mode_record(matrix, mode)
    assert record["granularity"] == "signal", mode
    qualifier = record["read_paths_qualifier"]
    assert "signal" in qualifier
    assert "never merged in" in qualifier
    assert "a rule that targets this mode reads this path" not in qualifier


def test_ac11_qualifier_renders_immediately_after_the_mode_table():
    lines = _COMMITTED_MD.read_text(encoding="utf-8").splitlines()
    mode_header_idx = None
    rule_header_idx = None
    for idx, line in enumerate(lines):
        if mode_header_idx is None and "Pipeline-detected" in line:
            mode_header_idx = idx
        if rule_header_idx is None and "Declared modes" in line:
            rule_header_idx = idx
    assert mode_header_idx is not None
    assert rule_header_idx is not None
    section = "\n".join(lines[mode_header_idx:rule_header_idx])
    assert "signal" in section
    assert "never merged in" in section


# =========================================================================== #
# AC12: an unclassified/dropped consumed path is reported, not silently
# dropped
# =========================================================================== #


def test_ac12_classification_conflicts_folded_from_catalogue(matrix):
    import segfacet.catalogue as catalogue_module

    live_conflicts = catalogue_module.path_classification_conflicts()
    assert matrix["classification_conflicts"] == list(live_conflicts)


def test_adv_ac12_dropped_consumed_path_reported_and_conformant_false(matrix_consumed_path_dropped):
    d = matrix_consumed_path_dropped
    conflicts = d["classification_conflicts"]
    assert conflicts, "expected at least one classification conflict"
    assert any("reference_delta" in c for c in conflicts), conflicts
    assert any("physical_volume_mm3" in c or "robust_z" in c for c in conflicts), conflicts
    assert d["conformance"]["conformant"] is False


# =========================================================================== #
# AC13: one conformance row per manifest case, across both corpora
# =========================================================================== #


def test_ac13_conformance_carries_thirteen_rows_across_both_corpora(matrix):
    cases = matrix["conformance"]["cases"]
    assert cases, "expected a non-empty conformance case list"
    actual_keys = {(c["corpus"], c["case_id"]) for c in cases}
    expected_keys = _all_manifest_case_keys()
    assert actual_keys == expected_keys
    assert len(cases) == 13, len(cases)
    geometric = [c for c in cases if c["corpus"] == "geometric"]
    intensity = [c for c in cases if c["corpus"] == "intensity"]
    assert len(geometric) == 9, len(geometric)
    assert len(intensity) == 4, len(intensity)
    for case in cases:
        for key in ("corpus", "case_id", "mode", "expected_firing", "measured_firing", "agrees", "expected_source"):
            assert key in case, (case, key)


# =========================================================================== #
# AC14: an unspecified mode-carrying case is a named hole
# =========================================================================== #


def test_ac14_committed_tree_has_no_unspecified_cases(matrix):
    assert matrix["conformance"]["unspecified_cases"] == []


def test_adv_ac14_emptied_corpus_cases_makes_the_manifest_case_a_named_hole(matrix_mode5_corpus_cases_emptied):
    d = matrix_mode5_corpus_cases_emptied
    conformance = d["conformance"]
    unspecified = conformance["unspecified_cases"]
    assert unspecified, "expected at least one unspecified case"
    assert any(entry.get("case_id") == "mode5_remove_level" for entry in unspecified), unspecified

    cases_by_key = {(c["corpus"], c["case_id"]): c for c in conformance["cases"]}
    orphaned = cases_by_key[("geometric", "mode5_remove_level")]
    assert orphaned["expected_source"] == "unspecified", orphaned
    assert orphaned["agrees"] is False, orphaned


# =========================================================================== #
# AC15: the clean controls are scored, with their source labelled
# =========================================================================== #


def test_ac15_clean_controls_labelled_manifest_clean_control(matrix):
    cases_by_key = {(c["corpus"], c["case_id"]): c for c in matrix["conformance"]["cases"]}
    for key in (("geometric", "clean_control"), ("intensity", "clean_hu")):
        assert key in cases_by_key, key
        entry = cases_by_key[key]
        assert entry["expected_source"] == "manifest-clean-control", entry
        assert entry["expected_firing"] == [], entry
        assert "measured_firing" in entry


# =========================================================================== #
# AC16: agreement is scored and the committed tree is conformant
# =========================================================================== #


def test_ac16_committed_tree_agrees_thirteen_of_thirteen_and_is_conformant(matrix):
    conformance = matrix["conformance"]
    assert conformance["disagree_count"] == 0
    assert conformance["agree_count"] == 13
    assert conformance["conformant"] is True
    assert conformance["disagreements"] == []


# =========================================================================== #
# AC17: a deliberately altered expected set fails, naming case, expected and
# measured (the headline check)
# =========================================================================== #


def test_adv_ac17_altered_expected_set_fails_naming_case_expected_and_measured(
    matrix_mode3_expected_firing_altered,
):
    conformance = matrix_mode3_expected_firing_altered["conformance"]
    assert conformance["conformant"] is False
    disagreements = conformance["disagreements"]
    assert disagreements, "expected at least one disagreement"

    named = [d for d in disagreements if d.get("case_id") == "mode3_inject_islands"]
    assert named, disagreements
    entry = named[0]
    assert list(entry["expected_firing"]) == ["coverage"], entry
    assert list(entry["measured_firing"]) == ["fragmentation"], entry

    message = repr(disagreements)
    for token in ("mode3_inject_islands", "coverage", "fragmentation"):
        assert token in message, (token, message)


def test_ac17_committed_tree_conformance_assertion_would_fail_loudly_with_all_three_named():
    """The test that asserts conformance over the live tree (AC16, above)
    fails with case, expected and measured all in its own message -- this
    test proves that failure message shape directly, independently of
    whether AC16's own assertion is currently green."""
    import segfacet.failure_modes as fm

    case = fm.SPECIFICATION[3].corpus_cases[0]
    altered = dataclasses.replace(case, expected_firing=("coverage",))
    measured = fm.measured_firing(case)
    failure_text = (
        f"disagreement: case={altered.case_id!r} expected={altered.expected_firing!r} "
        f"measured={measured!r}"
    )
    assert "mode3_inject_islands" in failure_text
    assert "coverage" in failure_text
    assert "fragmentation" in failure_text


# =========================================================================== #
# AC18: `cases` and `pipeline_detected` are derived across both corpora
# =========================================================================== #


def test_ac18_mode9_cases_and_pipeline_detected_span_both_corpora(matrix):
    mode9 = _mode_record(matrix, 9)
    assert mode9["pipeline_detected"] is True
    case_ids = {c["case_id"] for c in mode9["cases"]}
    assert case_ids == {"implausible_metal", "implausible_soft_tissue", "degenerate_uniform"}
    for case in mode9["cases"]:
        assert case["detection"] == "intensity_pipeline", case


def test_ac18_mode8_pipeline_detected_stays_false(matrix):
    mode8 = _mode_record(matrix, 8)
    assert mode8["pipeline_detected"] is False
    detections = {c["detection"] for c in mode8["cases"]}
    assert detections == {"reconstructed_record"}, detections


def test_ac18_no_geometric_only_mode_cases_change_from_the_committed_artifact(matrix):
    """Modes 1-8's own per-mode ``cases``/``pipeline_detected`` are
    untouched by the two-corpora extension -- only mode 9 (intensity)
    gains cases. Compared against the committed artifact (the durable
    "base" once this item's regeneration lands) rather than a git-history
    lookup, matching the AC19 attribution test's own pattern."""
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    committed_modes = _mode_records(committed_payload)
    for mode in range(1, 9):
        fresh_record = _mode_record(matrix, mode)
        committed_record = committed_modes[mode]
        assert fresh_record["cases"] == committed_record["cases"], mode
        assert fresh_record["pipeline_detected"] == committed_record["pipeline_detected"], mode
        for case in fresh_record["cases"]:
            assert case["case_id"] in {
                c["case_id"] for c in _geometric_manifest_cases()
            }, (mode, case)


# =========================================================================== #
# AC19: attribution is derived from the specification's corpus cases,
# across both corpora
# =========================================================================== #


def test_ac19_mode9_intensity_attributes_corpus_and_reference_delta_analytic(matrix):
    mode9 = _mode_record(matrix, 9)
    assert mode9["rule_attribution"]["intensity"] == "corpus"
    assert mode9["rule_attribution"]["intensity_reference_delta"] == "analytic"


def test_ac19_modes_1_to_8_attribution_matches_the_base_artifact(matrix):
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    committed_modes = _mode_records(committed_payload)
    for mode in range(1, 9):
        fresh_attribution = _mode_record(matrix, mode)["rule_attribution"]
        committed_attribution = committed_modes[mode]["rule_attribution"]
        assert fresh_attribution == committed_attribution, mode


def test_adv_ac19_renarrowed_reference_delta_shrinks_mode1_attribution(
    matrix, matrix_reference_delta_renarrowed
):
    before = _mode_record(matrix, 1)["rule_attribution"]
    after = _mode_record(matrix_reference_delta_renarrowed, 1)["rule_attribution"]
    assert "reference_delta" in before
    assert "reference_delta" not in after


# =========================================================================== #
# AC20: both artifacts regenerate byte-identically
# =========================================================================== #


def test_ac20_both_artifacts_regenerate_byte_identically_run_to_run(tmp_path):
    import segfacet.traceability as traceability

    json_a, md_a = tmp_path / "a.json", tmp_path / "a.md"
    json_b, md_b = tmp_path / "b.json", tmp_path / "b.md"
    traceability.main(["--json", str(json_a), "--md", str(md_a)])
    traceability.main(["--json", str(json_b), "--md", str(md_b)])

    bytes_a_json, bytes_b_json = json_a.read_bytes(), json_b.read_bytes()
    bytes_a_md, bytes_b_md = md_a.read_bytes(), md_b.read_bytes()
    assert bytes_a_json, "expected non-empty JSON output"
    assert bytes_a_md, "expected non-empty markdown output"
    assert bytes_a_json == bytes_b_json
    assert bytes_a_md == bytes_b_md


def test_ac20_fresh_matches_committed_byte_for_byte(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact
    import segfacet.traceability as traceability

    json_dest, md_dest = tmp_path / "tm.json", tmp_path / "tm.md"
    traceability.main(["--json", str(json_dest), "--md", str(md_dest)])

    fresh_json_bytes = json_dest.read_bytes()
    committed_json_bytes = _COMMITTED_JSON.read_bytes()
    assert fresh_json_bytes, "expected non-empty fresh JSON"
    assert committed_json_bytes, "expected non-empty committed JSON"
    assert_matches_committed_artifact(json_dest, _COMMITTED_JSON)

    fresh_md_bytes = md_dest.read_bytes()
    committed_md_bytes = _COMMITTED_MD.read_bytes()
    assert fresh_md_bytes, "expected non-empty fresh markdown"
    assert fresh_md_bytes == committed_md_bytes


# =========================================================================== #
# AC21: neither artifact carries a float leaf
# =========================================================================== #


def _walk_leaves(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_leaves(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_leaves(value)
    else:
        yield node


def test_ac21_traceability_matrix_has_no_float_leaf(matrix):
    fresh_floats = [v for v in _walk_leaves(matrix) if isinstance(v, float)]
    assert fresh_floats == [], fresh_floats

    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    committed_floats = [v for v in _walk_leaves(committed_payload) if isinstance(v, float)]
    assert committed_floats == [], committed_floats


def test_ac21_failure_modes_specification_has_no_float_leaf():
    import segfacet.failure_modes as failure_modes_module

    fresh_payload = failure_modes_module.specification_to_dict()
    fresh_floats = [v for v in _walk_leaves(fresh_payload) if isinstance(v, float)]
    assert fresh_floats == [], fresh_floats

    committed_payload = json.loads(_FM_COMMITTED_JSON.read_text(encoding="utf-8"))
    committed_floats = [v for v in _walk_leaves(committed_payload) if isinstance(v, float)]
    assert committed_floats == [], committed_floats


# =========================================================================== #
# AC22: the LF pin holds for all four generated paths
# =========================================================================== #


def test_ac22_neither_artifact_carries_a_carriage_return():
    for path in (_COMMITTED_JSON, _COMMITTED_MD, _FM_COMMITTED_JSON, _FM_COMMITTED_MD):
        data = path.read_bytes()
        assert data, path
        assert b"\r" not in data, path


def test_ac22_gitattributes_pins_all_four_generated_paths_eol_lf():
    text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rel_path in (
        "docs/aide/traceability_matrix.generated.json",
        "docs/aide/traceability_matrix.generated.md",
        "docs/aide/failure_modes.generated.json",
        "docs/aide/failure_modes.generated.md",
    ):
        pattern = re.compile(re.escape(rel_path) + r"[^\n]*eol=lf")
        assert pattern.search(text), rel_path


def _aide_module():
    import importlib.util

    aide_script = _REPO_ROOT / ".aide" / "scripts" / "aide.py"
    spec = importlib.util.spec_from_file_location("_aide_cli_149", aide_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_ac22_aide_check_reports_no_gitattributes_warning_for_these_paths():
    aide = _aide_module()
    _errors, warnings = aide.run_checks(_REPO_ROOT, aide.load_config(_REPO_ROOT))
    offending = [
        w
        for w in warnings
        if "gitattributes" in str(w).lower()
        and (
            "traceability_matrix.generated" in str(w)
            or "failure_modes.generated" in str(w)
        )
    ]
    assert offending == [], offending


# =========================================================================== #
# AC23: `GROUNDS` gains a sixth member
# =========================================================================== #


def test_ac23_grounds_has_exactly_six_members_the_sixth_is_no_float_leaf():
    import committed_artifact_guard as guard

    assert len(guard.GROUNDS) == 6
    assert guard.GROUNDS[-1] == "no-float-leaf", guard.GROUNDS


def test_ac23_module_docstring_names_the_discharging_no_float_leaf_test():
    import committed_artifact_guard as guard

    doc = guard.__doc__ or ""
    assert "no-float-leaf" in doc
    assert "float" in doc.lower()


# =========================================================================== #
# AC24: both artifacts are allowlisted under it, with reasons
# =========================================================================== #


def test_ac24_four_entries_allowlisted_under_no_float_leaf_with_reasons():
    import committed_artifact_guard as guard

    expected_paths = {
        "docs/aide/traceability_matrix.generated.json",
        "docs/aide/traceability_matrix.generated.md",
        "docs/aide/failure_modes.generated.json",
        "docs/aide/failure_modes.generated.md",
    }
    matching = [e for e in guard.ALLOWLIST if e.path in expected_paths]
    matched_paths = {e.path for e in matching}
    assert matched_paths == expected_paths, matched_paths

    for entry in matching:
        assert entry.ground == "no-float-leaf", entry
        assert entry.reason, entry
        assert "\n" not in entry.reason, entry


# =========================================================================== #
# AC25: the guard actually sees those comparisons (non-vacuity)
# =========================================================================== #


def test_ac25_guard_reports_violations_when_the_four_entries_are_dropped(monkeypatch):
    import committed_artifact_guard as guard

    dropped_paths = {
        "docs/aide/traceability_matrix.generated.json",
        "docs/aide/traceability_matrix.generated.md",
        "docs/aide/failure_modes.generated.json",
        "docs/aide/failure_modes.generated.md",
    }
    narrowed = tuple(e for e in guard.ALLOWLIST if e.path not in dropped_paths)
    assert len(narrowed) == len(guard.ALLOWLIST) - 4, "fixture assumption violated"
    monkeypatch.setattr(guard, "ALLOWLIST", narrowed)

    violations = list(guard.iter_violations(_REPO_ROOT / "tests"))
    assert violations, "expected non-vacuous guard visibility with the entries dropped"
    violated_paths = {v.committed_path for v in violations}
    assert "docs/aide/traceability_matrix.generated.md" in violated_paths, violated_paths
    assert "docs/aide/failure_modes.generated.md" in violated_paths, violated_paths


# =========================================================================== #
# AC26: the guard is clean as shipped
# =========================================================================== #


def test_ac26_guard_is_clean_with_the_committed_allowlist():
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(_REPO_ROOT / "tests"))
    assert violations == [], [guard.violation_message([v]) for v in violations]


# =========================================================================== #
# AC28: no build_matrix() call sits in a test body (cross-module claim)
# =========================================================================== #


def test_ac28_no_build_matrix_call_outside_a_fixture_across_both_modules():
    for module_path in (Path(__file__), _TEST_138_PATH):
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        sites = _build_matrix_call_sites(tree)
        non_fixtured = [lineno for lineno, in_fixture in sites if not in_fixture]
        assert non_fixtured == [], (module_path, non_fixtured)


# =========================================================================== #
# AC29: the call-site count is bounded and asserted (this module's own half)
# =========================================================================== #


def test_ac29_this_modules_call_site_count_matches_its_budget():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    sites = _build_matrix_call_sites(tree)
    assert len(sites) == _BUILD_MATRIX_CALL_SITE_BUDGET, (len(sites), _BUILD_MATRIX_CALL_SITE_BUDGET)
    assert _BUILD_MATRIX_CALL_SITE_BUDGET <= 20, _BUILD_MATRIX_CALL_SITE_BUDGET


# =========================================================================== #
# AC30: the generator holds no cache
# =========================================================================== #


def test_adv_ac30_two_builds_with_specification_patched_between_differ(
    two_builds_with_specification_patched_between,
):
    d_before, d_after = two_builds_with_specification_patched_between
    title_before = _mode_record(d_before, 8)["title"]
    title_after = _mode_record(d_after, 8)["title"]
    assert title_after != title_before, (title_before, title_after)


def test_ac30_no_cache_construct_in_the_generator_source():
    source = (_REPO_ROOT / "src" / "segfacet" / "traceability.py").read_text(encoding="utf-8")
    for forbidden in ("lru_cache", "functools.cache"):
        assert forbidden not in source, forbidden

    tree = ast.parse(source)
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            call_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert call_name != "build_matrix", (
                "module-level memo dict assigned from a build_matrix() result",
                ast.dump(stmt),
            )


# =========================================================================== #
# AC31: every adversarial monkeypatch fixture re-derives
# =========================================================================== #


@pytest.mark.parametrize(
    "fixture_name",
    [
        "matrix_mode3_expected_firing_altered",
        "matrix_mode5_corpus_cases_emptied",
        "matrix_consumed_path_dropped",
        "matrix_derive_status_patched",
        "matrix_mode8_name_patched",
        "matrix_reference_delta_renarrowed",
    ],
)
def test_ac31_every_adversarial_fixture_rederives_from_the_shared_unpatched_fixture(
    fixture_name, matrix, request
):
    patched = request.getfixturevalue(fixture_name)
    assert patched != matrix, fixture_name


# =========================================================================== #
# AC32: build_matrix stays inert at evaluation time
# =========================================================================== #


def test_ac32_build_matrix_is_inert_and_deterministic_at_evaluation_time(inertness_probe):
    before, after, d1, d2 = inertness_probe
    assert isinstance(before, list)
    assert after == before
    assert d1 == d2


def test_adv_ac32_matrix_to_dict_mutation_does_not_leak_into_a_later_call(raw_matrix):
    import segfacet.traceability as traceability

    d1 = traceability.matrix_to_dict(raw_matrix)
    assert d1, "expected a non-empty dict"
    d1["conformance"] = "deliberately corrupted by this test"
    d2 = traceability.matrix_to_dict(raw_matrix)
    assert d2["conformance"] != "deliberately corrupted by this test"


# =========================================================================== #
# AC33: no exercise columns are built (scope fence)
# =========================================================================== #


def test_ac33_no_per_rule_or_per_operator_exercise_column_in_either_artifact():
    json_text = _COMMITTED_JSON.read_text(encoding="utf-8")
    md_text = _COMMITTED_MD.read_text(encoding="utf-8")
    for forbidden_token in ("exercise_count", "operator_exercise", "corpus_exercise", "exercise column"):
        assert forbidden_token not in json_text, forbidden_token
        assert forbidden_token not in md_text, forbidden_token


def test_ac33_traceability_module_defines_no_exercise_derivation():
    source = (_REPO_ROOT / "src" / "segfacet" / "traceability.py").read_text(encoding="utf-8")
    for forbidden_token in ("exercise_count", "operator_exercise", "corpus_exercise"):
        assert forbidden_token not in source, forbidden_token

