# Item 007 — Empty / Near-Empty Detection

> **Status:** 📋 Planned · **Created:** 2026-06-25
> **Stage:** 1 — End-to-End Thin Slice: Empty Detection + Report
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 007
> **Objectives:** G1 — Detect empty / trivially-failed segmentations
> **Suggested branch:** `aide/007-empty-detection`

---

## Description

Implement configurable detection of **empty** and **near-empty** (trivially-
failed) segmentations. Three independent conditions are checked; any one that
fires marks the segmentation as a failure:

1. **No labels present** — the label map is all-zero (foreground voxel count is 0
   and distinct label count is 0).
2. **Total foreground below N voxels** — the total count of all non-zero voxels
   is below a configurable threshold `min_foreground_voxels`.
3. **Fewer than K distinct labels** — the number of distinct non-zero label
   values is below a configurable threshold `min_label_count`.

All thresholds are read from `HeuristicConfig` (item 005). The default values
(`min_foreground_voxels=0`, `min_label_count=0`) mean "no threshold applied", so
by default the only failing case is a completely empty map.

The function lives at `src/segqc/empty.py` and is importable as
`from segqc.empty import check_empty`. It accepts a NiBabel `Nifti1Image` (the
instance label map) and a `HeuristicConfig`, and returns a `CheckResult`
(a small dataclass / named tuple) carrying:

- `is_empty: bool` — True if any condition fires.
- `reasons: list[str]` — human-readable reason strings for each fired condition
  (empty list if none fires). These strings should be human-friendly with no raw
  Python library internals.
- `foreground_voxels: int` — total non-zero voxel count (always computed).
- `label_count: int` — distinct non-zero label count (always computed).

Item 010 (pipeline wiring) will wrap these reason strings into `Reason` objects
and attach them to a `Verdict`. This item does **not** depend on `segqc.verdict`
(item 008) at runtime; the coupling is deferred to item 010.

### Scope boundary

| Concern | Owned by | This item |
|---|---|---|
| `HeuristicConfig` dataclass and `min_*` fields | Item 005 | **consumed** here — already stubbed |
| `Severity`, `Reason`, `Verdict` data model | Item 008 | **not** used here; strings returned instead |
| Pipeline wiring (CLI end-to-end) | Item 010 | not here |
| Per-vertebra QC (volume, shape, overlap heuristics) | Stage 4 | not here |

---

## Acceptance Criteria

- [ ] **AC-1 Empty label map → failure**: `check_empty` called with an all-zero
      label map returns `is_empty=True` and a non-empty `reasons` list, regardless
      of threshold settings.
- [ ] **AC-2 Foreground threshold fires correctly**: when `min_foreground_voxels`
      is set to a value N > 0, a label map with fewer than N foreground voxels
      (but at least one label present) returns `is_empty=True` with a reason
      string that mentions voxel count. A map with exactly N voxels passes.
- [ ] **AC-3 Label-count threshold fires correctly**: when `min_label_count` is
      set to a value K > 0, a label map with fewer than K distinct non-zero labels
      returns `is_empty=True` with a reason string that mentions label count. A map
      with exactly K distinct labels passes.
- [ ] **AC-4 Populated map passes with default thresholds**: a standard
      multi-label fixture (≥1 foreground voxel, ≥1 label) with `min_foreground_voxels=0`
      and `min_label_count=0` (the defaults) returns `is_empty=False` and an
      empty `reasons` list.
- [ ] **AC-5 Both thresholds can fire simultaneously**: a single-label,
      single-voxel map with `min_foreground_voxels=2` and `min_label_count=2`
      returns `is_empty=True` with two separate reason strings (one per fired
      condition).
- [ ] **AC-6 Metadata always returned**: `foreground_voxels` and `label_count`
      on the returned `CheckResult` always reflect the actual counts from the label
      map, regardless of whether any threshold fired.
- [ ] **AC-7 Config controls thresholds**: raising `min_foreground_voxels` from
      0 to a value above the fixture's voxel count changes the verdict from pass
      to fail without changing the input image.
- [ ] **AC-8 Module location**: `from segqc.empty import check_empty` imports
      without error.
- [ ] **AC-9 No non-stdlib runtime imports beyond numpy/nibabel**: the module must
      not import `scipy`, `skimage`, `segqc.verdict`, or any other package beyond
      the Python standard library, NumPy, and NiBabel.
- [ ] **AC-10 Reason strings are human-friendly**: no reason string contains raw
      Python exception text, class names like `NiftiImage`, or internal attribute
      paths. Each reason string mentions the relevant threshold value and the
      actual count.

---

## Implementation Steps

1. **Create `src/segqc/empty.py`**:
   - Define `CheckResult` as a `dataclasses.dataclass(frozen=True)` with:
     `is_empty: bool`, `reasons: tuple[str, ...]`, `foreground_voxels: int`,
     `label_count: int`.
   - Define `check_empty(seg_img: nib.Nifti1Image, config: HeuristicConfig) -> CheckResult`:
     - Extract the label array from `seg_img` via `np.asanyarray(seg_img.dataobj)`.
     - Compute `foreground_mask = arr != 0`, `foreground_voxels = int(foreground_mask.sum())`.
     - Compute `label_count = int(np.unique(arr[foreground_mask]).size)` if there is
       foreground; else `label_count = 0`.
     - Check conditions in order, accumulating reason strings:
       1. If `foreground_voxels == 0`: append `"No foreground voxels found (empty label map)."`.
       2. Else if `config.min_foreground_voxels > 0` and
          `foreground_voxels < config.min_foreground_voxels`: append a string such as
          `f"Foreground voxel count {foreground_voxels} is below the minimum {config.min_foreground_voxels}."`.
       3. If `config.min_label_count > 0` and `label_count < config.min_label_count`:
          append a string such as
          `f"Distinct label count {label_count} is below the minimum {config.min_label_count}."`.
     - Return `CheckResult(is_empty=bool(reasons), reasons=tuple(reasons), ...)`.

