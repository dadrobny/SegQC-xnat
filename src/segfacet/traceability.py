"""Generated failure-mode conformance report (item 149; Stage 30 -- Failure-
Mode Specification: the §6 catalogue as an authored source).

Items 144-148 built ``segfacet.failure_modes.SPECIFICATION`` as the
**primary, authored record** of every §6 failure mode -- a schema, a
derivation for lifecycle status and evidence rung, and a per-corpus-case
measured firing set. Before item 149, this module (item 138) instead
cross-checked **five partial sources** that could agree or disagree with no
document able to adjudicate. That cross-check is retired: :func:`build_matrix`
now reads the specification as its **primary source** (:data:`primary_source`
in every rendered artifact, ``"src/segfacet/failure_modes.py"``), and reports,
per mode:

- the *derived* lifecycle ``status`` (:func:`segfacet.failure_modes.derive_status`)
  beside the *authored* ``authored_status`` (``ModeSpec.status``);
- one ``edge_rungs`` entry per ``IntendedRule`` the specification carries for
  that mode, verbatim and in order, plus the derived per-mode ``rung``
  (:func:`segfacet.failure_modes.derive_mode_rung`);
- two **separate, separately-labelled** path columns: ``anchor_paths`` (the
  Stage-18 metric anchor, unfiltered, from
  ``segfacet.feature_docs.MODE_ANCHOR_PATHS``) and ``read_paths`` (the sorted
  union, over the mode's declaring rules, of the leaf paths each rule
  classifies ``"signal"`` -- item 148's
  ``RuleModeDeclaration.consumed_paths`` / ``CatalogueEntry.mode_roles``).
  Never unioned into one field (item 138's ``feature_paths`` conflation is
  gone).

And, new in item 149, a **conformance direction**: per case in **both**
committed corpus manifests (``tests/corpus/manifest.json`` and
``tests/corpus/intensity/manifest.json``), the specification's *expected*
firing set beside the *measured* firing set
(:func:`segfacet.failure_modes.measured_firing`), scored for agreement. A
manifest case with no ``ModeSpec.corpus_cases`` entry covering it is a named
hole (``expected_source == "unspecified"``); the two ``failure_mode == 0``
clean controls are scored too, labelled ``"manifest-clean-control"`` since §6
defines no mode 0. This is the check none of queue-019's shape tests could
express: running the case and comparing the sets tests the specification's
*truth*, not merely its *shape*.

Two directions are unaffected by this item and stay exactly as item 138 left
them, over the same registered-rule/registry-declaration inputs:

- **mode -> rule** / **rule -> mode** -- each *scored*, not guaranteed:
  read the ``complete``/``holes`` fields under ``directions`` for the live
  answer.
- **feature -> rule** -- deliberately **not** complete; the qualifier beside
  the count says why (unchanged from item 138).

Every ``(mode, rule)`` edge carries an **attribution** -- ``"corpus"`` when at
least one of that mode's ``SPECIFICATION[mode].corpus_cases`` lists the rule
in its ``expected_firing``, ``"analytic"`` otherwise. This, too, is a
"primary source" move (item 149 Decision D2): before this item the column was
derived from :func:`segfacet.catalogue.scan_synth_rule_mode_map`, an AST scan
matching only geometric ``Expectation(...)`` literals, so mode 9's
``intensity`` edge (corpus-designated only in the intensity manifest, which
the scan never reads) rendered ``"analytic"`` beside a rung claiming three
committed intensity cases drive it end-to-end. The scan is still read, for
``corpus_designated_unregistered_rule_ids`` only.

An unclassified or dropped ``consumed_paths`` entry is folded in from
:func:`segfacet.catalogue.path_classification_conflicts` as
``classification_conflicts`` rather than re-derived, and contributes to the
matrix-level ``conformance.conformant`` flag alongside the per-case agreement
count.

Scope fence
-----------
This module *reports*. It decides no disposition, changes no rule,
threshold, extractor, verdict, report schema, or CLI behaviour, and
regenerates neither of item 103's catalogue artifacts. It builds **no**
per-rule or per-operator corpus-**exercise** columns -- item 139's
deliverable, re-specified against this output, stays Stage 20's. It adopts
no specificity ratchet (item 140) and does not touch
``eval/severity_ladder.py`` (item 141).

Determinism contract
---------------------
:func:`build_matrix` never mutates any input; two calls return equal,
immutable matrices (frozen dataclasses / tuples throughout), and it holds
**no cache** -- deliberately, so the adversarial monkeypatch tests that prove
the report is live cannot be defeated by a memoised result. Heavy imports
(NumPy/SciPy/NiBabel, via ``segfacet.catalogue``/``segfacet.heuristics``/
``segfacet.failure_modes``) are deferred into function bodies, per house
style, so ``import segfacet.traceability`` alone stays cheap and importing it
plus calling :func:`build_matrix` never mutates any importable module's
state (AC32).

Public API
----------
``build_matrix() -> TraceabilityMatrix``
    Assemble the full matrix. Takes no required argument.
``matrix_to_dict(matrix) -> dict``
    A deterministic, JSON-ready dict. ``json.dumps(..., indent=2,
    sort_keys=True, ensure_ascii=False)`` plus one trailing newline is the
    committed JSON's exact serialisation.
``render_markdown(matrix) -> str``
    A deterministic Markdown rendering of the same matrix.
``main(argv=None) -> int``
    ``python -m segfacet.traceability [--json PATH] [--md PATH]``; defaults
    to the two committed artifact paths under ``docs/aide/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Set, Tuple

__all__ = ["build_matrix", "matrix_to_dict", "render_markdown", "main"]

SCHEMA_VERSION = "1.1"

_REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
MD_PATH = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"

_PRIMARY_SOURCE = "src/segfacet/failure_modes.py"

_NOTE = (
    "Generated by `python -m segfacet.traceability` (item 138; re-pointed at "
    f"{_PRIMARY_SOURCE} as its primary source by item 149). Do not hand-edit "
    f"this document -- edit the authored failure-mode specification in "
    f"{_PRIMARY_SOURCE} (every mode's title, status, per-edge evidence rung, "
    "mechanism sentence and per-corpus-case expected firing set is read live "
    "from it) or the underlying rule/catalogue sources this matrix also "
    "derives from, then regenerate. "
    "mode -> rule and rule -> mode each report their own completeness and "
    "name every hole: read the `complete`/`holes` fields rather than "
    "assuming either is complete. Since item 146 a mode may legitimately "
    "carry no rule -- a `proposed` entry in "
    "segfacet.failure_modes.SPECIFICATION is listed and defined but "
    "deliberately unimplemented -- and it appears as a mode -> rule hole. "
    "feature -> rule is deliberately incomplete -- see "
    "the `features.read_by_no_rule.qualifier` field. "
    "The `conformance` section (item 149) drives every corpus case in both "
    "committed manifests through the specification's expected firing set and "
    "the live measured firing set: read `conformance.disagreements` and "
    "`conformance.unspecified_cases` for the live answer, never assume "
    "`conformant`."
)

_FEATURE_QUALIFIER = (
    "a leaf path no rule reads is inventory, not a gap: the feature record "
    "is a deliberately over-broad vector rules select from, and full "
    "consumption is never an expected end state."
)

_READ_PATHS_QUALIFIER = (
    "mode -> read_paths is signal-classified: a path's presence in a mode "
    "row's read_paths means a rule declaring this mode classifies that path "
    "\"signal\" (segfacet.heuristics.rule.RuleModeDeclaration.consumed_paths, "
    "item 148), not that this path alone evidences this mode. The Stage-18 "
    "metric anchor (anchor_paths) is a separate column that is never merged "
    "in."
)


# =========================================================================== #
# Retired here by item 147 (2026-09-04): ``RUNGS``, ``RUNG_LABELS``,
# ``ModeRung`` and ``MODE_RUNGS``.
#
# This module authored a mode's evidence rung and mechanism sentence as
# constants while there was nowhere better to put them. There is now:
# ``segfacet.failure_modes.SPECIFICATION`` carries a per-**edge**
# ``evidence_rung`` (item 145) that ``derive_mode_rung()`` folds into a
# per-mode rung, and an authored ``ModeSpec.mechanism`` (item 147). The rung
# vocabulary lives beside it as ``failure_modes.EVIDENCE_RUNGS``, and
# ``RUNG_LABELS`` moved there verbatim. ``build_matrix`` reads all of it
# live, so modes 9 and 10 -- which this module's authored dict never carried
# -- stop rendering an empty rung and an empty title.
#
# Item 149 re-points ``build_matrix`` itself at the specification as its
# primary source (the "conflated union" ``feature_paths`` field the earlier
# comment block described is gone too -- see ``read_paths``/``anchor_paths``
# below). Do not re-introduce a constant, a rung dict literal, or a module-
# level ``MODE_RUNGS``/``ModeRung``/``RUNGS``/``RUNG_LABELS`` binding here: a
# mode fact belongs in the specification.
# =========================================================================== #


# =========================================================================== #
# Frozen record dataclasses
# =========================================================================== #


@dataclass(frozen=True)
class ModeRecord:
    mode: int
    title: str
    status: str
    authored_status: str
    edge_rungs: Tuple[Tuple[str, str, str], ...]
    rung: str
    mechanism: str
    rules: Tuple[str, ...]
    rule_attribution: Tuple[Tuple[str, str], ...]
    pipeline_detected: bool
    cases: Tuple[Tuple[str, str], ...]
    anchor_paths: Tuple[str, ...]
    read_paths: Tuple[str, ...]
    granularity: str
    read_paths_qualifier: str


@dataclass(frozen=True)
class RuleRecord:
    rule_id: str
    modes: Tuple[int, ...]
    declaration_state: str
    mode_less_reason: str
    evidence: Tuple[str, ...]
    feature_paths: Tuple[str, ...]


@dataclass(frozen=True)
class DirectionReport:
    complete: bool
    holes: Tuple[str, ...]


@dataclass(frozen=True)
class FeatureDirection:
    total_paths: int
    read_by_rule: int
    read_by_no_rule_count: int
    read_by_no_rule_required: bool
    read_by_no_rule_qualifier: str
    unwired: int
    by_rule: Tuple[Tuple[str, int], ...]


@dataclass(frozen=True)
class ConformanceCase:
    corpus: str
    case_id: str
    mode: int
    expected_firing: Tuple[str, ...]
    measured_firing: Tuple[str, ...]
    agrees: bool
    expected_source: str


@dataclass(frozen=True)
class ConformanceReport:
    cases: Tuple[ConformanceCase, ...]
    agree_count: int
    disagree_count: int
    conformant: bool
    disagreements: Tuple[ConformanceCase, ...]
    unspecified_cases: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class TraceabilityMatrix:
    schema_version: str
    primary_source: str
    note: str
    modes: Tuple[ModeRecord, ...]
    rules: Tuple[RuleRecord, ...]
    features: FeatureDirection
    mode_to_rule: DirectionReport
    rule_to_mode: DirectionReport
    corpus_designated_unregistered_rule_ids: Tuple[str, ...]
    classification_conflicts: Tuple[str, ...]
    conformance: ConformanceReport


# =========================================================================== #
# The private ``_vision_mode_titles()`` parse lived here until item 147 moved
# it to its one public home, ``failure_modes.vision_seed_titles()``. A mode
# row's title now comes from ``SPECIFICATION[mode].name`` -- the record --
# and the §6 seed list is checked against that record there, once.
# =========================================================================== #


# =========================================================================== #
# build_matrix
# =========================================================================== #


def _normalise_evidence(evidence) -> Tuple[str, ...]:
    """A malformed ``evidence`` (item 136's known weakness -- a bare ``str``
    is itself iterable-of-characters) collapses to one element (AC27),
    never a per-character split."""
    if isinstance(evidence, str):
        return (evidence,) if evidence else ()
    return tuple(evidence) if evidence else ()


#: Manifest ``detection`` values that mean "produced by a real (or intensity)
#: pipeline run", as opposed to a deliberately-reconstructed record
#: (``"reconstructed_record"``, mode 8's overlap case -- structurally
#: impossible for any real segmenter output, so it never counts as
#: pipeline-detected).
_PIPELINE_DETECTIONS = frozenset({"pipeline", "intensity_pipeline"})


def _build_conformance(failure_modes_module) -> ConformanceReport:
    """Per corpus case, across **both** committed manifests: the
    specification's expected firing set beside the live measured firing set
    (AC13-AC17, AC33's dependency A1/A2/A3). Never re-derives the manifest
    enumeration from the specification -- a manifest case with no covering
    ``ModeSpec.corpus_cases`` entry is a named hole (AC14), not a silent
    omission, which is why the loop below always walks the manifests, never
    ``SPECIFICATION`` itself."""
    from segfacet.synth import corpus as corpus_module
    from segfacet.synth import intensity as intensity_module

    specification = failure_modes_module.SPECIFICATION

    spec_case_index: Dict[Tuple[str, str], Tuple[int, object]] = {}
    for mode_id, mode_spec in specification.items():
        for case in mode_spec.corpus_cases:
            spec_case_index[(case.corpus, case.case_id)] = (mode_id, case)

    cases: list = []
    unspecified_cases: list = []

    for corpus_name, manifest_cases in (
        ("geometric", corpus_module.load_manifest().get("cases", [])),
        ("intensity", intensity_module.load_intensity_manifest().get("cases", [])),
    ):
        for manifest_case in manifest_cases:
            case_id = manifest_case.get("case_id")
            mode_id = manifest_case.get("failure_mode")
            key = (corpus_name, case_id)

            probe = failure_modes_module.CorpusCaseExpectation(
                case_id=case_id, corpus=corpus_name, expected_firing=(), reason=""
            )
            measured = failure_modes_module.measured_firing(probe)

            if mode_id == 0:
                expected_firing: Tuple[str, ...] = ()
                expected_source = "manifest-clean-control"
                agrees = set(measured) == set(expected_firing)
            elif key in spec_case_index:
                _spec_mode_id, spec_case = spec_case_index[key]
                expected_firing = tuple(spec_case.expected_firing)
                expected_source = "specification"
                agrees = set(measured) == set(expected_firing)
            else:
                expected_firing = ()
                expected_source = "unspecified"
                agrees = False
                unspecified_cases.append((corpus_name, case_id))

            cases.append(
                ConformanceCase(
                    corpus=corpus_name,
                    case_id=case_id,
                    mode=mode_id,
                    expected_firing=expected_firing,
                    measured_firing=tuple(measured),
                    agrees=agrees,
                    expected_source=expected_source,
                )
            )

    cases.sort(key=lambda c: (c.corpus, c.case_id))
    disagreements = tuple(c for c in cases if not c.agrees)
    agree_count = sum(1 for c in cases if c.agrees)
    disagree_count = len(cases) - agree_count

    return ConformanceReport(
        cases=tuple(cases),
        agree_count=agree_count,
        disagree_count=disagree_count,
        conformant=disagree_count == 0,
        disagreements=disagreements,
        unspecified_cases=tuple(sorted(unspecified_cases)),
    )


def build_matrix() -> TraceabilityMatrix:
    """Assemble the full :class:`TraceabilityMatrix`.

    Never mutates any input (the registry, the catalogue, the specification,
    the two committed manifests); two calls return equal matrices. Deferred
    imports (house style). Holds no cache (AC30) -- every call re-derives
    from scratch, which is what makes the adversarial monkeypatch tests below
    meaningful."""
    import re

    from segfacet import failure_modes as failure_modes_module
    from segfacet import feature_docs as feature_docs_module
    from segfacet.catalogue import (
        build_catalogue,
        path_classification_conflicts,
        rule_declaration_conflicts,
        scan_synth_rule_mode_map,
    )
    from segfacet.heuristics.rule import iter_rule_declarations, iter_rules

    mode_anchor_paths = feature_docs_module.MODE_ANCHOR_PATHS
    # The matrix's known-mode source is the authored specification (item
    # 144), not feature_docs.MODE_ANCHOR_PATHS's key set. A mode with no
    # MODE_ANCHOR_PATHS entry (mode 9, 10) still gets a full mode row; its
    # anchor_paths render empty via mode_anchor_paths.get(mode, ()).
    known_modes = set(failure_modes_module.SPECIFICATION.keys())

    cat = build_catalogue(strict=True)
    paths_by_rule: Dict[str, Tuple[str, ...]] = {}
    for rule_id_iter in {rid for entry in cat.entries for rid in entry.consuming_rules}:
        paths_by_rule[rule_id_iter] = tuple(
            sorted(e.path for e in cat.entries if rule_id_iter in e.consuming_rules)
        )

    # Item 149 AC10: the read-path column is the sorted union, over a mode's
    # declaring rules, of the leaf paths that rule classifies "signal" in
    # CatalogueEntry.mode_roles -- never a bookkeeping / not-read /
    # unclassified path.
    signal_paths_by_rule: Dict[str, Set[str]] = {}
    for entry in cat.entries:
        for rule_id_iter, role in entry.mode_roles:
            if role != "signal":
                continue
            signal_paths_by_rule.setdefault(rule_id_iter, set()).add(entry.path)

    total_paths = len(cat.entries)
    read_by_rule = sum(1 for e in cat.entries if e.consuming_rules)
    read_by_no_rule = total_paths - read_by_rule
    unwired = sum(1 for e in cat.entries if e.status == "unwired")
    by_rule_counts: Dict[str, int] = {}
    for e in cat.entries:
        for rid in e.consuming_rules:
            by_rule_counts[rid] = by_rule_counts.get(rid, 0) + 1

    corpus_map = scan_synth_rule_mode_map()

    registered_rule_ids = sorted(r.rule_id for r in iter_rules())
    declared_modes_by_rule: Dict[str, Tuple[int, ...]] = {}
    mode_less_reason_by_rule: Dict[str, str] = {}
    declaration_state_by_rule: Dict[str, str] = {}
    evidence_by_rule: Dict[str, Tuple[str, ...]] = {}

    for rule_id, decl in iter_rule_declarations():
        if decl is None:
            declaration_state_by_rule[rule_id] = "undeclared"
            declared_modes_by_rule[rule_id] = ()
            mode_less_reason_by_rule[rule_id] = ""
            evidence_by_rule[rule_id] = ()
            continue
        if decl.modes:
            declaration_state_by_rule[rule_id] = "declared"
            declared_modes_by_rule[rule_id] = tuple(decl.modes)
            mode_less_reason_by_rule[rule_id] = ""
            evidence_by_rule[rule_id] = _normalise_evidence(decl.evidence)
        elif decl.mode_less_reason:
            declaration_state_by_rule[rule_id] = "mode_less"
            declared_modes_by_rule[rule_id] = ()
            mode_less_reason_by_rule[rule_id] = decl.mode_less_reason
            evidence_by_rule[rule_id] = _normalise_evidence(decl.evidence)
        elif decl.pending_reason:
            declaration_state_by_rule[rule_id] = "pending"
            declared_modes_by_rule[rule_id] = ()
            mode_less_reason_by_rule[rule_id] = ""
            evidence_by_rule[rule_id] = _normalise_evidence(decl.evidence)
        else:
            declaration_state_by_rule[rule_id] = "undeclared"
            declared_modes_by_rule[rule_id] = ()
            mode_less_reason_by_rule[rule_id] = ""
            evidence_by_rule[rule_id] = ()

    # rule -> mode direction: complete iff every registered rule is
    # "declared" or "mode_less" (AC18, AC26) -- AND, for a "declared" rule,
    # at least one of its declared modes is actually known to the
    # specification. A rule declaring only modes outside
    # failure_modes.SPECIFICATION's key set is "declared" by
    # declaration_state alone but targets no known mode, which is exactly a
    # rule -> mode hole per this module's own completeness contract.
    # catalogue's rule_declaration_conflicts() already reports this
    # disagreement (its "declared §6 mode ... is outside
    # segfacet.failure_modes.SPECIFICATION's key set" message); folded in
    # here rather than re-derived, so the artifact's own completeness claim
    # covers it too, and rules_by_mode (which is built from
    # declared_modes_by_rule directly) never silently drops it.
    _uncatalogued_mode_rule_ids = set()
    _uncatalogued_mode_re = re.compile(
        r"^rule '([^']+)': declared §6 mode \d+ is outside"
    )
    for _message in rule_declaration_conflicts():
        _match = _uncatalogued_mode_re.match(_message)
        if _match:
            _uncatalogued_mode_rule_ids.add(_match.group(1))

    rule_to_mode_holes = tuple(
        sorted(
            rule_id
            for rule_id in registered_rule_ids
            if declaration_state_by_rule.get(rule_id, "undeclared")
            not in ("declared", "mode_less")
            or (
                declaration_state_by_rule.get(rule_id) == "declared"
                and rule_id in _uncatalogued_mode_rule_ids
                and not (set(declared_modes_by_rule.get(rule_id, ())) & known_modes)
            )
        )
    )
    rule_to_mode = DirectionReport(complete=not rule_to_mode_holes, holes=rule_to_mode_holes)

    # mode -> rule: rules declaring each mode, derived from the shipped
    # declarations (AC11).
    rules_by_mode: Dict[int, Tuple[str, ...]] = {}
    for mode in known_modes:
        rules_by_mode[mode] = tuple(
            sorted(
                rule_id
                for rule_id in registered_rule_ids
                if mode in declared_modes_by_rule.get(rule_id, ())
            )
        )

    unregistered_designated = tuple(
        sorted(rid for rid in corpus_map if rid not in registered_rule_ids)
    )

    mode_to_rule_holes = tuple(
        sorted(str(mode) for mode in known_modes if not rules_by_mode.get(mode))
    ) + unregistered_designated
    mode_to_rule_holes = tuple(sorted(set(mode_to_rule_holes)))
    mode_to_rule = DirectionReport(
        complete=not mode_to_rule_holes and not unregistered_designated,
        holes=mode_to_rule_holes,
    )

    # Both committed manifests -> cases_by_mode + pipeline_detected (item 149
    # AC18: re-derived across BOTH corpora, not the geometric one alone).
    from segfacet.synth import corpus as corpus_module
    from segfacet.synth import intensity as intensity_module

    manifest_cases_all = [
        ("geometric", c)
        for c in corpus_module.load_manifest().get("cases", [])
    ] + [
        ("intensity", c)
        for c in intensity_module.load_intensity_manifest().get("cases", [])
    ]
    cases_by_mode: Dict[int, Tuple[Tuple[str, str], ...]] = {}
    pipeline_detected_by_mode: Dict[int, bool] = {}
    for mode in known_modes:
        cases = tuple(
            (c["case_id"], c.get("detection"))
            for _corpus_name, c in manifest_cases_all
            if c.get("failure_mode") == mode
        )
        cases_by_mode[mode] = cases
        pipeline_detected_by_mode[mode] = any(
            detection in _PIPELINE_DETECTIONS for _cid, detection in cases
        )

    # Item 149 Decision D2: attribution is derived from the specification's
    # own corpus_cases (which span both corpora by construction), not from
    # scan_synth_rule_mode_map (which only ever matched geometric
    # Expectation(...) literals). The scan is still read above, for
    # corpus_designated_unregistered_rule_ids only.
    specification = failure_modes_module.SPECIFICATION
    corpus_rule_ids_by_mode: Dict[int, Set[str]] = {}
    for mode_id, mode_spec in specification.items():
        ids: Set[str] = set()
        for case in mode_spec.corpus_cases:
            ids |= set(case.expected_firing)
        corpus_rule_ids_by_mode[mode_id] = ids

    modes: list = []
    for mode in sorted(known_modes):
        anchors = tuple(mode_anchor_paths.get(mode, ()))
        rules_for_mode = rules_by_mode.get(mode, ())
        read_union: Set[str] = set()
        for rule_id in rules_for_mode:
            read_union |= signal_paths_by_rule.get(rule_id, set())
        corpus_designated_ids = corpus_rule_ids_by_mode.get(mode, set())
        attribution = tuple(
            (
                rule_id,
                "corpus" if rule_id in corpus_designated_ids else "analytic",
            )
            for rule_id in rules_for_mode
        )
        # Item 147/149: title, status, edge_rungs, rung and mechanism are
        # read live from the specification. ``derive_status``,
        # ``derive_mode_rung`` and ``SPECIFICATION`` are reached through the
        # module object (never bound by name at import) so a test can
        # substitute either and see the matrix follow.
        mode_spec = specification[mode]
        derived_rung = failure_modes_module.derive_mode_rung(mode_spec)
        # ``None`` is a legitimate answer -- mode 10, a `proposed` entry, has
        # no edges by design. It is carried as "" through the frozen record
        # and rendered as an explicit absence by both serialisers, never as a
        # blank indistinguishable from a failed lookup.
        rung = derived_rung or ""
        edge_rungs = tuple(
            (rule.rule_id, rule.detector, rule.evidence_rung)
            for rule in mode_spec.intended_rules
        )
        modes.append(
            ModeRecord(
                mode=mode,
                title=mode_spec.name,
                status=failure_modes_module.derive_status(mode_spec),
                authored_status=mode_spec.status,
                edge_rungs=edge_rungs,
                rung=rung,
                mechanism=mode_spec.mechanism,
                rules=rules_for_mode,
                rule_attribution=attribution,
                pipeline_detected=pipeline_detected_by_mode.get(mode, False),
                cases=cases_by_mode.get(mode, ()),
                anchor_paths=anchors,
                read_paths=tuple(sorted(read_union)),
                granularity="signal",
                read_paths_qualifier=_READ_PATHS_QUALIFIER,
            )
        )

    rules: list = []
    for rule_id in registered_rule_ids:
        rules.append(
            RuleRecord(
                rule_id=rule_id,
                modes=declared_modes_by_rule.get(rule_id, ()),
                declaration_state=declaration_state_by_rule.get(rule_id, "undeclared"),
                mode_less_reason=mode_less_reason_by_rule.get(rule_id, ""),
                evidence=evidence_by_rule.get(rule_id, ()),
                feature_paths=paths_by_rule.get(rule_id, ()),
            )
        )

    features = FeatureDirection(
        total_paths=total_paths,
        read_by_rule=read_by_rule,
        read_by_no_rule_count=read_by_no_rule,
        read_by_no_rule_required=False,
        read_by_no_rule_qualifier=_FEATURE_QUALIFIER,
        unwired=unwired,
        by_rule=tuple(sorted(by_rule_counts.items())),
    )

    classification_conflicts = tuple(path_classification_conflicts())
    conformance = _build_conformance(failure_modes_module)
    if classification_conflicts:
        conformance = ConformanceReport(
            cases=conformance.cases,
            agree_count=conformance.agree_count,
            disagree_count=conformance.disagree_count,
            conformant=False,
            disagreements=conformance.disagreements,
            unspecified_cases=conformance.unspecified_cases,
        )

    return TraceabilityMatrix(
        schema_version=SCHEMA_VERSION,
        primary_source=_PRIMARY_SOURCE,
        note=_NOTE,
        modes=tuple(modes),
        rules=tuple(rules),
        features=features,
        mode_to_rule=mode_to_rule,
        rule_to_mode=rule_to_mode,
        corpus_designated_unregistered_rule_ids=unregistered_designated,
        classification_conflicts=classification_conflicts,
        conformance=conformance,
    )


# =========================================================================== #
# matrix_to_dict / render_markdown
# =========================================================================== #


def _conformance_case_to_dict(case: ConformanceCase) -> dict:
    return {
        "corpus": case.corpus,
        "case_id": case.case_id,
        "mode": case.mode,
        "expected_firing": list(case.expected_firing),
        "measured_firing": list(case.measured_firing),
        "agrees": case.agrees,
        "expected_source": case.expected_source,
    }


def matrix_to_dict(matrix: TraceabilityMatrix) -> dict:
    """A deterministic, JSON-ready dict for *matrix*. Returns a fresh dict
    tree on every call -- mutating the result never leaks into a later
    call (AC32)."""
    return {
        "schema_version": matrix.schema_version,
        "primary_source": matrix.primary_source,
        "note": matrix.note,
        "modes": {
            str(m.mode): {
                "mode": m.mode,
                "title": m.title,
                "status": m.status,
                "authored_status": m.authored_status,
                "edge_rungs": [list(edge) for edge in m.edge_rungs],
                # An absent rung is `null`, not `""` (item 147 AC8): mode 10
                # legitimately has no edges to derive one from, and a JSON
                # reader must be able to tell that apart from a rung whose
                # lookup failed.
                "rung": m.rung or None,
                "mechanism": m.mechanism,
                "rules": list(m.rules),
                "rule_attribution": dict(m.rule_attribution),
                "pipeline_detected": m.pipeline_detected,
                "cases": [{"case_id": cid, "detection": det} for cid, det in m.cases],
                "anchor_paths": list(m.anchor_paths),
                "read_paths": list(m.read_paths),
                "granularity": m.granularity,
                "read_paths_qualifier": m.read_paths_qualifier,
            }
            for m in matrix.modes
        },
        "rules": {
            r.rule_id: {
                "rule_id": r.rule_id,
                "modes": list(r.modes),
                "declaration_state": r.declaration_state,
                "mode_less_reason": r.mode_less_reason,
                "evidence": list(r.evidence),
                "feature_paths": list(r.feature_paths),
                "feature_path_count": len(r.feature_paths),
            }
            for r in matrix.rules
        },
        "features": {
            "total_paths": matrix.features.total_paths,
            "read_by_rule": matrix.features.read_by_rule,
            "read_by_no_rule": {
                "count": matrix.features.read_by_no_rule_count,
                "required": matrix.features.read_by_no_rule_required,
                "qualifier": matrix.features.read_by_no_rule_qualifier,
            },
            "unwired": matrix.features.unwired,
            "by_rule": dict(matrix.features.by_rule),
        },
        "directions": {
            "mode_to_rule": {
                "complete": matrix.mode_to_rule.complete,
                "holes": list(matrix.mode_to_rule.holes),
            },
            "rule_to_mode": {
                "complete": matrix.rule_to_mode.complete,
                "holes": list(matrix.rule_to_mode.holes),
            },
        },
        "corpus_designated_unregistered_rule_ids": list(
            matrix.corpus_designated_unregistered_rule_ids
        ),
        "classification_conflicts": list(matrix.classification_conflicts),
        "conformance": {
            "cases": [_conformance_case_to_dict(c) for c in matrix.conformance.cases],
            "agree_count": matrix.conformance.agree_count,
            "disagree_count": matrix.conformance.disagree_count,
            "conformant": matrix.conformance.conformant,
            "disagreements": [
                _conformance_case_to_dict(c) for c in matrix.conformance.disagreements
            ],
            "unspecified_cases": [
                {"corpus": corpus, "case_id": case_id}
                for corpus, case_id in matrix.conformance.unspecified_cases
            ],
        },
    }


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(matrix: TraceabilityMatrix) -> str:
    """Render *matrix* as Markdown: a preamble, a mode table (immediately
    followed by the signal-classification qualifier), a rule table, the
    feature-direction section (its count immediately followed by the
    "inventory, not a gap" qualifier), and the conformance section (item
    149)."""
    lines = [
        "# Failure-Mode Conformance Report",
        "",
        _md_escape(matrix.note),
        "",
        f"Primary source: `{matrix.primary_source}`.",
        "",
        "## Section 6 modes -> rules",
        "",
        f"Direction complete: {matrix.mode_to_rule.complete}. "
        f"Holes: {', '.join(matrix.mode_to_rule.holes) if matrix.mode_to_rule.holes else 'none'}.",
        "",
        "| Mode | §6 title | Status (derived) | Status (authored) | "
        "Rules (attribution) | Per-edge rungs | Evidence rung (derived) | "
        "Pipeline-detected | Stage-18 metric anchor paths | Rule signal read paths |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in matrix.modes:
        attribution_by_rule = dict(m.rule_attribution)
        rules_cell = ", ".join(f"{rid} ({attribution_by_rule[rid]})" for rid in m.rules)
        edge_rungs_cell = "; ".join(
            f"{rule_id} ({detector or 'no detector named'}): {evidence_rung}"
            for rule_id, detector, evidence_rung in m.edge_rungs
        )
        cells = [
            str(m.mode),
            _md_escape(m.title),
            m.status,
            m.authored_status,
            _md_escape(rules_cell),
            _md_escape(edge_rungs_cell) or "(none)",
            f"{m.rung or '(none)'} -- {_md_escape(m.mechanism) or '(none)'}",
            str(m.pipeline_detected),
            ", ".join(m.anchor_paths) or "(none)",
            ", ".join(m.read_paths) or "(none)",
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            _md_escape(_READ_PATHS_QUALIFIER),
            "",
            "## Rules -> section 6 modes",
            "",
            f"Direction complete: {matrix.rule_to_mode.complete}. "
            f"Holes: {', '.join(matrix.rule_to_mode.holes) if matrix.rule_to_mode.holes else 'none'}.",
            "",
            "| Rule | Declared modes | State | Evidence | Feature paths |",
            "|---|---|---|---|---|",
        ]
    )
    for r in matrix.rules:
        state_cell = r.declaration_state
        if r.mode_less_reason:
            state_cell = f"{r.declaration_state}: {_md_escape(r.mode_less_reason)}"
        cells = [
            r.rule_id,
            ", ".join(str(mode) for mode in r.modes),
            state_cell,
            _md_escape(" · ".join(r.evidence)),
            ", ".join(r.feature_paths),
        ]
        lines.append("| " + " | ".join(cells) + " |")

    unregistered = ", ".join(matrix.corpus_designated_unregistered_rule_ids) or "none"
    lines.extend(
        [
            "",
            f"Corpus-designated rule ids that no rule registers: {unregistered}.",
            "",
            "## Features -> rules",
            "",
            f"Total catalogued paths: {matrix.features.total_paths}. "
            f"Read by >=1 rule: {matrix.features.read_by_rule}. "
            f"Read by no rule: {matrix.features.read_by_no_rule_count}. "
            f"Unwired: {matrix.features.unwired}.",
            "",
            _md_escape(matrix.features.read_by_no_rule_qualifier),
            "",
            "## Classification conflicts",
            "",
        ]
    )
    if matrix.classification_conflicts:
        for message in matrix.classification_conflicts:
            lines.append(f"- {_md_escape(message)}")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Conformance — expected vs measured firing",
            "",
            f"Agree: {matrix.conformance.agree_count}. "
            f"Disagree: {matrix.conformance.disagree_count}. "
            f"Conformant: {matrix.conformance.conformant}.",
            "",
            "| Corpus | Case | Mode | Expected firing | Measured firing | Agrees | Source |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for c in matrix.conformance.cases:
        cells = [
            c.corpus,
            c.case_id,
            str(c.mode),
            ", ".join(c.expected_firing) or "(none)",
            ", ".join(c.measured_firing) or "(none)",
            str(c.agrees),
            c.expected_source,
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(["", "Disagreements:", ""])
    if matrix.conformance.disagreements:
        for c in matrix.conformance.disagreements:
            lines.append(
                f"- {c.corpus}/{c.case_id} (mode {c.mode}): expected "
                f"[{', '.join(c.expected_firing) or 'none'}], measured "
                f"[{', '.join(c.measured_firing) or 'none'}], source: "
                f"{c.expected_source}."
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "Unspecified cases (a manifest case with no covering `ModeSpec.corpus_cases` entry):", ""])
    if matrix.conformance.unspecified_cases:
        for corpus, case_id in matrix.conformance.unspecified_cases:
            lines.append(f"- {corpus}/{case_id}")
    else:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


# =========================================================================== #
# __main__
# =========================================================================== #


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Regenerate the generated failure-mode conformance report (item 149; was the traceability matrix, item 138)."
    )
    parser.add_argument("--json", type=Path, default=JSON_PATH)
    parser.add_argument("--md", type=Path, default=MD_PATH)
    args = parser.parse_args(argv)

    matrix = build_matrix()

    json_text = json.dumps(matrix_to_dict(matrix), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    md_text = render_markdown(matrix)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_bytes(json_text.encode("utf-8"))
    args.md.write_bytes(md_text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
