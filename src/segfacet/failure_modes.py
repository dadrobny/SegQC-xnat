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
centroid-displacement value. The ninth mode and the first ``proposed`` entry
are item 146's.

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
                "item-143-corrected corpus (2026-09-03). The rule's rank "
                "cap admits only a single rank descent per pair "
                "(rank(v) == v - 1 under the TPTBox default), so this "
                "fixture is a degraded, single-descent instance -- it does "
                "not represent section 6.7's own two-descent example "
                "L1 -> T12 -> L2 -> L5, which needs real data to exercise, "
                "hence the needs-real-data rung despite this case's "
                "pipeline detection (item 145 A4)."
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
    )
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

    ``"validated"`` iff *mode* carries >=1 corpus case and every one
    :func:`case_agrees`; else ``"implemented"`` iff at least one registered
    rule declares ``mode.id`` (:func:`_registry_declares`); else the
    authored ``mode.status`` (``"proposed"`` or ``"specified"``) unchanged.
    The empty set never satisfies the "every case agrees" quantifier
    vacuously -- an empty ``corpus_cases`` cannot reach ``"validated"``.
    """
    if mode.corpus_cases and all(case_agrees(case) for case in mode.corpus_cases):
        return "validated"
    if _registry_declares(mode.id):
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
