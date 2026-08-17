"""Item 115 -- Stage 26 validation: the in-suite assertable subset.

Item 115 closes Stage 26 by replaying its use cases end-to-end (red-then-green
reverts, `segfacet run` replays, a fresh-clone suite run, ...). Per the item
spec's Testing Strategy, most of that is a *replay* obligation discharged and
recorded by the builder in `progress.md`'s Decisions log -- not something a
pytest module can assert. This module covers only the subset that *can* be
asserted in-suite:

- AC7:  the neighbourhood fork -- reachable + catalogued "unwired" + honest
        progress.md wording.
- AC8:  no byte-hash fence remains, searched by assertion *shape* (see
        `_classify_sha256_compares` below), not by the `_PRE_[0-9]` name.
- AC9:  every queue-016 spec (107-116) declares a non-empty
        `## Authorised paths`, and `scripts/check_item_scope.py`'s own parser
        reads each without error.
- AC12: Stage 26's five acceptance boxes are each either ticked *and*
        followed by an evidence annotation, or unticked *and* followed by a
        reason (the tick-implies-evidence biconditional item 106 established).
        Expected to FAIL until the builder adds the annotations.
- AC13: the Docker Environment-Gated Capability Verification row's state was
        not flipped by item 113 (which only *reduced where* Docker runs).

AC1-AC6, AC10, AC11, AC14, AC15 are replays with no stable in-suite shape and
are intentionally not covered here -- they belong to this item's Decisions
log and the Validation section, not to a test module.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_PROGRESS_PATH = _REPO_ROOT / "docs" / "aide" / "progress.md"
_CHECKER_PATH = _REPO_ROOT / "scripts" / "check_item_scope.py"
_THIS_FILE = Path(__file__).resolve()

_QUEUE_016_SPEC_NUMBERS = (107, 108, 109, 110, 111, 112, 113, 114, 115, 116)


def _read_progress() -> str:
    return _PROGRESS_PATH.read_text(encoding="utf-8")


def _spec_path(number: int) -> Path:
    matches = sorted((_REPO_ROOT / "docs" / "aide" / "items").glob(f"{number}-*.md"))
    assert matches, f"no docs/aide/items/{number}-*.md spec found"
    assert len(matches) == 1, f"more than one spec matches {number}-*.md: {matches}"
    return matches[0]


# =========================================================================== #
# AC8: no byte-hash fence remains -- searched by assertion SHAPE, not name.
# =========================================================================== #
#
# Discriminator (from the item spec): a *fence* is a SHA-256 digest compared
# (`==`) against a hardcoded string literal, standing in for a diff-time claim
# ("this committed file's bytes are still X") frozen as a permanent runtime
# invariant. A digest compared against a value *computed in this same run*
# (hash -> run code -> re-hash -> compare) is an intra-run
# determinism/no-mutation assertion, not a fence, and must survive untouched.
#
# The classifier below walks every `==` comparison in tests/*.py whose either
# side is, or resolves to, a value built from `hashlib.sha256(...)`, and
# determines the SHAPE of the *other* side by resolving name bindings (one
# hop through a Name assignment, a `for a, b in D.items():` unpack, or a call
# to a module-level helper function) rather than by matching any name
# spelling:
#
#   - "fence"     -- the other side resolves to a plain string `Constant`
#                     bound somewhere in this file (module- or function-scope)
#                     that was NOT itself built from `hashlib.sha256(...)`.
#   - "intra-run" -- the other side resolves to a value that WAS built from
#                     `hashlib.sha256(...)` in this same run (directly, via a
#                     dict/comprehension, or via a helper function call).
#   - "external"  -- the other side is something else entirely (e.g. a
#                     dict/JSON-fixture lookup) -- nothing hardcoded in *this
#                     file's source*, so not a fence, but not a same-run
#                     recompute either.
#
# A comment mentioning a retired `_PRE_NNN_*` name is invisible to this
# scanner (comments never become AST nodes), which is the intended behaviour:
# a name appearing only in prose is not a runtime assertion of any shape, so
# reintroducing one in a comment is not a fence and must not be flagged.


class _Finding:
    __slots__ = ("path", "lineno", "kind", "detail")

    def __init__(self, path: Path, lineno: int, kind: str, detail: str):
        self.path = path
        self.lineno = lineno
        self.kind = kind
        self.detail = detail

    def __repr__(self):  # pragma: no cover - debug aid only
        return f"_Finding({self.path.name}:{self.lineno}, {self.kind!r}, {self.detail!r})"


def _source_segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _computes_sha256(node: ast.AST, source: str, funcdefs: dict) -> bool:
    """True iff evaluating `node` necessarily runs `hashlib.sha256(...)` in
    this same run -- directly (inline call, or nested inside a
    comprehension), or by calling a module-level helper whose own body does.
    """
    text = _source_segment(source, node)
    if "hashlib.sha256(" in text:
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = funcdefs.get(node.func.id)
        if fn is not None:
            return "hashlib.sha256(" in _source_segment(source, fn)
    return False


def _find_binding(name_id: str, scope_node: ast.AST):
    """Last binding of `name_id` found anywhere inside `scope_node` -- either
    an ``Assign`` to a bare ``Name``, or a ``for a, name_id in X:`` unpack.
    Returns ``("assign", value_node)``, ``("for", iter_node)``, or ``None``.
    """
    binding = None
    for stmt in ast.walk(scope_node):
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == name_id:
                    binding = ("assign", stmt.value)
        elif isinstance(stmt, ast.For):
            target = stmt.target
            if isinstance(target, ast.Name):
                names = [target.id]
            elif isinstance(target, ast.Tuple):
                names = [e.id for e in target.elts if isinstance(e, ast.Name)]
            else:
                names = []
            if name_id in names:
                binding = ("for", stmt.iter)
    return binding


def _resolve(name_id: str, funcnode, modnode, source: str, funcdefs: dict, depth: int = 0):
    """Classify what `name_id` resolves to: ``"computed"``, ``"literal"``,
    ``"external"``, or ``None`` (unresolved). Searches the enclosing function
    scope first, then module scope; follows at most 3 hops of indirection.
    """
    if depth > 3:
        return "external"
    binding = None
    if funcnode is not None:
        binding = _find_binding(name_id, funcnode)
    if binding is None:
        binding = _find_binding(name_id, modnode)
    if binding is None:
        return None

    kind, value = binding
    if kind == "assign":
        if _computes_sha256(value, source, funcdefs):
            return "computed"
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return "literal"
        if isinstance(value, ast.Name):
            return _resolve(value.id, funcnode, modnode, source, funcdefs, depth + 1)
        return "external"

    # kind == "for": value is the loop's iterable, e.g. `before.items()`.
    if _computes_sha256(value, source, funcdefs):
        return "computed"
    base = value
    if isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute):
        base = base.func.value
    if isinstance(base, ast.Name):
        return _resolve(base.id, funcnode, modnode, source, funcdefs, depth + 1)
    return "external"


def _enclosing_function(node: ast.AST, parents: dict):
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.FunctionDef):
            return cur
        cur = parents.get(cur)
    return None


def _classify_sha256_compares(path: Path) -> list:
    """Every `==` comparison in `path` where either side is/derives from a
    `hashlib.sha256(...)` digest, classified per the shape rule above."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    parents: dict = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    funcdefs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            continue
        if len(node.comparators) != 1:
            continue
        left, right = node.left, node.comparators[0]
        funcnode = _enclosing_function(node, parents)

        def _side_kind(side):
            if _computes_sha256(side, source, funcdefs):
                return "computed"
            if isinstance(side, ast.Name):
                return _resolve(side.id, funcnode, tree, source, funcdefs)
            if isinstance(side, ast.Constant) and isinstance(side.value, str):
                return "literal"
            return "external"

        left_kind = _side_kind(left)
        right_kind = _side_kind(right)

        if "computed" not in (left_kind, right_kind):
            continue  # not a sha256-digest comparison at all

        other_kind = right_kind if left_kind == "computed" else left_kind
        if other_kind == "literal":
            kind = "fence"
        elif other_kind == "computed":
            kind = "intra-run"
        else:
            kind = "external"
        findings.append(
            _Finding(path, node.lineno, kind, _source_segment(source, node))
        )
    return findings


