"""Evaluation cohort model & harness driver (item 053).

This is the §8 **harness**: it ties the three already-merged comparison
primitives -- level-1 verdict-outcome classification (item 052), level-2
DICE-vs-GT overlap (item 050), and level-3 feature-set match (item 051) --
together with the real pipeline (:func:`segqc.pipeline.run_qc`, item 035)
into one **per-case evaluation record**, and a thin cohort wrapper over many
such records.

A :class:`EvaluationCase` names a ground-truth (GT) segmentation, an optional
candidate segmentation (a segmenter output to score against GT), and a
ground-truth expectation mapping (the ``Expectation.to_dict()`` /
``tests/corpus`` manifest-case shape item 052 consumes). Driving a case with
:func:`evaluate_case` produces a :class:`CaseEvaluation`: the *subject under
QC* -- the candidate when present, otherwise the GT itself -- is run through
the plain pipeline and classified against the expectation (always populated);
when a candidate is present, the candidate is additionally scored against the
GT for DICE overlap and feature-set divergence.

:func:`evaluate_cohort` drives many cases, in order, into a
:class:`CohortEvaluation`, rejecting duplicate ``case_id``s so downstream
item 054 can key records by id.

This module does no metric interpretation or cross-case aggregation (item
054), no threshold calibration (055), no report rendering (056), and no CLI
entry point (057); it produces stable per-case records only. It does not
re-implement any comparison maths -- it calls the merged primitives
(050/051/052) and the merged pipeline (``run_qc``, item 035) unchanged, and
has no dependency on the Stage-5 test-only reconstruction machinery
(``segqc.synth.regression``): it runs the plain pipeline, exactly as an
external cohort would.

Public API
----------
``EvaluationCase``
    Frozen dataclass: the per-case input spec (``case_id``, ``gt``,
    ``candidate``, ``expected``, ``spacing``, ``metadata``).
``CaseEvaluation``
    Frozen dataclass: the per-case output record (``outcome``, ``overlap``,
    ``feature_match``, ``candidate_present``, ``subject``, ``metadata``), with
    a JSON-serialisable ``to_dict()``.
``CohortEvaluation``
    Frozen dataclass wrapping a tuple of :class:`CaseEvaluation` records, with
    ``n_cases`` and a JSON-serialisable ``to_dict()``.
``evaluate_case(case, config, *, positive_severity=Severity.FLAG) ->
CaseEvaluation``
    Drive one case through the pipeline and the three comparison primitives.
``evaluate_cohort(cases, config, *, positive_severity=Severity.FLAG) ->
CohortEvaluation``
    Drive many cases, in order, into a cohort.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence, Tuple, Union

from segqc.eval.outcome import CaseOutcome, Outcome
from segqc.eval.overlap import OverlapResult
from segqc.eval.feature_match import FeatureMatchResult
from segqc.io import SegQCInputError
from segqc.verdict import Severity

if TYPE_CHECKING:
    import nibabel as nib
    import numpy as np

    from segqc.config import HeuristicConfig

__all__ = [
    "EvaluationCase",
    "CaseEvaluation",
    "CohortEvaluation",
    "evaluate_case",
    "evaluate_cohort",
]

SegSource = Union["nib.Nifti1Image", "np.ndarray", os.PathLike, str]

_DEFAULT_SPACING: Tuple[float, float, float] = (1.0, 1.0, 1.0)


# --------------------------------------------------------------------------- #
# EvaluationCase
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvaluationCase:
    """The per-case *input* spec fed to :func:`evaluate_case`.

    Attributes
    ----------
    case_id:
        A unique (within a cohort) identifier for this case.
    gt:
        The ground-truth segmentation source: a ``nibabel.Nifti1Image``, a
        NumPy ``ndarray`` (wrapped with a diagonal affine derived from
        ``spacing``), or a path-like to a single seg NIfTI on disk.
    candidate:
        An optional candidate segmentation source (same accepted forms as
        ``gt``) -- a segmenter output to score against ``gt``. ``None`` means
        "no candidate": the GT itself is the subject under QC.
    expected:
        The ground-truth expectation mapping, in the
        ``Expectation.to_dict()`` / ``tests/corpus`` manifest-case shape
        (item 052). Only ``expected_verdict`` is required.
    spacing:
        Optional ``(sx, sy, sz)`` voxel spacing in mm, used only when a
        source is given as a bare ``ndarray`` (default isotropic
        ``(1.0, 1.0, 1.0)``).
    metadata:
        Optional free-form mapping carried through to the output record.
    """

    case_id: str
    gt: SegSource
    expected: Mapping[str, Any]
    candidate: Optional[SegSource] = None
    spacing: Optional[Tuple[float, float, float]] = None
    metadata: Optional[Mapping[str, Any]] = None


# --------------------------------------------------------------------------- #
# Seg-source resolution
# --------------------------------------------------------------------------- #


def _resolve_seg(source: SegSource, spacing: Optional[Tuple[float, float, float]]) -> "nib.Nifti1Image":
    """Resolve *source* to a ``nibabel.Nifti1Image``, never mutating it.

    Parameters
    ----------
    source:
        A ``Nifti1Image``, an ``ndarray``, or a path-like.
    spacing:
        ``(sx, sy, sz)`` used only to build a diagonal affine for a bare
        ``ndarray`` source; defaults to isotropic ``(1.0, 1.0, 1.0)``.

    Returns
    -------
    nibabel.Nifti1Image
    """
    import nibabel as nib
    import numpy as np

    if isinstance(source, nib.Nifti1Image):
        return source

    if isinstance(source, np.ndarray):
        sx, sy, sz = (float(s) for s in (spacing or _DEFAULT_SPACING))
        affine = np.diag([sx, sy, sz, 1.0]).astype(np.float64)
        data = np.asanyarray(source)
        try:
            return nib.Nifti1Image(data, affine, dtype=source.dtype)
        except nib.spatialimages.HeaderDataError:
            # A degenerate affine (e.g. a zero spacing component) is
            # singular and cannot be decomposed into a qform rotation --
            # nibabel raises trying to derive one during construction.
            # ``spacing`` carries no documented non-zero restriction, so
            # degrade gracefully instead: build the image without an
            # implicit qform, set the affine directly via sform, and record
            # the exact requested spacing on the header so downstream
            # ``header.get_zooms()`` reads (e.g. for physical-volume
            # calculations) still see the degenerate component.
            img = nib.Nifti1Image(data, None, dtype=source.dtype)
            img.set_sform(affine, code=1)
            img.set_qform(None, code=0)
            img.header.set_zooms((sx, sy, sz))
            return img

    # Path-like: load a single seg NIfTI, integer labels preserved.
    return nib.load(os.fspath(source))


# --------------------------------------------------------------------------- #
# CaseEvaluation
# --------------------------------------------------------------------------- #


def _tuples_to_lists(obj: Any) -> Any:
    """Recursively coerce any ``tuple`` in *obj* to a ``list``.

    ``dataclasses.asdict`` preserves tuple-typed fields (e.g.
    ``OverlapResult.per_label``) as Python tuples. ``json.dumps`` encodes a
    tuple identically to a list, but ``json.loads`` always comes back as a
    list -- so a pre-dump dict containing tuples never compares equal to its
    own post-round-trip counterpart. Applying this pass makes the dict
    already "plain JSON" shaped before any dump/load round trip.
    """
    if isinstance(obj, tuple):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, list):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _tuples_to_lists(v) for k, v in obj.items()}
    return obj


def _asdict_enum_safe(obj: Any) -> Any:
    """``dataclasses.asdict``-like conversion that reduces ``Outcome`` to ``.value``.

    All tuple-typed fields (nested arbitrarily deep) are also coerced to
    lists so the result is already in plain-JSON shape -- see
    :func:`_tuples_to_lists`.
    """
    if obj is None:
        return None
    return _tuples_to_lists(
        dataclasses.asdict(
            obj,
            dict_factory=lambda pairs: {
                k: (v.value if isinstance(v, Outcome) else v) for k, v in pairs
            },
        )
    )


@dataclass(frozen=True)
class CaseEvaluation:
    """The per-case *output* record produced by :func:`evaluate_case`.

    Attributes
    ----------
    case_id:
        The case's identifier, carried through from :class:`EvaluationCase`.
    outcome:
        The level-1 verdict-outcome classification (item 052). Always
        populated -- computed against the subject under QC (see ``subject``).
    overlap:
        The level-2 DICE/Jaccard overlap of the candidate vs GT (item 050).
        ``None`` when no candidate was supplied.
    feature_match:
        The level-3 feature-set divergence of the candidate vs GT (item 051).
        ``None`` when no candidate was supplied.
    candidate_present:
        Whether a candidate was supplied for this case.
    subject:
        Which side was run through the pipeline as the subject under QC:
        ``"candidate"`` when a candidate was supplied, else ``"gt"``.
    metadata:
        Carried through from :class:`EvaluationCase`, unchanged.
    """

    case_id: str
    outcome: CaseOutcome
    overlap: Optional[OverlapResult]
    feature_match: Optional[FeatureMatchResult]
    candidate_present: bool
    subject: str
    metadata: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable nested dict for this record.

        The ``Outcome`` enum is reduced to its plain string ``.value``; the
        primitive dataclasses (``CaseOutcome``, ``OverlapResult``,
        ``FeatureMatchResult``) are reduced to nested plain dicts.
        """
        return {
            "case_id": self.case_id,
            "outcome": _asdict_enum_safe(self.outcome),
            "overlap": _asdict_enum_safe(self.overlap),
            "feature_match": _asdict_enum_safe(self.feature_match),
            "candidate_present": self.candidate_present,
            "subject": self.subject,
            "metadata": dict(self.metadata) if self.metadata is not None else None,
        }


