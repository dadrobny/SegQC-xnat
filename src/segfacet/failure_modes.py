"""The failure-mode specification module (item 144; Stage 30 -- Failure-Mode
Specification: the vision.md §6 catalogue as an authored source).

This module is the **primary record** vision.md §6 describes: one frozen
:class:`ModeSpec` declaration per §6 failure mode, shaped after
``RuleModeDeclaration`` (:mod:`segfacet.heuristics.rule`, item 136), from
which ``docs/aide/failure_modes.generated.{md,json}`` are rendered by
zero-argument regeneration (:func:`main`). Today the catalogue exists as five
partial sources that agree without any of them being a specification
(queue-020, "The five partial sources this stage collapses"); this module is
the object the rest of the stage (items 145-151) reads, writes into, and
renders.

**This module ships the schema, the validation, the derivation and the
rendering -- not the entries.** :data:`SPECIFICATION` carries a **minimal
seed set of two entries** (modes 3 and 8) chosen to exercise both derivation
paths end-to-end (item spec A4): mode 3 is ``single-channel-observable`` with
a ``pipeline``-detected corpus case, and mode 8 is
``structurally-unobservable`` with a ``reconstructed_record``-detected corpus
case. The remaining seven modes are item 145's; the ninth mode and the first
``proposed`` entry are item 146's.

Lifecycle status
-----------------
``status`` is **authored only** for ``"proposed"`` and ``"specified"``
(:data:`AUTHORED_STATUSES`) -- constructing a :class:`ModeSpec` with
``status="implemented"`` or ``status="validated"`` raises ``ValueError``
even though both are members of :data:`STATUSES`. ``"implemented"`` (>=1
**registered** rule declares the mode) and ``"validated"`` (every corpus
case's **measured** firing set equals its authored ``expected_firing``) are
derived from live state on every read and on every regeneration by
:func:`derive_status` -- never authored, and a value forced past
``__post_init__`` (via ``object.__setattr__``) is reported by
:func:`specification_conflicts`, naming the mode.

Scope fence
-----------
No new rule, threshold, extractor, verdict, report schema or CLI behaviour.
Nothing under ``src/segfacet/heuristics/`` changes: :func:`derive_status`
*reads* the registry and each rule's ``RuleModeDeclaration``; moving any
declaration onto this schema is item 146's/147's. No corpus case is added or
changed; the committed corpus (``tests/corpus/manifest.json``) is **read** to
measure firing sets. ``vision.md`` and ``roadmap.md`` are not edited.

Determinism contract
---------------------
:func:`specification_to_dict` and :func:`render_markdown` never mutate any
input and return a fresh tree on every call; two calls compare equal and
neither leaks state into a later call. Heavy imports (NumPy / SciPy /
NiBabel, reached only through :mod:`segfacet.synth.regression` inside
:func:`measured_firing`) are deferred into function bodies, per house style
(:mod:`segfacet.traceability`), so ``import segfacet.failure_modes`` alone
stays cheap.

Public API
----------
``ModeSpec``, ``CandidateFeature``, ``IntendedRule``, ``CorpusCaseExpectation``
    Frozen dataclasses (the schema).
``SPECIFICATION``
    The immutable, ascending-by-id seed (a ``MappingProxyType``).
``iter_modes() -> Iterator[ModeSpec]``
    Yield the seed modes in ascending ``id`` order. Takes no argument.
``derive_status(mode) -> str`` / ``derive_mode_rung(mode) -> Optional[str]``
    Live derivations (AC9/AC10, AC14).
``measured_firing(case) -> Tuple[str, ...]`` / ``case_agrees(case) -> bool``
    Drive one ``CorpusCaseExpectation`` through the same public harness
    ``segfacet.synth.regression`` exposes (dispatching on the manifest case's
    ``detection`` field), and compare against its authored
    ``expected_firing``.
``specification_conflicts(modes=None) -> Tuple[str, ...]``
    The conformance check: a hand-set derived ``status`` past construction,
    named. Defaults to the shipped :data:`SPECIFICATION`.
``specification_to_dict() -> dict``
    A deterministic, JSON-ready dict. Takes no argument.
``render_markdown() -> str``
    A deterministic Markdown rendering of the same specification.
``main(argv=None) -> int``
    ``python -m segfacet.failure_modes [--json PATH] [--md PATH]``; defaults
    to the two committed artifact paths under ``docs/aide/``.

Sign-off
--------
No maintainer sign-off is recorded yet. Item 150 records it here, in this
docstring, once the finished Stage-30 rendering (items 145-149) has been
reviewed.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import MappingProxyType
from typing import Dict, FrozenSet, Iterable, Iterator, Mapping, Optional, Tuple

__all__ = [
    "ModeSpec",
    "CandidateFeature",
    "IntendedRule",
    "CorpusCaseExpectation",
    "SPECIFICATION",
    "iter_modes",
    "derive_status",
    "derive_mode_rung",
    "measured_firing",
    "case_agrees",
    "specification_conflicts",
    "specification_to_dict",
    "render_markdown",
    "main",
    "STATUSES",
    "AUTHORED_STATUSES",
    "OBSERVABILITY",
    "PROVENANCE",
    "CANDIDATE_ROLES",
    "EVIDENCE_RUNGS",
    "SCHEMA_VERSION",
    "JSON_PATH",
    "MD_PATH",
]

SCHEMA_VERSION = "1.0"

_REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.json"
MD_PATH = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.md"

_NOTE = (
    "Generated by `python -m segfacet.failure_modes` (item 144). Do not "
    "hand-edit this document -- edit the seed ModeSpec entries in "
    "src/segfacet/failure_modes.py (the authored fields), then regenerate. "
    "`status_authored` is the hand-set proposed/specified value; "
    "`status_derived` and `derived_rung` are computed live from the rule "
    "registry and the committed corpus on every regeneration -- never "
    "hand-set past construction (see specification_conflicts())."
)


# =========================================================================== #
# Closed vocabularies (AC4-AC6, AC12, AC13, AC15)
# =========================================================================== #

STATUSES: Tuple[str, ...] = ("proposed", "specified", "implemented", "validated")
AUTHORED_STATUSES: Tuple[str, ...] = ("proposed", "specified")

OBSERVABILITY: Tuple[str, ...] = (
    "single-channel-observable",
    "needs-paired-scan",
    "structurally-unobservable",
)

PROVENANCE: Tuple[str, ...] = ("hypothesised", "discovered")

CANDIDATE_ROLES: Tuple[str, ...] = ("stage18-metric-anchor", "hypothesised")

# Strongest-first (A6 / AC14: "a mode's rung is derived as the strongest of
# its edges").
EVIDENCE_RUNGS: Tuple[str, ...] = (
    "synthetic-demonstrable",
    "needs-real-data",
    "structurally-unobservable",
)
_RUNG_STRENGTH: Dict[str, int] = {rung: index for index, rung in enumerate(EVIDENCE_RUNGS)}


def _accepted_severities() -> FrozenSet[str]:
    """Derived from :class:`segfacet.verdict.Severity`, minus ``"pass"``
    (A9/AC15) -- never hand-typed, so this stays honest if the enum changes."""
    from segfacet.verdict import Severity

    return frozenset(s.label for s in Severity) - {"pass"}


# =========================================================================== #
# Frozen record dataclasses -- the schema (AC2, AC12, AC13)
#
# Only ModeSpec validates (its __post_init__ walks the whole tree it owns);
# CandidateFeature / IntendedRule / CorpusCaseExpectation are plain frozen
# records so a caller can construct an intentionally-invalid one to exercise
# ModeSpec's validation (the item spec's Testing Strategy pattern).
# =========================================================================== #


@dataclasses.dataclass(frozen=True)
class CandidateFeature:
    """One candidate feature path for a mode, labelled with its **role**
    (AC12) -- ``"stage18-metric-anchor"`` (validated against
    ``segfacet.feature_docs.MODE_ANCHOR_PATHS[mode.id]`` by
    :class:`ModeSpec`) or ``"hypothesised"`` (not yet anchored)."""

    path: str
    role: str


@dataclasses.dataclass(frozen=True)
class IntendedRule:
    """One mode <-> rule edge, carrying the **per-edge evidence rung**
    (AC13, gate 3 decision 3). ``detector`` names the specific detector
    within a rule that has several; may be empty."""

    rule_id: str
    detector: str
    evidence_rung: str


@dataclasses.dataclass(frozen=True)
class CorpusCaseExpectation:
    """One committed corpus case's **expected** firing set for a mode (A2:
    the full set of ``rule_id``s the case's detection path produces, not the
    manifest's narrower ``expected_rule_ids``)."""

    case_id: str
    corpus: str
    expected_firing: Tuple[str, ...]
    reason: str


