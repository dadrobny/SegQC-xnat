# Item 015: Overlap detection between labels

**Status:** 📋 Planned
**Branch:** `aide/015-overlap-detection`
**Stage:** 2 — Geometric & Topological Feature Extraction

---

## Description

Detect **voxel-level overlap** between vertebra labels (voxels shared by two or
more label values — which should not occur in a valid instance segmentation but
does in failure mode 8). For each overlapping pair, report: the two label
integers, their anatomical names, and the overlap voxel count. Expose via
`segqc/features/overlap.py`. Overlap presence is the direct input for the
overlap heuristic in Stage 4.

---

## Acceptance Criteria

**AC1: A fixture with a deliberately overlapping pair of labels yields the
correct pair list and count.**
When a label map contains voxels painted with two different non-zero values at
the same position (overlap injected by writing the same voxels twice with
different labels), `detect_overlaps` must return a non-empty list of
`OverlapPair` records containing those two label integers and the correct voxel
count for that pair.

> In practice NIfTI/numpy label maps hold a single integer per voxel, so
> "overlap" must be represented by a separate mechanism — the implementation
> must accept a 4-D input array (shape `[L, X, Y, Z]` boolean mask stack, one
> channel per label) or an equivalent multi-label representation that allows a
> voxel to belong to multiple labels simultaneously. The exact API is left to
> the implementer; these tests fix the contract.

**AC2: A non-overlapping fixture yields an empty result.**
When no voxel is shared between any two labels, `detect_overlaps` returns an
empty sequence.

**AC3: Partial overlaps at different counts are verified.**
For two or more pairs with known, distinct overlap voxel counts, each
`OverlapPair` record carries the correct count for its pair. A pair with 10
shared voxels and a pair with 3 shared voxels appear as separate records with
those exact counts.

**AC4: Results are deterministic.**
Calling `detect_overlaps` twice with the same input returns identical results
(same pairs, same counts, same order or sortable to the same order).

---

## Decisions & Trade-offs

- **Multi-label input representation.** A standard 3-D integer label map cannot
  represent a voxel belonging to two labels simultaneously (only one integer fits
  per voxel). The module therefore accepts a **boolean mask stack**: a 4-D numpy
  array of shape `(n_labels, X, Y, Z)` together with a corresponding 1-D array
  of label integers of length `n_labels`. Overlap at voxel `(x, y, z)` is
  detected by checking whether `mask_stack[:, x, y, z].sum() > 1`.
- **OverlapPair record.** A dataclass (or NamedTuple) with fields:
  `label_a: int`, `label_b: int`, `name_a: str`, `name_b: str`,
  `overlap_voxels: int`. Pair ordering (`label_a < label_b`) is enforced so
  duplicate pairs cannot arise.
- **Anatomical names.** Resolved via the default `LabelConvention`; unmapped
  labels fall back to `UNKNOWN`.
- **Empty input.** Zero labels → empty result. One label → empty result (no
  pair possible).
- **Duplicate-pair safety.** The implementation iterates unique label pairs, so
  `(A, B)` and `(B, A)` are never both emitted.
- **Scope.** Serialisation into the JSON report is item 016; this module only
  computes and returns `OverlapPair` records.