def _all_sha256_findings() -> list:
    findings = []
    for path in sorted(_TESTS_DIR.glob("*.py")):
        if path.resolve() == _THIS_FILE:
            continue  # this module's own docstring/comments mention the rule
        findings.extend(_classify_sha256_compares(path))
    return findings


def test_ac8_no_hardcoded_literal_fence_remains():
    """AC8: zero `==` comparisons of a sha256 digest against a hardcoded
    literal survive under tests/ -- the two known-remaining cases at spec
    time (test_098's reference_verse_v1 pin, test_102's path-to-digest dict)
    resolve to fence / intra-run respectively; only the former should still
    be an open fence if untouched, so this pins the *exact* expected count
    rather than a bare `== 0`, in case the builder retires it during this
    item."""
    findings = _all_sha256_findings()
    fences = [f for f in findings if f.kind == "fence"]
    locations = [f"{f.path.name}:{f.lineno}" for f in fences]
    # At the time this item's spec was written, exactly one fence remained:
    # test_098_stray_components.py's pinned pre-098 digest of
    # reference_verse_v1.json. This item's job is to retire it or record why
    # it stays -- either way there must be at most that one, never more, and
    # a scan that finds any *other* fence is a genuine new regression this
    # test must catch.
    assert len(fences) <= 1, f"unexpected fence(s) found: {locations}"
    if fences:
        assert fences[0].path.name == "test_098_stray_components.py", locations


