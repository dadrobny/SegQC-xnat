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
rendering.** Item 144 shipped a minimal seed set of two entries (modes 3 and
8) to exercise both derivation paths end-to-end (item spec A4); item 145
entered the remaining six and re-authored those two, so :data:`SPECIFICATION`
now carries all **eight** of vision.md §6's hypothesised modes, every schema
field populated, each with the live-registry-declared edges, the
per-corpus-case measured firing set, and (mode 6) a freshly measured
centroid-displacement value. Item 146 then added the **ninth** mode and the
first ``proposed`` entry, so :data:`SPECIFICATION` now carries ten.

Adding the ninth mode (item 146, 2026-09-04)
--------------------------------------------
Mode 9 ("Implausible tissue under a label") is deliberately **not** one of
vision.md §6's numbered eight. It entered through this module's schema,
acquired its rules by their declarations moving from mode-less to
``modes=(9,)``, and derives ``"validated"`` from live state -- evidence for
§6's own claim that a mode can be added **without everything being rebuilt**:
neither the eight seed entries, the ``ModeSpec`` schema, the rule engine, nor
any rule's ``evaluate`` body was touched. What had to change, and only this:

* ``src/segfacet/failure_modes.py`` -- ``_MODE_9`` and ``_MODE_10`` authored
  and appended to the ``_build_specification`` tuple; :func:`measured_firing`
  gained a first-level dispatch on ``CorpusCaseExpectation.corpus``;
  :func:`specification_conflicts` gained the ``proposed``-drift check;
  :func:`render_markdown` gained ``- (none)`` for an empty section; and
  :func:`derive_status` gained a declaring-rule precondition on
  ``"validated"`` (the item-145 review finding, ``docs/aide/insights.md``,
  2026-09-03).
* ``src/segfacet/heuristics/intensity.py`` and
  ``src/segfacet/heuristics/intensity_reference_delta.py`` -- the
  ``mode_declaration`` **literal** only, from ``mode_less_reason=...`` to
  ``modes=(9,)`` with an ``evidence`` tuple naming
  ``tests/corpus/intensity/manifest.json``. No threshold, condition,
  severity or ``evaluate`` line changed; ``run_rules``' output on a fixed
  record is unchanged, because the declaration is metadata the engine never
  reads.
* ``src/segfacet/synth/regression.py`` -- ``loaded_intensity_case`` and
  ``intensity_pipeline_findings``, the intensity sibling of
  ``loaded_seg_image`` / ``pipeline_findings``. The second committed corpus
  had no public harness at all until this item.
* ``src/segfacet/synth/__init__.py`` -- both names re-exported, additively.
* ``src/segfacet/synth/intensity.py`` -- the manifest's per-case
  ``failure_mode`` / ``failure_mode_name`` / ``detection`` /
  ``expected_firing`` fields, written by the generator (never hand-edited)
  at an unchanged ``INTENSITY_MANIFEST_VERSION``, since the change is purely
  additive.
* ``src/segfacet/catalogue.py`` -- ``rule_declaration_conflicts``' known-mode
  set now comes from :data:`SPECIFICATION`'s keys rather than
  ``feature_docs.MODE_ANCHOR_PATHS``' (item 146 A7; item 147 completes the
  collapse). ``MODE_ANCHOR_PATHS`` itself is untouched and its key set stays
  exactly 1-8, which is why mode 9's candidate features carry
  ``role="hypothesised"`` and never ``"stage18-metric-anchor"``.

Mode 10 ("Collapsed or duplicated label set") is the catalogue's first
``proposed`` entry: no rules, no corpus cases, one hypothesised candidate
feature, and a status that derives ``"proposed"`` from that emptiness. It
exists so the conformance report shows a listed, unimplemented mode, and so
the rendering has to render one legibly. Its detector is explicitly item
146's non-goal; nothing here fabricates one.

Becoming the record (item 147, 2026-09-04)
------------------------------------------
Items 144-146 built the specification beside the five partial sources
queue-020 names; item 147 collapses those sources onto it, so this module
is now the single place an operational claim about a failure mode is
authored:

* ``ModeSpec`` gained two authored fields. ``short_name`` carries the
  paraphrase both committed corpus manifests hold in ``failure_mode_name``
  (``segfacet.synth.perturbation.FAILURE_MODE_NAMES`` is now
  :func:`failure_mode_names` derived over :data:`SPECIFICATION`, not a
  hand-typed literal); ``mechanism`` carries the evidence-rung mechanism
  sentence that ``segfacet.traceability.MODE_RUNGS`` used to author. Both
  default to ``""`` so a standalone ``ModeSpec(...)`` in a test keeps
  working; every shipped entry carries both, non-empty.
* ``traceability.MODE_RUNGS`` / ``ModeRung`` / ``RUNGS`` are retired.
  :data:`RUNG_LABELS` moved here verbatim, and the matrix's per-mode rung
  is :func:`derive_mode_rung` over the per-edge rungs item 145 authored.
* The ``vision.md`` §6 parse moved here as the public
  :func:`vision_seed_titles`. It is the **seed**, not the record: the one
  kept conformance check in that direction is that modes 1-8's ``name``
  fields still equal §6's list. No other module under ``src/segfacet/``
  reads ``vision.md``.
* The reserved ``"corpus"`` evidence tag is retired rather than hardened
  (``docs/aide/insights.md``, item 136, 2026-09-02, three located defects):
  it was an exact-element membership test over an unvalidated tuple. The
  claim it stood for is data now -- item 145's per-edge rungs -- and the
  seam it gated is replaced by :func:`specification_conflicts`' two new
  specification-side directions (an ``IntendedRule`` edge the named rule
  does not declare; a committed corpus case the specification does not
  carry, or whose manifest expectation disagrees with it).

Mode 7's rung rationale is settled here as one measured sentence
(:data:`SPECIFICATION`\\ ``[7].mechanism``), correcting the ``rank(v) ==
v - 1`` claim item 145 transcribed from ``MODE_RUNGS``: see that field.

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
``vision_seed_titles() -> Dict[int, str]``
    The vision.md §6 numbered titles, parsed live (item 147 AC4) -- this
    module is the only reader of that document under ``src/segfacet/``.
``failure_mode_names() -> Mapping[int, str]``
    ``{0: CLEAN_CONTROL_NAME}`` plus every mode's ``short_name``; the
    binding ``segfacet.synth.perturbation.FAILURE_MODE_NAMES`` resolves to.
``CLEAN_CONTROL_NAME`` / ``RUNG_LABELS``
    The key-0 clean-control name, and the human-readable rung labels moved
    here from ``segfacet.traceability`` (item 147).