2. **Expose in `src/segqc/__init__.py`**: optionally add `check_empty` to
   `__all__` (not required but convenient).

3. **Write `tests/test_007_empty_detection.py`** covering all ten ACs plus
   adversarial/edge cases.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Fixtures:** use `empty_labelmap`, `labelled_blocks`, and `anisotropic` from
  `conftest.py` for the canonical cases. Build ad-hoc `make_labelmap` volumes
  from `synthetic.py` for threshold boundary tests.
- **Test module:** `tests/test_007_empty_detection.py`.
- **Coverage:** all ten ACs; adversarial / edge cases including threshold
  boundaries (exactly at threshold, one below, one above), single-voxel maps,
  single-label maps, large voxel counts, negative/zero threshold values.
- **No external services, no I/O (beyond fixtures), no network.**

---

## Dependencies

- **Upstream:**
  - Item 001 (package skeleton) — ✅ merged.
  - Item 002 (synthetic NIfTI fixtures) — ✅ merged.
  - Item 003 (NIfTI I/O loader) — ✅ merged; provides the NiBabel image type.
  - Item 005 (heuristic config, `HeuristicConfig`) — ✅ merged; the
    `min_foreground_voxels` and `min_label_count` fields are ready.
- **Parallel:**
  - Item 008 (QC verdict model) — can be developed in parallel; this item does
    not import from `segqc.verdict`.
- **Downstream:**
  - Item 010 (pipeline wiring) — calls `check_empty` and converts its output
    into `Verdict` objects.

---

## Decisions & Trade-offs

1. **No runtime imports beyond stdlib, NumPy, and NiBabel.** `scipy`,
   `skimage`, and `segqc.verdict` are excluded. The function returns plain
   strings rather than `Reason` objects so item 010 can wire the output into
   the verdict model without a circular dependency.

2. **`CheckResult` is a frozen dataclass.** Immutable after construction,
   consistent with the `@dataclass(frozen=True)` style used in `segqc.io`,
   `segqc.labels`, and `segqc.config`.

3. **`reasons` field is `tuple[str, ...]`, not `list[str]`.** Tuples are
   immutable and hash cleanly, which is consistent with the frozen dataclass
   contract and simplifies equality checks in tests.

4. **Array extracted via `np.asanyarray(seg_img.dataobj)`.** Avoids an
   unnecessary data copy for memory-mapped images; the original array is never
   modified.

5. **`label_count = 0` when the map is completely empty.** Avoids calling
   `np.unique` on an empty boolean slice; gives a well-defined zero rather than
   raising or returning an unexpected value.

6. **Foreground-threshold check uses `else if` (not `if`).** When the map is
   completely empty the "no foreground" reason already fires; the
   `min_foreground_voxels` condition is only evaluated for non-empty maps to
   avoid double-counting. The `min_label_count` condition is independent and
   runs for all maps so `min_label_count=1` fires on an empty map (0 labels < 1).

7. **NiBabel is a lazy import inside `check_empty`.** The module-level code
   imports only stdlib + NumPy so the module can be imported cheaply in
   contexts where NiBabel is not yet needed. This also avoids a top-level
   circular-import risk if the package is ever restructured.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + NiBabel; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]` (no new deps expected).
- **Environment variables / secrets:** none.
- **Ports:** none.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` exits 0.
- [ ] **Tests pass:** `python -m pytest tests/test_007_empty_detection.py` is green.
- [ ] **Import check:**
  ```python
  from segqc.empty import check_empty, CheckResult
  print('ok')
  ```
- [ ] **Smoke test:**
  ```python
  from synthetic import empty_case, labelled_blocks_case
  from segqc.config import default_config
  from segqc.empty import check_empty

  cfg = default_config()
  empty = empty_case()
  result = check_empty(empty.seg_img, cfg)
  assert result.is_empty, "empty map should fail"

  populated = labelled_blocks_case()
  result2 = check_empty(populated.seg_img, cfg)
  assert not result2.is_empty, "populated map should pass"
  print('smoke ok')
  ```

### Expected Outcomes

- `check_empty` on an all-zero label map returns `is_empty=True` with ≥1 reason.
- `check_empty` on a populated map with default config returns `is_empty=False`.
- Threshold settings correctly alter the verdict as specified.
- `pytest tests/test_007_empty_detection.py` reports 0 failures.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 1 **"Empty / near-empty detection…"** deliverable from 📋 → ✅
  (mark 🚧 while in progress).
- Per `CLAUDE.md`: work on branch `aide/007-empty-detection`, `git pull --rebase`
  before editing `progress.md`, keep edits scoped to this item's rows, and
  direct-merge (no PR required) once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 007` to
implement this work item.
