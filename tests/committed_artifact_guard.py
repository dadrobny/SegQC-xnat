"""Static classifier + allowlist for byte-exact fresh-vs-committed comparisons
under ``tests/`` (item 127).

``segfacet.synth.golden.assert_matches_committed_artifact`` is the one path a
test should take to compare freshly-generated output against a committed
artifact (numeric-tolerance leaves, everything else exact -- item 078). This
module is the enforcing half: :func:`classify_module` walks a test module's
AST for a byte-exact (``==``/``!=``) comparison where exactly one operand
resolves to a **committed** path (a repo-relative file this repo ships, not
something the test itself wrote under ``tmp_path`` this run) and the other
operand does not resolve to that *same* committed path, then reports it as a
:class:`Violation` unless the committed path is covered by :data:`ALLOWLIST`.
:func:`violation_message` renders the failure, naming
``assert_matches_committed_artifact`` as the fix.

Standing rule: the emission-clamp requirement
----------------------------------------------
An artifact that reports a raw float measurement alongside its own
"meaningfully nonzero" threshold must clamp sub-threshold values to a fixed
sentinel at the serialisation boundary before it can be byte-compared --
quantisation alone (``float(f"{v:.6g}")``) cannot stabilise cancellation-scale
numerical residue, which is still noise at six significant digits (measured
2026-08-30, PR #56). ``segfacet.observed_range.emission_range`` is the shipped
example: a covered-but-not-informative population emits
``(0.0, 0.0, 0.0, 0.0)`` while ``PopulationRange`` keeps the raw measurement
for every caller that classifies on it. Four other grounds make byte
comparison legitimate -- see :data:`GROUNDS` -- and every :data:`ALLOWLIST`
entry names its ground and carries a one-line reason.

Standing rule: the consumer-survey requirement
------------------------------------------------
A spec that changes a feature the reference artifact aggregates must survey
its consumers **mechanically** -- ``grep -l build_and_write_default tests/``
-- never by hand-listing. Item 123's recalibration is the precedent: the same
four-line fresh-vs-committed comparison existed in four unrelated modules, and
hand-listing found only three of them.

``src/segfacet/reference/reference_default.json`` is deliberately absent from
:data:`ALLOWLIST`: 454 of its 1133 float leaves (measured 2026-08-31) are
full-precision computed statistics, exactly the shape item 078 proved is not
byte-stable across NumPy versions, platform BLAS/SIMD and libm rounding. Every
comparison against it goes through ``assert_matches_committed_artifact``
instead (item 127's AC2/AC10 helper cases and AC16's synthetic violation both
exercise this exclusion directly).

Precise, not exhaustive
------------------------
:func:`classify_module` resolves an operand to a committed path only through:
a string literal passed to ``Path(...)``; a module-level constant built from a
chain of ``.resolve()``/``.parent`` starting at ``Path(__file__)`` (a
"``_REPO_ROOT``-style" root), optionally further joined with literal string
segments via ``/``; a local variable assigned from one of those in the same
function; and the recognised read shapes ``.read_bytes()``,
``.read_text(...)`` and ``hashlib.sha256(<path>.read_bytes()).hexdigest()`` --
including a local variable that was itself assigned from one of those read
shapes earlier in the same function (the "unchanged fence" idiom: read once,
do something, read again, compare to the stored value). Anything it cannot
resolve this way -- a loop variable, a function argument, a path built from
``tmp_path``, a value produced by an arbitrary function call, a value reached
through ``json.loads`` -- is skipped **in silence**. A reported
:class:`Violation` is therefore authoritative; a clean :func:`iter_violations`
run is not a proof of absence.
"""

from __future__ import annotations

import ast
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Allowlist
# --------------------------------------------------------------------------- #

#: Closed vocabulary of grounds on which a byte-exact fresh-vs-committed
#: comparison is legitimate. Adding a sixth member is a deliberate edit an
#: author must justify -- that is the point.
GROUNDS: Tuple[str, ...] = (
    "exact-parameter-floats",
    "emission-clamped",
    "hand-written-literals",
    "binary-fixture",
    "integrity-pin",
)


@dataclass(frozen=True)
class AllowlistEntry:
    """One legitimate byte-exact fresh-vs-committed comparison.

    ``path`` is a repo-relative path or glob (matched against a resolved
    committed path with :func:`fnmatch.fnmatch`); ``ground`` is a member of
    :data:`GROUNDS`; ``reason`` is a non-empty single-line justification.
    """

    path: str
    ground: str
    reason: str