# --------------------------------------------------------------------------- #
# CohortEvaluation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CohortEvaluation:
    """A collection of :class:`CaseEvaluation` records, in input order.

    Attributes
    ----------
    cases:
        One :class:`CaseEvaluation` per input :class:`EvaluationCase`, in the
        same order.
    """

    cases: Tuple[CaseEvaluation, ...]

    @property
    def n_cases(self) -> int:
        """Return the number of records in this cohort."""
        return len(self.cases)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict: ``{"cases": [record.to_dict(), ...]}``."""
        return {"cases": [case.to_dict() for case in self.cases]}


# --------------------------------------------------------------------------- #
# evaluate_case
# --------------------------------------------------------------------------- #


def evaluate_case(
    case: EvaluationCase,
    config: "HeuristicConfig",
    *,
    positive_severity: Severity = Severity.FLAG,
) -> CaseEvaluation:
    """Drive one :class:`EvaluationCase` through the pipeline and comparisons.

    The subject under QC is the candidate when present, otherwise the GT.
    ``run_qc`` is always called on the subject and the result is classified
    via ``classify_outcome`` (item 052) against ``case.expected`` -- this is
    always populated. When a candidate is present, it is additionally scored
    against the GT for DICE overlap (item 050, using the candidate's already
    -computed features block re-used for feature-set divergence, item 051);
    when absent, both stay ``None`` and ``candidate_present`` is ``False`` --
    no error is raised for a missing candidate.

    Parameters
    ----------
    case:
        The case to evaluate. Not mutated.
    config:
        A :class:`~segqc.config.HeuristicConfig`, threaded through to
        ``run_qc``/``extract_feature_record``. Not mutated.
    positive_severity:
        Threshold severity passed through to ``classify_outcome`` (item 052).

    Returns
    -------
    CaseEvaluation

    Raises
    ------
    segqc.io.SegQCInputError
        Propagated unmodified from ``compute_overlap`` (shape mismatch) or
        ``classify_outcome`` (malformed ``expected`` mapping).
    """
    from segqc.eval.feature_match import compute_feature_match
    from segqc.eval.outcome import classify_outcome
    from segqc.eval.overlap import compute_overlap
    from segqc.pipeline import extract_feature_record, run_qc

    import numpy as np

    gt_img = _resolve_seg(case.gt, case.spacing)
    candidate_present = case.candidate is not None
    candidate_img = (
        _resolve_seg(case.candidate, case.spacing) if candidate_present else None
    )

    subject_img = candidate_img if candidate_present else gt_img
    subject = "candidate" if candidate_present else "gt"

    case_result, subject_block = run_qc(subject_img, config)
    outcome = classify_outcome(
        case.expected, case_result, positive_severity=positive_severity
    )

    overlap: Optional[OverlapResult] = None
    feature_match: Optional[FeatureMatchResult] = None
    if candidate_present:
        candidate_arr = np.asanyarray(candidate_img.dataobj)
        gt_arr = np.asanyarray(gt_img.dataobj)
        gt_spacing = tuple(float(z) for z in gt_img.header.get_zooms()[:3])
        overlap = compute_overlap(candidate_arr, gt_arr, gt_spacing)

        gt_block = extract_feature_record(gt_img, config)
        feature_match = compute_feature_match(subject_block, gt_block)

    return CaseEvaluation(
        case_id=case.case_id,
        outcome=outcome,
        overlap=overlap,
        feature_match=feature_match,
        candidate_present=candidate_present,
        subject=subject,
        metadata=case.metadata,
    )


# --------------------------------------------------------------------------- #
# evaluate_cohort
# --------------------------------------------------------------------------- #


def evaluate_cohort(
    cases: Sequence[EvaluationCase],
    config: "HeuristicConfig",
    *,
    positive_severity: Severity = Severity.FLAG,
) -> CohortEvaluation:
    """Drive many :class:`EvaluationCase`\\ s, in order, into a :class:`CohortEvaluation`.

    Parameters
    ----------
    cases:
        The cases to evaluate, in order. ``case_id``s must be unique within
        the cohort. An empty sequence returns an empty cohort without error.
    config:
        A :class:`~segqc.config.HeuristicConfig`, threaded through to
        :func:`evaluate_case` for every case.
    positive_severity:
        Threshold severity passed through to :func:`evaluate_case` for every
        case.

    Returns
    -------
    CohortEvaluation
        Exactly ``len(cases)`` records, one per input case, in input order.

    Raises
    ------
    segqc.io.SegQCInputError
        If two or more cases share a ``case_id``.
    """
    seen = set()
    for case in cases:
        if case.case_id in seen:
            raise SegQCInputError(
                f"evaluate_cohort: duplicate case_id {case.case_id!r}; "
                "case_ids must be unique within a cohort."
            )
        seen.add(case.case_id)

    records = tuple(
        evaluate_case(case, config, positive_severity=positive_severity)
        for case in cases
    )
    return CohortEvaluation(cases=records)
