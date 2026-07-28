"""Feature-catalogue drift test (item 104; Stage 19).

Guards item 103's generated feature & rule catalogue
(``src/segfacet/catalogue.py`` + ``src/segfacet/feature_docs.py``) against
silent drift between the *realised* record shape and its authored
documentation, and between both of those and the committed artifact
(``docs/aide/feature_catalogue.generated.json``). This module adds **no
production code** -- it is the CI mechanism that makes item 103's strict-mode
guard (``build_catalogue(strict=True)`` raising ``FeatureDocMissing`` /
``CatalogueError``) provably reached by every default ``python -m pytest``
run, plus a pre-diagnosed, sorted, complete report for when it fires.

Covers Acceptance Criteria AC1-AC22:

- AC1:  the module is ungated -- no ``importorskip``/skip/xfail marker, no
        ``os.environ``-conditional skip, and its imports name only stdlib,
        ``pytest``, and ``segfacet.*`` (never ``radiomics``/``cupy``/
        ``docker``/``subprocess``).
- AC2:  the walk is imported from ``segfacet.catalogue`` (``iter_leaf_paths``,
        ``iter_driver_records``), never reimplemented -- no function in this
        module recurses over a record.
- AC3:  no list/tuple/set/frozenset display holds >=12 path-shaped string
        constants (the six-path AC7 sentinel tuple is the largest legitimate
        one).
- AC4:  no absolute path literal (``/``, ``\\``, or a drive-letter prefix)
        anywhere in this module's source.
- AC5:  no ``hashlib`` import and no ``Path.read_bytes`` call -- this module
        compares parsed path sets, never bytes.
- AC6:  ``covered_paths()`` is the union of ``iter_leaf_paths(record)`` over
        every ``iter_driver_records()`` pair, and is deterministic.
- AC7:  the anti-vacuity floor -- >=3 driver pairs, a non-empty
        ``covered_paths()`` containing all six sentinel paths, a non-empty
        ``FEATURE_DOCS``.
- AC8:  direction 1 (realised-but-undocumented) is clean on the current tree
        and ``drift_report`` names an injected offender.
- AC9:  direction 2 (documented-but-no-longer-produced) likewise.
- AC10: both directions reported together, sorted, complete, with ``None``
        (never ``""``) when both sides are empty.
- AC11: every non-``None`` message names ``src/segfacet/feature_docs.py`` and
        ``python -m segfacet.catalogue``.
- AC12: ``strict_build_message`` exercises the real
        ``build_catalogue(strict=True)`` (returns ``None`` on the current
        tree) and converts ``FeatureDocMissing``/``CatalogueError`` stubs into
        a named message; a non-``CatalogueError`` stub propagates untouched.
- AC13: the committed artifact parses as JSON and every entry has a
        non-empty ``str`` ``path`` and a valid ``origin``.
- AC14: ``iter_committed_entries`` tolerates a flat ``"entries"`` list or
        nested ``"groups"[*]["entries"]``, and fails naming the top-level
        keys otherwise.
- AC15: direction 3 (stale committed artifact) is clean on the current tree
        and names an injected stale path.
- AC16: direction 4 (orphaned record-tier artifact entry) likewise.
- AC17: the committed artifact carries no duplicate paths.
- AC18: at least one committed entry is ``origin == "augmented"``, and no
        record-tier path is ever excused by that exemption.
- AC19: injecting one synthetic path into a *local copy* of the real
        ``covered_paths()`` result is caught, naming exactly that path;
        removing one real path is caught the same way.
- AC20: nothing shipped is mutated -- ``FEATURE_DOCS`` and the first driver
        record are unchanged after every check runs, and ``FEATURE_DOCS``
        rejects item assignment.
- AC21: running the four comparisons twice in one session is idempotent.
- AC22: the scope fence (this file adds exactly one new file) is verified by
        the validator's ``git diff``, not by a pytest in this module -- see
        Decisions & Trade-offs in the item 104 spec.

Adversarial / edge-case scenarios included: ``drift_report`` with both sides
empty (``None``, not ``""``); one side empty, the other a singleton (only one
labelled block appears); unsorted/duplicate-bearing input containers
producing identical sorted output; path strings containing ``{label}``/``[]``
surviving verbatim; ``iter_committed_entries`` over a flat layout, a nested
layout, an empty-groups layout, and an unrecognised layout; a missing
committed artifact reported as a named failure, never a bare
``FileNotFoundError``; an artifact entry with an unrecognised ``origin``
string failing loudly rather than being silently dropped; a non-
``CatalogueError`` stub propagating out of ``strict_build_message``; and
``covered_paths()`` called twice with the underlying driver records left
unmutated.
"""

