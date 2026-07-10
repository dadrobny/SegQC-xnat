"""Synthetic-corpus foundation: clean-GT spine builder + perturbation
framework (item 036).

Two deliverables, re-exported here as the single public surface every
downstream Stage 5 item (037-042) imports against:

1. :func:`build_clean_spine` -- a parametric, deterministic positive-control
   spine builder whose default output passes the real Stage 4 pipeline
   (:func:`segqc.pipeline.run_qc`, bundled default config) with zero
   findings.
2. The perturbation framework -- :class:`Perturbation`, :class:`Expectation`,
   :class:`PerturbationResult`, the name-keyed registry, and the reference
   :class:`IdentityPerturbation`.

Importing this package (``import segqc.synth``) imports
``segqc.synth.perturbation``, which self-registers ``IdentityPerturbation``
under ``"identity"`` -- mirroring how ``segqc.heuristics.__init__`` imports
its rule modules so every rule self-registers on import. It also imports
``segqc.synth.component_shape`` (item 037), which self-registers
``FragmentPerturbation``/``FusePerturbation``/``InjectIslandsPerturbation``
under ``"fragment"``/``"fuse"``/``"inject_islands"``.
"""

from __future__ import annotations

from segqc.synth.clean_gt import CleanSpine, DEFAULT_LEVELS, build_clean_spine
from segqc.synth.perturbation import (
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
from segqc.synth.component_shape import (
    FragmentPerturbation,
    FusePerturbation,
    InjectIslandsPerturbation,
)
from segqc.synth.coverage_border_overlap import (
    CropAtBorderPerturbation,
    ForceOverlapPerturbation,
    RemoveLevelPerturbation,
)
from segqc.synth.identity_ordering_alignment import (
    DisplacePerturbation,
    RelabelSwapPerturbation,
    SequenceBreakPerturbation,
)
from segqc.synth.corpus import (
    CORPUS_DIR,
    FIXTURES_DIRNAME,
    MANIFEST_PATH,
    MANIFEST_VERSION,
    build_corpus,
    load_manifest,
    write_corpus,
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
]