@dataclasses.dataclass(frozen=True)
class ModeSpec:
    """One frozen failure-mode declaration, carrying exactly vision.md §6's
    fields (AC2). Validates the whole tree it owns in ``__post_init__``;
    every raised ``ValueError`` names the offending mode (``id``, or
    ``name`` where ``id`` itself is the offending field) and field."""

    id: int
    name: str
    definition: str
    discriminator: str
    observability: str
    candidate_features: Tuple[CandidateFeature, ...]
    intended_rules: Tuple[IntendedRule, ...]
    corpus_cases: Tuple[CorpusCaseExpectation, ...]
    severity: str
    status: str
    provenance: str

    def __post_init__(self) -> None:
        self._require_valid_id()

        for field_name in (
            "name",
            "definition",
            "discriminator",
            "observability",
            "severity",
            "status",
            "provenance",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"ModeSpec {self.id}: '{field_name}' must be a non-empty str, "
                    f"got {value!r}."
                )

        if self.status not in STATUSES:
            raise ValueError(
                f"ModeSpec {self.id}: 'status' {self.status!r} is not a member of "
                f"STATUSES {STATUSES}."
            )
        if self.status not in AUTHORED_STATUSES:
            raise ValueError(
                f"ModeSpec {self.id}: 'status' may only be authored as one of "
                f"AUTHORED_STATUSES {AUTHORED_STATUSES}; {self.status!r} is derived "
                f"exclusively by derive_status(), never hand-authored past construction."
            )

        if self.observability not in OBSERVABILITY:
            raise ValueError(
                f"ModeSpec {self.id}: 'observability' {self.observability!r} is not a "
                f"member of OBSERVABILITY {OBSERVABILITY}."
            )

        if self.provenance not in PROVENANCE:
            raise ValueError(
                f"ModeSpec {self.id}: 'provenance' {self.provenance!r} is not a member "
                f"of PROVENANCE {PROVENANCE}."
            )

        accepted_severities = _accepted_severities()
        if self.severity not in accepted_severities:
            raise ValueError(
                f"ModeSpec {self.id}: 'severity' {self.severity!r} is not a member of "
                f"{sorted(accepted_severities)} (derived from segfacet.verdict.Severity, "
                f"minus 'pass')."
            )

        self._validate_candidate_features()
        self._validate_intended_rules()
        self._validate_corpus_cases()

    def _require_valid_id(self) -> None:
        value = self.id
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(
                f"ModeSpec {self.name!r}: 'id' must be an int >= 1, got {value!r}."
            )

    def _validate_candidate_features(self) -> None:
        if not isinstance(self.candidate_features, tuple):
            raise ValueError(
                f"ModeSpec {self.id}: 'candidate_features' must be a tuple, got "
                f"{type(self.candidate_features).__name__}."
            )

        from segfacet import feature_docs as feature_docs_module

        for feature in self.candidate_features:
            if not isinstance(feature, CandidateFeature):
                raise ValueError(
                    f"ModeSpec {self.id}: 'candidate_features' elements must be "
                    f"CandidateFeature, got {feature!r}."
                )
            if feature.role not in CANDIDATE_ROLES:
                raise ValueError(
                    f"ModeSpec {self.id}: candidate feature {feature.path!r} has role "
                    f"{feature.role!r}, which is not a member of CANDIDATE_ROLES "
                    f"{CANDIDATE_ROLES}."
                )
            if feature.role == "stage18-metric-anchor":
                anchor_paths = feature_docs_module.MODE_ANCHOR_PATHS.get(self.id)
                if anchor_paths is None:
                    raise ValueError(
                        f"ModeSpec {self.id}: candidate feature {feature.path!r} is "
                        f"labelled 'stage18-metric-anchor', but mode {self.id} has no "
                        f"entry in segfacet.feature_docs.MODE_ANCHOR_PATHS (keys: "
                        f"{sorted(feature_docs_module.MODE_ANCHOR_PATHS)})."
                    )
                if feature.path not in anchor_paths:
                    raise ValueError(
                        f"ModeSpec {self.id}: candidate feature path {feature.path!r} "
                        f"is labelled 'stage18-metric-anchor' but is not an element of "
                        f"MODE_ANCHOR_PATHS[{self.id}] {anchor_paths!r}."
                    )

    def _validate_intended_rules(self) -> None:
        if not isinstance(self.intended_rules, tuple):
            raise ValueError(
                f"ModeSpec {self.id}: 'intended_rules' must be a tuple, got "
                f"{type(self.intended_rules).__name__}."
            )

        seen_rule_ids: set = set()
        for rule in self.intended_rules:
            if not isinstance(rule, IntendedRule):
                raise ValueError(
                    f"ModeSpec {self.id}: 'intended_rules' elements must be "
                    f"IntendedRule, got {rule!r}."
                )
            if not rule.rule_id:
                raise ValueError(
                    f"ModeSpec {self.id}: an intended rule has an empty 'rule_id' "
                    f"({rule!r})."
                )
            if rule.evidence_rung not in EVIDENCE_RUNGS:
                raise ValueError(
                    f"ModeSpec {self.id}: intended rule {rule.rule_id!r} has "
                    f"evidence_rung {rule.evidence_rung!r}, which is not a member of "
                    f"EVIDENCE_RUNGS {EVIDENCE_RUNGS}."
                )
            if rule.rule_id in seen_rule_ids:
                raise ValueError(
                    f"ModeSpec {self.id}: duplicate intended-rule rule_id "
                    f"{rule.rule_id!r}."
                )
            seen_rule_ids.add(rule.rule_id)

    def _validate_corpus_cases(self) -> None:
        if not isinstance(self.corpus_cases, tuple):
            raise ValueError(
                f"ModeSpec {self.id}: 'corpus_cases' must be a tuple, got "
                f"{type(self.corpus_cases).__name__}."
            )

        seen_case_ids: set = set()
        for case in self.corpus_cases:
            if not isinstance(case, CorpusCaseExpectation):
                raise ValueError(
                    f"ModeSpec {self.id}: 'corpus_cases' elements must be "
                    f"CorpusCaseExpectation, got {case!r}."
                )
            if not isinstance(case.expected_firing, tuple):
                raise ValueError(
                    f"ModeSpec {self.id}: corpus case {case.case_id!r}'s "
                    f"'expected_firing' must be a tuple, got "
                    f"{type(case.expected_firing).__name__}."
                )
            if case.case_id in seen_case_ids:
                raise ValueError(
                    f"ModeSpec {self.id}: duplicate corpus case_id {case.case_id!r}."
                )
            seen_case_ids.add(case.case_id)