from __future__ import annotations

import ast
import copy
import functools
import json
import re
from pathlib import Path

import pytest

from segfacet.catalogue import (
    CatalogueError,
    FeatureDocMissing,
    build_catalogue,
    iter_driver_records,
    iter_leaf_paths,
)
from segfacet.feature_docs import FEATURE_DOCS

# =========================================================================== #
# Path constants (AC4: no absolute literal; addressed relative to repo root)
# =========================================================================== #

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_ARTIFACT = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"

# The AC7 anti-vacuity sentinel: six paths item 103's AC4/AC5 pin, so this
# cannot rot silently. Deliberately the largest legitimate path-shaped literal
# in this module (AC3's threshold is 12).
_SENTINEL_PATHS = (
    "features_version",
    "per_label.{label}.geometry.touches_superior",
    "per_label.{label}.components.fragmentation_index",
    "relationships.out_of_order_labels[]",
    "stage3.per_label_offsets[].offset_mm",
    "overlaps[].overlap_voxels",
)

_REMEDIATION = (
    "Add them to src/segfacet/feature_docs.py, then regenerate: "
    "python -m segfacet.catalogue"
)

_VALID_ORIGINS = {"record", "augmented"}


# =========================================================================== #
# Module-level helpers (the surface the AC tests exercise directly)
# =========================================================================== #


def covered_paths() -> frozenset:
    """Union of ``iter_leaf_paths(record)`` over every driver record (AC6)."""
    union: set = set()
    for _driver_id, record in iter_driver_records():
        union |= iter_leaf_paths(record)
    return frozenset(union)


def documented_paths() -> frozenset:
    return frozenset(FEATURE_DOCS)


def _drift_block(label: str, paths) -> str:
    lines = [f"{len(paths)} leaf path(s) {label}:"]
    for path in sorted(paths):
        lines.append(f"  - {path}")
    return "\n".join(lines)


def drift_report(*, realised, documented, realised_label, documented_label):
    """The one reporter every direction routes through.

    Returns ``None`` iff both differences are empty; otherwise the two
    labelled, sorted, duplicate-free blocks plus the remediation line
    (AC8-AC11).
    """
    only_realised = set(realised) - set(documented)
    only_documented = set(documented) - set(realised)
    if not only_realised and not only_documented:
        return None
    blocks = []
    if only_realised:
        blocks.append(_drift_block(realised_label, only_realised))
    if only_documented:
        blocks.append(_drift_block(documented_label, only_documented))
    return "\n".join(blocks) + "\n" + _REMEDIATION


