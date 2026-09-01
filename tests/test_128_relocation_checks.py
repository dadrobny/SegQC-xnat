"""Checking module for item 128 -- relocate the ``reference_verse_v1``
integrity pin and rename ``test_102``'s fence header (Stage 29, D3).

Ownership split per the item spec: the builder relocates the pin itself
(``tests/test_128_reference_verse_v1_integrity.py``, the new module's own
AC1-AC8 tests) and reconciles the four downstream consumers. This module is
the independent *checking* half -- it verifies every AC by reading source/AST,
running ``git check-attr``, hashing the artifact, driving the item-127
classifier and the item-115 fence classifier's discriminator, comparing the
decision table's cells, and replaying ``aide check``.

Every test here that depends on the new module
(``tests/test_128_reference_verse_v1_integrity.py``) or on the four
reconciled consumers is expected to FAIL until the builder lands -- imports
are deferred into test bodies so collection succeeds regardless (per the
project's test-writer convention, see ``tests/test_127_committed_artifact_
tolerance.py``'s docstring for the same shape).

**AC20's trap.** ``tests/test_115_stage26_validation.py``'s shape-based
classifier caps the corpus at one sha256-vs-literal "fence" -- the relocated
pin itself. Asserting AC20 (the decision table's four signed cells are
unchanged) via a digest comparison would introduce a *second* fence and turn
AC13 red. So :func:`test_ac20_*` below compares the four cells as plain
strings against literals captured from the document as it stood before this
item touched it, exactly as the spec's Testing Strategy directs -- never
``hashlib.sha256(...) == "<literal>"``.

Adversarial / edge cases:

- A synthetic module that pins the artifact through a helper-function call
  (not the required repo-root-relative literal chain) is confirmed
  *invisible* to item 127's classifier -- the queue's own stated failure mode
  for a relocation that reverted to ``bundled_production_reference_path()``.
- A synthetic fence-classifier header string containing ``scope fence`` in a
  different case (``SCOPE FENCE``) is confirmed to still trip AC16's
  case-insensitive absence check, so a builder cannot dodge the requirement
  by changing case.
- A synthetic decision-table row with a whitespace-only cell change (an
  added trailing space) is confirmed to be caught by the AC20 string
  comparison, proving it is not accidentally tolerant of insignificant
  whitespace drift.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess

from run_process import run_utf8
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_NEW_MODULE_NAME = "test_128_reference_verse_v1_integrity.py"
_NEW_MODULE_PATH = _TESTS_DIR / _NEW_MODULE_NAME
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"
_ARTIFACT_PATH = (
    _REPO_ROOT / "src" / "segfacet" / "reference" / "reference_verse_v1.json"
)
_ARTIFACT_REL_POSIX = "src/segfacet/reference/reference_verse_v1.json"
_RELEASED_DIGEST = (
    "2048804f60208a4dea0cbe8d0980e1e6228c68b52b6331375f768254fc73b5da"
)
_DECISION_TABLE = _REPO_ROOT / "docs" / "aide" / "golden-decision-table.md"


def _new_module_source() -> str:
    assert _NEW_MODULE_PATH.is_file(), (
        f"{_NEW_MODULE_NAME} does not exist yet -- builder has not landed"
    )
    return _NEW_MODULE_PATH.read_text(encoding="utf-8")


def _new_module_ast() -> ast.Module:
    return ast.parse(_new_module_source(), filename=str(_NEW_MODULE_PATH))


# =========================================================================== #
# AC1: the pin has a module named for the artifact
# =========================================================================== #


def test_ac1_new_module_exists():
    assert _NEW_MODULE_PATH.is_file(), f"{_NEW_MODULE_PATH} does not exist"


def test_ac1_module_docstring_names_the_artifact_and_its_provenance():
    tree = _new_module_ast()
    docstring = ast.get_docstring(tree) or ""
    assert docstring, f"{_NEW_MODULE_NAME} has no module docstring"
    assert "reference_verse_v1.json" in docstring
    assert "not regenerable in CI" in docstring or "not CI-regenerable" in docstring
    assert re.search(r"production", docstring, re.IGNORECASE)


# =========================================================================== #
# AC2: identifiers say what they protect
# =========================================================================== #


def test_ac2_digest_identifier_is_the_released_name():
    source = _new_module_source()
    assert "_RELEASED_REFERENCE_VERSE_V1_SHA256" in source


def test_ac2_no_identifier_carries_pre_098_or_ac18():
    tree = _new_module_ast()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    offenders = [
        n for n in names if "PRE_098" in n or "pre_098" in n or "ac18" in n.lower()
    ]
    assert not offenders, f"identifiers still reference the old name: {offenders}"


# =========================================================================== #
# AC3: the digest literal is carried across verbatim
# =========================================================================== #


def test_ac3_released_digest_equals_carried_over_literal():
    from importlib import import_module

    mod = import_module("test_128_reference_verse_v1_integrity")
    assert mod._RELEASED_REFERENCE_VERSE_V1_SHA256 == _RELEASED_DIGEST


# =========================================================================== #
# AC4: the pin holds against the committed artifact
# =========================================================================== #


def test_ac4_artifact_digest_matches_released_pin():
    """Deliberately compares the fresh digest against the new module's own
    constant (an ``ast.Attribute`` access, not a local literal) rather than
    against this file's ``_RELEASED_DIGEST`` -- a ``hashlib.sha256(...) ==
    <local literal>`` shape here would itself be classified 'fence' by
    ``test_115_stage26_validation.py``'s shape-based scanner and, alongside
    the relocated pin, push the corpus to two fences, breaking AC13. See
    the module docstring's note on the AC20 trap; the same discriminator
    applies here."""
    import hashlib
    from importlib import import_module

    mod = import_module("test_128_reference_verse_v1_integrity")
    digest = hashlib.sha256(_ARTIFACT_PATH.read_bytes()).hexdigest()
    assert digest == mod._RELEASED_REFERENCE_VERSE_V1_SHA256


# =========================================================================== #
# AC5: the pin still fails when a byte of the artifact changes
# =========================================================================== #


def test_ac5_one_byte_mutation_changes_the_digest(tmp_path):
    import hashlib

    original = _ARTIFACT_PATH.read_bytes()
    assert original, "artifact is unexpectedly empty"

    mutated = bytearray(original)
    mutated[0] = (mutated[0] + 1) % 256
    mutated_path = tmp_path / "reference_verse_v1_mutated.json"
    mutated_path.write_bytes(bytes(mutated))

    mutated_digest = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
    assert mutated_digest != _RELEASED_DIGEST, (
        "a one-byte mutation must not still match the released digest -- the "
        "pin would be a tautology"
    )


def test_ac5_digest_computation_is_deterministic_within_one_run():
    import hashlib

    first = hashlib.sha256(_ARTIFACT_PATH.read_bytes()).hexdigest()
    second = hashlib.sha256(_ARTIFACT_PATH.read_bytes()).hexdigest()
    assert first == second


# =========================================================================== #
# AC6: statically visible to item 127's classifier
# =========================================================================== #


def test_ac6_classifier_flags_the_pin_with_allowlist_emptied(monkeypatch):
    import committed_artifact_guard as guard

    monkeypatch.setattr(guard, "ALLOWLIST", ())
    source = _new_module_source()
    violations = guard.classify_module(source, _NEW_MODULE_NAME)
    matching = [v for v in violations if v.committed_path == _ARTIFACT_REL_POSIX]
    assert matching, (
        f"expected classify_module to report a violation with committed_path "
        f"== {_ARTIFACT_REL_POSIX!r} once the allowlist is emptied; got "
        f"{violations}"
    )


def test_ac6_classifier_reports_zero_violations_with_allowlist_intact():
    """The real allowlist covers this artifact (integrity-pin ground), so
    the un-monkeypatched classifier must report nothing for it -- pairs with
    the AC6 test above to prove the empty-allowlist result isn't a red
    herring caused by some other unrelated violation in the same module."""
    import committed_artifact_guard as guard

    source = _new_module_source()
    violations = guard.classify_module(source, _NEW_MODULE_NAME)
    matching = [v for v in violations if v.committed_path == _ARTIFACT_REL_POSIX]
    assert not matching, (
        f"the real allowlist should cover {_ARTIFACT_REL_POSIX!r} already: "
        f"{matching}"
    )


# =========================================================================== #
# AC7: the pin covers the artifact the package actually ships
# =========================================================================== #


def test_ac7_pinned_path_matches_bundled_production_reference_path():
    from segfacet.reference.artifact import bundled_production_reference_path

    from importlib import import_module

    mod = import_module("test_128_reference_verse_v1_integrity")
    assert hasattr(mod, "_ARTIFACT"), (
        "expected a module-level _ARTIFACT constant per the spec's "
        "Implementation Steps"
    )
    assert mod._ARTIFACT.resolve() == bundled_production_reference_path().resolve()


# =========================================================================== #
# AC8: the load-and-score companion moves with the pin
# =========================================================================== #


def test_ac8_new_module_defines_a_load_and_score_companion():
    tree = _new_module_ast()
    names = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    matching = [n for n in names if "load" in n.lower() and "scor" in n.lower()]
    assert matching, (
        f"no load-and-score companion test found among {sorted(names)}"
    )


def test_ac8_companion_body_asserts_bounds_finding_on_label_22():
    tree = _new_module_ast()
    source = _new_module_source()
    candidates = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and "load" in n.name.lower()
        and "scor" in n.name.lower()
    ]
    assert candidates, "no load-and-score companion found to inspect"
    segment = ast.get_source_segment(source, candidates[0]) or ""
    assert "run_qc_with_reference" in segment
    assert "bounds" in segment
    assert "22" in segment


def test_ac8_companion_actually_runs_and_finds_label_22_bounds_finding():
    """Independent of the new module's own test -- run the same shape
    directly against the public reference API and corpus, so a builder who
    wrote a companion test that asserts something else entirely (but still
    contains the strings 'bounds'/'22') cannot pass AC8 vacuously."""
    from segfacet.config import bundled_default_config
    from segfacet.pipeline import run_qc_with_reference
    from segfacet.reference.artifact import bundled_production_reference
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.regression import loaded_seg_image

    manifest = load_manifest()
    case = next(
        c for c in manifest["cases"] if c["case_id"] == "mode6_crop_at_border"
    )
    seg_img = loaded_seg_image(case)
    reference = bundled_production_reference()

    case_result, _block, _delta = run_qc_with_reference(
        seg_img, bundled_default_config(), reference
    )
    bounds_22 = [
        f
        for f in case_result.findings
        if f.rule_id == "bounds" and 22 in f.labels
    ]
    assert len(bounds_22) >= 1


# =========================================================================== #
# AC9: test_098 no longer defines the pin
# =========================================================================== #

_OLD_IDENTIFIERS = (
    "_PRE_098_REFERENCE_VERSE_V1_SHA256",
    "test_ac18_reference_verse_v1_bytes_unchanged",
    "test_ac18_reference_verse_v1_still_loads_and_scores_a_case",
)


def test_ac9_test098_defines_none_of_the_old_identifiers():
    module = "tests/test_098_stray_components.py"
    tree = ast.parse((_REPO_ROOT / module).read_text(encoding="utf-8"), filename=module)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    present = [n for n in _OLD_IDENTIFIERS if n in names]
    assert not present, f"{module} still defines {present}"


# =========================================================================== #
# AC10: the old identifier is gone from the whole test tree
# =========================================================================== #


def test_ac10_old_digest_identifier_absent_from_every_test_module():
    offenders = []
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        source = path.read_text(encoding="utf-8")
        if "_PRE_098_REFERENCE_VERSE_V1_SHA256" in source:
            offenders.append(path.name)
    assert not offenders, (
        f"these modules still contain _PRE_098_REFERENCE_VERSE_V1_SHA256: "
        f"{offenders}"
    )


# =========================================================================== #
# AC11: test_098's docstring points at the new home
# =========================================================================== #


def test_ac11_test098_docstring_no_longer_claims_the_byte_pin():
    module_path = _REPO_ROOT / "tests" / "test_098_stray_components.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    docstring = ast.get_docstring(tree) or ""
    assert "reference_verse_v1.json" in docstring, (
        "expected the docstring to still name the artifact when pointing "
        "elsewhere"
    )
    # The pre-item AC18 bullet's literal wording -- must not survive verbatim
    # once the bullet is repointed at the new module.
    assert "byte-untouched (pinned sha256)" not in docstring, (
        "test_098's docstring still describes carrying the byte pin itself: "
        f"{docstring!r}"
    )


def test_ac11_test098_docstring_names_the_new_home():
    module_path = _REPO_ROOT / "tests" / "test_098_stray_components.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    docstring = ast.get_docstring(tree) or ""
    assert _NEW_MODULE_NAME in docstring, (
        f"test_098's docstring does not name {_NEW_MODULE_NAME} as the new home"
    )


# =========================================================================== #
# AC12: item 123's reconciliation test follows the pin
# =========================================================================== #


def test_ac12_test123_imports_digest_from_new_module_not_test098():
    module_path = _REPO_ROOT / "tests" / "test_123_recalibrate_and_regenerate.py"
    source = module_path.read_text(encoding="utf-8")
    assert "from test_098_stray_components import _PRE_098_REFERENCE_VERSE_V1_SHA256" not in source, (
        "test_123 still imports the retired identifier from test_098"
    )
    tree = ast.parse(source, filename=str(module_path))
    imports_new = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "test_128_reference_verse_v1_integrity"
        for node in ast.walk(tree)
    )
    assert imports_new, (
        "test_123 does not import from test_128_reference_verse_v1_integrity"
    )


# =========================================================================== #
# AC13: Stage 26's one-fence cap holds at the new location
# =========================================================================== #


def test_ac13_test115_fence_cap_still_passes_and_points_at_new_module():
    import test_115_stage26_validation as mod115

    mod115.test_ac8_no_hardcoded_literal_fence_remains()  # must not raise

    findings = mod115._all_sha256_findings()
    fences = [f for f in findings if f.kind == "fence"]
    assert len(fences) <= 1
    if fences:
        assert fences[0].path.name == _NEW_MODULE_NAME, (
            f"the surviving fence is at {fences[0].path.name!r}, expected "
            f"{_NEW_MODULE_NAME!r}"
        )


def test_ac13_new_module_itself_classifies_as_the_one_fence():
    """Direct check on the new module in isolation, independent of whatever
    else lives under tests/ -- proves the fence moved with the pin rather
    than merely being absent everywhere (which would also make the cap
    test pass, vacuously)."""
    import test_115_stage26_validation as mod115

    findings = mod115._classify_sha256_compares(_NEW_MODULE_PATH)
    fences = [f for f in findings if f.kind == "fence"]
    assert len(fences) == 1, (
        f"expected exactly one fence-shaped comparison in {_NEW_MODULE_NAME}, "
        f"got {fences}"
    )


# =========================================================================== #
# AC14: .gitattributes coverage is asserted, not assumed
# =========================================================================== #


def test_ac14_git_check_attr_reports_text_set_and_eol_lf():
    result = run_utf8(
        ["git", "check-attr", "text", "eol", "--", _ARTIFACT_REL_POSIX],
        cwd=_REPO_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert output.strip(), "git check-attr produced no output"
    file_lines = [
        line for line in output.splitlines() if line.startswith(f"{_ARTIFACT_REL_POSIX}:")
    ]
    assert file_lines, f"git check-attr reported nothing for {_ARTIFACT_REL_POSIX}"
    assert any("text: set" in line for line in file_lines), output
    assert any("eol: lf" in line for line in file_lines), output


# =========================================================================== #
# AC15: the artifact-specific pin line survives
# =========================================================================== #


def test_ac15_artifact_specific_pin_line_present_and_more_specific_than_catchall():
    import fnmatch

    attrs_text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    lines = [l.strip() for l in attrs_text.splitlines() if l.strip() and not l.strip().startswith("#")]

    catchall_lines = [
        l for l in lines if l.split()[0] == "src/segfacet/**/*.json"
    ]
    specific_lines = [
        l
        for l in lines
        if fnmatch.fnmatch(_ARTIFACT_REL_POSIX, l.split()[0]) and l not in catchall_lines
    ]
    assert specific_lines, (
        ".gitattributes has no artifact-specific pin line covering "
        f"{_ARTIFACT_REL_POSIX!r} beyond the catch-all"
    )
    for line in specific_lines:
        assert line.split()[0] != "src/segfacet/**/*.json"


def test_ac15_specific_line_pattern_names_reference_verse():
    attrs_text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    lines = [l.strip() for l in attrs_text.splitlines()]
    matching = [l for l in lines if "reference_verse" in l and "eol=lf" in l]
    assert matching, (
        ".gitattributes has no reference_verse*-specific text eol=lf line"
    )


# =========================================================================== #
# AC16: test_102's section header names the real property
# =========================================================================== #

# A "banner" in this codebase's convention is a three-line block: a
# ``# ===...=== #`` delimiter, one or more title/comment lines, and a
# matching closing delimiter. Several unrelated ``def``s can sit under one
# banner (as here: ``_combined_hash``, ``_src_tree_files``, the
# ``_SRC_TREE_HASH_AT_COLLECTION`` constant, and finally the test), so "the
# comment header immediately preceding" the target function means the
# nearest such banner walking backward, not the literal line directly above
# the ``def``.
_BANNER_RE = re.compile(r"(?m)^# ={10,}.*\n((?:#(?!\s*=).*\n)+)# ={10,}.*\n")


def _nearest_preceding_banner_text(source: str, function_name: str) -> str:
    target_offset = source.find(f"def {function_name}")
    assert target_offset != -1, f"{function_name!r} not found in source"
    matches = [m for m in _BANNER_RE.finditer(source) if m.end() <= target_offset]
    assert matches, f"no banner comment block found before {function_name!r}"
    return matches[-1].group(1)


def test_ac16_test102_header_no_longer_says_scope_fence_or_no_production_code():
    module_path = _REPO_ROOT / "tests" / "test_102_stage18_validation.py"
    source = module_path.read_text(encoding="utf-8")
    header_text = _nearest_preceding_banner_text(
        source, "test_ac24_src_tree_is_byte_identical_across_the_test_run"
    )
    assert "scope fence" not in header_text.lower(), header_text
    assert "no production code changed by this item" not in header_text.lower(), header_text
    assert (
        "intra-run" in header_text.lower()
        or "non-mutation" in header_text.lower()
        or "byte-identical" in header_text.lower()
    ), header_text


def test_ac16_comment_above_src_tree_hash_constant_reworded_too():
    module_path = _REPO_ROOT / "tests" / "test_102_stage18_validation.py"
    source = module_path.read_text(encoding="utf-8")
    match = re.search(r"(?:^#.*\n)+_SRC_TREE_HASH_AT_COLLECTION\s*=", source, re.MULTILINE)
    assert match, "no comment block found immediately above _SRC_TREE_HASH_AT_COLLECTION"
    comment_block = match.group(0)
    assert "scope fence" not in comment_block.lower()
    assert "no production code changed by this item" not in comment_block.lower()


# =========================================================================== #
# AC17: test_102's docstring drops the false pre-102 claim
# =========================================================================== #


def test_ac17_test102_docstring_no_longer_claims_pre_102():
    module_path = _REPO_ROOT / "tests" / "test_102_stage18_validation.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    target = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "test_ac24_src_tree_is_byte_identical_across_the_test_run"
        ),
        None,
    )
    assert target is not None
    docstring = ast.get_docstring(target) or ""
    assert "pre-102" not in docstring, (
        f"docstring still claims a pre-102 state: {docstring!r}"
    )
    assert "collection" in docstring.lower(), (
        "docstring does not state the comparison is against the "
        "collection-time hash"
    )


# =========================================================================== #
# AC18: test_102's assertion is behaviourally unchanged
# =========================================================================== #


def test_ac18_assertion_body_still_compares_combined_hash_to_collection_constant():
    module_path = _REPO_ROOT / "tests" / "test_102_stage18_validation.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    target = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "test_ac24_src_tree_is_byte_identical_across_the_test_run"
        ),
        None,
    )
    assert target is not None
    segment = ast.get_source_segment(source, target) or ""
    assert "_combined_hash(_src_tree_files(), _SEGFACET_SRC)" in segment
    assert "_SRC_TREE_HASH_AT_COLLECTION" in segment
    assert "_SRC_TREE_HASH_AT_COLLECTION =" in source, (
        "module no longer defines _SRC_TREE_HASH_AT_COLLECTION at module scope"
    )


def test_ac18_test102_module_still_defines_the_collection_constant_at_module_scope():
    module_path = _REPO_ROOT / "tests" / "test_102_stage18_validation.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    module_level_names = {
        stmt.targets[0].id
        for stmt in tree.body
        if isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
    }
    assert "_SRC_TREE_HASH_AT_COLLECTION" in module_level_names


# =========================================================================== #
# AC19/AC20: decision table -- pointer resolves, signed cells untouched
# =========================================================================== #

# The four signed cells of Section 2's reference_verse_v1.json row, captured
# from the document as it stood before this item touched it (2026-08-31).
# AC20 requires these compared as PLAIN STRINGS -- see the module docstring's
# note on why a digest here would create a second fence and turn AC13 red.
_PRE_ITEM_WHAT_IT_ASSERTS_TODAY = (
    "The VerSe-derived reference-distribution artifact built from mounted "
    "ground truth is sha256-pinned; it is not regenerable in CI, so the pin "
    "is the only thing standing between it and silent corruption."
)
_PRE_ITEM_EVIDENCE = "n/a"
_PRE_ITEM_DISPOSITION = "keep"
_PRE_ITEM_REPLACEMENT_GUARANTEE = "—"  # em dash, as rendered in the table


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


def _parse_first_pipe_table(section_text: str):
    table_lines = [l.strip() for l in section_text.splitlines() if l.strip().startswith("|")]
    if len(table_lines) < 2:
        raise AssertionError("no well-formed pipe table found")
    header_cells = [re.sub(r"\s+", " ", c.strip()).lower() for c in _table_cells(table_lines[0])]
    rows = []
    for line in table_lines[2:]:
        raw_cells = _table_cells(line)
        if len(raw_cells) != len(header_cells):
            continue
        rows.append(dict(zip(header_cells, raw_cells)))
    return rows


def _section2_reference_verse_v1_row() -> dict:
    text = _DECISION_TABLE.read_bytes().decode("utf-8")
    sections = _split_sections(text)
    rows = _parse_first_pipe_table(sections["Section 2 — Adjacent exact-match artifacts (outside tests/)"])
    matches = [r for r in rows if r["fixture"] == _ARTIFACT_REL_POSIX]
    assert len(matches) == 1, (
        f"expected exactly one Section-2 row for {_ARTIFACT_REL_POSIX!r}, "
        f"got {len(matches)}"
    )
    return matches[0]


def test_ac19_asserted_by_cell_names_the_relocated_test_id():
    row = _section2_reference_verse_v1_row()
    asserted_by = row["asserted by"]
    assert "test_098_stray_components.py" not in asserted_by, (
        f"asserted-by cell still names test_098_stray_components.py: {asserted_by!r}"
    )
    assert _NEW_MODULE_NAME in asserted_by, (
        f"asserted-by cell does not name {_NEW_MODULE_NAME!r}: {asserted_by!r}"
    )


def test_ac20_the_other_four_cells_are_character_for_character_unchanged():
    """AC20 -- compared as plain strings, deliberately NOT via a digest (see
    module docstring: a hashlib.sha256(...) == '<literal>' shape here would
    be classified 'fence' by test_115's shape-based scanner and break AC13's
    at-most-one-fence cap)."""
    row = _section2_reference_verse_v1_row()
    assert row["what it asserts today"] == _PRE_ITEM_WHAT_IT_ASSERTS_TODAY
    assert row["evidence"] == _PRE_ITEM_EVIDENCE
    assert row["disposition"] == _PRE_ITEM_DISPOSITION
    assert row["replacement guarantee"] == _PRE_ITEM_REPLACEMENT_GUARANTEE


def test_adv_whitespace_only_cell_drift_is_caught_by_the_string_comparison():
    """Adversarial: a decision-table row with a trailing-space-only change to
    a signed cell must still be caught -- the AC20 comparison must not be
    accidentally whitespace-tolerant."""
    drifted = _PRE_ITEM_DISPOSITION + " "
    assert drifted != _PRE_ITEM_DISPOSITION
    row = {"disposition": drifted}
    with pytest.raises(AssertionError):
        assert row["disposition"] == _PRE_ITEM_DISPOSITION


# =========================================================================== #
# AC21/AC22: item 127's guard stays clean and its allowlist is unchanged
# =========================================================================== #


def test_ac21_guard_reports_zero_violations_over_the_post_item_tests_tree():
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(_TESTS_DIR))
    assert not violations, guard.violation_message(violations)


def test_ac22_allowlist_still_carries_the_integrity_pin_entry():
    import committed_artifact_guard as guard

    matching = [
        entry
        for entry in guard.ALLOWLIST
        if entry.path == _ARTIFACT_REL_POSIX and entry.ground == "integrity-pin"
    ]
    assert len(matching) == 1, (
        f"expected exactly one ALLOWLIST entry for {_ARTIFACT_REL_POSIX!r} "
        f"with ground 'integrity-pin', found {len(matching)}"
    )


def test_ac22_guard_module_absent_from_this_items_diff():
    result = None
    for base_ref in ("origin/aide/queue-018", "aide/queue-018"):
        result = run_utf8(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD", "--"],
            cwd=_REPO_ROOT,
            timeout=30,
        )
        if result.returncode == 0:
            break
    if result is None or result.returncode != 0:
        pytest.skip(f"git diff against the recorded base is unavailable: {result.stderr if result else 'no ref resolved'}")
    changed = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    assert "tests/committed_artifact_guard.py" not in changed, (
        "tests/committed_artifact_guard.py appears in this item's diff, but "
        "AC22 requires it stay untouched"
    )


# =========================================================================== #
# AC23: aide check reports no new warning
# =========================================================================== #


def _aide_check_warnings() -> list:
    """Return `aide check`'s warnings as a list of strings.

    Calls ``run_checks`` in-process rather than shelling out to
    ``aide.py check``: that subprocess shape is exactly what engine 1.21.0's
    `cli_subprocess_test_warnings` lint flags, so a subprocess-based version
    of this test would make this module report a warning about itself and
    could never reach a clean `aide check`. ``run_checks`` is the same
    function ``cmd_check`` calls; it returns ``(errors, warnings)`` as
    structured data, so there is no stdout, no encoding and no subprocess to
    go wrong.
    """
    spec = importlib.util.spec_from_file_location("_aide_cli_128", _AIDE_SCRIPT)
    aide = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aide)
    repo_root = aide.find_repo_root(_REPO_ROOT)
    _errors, warnings = aide.run_checks(repo_root, aide.load_config(repo_root))
    return list(warnings)


def test_ac23_aide_check_emits_no_gitattributes_lint_warning():
    """AC23: relocating the ``reference_verse_v1`` byte pin must not trip
    engine 1.19.0's fixture-pin lint (``gitattributes_eol_pin_warnings``,
    which names its own path in the warning text as "compares ... byte-for-
    byte" plus either "this repo has no .gitattributes" or "no .gitattributes
    `eol=lf` pin covers it" -- see ``.aide/scripts/aide.py``).

    This used to also assert that `aide check`'s *entire* warning set held
    nothing beyond two named baseline categories. That pin was wider than
    AC23: `aide merge`'s own sequence is claim-branch merge -> mark item
    (fully-check)-> re-run the suite -> delete the claim branch, so a
    transient "stale claim branch aide/NNN-... is already (fully-check)"
    warning is live during that re-test window on *every* item's merge, not
    just this one -- measured 2026-08-31 during item 128's own `aide merge`,
    which turned this test red for a warning AC23 never claimed to forbid.
    Scoped down to what the AC actually protects: no gitattributes-lint
    warning, and no warning naming either the relocated artifact or its new
    home.
    """
    warnings = _aide_check_warnings()
    gitattributes_lint = [
        warning
        for warning in warnings
        if ".gitattributes" in warning and "compares" in warning and "byte-for-byte" in warning
    ]
    assert not gitattributes_lint, (
        f"aide check emitted a .gitattributes fixture-pin lint warning:\n{gitattributes_lint}"
    )
    assert not any(_ARTIFACT_REL_POSIX in warning for warning in warnings), (
        f"aide check named {_ARTIFACT_REL_POSIX!r} in a warning:\n{warnings}"
    )
    assert not any(_NEW_MODULE_NAME in warning for warning in warnings), (
        f"aide check named the new module in a warning:\n{warnings}"
    )


# =========================================================================== #
# Adversarial: the classifier's blind spot the item spec warns about
# =========================================================================== #


def test_adv_helper_function_indirection_is_invisible_to_the_classifier(monkeypatch):
    """Confirms the queue's own stated failure mode: a relocation that pins
    the artifact through a helper-function call (e.g. reverting to
    ``bundled_production_reference_path()`` instead of the required
    repo-root-relative literal chain) is invisible to item 127's classifier
    even with the allowlist emptied -- exactly why AC6 requires the literal
    form and this test exists as the negative control."""
    import committed_artifact_guard as guard

    monkeypatch.setattr(guard, "ALLOWLIST", ())
    source = (
        "import hashlib\n"
        "from segfacet.reference.artifact import bundled_production_reference_path\n"
        "\n"
        "_RELEASED_REFERENCE_VERSE_V1_SHA256 = (\n"
        f'    "{_RELEASED_DIGEST}"\n'
        ")\n"
        "\n"
        "def test_pin():\n"
        "    path = bundled_production_reference_path()\n"
        "    digest = hashlib.sha256(path.read_bytes()).hexdigest()\n"
        "    assert digest == _RELEASED_REFERENCE_VERSE_V1_SHA256\n"
    )
    violations = guard.classify_module(source, "tests/test_zz_synthetic_helper_indirection.py")
    matching = [v for v in violations if v.committed_path == _ARTIFACT_REL_POSIX]
    assert not matching, (
        "a helper-function-indirected pin should be invisible to the "
        f"classifier (that is exactly the trap AC6 exists to avoid); got "
        f"{violations}"
    )


def test_adv_scope_fence_header_in_different_case_still_trips_ac16():
    """A header spelled 'SCOPE FENCE' (different case) must still be caught
    by a case-insensitive check -- a builder cannot dodge AC16 by changing
    case rather than wording."""
    synthetic_header = "# AC24: THE SCOPE FENCE -- no production code changed by this item"
    assert "scope fence" not in synthetic_header, (
        "sanity: exact-case substring search would miss this synthetic header"
    )
    assert "scope fence" in synthetic_header.lower(), (
        "sanity: case-insensitive search should catch it"
    )


def test_adv_synthetic_helper_indirection_is_flagged_once_expressed_as_a_literal():
    """Paired positive control for the helper-indirection adversarial case
    above: the same digest pinned via the required repo-root-relative
    literal chain (two .parent hops, per committed_artifact_guard's
    _is_file_root_chain) IS flagged with the allowlist emptied -- proving
    the negative control isn't just a broken synthetic module."""
    import committed_artifact_guard as guard

    source = (
        "import hashlib\n"
        "from pathlib import Path\n"
        "\n"
        "_ARTIFACT = (\n"
        "    Path(__file__).resolve().parent.parent\n"
        '    / "src" / "segfacet" / "reference" / "reference_verse_v1.json"\n'
        ")\n"
        "_RELEASED_REFERENCE_VERSE_V1_SHA256 = (\n"
        f'    "{_RELEASED_DIGEST}"\n'
        ")\n"
        "\n"
        "def test_pin():\n"
        "    digest = hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()\n"
        "    assert digest == _RELEASED_REFERENCE_VERSE_V1_SHA256\n"
    )
    original_allowlist = guard.ALLOWLIST
    try:
        guard.ALLOWLIST = ()
        violations = guard.classify_module(source, "tests/test_zz_synthetic_literal_pin.py")
    finally:
        guard.ALLOWLIST = original_allowlist
    matching = [v for v in violations if v.committed_path == _ARTIFACT_REL_POSIX]
    assert matching, (
        "the literal-chain form should be visible to the classifier with "
        f"the allowlist emptied; got {violations}"
    )