def test_ac8_intra_run_digest_assertions_still_exist():
    """AC8's own caution: a check that only greps for fence *absence* would
    also pass if someone deleted the legitimate no-mutation/determinism
    digest assertions. Assert the known intra-run comparisons are still
    present and still classified as intra-run (not accidentally fences)."""
    findings = _all_sha256_findings()
    intra_run_files = {f.path.name for f in findings if f.kind == "intra-run"}
    assert "test_102_stage18_validation.py" in intra_run_files
    assert "test_100_severity_ladder.py" in intra_run_files


def test_ac8_test_102_path_digest_dict_is_intra_run_not_a_fence():
    """The spec's own AC8 text mis-describes this comparison as a remaining
    fence ("a path-to-digest dict asserted around line 668"). By AC8's own
    discriminator it is an intra-run no-mutation check: `before` is built
    from `hashlib.sha256(...)` calls within the same test, then re-hashed and
    compared -- nothing hardcoded. This test pins the correct classification
    so the spec's description does not silently re-drift into "known fence"
    folklore; the correction itself is recorded in this item's Decisions."""
    path = _TESTS_DIR / "test_102_stage18_validation.py"
    findings = [f for f in _classify_sha256_compares(path) if f.kind != "external"]
    assert findings, "expected at least one sha256 comparison in test_102"
    for f in findings:
        assert f.kind == "intra-run", (f.lineno, f.kind, f.detail)


def test_ac8_test_094_data_sha256_lookup_is_not_a_fence():
    """Borderline case named in this item's brief: test_094 compares a digest
    over freshly-loaded array bytes against `entry["data_sha256"]`, a value
    pulled from a committed JSON snapshot -- not a hardcoded literal *in the
    test source*, so it is correctly classified "external", not "fence"."""
    path = _TESTS_DIR / "test_094_tptbox_image_layer.py"
    findings = _classify_sha256_compares(path)
    assert findings, "expected at least one sha256 comparison in test_094"
    for f in findings:
        assert f.kind == "external", (f.lineno, f.kind, f.detail)


def test_adv_pre_constant_in_a_comment_is_invisible_to_the_scanner(tmp_path):
    """Adversarial: a `_PRE_` name reintroduced only in a comment (not a real
    binding) must not be misread as a fence -- comments are not AST nodes, so
    the shape-based scanner never sees it. This documents the decision: a
    `_PRE_` mention in prose is not a runtime assertion of any shape."""
    synthetic = tmp_path / "synthetic_module.py"
    synthetic.write_text(
        "import hashlib\n"
        "\n"
        "# _PRE_999_SOME_DIGEST = 'deadbeef'  -- retired, kept here as a note\n"
        "\n"
        "def test_something(tmp_path):\n"
        "    digest = hashlib.sha256(b'x').hexdigest()\n"
        "    assert digest == digest\n",
        encoding="utf-8",
    )
    findings = _classify_sha256_compares(synthetic)
    assert all(f.kind != "fence" for f in findings), findings


