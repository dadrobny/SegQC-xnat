"""Tests for item 127 -- tolerance by construction for committed-artifact
comparisons.

Two independently testable surfaces:

1. ``segfacet.synth.golden.assert_matches_committed_artifact`` (AC1-AC10): a
   single assert-style helper that applies ``reports_close`` semantics
   (numeric leaves within tolerance; everything else exact) between a fresh
   structure and a committed one, and reports where they first diverge.
2. ``tests/committed_artifact_guard.py`` (AC12-AC22), a new builder-owned
   module carrying a structured allowlist and a static classifier
   (``classify_module`` / ``iter_violations``) that flags a byte-exact
   fresh-vs-committed comparison whose committed artifact is not allowlisted.

Both are new production/test-infrastructure surfaces this item's builder has
not yet written, so every test below that imports
``segfacet.synth.golden.assert_matches_committed_artifact`` or
``committed_artifact_guard`` is expected to fail (collection succeeds --
imports are local to each test function) until that work lands. AC11's
migration checks and the AC15/AC23 sweeps over the real ``tests/`` tree are
likewise red until the four call sites are migrated.

Every synthetic "offender" module used to exercise the classifier is built as
an in-memory source string (optionally written under ``tmp_path``) -- never
added to the real ``tests/`` tree, where item 126's own sweep would flag it
and where it would corrupt AC15's real-tree assertion.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
GITATTRIBUTES_PATH = REPO_ROOT / ".gitattributes"

# The four modules item 127 migrates to the new helper (spec table, AC11).
_MIGRATED_MODULES = (
    "test_063_reference_intensity.py",
    "test_081_reference_morphology.py",
    "test_120_leave_one_out_offset.py",
    "test_123_recalibrate_and_regenerate.py",
)

# The exact open-coded snippets item 127 deletes from each migrated module
# (as committed 2026-08-31 -- see the spec's table).
_OLD_SNIPPETS = (
    'committed = json.loads(default_artifact_path().read_text(encoding="utf-8"))\n    assert reports_close(regenerated, committed)',
    'committed = json.loads(default_artifact_path().read_text(encoding="utf-8"))\n    assert reports_close(fresh, committed)',
)


# =========================================================================== #
# Shared structure builders for the helper tests (AC1-AC10)
# =========================================================================== #


def _base_structure() -> dict:
    return {
        "features": {
            "a": 1.5,
            "flag": True,
            "name": "clean",
            "nested": {"x": 0.25, "y": None},
        },
        "levels": [1, 2, 3],
    }


def _write_json(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


# =========================================================================== #
# AC1: the helper exists and is exported
# =========================================================================== #


def test_ac1_helper_exists_in_module_all():
    from segfacet.synth import golden as golden_mod

    assert hasattr(golden_mod, "assert_matches_committed_artifact")
    assert "assert_matches_committed_artifact" in golden_mod.__all__


def test_ac1_helper_re_exported_from_segfacet_synth():
    import segfacet.synth as synth_pkg
    from segfacet.synth import golden as golden_mod

    assert hasattr(synth_pkg, "assert_matches_committed_artifact")
    assert "assert_matches_committed_artifact" in synth_pkg.__all__
    assert (
        synth_pkg.assert_matches_committed_artifact
        is golden_mod.assert_matches_committed_artifact
    )


# =========================================================================== #
# AC2: a 1-ULP float difference passes
# =========================================================================== #


def test_ac2_one_ulp_float_difference_passes(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = _base_structure()
    fresh["features"]["a"] = math.nextafter(fresh["features"]["a"], math.inf)
    assert fresh["features"]["a"] != committed["features"]["a"]

    assert_matches_committed_artifact(fresh, committed_path)  # must not raise


# =========================================================================== #
# AC3: a differing string fails
# =========================================================================== #


def test_ac3_differing_string_leaf_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = _base_structure()
    fresh["features"]["name"] = "dirty"

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


# =========================================================================== #
# AC4: a differing bool fails, and True is never 1.0
# =========================================================================== #


def test_ac4_differing_bool_leaf_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = _base_structure()
    fresh["features"]["flag"] = False

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


def test_ac4_true_vs_one_int_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed_path = _write_json(tmp_path / "committed.json", {"flag": True})
    with pytest.raises(AssertionError):
        assert_matches_committed_artifact({"flag": 1}, committed_path)


def test_ac4_true_vs_one_float_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed_path = _write_json(tmp_path / "committed.json", {"flag": True})
    with pytest.raises(AssertionError):
        assert_matches_committed_artifact({"flag": 1.0}, committed_path)


# =========================================================================== #
# AC5: a missing or extra key fails
# =========================================================================== #


def test_ac5_missing_key_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = _base_structure()
    del fresh["features"]["name"]

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


def test_ac5_extra_key_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = _base_structure()
    fresh["features"]["extra"] = "surprise"

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


# =========================================================================== #
# AC6: list order is exact
# =========================================================================== #


def test_ac6_permuted_list_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = _base_structure()
    fresh["levels"] = list(reversed(fresh["levels"]))
    assert fresh["levels"] != committed["levels"]

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


# =========================================================================== #
# AC7: the fresh side accepts a path or a parsed object
# =========================================================================== #


def test_ac7_fresh_path_and_parsed_object_agree_when_matching(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh_path = _write_json(tmp_path / "fresh.json", committed)
    fresh_obj = json.loads(fresh_path.read_text(encoding="utf-8"))

    assert_matches_committed_artifact(fresh_path, committed_path)  # Path
    assert_matches_committed_artifact(str(fresh_path), committed_path)  # str
    assert_matches_committed_artifact(fresh_obj, committed_path)  # parsed dict


def test_ac7_fresh_path_and_parsed_object_agree_when_mismatched(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = _base_structure()
    committed_path = _write_json(tmp_path / "committed.json", committed)

    mismatched = _base_structure()
    mismatched["features"]["name"] = "dirty"
    mismatched_path = _write_json(tmp_path / "mismatched.json", mismatched)

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(mismatched_path, committed_path)
    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(mismatched, committed_path)


# =========================================================================== #
# AC8: a missing committed artifact fails loudly
# =========================================================================== #


def test_ac8_missing_committed_artifact_raises_file_not_found_naming_path(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    missing = tmp_path / "does_not_exist.json"
    assert not missing.exists()

    with pytest.raises(FileNotFoundError) as excinfo:
        assert_matches_committed_artifact({"a": 1}, missing)

    assert str(missing) in str(excinfo.value)
    assert not missing.exists(), "the helper must not create the committed file"


def test_ac8_missing_committed_artifact_does_not_skip(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    missing = tmp_path / "does_not_exist.json"
    try:
        assert_matches_committed_artifact({"a": 1}, missing)
    except pytest.skip.Exception as exc:  # noqa: BLE001 - see docstring
        pytest.fail(f"missing committed artifact causes a skip, not a failure: {exc}")
    except FileNotFoundError:
        pass
    else:
        pytest.fail("missing committed artifact silently passed instead of failing")


# =========================================================================== #
# AC9: the failure message locates the difference
# =========================================================================== #


def test_ac9_failure_message_names_path_and_diverging_values(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = {"features": {"a": 1.0, "b": "left-value"}}
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = {"features": {"a": 1.0, "b": "right-value"}}

    with pytest.raises(AssertionError) as excinfo:
        assert_matches_committed_artifact(fresh, committed_path)

    message = str(excinfo.value)
    assert str(committed_path) in message, "message does not name the committed path"
    assert "b" in message, "message does not point at the diverging leaf's key"
    assert "left-value" in message, "message omits the committed value"
    assert "right-value" in message, "message omits the fresh value"


# =========================================================================== #
# AC10: the helper's verdict agrees with reports_close
# =========================================================================== #


def _ac10_case_pairs():
    def base():
        return _base_structure()

    ulp_a = base()
    ulp_a["features"]["a"] = math.nextafter(ulp_a["features"]["a"], math.inf)

    string_a = base()
    string_a["features"]["name"] = "dirty"

    bool_a = base()
    bool_a["features"]["flag"] = False

    bool_vs_int_a = base()
    bool_vs_int_a["features"]["flag"] = 1

    bool_vs_float_a = base()
    bool_vs_float_a["features"]["flag"] = 1.0

    int_vs_float_a = {"a": 3}
    int_vs_float_b = {"a": 3.0}

    missing_key_a = base()
    del missing_key_a["features"]["name"]

    extra_key_a = base()
    extra_key_a["features"]["extra"] = "surprise"

    permuted_list_a = base()
    permuted_list_a["levels"] = list(reversed(permuted_list_a["levels"]))

    nested_permutation_a = {"items": [{"id": 1}, {"id": 2}]}
    nested_permutation_b = {"items": [{"id": 2}, {"id": 1}]}

    return [
        ("identical", base(), base()),
        ("one-ulp-float", ulp_a, base()),
        ("differing-string", string_a, base()),
        ("differing-bool", bool_a, base()),
        ("bool-vs-int-one", bool_vs_int_a, base()),
        ("bool-vs-float-one", bool_vs_float_a, base()),
        ("int-vs-float-equal-value", int_vs_float_a, int_vs_float_b),
        ("missing-key", missing_key_a, base()),
        ("extra-key", extra_key_a, base()),
        ("permuted-list", permuted_list_a, base()),
        ("nested-list-of-dict-permutation", nested_permutation_a, nested_permutation_b),
        ("nan-both-sides", {"value": float("nan")}, {"value": float("nan")}),
        ("infinity-both-sides", {"value": float("inf")}, {"value": float("inf")}),
        ("empty-dict", {}, {}),
        ("empty-list", {"items": []}, {"items": []}),
        ("nested-empty-list", {"a": []}, {"a": []}),
    ]


@pytest.mark.parametrize("case_id, fresh, committed", _ac10_case_pairs())
def test_ac10_helper_agrees_with_reports_close(tmp_path, case_id, fresh, committed):
    from segfacet.synth.golden import assert_matches_committed_artifact, reports_close

    committed_path = _write_json(tmp_path / f"{case_id}.json", committed)
    expect_mismatch = not reports_close(fresh, committed)

    if expect_mismatch:
        with pytest.raises(AssertionError):
            assert_matches_committed_artifact(fresh, committed_path)
    else:
        assert_matches_committed_artifact(fresh, committed_path)  # must not raise


# =========================================================================== #
# AC11: the four existing comparisons go through the helper
# =========================================================================== #


@pytest.mark.parametrize("module_name", _MIGRATED_MODULES)
def test_ac11_migrated_module_calls_the_helper(module_name):
    source = (TESTS_DIR / module_name).read_text(encoding="utf-8")
    assert "assert_matches_committed_artifact(" in source, (
        f"{module_name} does not call assert_matches_committed_artifact for "
        "its fresh-vs-committed comparison"
    )


@pytest.mark.parametrize("module_name", _MIGRATED_MODULES)
def test_ac11_migrated_module_no_longer_open_codes_the_comparison(module_name):
    source = (TESTS_DIR / module_name).read_text(encoding="utf-8")
    for snippet in _OLD_SNIPPETS:
        assert snippet not in source, (
            f"{module_name} still contains the open-coded fresh-vs-committed "
            "reports_close comparison this item migrates"
        )


def test_ac11_no_module_calls_reports_close_directly_on_committed_data():
    """Sweep every test module under ``tests/`` for the shape this item
    retires: a function that reads ``default_artifact_path()`` (the only
    committed artifact this item's four call sites compare against) and also
    calls ``reports_close`` -- the open-coded fresh-vs-committed idiom. A
    fresh-vs-fresh ``reports_close`` call untouched by this item never reads
    ``default_artifact_path()``, so it never trips this sweep."""
    import ast

    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        source = path.read_text(encoding="utf-8")
        if "default_artifact_path()" not in source or "reports_close(" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = ast.get_source_segment(source, node)
            if segment is None:
                continue
            if "default_artifact_path()" in segment and "reports_close(" in segment:
                offenders.append(f"{path.name}::{node.name}")

    assert not offenders, (
        "these functions still call reports_close directly on a structure "
        f"loaded from a committed artifact instead of using "
        f"assert_matches_committed_artifact: {offenders}"
    )


# =========================================================================== #
# Guard module: AC12-AC22 (tests/committed_artifact_guard.py)
# =========================================================================== #


def test_ac12_allowlist_entries_are_fully_populated():
    import committed_artifact_guard as guard

    assert guard.ALLOWLIST, "allowlist is empty"
    for entry in guard.ALLOWLIST:
        assert entry.path, f"allowlist entry has an empty path/glob: {entry!r}"
        assert entry.ground, f"allowlist entry has an empty ground: {entry!r}"
        assert entry.ground in guard.GROUNDS, (
            f"allowlist entry's ground {entry.ground!r} is not in the closed "
            f"vocabulary {guard.GROUNDS!r}"
        )
        assert entry.reason, f"allowlist entry has an empty reason: {entry!r}"
        assert "\n" not in entry.reason, (
            f"allowlist entry's reason is not single-line: {entry!r}"
        )


def test_ac12_ground_vocabulary_is_closed_at_five_members():
    import committed_artifact_guard as guard

    assert set(guard.GROUNDS) == {
        "exact-parameter-floats",
        "emission-clamped",
        "hand-written-literals",
        "binary-fixture",
        "integrity-pin",
    }


def test_ac13_no_stale_allowlist_entry():
    import committed_artifact_guard as guard

    for entry in guard.ALLOWLIST:
        matches = list(REPO_ROOT.glob(entry.path))
        assert matches, (
            f"allowlist entry {entry.path!r} matches no file in the working tree"
        )


def test_ac14_every_allowlisted_path_is_line_ending_pinned():
    import committed_artifact_guard as guard

    attrs_lines = [
        line.strip()
        for line in GITATTRIBUTES_PATH.read_text(encoding="utf-8").splitlines()
    ]
    unpinned = [
        entry.path
        for entry in guard.ALLOWLIST
        if not any(
            line.startswith(entry.path) and ("eol=lf" in line or "binary" in line)
            for line in attrs_lines
        )
    ]
    assert not unpinned, (
        f"these allowlist entries have no text eol=lf / binary .gitattributes "
        f"pin: {unpinned}"
    )


def test_ac15_classifier_reports_zero_violations_on_tests_tree():
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(TESTS_DIR))
    assert not violations, guard.violation_message(violations)


def test_ac16_off_allowlist_comparison_is_classified_as_violation():
    import committed_artifact_guard as guard

    source = (
        "from pathlib import Path\n"
        "\n"
        "def test_offender(tmp_path):\n"
        '    dest = tmp_path / "regen.json"\n'
        '    dest.write_bytes(b"{}")\n'
        '    committed = Path("src/segfacet/reference/reference_default.json")\n'
        "    assert dest.read_bytes() == committed.read_bytes()\n"
    )
    violations = guard.classify_module(source, "tests/test_zz_synthetic_offender.py")
    assert violations, "expected a violation for the off-allowlist comparison"


def test_ac17_violation_message_names_the_helper():
    import committed_artifact_guard as guard

    source = (
        "from pathlib import Path\n"
        "\n"
        "def test_offender(tmp_path):\n"
        '    dest = tmp_path / "regen.json"\n'
        '    dest.write_bytes(b"{}")\n'
        '    committed = Path("src/segfacet/reference/reference_default.json")\n'
        "    assert dest.read_bytes() == committed.read_bytes()\n"
    )
    violations = guard.classify_module(source, "tests/test_zz_synthetic_offender.py")
    message = guard.violation_message(violations)
    assert "assert_matches_committed_artifact" in message


def test_ac18_unchanged_fence_is_not_a_violation():
    import committed_artifact_guard as guard

    source = (
        "from pathlib import Path\n"
        "\n"
        "def test_fence():\n"
        '    p = Path("src/segfacet/reference/reference_default.json")\n'
        "    before = p.read_bytes()\n"
        "    # ... some unrelated operation happens here ...\n"
        "    assert p.read_bytes() == before\n"
    )
    violations = guard.classify_module(source, "tests/test_zz_fence.py")
    assert not violations, (
        "an unchanged-fence comparing the same committed path to itself "
        f"twice within one run must not be a violation: {violations}"
    )


def test_ac19_fresh_vs_fresh_comparison_is_not_a_violation():
    import committed_artifact_guard as guard

    source = (
        "def test_fresh(tmp_path):\n"
        '    a = tmp_path / "a.json"\n'
        '    b = tmp_path / "b.json"\n'
        '    a.write_bytes(b"{}")\n'
        '    b.write_bytes(b"{}")\n'
        "    assert a.read_bytes() == b.read_bytes()\n"
    )
    violations = guard.classify_module(source, "tests/test_zz_fresh.py")
    assert not violations, (
        f"comparing two files written under tmp_path within one run must "
        f"not be a violation: {violations}"
    )


def test_ac20_reference_default_excluded_from_allowlist():
    import committed_artifact_guard as guard

    paths = [entry.path for entry in guard.ALLOWLIST]
    assert "src/segfacet/reference/reference_default.json" not in paths


def test_ac20_guard_records_reference_default_exclusion_reason():
    import committed_artifact_guard as guard

    docstring = guard.__doc__ or ""
    assert "reference_default.json" in docstring, (
        "guard module docstring does not name reference_default.json's "
        "exclusion"
    )


def test_ac21_reference_verse_v1_allowlisted_as_integrity_pin_by_path():
    import committed_artifact_guard as guard

    matching = [
        entry
        for entry in guard.ALLOWLIST
        if entry.path == "src/segfacet/reference/reference_verse_v1.json"
    ]
    assert len(matching) == 1, (
        "reference_verse_v1.json must be allowlisted by its exact fixture "
        "path, not by the name or location of the test that consumes it"
    )
    assert matching[0].ground == "integrity-pin"


def test_ac22_guard_records_the_emission_clamp_rule():
    import committed_artifact_guard as guard

    docstring = guard.__doc__ or ""
    assert "segfacet.observed_range.emission_range" in docstring


def test_ac22_guard_records_the_consumer_survey_rule():
    import committed_artifact_guard as guard

    docstring = guard.__doc__ or ""
    assert "grep -l build_and_write_default tests/" in docstring


# =========================================================================== #
# AC23: item 111's .gitattributes survey still holds
# =========================================================================== #


def test_ac23_known_byte_exact_fixture_families_unchanged():
    import test_111_golden_guard as mod111

    assert mod111._KNOWN_BYTE_EXACT_FIXTURE_FAMILIES == (
        "tests/corpus/manifest.json",
        "tests/corpus/intensity/manifest.json",
        "tests/corpus/094_pre_migration_snapshot.json",
        "src/segfacet/reference/reference_default.json",
        "docs/aide/feature_catalogue.generated.json",
        "docs/aide/feature_catalogue.generated.md",
        "docs/aide/golden-decision-table.md",
        "tests/golden/*.json",
    )


def test_ac23_survey_test_still_passes():
    import test_111_golden_guard as mod111

    mod111.test_ac4_survey_every_byte_exact_fixture_family_is_pinned()  # must not raise


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_edge_float_difference_within_tolerance_passes(tmp_path):
    from segfacet.synth.golden import (
        GOLDEN_ABS_TOL,
        GOLDEN_REL_TOL,
        assert_matches_committed_artifact,
    )

    committed_value = 10.0
    committed_path = _write_json(tmp_path / "committed.json", {"v": committed_value})

    drift = committed_value * GOLDEN_REL_TOL * 0.1
    fresh_value = committed_value + drift
    assert fresh_value != committed_value
    assert abs(fresh_value - committed_value) < max(
        GOLDEN_REL_TOL * committed_value, GOLDEN_ABS_TOL
    )

    assert_matches_committed_artifact({"v": fresh_value}, committed_path)  # not raise


def test_edge_float_difference_beyond_tolerance_fails(tmp_path):
    from segfacet.synth.golden import GOLDEN_REL_TOL, assert_matches_committed_artifact

    committed_value = 10.0
    committed_path = _write_json(tmp_path / "committed.json", {"v": committed_value})

    fresh_value = committed_value * (1 + GOLDEN_REL_TOL * 1_000_000)
    assert abs(fresh_value - committed_value) > GOLDEN_REL_TOL * committed_value

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact({"v": fresh_value}, committed_path)


def test_edge_nan_leaf_both_sides_is_not_treated_as_equal(tmp_path):
    """NaN is never close to NaN under math.isclose, so reports_close is
    False for a NaN leaf on both sides and the helper must agree (AC10)."""
    from segfacet.synth.golden import assert_matches_committed_artifact, reports_close

    committed = {"value": float("nan")}
    committed_path = _write_json(tmp_path / "committed.json", committed)
    fresh = {"value": float("nan")}

    assert reports_close(fresh, committed) is False
    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


def test_edge_nested_list_of_dict_permutation_fails(tmp_path):
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed = {"cases": [{"id": "a", "score": 1}, {"id": "b", "score": 2}]}
    committed_path = _write_json(tmp_path / "committed.json", committed)

    fresh = {"cases": [{"id": "b", "score": 2}, {"id": "a", "score": 1}]}

    with pytest.raises(AssertionError):
        assert_matches_committed_artifact(fresh, committed_path)


def test_edge_committed_artifact_with_crlf_still_compares_correctly(tmp_path):
    """A committed file with CRLF line endings must still be read and
    compared correctly -- the helper reads UTF-8 text and parses JSON, which
    is line-ending agnostic."""
    from segfacet.synth.golden import assert_matches_committed_artifact

    committed_path = tmp_path / "committed.json"
    committed_path.write_bytes(b'{\r\n  "a": 1,\r\n  "b": "clean"\r\n}\r\n')

    assert_matches_committed_artifact({"a": 1, "b": "clean"}, committed_path)  # ok
    with pytest.raises(AssertionError):
        assert_matches_committed_artifact({"a": 1, "b": "dirty"}, committed_path)


def test_edge_synthetic_module_with_no_valid_python_reports_no_violation():
    import committed_artifact_guard as guard

    violations = guard.classify_module("not valid python ::::", "tests/test_zz_bad.py")
    assert not violations


def test_edge_empty_synthetic_module_reports_no_violation():
    import committed_artifact_guard as guard

    violations = guard.classify_module("", "tests/test_zz_empty.py")
    assert not violations


def test_edge_unresolvable_operands_are_skipped_in_silence():
    """A comparison whose operands are entirely unresolvable (a loop
    variable, a function argument) must not be classified as a violation --
    this pins the documented precise-not-exhaustive contract."""
    import committed_artifact_guard as guard

    source = (
        "def test_loop(paths, tmp_path):\n"
        "    for p in paths:\n"
        "        fresh = tmp_path / p.name\n"
        "        assert fresh.read_bytes() == p.read_bytes()\n"
    )
    violations = guard.classify_module(source, "tests/test_zz_unresolvable.py")
    assert not violations


def test_edge_offender_via_alias_import_against_allowlisted_path_not_flagged(tmp_path):
    """A byte comparison against an *allowlisted* committed path, resolved
    through a locally aliased Path constant, must not be flagged -- exercises
    both the local-variable-alias resolution rule and the allowlist lookup
    together, via the real ``iter_violations`` sweep over a directory under
    ``tmp_path`` (never the real tests/ tree)."""
    import committed_artifact_guard as guard

    offender_source = (
        "from pathlib import Path\n"
        "\n"
        "_REPO_ROOT = Path(__file__).resolve().parent.parent.parent\n"
        "\n"
        "def test_offender(tmp_path):\n"
        '    manifest = _REPO_ROOT / "tests" / "corpus" / "manifest.json"\n'
        "    alias = manifest\n"
        '    fresh = tmp_path / "fresh.json"\n'
        '    fresh.write_bytes(b"{}")\n'
        "    assert fresh.read_bytes() == alias.read_bytes()\n"
    )
    offender_path = tmp_path / "test_zz_synthetic_alias_offender.py"
    offender_path.write_text(offender_source, encoding="utf-8")

    violations = list(guard.iter_violations(tmp_path))
    assert not violations, (
        "a byte comparison against an allowlisted path, reached through a "
        f"local alias, must not be a violation: {violations}"
    )


def test_edge_classifier_is_deterministic_across_repeated_calls():
    import committed_artifact_guard as guard

    source = (
        "from pathlib import Path\n"
        "\n"
        "def test_offender(tmp_path):\n"
        '    dest = tmp_path / "regen.json"\n'
        '    dest.write_bytes(b"{}")\n'
        '    committed = Path("src/segfacet/reference/reference_default.json")\n'
        "    assert dest.read_bytes() == committed.read_bytes()\n"
    )
    first = guard.classify_module(source, "tests/test_zz_synthetic_offender.py")
    second = guard.classify_module(source, "tests/test_zz_synthetic_offender.py")
    assert first == second