def strict_build_message(build_fn):
    """Call *build_fn* and convert ``CatalogueError``/``FeatureDocMissing``
    into a named message (AC12). Never swallows any other exception."""
    try:
        build_fn()
    except CatalogueError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def load_committed_catalogue(path: Path = _ARTIFACT):
    """Parse the committed catalogue artifact as JSON.

    An absent artifact fails with a named, actionable message -- never a bare
    ``FileNotFoundError`` traceback.
    """
    if not path.exists():
        pytest.fail(
            "committed catalogue artifact not found at "
            f"{path} (expected {_ARTIFACT}). Regenerate with: "
            "python -m segfacet.catalogue"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def iter_committed_entries(doc):
    """Tolerant reader (AC14): a flat ``"entries"`` list, or entries nested
    under ``"groups"[*]["entries"]``. Fails naming the top-level keys when
    neither layout is present."""
    if isinstance(doc, dict) and "entries" in doc:
        return list(doc["entries"])
    if isinstance(doc, dict) and "groups" in doc:
        entries = []
        for group in doc["groups"]:
            entries.extend(group.get("entries", []))
        return entries
    keys = sorted(doc.keys()) if isinstance(doc, dict) else []
    pytest.fail(
        "committed catalogue document has neither a top-level 'entries' "
        f"list nor 'groups'[*]['entries']; top-level keys found: {keys!r}"
    )


def _assert_valid_entries(entries) -> None:
    """AC13: every entry has a non-empty ``str`` ``path`` and a valid
    ``origin``, failing with a named entry rather than dropping it."""
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        origin = entry.get("origin") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path:
            pytest.fail(
                f"committed catalogue entry has no non-empty str 'path': "
                f"{entry!r}; item 103's catalogue_to_dict must emit 'path' "
                "and 'origin'."
            )
        if origin not in _VALID_ORIGINS:
            pytest.fail(
                f"committed catalogue entry {path!r} has invalid 'origin' "
                f"{origin!r} (expected one of {sorted(_VALID_ORIGINS)}); "
                "item 103's catalogue_to_dict must emit 'path' and 'origin'."
            )


def _module_ast() -> ast.Module:
    source = Path(__file__).read_text(encoding="utf-8")
    return ast.parse(source)


# =========================================================================== #
# Module-scoped fixtures (built once per session)
# =========================================================================== #


@pytest.fixture(scope="module")
def realised():
    return covered_paths()


@pytest.fixture(scope="module")
def documented():
    return documented_paths()


@pytest.fixture(scope="module")
def committed():
    return load_committed_catalogue()


@pytest.fixture(scope="module")
def committed_entries(committed):
    return iter_committed_entries(committed)


@pytest.fixture(scope="module")
def committed_paths(committed_entries):
    return frozenset(e["path"] for e in committed_entries)


@pytest.fixture(scope="module")
def committed_record_paths(committed_entries):
    return frozenset(
        e["path"] for e in committed_entries if e.get("origin") == "record"
    )


# =========================================================================== #
# AC1: the module is ungated
# =========================================================================== #


def test_ac1_no_importorskip_or_skip_markers():
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "importorskip":
                pytest.fail("found pytest.importorskip in module source")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                dumped = ast.dump(deco)
                if "skip" in dumped or "xfail" in dumped:
                    pytest.fail(f"found skip/xfail decorator: {dumped}")


def test_ac1_no_os_environ_conditional_skip():
    # An os.environ-conditional skip requires importing "os" in the first
    # place; this module never does (AST-checked, not a source-text scan, so
    # this test's own assertion text can never trip itself).
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "os"
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] != "os"


def test_ac1_imports_name_only_stdlib_pytest_or_segfacet():
    tree = _module_ast()
    banned = {"radiomics", "cupy", "docker", "subprocess"}
    allowed = {
        "__future__",
        "ast",
        "copy",
        "functools",
        "json",
        "re",
        "pathlib",
        "pytest",
        "segfacet",
    }
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names = [node.module.split(".")[0]]
        for name in names:
            assert name not in banned, name
            assert name in allowed, name


# =========================================================================== #
# AC2: the walk is imported, never reimplemented
# =========================================================================== #


def test_ac2_imports_iter_leaf_paths_and_iter_driver_records():
    tree = _module_ast()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "segfacet.catalogue":
            imported |= {alias.name for alias in node.names}
    assert {"iter_leaf_paths", "iter_driver_records"}.issubset(imported)


def test_ac2_no_function_recurses_over_a_record():
    tree = _module_ast()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        func_name = node.name
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == func_name
            ):
                pytest.fail(f"{func_name} appears to recurse over a record")