#: Every entry below is measured against the post-item-126 inventory
#: (2026-08-31): the nine snapshots from the retired corpus golden-snapshot
#: store (see item 126 / ``docs/aide/golden-decision-table.md``'s Retirement
#: execution log) and the two
#: ``tests/golden/0NN_*.json`` snapshots item 126 retired are absent here, and
#: ``tests/golden/report_format_contract.json`` -- the surviving fixture -- is
#: keyed by the same ``tests/golden/*.json`` glob its ``.gitattributes`` pin
#: uses, not by its own filename. ``src/segfacet/reference/reference_default.json``
#: is deliberately absent -- see the module docstring. ``docs/aide/golden-
#: decision-table.md`` is read-only prose, never regenerated and compared
#: fresh-vs-committed, so it stays out of this allowlist even though it is
#: byte-read and LF-pinned (``tests/test_111_golden_guard.py``'s
#: ``_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES`` covers that separately).
ALLOWLIST: Tuple[AllowlistEntry, ...] = (
    AllowlistEntry(
        path="tests/corpus/manifest.json",
        ground="exact-parameter-floats",
        reason="36 float leaves, all declared generator parameters or exact "
        "binary values (6.0, 1.0); no computed measurement.",
    ),
    AllowlistEntry(
        path="tests/corpus/intensity/manifest.json",
        ground="exact-parameter-floats",
        reason="Same generator, 16 float leaves, all exact.",
    ),
    AllowlistEntry(
        path="tests/corpus/094_pre_migration_snapshot.json",
        ground="exact-parameter-floats",
        reason="285 float leaves, all affine/spacing components that are "
        "exact binary values; the array payloads are carried as digests, "
        "not floats.",
    ),
    AllowlistEntry(
        path="tests/corpus/fixtures/*.nii.gz",
        ground="binary-fixture",
        reason="Integer label and scan volumes; gzip of an exact byte "
        "payload, pinned binary in .gitattributes.",
    ),
    AllowlistEntry(
        path="tests/corpus/intensity/fixtures/*.nii.gz",
        ground="binary-fixture",
        reason="Same, for the intensity corpus.",
    ),
    AllowlistEntry(
        path="docs/aide/feature_catalogue.generated.json",
        ground="emission-clamped",
        reason="Observed-range floats are quantised to six significant "
        "figures and sub-floor noise is clamped to 0.0 at emission "
        "(segfacet.observed_range.emission_range, item 124).",
    ),
    AllowlistEntry(
        path="docs/aide/feature_catalogue.generated.md",
        ground="emission-clamped",
        reason="The rendered form of the same clamped values.",
    ),
    AllowlistEntry(
        path="tests/golden/*.json",
        ground="hand-written-literals",
        reason="Item 126's feature-value-free format fixture "
        "(report_format_contract.json): every number is a literal "
        "serialised straight through, so the comparison is a formatting "
        "guarantee, not a measurement.",
    ),
    AllowlistEntry(
        path="src/segfacet/reference/reference_verse_v1.json",
        ground="integrity-pin",
        reason="A released production artifact compared against a recorded "
        "digest; there is no freshly computed side, so a change must be "
        "deliberate.",
    ),
)


def _matches_allowlist(committed_path: str) -> bool:
    return any(fnmatch.fnmatch(committed_path, entry.path) for entry in ALLOWLIST)


# --------------------------------------------------------------------------- #
# Violations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Violation:
    """One off-allowlist byte-exact fresh-vs-committed comparison."""

    module: str
    line: int
    committed_path: str


