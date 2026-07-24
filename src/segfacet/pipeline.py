"""Feature-extraction + QC orchestration pipeline (item 035).

Turns the already-merged Stage 2/3 extractors (items 011-020), the
``build_features_block`` assembler (item 016/022), the Stage 4 rule engine
(items 026-033), and the verdict aggregator (item 034) into a single,
production entry point that ``segfacet run`` (``cli.py``) drives:

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
    verdict, and return both the :class:`~segfacet.aggregate.CaseResult` and the
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
4. **Heavy imports (NumPy, SciPy, the ``segfacet.features``/``segfacet.heuristics``
   submodules) are deferred inside the functions**, consistent with the CLI's
   existing deferred-import style, so ``import segfacet.pipeline`` alone stays
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

    from segfacet.aggregate import CaseResult
    from segfacet.config import HeuristicConfig
    from segfacet.reference.schema import ReferenceDistribution
    from segfacet.verdict import Reason

__all__ = [
    "extract_feature_record",
    "run_qc",
    "run_qc_with_reference",
    "run_qc_with_intensity",
]


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
        A :class:`~segfacet.config.HeuristicConfig`, threaded through to
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

    from segfacet.feature_report import build_features_block
    from segfacet.features.centroids import compute_centroid
    from segfacet.features.components import compute_components
    from segfacet.features.geometry import compute_label_geometry
    from segfacet.features.overlap import detect_overlaps
    from segfacet.features.relationships import compute_spine_relationships

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
        from segfacet.features.consistency import (
            compute_monotonic_consistency,
            compute_spacing_consistency,
        )
        from segfacet.features.orientation import (
            compute_spine_curvature,
            compute_vertebra_orientations,
        )
        from segfacet.features.spline import fit_centroid_spline
        from segfacet.features.spline_offset import compute_spline_offsets

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
        A :class:`~segfacet.config.HeuristicConfig`.
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
        :class:`~segfacet.verdict.Verdict`. Deterministic: repeated calls on the
        same inputs return equal results.
    """
    from segfacet.aggregate import build_case_result
    from segfacet.heuristics import run_rules

    features_block = extract_feature_record(seg_img, config)
    findings = run_rules(features_block, config)
    case_result = build_case_result(
        findings, config, base_reasons=base_reasons, base_per_label=base_per_label
    )
    return case_result, features_block


def run_qc_with_reference(
    seg_img: "nib.Nifti1Image",
    config: "HeuristicConfig",
    reference: "ReferenceDistribution",
    *,
    base_reasons: Sequence["Reason"] = (),
    base_per_label: Optional[Mapping[int, Sequence["Reason"]]] = None,
    stratum: str = "all",
    lower_pct: float = 1,
    upper_pct: float = 99,
) -> Tuple["CaseResult", dict, dict]:
    """Extract features, compute a reference delta, run the Stage 4 rules
    over a reference-aware record, and aggregate a verdict (item 049).

    A reference-aware sibling of :func:`run_qc`: additionally computes item
    046's delta-to-reference block and attaches both the reference and its
    delta to the record fed to the rule engine (under ``"reference"`` and
    ``"reference_delta"`` respectively), so item 047's ``ReferenceDeltaRule``
    and item 048's reference-mode ``BoundsRule`` can act on them. The
    returned ``features_block`` never carries those keys -- they live only on
    the transient rule-evaluation record -- so it stays schema-clean and
    identical in shape to :func:`extract_feature_record`'s plain output.

    ``run_qc`` itself is untouched: this is an additive code path, not a
    modification, so the ~40 existing 2-tuple call sites and the item-042
    golden snapshots stay byte-identical.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map.
    config:
        A :class:`~segfacet.config.HeuristicConfig`.
    reference:
        A :class:`~segfacet.reference.schema.ReferenceDistribution` to compare
        *seg_img*'s per-label geometry against. Not mutated.
    base_reasons:
        Optional pre-existing case-level reasons, threaded through to
        ``aggregate.build_case_result``. Not mutated.
    base_per_label:
        Optional pre-existing per-vertebra reasons, keyed by integer label.
        Threaded through to ``aggregate.build_case_result``. Not mutated.
    stratum:
        The reference stratum to compare against (default ``"all"``, item
        043's ``ALL_STRATUM``).
    lower_pct, upper_pct:
        The percentile pair defining the reference's in-range band (default
        ``1``/``99``, matching item 046's ``DEFAULT_LOWER_PCT``/
        ``DEFAULT_UPPER_PCT``).

    Returns
    -------
    tuple[CaseResult, dict, dict]
        ``(case_result, features_block, reference_delta)`` where
        ``features_block`` carries no ``reference``/``reference_delta`` keys
        and ``reference_delta`` equals
        ``reference_delta_to_dict(compute_reference_delta(features_block,
        reference, stratum=stratum, lower_pct=lower_pct,
        upper_pct=upper_pct))``. Deterministic and non-mutating: repeated
        calls on the same inputs return equal results, and neither
        ``seg_img``, ``config``, nor ``reference`` is modified.
    """
    from segfacet.aggregate import build_case_result
    from segfacet.heuristics import run_rules
    from segfacet.reference import compute_reference_delta, reference_delta_to_dict

    features_block = extract_feature_record(seg_img, config)

    delta = compute_reference_delta(
        features_block, reference, stratum=stratum, lower_pct=lower_pct, upper_pct=upper_pct
    )
    reference_delta = reference_delta_to_dict(delta)

    rule_record = {
        **features_block,
        "reference": reference,
        "reference_delta": reference_delta,
    }
    findings = run_rules(rule_record, config)
    case_result = build_case_result(
        findings, config, base_reasons=base_reasons, base_per_label=base_per_label
    )
    return case_result, features_block, reference_delta