# =========================================================================== #
# AC3: no hand-typed path table
# =========================================================================== #


def test_ac3_no_hand_typed_path_table():
    tree = _module_ast()
    for node in ast.walk(tree):
        elts = None
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elts = node.elts
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset"
            and node.args
            and hasattr(node.args[0], "elts")
        ):
            elts = node.args[0].elts
        if elts is None:
            continue
        path_like = [
            e.value
            for e in elts
            if isinstance(e, ast.Constant)
            and isinstance(e.value, str)
            and ("." in e.value or "[]" in e.value)
        ]
        assert len(path_like) < 12, (
            f"literal collection with {len(path_like)} path-shaped strings found"
        )


# =========================================================================== #
# AC4: no absolute path literal
# =========================================================================== #


def test_ac4_no_absolute_path_literal():
    # Length-gated: a bare single-character "/" or "\\" delimiter literal
    # (as used by this very check's own startswith(...) calls) is not itself
    # an absolute path, so it must not trip this self-scan.
    tree = _module_ast()
    drive_re = re.compile(r"^[A-Za-z]:.")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) <= 1:
                continue
            assert not node.value.startswith("/"), node.value
            assert not node.value.startswith("\\"), node.value
            assert not drive_re.match(node.value), node.value


# =========================================================================== #
# AC5: no byte or hash comparison of a committed file
# =========================================================================== #


def test_ac5_no_hashlib_import():
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "hashlib"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "hashlib"


def test_ac5_no_read_bytes_call():
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "read_bytes":
            pytest.fail("found a .read_bytes() call in module source")


# =========================================================================== #
# AC6: covered_paths() is the union over the driver set, deterministic
# =========================================================================== #


def test_ac6_covered_paths_is_union_over_driver_records():
    union = set()
    for _driver_id, record in iter_driver_records():
        union |= iter_leaf_paths(record)
    assert covered_paths() == frozenset(union)


def test_ac6_covered_paths_deterministic_across_calls():
    assert covered_paths() == covered_paths()


# =========================================================================== #
# AC7: the check cannot pass vacuously
# =========================================================================== #


def test_ac7_iter_driver_records_yields_at_least_three_pairs():
    pairs = list(iter_driver_records())
    assert len(pairs) >= 3


def test_ac7_covered_paths_nonempty_and_contains_sentinels(realised):
    assert realised
    for path in _SENTINEL_PATHS:
        assert path in realised, path


def test_ac7_feature_docs_nonempty(documented):
    assert documented


# =========================================================================== #
# AC8: direction 1 -- undocumented realised feature
# =========================================================================== #


def test_ac8_direction1_clean_on_current_tree(realised, documented):
    assert realised - documented == set()


def test_ac8_direction1_reports_undocumented_path():
    message = drift_report(
        realised={"features_version", "per_label.{label}.geometry.zzz_injected"},
        documented={"features_version"},
        realised_label="realised by the record but absent from FEATURE_DOCS",
        documented_label=(
            "documented in FEATURE_DOCS but no longer produced by the record"
        ),
    )
    assert message is not None
    assert "per_label.{label}.geometry.zzz_injected" in message
    assert "realised" in message
    assert "absent from FEATURE_DOCS" in message


# =========================================================================== #
# AC9: direction 2 -- documented feature no longer produced
# =========================================================================== #


def test_ac9_direction2_clean_on_current_tree(realised, documented):
    assert documented - realised == set()


def test_ac9_direction2_reports_no_longer_produced_path():
    message = drift_report(
        realised={"features_version"},
        documented={"features_version", "relationships.gone_forever"},
        realised_label="realised by the record but absent from FEATURE_DOCS",
        documented_label=(
            "documented in FEATURE_DOCS but no longer produced by the record"
        ),
    )
    assert message is not None
    assert "relationships.gone_forever" in message
    assert "no longer produced" in message


# =========================================================================== #
# AC10: both directions reported together, sorted, complete
# =========================================================================== #