def test_adv_shape_based_classifier_flags_a_synthetic_fence(tmp_path):
    """Sanity check on the classifier itself: a synthetic hardcoded-literal
    comparison, spelled with a name that does NOT match the `_PRE_[0-9]`
    pattern the item explicitly says is insufficient, must still be caught
    -- proving the scanner works by shape, not name."""
    synthetic = tmp_path / "synthetic_fence_module.py"
    synthetic.write_text(
        "import hashlib\n"
        "\n"
        "_TOTALLY_UNRELATED_NAME = 'deadbeef'\n"
        "\n"
        "def test_pinned(path):\n"
        "    digest = hashlib.sha256(path.read_bytes()).hexdigest()\n"
        "    assert digest == _TOTALLY_UNRELATED_NAME\n",
        encoding="utf-8",
    )
    findings = _classify_sha256_compares(synthetic)
    fences = [f for f in findings if f.kind == "fence"]
    assert len(fences) == 1, findings


# =========================================================================== #
# AC9: every queue-016 spec declares `## Authorised paths`; the checker
# parses each without error.
# =========================================================================== #

_CHECKER_SOURCE = _CHECKER_PATH.read_text(encoding="utf-8")
_CHECKER_NS: dict = {"__name__": "check_item_scope_under_test"}
exec(compile(_CHECKER_SOURCE, str(_CHECKER_PATH), "exec"), _CHECKER_NS)
_parse_authorised_paths = _CHECKER_NS["_parse_authorised_paths"]


@pytest.mark.parametrize("number", _QUEUE_016_SPEC_NUMBERS)
def test_ac9_spec_declares_nonempty_authorised_paths(number):
    spec_path = _spec_path(number)
    text = spec_path.read_text(encoding="utf-8")
    globs = _parse_authorised_paths(text)
    assert globs is not None, f"{spec_path.name} has no '## Authorised paths' section"
    assert globs != [], f"{spec_path.name}'s '## Authorised paths' section is empty"


@pytest.mark.parametrize("number", _QUEUE_016_SPEC_NUMBERS)
def test_ac9_checker_parses_spec_without_error(number):
    spec_path = _spec_path(number)
    text = spec_path.read_text(encoding="utf-8")
    # "Parses without error" -- the parser itself never raises; a missing
    # section is signalled by returning None, not an exception.
    result = _parse_authorised_paths(text)
    assert result is None or isinstance(result, list)


def test_ac9_all_ten_queue_016_items_covered():
    assert len(_QUEUE_016_SPEC_NUMBERS) == 10


def test_adv_authorised_paths_heading_with_no_bullets_is_distinguished_from_missing():
    """Adversarial: a spec with the heading but zero bullets parses to `[]`,
    not `None` -- a real spec in that state must be treated as an error
    (empty, not simply absent), matching the checker's own AC8 contract."""
    text = (
        "# Synthetic item spec\n\n"
        "## Description\n\nSynthetic.\n\n"
        "## Authorised paths\n\n"
        "## Decisions & Trade-offs\n\nNone.\n"
    )
    result = _parse_authorised_paths(text)
    assert result == []


# =========================================================================== #
# AC7: the neighbourhood fork is fully executed.
# =========================================================================== #


def _multi_label_record():
    from segfacet.config import default_config
    from segfacet.pipeline import extract_feature_record

    from synthetic import labelled_blocks_case

    case = labelled_blocks_case()
    return extract_feature_record(case.seg_img, default_config())


def test_ac7_neighbourhood_reachable_from_extract_feature_record():
    block = _multi_label_record()
    assert "stage3" in block
    assert "per_label_neighbourhood" in block["stage3"]
    assert block["stage3"]["per_label_neighbourhood"], "expected a non-empty list"