def run_qc_with_intensity(
    seg_img: "nib.Nifti1Image",
    scan_img: "nib.Nifti1Image",
    config: "HeuristicConfig",
    *,
    reference: "Optional[ReferenceDistribution]" = None,
    base_reasons: Sequence["Reason"] = (),
    base_per_label: Optional[Mapping[int, Sequence["Reason"]]] = None,
    enable_pyradiomics: bool = True,
    stratum: str = "all",
    lower_pct: float = 1,
    upper_pct: float = 99,
) -> Tuple["CaseResult", dict, dict, Optional[dict], Optional[dict]]:
    """Extract geometric + intensity features, run the Stage 4 rules over the
    composed record, and aggregate a verdict (item 065).

    An intensity-aware sibling of :func:`run_qc` / :func:`run_qc_with_reference`:
    composes :func:`extract_feature_record` with item 059/060's per-label
    intensity/radiomics extraction and item 061's ``image_features`` block
    assembly, attaching ``image_features`` to the record fed to the rule
    engine (under ``"image_features"``) so item 062's ``IntensityRule`` can
    act on it. When a *reference* is supplied, also computes the geometric
    reference delta (item 046) and the intensity reference delta (item 064),
    attaching ``"reference"``, ``"reference_delta"``, and
    ``"intensity_reference_delta"`` to the record so item 047's
    ``ReferenceDeltaRule`` and item 064's ``IntensityReferenceDeltaRule`` can
    act on them too.

    ``run_qc``/``run_qc_with_reference`` are not edited: this is a new,
    additive code path, so their existing call sites and the item-042 golden
    snapshots stay byte-identical.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map.
    scan_img:
        A NiBabel ``Nifti1Image`` carrying scan intensity data, grid-aligned
        with ``seg_img`` (same shape, compatible affine; item 059's
        ``_check_alignment`` raises ``ValueError`` otherwise).
    config:
        A :class:`~segfacet.config.HeuristicConfig`.
    reference:
        Optional :class:`~segfacet.reference.schema.ReferenceDistribution`. When
        given, both the geometric and intensity reference deltas are
        computed and attached; when ``None`` (default), both delta return
        values are ``None`` and no delta-related key is added to the record.
    base_reasons:
        Optional pre-existing case-level reasons, threaded through to
        ``aggregate.build_case_result``. Not mutated.
    base_per_label:
        Optional pre-existing per-vertebra reasons, keyed by integer label.
        Threaded through to ``aggregate.build_case_result``. Not mutated.
    enable_pyradiomics:
        Forwarded to item 060's ``compute_radiomics_features``; when
        ``False``, forces the builtin (first-order-only) backend even if
        PyRadiomics happens to be installed.
    stratum:
        The reference stratum to compare against (default ``"all"``).
    lower_pct, upper_pct:
        The percentile pair defining the reference's in-range band.

    Returns
    -------
    tuple[CaseResult, dict, dict, dict | None, dict | None]
        ``(case_result, features_block, image_features_block, reference_delta,
        intensity_reference_delta)``. ``features_block`` carries no
        ``image_features``/``reference``/``reference_delta``/
        ``intensity_reference_delta`` keys -- those live only on the
        transient rule-evaluation record. ``image_features_block`` is
        always populated (``available == True``) when this function
        succeeds. ``reference_delta``/``intensity_reference_delta`` are
        ``None`` unless *reference* is given. Deterministic and
        non-mutating: repeated calls on the same inputs return equal
        results, and none of ``seg_img``, ``scan_img``, ``config``, nor
        ``reference`` is modified.

    Raises
    ------
    ValueError
        If ``scan_img`` and ``seg_img`` have mismatched shapes or
        incompatible affines (beyond tolerance) -- item 059's
        ``_check_alignment`` guard.
    """
    from segfacet.aggregate import build_case_result
    from segfacet.feature_report import build_image_features_block
    from segfacet.features.radiomics import compute_radiomics_features
    from segfacet.heuristics import run_rules
    from segfacet.reference import (
        compute_intensity_reference_delta,
        compute_reference_delta,
        reference_delta_to_dict,
    )

    features_block = extract_feature_record(seg_img, config)

    radiomics = compute_radiomics_features(
        scan_img, seg_img, enable_pyradiomics=enable_pyradiomics
    )
    image_features_block = build_image_features_block(
        intensity={label: r.first_order for label, r in radiomics.items()},
        extended={label: r.extended for label, r in radiomics.items()},
        backend=(
            "pyradiomics"
            if any(r.radiomics_available for r in radiomics.values())
            else "builtin"
        ),
        radiomics_available=any(
            r.radiomics_available for r in radiomics.values()
        ),
    )

    rule_record = {**features_block, "image_features": image_features_block}

    reference_delta: Optional[dict] = None
    intensity_reference_delta: Optional[dict] = None
    if reference is not None:
        delta = compute_reference_delta(
            features_block,
            reference,
            stratum=stratum,
            lower_pct=lower_pct,
            upper_pct=upper_pct,
        )
        reference_delta = reference_delta_to_dict(delta)

        intensity_delta = compute_intensity_reference_delta(
            features_block,
            image_features_block,
            reference,
            stratum=stratum,
            lower_pct=lower_pct,
            upper_pct=upper_pct,
        )
        intensity_reference_delta = reference_delta_to_dict(intensity_delta)

        rule_record["reference"] = reference
        rule_record["reference_delta"] = reference_delta
        rule_record["intensity_reference_delta"] = intensity_reference_delta

    findings = run_rules(rule_record, config)
    case_result = build_case_result(
        findings, config, base_reasons=base_reasons, base_per_label=base_per_label
    )
    return (
        case_result,
        features_block,
        image_features_block,
        reference_delta,
        intensity_reference_delta,
    )
