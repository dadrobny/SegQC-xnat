"""Stage-7 evaluation package (§8: candidate-vs-reference comparison primitives).

Each module in this package is a pure, independent comparison primitive that
scores one aspect of a candidate result against a reference/ground-truth
counterpart; item 053's evaluation harness assembles them per case. This
package performs no cohort aggregation, correlation, or verdict-interpretation
logic of its own.

Currently exposes the level-2 **DICE-vs-GT** segmentation-overlap primitive
(item 050); see :mod:`segqc.eval.overlap`.
"""

from __future__ import annotations

from .overlap import LabelOverlap, OverlapResult, compute_overlap

__all__ = [
    "compute_overlap",
    "LabelOverlap",
    "OverlapResult",
]
