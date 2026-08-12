"""Tests for item 105 -- golden-file decision table + human sign-off (Stage 19).

This item's production deliverable is a *document*,
``docs/aide/golden-decision-table.md``, not code -- so this module is the
oracle a builder writes that document against, mirroring how item 103's tests
were written before its production modules existed. Until the document is
written, most of the tests below fail (missing-file errors); that is
expected at this point in the pipeline and is not this module's bug.

The module supplies its own ~25-line Markdown pipe-table parser
(``_split_sections`` / ``_parse_first_pipe_table``) -- there is no production
parser to import, per the Testing Strategy's "one hand-authored document with
a machine-checked table, not a generator" design. Every structural
Acceptance Criterion (AC2-AC7, AC9, AC13) runs off that one parse.

Covers Acceptance Criteria AC1-AC14:

- AC1:  the document exists, is written with ``\\n`` newlines (no ``\\r``),
        and carries the five mandated level-2 headings in order.
- AC2:  Section 1's table header is exactly the six mandated columns.
- AC3:  Section 1's fixture set equals a filesystem walk of ``tests/`` for
        non-``.py`` files (excluding ``__pycache__``/``.pytest_cache``), in
        both directions, with no duplicate fixture path.
- AC4:  every Section-1/Section-2 disposition is exactly ``keep`` or exactly
        ``retire``.
- AC5:  ``retire`` rows name a concrete replacement; ``keep`` rows carry
        ``—`` in that cell.
- AC6:  every ``asserted by`` cell names real, on-disk test modules (and,
        where ``::``-qualified, real test functions in them).
- AC7:  the nine corpus-golden rows' ``evidence`` cells carry a *measured*
        (not transcribed) unwired-leaf fraction, recomputed via
        ``segfacet.catalogue.build_catalogue()``/``iter_leaf_paths``.
- AC8:  the byte-reproducibility disclaimer cites ``synth/golden.py`` and
        names three surviving determinism assertions by fully-qualified id,
        each resolving to a real test function.
- AC9:  Section 2 uses the same six columns and contains exactly the seven
        mandated adjacent-artifact rows, no more, no fewer.
- AC10: Section 3's prose names the two ``_PRE_098_*`` identifiers (real in
        ``test_098``), the ``test_102`` import, and a blanket disposition for
        the ``_PRE_NNN_*`` sha256 scope-fence constants.
- AC11: the document names ``progress.md``'s Stage-19 checkbox as the sole
        attestation and contains no sign-off field of its own.
- AC12: ``progress.md``'s Stage-19 sign-off checkbox is honestly unticked or
        ticked with an italic evidence note -- checked as an explicit
        three-branch predicate, not an ``if ticked:`` no-op.
- AC13: the Divergences section names exactly the ``keep`` rows, in both
        directions.
- AC14: the scope fence -- ``tests/corpus/**`` and ``src/segfacet/**`` are
        byte-unchanged (hash-pinned); ``tests/golden/**`` (not LF-pinned) is
        checked by name-set + text-digest, not bytes; ``.gitattributes`` is
        byte-unchanged.

Adversarial / edge-case scenarios included: a disposition cell surviving
strip with a trailing period or wrong case; a ``retire`` replacement cell of
``—``/``TBD``/``see above``; a duplicated fixture path where the *sets*
still match; an ``asserted by`` cell naming a nonexistent module or missing
function; a malformed/degenerate ``evidence`` cell (missing trailing words,
``N > M``); a synthetic ``**Signed off:**`` line; a Divergences section
naming a ``retire`` row; an empty (header-only) Section-1 table; a malformed
pipe table with a cell-count mismatch, asserted to fail naming the offending
line rather than raising ``IndexError``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTS_DIR = Path(__file__).resolve().parent
_DOC_PATH = _REPO_ROOT / "docs" / "aide" / "golden-decision-table.md"
_PROGRESS_PATH = _REPO_ROOT / "docs" / "aide" / "progress.md"
_CORPUS_GOLDEN_DIR = _TESTS_DIR / "corpus" / "golden"

_EXPECTED_COLUMNS = (
    "fixture",
    "what it asserts today",
    "asserted by",
    "evidence",
    "disposition",
    "replacement guarantee",
)

_SECTION_HEADINGS = (
    "Section 1 — Committed test fixtures",
    "Section 2 — Adjacent exact-match artifacts (outside tests/)",
    "Section 3 — In-module frozen snapshots",
    "Not about byte reproducibility",
    "Divergences from the roadmap's working assumption",
)


# =========================================================================== #
# The module's own ~25-line Markdown pipe-table parser (Testing Strategy)
# =========================================================================== #


def _split_sections(text: str) -> dict:
    """Split ``text`` on level-2 (``## ``) headings; return
    ``{heading_text: body_text}`` keyed by heading, in encounter order."""
    heading_re = re.compile(r"(?m)^## (.+?)\s*$")
    matches = list(heading_re.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[title] = text[start:end]
    return sections


def _normalise_header_cell(cell: str) -> str:
    return re.sub(r"\s+", " ", cell.strip()).lower()


def _table_cells(line: str) -> list:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _parse_first_pipe_table(section_text: str, *, where: str = ""):
    """Parse the first Markdown pipe table in ``section_text``. Returns
    ``(header_cells, rows)`` where ``rows`` is ``list[dict[str, str]]`` keyed
    by the normalised header cells, ignoring the ``|---|`` separator row.
    Raises ``AssertionError`` naming the offending line on a malformed table
    rather than letting an ``IndexError`` propagate."""
    table_lines = []
    in_table = False
    for line in section_text.splitlines():
        if line.strip().startswith("|"):
            table_lines.append(line.strip())
            in_table = True
        elif in_table:
            break

    if not table_lines:
        raise AssertionError(f"no pipe table found in section {where!r}")
    if len(table_lines) < 2:
        raise AssertionError(
            f"malformed table in section {where!r}: missing separator row "
            f"(only found {table_lines!r})"
        )

    header_cells = [_normalise_header_cell(c) for c in _table_cells(table_lines[0])]
    separator_cells = _table_cells(table_lines[1])
    if not all(re.fullmatch(r":?-{1,}:?", c) for c in separator_cells):
        raise AssertionError(
            f"malformed table in section {where!r}: row 2 is not a separator "
            f"row: {table_lines[1]!r}"
        )

    rows = []
    for line in table_lines[2:]:
        raw_cells = _table_cells(line)
        if len(raw_cells) != len(header_cells):
            raise AssertionError(
                f"malformed table row in section {where!r}: expected "
                f"{len(header_cells)} cells, got {len(raw_cells)}: {line!r}"
            )
        rows.append(dict(zip(header_cells, raw_cells)))
    return header_cells, rows


# =========================================================================== #
# Shared fixtures
# =========================================================================== #


@pytest.fixture(scope="module")
def doc_text() -> str:
    return _DOC_PATH.read_bytes().decode("utf-8")


@pytest.fixture(scope="module")
def sections(doc_text) -> dict:
    return _split_sections(doc_text)


@pytest.fixture(scope="module")
def section1_rows(sections):
    _, rows = _parse_first_pipe_table(
        sections["Section 1 — Committed test fixtures"], where="Section 1"
    )
    return rows


@pytest.fixture(scope="module")
def section2_rows(sections):
    _, rows = _parse_first_pipe_table(
        sections["Section 2 — Adjacent exact-match artifacts (outside tests/)"],
        where="Section 2",
    )
    return rows


def _row_for_fixture(rows, fixture_path: str) -> dict:
    matches = [r for r in rows if r["fixture"] == fixture_path]
    assert len(matches) == 1, (
        f"expected exactly one row for {fixture_path!r}, got {len(matches)}"
    )
    return matches[0]


# =========================================================================== #
# AC1: the document exists with the mandated section structure
# =========================================================================== #


def test_ac1_document_exists_written_with_lf_newlines():
    raw = _DOC_PATH.read_bytes()
    assert b"\r" not in raw, "document must use \\n newlines (write_bytes)"


def test_ac1_mandated_headings_present_in_order(doc_text):
    positions = []
    for heading in _SECTION_HEADINGS:
        needle = f"## {heading}"
        idx = doc_text.find(needle)
        assert idx != -1, f"missing heading: {needle!r}"
        positions.append(idx)
    assert positions == sorted(positions), "sections are not in the mandated order"


# =========================================================================== #
# AC2: Section 1's table carries exactly the mandated columns, in order
# =========================================================================== #


def test_ac2_section1_header_has_exact_mandated_columns(sections):
    header_cells, _ = _parse_first_pipe_table(
        sections["Section 1 — Committed test fixtures"], where="Section 1"
    )
    assert tuple(header_cells) == _EXPECTED_COLUMNS


# =========================================================================== #
# AC3: Section 1 enumerates every committed test fixture exactly once
# =========================================================================== #


def _walk_tests_non_py_files() -> set:
    found = set()
    for path in _TESTS_DIR.rglob("*"):
        if not path.is_file() or path.suffix == ".py":
            continue
        parts = set(path.relative_to(_TESTS_DIR).parts)
        if "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        found.add(path.relative_to(_REPO_ROOT).as_posix())
    return found


def test_ac3_current_tree_has_29_non_py_fixtures():
    assert len(_walk_tests_non_py_files()) == 29


def test_ac3_section1_fixture_set_equals_filesystem_walk_both_directions(section1_rows):
    documented = [row["fixture"] for row in section1_rows]
    documented_set = set(documented)
    duplicates = sorted({p for p in documented_set if documented.count(p) > 1})
    assert not duplicates, f"duplicate fixture path(s) in Section 1: {duplicates}"

    on_disk = _walk_tests_non_py_files()
    missing = sorted(on_disk - documented_set)
    extra = sorted(documented_set - on_disk)
    assert not missing and not extra, (
        f"Section 1 completeness mismatch -- missing from table: {missing}; "
        f"extra rows not on disk: {extra}"
    )


# =========================================================================== #
# AC4: every Section-1/Section-2 disposition is from the fixed vocabulary
# =========================================================================== #


def test_ac4_every_disposition_is_keep_or_retire(section1_rows, section2_rows):
    for row in section1_rows + section2_rows:
        assert row["disposition"] in ("keep", "retire"), row


# =========================================================================== #
# AC5: retire rows name a replacement, keep rows carry the placeholder
# =========================================================================== #

_MODULE_REF_RE = re.compile(r"tests/test_\d+\w*\.py")
_FUNC_REF_RE = re.compile(r"::test_\w+")
_STAGE_REF_RE = re.compile(r"stage\s*\d+", re.IGNORECASE)


def _names_concrete_artifact(text: str) -> bool:
    return bool(
        _MODULE_REF_RE.search(text) or _FUNC_REF_RE.search(text) or _STAGE_REF_RE.search(text)
    )


def test_ac5_retire_rows_name_replacement_keep_rows_carry_placeholder(
    section1_rows, section2_rows
):
    for row in section1_rows + section2_rows:
        cell = row["replacement guarantee"]
        if row["disposition"] == "retire":
            assert cell and cell != "—", row
            assert _names_concrete_artifact(cell), (
                f"retire row's replacement guarantee names no concrete artifact: {row}"
            )
        else:
            assert cell == "—", row


# =========================================================================== #
# AC6: every "asserted by" cell resolves to real tests
# =========================================================================== #

_MODULE_NAME_RE = re.compile(r"tests/test_\d+\w*\.py")
_QUALIFIED_FUNC_RE = re.compile(r"(tests/test_\d+\w*\.py)::(\w+)")


def test_ac6_asserted_by_cells_resolve_to_real_tests(section1_rows, section2_rows):
    for row in section1_rows + section2_rows:
        cell = row["asserted by"]
        modules = _MODULE_NAME_RE.findall(cell)
        assert modules, f"'asserted by' cell names no test module: {row}"
        for module in sorted(set(modules)):
            assert (_REPO_ROOT / module).is_file(), (
                f"{module!r} named in row {row!r} does not exist"
            )
        for module, func in _QUALIFIED_FUNC_RE.findall(cell):
            source = (_REPO_ROOT / module).read_text(encoding="utf-8")
            assert re.search(rf"def {re.escape(func)}\b", source), (
                f"{func!r} not found in {module!r} (row: {row})"
            )


# =========================================================================== #
# AC7: the nine corpus-golden rows carry a *measured* unwired fraction
# =========================================================================== #

_EVIDENCE_RE = re.compile(r"^(\d+)/(\d+) leaf paths unwired$")

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


@pytest.mark.parametrize("case_id", _GOLDEN_CASE_IDS)
def test_ac7_golden_row_evidence_is_measured_not_transcribed(section1_rows, case_id):
    import segfacet.catalogue as catalogue

    fixture_path = f"tests/corpus/golden/{case_id}.json"
    row = _row_for_fixture(section1_rows, fixture_path)
    match = _EVIDENCE_RE.match(row["evidence"].strip())
    assert match, (
        f"evidence cell does not match 'N/M leaf paths unwired': {row['evidence']!r}"
    )
    documented_n, documented_m = int(match.group(1)), int(match.group(2))
    assert 0 <= documented_n <= documented_m
    assert documented_m > 0

    golden = json.loads((_CORPUS_GOLDEN_DIR / f"{case_id}.json").read_bytes())
    leaf_paths = catalogue.iter_leaf_paths(golden["features"])
    cat = catalogue.build_catalogue()
    status_by_path = {entry.path: entry.status for entry in cat.entries}

    measured_m = len(leaf_paths)
    measured_n = sum(1 for p in leaf_paths if status_by_path.get(p) == "unwired")

    assert documented_m == measured_m, (case_id, "M", documented_m, measured_m)
    assert documented_n == measured_n, (case_id, "N", documented_n, measured_n)


# =========================================================================== #
# AC8: the byte-reproducibility disclaimer names the surviving assertions
# =========================================================================== #

_AC8_REQUIRED_TEST_IDS = (
    "tests/test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical",
    "tests/test_042_golden_determinism.py::test_ac12_main_regenerates_matching_goldens",
    "tests/test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism",
)


def test_ac8_disclaimer_cites_synth_golden_module(sections):
    body = sections["Not about byte reproducibility"]
    assert "src/segfacet/synth/golden.py" in body
    assert (_REPO_ROOT / "src" / "segfacet" / "synth" / "golden.py").is_file()


@pytest.mark.parametrize("test_id", _AC8_REQUIRED_TEST_IDS)
def test_ac8_disclaimer_names_surviving_assertion_and_it_resolves(sections, test_id):
    body = sections["Not about byte reproducibility"]
    assert test_id in body, test_id
    module, func = test_id.split("::")
    source = (_REPO_ROOT / module).read_text(encoding="utf-8")
    assert re.search(rf"def {re.escape(func)}\b", source), test_id


# =========================================================================== #
# AC9: Section 2 covers every adjacent artifact by name
# =========================================================================== #

_SECTION2_EXPECTED_FIXTURES = (
    "src/segfacet/reference/reference_default.json",
    "src/segfacet/reference/reference_verse_v1.json",
    "src/segfacet/report_schema_v0.json",
    "src/segfacet/eval/eval_report_schema_v0.json",
    "src/segfacet/eval/per_mode_comparison_schema_v0.json",
    "docs/aide/feature_catalogue.generated.json",
    "docs/aide/feature_catalogue.generated.md",
)


def test_ac9_section2_header_matches_section1_columns(sections):
    header_cells, _ = _parse_first_pipe_table(
        sections["Section 2 — Adjacent exact-match artifacts (outside tests/)"],
        where="Section 2",
    )
    assert tuple(header_cells) == _EXPECTED_COLUMNS


def test_ac9_section2_contains_exactly_the_seven_mandated_rows(section2_rows):
    fixtures = [row["fixture"] for row in section2_rows]
    assert set(fixtures) == set(_SECTION2_EXPECTED_FIXTURES)
    assert len(fixtures) == len(_SECTION2_EXPECTED_FIXTURES), "duplicate row in Section 2"


# =========================================================================== #
# AC10: Section 3 names the in-module frozen snapshots
# =========================================================================== #


def test_ac10_section3_names_pre_098_identifiers_present_in_test_098(sections):
    body = sections["Section 3 — In-module frozen snapshots"]
    source_098 = (_REPO_ROOT / "tests" / "test_098_stray_components.py").read_text(
        encoding="utf-8"
    )
    for identifier in (
        "_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS",
        "_PRE_098_GOLDEN_VERDICT_AND_FINDINGS",
    ):
        assert identifier in body, identifier
        assert identifier in source_098, identifier


def test_ac10_section3_states_test_102_imports_it(sections):
    body = sections["Section 3 — In-module frozen snapshots"]
    assert "tests/test_102_stage18_validation.py" in body
    source_102 = (_REPO_ROOT / "tests" / "test_102_stage18_validation.py").read_text(
        encoding="utf-8"
    )
    assert "_PRE_098_GOLDEN_VERDICT_AND_FINDINGS" in source_102


def test_ac10_section3_states_blanket_disposition_for_pre_nnn_constants(sections):
    body = sections["Section 3 — In-module frozen snapshots"]
    assert "_PRE_NNN_" in body
    assert re.search(r"\bkeep\b", body), (
        "Section 3 must state a disposition for the _PRE_NNN_* scope-fence constants"
    )


# =========================================================================== #
# AC11: the document declares progress.md as the sole attestation
# =========================================================================== #

_SIGNOFF_LINE_RE = re.compile(
    r"(?im)^\s*(\*\*)?(signed[- ]off|sign[- ]off|approved by|reviewer|signature)\b"
)


def test_ac11_names_progress_md_stage19_checkbox_as_attestation(doc_text):
    assert "progress.md" in doc_text
    assert "Stage 19" in doc_text


def test_ac11_no_line_matches_signoff_field_pattern(doc_text):
    assert not _SIGNOFF_LINE_RE.search(doc_text), (
        "document must not carry a sign-off field of its own"
    )


def test_adv_ac11_signoff_line_pattern_is_actually_reachable():
    sample = "**Signed off:** Jane Doe, 2026-07-28\n"
    assert _SIGNOFF_LINE_RE.search(sample), "regression guard: pattern must match a real offender"


# =========================================================================== #
# AC12: progress.md's Stage-19 sign-off checkbox is honest
# =========================================================================== #


def _ac12_signoff_ok(ticked: bool, block_after_checkbox: str) -> bool:
    evidence_match = re.search(r"\*\(.*?\)\*", block_after_checkbox, re.DOTALL)
    if not ticked:
        return evidence_match is None
    if evidence_match is None:
        return False
    return "golden-decision-table.md" in evidence_match.group(0)


def test_adv_ac12_unticked_without_evidence_note_passes():
    block = "The golden decision table is complete and signed off by the human reviewer."
    assert _ac12_signoff_ok(False, block)


def test_adv_ac12_ticked_with_evidence_note_passes():
    block = (
        "The golden decision table is complete and signed off by the human "
        "reviewer. *(golden-decision-table.md, 2026-07-28)*"
    )
    assert _ac12_signoff_ok(True, block)


def test_adv_ac12_ticked_without_evidence_note_fails():
    block = "The golden decision table is complete and signed off by the human reviewer."
    assert not _ac12_signoff_ok(True, block)


def _stage19_signoff_block(progress_text: str):
    anchor = "golden decision table is complete and signed off"
    idx = progress_text.find(anchor)
    assert idx != -1, "Stage 19 acceptance list has no golden-decision-table sign-off item"
    line_start = progress_text.rfind("\n", 0, idx) + 1
    checkbox_match = re.match(r"- \[([ xX])\] ", progress_text[line_start:])
    assert checkbox_match, "sign-off item is not a checkbox list item"
    ticked = checkbox_match.group(1).lower() == "x"

    end_blank = progress_text.find("\n\n", idx)
    end_hr = progress_text.find("\n---", idx)
    candidates = [e for e in (end_blank, end_hr) if e != -1]
    block_end = min(candidates) if candidates else len(progress_text)
    return ticked, progress_text[line_start:block_end]


def test_ac12_real_progress_md_stage19_checkbox_is_honest():
    text = _PROGRESS_PATH.read_text(encoding="utf-8")
    ticked, block = _stage19_signoff_block(text)
    assert _ac12_signoff_ok(ticked, block), (
        "progress.md's Stage-19 sign-off checkbox is neither honestly "
        "unticked nor ticked-with-evidence"
    )


# =========================================================================== #
# AC13: divergences from the roadmap's working assumption are itemised
# =========================================================================== #


def test_ac13_divergences_section_names_exactly_the_keep_rows(
    sections, section1_rows, section2_rows
):
    body = sections["Divergences from the roadmap's working assumption"]
    all_rows = section1_rows + section2_rows
    keep_fixtures = {row["fixture"] for row in all_rows if row["disposition"] == "keep"}
    retire_fixtures = {row["fixture"] for row in all_rows if row["disposition"] == "retire"}

    missing = sorted(f for f in keep_fixtures if f not in body)
    assert not missing, f"Divergences section omits keep row(s): {missing}"

    wrongly_named = sorted(f for f in retire_fixtures if f in body)
    assert not wrongly_named, (
        f"Divergences section names retire row(s) that must not appear: {wrongly_named}"
    )


# =========================================================================== #
# AC14: (byte-hash scope fences formerly here were removed by item 107; see
# docs/aide/items/107-retire-byte-hash-scope-fences.md. Diff-time scope is
# now checked by scripts/check_item_scope.py on the branch.)
# =========================================================================== #


# =========================================================================== #
# Adversarial / edge cases (parser + validation logic exercised directly,
# independent of whether the real document exists yet)
# =========================================================================== #


def test_adv_parser_raises_naming_offending_line_on_cell_count_mismatch():
    section = "\n\n| a | b |\n|---|---|\n| only-one-cell |\n"
    with pytest.raises(AssertionError, match=r"only-one-cell"):
        _parse_first_pipe_table(section, where="synthetic")


def test_adv_ac4_disposition_with_trailing_period_or_wrong_case_is_rejected():
    section = (
        "\n\n| fixture | what it asserts today | asserted by | evidence | "
        "disposition | replacement guarantee |\n"
        "|---|---|---|---|---|---|\n"
        "| tests/example.json | x | tests/test_000_x.py | n/a | keep. | — |\n"
    )
    _, rows = _parse_first_pipe_table(section, where="synthetic")
    assert rows[0]["disposition"] not in ("keep", "retire")


@pytest.mark.parametrize("replacement", ["—", "TBD", "see above", ""])
def test_adv_ac5_retire_row_with_vague_replacement_is_rejected(replacement):
    is_acceptable = bool(
        replacement and replacement != "—" and _names_concrete_artifact(replacement)
    )
    assert not is_acceptable


def test_adv_ac3_duplicated_fixture_path_caught_even_when_sets_still_match():
    section = (
        "\n\n| fixture | what it asserts today | asserted by | evidence | "
        "disposition | replacement guarantee |\n"
        "|---|---|---|---|---|---|\n"
        "| tests/a.json | x | tests/test_000_x.py | n/a | keep | — |\n"
        "| tests/a.json | y | tests/test_000_x.py | n/a | keep | — |\n"
    )
    _, rows = _parse_first_pipe_table(section, where="synthetic")
    fixtures = [r["fixture"] for r in rows]
    assert len(fixtures) != len(set(fixtures))


def test_adv_ac3_empty_header_only_table_fails_with_full_missing_list():
    section = (
        "\n\n| fixture | what it asserts today | asserted by | evidence | "
        "disposition | replacement guarantee |\n"
        "|---|---|---|---|---|---|\n"
    )
    _, rows = _parse_first_pipe_table(section, where="synthetic")
    assert rows == []
    documented_set = {r["fixture"] for r in rows}
    missing = sorted(_walk_tests_non_py_files() - documented_set)
    assert len(missing) == 29, "an empty table must not trivially pass on two empty sets"


def test_adv_ac6_asserted_by_naming_nonexistent_module_is_detectable():
    cell = "tests/test_999_does_not_exist_item105.py"
    modules = _MODULE_NAME_RE.findall(cell)
    assert modules
    assert not (_REPO_ROOT / modules[0]).is_file()


def test_adv_ac6_asserted_by_naming_missing_function_is_detectable():
    module = "tests/test_042_golden_determinism.py"
    func = "test_does_not_exist_at_all_item105"
    source = (_REPO_ROOT / module).read_text(encoding="utf-8")
    assert not re.search(rf"def {re.escape(func)}\b", source)


@pytest.mark.parametrize(
    "cell", ["34/67", "34 of 67 leaf paths unwired", "70/67 leaf paths unwired"]
)
def test_adv_ac7_malformed_evidence_cell_fails_format_before_arithmetic(cell):
    match = _EVIDENCE_RE.match(cell.strip())
    if match is None:
        return  # correctly rejected on format alone
    n, m = int(match.group(1)), int(match.group(2))
    assert not (0 <= n <= m), "expected the N>M case to fail on arithmetic instead"


def test_adv_ac13_divergences_naming_a_retire_fixture_is_flagged():
    retire_fixtures = {"tests/b.json"}
    body = "See tests/a.json and tests/b.json for details."
    wrongly_named = sorted(f for f in retire_fixtures if f in body)
    assert wrongly_named == ["tests/b.json"]


def test_adv_ac13_divergences_omitting_a_keep_fixture_is_flagged():
    keep_fixtures = {"tests/a.json", "tests/c.json"}
    body = "See tests/a.json for details."
    missing = sorted(f for f in keep_fixtures if f not in body)
    assert missing == ["tests/c.json"]