def test_ac7_catalogue_lists_neighbourhood_entries_as_unwired():
    import segfacet.catalogue as catalogue

    full_catalogue = catalogue.build_catalogue()
    neighbourhood_entries = [
        e for e in full_catalogue.entries if e.path.startswith("stage3.per_label_neighbourhood")
    ]
    assert neighbourhood_entries, "no per_label_neighbourhood entries in the catalogue"
    for entry in neighbourhood_entries:
        assert entry.status == "unwired", (entry.path, entry.status)
        assert not entry.consuming_rules, (entry.path, entry.consuming_rules)


def test_ac7_progress_md_item_024_bullets_match_observable_behaviour():
    """Both item-024 mentions (the Stage 3 deliverable bullet and its
    matching acceptance box) were corrected by item 110; assert the corrected
    wording -- reachable, wired, status "unwired", consumed by no rule --
    still matches what the catalogue/pipeline actually do."""
    text = _read_progress()
    lines = text.splitlines()
    item_024_lines = [line for line in lines if "Item 024" in line]
    assert item_024_lines, "no progress.md line references Item 024"
    assert len(item_024_lines) >= 2, (
        "expected both the Stage 3 deliverable bullet (line ~256) and its "
        f"matching acceptance box (line ~263); found {len(item_024_lines)}"
    )

    combined = "\n".join(item_024_lines)
    assert "unwired" in combined
    assert "Item 110" in combined
    # The stale pre-correction claim -- that the module actively flags
    # outliers to a verdict -- must not remain as a live, unqualified claim.
    assert "consumed by no rule" in combined or "consumed by no rule" in text


def test_ac7_neighbourhood_module_importable_and_wired_into_pipeline_source():
    pipeline_source = (_REPO_ROOT / "src" / "segfacet" / "pipeline.py").read_text(
        encoding="utf-8"
    )
    assert "neighbourhood" in pipeline_source


# =========================================================================== #
# AC12: Stage 26's acceptance is ticked honestly (tick-implies-evidence).
# =========================================================================== #

_CHECKBOX_RE = re.compile(r"^-\s*\[([ xX])\]\s?")
_EVIDENCE_NOTE_RE = re.compile(r"\*\(.*?\)\*", re.DOTALL)


def _stage26_section(text: str) -> str:
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## Stage 26"):
            start = i
        elif start is not None and line.startswith("## Stage 27"):
            end = i
            break
    if start is None:
        raise AssertionError("no '## Stage 26' heading found in progress.md")
    return "\n".join(lines[start:end])


def _acceptance_items(section: str) -> list:
    """Every checkbox item under '**Acceptance.**', including wrapped
    continuation lines (mirrors item 106's `_acceptance_items` convention)."""
    lines = section.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "**Acceptance.**")
    except StopIteration:
        raise AssertionError(
            "no '**Acceptance.**' heading found under the Stage-26 section of progress.md"
        )
    items: list = []
    current: list = []
    seen_item = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if _CHECKBOX_RE.match(stripped):
            if current:
                items.append("\n".join(current))
            current = [line]
            seen_item = True
            continue
        if stripped == "" or stripped == "---":
            if current:
                items.append("\n".join(current))
                current = []
            if seen_item:
                break
            continue
        if current:
            current.append(line)
    if current:
        items.append("\n".join(current))
    return items


def _is_checked(item_text: str) -> bool:
    first_line = item_text.splitlines()[0].strip()
    m = _CHECKBOX_RE.match(first_line)
    assert m, f"not a checkbox list item: {first_line!r}"
    return m.group(1).lower() == "x"


def _has_annotation(item_text: str) -> bool:
    """A `*(...)*` parenthetical trailing the box text -- evidence when
    ticked, a reason when unticked (the Stage 17 box at progress.md:744,
    `- [ ] ... *(Unticked because ...)*`, is the model for the
    unticked-plus-reason shape).

    Engine 1.5.0 made that shape durable: `aide progress set` no longer
    derives acceptance ticks, so an unticked-with-reason box survives any
    later status change, and ticking is the explicit `aide progress accept`.
    Before that, both this box and Stage 26's fifth were re-ticked by any
    `progress set` call for any item, which is why the Stage 17 one was
    described here as a tripwire.
    """
    return bool(_EVIDENCE_NOTE_RE.search(item_text))


