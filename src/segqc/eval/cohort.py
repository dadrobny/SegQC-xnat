"""Evaluation-cohort manifest loader (item 057).

This is the general, dataset-agnostic ingestion path for the ``segqc
evaluate`` CLI entry point: a small, synth-independent JSON manifest naming a
set of ``(GT, optional candidate, expectation)`` cases -- e.g. a mounted
VerSe GT / TotalSegmentator-vs-GT cohort -- resolved into a
``list[segqc.eval.harness.EvaluationCase]`` ready for
:func:`segqc.eval.harness.evaluate_cohort`.

Manifest shape (pinned in the item 057 spec's Assumptions)::

    {
      "manifest_version": 1,
      "cases": [
        {
          "case_id": "sub-001",
          "gt": "fixtures/sub-001_gt.nii.gz",
          "candidate": "fixtures/sub-001_cand.nii.gz",
          "spacing": [1.0, 1.0, 1.0],
          "expected": {
            "expected_verdict": "pass",
            "expected_rule_ids": [],
            "expected_labels": [],
            "failure_mode": 0,
            "failure_mode_name": "clean control (no failure)"
          },
          "metadata": {}
        }
      ]
    }

``case_id``, ``gt``, and ``expected`` (with ``expected_verdict``) are
**required** per case; ``candidate``, ``spacing``, and ``metadata`` are
optional. ``gt``/``candidate`` are resolved **relative to the manifest
file's own directory** (like the Stage-5 corpus manifest's ``seg_fixture``)
and existence-checked eagerly so a missing fixture is reported as a clear
:class:`~segqc.io.SegQCInputError`, not a deferred ``nib.load`` traceback.

This is an **input** artifact (not a byte-reproducible output), so it is
validated in code rather than via a bundled JSON schema; an unrecognised
``manifest_version`` is accepted with a logged note (forward-compatible) --
only structural violations raise.

Public API
----------
``EVAL_COHORT_MANIFEST_VERSION``
    The manifest-version integer this loader was written against (``1``).
``load_cohort_manifest(path) -> list[EvaluationCase]``
    Parse a cohort manifest and build one :class:`EvaluationCase` per case,
    in manifest order.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, List, Mapping, Optional, Tuple, Union

from segqc.eval.harness import EvaluationCase
from segqc.io import SegQCInputError

__all__ = [
    "EVAL_COHORT_MANIFEST_VERSION",
    "load_cohort_manifest",
]

logger = logging.getLogger(__name__)

#: The manifest-version integer this loader was written against.
EVAL_COHORT_MANIFEST_VERSION: int = 1


def _resolve_path(base_dir: pathlib.Path, value: str, *, field: str, case_id: Any) -> str:
    """Resolve *value* relative to *base_dir* and assert it exists on disk."""
    resolved = (base_dir / value).resolve()
    if not resolved.exists():
        raise SegQCInputError(
            f"load_cohort_manifest: case {case_id!r} field {field!r} does not "
            f"exist on disk: {resolved}"
        )
    return str(resolved)


def _spacing_from(raw: Any, *, case_id: Any) -> Optional[Tuple[float, float, float]]:
    if raw is None:
        return None
    try:
        sx, sy, sz = raw
        return (float(sx), float(sy), float(sz))
    except (TypeError, ValueError) as exc:
        raise SegQCInputError(
            f"load_cohort_manifest: case {case_id!r} field 'spacing' must be a "
            f"3-element (sx, sy, sz) sequence; got {raw!r}"
        ) from exc


def load_cohort_manifest(
    path: Union[str, "pathlib.PathLike"],
) -> List[EvaluationCase]:
    """Parse an evaluation-cohort manifest JSON at *path* and build one
    :class:`~segqc.eval.harness.EvaluationCase` per case, in manifest order.

    Parameters
    ----------
    path:
        Path to the manifest JSON file. ``gt``/``candidate`` case paths are
        resolved relative to ``path``'s parent directory.

    Returns
    -------
    list[EvaluationCase]
        One case per manifest entry, in manifest order.

    Raises
    ------
    segqc.io.SegQCInputError
        If the manifest file cannot be read/parsed as JSON, has no top-level
        ``"cases"`` array, a case is missing ``case_id``/``gt``/``expected``,
        an ``expected`` mapping lacks ``expected_verdict``, two cases share a
        ``case_id``, or a resolved ``gt``/``candidate`` path does not exist
        on disk.
    """
    manifest_path = pathlib.Path(path)
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SegQCInputError(
            f"load_cohort_manifest: cannot read manifest file: {manifest_path}"
        ) from exc

    try:
        manifest = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SegQCInputError(
            f"load_cohort_manifest: manifest is not valid JSON: {manifest_path} "
            f"({exc})"
        ) from exc

    if not isinstance(manifest, Mapping) or "cases" not in manifest:
        raise SegQCInputError(
            f"load_cohort_manifest: manifest has no top-level 'cases' array: "
            f"{manifest_path}"
        )

    raw_cases = manifest["cases"]
    if not isinstance(raw_cases, list):
        raise SegQCInputError(
            f"load_cohort_manifest: manifest 'cases' must be an array: "
            f"{manifest_path}"
        )

    manifest_version = manifest.get("manifest_version")
    if manifest_version is not None and manifest_version != EVAL_COHORT_MANIFEST_VERSION:
        logger.info(
            "load_cohort_manifest: manifest_version %r differs from the "
            "loader's known version %r (%s); accepting forward-compatibly.",
            manifest_version, EVAL_COHORT_MANIFEST_VERSION, manifest_path,
        )

    base_dir = manifest_path.parent

    cases: List[EvaluationCase] = []
    seen_ids: set = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, Mapping):
            raise SegQCInputError(
                f"load_cohort_manifest: case at index {index} is not an "
                f"object: {manifest_path}"
            )

        if "case_id" not in raw_case:
            raise SegQCInputError(
                f"load_cohort_manifest: case at index {index} is missing "
                f"required field 'case_id': {manifest_path}"
            )
        case_id = raw_case["case_id"]

        if "gt" not in raw_case:
            raise SegQCInputError(
                f"load_cohort_manifest: case {case_id!r} is missing required "
                f"field 'gt': {manifest_path}"
            )
        if "expected" not in raw_case:
            raise SegQCInputError(
                f"load_cohort_manifest: case {case_id!r} is missing required "
                f"field 'expected': {manifest_path}"
            )

        expected = raw_case["expected"]
        if not isinstance(expected, Mapping) or "expected_verdict" not in expected:
            raise SegQCInputError(
                f"load_cohort_manifest: case {case_id!r}'s 'expected' mapping "
                f"is missing required key 'expected_verdict': {manifest_path}"
            )

        if case_id in seen_ids:
            raise SegQCInputError(
                f"load_cohort_manifest: duplicate case_id {case_id!r} in "
                f"{manifest_path}"
            )
        seen_ids.add(case_id)

        gt_path = _resolve_path(base_dir, raw_case["gt"], field="gt", case_id=case_id)

        candidate_raw = raw_case.get("candidate")
        candidate_path = (
            _resolve_path(base_dir, candidate_raw, field="candidate", case_id=case_id)
            if candidate_raw is not None
            else None
        )

        spacing = _spacing_from(raw_case.get("spacing"), case_id=case_id)

        metadata_raw = raw_case.get("metadata")
        metadata = dict(metadata_raw) if metadata_raw is not None else None

        cases.append(
            EvaluationCase(
                case_id=case_id,
                gt=gt_path,
                candidate=candidate_path,
                expected=dict(expected),
                spacing=spacing,
                metadata=metadata,
            )
        )

    return cases