def test_ac10_both_directions_reported_sorted_and_complete():
    message = drift_report(
        realised={"z.path", "a.path", "shared"},
        documented={"shared", "m.path", "b.path"},
        realised_label="LABEL_A",
        documented_label="LABEL_B",
    )
    assert message is not None
    for path in ("z.path", "a.path", "m.path", "b.path"):
        assert path in message
    assert "LABEL_A" in message
    assert "LABEL_B" in message
    assert message.index("a.path") < message.index("z.path")
    assert message.index("b.path") < message.index("m.path")
    assert "..." not in message


def test_ac10_drift_report_none_not_empty_string_when_both_empty():
    result = drift_report(
        realised=set(), documented=set(), realised_label="A", documented_label="B"
    )
    assert result is None
    assert result != ""


# =========================================================================== #
# AC11: every drift message is actionable
# =========================================================================== #


def test_ac11_message_names_feature_docs_file_and_regen_command():
    message = drift_report(
        realised={"only.here"},
        documented=set(),
        realised_label="A",
        documented_label="B",
    )
    assert message is not None
    assert "src/segfacet/feature_docs.py" in message
    assert "python -m segfacet.catalogue" in message


# =========================================================================== #
# AC12: the strict production mechanism is exercised
# =========================================================================== #


def test_ac12_real_strict_build_succeeds_on_current_tree():
    message = strict_build_message(functools.partial(build_catalogue, strict=True))
    assert message is None, message


def test_ac12_feature_doc_missing_stub_reports_path():
    def _stub():
        raise FeatureDocMissing(
            "undocumented leaf path: per_label.{label}.geometry.zzz"
        )

    message = strict_build_message(_stub)
    assert message is not None
    assert "per_label.{label}.geometry.zzz" in message
    assert "FeatureDocMissing" in message


def test_ac12_catalogue_error_stub_reports_key():
    def _stub():
        raise CatalogueError("stale FEATURE_DOCS key: relationships.gone")

    message = strict_build_message(_stub)
    assert message is not None
    assert "relationships.gone" in message
    assert "CatalogueError" in message


def test_ac12_non_catalogue_error_propagates():
    def _stub():
        raise ValueError("not a catalogue error")

    with pytest.raises(ValueError):
        strict_build_message(_stub)


# =========================================================================== #
# AC13: the committed artifact exposes the fields the check needs
# =========================================================================== #


def test_ac13_committed_artifact_parses_as_json(committed):
    assert isinstance(committed, dict)


def test_ac13_every_entry_has_valid_path_and_origin(committed_entries):
    _assert_valid_entries(committed_entries)


def test_adv_unknown_origin_string_fails_naming_the_entry():
    doc = {"entries": [{"path": "some.path", "origin": "synthetic"}]}
    entries = iter_committed_entries(doc)
    with pytest.raises(pytest.fail.Exception) as excinfo:
        _assert_valid_entries(entries)
    assert "some.path" in str(excinfo.value)


def test_adv_missing_path_field_fails_naming_the_entry():
    doc = {"entries": [{"origin": "record"}]}
    entries = iter_committed_entries(doc)
    with pytest.raises(pytest.fail.Exception):
        _assert_valid_entries(entries)


# =========================================================================== #
# AC14: the artifact reader tolerates either serialisation layout
# =========================================================================== #


def test_ac14_flat_entries_layout():
    doc = {"entries": [{"path": "a"}, {"path": "b"}]}
    assert iter_committed_entries(doc) == [{"path": "a"}, {"path": "b"}]


def test_ac14_nested_groups_layout():
    doc = {
        "groups": [
            {"entries": [{"path": "a"}]},
            {"entries": [{"path": "b"}]},
        ]
    }
    assert iter_committed_entries(doc) == [{"path": "a"}, {"path": "b"}]


def test_ac14_empty_groups_returns_empty_list_no_crash():
    assert iter_committed_entries({"groups": []}) == []
    assert (
        iter_committed_entries({"groups": [{"entries": []}, {"entries": []}]}) == []
    )


