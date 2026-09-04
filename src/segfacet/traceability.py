"""Generated failure-mode <-> rule <-> feature traceability matrix (item 138;
Stage 20 -- Failure-Mode <-> Feature <-> Rule Traceability & Specificity
Harness).

Assembles item 103's generated feature catalogue
(:func:`segfacet.catalogue.build_catalogue`), the rule registry
(:func:`segfacet.heuristics.rule.iter_rules`), items 136/137's
``RuleModeDeclaration``s, the corpus-derived ``rule_id -> section 6 mode`` map
(:func:`segfacet.catalogue.scan_synth_rule_mode_map`) and the committed corpus
manifest (:func:`segfacet.synth.corpus.load_manifest`) into one committed
matrix, over **three directions scored separately**:

- **mode -> rule** -- complete, always: every catalogued section-6 mode must
  have >=1 declaring rule, or the direction is reported ``complete: False``
  with the mode named as a hole.
- **rule -> mode** -- complete, always: every registered rule must carry
  either a targeted or a mode-less declaration, or the direction is reported
  ``complete: False`` with the rule named as a hole.
- **feature -> rule** -- deliberately **not** complete. The feature record is
  an over-broad vector rules select from; a leaf path read by no rule is
  *inventory, not a gap*. The matrix carries that qualifier beside the count
  it reports, in both artifacts, so it cannot be mistaken for a shortfall.

Every mode row also carries an **evidence rung** from the closed
three-value vocabulary the roadmap fixes -- whether the mode's failure has
actually been *demonstrated end-to-end* on the corpus, which is a claim
distinct from "a rule covers this mode" -- plus the mechanism sentence that
says why. **Item 147 retired this module's authored constants for both.**
Every mode row's ``title``, ``rung``, ``rung_label`` and ``mechanism`` are
now read live from ``segfacet.failure_modes``: the title from
``SPECIFICATION[mode].name``, the rung from ``derive_mode_rung()`` folding
that mode's per-edge ``evidence_rung``s (item 145), the label from the
moved ``RUNG_LABELS``, and the sentence from the authored
``ModeSpec.mechanism``. This module authors no mode fact of its own any
more; it reads and reports. Everything checked *about* those fields
(closed-vocabulary membership, the corpus cross-check, and that the
mechanism names a token that resolves against live state) stays derived
and enforced by the test suite, never by a character-count floor (A14).

The §6 seed-title parse this module used to own has moved to
``segfacet.failure_modes.vision_seed_titles()`` (item 147 AC4), which is
now the only module under ``src/segfacet/`` that reads the vision
document at all. The seed titles are checked against the specification's
names there rather than substituted for them here.

Every (mode, rule) edge additionally carries an **attribution** --
``"corpus"`` when the corpus-derived map itself designates that rule for
that mode, ``"analytic"`` when only the rule's own declaration claims it,
derived from :func:`segfacet.catalogue.scan_synth_rule_mode_map` and never
from the declaration's own free-form ``evidence`` tag (item 137's A7,
closed here).

Scope fence
-----------
This module *reports*. It decides no disposition, changes no rule,
threshold, extractor, verdict, report schema, or CLI behaviour, and
regenerates neither of item 103's catalogue artifacts. It is not the
per-rule / per-operator corpus-exercise report (item 139, which extends this
same module and these same artifacts), does not adopt the specificity
ratchet (item 140), and does not touch ``eval/severity_ladder.py`` (item
141).

Determinism contract
---------------------
:func:`build_matrix` never mutates any input; two calls return equal,
immutable matrices (frozen dataclasses / tuples throughout). Heavy imports
(NumPy/SciPy/NiBabel, via ``segfacet.catalogue``/``segfacet.heuristics``) are
deferred into function bodies, per house style, so ``import
segfacet.traceability`` alone stays cheap and importing it plus calling
:func:`build_matrix` never mutates any importable module's state (AC30).

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
from typing import Dict, Mapping, Optional, Sequence, Tuple

__all__ = ["build_matrix", "matrix_to_dict", "render_markdown", "main"]

SCHEMA_VERSION = "1.0"

_REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
MD_PATH = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"

_NOTE = (
    "Generated by `python -m segfacet.traceability` (item 138). Do not "
    "hand-edit this document -- edit the authored failure-mode "
    "specification in src/segfacet/failure_modes.py (every mode's title, "
    "per-edge evidence rung and mechanism sentence is read live from it "
    "since item 147) or the underlying rule/catalogue sources this matrix "
    "derives from, then regenerate. "
    "mode -> rule and rule -> mode each report their own completeness and "
    "name every hole: read the `complete`/`holes` fields rather than "
    "assuming either is complete. Since item 146 a mode may legitimately "
    "carry no rule -- a `proposed` entry in "
    "segfacet.failure_modes.SPECIFICATION is listed and defined but "
    "deliberately unimplemented -- and it appears as a mode -> rule hole. "
    "feature -> rule is deliberately incomplete -- see "
    "the `features.read_by_no_rule.qualifier` field."
)

_FEATURE_QUALIFIER = (
    "a leaf path no rule reads is inventory, not a gap: the feature record "
    "is a deliberately over-broad vector rules select from, and full "
    "consumption is never an expected end state."
)

_GRANULARITY_QUALIFIER = (
    "mode -> feature is rule-granular: a path's presence in a mode row "
    "means a rule that targets this mode reads this path, not that this "
    "path alone evidences this mode."
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
# The retired block was the second of the five partial sources queue-020
# names. Do not re-introduce a constant here: a mode fact belongs in the
# specification.
# =========================================================================== #


# =========================================================================== #
# Frozen record dataclasses
# =========================================================================== #


@dataclass(frozen=True)
class ModeRecord:
    mode: int
    title: str
    rung: str
    rung_label: str
    mechanism: str
    rules: Tuple[str, ...]
    rule_attribution: Tuple[Tuple[str, str], ...]
    pipeline_detected: bool
    cases: Tuple[Tuple[str, str], ...]
    anchor_paths: Tuple[str, ...]
    feature_paths: Tuple[str, ...]
    granularity: str
    feature_paths_qualifier: str


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
class TraceabilityMatrix:
    schema_version: str
    note: str
    modes: Tuple[ModeRecord, ...]
    rules: Tuple[RuleRecord, ...]
    features: FeatureDirection
    mode_to_rule: DirectionReport
    rule_to_mode: DirectionReport
    corpus_designated_unregistered_rule_ids: Tuple[str, ...]


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


def build_matrix() -> TraceabilityMatrix:
    """Assemble the full :class:`TraceabilityMatrix`.

    Never mutates any input (the registry, the catalogue, the manifest);
    two calls return equal matrices. Deferred imports (house style)."""
    import re

    from segfacet import failure_modes as failure_modes_module
    from segfacet import feature_docs as feature_docs_module
    from segfacet.catalogue import (
        build_catalogue,
        rule_declaration_conflicts,
        scan_synth_rule_mode_map,
    )
    from segfacet.heuristics.rule import iter_rule_declarations, iter_rules
    from segfacet.synth.corpus import load_manifest

    mode_anchor_paths = feature_docs_module.MODE_ANCHOR_PATHS
    # The matrix's known-mode source is the authored specification (item
    # 144), not feature_docs.MODE_ANCHOR_PATHS's key set -- mirrors A7's
    # move for catalogue.rule_declaration_conflicts (item 146). A mode with
    # no MODE_ANCHOR_PATHS entry (mode 9) still gets a full mode row; its
    # anchor_paths render empty via mode_anchor_paths.get(mode, ()).
    known_modes = set(failure_modes_module.SPECIFICATION.keys())

    cat = build_catalogue(strict=True)
    paths_by_rule: Dict[str, Tuple[str, ...]] = {}
    for rule_id_iter in {rid for entry in cat.entries for rid in entry.consuming_rules}:
        paths_by_rule[rule_id_iter] = tuple(
            sorted(e.path for e in cat.entries if rule_id_iter in e.consuming_rules)
        )

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
    # specification (item 146's A7 move: known_modes above, not
    # feature_docs.MODE_ANCHOR_PATHS's key set). A rule declaring only
    # modes outside failure_modes.SPECIFICATION's key set is "declared" by
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

    # Corpus manifest -> cases_by_mode + pipeline_detected.
    manifest = load_manifest()
    cases_by_mode: Dict[int, Tuple[Tuple[str, str], ...]] = {}
    pipeline_detected_by_mode: Dict[int, bool] = {}
    for mode in known_modes:
        cases = tuple(
            (c["case_id"], c.get("detection"))
            for c in manifest.get("cases", [])
            if c.get("failure_mode") == mode
        )
        cases_by_mode[mode] = cases
        pipeline_detected_by_mode[mode] = any(detection == "pipeline" for _cid, detection in cases)

    specification = failure_modes_module.SPECIFICATION

    modes: list = []
    for mode in sorted(known_modes):
        anchors = tuple(mode_anchor_paths.get(mode, ()))
        rules_for_mode = rules_by_mode.get(mode, ())
        feature_union = set(anchors)
        for rule_id in rules_for_mode:
            feature_union |= set(paths_by_rule.get(rule_id, ()))
        attribution = tuple(
            (
                rule_id,
                "corpus" if mode in corpus_map.get(rule_id, ()) else "analytic",
            )
            for rule_id in rules_for_mode
        )
        # Item 147: title, rung, rung_label and mechanism are read live from
        # the specification. ``derive_mode_rung`` and ``SPECIFICATION`` are
        # reached through the module object (never bound by name at import)
        # so a test can substitute either and see the matrix follow.
        mode_spec = specification[mode]
        derived_rung = failure_modes_module.derive_mode_rung(mode_spec)
        # ``None`` is a legitimate answer -- mode 10, a `proposed` entry, has
        # no edges by design. It is carried as "" through the frozen record
        # and rendered as an explicit absence by both serialisers, never as a
        # blank indistinguishable from a failed lookup.
        rung = derived_rung or ""
        modes.append(
            ModeRecord(
                mode=mode,
                title=mode_spec.name,
                rung=rung,
                rung_label=failure_modes_module.RUNG_LABELS.get(rung, ""),
                mechanism=mode_spec.mechanism,
                rules=rules_for_mode,
                rule_attribution=attribution,
                pipeline_detected=pipeline_detected_by_mode.get(mode, False),
                cases=cases_by_mode.get(mode, ()),
                anchor_paths=anchors,
                feature_paths=tuple(sorted(feature_union)),
                granularity="rule",
                feature_paths_qualifier=_GRANULARITY_QUALIFIER,
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

    return TraceabilityMatrix(
        schema_version=SCHEMA_VERSION,
        note=_NOTE,
        modes=tuple(modes),
        rules=tuple(rules),
        features=features,
        mode_to_rule=mode_to_rule,
        rule_to_mode=rule_to_mode,
        corpus_designated_unregistered_rule_ids=unregistered_designated,
    )


# =========================================================================== #
# matrix_to_dict / render_markdown
# =========================================================================== #


def matrix_to_dict(matrix: TraceabilityMatrix) -> dict:
    """A deterministic, JSON-ready dict for *matrix*. Returns a fresh dict
    tree on every call -- mutating the result never leaks into a later
    call (AC30)."""
    return {
        "schema_version": matrix.schema_version,
        "note": matrix.note,
        "modes": {
            str(m.mode): {
                "mode": m.mode,
                "title": m.title,
                # An absent rung is `null`, not `""` (item 147 AC8): mode 10
                # legitimately has no edges to derive one from, and a JSON
                # reader must be able to tell that apart from a rung whose
                # lookup failed.
                "rung": m.rung or None,
                "rung_label": m.rung_label,
                "mechanism": m.mechanism,
                "rules": list(m.rules),
                "rule_attribution": dict(m.rule_attribution),
                "pipeline_detected": m.pipeline_detected,
                "cases": [{"case_id": cid, "detection": det} for cid, det in m.cases],
                "anchor_paths": list(m.anchor_paths),
                "feature_paths": list(m.feature_paths),
                "granularity": m.granularity,
                "feature_paths_qualifier": m.feature_paths_qualifier,
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
    }


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(matrix: TraceabilityMatrix) -> str:
    """Render *matrix* as Markdown: a preamble, a mode table (immediately
    followed by the rule-granularity qualifier), a rule table, and the
    feature-direction section (its count immediately followed by the
    "inventory, not a gap" qualifier)."""
    lines = [
        "# Failure-Mode <-> Rule <-> Feature Traceability Matrix",
        "",
        _md_escape(matrix.note),
        "",
        "## Section 6 modes -> rules",
        "",
        f"Direction complete: {matrix.mode_to_rule.complete}. "
        f"Holes: {', '.join(matrix.mode_to_rule.holes) if matrix.mode_to_rule.holes else 'none'}.",
        "",
        "| Mode | §6 title | Rules (attribution) | Evidence rung | "
        "Pipeline-detected | Stage-18 metric anchor paths | Feature paths |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in matrix.modes:
        attribution_by_rule = dict(m.rule_attribution)
        rules_cell = ", ".join(f"{rid} ({attribution_by_rule[rid]})" for rid in m.rules)
        cells = [
            str(m.mode),
            _md_escape(m.title),
            _md_escape(rules_cell),
            f"{m.rung or '(none)'} -- {_md_escape(m.mechanism) or '(none)'}",
            str(m.pipeline_detected),
            ", ".join(m.anchor_paths) or "(none)",
            ", ".join(m.feature_paths),
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            _md_escape(_GRANULARITY_QUALIFIER),
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
        ]
    )
    return "\n".join(lines) + "\n"


# =========================================================================== #
# __main__
# =========================================================================== #


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Regenerate the generated failure-mode <-> rule <-> feature traceability matrix (item 138)."
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