def violation_message(violations) -> str:
    """Render *violations* as a failure message naming the fix
    (``assert_matches_committed_artifact``) and, per violation, the module,
    line and committed path."""
    lines = [
        "byte-exact comparison(s) against a committed artifact outside the "
        "allowlist -- use segfacet.synth.golden.assert_matches_committed_artifact "
        "instead (see tests/committed_artifact_guard.py):",
    ]
    for v in violations:
        lines.append(f"  {v.module}:{v.line} -- committed artifact {v.committed_path!r}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# AST resolution -- see the module docstring's "Precise, not exhaustive"
# --------------------------------------------------------------------------- #


def _is_name(node, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _file_root_parent_count(node) -> Optional[int]:
    """If *node* is a chain of ``.resolve()``/``.parent`` starting at
    ``Path(__file__)``, return how many ``.parent`` steps it takes (0 for
    ``Path(__file__)`` itself); otherwise ``None``."""
    if isinstance(node, ast.Call) and _is_name(node.func, "Path") and len(node.args) == 1:
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id == "__file__":
            return 0
        return None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
        and not node.args
    ):
        return _file_root_parent_count(node.func.value)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        inner = _file_root_parent_count(node.value)
        return None if inner is None else inner + 1
    return None


def _is_file_root_chain(node) -> bool:
    """True iff *node* is a ``Path(__file__)``-based chain reaching at least
    two ``.parent`` steps up, e.g. ``Path(__file__).resolve().parent.parent``.

    A *single* ``.parent`` (a module's own containing directory, e.g.
    ``tests/`` for a module directly under it) is deliberately not treated as
    "the repo root" -- this classifier has no notion of a module's real
    on-disk depth (see the module docstring), so a one-parent chain used to
    join further literal segments (e.g. ``Path(__file__).parent / "golden" /
    "x.json"``) would otherwise resolve to a path relative to the *module's*
    directory rather than the repo root, and silently mismatch every
    repo-relative allowlist entry.
    """
    count = _file_root_parent_count(node)
    return count is not None and count >= 2


def _resolve_expr(node, known: Dict[str, str]) -> Optional[str]:
    """Resolve *node* to a repo-relative path string, or ``None`` if it is
    not one of the recognised shapes (see the module docstring)."""
    if _is_file_root_chain(node):
        return ""
    if isinstance(node, ast.Name):
        return known.get(node.id)
    if isinstance(node, ast.Call) and _is_name(node.func, "Path") and len(node.args) == 1:
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _resolve_expr(node.left, known)
        if left is None:
            return None
        if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            return None
        segment = node.right.value
        return segment if left == "" else f"{left.rstrip('/')}/{segment}"
    return None


def _extract_path_expr_from_read(node) -> Optional[ast.expr]:
    """If *node* is one of the recognised committed-artifact read shapes
    (``.read_bytes()``, ``.read_text(...)``,
    ``hashlib.sha256(<path>.read_bytes()).hexdigest()``), return the AST
    expression for the path it reads. Otherwise ``None``."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in ("read_bytes", "read_text"):
        return func.value
    if isinstance(func, ast.Attribute) and func.attr == "hexdigest" and not node.args:
        inner = func.value
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "sha256"
            and isinstance(inner.func.value, ast.Name)
            and inner.func.value.id == "hashlib"
            and len(inner.args) == 1
        ):
            return _extract_path_expr_from_read(inner.args[0])
    return None


def _walk_stmts(stmts):
    """Yield every statement under *stmts*, recursing into ``body``,
    ``orelse`` and ``finalbody`` in source order."""
    for stmt in stmts:
        yield stmt
        for field in ("body", "orelse", "finalbody"):
            substmts = getattr(stmt, field, None)
            if substmts:
                yield from _walk_stmts(substmts)


def _module_level_paths(tree: ast.Module) -> Dict[str, str]:
    known: Dict[str, str] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            resolved = _resolve_expr(stmt.value, known)
            if resolved is not None:
                known[stmt.targets[0].id] = resolved
    return known


def _resolve_operand(
    operand: ast.expr, known: Dict[str, str], read_results: Dict[str, str]
) -> Optional[str]:
    """Resolve one comparison operand to a committed path, if it is (or
    stands in for) a read of one."""
    path_expr = _extract_path_expr_from_read(operand)
    if path_expr is not None:
        return _resolve_expr(path_expr, known)
    if isinstance(operand, ast.Name) and operand.id in read_results:
        return read_results[operand.id]
    return None


def _classify_function(func, module_known: Dict[str, str], module_path: str) -> List[Violation]:
    local_known: Dict[str, str] = dict(module_known)
    local_reads: Dict[str, str] = {}

    for stmt in _walk_stmts(func.body):
        if not (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            continue
        name = stmt.targets[0].id
        resolved = _resolve_expr(stmt.value, local_known)
        if resolved is not None:
            local_known[name] = resolved
            continue
        path_expr = _extract_path_expr_from_read(stmt.value)
        if path_expr is not None:
            read_resolved = _resolve_expr(path_expr, local_known)
            if read_resolved is not None:
                local_reads[name] = read_resolved

    violations: List[Violation] = []
    for stmt in _walk_stmts(func.body):
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Compare):
                continue
            if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
                continue
            if len(node.comparators) != 1:
                continue
            left = _resolve_operand(node.left, local_known, local_reads)
            right = _resolve_operand(node.comparators[0], local_known, local_reads)
            resolved = [r for r in (left, right) if r is not None]
            if len(resolved) != 1:
                # Zero operands resolve (fresh-vs-fresh, AC19) or both
                # resolve to (the same, AC18, or a different) committed
                # path -- neither is a fresh-vs-committed comparison.
                continue
            committed_path = resolved[0]
            if not _matches_allowlist(committed_path):
                violations.append(
                    Violation(module=module_path, line=node.lineno, committed_path=committed_path)
                )
    return violations


def classify_module(source: str, module_path: str) -> List[Violation]:
    """Classify one test module's *source* for byte-exact fresh-vs-committed
    comparisons whose committed artifact is not on :data:`ALLOWLIST`.

    *module_path* is a label for the module (used only in the returned
    :class:`Violation`\\ s), typically its repo-relative path. Invalid Python
    (or empty source) reports no violations rather than raising -- see the
    module docstring's "Precise, not exhaustive" section."""
    try:
        tree = ast.parse(source, filename=module_path)
    except SyntaxError:
        return []

    module_known = _module_level_paths(tree)

    violations: List[Violation] = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_classify_function(stmt, module_known, module_path))
    return violations


def iter_violations(tests_dir) -> Iterator[Violation]:
    """Map :func:`classify_module` over every ``*.py`` file directly under
    *tests_dir* (non-recursive -- ``tests/`` carries no nested test
    packages), in sorted filename order."""
    tests_dir = Path(tests_dir)
    for path in sorted(tests_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for violation in classify_module(source, path.as_posix()):
            yield violation