def test_ac14_neither_layout_fails_naming_top_level_keys():
    with pytest.raises(pytest.fail.Exception) as excinfo:
        iter_committed_entries({"unexpected": 1, "another": 2})
    message = str(excinfo.value)
    assert "unexpected" in message
    assert "another" in message


# =========================================================================== #
# AC15: direction 3 -- stale committed artifact
# =========================================================================== #


def test_ac15_direction3_clean_on_current_tree(realised, committed_paths):
    assert realised - committed_paths == set()


def test_ac15_direction3_reports_stale_artifact_path():
    message = drift_report(
        realised={"a.path", "b.path"},
        documented={"a.path"},
        realised_label="realised by the record but missing from the committed artifact",
        documented_label="present in the committed artifact but no longer realised",
    )
    assert message is not None
    assert "b.path" in message
    assert "python -m segfacet.catalogue" in message


# =========================================================================== #
# AC16: direction 4 -- orphaned record-tier artifact entry
# =========================================================================== #


def test_ac16_direction4_clean_on_current_tree(realised, committed_record_paths):
    assert committed_record_paths - realised == set()


def test_ac16_direction4_reports_orphaned_record_tier_path():
    message = drift_report(
        realised={"a.path"},
        documented={"a.path", "orphan.path"},
        realised_label="realised by the record but missing from the committed artifact",
        documented_label=(
            "a record-tier entry in the committed artifact but no longer realised"
        ),
    )
    assert message is not None
    assert "orphan.path" in message
    assert "python -m segfacet.catalogue" in message


# =========================================================================== #
# AC17: no duplicate paths in the committed artifact
# =========================================================================== #


def test_ac17_no_duplicate_paths_in_committed_artifact(committed_entries):
    paths = [e["path"] for e in committed_entries]
    if len(paths) != len(set(paths)):
        seen: set = set()
        dupes: set = set()
        for path in paths:
            if path in seen:
                dupes.add(path)
            seen.add(path)
        pytest.fail(f"committed catalogue has duplicate path(s): {sorted(dupes)}")
    assert len(paths) == len(set(paths))


# =========================================================================== #
# AC18: the augmented-tier exemption is explicit and non-vacuous
# =========================================================================== #


def test_ac18_at_least_one_augmented_entry_exists(committed_entries):
    augmented = [e for e in committed_entries if e.get("origin") == "augmented"]
    assert augmented, "expected at least one committed entry with origin == 'augmented'"


def test_ac18_augmented_exemption_never_covers_a_record_tier_path(
    committed_entries, realised
):
    origin_by_path = {e["path"]: e.get("origin") for e in committed_entries}
    exempted = set(origin_by_path) - set(realised)
    for path in exempted:
        assert origin_by_path[path] == "augmented", (
            f"path {path!r} is absent from the realised set but is not "
            "origin == 'augmented' -- a record-tier path is being excused"
        )


# =========================================================================== #
# AC19: injected drift is detected end-to-end from real inputs
# =========================================================================== #


def test_ac19_injected_extra_path_detected_under_direction1(realised):
    injected_path = "per_label.{label}.geometry.zzz_drift_probe"
    local_realised = set(realised) | {injected_path}
    local_documented = set(documented_paths())
    message = drift_report(
        realised=local_realised,
        documented=local_documented,
        realised_label="realised by the record but absent from FEATURE_DOCS",
        documented_label=(
            "documented in FEATURE_DOCS but no longer produced by the record"
        ),
    )
    assert message is not None
    assert injected_path in message
    assert (local_realised - local_documented) == {injected_path}


def test_ac19_removed_real_path_detected_under_direction2(realised):
    local_documented = set(documented_paths())
    removed = sorted(local_documented)[0]
    local_realised = set(realised) - {removed}
    message = drift_report(
        realised=local_realised,
        documented=local_documented,
        realised_label="realised by the record but absent from FEATURE_DOCS",
        documented_label=(
            "documented in FEATURE_DOCS but no longer produced by the record"
        ),
    )
    assert message is not None
    assert removed in message
    assert (local_documented - local_realised) == {removed}


