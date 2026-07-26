"""Run-manifest provenance record (item 096).

Carries per-run segmenter/dataset provenance -- segmenter version/SHA,
weights hash, seed, dataset id, post-processing toggles, and the resolved
``numpy``/``TPTBox``/``segfacet`` package versions -- alongside ``segfacet
run`` and ``segfacet evaluate`` output, following the existing
``EvaluationProvenance`` pattern (item 056, ``segfacet.eval.report``): a
frozen dataclass + ``.to_dict()``, embedded in a schema-validated report.

Every field is optional and caller-supplied except ``resolved_versions``,
which is always auto-populated (via ``importlib.metadata.version(...)``)
whenever a manifest is built at all -- it answers "what was actually
installed," not something a caller states. A manifest is only built (i.e.
:func:`build_run_manifest` returns non-``None``) when at least one
caller-supplied field is given; a plain invocation with no segmenter behind
its input omits the block entirely.

Public API
----------
``RunManifest``
    Frozen dataclass: ``segmenter_version``, ``segmenter_sha``,
    ``weights_hash``, ``seed``, ``dataset_id``, ``postproc_toggles``,
    ``resolved_versions``.
``build_run_manifest(*, segmenter_version=None, ...) -> Optional[RunManifest]``
    Build a manifest from caller-supplied fields, or ``None`` if none were
    given.

Dependencies: stdlib only (``importlib.metadata``); no NumPy/SciPy/NiBabel
imports.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Sequence

__all__ = ["RunManifest", "build_run_manifest"]


# --------------------------------------------------------------------------- #
# RunManifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunManifest:
    """Per-run provenance record.

    Attributes
    ----------
    segmenter_version:
        Caller-supplied version string of the segmenter that produced the
        input, or ``None`` when not given.
    segmenter_sha:
        Caller-supplied commit SHA (or similar) of the segmenter, or
        ``None`` when not given.
    weights_hash:
        Caller-supplied hash of the segmenter's weights, or ``None`` when
        not given.
    seed:
        Caller-supplied integer seed, or ``None`` when not given. ``0`` is a
        meaningful, distinct value from ``None`` (falsy-but-not-unset).
    dataset_id:
        Caller-supplied dataset identifier, or ``None`` when not given.
    postproc_toggles:
        Caller-supplied free-form JSON-compatible mapping of
        post-processing toggles, or ``None`` when not given. An explicitly
        empty ``{}`` is distinct from ``None`` (given-but-empty).
    resolved_versions:
        Auto-populated mapping of package name to its resolved installed
        version string, or ``None`` per entry when that package's metadata
        is not discoverable.
    """

    segmenter_version: Optional[str]
    segmenter_sha: Optional[str]
    weights_hash: Optional[str]
    seed: Optional[int]
    dataset_id: Optional[str]
    postproc_toggles: Optional[dict]
    resolved_versions: Dict[str, Optional[str]]

    def to_dict(self) -> dict:
        """Return a plain, JSON-serialisable dict with every field present.

        Mirrors ``EvaluationProvenance.to_dict()``'s discipline: an unset
        optional field is ``None`` in the output, never omitted.
        """
        return {
            "segmenter_version": self.segmenter_version,
            "segmenter_sha": self.segmenter_sha,
            "weights_hash": self.weights_hash,
            "seed": self.seed,
            "dataset_id": self.dataset_id,
            "postproc_toggles": self.postproc_toggles,
            "resolved_versions": dict(self.resolved_versions),
        }


# --------------------------------------------------------------------------- #
# Version resolution
# --------------------------------------------------------------------------- #


def _resolve_versions(package_names: Sequence[str]) -> Dict[str, Optional[str]]:
    """Resolve each name in *package_names* to its installed version via
    :func:`importlib.metadata.version`, or ``None`` when that package's
    metadata is not discoverable. Never raises."""
    resolved: Dict[str, Optional[str]] = {}
    for name in package_names:
        try:
            resolved[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            resolved[name] = None
    return resolved


# --------------------------------------------------------------------------- #
# build_run_manifest
# --------------------------------------------------------------------------- #

_VersionResolver = Callable[[Sequence[str]], Dict[str, Optional[str]]]


def build_run_manifest(
    *,
    segmenter_version: Optional[str] = None,
    segmenter_sha: Optional[str] = None,
    weights_hash: Optional[str] = None,
    seed: Optional[int] = None,
    dataset_id: Optional[str] = None,
    postproc_toggles: Optional[dict] = None,
    _version_resolver: _VersionResolver = _resolve_versions,
) -> Optional[RunManifest]:
    """Build a :class:`RunManifest` from caller-supplied fields, or return
    ``None`` when every caller-supplied field is ``None``.

    Parameters
    ----------
    segmenter_version, segmenter_sha, weights_hash, seed, dataset_id,
    postproc_toggles:
        Caller-supplied provenance fields; each optional. A falsy-but-not-
        ``None`` value (``seed=0``, ``postproc_toggles={}``) still counts as
        "given" -- only an actual ``None`` is treated as "not given".
    _version_resolver:
        Injectable resolver (``Sequence[str] -> Dict[str, Optional[str]]``)
        used to populate ``resolved_versions``. Defaults to
        :func:`_resolve_versions` (real ``importlib.metadata`` lookups);
        tests inject a fixed resolver for byte-reproducibility independent
        of the actual installed environment.

    Returns
    -------
    Optional[RunManifest]
        ``None`` if no caller-supplied field was given; otherwise a
        :class:`RunManifest` with ``resolved_versions`` populated from
        ``_version_resolver(("numpy", "tptbox", "segfacet"))``.
    """
    caller_fields = (
        segmenter_version,
        segmenter_sha,
        weights_hash,
        seed,
        dataset_id,
        postproc_toggles,
    )
    if all(field is None for field in caller_fields):
        return None

    resolved_versions = _version_resolver(("numpy", "tptbox", "segfacet"))

    return RunManifest(
        segmenter_version=segmenter_version,
        segmenter_sha=segmenter_sha,
        weights_hash=weights_hash,
        seed=seed,
        dataset_id=dataset_id,
        postproc_toggles=postproc_toggles,
        resolved_versions=resolved_versions,
    )