def _biconditional_violations(section: str) -> list:
    """Every acceptance item that is ticked-without-annotation or
    unticked-without-annotation; empty iff the biconditional holds."""
    violations = []
    for item in _acceptance_items(section):
        if not _has_annotation(item):
            violations.append(item.splitlines()[0].strip())
    return violations


def test_ac12_stage26_has_five_acceptance_boxes():
    section = _stage26_section(_read_progress())
    items = _acceptance_items(section)
    assert len(items) == 5, items


def test_ac12_every_stage26_box_ticked_implies_evidence_or_unticked_implies_reason():
    """AC12: expected to FAIL until the builder adds the evidence/reason
    annotations -- Stage 26's five boxes currently carry neither."""
    section = _stage26_section(_read_progress())
    violations = _biconditional_violations(section)
    assert violations == [], (
        "Stage 26 acceptance box(es) with no evidence/reason annotation: "
        f"{violations}"
    )


def test_adv_ticked_box_with_no_annotation_is_flagged():
    """Adversarial (spec-named): a Stage 26 box ticked with no annotation
    must fail the biconditional check, proving the helper doesn't silently
    pass a false claim."""
    synthetic_section = (
        "## Stage 26 — Carried-Defect Remediation (pre-real-data) (G2, G7) — 🚧\n\n"
        "**Acceptance.**\n\n"
        "- [x] Each defect has a regression test that fails before its fix.\n"
    )
    violations = _biconditional_violations(synthetic_section)
    assert violations, "expected the annotation-less ticked box to be flagged"


def test_adv_unticked_box_with_reason_is_not_flagged():
    synthetic_section = (
        "## Stage 26 — Carried-Defect Remediation (pre-real-data) (G2, G7) — 🚧\n\n"
        "**Acceptance.**\n\n"
        "- [ ] Each defect has a regression test that fails before its fix. "
        "*(Unticked because the red-then-green replay was not performed in "
        "this execution environment.)*\n"
    )
    violations = _biconditional_violations(synthetic_section)
    assert violations == []


# =========================================================================== #
# AC13: verification rows reflect reality -- Docker row unchanged by item 113.
# =========================================================================== #


def _table_row(text: str, needle: str) -> str:
    for line in text.splitlines():
        if line.startswith("|") and needle in line:
            return line
    raise AssertionError(f"no table row containing {needle!r} found in progress.md")


def _row_cells(row_line: str) -> list:
    stripped = row_line.strip()
    assert stripped.startswith("|") and stripped.endswith("|"), row_line
    return [c.strip() for c in stripped[1:-1].split("|")]


def test_ac13_docker_verification_row_status_still_verified():
    text = _read_progress()
    row = _table_row(text, "Containerised pipeline (Docker build + run)")
    cells = _row_cells(row)
    assert len(cells) == 5, cells
    status_cell = cells[3]
    assert status_cell.startswith("✅ Verified"), status_cell


def test_ac13_docker_verification_row_evidence_date_unchanged_by_item_113():
    """Item 113 *reduces where* Docker runs (deselects the Docker-gated
    modules from one specific CI leg) but must not have flipped this row --
    pin the original verification date/host so a later drive-by edit that
    silently re-stamps the row (as if item 113 re-verified it) is caught."""
    text = _read_progress()
    row = _table_row(text, "Containerised pipeline (Docker build + run)")
    cells = _row_cells(row)
    status_cell = cells[3]
    assert "2026-07-14" in status_cell
    assert "GitHub Actions CI" in status_cell


def test_ac13_docker_verification_row_introduced_by_unchanged():
    text = _read_progress()
    row = _table_row(text, "Containerised pipeline (Docker build + run)")
    cells = _row_cells(row)
    introduced_by = cells[2]
    assert "Stage 9" in introduced_by
    assert "066" in introduced_by