# =========================================================================== #
# AC20: nothing shipped is mutated
# =========================================================================== #


def test_ac20_feature_docs_snapshot_unchanged_after_checks_run():
    snapshot = copy.deepcopy(dict(FEATURE_DOCS))
    covered_paths()
    documented_paths()
    load_committed_catalogue()
    assert dict(FEATURE_DOCS) == snapshot


def test_ac20_first_driver_record_snapshot_unchanged_after_checks_run():
    _first_id, first_record = next(iter(iter_driver_records()))
    snapshot = copy.deepcopy(first_record)
    covered_paths()
    _second_id, record_again = next(iter(iter_driver_records()))
    assert record_again == snapshot


def test_ac20_feature_docs_rejects_item_assignment():
    with pytest.raises(TypeError):
        FEATURE_DOCS["new.injected.path"] = None


# =========================================================================== #
# AC21: the whole check is idempotent
# =========================================================================== #


def test_ac21_running_the_four_comparisons_twice_is_idempotent():
    def _run_once():
        r = covered_paths()
        d = documented_paths()
        primary = drift_report(
            realised=r,
            documented=d,
            realised_label="realised by the record but absent from FEATURE_DOCS",
            documented_label=(
                "documented in FEATURE_DOCS but no longer produced by the record"
            ),
        )
        doc = load_committed_catalogue()
        entries = iter_committed_entries(doc)
        c_record = frozenset(e["path"] for e in entries if e.get("origin") == "record")
        artifact_message = drift_report(
            realised=r,
            documented=c_record,
            realised_label=(
                "realised by the record but missing from the committed artifact"
            ),
            documented_label=(
                "a record-tier entry in the committed artifact but no longer realised"
            ),
        )
        return primary, artifact_message

    first = _run_once()
    second = _run_once()
    assert first == second


# =========================================================================== #
# Adversarial / edge cases not already covered above
# =========================================================================== #


def test_adv_drift_report_one_sided_shows_only_that_label():
    message = drift_report(
        realised={"only.one"},
        documented=set(),
        realised_label="LABEL_REALISED",
        documented_label="LABEL_DOCUMENTED",
    )
    assert message is not None
    assert "LABEL_REALISED" in message
    assert "LABEL_DOCUMENTED" not in message


def test_adv_drift_report_sorted_and_duplicate_free_regardless_of_input_order():
    scrambled_list = ["m.path", "z.path", "a.path", "a.path"]
    scrambled_set = {"a.path", "z.path", "m.path"}
    documented = set()
    message_from_list = drift_report(
        realised=scrambled_list,
        documented=documented,
        realised_label="L",
        documented_label="D",
    )
    message_from_set = drift_report(
        realised=scrambled_set,
        documented=documented,
        realised_label="L",
        documented_label="D",
    )
    assert message_from_list == message_from_set
    assert message_from_list.count("a.path") == 1


def test_adv_brace_and_bracket_paths_survive_verbatim():
    path = "per_label.{label}.geometry.zzz[]"
    message = drift_report(
        realised={path}, documented=set(), realised_label="L", documented_label="D"
    )
    assert path in message


def test_adv_load_committed_catalogue_missing_file_fails_with_named_message(tmp_path):
    missing = tmp_path / "feature_catalogue.generated.json"
    with pytest.raises(pytest.fail.Exception) as excinfo:
        load_committed_catalogue(missing)
    message = str(excinfo.value)
    assert str(missing) in message
    assert "python -m segfacet.catalogue" in message


def test_adv_covered_paths_twice_and_driver_records_unmutated():
    first_records = dict(iter_driver_records())
    snapshot = copy.deepcopy(first_records)
    covered_paths()
    covered_paths()
    second_records = dict(iter_driver_records())
    assert second_records == snapshot