# =========================================================================== #
# The shipped seed (A4): modes 3 and 8 only.
#
# expected_firing is measured live on the item-143-corrected corpus and
# recorded literally here (transcribing a *computed* value would defeat AC1's
# no-heavy-import-at-module-level contract) -- see this item's Decisions log
# for the measurement transcript.
# =========================================================================== #

_MODE_3 = ModeSpec(
    id=3,
    name="Disconnected components / islands, especially tiny rogue segments",
    definition=(
        "A label's foreground voxels split into more than one connected "
        "component, with at least one stray component far smaller than the "
        "dominant body."
    ),
    discriminator=(
        "Distinguishes from mode 2 (over-/under-segmentation) by whether the "
        "dominant body itself stays intact."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="per_label.{label}.components.stray_component_sizes[]",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="fragmentation",
            detector="",
            evidence_rung="synthetic-demonstrable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode3_inject_islands",
            corpus="geometric",
            expected_firing=("fragmentation",),
            reason=(
                "pipeline-detected; fragmentation is the sole rule that fires "
                "on this corpus case, measured live via "
                "segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03)."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_8 = ModeSpec(
    id=8,
    name="Overlapping segments",
    definition="Two labels' foreground voxel sets intersect.",
    discriminator=(
        "Distinguishes from every other mode by requiring a second label's "
        "mask, unobservable from a single label map alone."
    ),
    observability="structurally-unobservable",
    candidate_features=(
        CandidateFeature(
            path="overlaps[].overlap_voxels",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="overlap",
            detector="",
            evidence_rung="structurally-unobservable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode8_force_overlap",
            corpus="geometric",
            expected_firing=("overlap",),
            reason=(
                "reconstructed-record-detected; overlap is the sole rule that "
                "fires on this corpus case, measured live via "
                "segfacet.synth.regression.reconstructed_findings on the "
                "item-143-corrected corpus (2026-09-03)."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

SPECIFICATION: Mapping[int, ModeSpec] = MappingProxyType(
    {mode.id: mode for mode in (_MODE_3, _MODE_8)}
)


def iter_modes() -> Iterator[ModeSpec]:
    """Yield the seed modes in ascending ``id`` order. Takes no argument."""
    for mode_id in sorted(SPECIFICATION):
        yield SPECIFICATION[mode_id]


# =========================================================================== #
# Derivation: measured_firing / case_agrees / derive_status / derive_mode_rung
# (AC9, AC10, AC14) -- deferred heavy imports (A3).
# =========================================================================== #


def measured_firing(case: CorpusCaseExpectation) -> Tuple[str, ...]:
    """The full set of ``rule_id``s among the findings *case*'s manifest
    entry's detection path produces, measured live through
    :mod:`segfacet.synth.regression` (A3) -- ``pipeline_findings`` for
    ``detection == "pipeline"``, ``reconstructed_findings`` for
    ``detection == "reconstructed_record"``. Only the geometric corpus is
    readable this way today (A3); ``corpus`` on *case* is informational, not
    a dispatch key."""
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.regression import pipeline_findings, reconstructed_findings

    manifest = load_manifest()
    manifest_case = None
    for candidate in manifest.get("cases", []):
        if candidate.get("case_id") == case.case_id:
            manifest_case = candidate
            break
    if manifest_case is None:
        raise ValueError(
            f"measured_firing: case_id {case.case_id!r} not found in the committed "
            f"corpus manifest (corpus={case.corpus!r})."
        )

    detection = manifest_case.get("detection")
    if detection == "pipeline":
        findings = pipeline_findings(manifest_case)
    elif detection == "reconstructed_record":
        findings = reconstructed_findings(manifest_case)
    else:
        raise ValueError(
            f"measured_firing: unrecognised detection {detection!r} for "
            f"case_id={case.case_id!r}."
        )
    return tuple(sorted({finding.rule_id for finding in findings}))


def case_agrees(case: CorpusCaseExpectation) -> bool:
    """``True`` iff *case*'s live :func:`measured_firing` set equals its
    authored ``expected_firing`` set."""
    return set(measured_firing(case)) == set(case.expected_firing)


def _registry_declares_exactly(mode_id: int) -> bool:
    """``True`` iff a rule is currently registered whose own
    ``RuleModeDeclaration.modes`` is exactly ``(mode_id,)`` -- a rule
    dedicated to this one mode, used only when *mode* carries no corpus case
    to measure against (AC9)."""
    from segfacet.heuristics.rule import iter_rule_declarations

    for _rule_id, declaration in iter_rule_declarations():
        if declaration is not None and declaration.modes == (mode_id,):
            return True
    return False


def derive_status(mode: ModeSpec) -> str:
    """The live-derived lifecycle status for *mode* (AC9, AC10).

    ``"validated"`` iff *mode* carries >=1 corpus case and every one
    :func:`case_agrees`. Otherwise, if *mode* carries >=1 corpus case, at
    least one measurement has run and disagreed --
    ``"implemented"``. With no corpus case at all, ``"implemented"`` iff a
    registered rule is dedicated to exactly this mode
    (:func:`_registry_declares_exactly`); otherwise the authored
    ``mode.status`` (``"proposed"`` or ``"specified"``) is returned
    unchanged. The empty set never satisfies the "every case agrees"
    quantifier vacuously -- an empty ``corpus_cases`` cannot reach
    ``"validated"``.
    """
    if mode.corpus_cases:
        if all(case_agrees(case) for case in mode.corpus_cases):
            return "validated"
        return "implemented"
    if _registry_declares_exactly(mode.id):
        return "implemented"
    return mode.status


def derive_mode_rung(mode: ModeSpec) -> Optional[str]:
    """The strongest :data:`EVIDENCE_RUNGS` member among *mode*'s
    ``intended_rules`` edges (AC14, A6); ``None`` for a mode with no edges."""
    if not mode.intended_rules:
        return None
    return min(
        (rule.evidence_rung for rule in mode.intended_rules),
        key=lambda rung: _RUNG_STRENGTH[rung],
    )


def specification_conflicts(
    modes: Optional[Iterable[ModeSpec]] = None,
) -> Tuple[str, ...]:
    """The conformance check behind AC8, defence in depth: one conflict per
    mode whose ``status`` field holds a value outside
    :data:`AUTHORED_STATUSES` (only reachable via ``object.__setattr__``
    forcing a value past ``__post_init__``, since construction itself
    already rejects it). Defaults to the shipped :data:`SPECIFICATION`
    (via :func:`iter_modes`); returns ``()`` for it."""
    if modes is None:
        modes = tuple(iter_modes())
    conflicts = []
    for mode in modes:
        if mode.status not in AUTHORED_STATUSES:
            conflicts.append(
                f"mode {mode.id}: 'status' field holds {mode.status!r}, which is not "
                f"a member of AUTHORED_STATUSES {AUTHORED_STATUSES} -- "
                f"'implemented'/'validated' must only ever be derived via "
                f"derive_status(), never hand-set past construction."
            )
    return tuple(conflicts)


# =========================================================================== #
# Rendering: specification_to_dict / render_markdown (AC19, AC20, AC23)
# =========================================================================== #


def specification_to_dict() -> dict:
    """A deterministic, JSON-ready dict for the shipped specification. Takes
    no argument. Returns a fresh dict tree on every call -- mutating the
    result never leaks into a later call."""
    modes = []
    for mode in iter_modes():
        modes.append(
            {
                "id": mode.id,
                "name": mode.name,
                "definition": mode.definition,
                "discriminator": mode.discriminator,
                "observability": mode.observability,
                "candidate_features": [
                    {"path": feature.path, "role": feature.role}
                    for feature in mode.candidate_features
                ],
                "intended_rules": [
                    {
                        "rule_id": rule.rule_id,
                        "detector": rule.detector,
                        "evidence_rung": rule.evidence_rung,
                    }
                    for rule in mode.intended_rules
                ],
                "corpus_cases": [
                    {
                        "case_id": case.case_id,
                        "corpus": case.corpus,
                        "expected_firing": list(case.expected_firing),
                        "reason": case.reason,
                        "agrees": case_agrees(case),
                    }
                    for case in mode.corpus_cases
                ],
                "severity": mode.severity,
                "status_authored": mode.status,
                "status_derived": derive_status(mode),
                "derived_rung": derive_mode_rung(mode),
                "provenance": mode.provenance,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "note": _NOTE,
        "modes": modes,
    }


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_markdown() -> str:
    """A deterministic Markdown rendering of the shipped specification --
    the review surface item 150 signs. Takes no argument. Lifecycle status
    is rendered as its word, never as one of the six AIDE status icons
    (AC23)."""
    payload = specification_to_dict()
    lines = [
        "# Failure-Mode Specification",
        "",
        _md_escape(payload["note"]),
        "",
        f"Schema version: {payload['schema_version']}.",
        "",
    ]
    for mode in payload["modes"]:
        lines.append(f"## Mode {mode['id']}: {mode['name']}")
        lines.append("")
        lines.append(f"- Definition: {_md_escape(mode['definition'])}")
        lines.append(f"- Discriminator: {_md_escape(mode['discriminator'])}")
        lines.append(f"- Observability: {mode['observability']}")
        lines.append(f"- Severity: {mode['severity']}")
        lines.append(f"- Provenance: {mode['provenance']}")
        lines.append(f"- Status, authored: {mode['status_authored']}")
        lines.append(f"- Status, derived (live): {mode['status_derived']}")
        rung = mode["derived_rung"] if mode["derived_rung"] is not None else "none"
        lines.append(f"- Derived rung (strongest edge, live): {rung}")
        lines.append("")
        lines.append("Candidate features:")
        lines.append("")
        for feature in mode["candidate_features"]:
            if feature["role"] == "stage18-metric-anchor":
                lines.append(
                    f"- Stage-18 metric anchor path (`{feature['role']}`): "
                    f"`{feature['path']}`"
                )
            else:
                lines.append(f"- `{feature['role']}` candidate path: `{feature['path']}`")
        lines.append("")
        lines.append("Intended rules:")
        lines.append("")
        for rule in mode["intended_rules"]:
            detector = rule["detector"] or "(none)"
            lines.append(
                f"- `{rule['rule_id']}` (detector: {detector}) -- evidence rung: "
                f"{rule['evidence_rung']}"
            )
        lines.append("")
        lines.append("Corpus cases:")
        lines.append("")
        for case in mode["corpus_cases"]:
            expected = ", ".join(case["expected_firing"]) if case["expected_firing"] else "(none)"
            lines.append(
                f"- `{case['case_id']}` ({case['corpus']}): expected firing = "
                f"[{expected}]; agrees with live measurement: {case['agrees']}. "
                f"{_md_escape(case['reason'])}"
            )
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


# =========================================================================== #
# __main__
# =========================================================================== #


def main(argv: Optional[Iterable[str]] = None) -> int:
    """``python -m segfacet.failure_modes [--json PATH] [--md PATH]``.
    Defaults to the two committed artifact paths under ``docs/aide/``.
    Writes both through ``Path.write_bytes`` -- never ``write_text`` -- so
    the byte stream is exactly what is serialised, with no platform newline
    translation (AC21)."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Regenerate the generated failure-mode specification rendering "
            "(item 144)."
        )
    )
    parser.add_argument("--json", type=Path, default=JSON_PATH)
    parser.add_argument("--md", type=Path, default=MD_PATH)
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = specification_to_dict()
    json_text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    md_text = render_markdown()

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_bytes(json_text.encode("utf-8"))
    args.md.write_bytes(md_text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
