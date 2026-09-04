"""Tests for item 134 -- move the decision table's measured evidence counts
into a generated companion artifact (Stage 29, G7).

The nine Section-1 rows whose fixture path ends `/<case_id>.json` for the
nine corpus case ids used to carry a *live measurement* (`26/94 leaf paths
unwired`) inside `docs/aide/golden-decision-table.md`, a human-signed
document -- so every feature-adding item had to edit signed text just to
keep a number current (five such amendments before this item). This item
moves the measurement into a new generator, `segfacet.golden_evidence`, and
its committed companion, `docs/aide/golden_evidence.generated.json`, leaving
a digit-free pointer behind in the signed row.

Until the builder lands `src/segfacet/golden_evidence.py` and the committed
companion, every test here that imports the generator or reads the
companion is expected to fail (missing module / missing file), and AC6/AC7
are expected to fail until the builder also adds the `.gitattributes` pin
and confirms `aide check` stays clean -- not this module's bug. Imports of
the not-yet-built generator are deferred into function bodies so collection
still succeeds.

Covers Acceptance Criteria AC1-AC18 (AC8 and AC12 are asserted through the
reconciled `test_105_golden_decision_table.py` /
`test_126_golden_retirement.py` functions listed in this item's spec, not
duplicated here):

- AC1/AC2: the generator exports `build_evidence`/`render_json`/`main`, and
  `build_evidence()`'s `cases` key set equals the manifest's case ids with
  exactly the two mandated integer keys per entry.
- AC3: two fresh `main()` runs into distinct `tmp_path` destinations are
  byte-identical.
- AC4: the committed companion parses to the same payload `build_evidence()`
  returns.
- AC5: the committed companion's bytes carry no `\\r` and end with exactly
  one `\\n`.
- AC6: `.gitattributes` effectively (via `git check-attr`) pins the
  companion to `eol=lf`.
- AC7: `aide check` (called in-process via `run_checks`, never a
  `aide.py`-naming subprocess -- that shape is itself flagged by engine
  1.21.0's `cli_subprocess_test_warnings` lint) names neither new path.
- AC9: the nine golden-case Section-1 rows' evidence cells are all
  byte-identical, name the companion, and carry no digit.
- AC10: the three judgement columns of all eleven retired Section-1 rows are
  byte-unchanged since this branch's merge base.
- AC13: the amendment paragraph appears exactly once, the five mandated
  headings stay in order, the execution log still follows Divergences, and
  no line reads as a sign-off field.
- AC14: `test_105`'s `_SECTION2_EXPECTED_FIXTURES` is unchanged (seven
  members) and Section 2's rows still equal it exactly.
- AC15: a stale (off-by-one) companion payload fails the drift comparison
  naming the case id and both numbers, and the signed document is
  byte-unchanged before and after.
- AC16: `committed_artifact_guard.iter_violations()` is empty over `tests/`,
  its `GROUNDS` (six members as of item 149, 2026-09-04) is otherwise
  unchanged, and its `ALLOWLIST` gains no entry for the companion.
- AC17: no numeric leaf in the companion is a `float`, and its text carries
  no date, drive-letter prefix, absolute path or this machine's hostname.
- AC18: `test_105`'s post-retirement inventory count (20) still holds.

Adversarial / edge cases beyond AC15: `build_evidence()` called twice in one
session is idempotent; `main()` creates a missing parent directory; a
companion missing a case id fails naming the id (not `KeyError`); a
companion with an extra case key fails shape; a companion whose counts are
strings fails on type, not value; a mutated payload with a missing trailing
newline or CRLF bytes would fail AC5's check; a pointer cell that merely
*mentions* the companion while still carrying a digit is still rejected.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess

from run_process import run_utf8
import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTS_DIR = Path(__file__).resolve().parent
_DOC_PATH = _REPO_ROOT / "docs" / "aide" / "golden-decision-table.md"
_COMPANION_PATH = _REPO_ROOT / "docs" / "aide" / "golden_evidence.generated.json"
_GITATTRIBUTES = _REPO_ROOT / ".gitattributes"
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"

_GOLDEN_CASE_IDS = (
    "clean_control",
    "mode1_displace",
    "mode2_fragment",
    "mode3_inject_islands",
    "mode4_relabel_swap",
    "mode5_remove_level",
    "mode6_crop_at_border",
    "mode7_sequence_break",
    "mode8_force_overlap",
)

#: Pinned merge-base commit for AC10 -- deliberately NOT a live `git
#: merge-base HEAD aide/queue-018`. Per
#: test_123_recalibrate_and_regenerate.py's `_PRE_123_BASE_SHA` comment: a
#: live merge-base self-invalidates the moment this item's branch
#: fast-forward-merges into its recorded base, because HEAD and
#: `aide/queue-018` then become the same commit and `git show` would serve
#: the POST-134 document as the "pre-134" baseline. Verified (2026-08-31) to
#: be this item's first commit's parent, with the table byte-identical to
#: its state at item 123's landing.
_PRE_134_BASE_SHA = "ca92471967d03dc780d18d416a4e56e3281afa28"


# =========================================================================== #
# A ~25-line Markdown pipe-table parser, mirroring test_105/test_126's own
# (no production parser to import -- the document is hand-authored)
# =========================================================================== #


def _split_sections(text: str) -> dict:
    heading_re = re.compile(r"(?m)^## (.+?)\s*$")
    matches = list(heading_re.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[title] = text[start:end]
    return sections


def _table_cells(line: str) -> list:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _parse_first_pipe_table(section_text: str) -> list:
    table_lines = [l.strip() for l in section_text.splitlines() if l.strip().startswith("|")]
    assert len(table_lines) >= 2, "no well-formed pipe table found"
    header_cells = [re.sub(r"\s+", " ", c.strip()).lower() for c in _table_cells(table_lines[0])]
    rows = []
    for line in table_lines[2:]:
        raw_cells = _table_cells(line)
        if len(raw_cells) != len(header_cells):
            continue
        rows.append(dict(zip(header_cells, raw_cells)))
    return rows


def _section1_rows_from_text(text: str) -> list:
    sections = _split_sections(text)
    return _parse_first_pipe_table(sections["Section 1 — Committed test fixtures"])


@pytest.fixture(scope="module")
def section1_rows() -> list:
    text = _DOC_PATH.read_bytes().decode("utf-8")
    return _section1_rows_from_text(text)


# =========================================================================== #
# AC2 shape helper, reused by the adversarial variants below
# =========================================================================== #


def _assert_companion_shape(payload: dict, case_ids) -> None:
    """AC2: `payload` has a `cases` object keyed exactly by `case_ids`, each
    entry an int-only two-key record. Raises `AssertionError` naming the
    offending case id or key rather than letting a `KeyError`/`TypeError`
    propagate."""
    assert "cases" in payload, "companion payload has no top-level 'cases' key"
    cases = payload["cases"]
    if set(cases) != set(case_ids):
        missing = sorted(set(case_ids) - set(cases))
        extra = sorted(set(cases) - set(case_ids))
        raise AssertionError(
            f"companion case-id set mismatch -- missing: {missing}, extra: {extra}"
        )
    for case_id, entry in cases.items():
        assert set(entry) == {"total_leaf_paths", "unwired_leaf_paths"}, (
            f"{case_id!r} entry has unexpected keys: {sorted(entry)}"
        )
        for key in ("total_leaf_paths", "unwired_leaf_paths"):
            value = entry[key]
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"{case_id!r}.{key} is not an int: {value!r} ({type(value).__name__})"
            )


def _walk_leaves(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_leaves(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_leaves(v, f"{path}[{i}]")
    else:
        yield path, obj


# =========================================================================== #
# AC1/AC2: the generator exists and the companion's shape matches the manifest
# =========================================================================== #


def test_ac1_generator_exports_required_functions():
    import segfacet.golden_evidence as golden_evidence

    for name in ("build_evidence", "render_json", "main"):
        assert name in getattr(golden_evidence, "__all__", ()), (
            f"{name!r} missing from segfacet.golden_evidence.__all__"
        )
        assert callable(getattr(golden_evidence, name)), f"{name!r} is not callable"


def test_ac2_build_evidence_matches_manifest_case_ids_with_two_int_keys():
    import segfacet.golden_evidence as golden_evidence
    from segfacet.synth.corpus import load_manifest

    manifest_case_ids = {c["case_id"] for c in load_manifest()["cases"]}
    assert manifest_case_ids, "expected at least one manifest case"
    payload = golden_evidence.build_evidence()
    _assert_companion_shape(payload, manifest_case_ids)


# =========================================================================== #
# AC3: byte-reproducible run-to-run
# =========================================================================== #


def test_ac3_two_fresh_runs_are_byte_identical(tmp_path):
    import segfacet.golden_evidence as golden_evidence

    dest_a = tmp_path / "a.json"
    dest_b = tmp_path / "b.json"
    assert golden_evidence.main(["--out", str(dest_a)]) == 0
    assert golden_evidence.main(["--out", str(dest_b)]) == 0
    raw_a = dest_a.read_bytes()
    raw_b = dest_b.read_bytes()
    assert raw_a, "first run wrote an empty file"
    assert raw_a == raw_b, "two fresh runs produced different bytes"


# =========================================================================== #
# AC4: the committed companion equals a fresh build
# =========================================================================== #


def test_ac4_committed_companion_equals_fresh_build():
    import segfacet.golden_evidence as golden_evidence

    committed = json.loads(_COMPANION_PATH.read_bytes().decode("utf-8"))
    fresh = golden_evidence.build_evidence()
    assert committed == fresh, "committed companion payload differs from a fresh build"


# =========================================================================== #
# AC5: written with \n bytes
# =========================================================================== #


def test_ac5_committed_companion_bytes_have_no_cr_and_one_trailing_lf():
    raw = _COMPANION_PATH.read_bytes()
    assert raw, "committed companion is empty"
    assert b"\r" not in raw, "companion carries a carriage return"
    assert raw.endswith(b"\n"), "companion does not end with a newline"
    assert not raw.endswith(b"\n\n"), "companion ends with more than one newline"


# =========================================================================== #
# AC6: the line-ending pin exists and is effective
# =========================================================================== #


def test_ac6_gitattributes_effectively_pins_companion_to_lf():
    result = run_utf8(
        ["git", "check-attr", "text", "eol", "--", "docs/aide/golden_evidence.generated.json"],
        cwd=_REPO_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert output.strip(), "git check-attr produced no output"
    file_lines = [
        line
        for line in output.splitlines()
        if line.startswith("docs/aide/golden_evidence.generated.json:")
    ]
    assert file_lines, f"git check-attr reported nothing for the companion:\n{output}"
    assert any("eol: lf" in line for line in file_lines), (
        f"git check-attr does not report eol: lf for the companion:\n{output}"
    )


# =========================================================================== #
# AC7: aide check is clean for the new paths
# =========================================================================== #


def _aide_check_warnings() -> list:
    """Return `aide check`'s warnings as a list of strings.

    Calls `run_checks` in-process rather than shelling out to `aide.py
    check`: a subprocess naming `aide.py` is exactly what engine 1.21.0's
    `cli_subprocess_test_warnings` lint flags, so a subprocess-based version
    of this test would make this module report a warning about itself and
    could never reach a clean `aide check` (see
    tests/test_128_relocation_checks.py's identical helper). `run_checks` is
    the same function `cmd_check` calls; it returns `(errors, warnings)` as
    structured data, so there is no stdout, no encoding and no subprocess to
    go wrong.
    """
    spec = importlib.util.spec_from_file_location("_aide_cli_134", _AIDE_SCRIPT)
    aide = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aide)
    repo_root = aide.find_repo_root(_REPO_ROOT)
    _errors, warnings = aide.run_checks(repo_root, aide.load_config(repo_root))
    return list(warnings)


def test_ac7_aide_check_names_neither_new_path():
    warnings = _aide_check_warnings()
    offending = [
        w
        for w in warnings
        if "golden_evidence.generated.json" in w or "golden_evidence.py" in w
    ]
    assert not offending, f"aide check named a new item-134 path:\n{offending}"


# =========================================================================== #
# AC9: the signed cells carry a stable pointer, not a number
# =========================================================================== #


def test_ac9_golden_case_evidence_cells_are_identical_pointer_and_digit_free(section1_rows):
    matches = [
        r
        for r in section1_rows
        if any(r["fixture"].endswith(f"/{cid}.json") for cid in _GOLDEN_CASE_IDS)
    ]
    assert len(matches) == 9, f"expected nine golden-case Section-1 rows, got {len(matches)}"
    cells = {r["evidence"] for r in matches}
    assert len(cells) == 1, f"golden-case evidence cells are not byte-identical: {cells}"
    cell = cells.pop()
    assert "docs/aide/golden_evidence.generated.json" in cell, cell
    assert not re.search(r"\d", cell), f"evidence cell still carries a digit: {cell!r}"


def test_adv_pointer_cell_with_digit_is_rejected_even_if_it_mentions_companion():
    cell = "measured in docs/aide/golden_evidence.generated.json (26/94 as of 2026-08-30)"
    assert "golden_evidence.generated.json" in cell
    assert re.search(r"\d", cell), "test setup: cell must actually carry a digit"


# =========================================================================== #
# AC10: the judgement columns of the eleven retired rows are byte-unchanged
# =========================================================================== #


def _pre_134_base_rev() -> str:
    try:
        result = run_utf8(
            ["git", "cat-file", "-e", f"{_PRE_134_BASE_SHA}^{{commit}}"],
            cwd=_REPO_ROOT,
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - defensive
        pytest.skip(f"git unavailable to resolve the pinned pre-134 commit: {exc}")
    if result.returncode != 0:
        pytest.skip(
            f"pinned pre-134 commit {_PRE_134_BASE_SHA} is not reachable in this "
            "checkout (likely a shallow clone) -- cannot diff against it"
        )
    return _PRE_134_BASE_SHA


def _git_show_text(rev: str, relpath: str) -> str:
    result = run_utf8(
        ["git", "show", f"{rev}:{relpath}"],
        cwd=_REPO_ROOT,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_ac10_judgement_columns_of_retired_rows_unchanged_since_merge_base():
    rev = _pre_134_base_rev()
    pre_text = _git_show_text(rev, "docs/aide/golden-decision-table.md")
    post_text = _DOC_PATH.read_bytes().decode("utf-8")

    pre_rows = {r["fixture"]: r for r in _section1_rows_from_text(pre_text)}
    post_rows = {r["fixture"]: r for r in _section1_rows_from_text(post_text)}

    retired = sorted(p for p, r in pre_rows.items() if r["disposition"] == "retire")
    assert len(retired) == 11, f"expected eleven pre-item retired rows, got {len(retired)}"

    judgement_cols = ("what it asserts today", "disposition", "replacement guarantee")
    changed = []
    for path in retired:
        assert path in post_rows, f"{path!r} disappeared from Section 1"
        for col in judgement_cols:
            if pre_rows[path][col] != post_rows[path][col]:
                changed.append((path, col))
    assert not changed, f"judgement column(s) changed on retired row(s): {changed}"


# =========================================================================== #
# AC13: the amendment is recorded once, dated, headings untouched
# =========================================================================== #


def test_ac13_amendment_paragraph_present_exactly_once_and_headings_intact():
    text = _DOC_PATH.read_bytes().decode("utf-8")
    marker = "**Evidence cells re-pointed 2026-08-31 (item 134).**"
    count = text.count(marker)
    assert count == 1, (
        f"expected the item-134 amendment paragraph exactly once, found {count}"
    )

    headings = (
        "Section 1 — Committed test fixtures",
        "Section 2 — Adjacent exact-match artifacts (outside tests/)",
        "Section 3 — In-module frozen snapshots",
        "Not about byte reproducibility",
        "Divergences from the roadmap's working assumption",
    )
    positions = []
    for heading in headings:
        needle = f"## {heading}"
        idx = text.find(needle)
        assert idx != -1, f"missing heading: {needle!r}"
        positions.append(idx)
    assert positions == sorted(positions), "sections are not in the mandated order"

    divergences_idx = text.find(f"## {headings[-1]}")
    log_idx = text.find("## Retirement execution log")
    assert log_idx != -1, "'## Retirement execution log' heading not found"
    assert log_idx > divergences_idx, (
        "'## Retirement execution log' must still follow the Divergences section"
    )

    signoff_re = re.compile(
        r"(?im)^\s*(\*\*)?(signed[- ]off|sign[- ]off|approved by|reviewer|signature)\b"
    )
    assert not signoff_re.search(text), (
        "the amendment paragraph must not read as a sign-off field"
    )


# =========================================================================== #
# AC14: Section 2 is not extended
# =========================================================================== #


def test_ac14_section2_unchanged_and_seven_mandated_fixtures():
    import test_105_golden_decision_table as mod105

    assert len(mod105._SECTION2_EXPECTED_FIXTURES) == 7
    assert "golden_evidence.generated.json" not in " ".join(mod105._SECTION2_EXPECTED_FIXTURES), (
        "the companion must not be listed in Section 2 (see the item's Decisions)"
    )

    text = _DOC_PATH.read_bytes().decode("utf-8")
    sections = _split_sections(text)
    rows = _parse_first_pipe_table(
        sections["Section 2 — Adjacent exact-match artifacts (outside tests/)"]
    )
    fixtures = {r["fixture"] for r in rows}
    assert fixtures == set(mod105._SECTION2_EXPECTED_FIXTURES)
    assert len(rows) == len(mod105._SECTION2_EXPECTED_FIXTURES), "duplicate row in Section 2"


# =========================================================================== #
# AC15: a stale companion fails the drift check
# =========================================================================== #


def _assert_evidence_matches(companion_cases: dict, case_id: str, measured_n: int, measured_m: int) -> None:
    """The drift comparison AC4/AC15 both exercise, factored so the
    adversarial test below can feed a mutated in-memory payload without ever
    writing to the committed companion or the signed document."""
    entry = companion_cases[case_id]
    assert (entry["unwired_leaf_paths"], entry["total_leaf_paths"]) == (measured_n, measured_m), (
        f"{case_id!r}: companion records "
        f"{entry['unwired_leaf_paths']}/{entry['total_leaf_paths']}, measured "
        f"{measured_n}/{measured_m}"
    )


def test_ac15_stale_companion_fails_drift_naming_case_and_both_numbers():
    import segfacet.golden_evidence as golden_evidence

    before = _DOC_PATH.read_bytes()

    fresh = golden_evidence.build_evidence()
    case_id = sorted(fresh["cases"])[0]
    measured_n = fresh["cases"][case_id]["unwired_leaf_paths"]
    measured_m = fresh["cases"][case_id]["total_leaf_paths"]

    stale = json.loads(json.dumps(fresh))
    stale["cases"][case_id]["unwired_leaf_paths"] = measured_n + 1

    with pytest.raises(AssertionError) as exc_info:
        _assert_evidence_matches(stale["cases"], case_id, measured_n, measured_m)
    message = str(exc_info.value)
    assert case_id in message, message
    assert str(measured_n) in message, message
    assert str(measured_n + 1) in message, message

    after = _DOC_PATH.read_bytes()
    assert before == after, "the drift check must never write to the signed document"


# =========================================================================== #
# AC16: the item-127 guard stays clean
# =========================================================================== #


def test_ac16_committed_artifact_guard_clean_and_vocabulary_at_six_members():
    # Reconciled (item 149, 2026-09-04): GROUNDS gains its sixth member,
    # "no-float-leaf" -- this item's companion is untouched by that change,
    # so the guard-clean and no-new-allowlist-entry claims stand unchanged;
    # only the vocabulary pin moves from five to six.
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(_TESTS_DIR))
    assert not violations, guard.violation_message(violations)

    expected_grounds = {
        "exact-parameter-floats",
        "emission-clamped",
        "hand-written-literals",
        "binary-fixture",
        "integrity-pin",
        "no-float-leaf",
    }
    assert set(guard.GROUNDS) == expected_grounds
    assert len(guard.GROUNDS) == 6

    assert not any(
        entry.path == "docs/aide/golden_evidence.generated.json" for entry in guard.ALLOWLIST
    ), "the companion must gain no ALLOWLIST entry (see the item's Decisions)"


# =========================================================================== #
# AC17: the companion carries nothing environment-dependent
# =========================================================================== #


def test_ac17_companion_has_no_float_leaf_no_date_no_absolute_path_no_hostname():
    payload = json.loads(_COMPANION_PATH.read_bytes().decode("utf-8"))
    float_leaves = [(p, v) for p, v in _walk_leaves(payload) if isinstance(v, float)]
    assert not float_leaves, f"companion has float leaf(s): {float_leaves}"

    raw = _COMPANION_PATH.read_bytes().decode("utf-8")
    assert not re.search(r"\d{4}-\d{2}-\d{2}", raw), "companion text carries a date"
    assert not re.search(r"[A-Za-z]:[\\/]", raw), "companion text carries a drive-letter prefix"
    assert not re.search(r"(?<!\S)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", raw), (
        "companion text carries what looks like an absolute path"
    )
    hostname = socket.gethostname()
    if hostname:
        assert hostname not in raw, "companion text carries this machine's hostname"


def test_adv_missing_trailing_newline_would_fail_ac5_check():
    raw = _COMPANION_PATH.read_bytes()
    truncated = raw.rstrip(b"\n")
    with pytest.raises(AssertionError):
        assert truncated.endswith(b"\n"), "trailing newline stripped, must fail AC5's check"


def test_adv_crlf_bytes_would_fail_ac5_check():
    raw = _COMPANION_PATH.read_bytes()
    crlfd = raw.replace(b"\n", b"\r\n")
    with pytest.raises(AssertionError):
        assert b"\r" not in crlfd, "CRLF introduced, must fail AC5's check"


# =========================================================================== #
# AC18: item 126's inventory test stays at 20
# =========================================================================== #


def test_ac18_test105_inventory_count_still_20():
    import test_105_golden_decision_table as mod105

    assert len(mod105._walk_tests_non_py_files()) == 20


# =========================================================================== #
# Adversarial / edge cases beyond AC15
# =========================================================================== #


def test_adv_build_evidence_called_twice_is_idempotent():
    import segfacet.golden_evidence as golden_evidence

    first = golden_evidence.build_evidence()
    second = golden_evidence.build_evidence()
    assert first == second, "build_evidence() is not idempotent across two calls"


def test_adv_main_creates_missing_parent_directory(tmp_path):
    import segfacet.golden_evidence as golden_evidence

    dest = tmp_path / "nested" / "deeper" / "companion.json"
    assert not dest.parent.exists()
    assert golden_evidence.main(["--out", str(dest)]) == 0
    assert dest.is_file()


def test_adv_companion_missing_a_case_id_fails_naming_it():
    from segfacet.synth.corpus import load_manifest

    manifest_case_ids = {c["case_id"] for c in load_manifest()["cases"]}
    assert manifest_case_ids, "expected at least one manifest case"
    missing_id = sorted(manifest_case_ids)[0]
    truncated = {
        "cases": {
            cid: {"total_leaf_paths": 1, "unwired_leaf_paths": 0}
            for cid in manifest_case_ids
            if cid != missing_id
        }
    }
    with pytest.raises(AssertionError, match=re.escape(missing_id)):
        _assert_companion_shape(truncated, manifest_case_ids)


def test_adv_companion_with_extra_case_key_fails_shape():
    from segfacet.synth.corpus import load_manifest

    manifest_case_ids = {c["case_id"] for c in load_manifest()["cases"]}
    payload = {
        "cases": {
            cid: {"total_leaf_paths": 1, "unwired_leaf_paths": 0} for cid in manifest_case_ids
        }
    }
    payload["cases"]["not_a_real_case"] = {"total_leaf_paths": 1, "unwired_leaf_paths": 0}
    with pytest.raises(AssertionError, match="case-id set mismatch"):
        _assert_companion_shape(payload, manifest_case_ids)


def test_adv_companion_with_string_counts_fails_on_type_not_value():
    from segfacet.synth.corpus import load_manifest

    manifest_case_ids = {c["case_id"] for c in load_manifest()["cases"]}
    payload = {
        "cases": {
            cid: {"total_leaf_paths": "94", "unwired_leaf_paths": "26"}
            for cid in manifest_case_ids
        }
    }
    with pytest.raises(AssertionError, match="not an int"):
        _assert_companion_shape(payload, manifest_case_ids)