``derive_status(mode) -> str`` / ``derive_mode_rung(mode) -> Optional[str]``
    Live derivations (AC9/AC10, AC14).
``measured_firing(case) -> Tuple[str, ...]`` / ``case_agrees(case) -> bool``
    Drive one ``CorpusCaseExpectation`` through the same public harness
    ``segfacet.synth.regression`` exposes (dispatching on the manifest case's
    ``detection`` field), and compare against its authored
    ``expected_firing``.
``specification_conflicts(modes=None) -> Tuple[str, ...]``
    The conformance check: a hand-set derived ``status`` past construction;
    ``proposed`` drift; an ``IntendedRule`` edge the named rule does not
    declare (or that no rule registers); a committed corpus case the
    specification does not carry, or whose manifest expectation disagrees
    with it. Defaults to the shipped :data:`SPECIFICATION`.
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
    "vision_seed_titles",
    "failure_mode_names",
    "CLEAN_CONTROL_NAME",
    "RUNG_LABELS",
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

#: Human-readable label per rung. Moved here verbatim from
#: ``segfacet.traceability`` by item 147 (A11), beside the vocabulary it
#: labels -- ``traceability`` kept a second, identical copy of both the
#: vocabulary (``RUNGS``) and these labels while the rungs themselves were
#: authored there.
RUNG_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "synthetic-demonstrable": "Demonstrated end-to-end on a synthetic corpus case",
        "needs-real-data": "Needs real data, or a corpus the fixtures cannot express",
        "structurally-unobservable": "Structurally unobservable in the supported input format",
    }
)

#: The name the two committed corpus manifests carry for the key-0 clean
#: control. Key 0 is **not** a failure mode and has no ``ModeSpec``; it stays
#: an explicit constant so :func:`failure_mode_names` can carry it without
#: the specification having to pretend a tenth-plus-one mode exists.
CLEAN_CONTROL_NAME = "clean control (no failure)"


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
    short_name: str = ""
    definition: str = ""
    discriminator: str = ""
    mechanism: str = ""
    observability: str = ""
    candidate_features: Tuple[CandidateFeature, ...] = ()
    intended_rules: Tuple[IntendedRule, ...] = ()
    corpus_cases: Tuple[CorpusCaseExpectation, ...] = ()
    severity: str = ""
    status: str = ""
    provenance: str = ""

    def __post_init__(self) -> None:
        self._require_valid_id()

        # `short_name` and `mechanism` are the two fields item 147 moved onto
        # this schema from the partial sources it retired
        # (``synth.perturbation.FAILURE_MODE_NAMES``' paraphrases and
        # ``traceability.MODE_RUNGS``' mechanism sentences). They default to
        # `""` at the dataclass level so every standalone ``ModeSpec(...)``
        # construction in the suite keeps working (item 147 A2), and the
        # "every shipped entry carries both, non-empty" invariant is asserted
        # over SPECIFICATION by the test suite rather than enforced here.
        # A non-str value is still rejected: it would reach the rendering.
        for optional_field_name in ("short_name", "mechanism"):
            optional_value = getattr(self, optional_field_name)
            if not isinstance(optional_value, str):
                raise ValueError(
                    f"ModeSpec {self.id}: '{optional_field_name}' must be a str "
                    f"(possibly empty), got {type(optional_value).__name__}."
                )

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
# The shipped eight (item 145): every vision.md section 6 mode entered.
#
# expected_firing, the detector tags and the mode-6 displacement are measured
# live on the item-143-corrected corpus and recorded literally here
# (transcribing a *computed* value would defeat AC1's no-heavy-import-at-
# module-level contract) -- see this item's Decisions log for the
# measurement transcript. The edge set/rung per mode is the live registry's
# declaration (AC5, AC6) as it stood on 2026-09-03; names are the vision.md
# section 6 parse (AC3), never hand-typed independently of it.
# =========================================================================== #

