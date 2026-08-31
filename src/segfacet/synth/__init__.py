"""Synthetic-corpus foundation: clean-GT spine builder + perturbation
framework (item 036).

Two deliverables, re-exported here as the single public surface every
downstream Stage 5 item (037-042) imports against:

1. :func:`build_clean_spine` -- a parametric, deterministic positive-control
   spine builder whose default output passes the real Stage 4 pipeline
   (:func:`segfacet.pipeline.run_qc`, bundled default config) with zero
   findings.
2. The perturbation framework -- :class:`Perturbation`, :class:`Expectation`,
   :class:`PerturbationResult`, the name-keyed registry, and the reference
   :class:`IdentityPerturbation`.

Importing this package (``import segfacet.synth``) imports
``segfacet.synth.perturbation``, which self-registers ``IdentityPerturbation``
under ``"identity"`` -- mirroring how ``segfacet.heuristics.__init__`` imports
its rule modules so every rule self-registers on import. It also imports
``segfacet.synth.component_shape`` (item 037), which self-registers
``FragmentPerturbation``/``FusePerturbation``/``InjectIslandsPerturbation``
under ``"fragment"``/``"fuse"``/``"inject_islands"``.
"""

from __future__ import annotations

from segfacet.synth.clean_gt import CleanSpine, DEFAULT_LEVELS, build_clean_spine
from segfacet.synth.perturbation import (
    CLEAN_CONTROL_MODE,
    FAILURE_MODE_NAMES,
    Expectation,
    IdentityPerturbation,
    Perturbation,
    PerturbationResult,
    get_perturbation,
    iter_perturbations,
    perturbation_names,
    register_perturbation,
    seeded_rng,
)
from segfacet.synth.component_shape import (
    FragmentPerturbation,
    FusePerturbation,
    InjectIslandsPerturbation,
)
from segfacet.synth.coverage_border_overlap import (
    CropAtBorderPerturbation,
    ForceOverlapPerturbation,
    RemoveLevelPerturbation,
)
from segfacet.synth.identity_ordering_alignment import (
    DisplacePerturbation,
    RelabelSwapPerturbation,
    SequenceBreakPerturbation,
)
from segfacet.synth.corpus import (
    CORPUS_DIR,
    FIXTURES_DIRNAME,
    MANIFEST_PATH,
    MANIFEST_VERSION,
    build_corpus,
    load_manifest,
    write_corpus,
)
from segfacet.synth.regression import (
    RECONSTRUCTIONS,
    designated_findings,
    designated_rule_fired,
    loaded_seg_image,
    offending_labels_match,
    pipeline_findings,
    pipeline_hides_designated_rule,
    pipeline_verdict_label,
    reconstructed_findings,
    verify_case,
)
from segfacet.synth.intensity import (
    BONE_PLAUSIBLE_BAND,
    CASE_RECIPE as INTENSITY_CASE_RECIPE,
    DEFAULT_HU_MODEL,
    HUModel,
    IMPLAUSIBLE_FILLS,
    ImplausibleFill,
    INTENSITY_CORPUS_DIR,
    INTENSITY_FIXTURES_DIRNAME,
    INTENSITY_MANIFEST_PATH,
    INTENSITY_MANIFEST_VERSION,
    IntensityCase,
    build_intensity_corpus,
    load_intensity_manifest,
    paint_clean_scan,
    paint_implausible_variant,
    write_intensity_corpus,
)
from segfacet.synth.golden import (
    GOLDEN_ABS_TOL,
    GOLDEN_REL_TOL,
    VOLATILE_POINTERS,
    VOLATILE_SENTINEL,
    build_report_for_case,
    canonical_json,
    check_case_golden,
    golden_path,
    load_golden,
    read_golden_text,
    reports_close,
    write_goldens,
)

__all__ = [
    "DEFAULT_LEVELS",
    "CleanSpine",
    "build_clean_spine",
    "CLEAN_CONTROL_MODE",
    "FAILURE_MODE_NAMES",
    "Expectation",
    "PerturbationResult",
    "Perturbation",
    "register_perturbation",
    "get_perturbation",
    "iter_perturbations",
    "perturbation_names",
    "seeded_rng",
    "IdentityPerturbation",
    "FragmentPerturbation",
    "FusePerturbation",
    "InjectIslandsPerturbation",
    "RemoveLevelPerturbation",
    "CropAtBorderPerturbation",
    "ForceOverlapPerturbation",
    "DisplacePerturbation",
    "RelabelSwapPerturbation",
    "SequenceBreakPerturbation",
    "CORPUS_DIR",
    "FIXTURES_DIRNAME",
    "MANIFEST_PATH",
    "MANIFEST_VERSION",
    "build_corpus",
    "load_manifest",
    "write_corpus",
    "RECONSTRUCTIONS",
    "loaded_seg_image",
    "pipeline_findings",
    "pipeline_verdict_label",
    "reconstructed_findings",
    "designated_findings",
    "designated_rule_fired",
    "offending_labels_match",
    "pipeline_hides_designated_rule",
    "verify_case",
    "GOLDEN_ABS_TOL",
    "GOLDEN_REL_TOL",
    "VOLATILE_POINTERS",
    "VOLATILE_SENTINEL",
    "build_report_for_case",
    "canonical_json",
    "check_case_golden",
    "golden_path",
    "load_golden",
    "read_golden_text",
    "reports_close",
    "write_goldens",
    "HUModel",
    "DEFAULT_HU_MODEL",
    "ImplausibleFill",
    "IMPLAUSIBLE_FILLS",
    "BONE_PLAUSIBLE_BAND",
    "paint_clean_scan",
    "paint_implausible_variant",
    "INTENSITY_CORPUS_DIR",
    "INTENSITY_MANIFEST_PATH",
    "INTENSITY_FIXTURES_DIRNAME",
    "INTENSITY_MANIFEST_VERSION",
    "IntensityCase",
    "INTENSITY_CASE_RECIPE",
    "build_intensity_corpus",
    "load_intensity_manifest",
    "write_intensity_corpus",
]
