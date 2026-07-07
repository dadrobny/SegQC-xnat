"""Feature-extraction + QC orchestration pipeline (item 035).

Turns the already-merged Stage 2/3 extractors (items 011-020), the
``build_features_block`` assembler (item 016/022), the Stage 4 rule engine
(items 026-033), and the verdict aggregator (item 034) into a single,
production entry point that ``segqc run`` (``cli.py``) drives:

``extract_feature_record(seg_img, config) -> dict``
    Compute the Stage 2 (and, when there are >= 2 labelled vertebrae, Stage 3)
    feature block for a segmentation image -- exactly the dict shape
    ``build_features_block`` already returns, unchanged, so it is the very
    same record the Stage 4 rules were written against.

``run_qc(seg_img, config, *, base_reasons=(), base_per_label=None) ->
tuple[CaseResult, dict]``
    Compose ``extract_feature_record`` with ``run_rules`` (item 026) and
    ``build_case_result`` (item 034) into one call: extract features, run the
    rules over them, fold the findings (plus any Stage 1 base reasons) into a
    verdict, and return both the :class:`~segqc.aggregate.CaseResult` and the
    features block (so the CLI can embed both in the JSON report).

Design decisions (item 035)
----------------------------
1. **No new record schema.** ``extract_feature_record`` returns exactly what
   ``feature_report.build_features_block`` returns; the rules already consume
   that shape (items 027-033), so nothing new is introduced here.
2. **Stage 3 guarded on >= 2 centroids.** ``fit_centroid_spline`` (item 017)
   raises for < 2 points, so Stage 3 is only attempted when at least two
   labels are present; 0/1-label maps still produce a valid Stage-2-only
   block (no ``stage3`` key), matching ``mislabel``'s tolerant handling of an
   absent ``stage3`` sub-block.
3. **Ascending integer-label order is the "ordered centroid sequence".** The
   per-label ordering already used by ``build_features_block`` (ascending
   integer label) is reused as the single consistent order fed to
   ``compute_spine_relationships``, the spline fit, and every Stage 3
   extractor -- deterministic and requires no extra bookkeeping.
4. **Heavy imports (NumPy, SciPy, the ``segqc.features``/``segqc.heuristics``
   submodules) are deferred inside the functions**, consistent with the CLI's
   existing deferred-import style, so ``import segqc.pipeline`` alone stays
   cheap.
5. **Read-only, deterministic, non-mutating.** Neither function mutates
   ``seg_img``, ``config``, ``base_reasons``, or ``base_per_label``; two calls
   on the same inputs return equal results (``aggregate_verdict`` /
   ``build_case_result`` already copy their inputs defensively).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence, Tuple

if TYPE_CHECKING:
    import nibabel as nib

    from segqc.aggregate import CaseResult
    from segqc.config import HeuristicConfig
    from segqc.verdict import Reason

__all__ = ["extract_feature_record", "run_qc"]


def extract_feature_record(seg_img: "nib.Nifti1Image", config: "HeuristicConfig") -> dict:
    """Assemble the per-case ``features`` block for *seg_img*.

    Derives the present labels from *seg_img* (sorted non-zero unique voxel
    values), computes the Stage 2 per-label maps (geometry, connected
    components, centroid), the case-level relationships and overlaps, and --
    when at least two labels are present -- the five Stage 3 objects (spline
    fit, per-label spline offsets, orientations, curvature, spacing/monotonic
    consistency). The result is exactly the dict
    ``feature_report.build_features_block(...)`` returns.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map. Read
        only -- never modified.
    config:
        A :class:`~segqc.config.HeuristicConfig`, threaded through to
        ``compute_components`` (item 012's ``min_fragment_voxels``).

    Returns
    -------
    dict
        A schema-valid ``features`` block: always carries
        ``features_version``, ``per_label``, ``relationships``, ``overlaps``;
        additionally carries ``stage3`` when >= 2 labels are present. Robust
        to 0- and 1-label maps -- never raises.
    """
    import numpy as np

    from segqc.feature_report import build_features_block
    from segqc.features.centroids import compute_centroid
    from segqc.features.components import compute_components
    from segqc.features.geometry import compute_label_geometry
    from segqc.features.overlap import detect_overlaps
    from segqc.features.relationships import compute_spine_relationships

    data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(data) if v != 0)

    geometry = {label: compute_label_geometry(seg_img, label) for label in labels}
    components = {
        label: compute_components(seg_img, label, config) for label in labels
    }
    centroids = {label: compute_centroid(seg_img, label) for label in labels}

    # Ascending-label order is the single consistent "ordered centroid
    # sequence" fed to relationships and every Stage 3 extractor below.
    ordered_centroids = [centroids[label] for label in labels]

    if labels:
        relationships = compute_spine_relationships(ordered_centroids)
    else:
        relationships = None

    if len(labels) >= 2:
        mask_stack = np.stack([data == label for label in labels], axis=0)
        overlaps = detect_overlaps(mask_stack, np.array(labels))
    else:
        overlaps = []

    stage3_kwargs: dict = {}
    if len(labels) >= 2:
        from segqc.features.consistency import (
            compute_monotonic_consistency,
            compute_spacing_consistency,
        )
        from segqc.features.orientation import (
            compute_spine_curvature,
            compute_vertebra_orientations,
        )
        from segqc.features.spline import fit_centroid_spline
        from segqc.features.spline_offset import compute_spline_offsets

        spacing_mm = tuple(float(z) for z in seg_img.header.get_zooms()[:3])
        fit = fit_centroid_spline(ordered_centroids)

        stage3_kwargs = {
            "spline_offsets": compute_spline_offsets(
                ordered_centroids, fit, spacing_mm=spacing_mm
            ),
            "orientations": compute_vertebra_orientations(seg_img, labels),
            "curvature": compute_spine_curvature(fit, ordered_centroids),
            "spacing_consistency": compute_spacing_consistency(ordered_centroids),
            "monotonic_consistency": compute_monotonic_consistency(
                ordered_centroids, fit
            ),
        }

    return build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=overlaps,
        **stage3_kwargs,
    )


def run_qc(
    seg_img: "nib.Nifti1Image",
    config: "HeuristicConfig",
    *,
    base_reasons: Sequence["Reason"] = (),
    base_per_label: Optional[Mapping[int, Sequence["Reason"]]] = None,
) -> Tuple["CaseResult", dict]:
    """Extract features, run the Stage 4 rules, and aggregate a verdict.

    Composes :func:`extract_feature_record`, ``run_rules`` (item 026), and
    ``build_case_result`` (item 034) into a single call for the CLI.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map.
    config:
        A :class:`~segqc.config.HeuristicConfig`.
    base_reasons:
        Optional pre-existing case-level reasons (e.g. the Stage 1
        empty/near-empty check) threaded through to
        ``aggregate.build_case_result``. Not mutated.
    base_per_label:
        Optional pre-existing per-vertebra reasons, keyed by integer label.
        Threaded through to ``aggregate.build_case_result``. Not mutated.

    Returns
    -------
    tuple[CaseResult, dict]
        ``(case_result, features_block)`` where
        ``case_result.findings == tuple(run_rules(features_block, config))``
        and ``case_result.verdict`` is the aggregated
        :class:`~segqc.verdict.Verdict`. Deterministic: repeated calls on the
        same inputs return equal results.
    """
    from segqc.aggregate import build_case_result
    from segqc.heuristics import run_rules

    features_block = extract_feature_record(seg_img, config)
    findings = run_rules(features_block, config)
    case_result = build_case_result(
        findings, config, base_reasons=base_reasons, base_per_label=base_per_label
    )
    return case_result, features_block