_MODE_1 = ModeSpec(
    id=1,
    name="Label not aligned with the anatomical vertebra it names",
    short_name="label not aligned with the vertebra it names",
    definition=(
        "A vertebra segment is present and carries the correct level's "
        "label, but its measured position -- the centroid's offset from the "
        "fitted spinal curve -- is displaced from where that vertebra "
        "actually sits, with the label touching no image border and its "
        "identity itself unquestioned."
    ),
    discriminator=(
        "Distinguishes from mode 4 by whether the label's identity is wrong "
        "(mode 4, an ordering/identity failure) or only its position along "
        "the spine is wrong while the identity stays correct (mode 1); "
        "distinguishes from mode 6 by whether a border-touching face "
        "explains the displacement (mode 6, a crop) or none does (mode 1)."
    ),
    mechanism=(
        "Item 120's held-out spline-offset measurement demonstrates label "
        "displacement end-to-end on the committed corpus case "
        "mode1_displace; under plain run_qc (no reference attached) it is "
        "caught solely by mislabel's Detector A via "
        "stage3.per_label_offsets[].offset_mm (measured: findings == "
        "['mislabel']). reference_delta additionally scores "
        "spline_offset_mm, but only once a reference is attached, which "
        "this corpus case's plain-pipeline detection is not."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="stage3.per_label_offsets[].offset_mm",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="mislabel",
            detector="Vertebra misaligned from spinal curve:",
            evidence_rung="synthetic-demonstrable",
        ),
        IntendedRule(
            rule_id="reference_delta",
            detector="",
            evidence_rung="needs-real-data",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode1_displace",
            corpus="geometric",
            expected_firing=("mislabel",),
            reason=(
                "pipeline-detected; mislabel (Detector A, position/"
                "alignment) is the sole rule that fires on this corpus "
                "case, measured live via "
                "segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03): label 22 (L3)'s "
                "centroid lies measurably off the fitted spinal curve while "
                "touching no image face, so reference_delta stays "
                "needs-real-data -- no committed corpus case designates it, "
                "only a cohort reference artifact can (A9/A1's analytic-only "
                "class)."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_2 = ModeSpec(
    id=2,
    name="Over-/under-segmentation — fused or fragmented vertebra segments",
    short_name="over-/under-segmentation (fused / fragmented)",
    definition=(
        "A label's physical volume, x/y/z extent, or fragmentation index "
        "departs from the plausible range for its level: fusion with a "
        "neighbouring vertebra reads over the volume/extent range and "
        "produces a fragmentation_index below the intact-body threshold "
        "(two comparably-sized components), while an under-segmented or "
        "partially-labelled vertebra reads under the range."
    ),
    discriminator=(
        "Distinguishes from mode 3 by whether the dominant body itself "
        "stays intact: mode 2's label splits into components of comparable "
        "size (fragmentation_index below threshold, largest_component_"
        "fraction well under 0.9), while mode 3's dominant body stays "
        "largely intact (largest_component_fraction >= 0.9) with only a "
        "small stray island splitting off."
    ),
    mechanism=(
        "The corpus case mode2_fragment demonstrates over-/"
        "under-segmentation end-to-end; under plain run_qc (no reference "
        "attached) it is caught solely by fragmentation's component-count "
        "checks (measured: findings == ['fragmentation']). bounds and "
        "reference_delta fire only once a reference is attached, and then "
        "fire identically on clean_control -- the documented "
        "uncalibrated-baseline noise (CLAUDE.md Gotchas, item 125) -- not "
        "evidence of mode-2-specific detection."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="per_label.{label}.components.fragmentation_index",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="fragmentation",
            detector="Fragmentation:",
            evidence_rung="synthetic-demonstrable",
        ),
        IntendedRule(
            rule_id="bounds",
            detector="",
            evidence_rung="needs-real-data",
        ),
        IntendedRule(
            rule_id="reference_delta",
            detector="",
            evidence_rung="needs-real-data",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode2_fragment",
            corpus="geometric",
            expected_firing=("fragmentation",),
            reason=(
                "pipeline-detected; fragmentation (Fragmentation: the "
                "label's fragmentation_index falls below threshold, two "
                "comparably-sized components) is the sole rule that fires "
                "on this corpus case, measured live via "
                "segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03). bounds and "
                "reference_delta both stay needs-real-data: no committed "
                "corpus case designates either for this mode, only "
                "hand-set physical ranges or a cohort reference artifact "
                "can (A1's analytic-only class)."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_3 = ModeSpec(
    id=3,
    name="Disconnected components / islands, especially tiny rogue segments",
    short_name="disconnected components / rogue islands",
    definition=(
        "A label's foreground voxels split into more than one connected "
        "component, with at least one stray component far smaller than the "
        "dominant body."
    ),
    discriminator=(
        "Distinguishes from mode 2 by whether the dominant body stays "
        "intact: mode 3 keeps its largest component holding "
        "largest_component_fraction >= 0.9 of the label's voxels, with a "
        "small stray island elsewhere, while mode 2's largest component "
        "holds a materially smaller share, reflecting genuine "
        "fragmentation rather than a rogue island."
    ),
    mechanism=(
        "The corpus case mode3_inject_islands demonstrates disconnected "
        "rogue-island segments end-to-end, detected by the fragmentation "
        "rule's stray-component checks."
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
            detector="Rogue island(s):",
            evidence_rung="synthetic-demonstrable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode3_inject_islands",
            corpus="geometric",
            expected_firing=("fragmentation",),
            reason=(
                "pipeline-detected; fragmentation (Rogue island(s): a small "
                "non-dominant component strictly below island_min_voxels) "
                "is the sole rule that fires on this corpus case, measured "
                "live via segfacet.synth.regression.pipeline_findings on "
                "the item-143-corrected corpus (2026-09-03)."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_4 = ModeSpec(
    id=4,
    name="Semantic mislabelling (wrong vertebra identification)",
    short_name="semantic mislabelling (wrong identification)",
    definition=(
        "A vertebra is segmented with the label of a different vertebra "
        "level: two adjacent labels are out of the anatomically expected "
        "order along the fitted spinal curve, even though each label's own "
        "geometry is otherwise plausible -- the labels' identities, not "
        "their positions, are wrong."
    ),
    discriminator=(
        "Distinguishes from mode 1 by whether the label's identity is "
        "wrong (mode 4, an ordering/identity failure between two adjacent "
        "labels) or only its position is wrong while the identity stays "
        "correct (mode 1)."
    ),
    mechanism=(
        "Item 132 closed the interpolating-spline-fit defect for semantic "
        "mislabelling, and the corpus case mode4_relabel_swap demonstrates "
        "a relabel-swap end-to-end, caught by mislabel's Detector B via "
        "stage3.monotonic_consistency.non_monotonic_pairs[] -- the field "
        "Detector B actually reads; MODE_ANCHOR_PATHS anchors this mode "
        "instead on the neighbouring is_monotonic field by design "
        "(feature_docs.py), not on the field the rule reads."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="stage3.monotonic_consistency.is_monotonic",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="mislabel",
            detector="Vertebra ordering inconsistent with label:",
            evidence_rung="synthetic-demonstrable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode4_relabel_swap",
            corpus="geometric",
            expected_firing=("mislabel",),
            reason=(
                "pipeline-detected; mislabel (Detector B, ordering/"
                "identity) is the sole rule that fires on this corpus "
                "case, measured live via "
                "segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03): labels 21 (L2) "
                "and 22 (L3) are out of expected order along the spline."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_5 = ModeSpec(
    id=5,
    name="Not all vertebrae in the image are segmented",
    short_name="not all vertebrae segmented (missing levels)",
    definition=(
        "One or more vertebrae expected to be present within the observed "
        "span of present levels carry no label at all -- the level is "
        "missing from the segmentation entirely, not merely misplaced or "
        "malformed."
    ),
    discriminator=(
        "Distinguishes from every other mode by being an absence rather "
        "than a defect: no per-label geometry exists at all for the "
        "missing level, whereas modes 1-4 and 6 all involve a mislocated, "
        "malformed or displaced *existing* label."
    ),
    mechanism=(
        "The corpus case mode5_remove_level demonstrates a missing "
        "vertebra end-to-end, caught by the coverage rule against "
        "relationships.missing_levels[] -- the field the rule actually "
        "reads; relationships.present_levels[] is read only by coverage's "
        "opt-in expected-levels span check, which ships disabled "
        "(expected_levels=[])."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="relationships.present_levels[]",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="coverage",
            detector="Missing interior level(s):",
            evidence_rung="synthetic-demonstrable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode5_remove_level",
            corpus="geometric",
            expected_firing=("coverage",),
            reason=(
                "pipeline-detected; coverage (Missing interior level(s): "
                "L3 absent within the observed present-level span) is the "
                "sole rule that fires on this corpus case, measured live "
                "via segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03)."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_6 = ModeSpec(
    id=6,
    name="Partial vertebra at the image border whose appearance changes",
    short_name="partial vertebra at the image border",
    definition=(
        "A vertebra at the edge of the imaging field of view is only "
        "partially captured: its label touches an image face, and the "
        "missing tissue displaces its measured centroid off the fitted "
        "spinal curve, changing both its geometry and its apparent "
        "position."
    ),
    discriminator=(
        "Distinguishes from mode 1 by a border-touching face: mode 6's "
        "clipped vertebra touches an image face, and that crop is what "
        "explains the centroid displacement, while mode 1's displaced "
        "vertebra touches no face at all -- the same misalignment "
        "detector legitimately co-fires on mode 6's case (co-detection is "
        "recorded, not suppressed), but the border-touch face is what "
        "identifies mode 6 rather than mode 1."
    ),
    mechanism=(
        "The corpus case mode6_crop_at_border demonstrates a "
        "border-cropped vertebra end-to-end -- the corpus operator crops "
        "the anterior face -- caught by the border rule reading "
        "per_label.{label}.geometry.touches_anterior."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="per_label.{label}.geometry.touches_left",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="border",
            detector="Partial vertebra clipped by FOV:",
            evidence_rung="synthetic-demonstrable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode6_crop_at_border",
            corpus="geometric",
            expected_firing=("border", "mislabel"),
            reason=(
                "pipeline-detected; measured live via "
                "segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03), this case fires "
                "two rules: border, because the cropped label 22 (L3) "
                "touches the anterior image face; and mislabel, because "
                "cropping the vertebra at the image border displaces its "
                "centroid 17.51 mm off the fitted spinal curve (spline) -- "
                "the legitimate co-detection this mode's discriminator "
                "names. mislabel is deliberately not one of mode 6's own "
                "intended_rules edges (AC5): only border is registered for "
                "mode 6."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_7 = ModeSpec(
    id=7,
    name="Non-continuous label sequence (e.g. L1 → T12 → L2 → L5)",
    short_name="non-continuous label sequence",
    definition=(
        "The sequence of labelled vertebra levels departs from anatomical "
        "order -- a level appears out of its expected cranio-caudal "
        "sequence relative to its neighbours in the labelled sequence, "
        "independent of any single label's own position or identity."
    ),
    discriminator=(
        "Distinguishes from mode 4 by scope: mode 4 is a pairwise ordering "
        "inconsistency between two adjacent labels along the fitted "
        "spinal curve, while mode 7 is a sequence-level discontinuity in "
        "the labelled level ordering itself, independent of any single "
        "label's spatial position."
    ),
    # Item 147 settles this sentence, correcting the claim item 145
    # transcribed from the retired traceability.MODE_RUNGS[7] and the
    # duplicate that stood in this mode's corpus-case reason
    # (docs/aide/insights.md, item 145, 2026-09-03). Every clause below is
    # measured, not asserted: the ranks from segfacet.labels (2026-09-04),
    # the "caps nothing" claim by driving SequenceRule on a one-descent and
    # a two-descent record (one finding each). This is the sentence's only
    # home in src/segfacet/.
    mechanism=(
        "segfacet.labels.CANONICAL_ORDER inserts the transitional label "
        "T13 at index 19, so a lumbar label's canonical rank equals its "
        "integer value (L1 = 20 → rank 20 ... L5 = 24 → rank 24) while a "
        "thoracic label's rank is its value minus one (T12 = 19 → rank "
        "18); section 6.7's own L1 → T12 → L2 → L5 example is therefore "
        "a SINGLE rank descent (ranks 20, 18, 21, 24), not the two "
        "descents §6 and the retired constant both called it. The sequence "
        "rule caps nothing: it raises exactly one finding whenever "
        "relationships.out_of_order_labels is non-empty, on a one-descent "
        "and on a two-descent record alike, as measured. The "
        "single-relabel cap belongs to the fixture generator "
        "synth/identity_ordering_alignment.py's SequenceBreakPerturbation, "
        "which relabels exactly one vertebra -- the tail, to T13 -- so the "
        "committed case mode7_sequence_break can express only a "
        "single-relabel break and a multi-relabel scramble needs real "
        "data, which is why this edge stays one rung below its case's "
        "pipeline detection."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="relationships.is_continuous",
            role="stage18-metric-anchor",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="sequence",
            detector="Non-continuous label sequence:",
            evidence_rung="needs-real-data",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode7_sequence_break",
            corpus="geometric",
            expected_firing=("sequence",),
            reason=(
                "pipeline-detected; sequence is the sole rule that fires "
                "on this corpus case, measured live via "
                "segfacet.synth.regression.pipeline_findings on the "
                "item-143-corrected corpus (2026-09-03). Why this edge's "
                "rung sits below that measured detection -- what the "
                "fixture generator can and cannot express -- is recorded "
                "once, in this mode's mechanism sentence (item 147); it is "
                "deliberately not repeated here."
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
    short_name="overlapping segments",
    definition=(
        "Two labels' foreground voxel sets intersect -- the same voxel is "
        "claimed by more than one label, a condition impossible in a valid "
        "single-channel integer label map."
    ),
    discriminator=(
        "Distinguishes from every other mode by requiring a second "
        "label's mask: it is unobservable from any single label's "
        "geometry alone, unlike modes 1-7, which are all detectable from "
        "one label's own geometry or the whole label map's per-label "
        "statistics."
    ),
    mechanism=(
        "A single-channel integer label map cannot assign two labels to "
        "one voxel, so overlaps[] populates only on a case deliberately "
        "corrupted to violate that invariant, which no real segmenter "
        "output can be; mode8_force_overlap therefore stays "
        "detection=\"reconstructed_record\" rather than pipeline-detected, "
        "while the overlap rule and the paths it reads remain correct and "
        "fully wired."
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
            detector="Overlapping segments:",
            evidence_rung="structurally-unobservable",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="mode8_force_overlap",
            corpus="geometric",
            expected_firing=("overlap",),
            reason=(
                "reconstructed-record-detected; overlap is the sole rule "
                "that fires on this corpus case, measured live via "
                "segfacet.synth.regression.reconstructed_findings on the "
                "item-143-corrected corpus (2026-09-03). A voxel in a "
                "single-channel integer label map holds exactly one "
                "label, so overlaps[] can only populate when the record "
                "is deliberately corrupted to violate that invariant -- "
                "which this case's reconstruction does."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)


# =========================================================================== #
# The ninth mode and the first `proposed` entry (item 146).
#
# Mode 9 is deliberately NOT one of vision.md section 6's numbered eight: it
# enters through the schema, acquires its rules by their declarations moving
# from mode-less to modes=(9,), and derives its status from live state --
# the exercise of section 6's own claim that a mode can be added without
# everything being rebuilt. Mode 10 is the catalogue's first `proposed`
# entry: listed, defined, and deliberately unimplemented.
#
# Mode 9's firing sets are measured through the item-146 harness
# segfacet.synth.regression.intensity_pipeline_findings over the committed
# intensity corpus (2026-09-04); see the item's Decisions log for the
# transcript.
# =========================================================================== #

_MODE_9 = ModeSpec(
    id=9,
    name="Implausible tissue under a label",
    short_name="Implausible tissue under a label",
    definition=(
        "On CT, the voxels a vertebra label claims do not carry "
        "bone-plausible Hounsfield-unit statistics: the label's median HU "
        "is implausibly low (soft tissue or air), implausibly high (metal "
        "or an implant), or its intensity spread is degenerate -- a "
        "near-zero standard deviation over a uniform region, which no real "
        "trabecular/cortical bone produces. The label map's geometry may be "
        "entirely well-formed; the failure is that the tissue underneath it "
        "is not the tissue the label names."
    ),
    discriminator=(
        "Distinguishes from modes 1-8 by requiring the paired intensity "
        "scan: every one of those eight is decidable from the label map "
        "alone, whereas mode 9 is invisible without the scan "
        "(observability = needs-paired-scan). Distinguishes from mode 1 in "
        "particular by what is wrong with an otherwise correctly-shaped, "
        "correctly-placed label -- mode 1's centroid is displaced from the "
        "fitted curve, while mode 9's label may sit exactly where it "
        "belongs and still cover the wrong tissue."
    ),
    mechanism=(
        "The committed intensity corpus demonstrates mode 9 end-to-end "
        "three times over: implausible_metal (label 22's median reads "
        "2999 HU, above the plausible bone band's ceiling), "
        "implausible_soft_tissue (40 HU, below its floor) and "
        "degenerate_uniform (a constant fill, zero spread) each drive the "
        "intensity rule through "
        "segfacet.synth.regression.intensity_pipeline_findings, which is "
        "why that edge sits at the strongest rung. "
        "intensity_reference_delta stays a rung below: the synthetic "
        "intensity corpus is built against no reference distribution and "
        "the harness attaches none, so nothing in the committed corpus "
        "can exercise it."
    ),
    observability="needs-paired-scan",
    candidate_features=(
        CandidateFeature(
            path="image_features.per_label[].median_hu",
            role="hypothesised",
        ),
        CandidateFeature(
            path="image_features.per_label[].std_hu",
            role="hypothesised",
        ),
        CandidateFeature(
            path="intensity_reference_delta.per_label[].robust_z",
            role="hypothesised",
        ),
    ),
    intended_rules=(
        IntendedRule(
            rule_id="intensity",
            detector=(
                "Implausible intensity (too low): / (too high): / "
                "(degenerate/uniform):"
            ),
            evidence_rung="synthetic-demonstrable",
        ),
        IntendedRule(
            rule_id="intensity_reference_delta",
            detector="",
            evidence_rung="needs-real-data",
        ),
    ),
    corpus_cases=(
        CorpusCaseExpectation(
            case_id="implausible_metal",
            corpus="intensity",
            expected_firing=("intensity",),
            reason=(
                "intensity-pipeline-detected; intensity is the sole rule "
                "that fires on this case, measured live via "
                "segfacet.synth.regression.intensity_pipeline_findings over "
                "tests/corpus/intensity/manifest.json (2026-09-04): label "
                "22 (L3)'s median reads 2999 HU, above the plausible bone "
                "band's 2000 HU ceiling. intensity_reference_delta cannot "
                "fire here because the synthetic intensity corpus is built "
                "against no reference distribution and the harness attaches "
                "none (item 146 A3), which is why its mode-9 edge stays at "
                "needs-real-data."
            ),
        ),
        CorpusCaseExpectation(
            case_id="implausible_soft_tissue",
            corpus="intensity",
            expected_firing=("intensity",),
            reason=(
                "intensity-pipeline-detected; intensity is the sole rule "
                "that fires on this case, measured live via "
                "segfacet.synth.regression.intensity_pipeline_findings over "
                "tests/corpus/intensity/manifest.json (2026-09-04): label "
                "22 (L3)'s median reads 40 HU, below the plausible bone "
                "band's 100 HU floor -- soft tissue under a vertebra label. "
                "intensity_reference_delta attaches no reference here "
                "(item 146 A3), so it stays needs-real-data."
            ),
        ),
        CorpusCaseExpectation(
            case_id="degenerate_uniform",
            corpus="intensity",
            expected_firing=("intensity",),
            reason=(
                "intensity-pipeline-detected; intensity is the sole rule "
                "that fires on this case, measured live via "
                "segfacet.synth.regression.intensity_pipeline_findings over "
                "tests/corpus/intensity/manifest.json (2026-09-04). It "
                "raises two findings, both from the same rule: the "
                "degenerate/uniform detector (std 0.00 HU, at or below the "
                "1.00 HU threshold) and, because the constant fill is 0 HU, "
                "the too-low detector as well -- so the firing SET is still "
                "{intensity}. intensity_reference_delta attaches no "
                "reference here (item 146 A3), so it stays needs-real-data."
            ),
        ),
    ),
    severity="flagged-for-review",
    status="specified",
    provenance="hypothesised",
)

_MODE_10 = ModeSpec(
    id=10,
    name="Collapsed or duplicated label set",
    short_name="collapsed or duplicated label set",
    definition=(
        "Two or more labels share an exact centroid -- the degenerate case "
        "a collapsed or duplicated label set produces. The Stage 3 spline "
        "fit cannot be computed over coincident centroids, so the record "
        "carries a stage3_unavailable reason instead of a stage3 block, "
        "every stage3-reading rule short-circuits on the missing block, and "
        "no finding of any kind is raised: the case passes silently "
        "(carried defect, item 129, 2026-08-31). The failure is the "
        "silence, not any single rule's verdict."
    ),
    discriminator=(
        "Distinguishes from mode 2 (fused or fragmented segments) by what "
        "the labels do rather than what the components do: mode 2's labels "
        "keep distinct centroids and its detectors fire, whereas mode 10's "
        "labels collapse onto one point and every stage3 detector goes "
        "quiet. Distinguishes from mode 8 (overlapping segments) by not "
        "requiring any shared voxel -- two disjoint labels can still share "
        "a centroid."
    ),
    mechanism=(
        "No rule exists for this mode yet, which is what `proposed` means: "
        "the failure is the silence, and silence is not something a "
        "detector can be pointed at without first deciding what the "
        "record should carry in place of the stage3 block. The candidate "
        "feature this mode names, stage3_unavailable.reason, is the one "
        "field a future detector would read -- it is populated today "
        "(item 129) and read by no rule, so the mode is listed, defined "
        "and deliberately unimplemented rather than hypothetical."
    ),
    observability="single-channel-observable",
    candidate_features=(
        CandidateFeature(
            path="stage3_unavailable.reason",
            role="hypothesised",
        ),
    ),
    intended_rules=(),
    corpus_cases=(),
    severity="flagged-for-review",
    status="proposed",
    provenance="hypothesised",
)


def _build_specification(modes: Iterable[ModeSpec]) -> Mapping[int, ModeSpec]:
    """Index *modes* by ``id`` into an immutable, ascending mapping,
    rejecting a duplicate ``id`` rather than letting the later entry
    silently replace the earlier one -- a dict comprehension would drop a
    hand-authored mode with a typo'd id with no diagnostic at all (items
    145/146 author six more entries by hand)."""
    by_id: Dict[int, ModeSpec] = {}
    for mode in modes:
        if mode.id in by_id:
            raise ValueError(
                f"SPECIFICATION: duplicate mode id {mode.id} "
                f"({by_id[mode.id].name!r} and {mode.name!r}) -- every mode id must "
                f"be unique."
            )
        by_id[mode.id] = mode
    return MappingProxyType({mode_id: by_id[mode_id] for mode_id in sorted(by_id)})


SPECIFICATION: Mapping[int, ModeSpec] = _build_specification(
    (
        _MODE_1,
        _MODE_2,
        _MODE_3,
        _MODE_4,
        _MODE_5,
        _MODE_6,
        _MODE_7,
        _MODE_8,
        _MODE_9,
        _MODE_10,
    )
)


def iter_modes() -> Iterator[ModeSpec]:
    """Yield the seed modes in ascending ``id`` order. Takes no argument."""
    for mode_id in sorted(SPECIFICATION):
        yield SPECIFICATION[mode_id]


# =========================================================================== #
# The vision.md §6 parse (item 147 AC4) -- one home, here.
# =========================================================================== #


def vision_seed_titles() -> Dict[int, str]:
    """The numbered titles of ``docs/aide/vision.md`` §6, parsed live.

    This is the **seed**, not the record. §6 names the eight modes this
    catalogue started from; :data:`SPECIFICATION` is what the catalogue
    *is* today, and it has grown past §6's list (mode 9 entered through
    the lifecycle, mode 10 is the first ``proposed`` entry). The one
    conformance claim in this direction is that the eight seed entries'
    ``name`` fields still equal §6's list -- nothing else reads this, and
    no consumer should treat a missing key as a missing mode.

    Item 147 moved this function here from ``segfacet.traceability``
    (where it was private) so that exactly one module under
    ``src/segfacet/`` reads ``vision.md`` at all.
    """
    import re

    text = (_REPO_ROOT / "docs" / "aide" / "vision.md").read_text(encoding="utf-8")
    section_match = re.search(
        r"^## 6\. Segmentation Failure Modes[^\n]*\n(.*?)(?=^## \d|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if section_match is None:
        raise RuntimeError(
            "segfacet.failure_modes: docs/aide/vision.md carries no "
            "'## 6. Segmentation Failure Modes' section to transcribe titles from."
        )
    section_text = section_match.group(1)
    items = re.findall(r"^\d+\.\s+(.+)$", section_text, flags=re.MULTILINE)
    titles: Dict[int, str] = {}
    for index, raw in enumerate(items, start=1):
        title = raw.strip()
        if title.endswith("."):
            title = title[:-1]
        title = re.sub(r"\s+", " ", title).strip()
        titles[index] = title
    return titles


# =========================================================================== #
# The derived failure-mode name map (item 147 AC21) -- the binding
# `segfacet.synth.perturbation.FAILURE_MODE_NAMES` now resolves to.
# =========================================================================== #


def failure_mode_names() -> Mapping[int, str]:
    """``{0: CLEAN_CONTROL_NAME}`` plus every mode's ``short_name``, keyed by
    mode id and ascending.

    The values are the **paraphrases** both committed corpus manifests carry
    in ``failure_mode_name``, not the vision §6 titles ``ModeSpec.name``
    holds -- which is why they are an authored field rather than derived
    from ``name``: re-pointing the manifests at ``name`` would be a corpus
    value change. Key 0 is explicit because the clean control is not a
    failure mode and has no ``ModeSpec`` entry.

    Returns an immutable mapping; a fresh proxy over a fresh dict on every
    call, so a caller mutating nothing can still not leak into a later one.
    """
    names: Dict[int, str] = {0: CLEAN_CONTROL_NAME}
    for mode_id in sorted(SPECIFICATION):
        names[mode_id] = SPECIFICATION[mode_id].short_name
    return MappingProxyType(names)


# =========================================================================== #
# Derivation: measured_firing / case_agrees / derive_status / derive_mode_rung
# (AC9, AC10, AC14) -- deferred heavy imports (A3).
# =========================================================================== #


def measured_firing(case: CorpusCaseExpectation) -> Tuple[str, ...]:
    """The full set of ``rule_id``s among the findings *case*'s manifest
    entry's detection path produces, measured live through
    :mod:`segfacet.synth.regression`.

    ``corpus`` is the **first** dispatch key (item 146): it selects which
    committed manifest the ``case_id`` is resolved against, and the
    vocabulary is closed and exact -- any value other than ``"geometric"``
    or ``"intensity"`` raises ``ValueError`` naming both the case and the
    unrecognised value, never a silent empty set. Within each corpus the
    manifest case's own ``detection`` field is the second dispatch key:

    * ``"geometric"`` -- ``tests/corpus/manifest.json``;
      ``pipeline_findings`` for ``detection == "pipeline"``,
      ``reconstructed_findings`` for ``detection == "reconstructed_record"``.
    * ``"intensity"`` -- ``tests/corpus/intensity/manifest.json``;
      ``intensity_pipeline_findings`` for
      ``detection == "intensity_pipeline"`` (item 146's public harness, the
      one intensity composition in production).
    """
    if case.corpus == "geometric":
        return _measured_firing_geometric(case)
    if case.corpus == "intensity":
        return _measured_firing_intensity(case)
    raise ValueError(
        f"measured_firing: unrecognised corpus {case.corpus!r} for case_id="
        f"{case.case_id!r}; the dispatch vocabulary is exactly "
        f"('geometric', 'intensity')."
    )


def _measured_firing_geometric(case: CorpusCaseExpectation) -> Tuple[str, ...]:
    """The ``corpus == "geometric"`` branch of :func:`measured_firing` --
    today's body verbatim, over ``tests/corpus/manifest.json``."""
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


def _measured_firing_intensity(case: CorpusCaseExpectation) -> Tuple[str, ...]:
    """The ``corpus == "intensity"`` branch of :func:`measured_firing`, over
    the committed ``tests/corpus/intensity/manifest.json``.

    ``segfacet.synth.intensity.load_intensity_manifest`` is reached through
    the module object rather than imported by name, so a test can substitute
    a manifest whose ``detection`` is unrecognised and observe the raise."""
    from segfacet.synth import intensity as intensity_module
    from segfacet.synth.regression import intensity_pipeline_findings

    manifest = intensity_module.load_intensity_manifest()
    manifest_case = None
    for candidate in manifest.get("cases", []):
        if candidate.get("case_id") == case.case_id:
            manifest_case = candidate
            break
    if manifest_case is None:
        raise ValueError(
            f"measured_firing: case_id {case.case_id!r} not found in the committed "
            f"intensity corpus manifest tests/corpus/intensity/manifest.json "
            f"(corpus={case.corpus!r})."
        )

    detection = manifest_case.get("detection")
    if detection != "intensity_pipeline":
        raise ValueError(
            f"measured_firing: unrecognised detection {detection!r} for "
            f"case_id={case.case_id!r} in the intensity corpus; the only "
            f"recognised value is 'intensity_pipeline'."
        )
    findings = intensity_pipeline_findings(manifest_case)
    return tuple(sorted({finding.rule_id for finding in findings}))


def case_agrees(case: CorpusCaseExpectation) -> bool:
    """``True`` iff *case*'s live :func:`measured_firing` set equals its
    authored ``expected_firing`` set.

    ``expected_firing`` must be a tuple. A bare ``str`` reaching this
    function -- a :class:`CorpusCaseExpectation` built standalone, outside
    the :class:`ModeSpec` tree whose ``__post_init__`` enforces AC7 -- would
    otherwise be compared character-wise (``set("border")``) and silently
    return ``False``, so it is rejected here too."""
    expected = case.expected_firing
    if not isinstance(expected, tuple):
        raise ValueError(
            f"case_agrees: corpus case {case.case_id!r}'s 'expected_firing' must be "
            f"a tuple, got {type(expected).__name__} -- a bare str or list would be "
            f"compared element-wise against the measured firing set."
        )
    return set(measured_firing(case)) == set(expected)


def _registry_declares(mode_id: int) -> bool:
    """``True`` iff at least one **registered** rule's
    ``RuleModeDeclaration`` lists *mode_id* among its ``modes``.

    This is vision.md §6's lifecycle definition verbatim ("``implemented``
    -- at least one registered rule declares the mode"), so a declaration
    spanning several modes (the real ``heuristics.fragmentation`` declares
    ``modes=(2, 3)``) counts for **every** mode it lists, not only for a
    mode it declares alone.

    Item 145 A1 authorised the same containment correction as a fallback;
    the item-144 review (commit 51dff83) had already landed it here.
    """
    from segfacet.heuristics.rule import iter_rule_declarations

    for _rule_id, declaration in iter_rule_declarations():
        if declaration is not None and mode_id in declaration.modes:
            return True
    return False


def derive_status(mode: ModeSpec) -> str:
    """The live-derived lifecycle status for *mode* (AC9, AC10).

    ``"validated"`` iff at least one **registered** rule declares
    ``mode.id`` **and** *mode* carries >=1 corpus case, every one of which
    :func:`case_agrees`; else ``"implemented"`` iff a registered rule
    declares ``mode.id`` (:func:`_registry_declares`); else the authored
    ``mode.status`` (``"proposed"`` or ``"specified"``) unchanged.
    The empty set never satisfies the "every case agrees" quantifier
    vacuously -- an empty ``corpus_cases`` cannot reach ``"validated"``.

    The declaring-rule precondition on ``"validated"`` is item 146's
    correction of an item-145 review finding (``docs/aide/insights.md``,
    item 145, 2026-09-03): the layering used to test the corpus-agreement
    clause first, so a mode with agreeing corpus cases and **no rule
    declaring it anywhere** derived ``"validated"`` without ever passing
    through ``"implemented"``. vision.md section 6's ladder is cumulative --
    validated implies implemented -- so the rung below is now a
    precondition, not merely the fallback. No shipped mode moves: all ten
    entries that reach the corpus-agreement clause are declared.
    """
    declared = _registry_declares(mode.id)
    if (
        declared
        and mode.corpus_cases
        and all(case_agrees(case) for case in mode.corpus_cases)
    ):
        return "validated"
    if declared:
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
    (via :func:`iter_modes`); returns ``()`` for it.

    Since item 146 it also reports **``proposed`` drift**: a mode authored
    ``"proposed"`` -- listed, defined, deliberately unimplemented -- whose
    :func:`derive_status` no longer returns ``"proposed"``, because a rule
    has acquired it or a corpus case now demonstrates it. That is not an
    error in the tree; it is the signal that the entry has outgrown its
    authored status and wants re-authoring as ``"specified"``.

    This check is deliberately **not** generalised to authored-vs-derived
    equality across the board: ``"specified"`` is precisely the status that
    is expected to derive further (every one of modes 1-9 is authored
    ``"specified"`` and derives ``"implemented"`` or ``"validated"``), so a
    blanket comparison would report the whole specification.
    """
    if modes is None:
        modes = tuple(iter_modes())
    modes = tuple(modes)
    conflicts = []
    for mode in modes:
        if mode.status not in AUTHORED_STATUSES:
            conflicts.append(
                f"mode {mode.id}: 'status' field holds {mode.status!r}, which is not "
                f"a member of AUTHORED_STATUSES {AUTHORED_STATUSES} -- "
                f"'implemented'/'validated' must only ever be derived via "
                f"derive_status(), never hand-set past construction."
            )
            continue
        if mode.status == "proposed":
            derived = derive_status(mode)
            if derived != "proposed":
                conflicts.append(
                    f"mode {mode.id}: authored status 'proposed' but derive_status() "
                    f"now returns {derived!r} -- a proposed (listed, unimplemented) "
                    f"entry has acquired a declaring rule or a demonstrating corpus "
                    f"case, and wants re-authoring as 'specified'."
                )

    conflicts.extend(_intended_rule_conflicts(modes))
    conflicts.extend(_corpus_case_conflicts(modes))
    return tuple(conflicts)


def _intended_rule_conflicts(modes: Tuple[ModeSpec, ...]) -> Tuple[str, ...]:
    """AC13: every ``IntendedRule`` edge must be an edge the named rule
    itself declares -- the specification -> declaration direction.

    Two shapes are reported, distinguished in the message: the named
    ``rule_id`` registers no rule at all, and the named rule registers but
    its ``RuleModeDeclaration`` does not list this mode. Together with
    ``catalogue.rule_declaration_conflicts()``'s opposite direction (a
    declared mode outside :data:`SPECIFICATION`), this replaces the
    ``"corpus"``-tagged declaration -> corpus check item 147 retired.
    """
    from segfacet.heuristics.rule import iter_rule_declarations

    declarations = dict(iter_rule_declarations())
    conflicts = []
    for mode in modes:
        for edge in mode.intended_rules:
            if edge.rule_id not in declarations:
                conflicts.append(
                    f"mode {mode.id}: intended rule {edge.rule_id!r} names a rule_id "
                    f"that no rule registers (registered: "
                    f"{sorted(declarations)!r})."
                )
                continue
            declaration = declarations[edge.rule_id]
            declared = set(declaration.modes) if declaration is not None else set()
            if mode.id not in declared:
                conflicts.append(
                    f"mode {mode.id}: intended rule {edge.rule_id!r} is registered but "
                    f"its RuleModeDeclaration does not declare mode {mode.id} "
                    f"(declared modes: {sorted(declared)!r})."
                )
    return tuple(conflicts)


def _corpus_case_conflicts(modes: Tuple[ModeSpec, ...]) -> Tuple[str, ...]:
    """AC14/AC15: every committed corpus case, in both manifests, must be
    carried by the mode its manifest entry names, and its manifest
    expectation must agree with the specification's ``expected_firing``.

    The two manifests express expectation differently (item 147 A9), and the
    relation applied is named in the message:

    * ``tests/corpus/manifest.json`` carries ``expected_rule_ids``, the
      narrow set expected *among* the fired findings -- compared by
      **subset**;
    * ``tests/corpus/intensity/manifest.json`` carries ``expected_firing``,
      the full set -- compared by **equality**.

    Cases whose ``failure_mode`` is 0 are the clean controls: not a failure
    mode, no ``ModeSpec`` entry, skipped. Manifests are read through the
    module objects (deferred imports, house style) so a test can substitute
    one.
    """
    from segfacet.synth import corpus as corpus_module
    from segfacet.synth import intensity as intensity_module

    by_id = {mode.id: mode for mode in modes}
    conflicts = []

    for corpus_name, cases, expectation_key, relation in (
        (
            "tests/corpus/manifest.json",
            corpus_module.load_manifest().get("cases", []),
            "expected_rule_ids",
            "subset",
        ),
        (
            "tests/corpus/intensity/manifest.json",
            intensity_module.load_intensity_manifest().get("cases", []),
            "expected_firing",
            "equality",
        ),
    ):
        for case in cases:
            mode_id = case.get("failure_mode")
            case_id = case.get("case_id")
            if mode_id == 0:
                continue
            mode = by_id.get(mode_id)
            if mode is None:
                # Out of scope for *this* call, not a conflict. `modes` may
                # be any subset of the specification -- item 144's
                # adversarial probes pass a single hand-built ModeSpec --
                # and a manifest case belonging to a mode the caller did not
                # pass says nothing about the modes it did. Reporting them
                # would bury the one conflict such a probe is asking about.
                continue
            expectation = None
            for candidate in mode.corpus_cases:
                if candidate.case_id == case_id:
                    expectation = candidate
                    break
            if expectation is None:
                conflicts.append(
                    f"corpus case {case_id!r} ({corpus_name}) names failure_mode "
                    f"{mode_id}, but mode {mode_id}'s corpus_cases do not carry that "
                    f"case_id (carried: "
                    f"{sorted(c.case_id for c in mode.corpus_cases)!r})."
                )
                continue
            manifest_set = set(case.get(expectation_key) or ())
            specified_set = set(expectation.expected_firing)
            disagrees = (
                not manifest_set <= specified_set
                if relation == "subset"
                else manifest_set != specified_set
            )
            if disagrees:
                conflicts.append(
                    f"corpus case {case_id!r} ({corpus_name}, mode {mode_id}): the "
                    f"manifest's {expectation_key} {sorted(manifest_set)!r} disagrees "
                    f"with the specification's expected_firing "
                    f"{sorted(specified_set)!r} under the {relation} relation this "
                    f"corpus is compared by."
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
                "short_name": mode.short_name,
                "definition": mode.definition,
                "discriminator": mode.discriminator,
                "mechanism": mode.mechanism,
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
    (AC23).

    An empty ``Candidate features:`` / ``Intended rules:`` / ``Corpus
    cases:`` section renders one ``- (none)`` bullet rather than nothing at
    all (item 146): the catalogue's first ``proposed`` entry has two empty
    sections by design, and a bare heading followed by the next heading
    reads to a reviewer as a hole in the document rather than as a
    deliberate absence."""
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
        lines.append(f"- Short name (corpus manifests): {mode['short_name'] or '(none)'}")
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
        if not mode["candidate_features"]:
            lines.append("- (none)")
        for feature in mode["candidate_features"]:
            if feature["role"] == "stage18-metric-anchor":
                lines.append(
                    f"- Stage-18 metric anchor path (`{feature['role']}`): "
                    f"`{feature['path']}`"
                )
            else:
                lines.append(f"- `{feature['role']}` candidate path: `{feature['path']}`")
        lines.append("")
        # Rendered *after* the candidate-feature list, deliberately: a
        # mechanism sentence names the paths it reasons about, and the first
        # place a reader (or a test scanning for the first occurrence of an
        # anchor path) meets one must be the bullet that labels it a
        # Stage-18 metric anchor, not a sentence that merely mentions it.
        lines.append(f"Mechanism: {_md_escape(mode['mechanism']) or '(none)'}")
        lines.append("")
        lines.append("Intended rules:")
        lines.append("")
        if not mode["intended_rules"]:
            lines.append("- (none)")
        for rule in mode["intended_rules"]:
            detector = rule["detector"] or "(none)"
            lines.append(
                f"- `{rule['rule_id']}` (detector: {detector}) -- evidence rung: "
                f"{rule['evidence_rung']}"
            )
        lines.append("")
        lines.append("Corpus cases:")
        lines.append("")
        if not mode["corpus_cases"]:
            lines.append("- (none)")
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
