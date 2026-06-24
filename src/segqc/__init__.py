"""segqc — automated quality control for vertebra instance segmentations.

This package provides an explainable, reference-grounded heuristic QC gate for
spine-segmentation label maps. See ``docs/aide/vision.md`` for the full vision.

This module is the single source of truth for the package version; the build
backend reads ``__version__`` from here (see ``[tool.hatch.version]`` in
``pyproject.toml``).
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
