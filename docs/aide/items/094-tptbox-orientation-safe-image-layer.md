# Item 094 — TPTBox-backed orientation-safe image layer

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6)
> **Queue:** [`../queue/queue-013.md`](../queue/queue-013.md) · Item 094 *(third
> of five; lands after 093/095 so TPTBox installs directly into the final
> Python-3.11+/numpy-range environment)*
> **Objectives:** G2 (a real segmenter's output may arrive in any orientation;
> today's loader silently trusts array storage order, which item 017's
> motivating bug class shows is unsafe), G6 (portable execution — no new
> platform/GPU requirement; TPTBox is CPU-only)
> **Suggested branch:** `aide/094-tptbox-orientation-safe-image-layer`

---

## Description

Add **TPTBox 0.7.5** (pinned exactly — confirmed with the user twice this
session; do **not** substitute `0.6.1`, which lacks 8 `NII` methods FACET
will use, including `dilate_msk_euclid`/`erode_msk_euclid`/`from_numpy`/
`to_stl`, and every upstream fix since) as a required core dependency, and
back `segfacet.io`'s `load_volume`/`load_case` with TPTBox's `NII` class:
`NII.load` for reading, `.reorient(axcodes_to=...)` for orientation
normalisation, and `.zoom`/`.affine` in place of the hand-rolled
`_spacing_from_affine` (`io.py:109-116`, a thin wrapper over
`nib.affines.voxel_sizes` that never normalises axis order — it just reports
spacing for whatever order the file happens to store). `Volume`/`Case` keep
their existing public field shape (`data`, `spacing`, `affine`, `path` /
`scan`, `seg`, `label_inventory`, `foreground_voxels`), so no other module
needs to change — per the confirmed scope decision, this item touches only
`segfacet.io`; the ~21 other modules that import `nibabel` directly stay
untouched (tracked as a follow-on gap, not migrated here).

### The orientation-normalisation target — derived, not guessed

`segfacet.features.geometry`'s own docstring already documents the
convention every downstream rule/feature depends on:

```
Image face          Anatomical flag
x == 0               touches_inferior
x == shape[0]-1       touches_superior
y == 0               touches_left
y == shape[1]-1       touches_right
z == 0               touches_anterior
z == shape[2]-1       touches_posterior
```

...captioned **"a pragmatic convention for tools that work in any orientation
without a reliable RAS header; downstream callers that have orientation
information can remap as needed."** This item is exactly that remap's
prerequisite, but deliberately does **not** perform the remap itself (that
would mean auditing/changing item 011's face-mapping table and every rule
that consumes it — explicitly out of scope, matching the confirmed
"io.py only" decision). Instead, this item normalises every loaded volume's
**array storage order** to a single, consistent target — **RAS** (nibabel's
own commonly-used default; `nib.affines.voxel_sizes`/`aff2axcodes` on the
existing synthetic fixtures' diagonal `diag([sx, sy, sz, 1])` affine already
resolves to `('R', 'A', 'S')`, i.e. `reorient(axcodes_to=("R","A","S"))` is
an **identity transform** on every existing synthetic fixture) — so that:

- **Two real files of the same anatomy stored in different orientations
  (RAS, LPS, or any other) now load to the *same* array layout**, which is
  the actual orientation-safety property a real segmenter's output needs
  (today's loader has no such guarantee — it trusts raw storage order).
- **Every existing synthetic fixture, golden snapshot, and downstream
  module is unaffected**, because reorienting an already-RAS affine to RAS
  is a no-op (axis permutation/flip, not interpolation) — this item changes
  *which* raw byte layout an arbitrarily-oriented **real** file is read as,
  not the meaning of the "pragmatic convention" table above, and not any
  currently-passing fixture's array.
- **The "pragmatic convention" table's anatomical mislabelling for real,
  non-synthetic data survives this item unchanged** — it is a pre-existing,
  explicitly-documented simplification, not introduced by this item, and
  fixing it (making `touches_superior` etc. genuinely correspond to true
  anatomy for arbitrarily-oriented real input) is a separate, larger
  follow-on this item does not attempt. Recorded as a `gap` insight (see
  Decisions).

**What this item is not:**
- **Not a migration of the ~21 other nibabel-importing modules.** Confirmed
  scope: `segfacet.io` only.
- **Not a voxel-grid resampling/interpolation change.** TPTBox's
  `rescale`/`resample_from_to` are exposed by the underlying `NII` object
  this item wires in, but this item does **not** call them by default —
  `load_volume` reorients (an exact axis permutation/flip, no
  interpolation) and reads spacing/affine; it does not resample anisotropic
  data to an isotropic grid. That is a separate, future concern (voxel
  values would change, affecting every feature — far riskier than this
  item's scope).
- **Not a fix to the geometry.py face-mapping table's anatomical
  correctness for real data.** See above.
- **Not the numpy<2/`spineps`-conda-env installation bootstrap.** TPTBox is
  declared as a normal `pyproject.toml` dependency here, which resolves
  fine (numpy>=2.0 automatically, per TPTBox's own declared marker) for a
  plain `pip install -e .`/CI install. **Separately**, this item documents
  (as a doc, not CI automation) the wheel-build-plus-`--no-deps` bootstrap
  needed to install FACET+TPTBox into an **existing** numpy<2 environment
  (e.g. the real `spineps` conda env: Python 3.11.15, numpy 1.26.4, monai
  1.4.0, TPTBox 0.6.1 → to be upgraded to 0.7.5) — recorded because item 097
  and any future real-SPINEPS validation will need to run FACET *inside*
  that exact environment.

## Acceptance Criteria

- [ ] **AC1: TPTBox is a pinned core dependency.** `pyproject.toml`'s
  `dependencies` includes `"tptbox==0.7.5"` (exact pin, not a loose bound).
- [ ] **AC2: `constraints.txt` is regenerated with TPTBox's transitive
  dependencies included.** Following the file's documented recipe on the
  item-095 Python-3.11 floor, now including TPTBox + its transitives
  (SimpleITK, scikit-learn, connected-components-3d, fill-voids, pynrrd,
  dill, requests, matplotlib per the queue's dependency-footprint note);
  `pip install -e .[dev] -c constraints.txt` succeeds end-to-end.
- [ ] **AC3: existing synthetic fixtures load byte-identically.** For every
  fixture the current suite loads via `load_volume`/`load_case` (the
  Stage-5 corpus, Stage 8's intensity fixtures, etc.), `Volume.data`,
  `.spacing`, and `.affine` are **unchanged** (byte-for-byte / exact-value)
  before and after this item — confirming `reorient(axcodes_to=("R","A","S"))`
  is a genuine no-op on the existing `('R','A','S')`-resolving diagonal
  affines.
- [ ] **AC4: a differently-oriented file of the same anatomy loads to an
  equivalent array.** A new fixture pair — the same synthetic label map
  saved twice, once with the existing diagonal RAS-ish affine and once with
  an axis-permuted-and/or-flipped array + a correspondingly transformed
  affine encoding an **LPS** (or another non-RAS) orientation of the *same*
  physical volume — both load via `load_volume` to array data that is
  **equal after accounting for the documented reorientation** (i.e. the
  same physical voxel ends up at the same array index in both loads); their
  `.spacing`/`.affine` describe the same physical geometry. This is the
  concrete test that orientation-safety is real, not merely "does not
  crash."
- [ ] **AC5: `Volume`/`Case`'s public shape is unchanged.** The dataclass
  field names/types in `io.py` are identical to before this item; no
  downstream module (outside `io.py` itself) requires any edit to keep
  passing.
- [ ] **AC6: `FacetInputError` semantics are preserved.** Every existing
  `load_volume`/`load_case` error path (missing file, directory-not-file,
  unreadable NIfTI, shape mismatch, incompatible affine) still raises
  `FacetInputError` with an equivalent, actionable message — TPTBox's own
  exceptions (if any) are caught and wrapped, never leaked raw.
- [ ] **AC7: a full `segfacet run` on a synthetic fixture is unaffected.**
  End-to-end CLI output (JSON + human report) for a committed fixture is
  unchanged (within the existing `reports_close` numeric tolerance) after
  this item — the migration is behaviour-preserving on every currently-
  exercised input.
- [ ] **AC8: the numpy<2 install bootstrap is documented.** A new doc
  (e.g. `docs/tptbox-install-numpy1.md`) records: why the bypass is needed
  (TPTBox 0.7.5's declared `numpy>=2.0` marker for `python>=3.11` is not a
  real code requirement — verified this session via TPTBox's own test suite
  passing under numpy 1.26.4 with zero numpy-2-only/removed API usage found
  by an AST scan), the exact procedure (build a wheel from the pinned
  `tptbox==0.7.5` checkout, install with `pip install --no-deps
  <wheel>`, record the wheel's sha256), and that this is needed only when
  installing into an **existing** numpy<2 environment (e.g. the real
  `spineps` conda env) — a plain `pip install -e .[dev]` (this item's own
  CI/dev path) needs no such workaround, since it resolves numpy>=2.0
  cleanly with nothing else present to conflict with.

## Assumptions

Clarify mode was forced to `interactive` for this batch. The three
substantive ambiguities raised were answered by the user (recorded here per
convention); the reorientation-target derivation below was resolved by
reading `segfacet/features/geometry.py`'s own documented convention rather
than asked, since it has a single defensible, code-grounded answer:

- **Scope is `segfacet.io` only** (confirmed with the user) — the other
  ~21 nibabel-importing modules are a tracked follow-on, not migrated here.
- **TPTBox becomes a required core dependency**, not an optional extra
  (confirmed with the user) — this is the new default orientation-safe
  path, not an accelerator like `pyradiomics`/`cupy`.
- **TPTBox is pinned to exactly `0.7.5`, never `0.6.1`** — confirmed twice
  this session (the user explicitly reiterated "stick to TPTBox 0.7.5,
  don't downgrade" after the numpy-marker finding). `0.6.1` is missing 8
  `NII` methods and every fix landed since.
- **The reorientation target is `("R", "A", "S")`** (RAS), derived from
  `geometry.py`'s own documented face-mapping table and the existing
  synthetic fixtures' diagonal affine (which already resolves to RAS via
  `nib.affines.voxel_sizes`/standard axcode detection). This is a
  **conservative** choice: it achieves real cross-orientation consistency
  for arbitrarily-oriented real input (AC4) while being a byte-identical
  no-op for every currently-passing fixture/golden (AC3) and requiring no
  change to `geometry.py`'s face-mapping table or any rule that consumes
  it. **Pinned as a load-bearing decision, not a default the builder should
  vary**: choosing a different target (e.g. one that would make
  `touches_superior` etc. genuinely anatomically correct) would silently
  break every existing fixture and rule and is explicitly the larger,
  out-of-scope follow-on named in the Description.
- **No voxel resampling/interpolation is introduced.** `rescale`/
  `resample_from_to` are exposed on the underlying TPTBox `NII` object this
  item wires in (a future item may call them), but `load_volume` itself
  does not invoke them — only `reorient` (axis permutation/flip) and
  spacing/affine extraction (`zoom`/`.affine`) are used, keeping voxel
  *values* unchanged for every input this item's ACs exercise.
- **The numpy<2 conda-env bootstrap (AC8) is documentation only, not CI
  automation** — CI has no pre-existing monai-populated environment to
  install into; the real target is the workstation's `spineps` conda env,
  outside CI's reach (mirroring how the Docker/GPU capabilities are
  verified manually/on real hardware elsewhere in this project, per
  `CLAUDE.md`'s Environment-Gated Capability Verification pattern) — though
  TPTBox itself is a required (not gated) dependency, so no new
  `[validation]` profile or verification-table row is added for TPTBox
  *presence*; the doc exists purely to make the numpy<2 install procedure
  reproducible when someone needs it.
- **Dependencies 093 (label convention, expected ✅) and 095 (Python
  3.11+/numpy range, expected ✅) — both merged by the time this item
  lands**, per the queue's stated execution order (093 → 095 → 094).

## Implementation Steps

All under `source_dir = src/segfacet`, confined to `io.py` plus packaging
files.

1. **`pyproject.toml`**: add `"tptbox==0.7.5"` to `dependencies`.
2. **`constraints.txt`**: regenerate (same recipe as item 095, now
   including TPTBox's transitive footprint).
3. **`src/segfacet/io.py`**:
   - Import TPTBox's `NII` (lazily, inside the function bodies that need
     it, matching this module's existing style of eager top-level imports
     for its current deps — confirm TPTBox's own import cost before
     deciding eager-vs-lazy; the module docstring's "Heavy imports deferred"
     convention used elsewhere in the CLI is the relevant precedent if
     TPTBox proves expensive to import).
   - Replace `load_volume`'s `nib.load(path_str)` + `_spacing_from_affine`
     path with `NII.load(path_str, seg=integer_labels)` (or the equivalent
     TPTBox call for scan vs. label-map loading), `.reorient(axcodes_to=
     ("R", "A", "S"))`, then read `.zoom` for spacing and `.affine` for the
     4x4 matrix, and the underlying array via `.get_array()`/
     `.get_seg_array()` as appropriate for `integer_labels`.
   - Preserve every existing behaviour: standalone-copy-not-a-view
     enforcement (`data.flags.owndata` check), the `FacetInputError`
     wrapping discipline (path-does-not-exist, is-a-directory, failed-read,
     failed-voxel-read), and the exact same dtype handling
     (`integer_labels=True` → header-native/rounded-to-int64;
     `integer_labels=False` → float64).
   - `load_case`'s shape/affine-compatibility checks (`_AFFINE_ATOL`/
     `_AFFINE_RTOL`) stay as they are — they compare two already-reoriented
     `Volume`s, so the tolerance logic is unaffected.
   - Remove `_spacing_from_affine` once nothing calls it (or keep it as a
     private fallback only if TPTBox's `NII.load` cannot be coaxed to
     handle every existing edge case cleanly — a decision for the builder
     to record if reality diverges from this plan).
4. **`docs/tptbox-install-numpy1.md`** (new): the AC8 bootstrap doc.
5. **Do not** touch any other module. `features/`, `heuristics/`,
   `reference/`, `eval/`, `synth/`, `cli.py` are all unmodified by this
   item.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_094_tptbox_image_layer.py`.
- **AC1/AC2**: metadata assertions (`pyproject.toml` contains the pin;
  `constraints.txt` contains `TPTBox`/its transitives) mirroring item 095's
  `test_095_env_migration.py` style.
- **AC3**: parametrise over the existing committed fixture set (or a
  representative subset) — load each via the new `load_volume`, assert
  `np.array_equal(data_before, data_after)` and exact `spacing`/`affine`
  equality against a pre-migration snapshot (captured from the current
  passing suite before this item's code change, e.g. via a fixture-diff
  test or by re-running the *old* loader in the test setup for comparison).
- **AC4**: build the LPS-vs-RAS fixture pair described in the AC itself (a
  small helper, not a committed binary fixture, mirroring how other Stage-
  17-adjacent tests hand-build inputs) — assert the two loads' arrays and
  affines describe the same physical volume.
- **AC5**: a `dataclasses.fields()` comparison of `Volume`/`Case` against
  the pre-item field set (name + type), or simply that all existing
  `io.py`-consuming tests pass unmodified.
- **AC6**: re-run every existing `FacetInputError` test in
  `tests/test_io.py` unmodified (or with only import-path changes) — all
  must still raise the same exception type with an equivalent message.
- **AC7**: run the full Stage-5 golden/regression suite; assert no output
  diverges beyond `reports_close`'s existing numeric tolerance.
- **AC8**: no automated test (documentation-only); the validator manually
  confirms the doc's procedure is internally consistent (e.g. by dry-running
  the wheel-build command locally, if feasible in the validation
  environment) and, if a `spineps`-like conda env is available, that
  following the doc's steps actually installs FACET successfully — else
  records the honest limitation.
- **Adversarial / edge cases:**
  - A NIfTI whose affine already exactly matches `("R","A","S")` but with a
    **non-diagonal** (rotated) direction-cosine matrix (still resolving to
    RAS axcodes, but not axis-aligned) — confirm `reorient` still reports
    RAS and does not crash (TPTBox's own reorientation handles rotation
    matrices; FACET only needs the axcode result, not axis-alignment).
  - A label map with `integer_labels=True` still round-trips through
    TPTBox's segmentation-array path without float-casting label values
    (mirrors the existing `test_io.py` dtype-preservation test).
  - Missing-file / directory / corrupt-file error paths (AC6) still exit
    via `FacetInputError`, not a raw TPTBox exception leaking through.

## Validation

Beyond the tests, run a full `segfacet run` on a committed synthetic
fixture and diff the JSON/human report against the pre-item output
(`reports_close` tolerance) — the observable end-to-end behaviour a user
would notice, not just unit-level equality. If a real, non-RAS-oriented
NIfTI is available in the working environment (even outside the committed
corpus — e.g. from the `spineps` workstation), an ad hoc load-and-inspect
pass (confirm `.spacing`/`.affine` look physically sensible, confirm no
crash) is a valuable additional check but not required for this item's ACs,
which are already testable on synthetic fixtures alone.

## Dependencies

- **Item 093 (expected ✅) — no code dependency**, sequenced before per
  queue order.
- **Item 095 (expected ✅) — hard dependency.** TPTBox installs into the
  Python 3.11+/numpy-range environment item 095 establishes; installing
  TPTBox against the old Python 3.9 floor was never attempted.
- **Downstream: item 097** (stage validation) depends on this item's
  numpy<2 bootstrap doc (AC8) and orientation-safety guarantee (AC4) to
  exercise a real SPINEPS-output round-trip.

## Decisions & Trade-offs

- **TPTBox's actual API matched the spec's description closely**, with a few
  concrete details discovered by inspecting the installed 0.7.5 package
  (import name is `TPTBox`, not `tptbox`; the pip distribution name
  `tptbox==0.7.5` is unaffected):
  - `NII.load(path, seg: bool, c_val=None)` — `seg` is a required positional
    bool (not a keyword defaulting to `False`), so `load_volume` passes
    `seg=integer_labels` explicitly for both call sites.
  - `NII.reorient(axcodes_to=..., inplace=False)` returns a **new** `NII`
    (default `inplace=False`), so `nii = nii.reorient(axcodes_to=...)` is the
    correct call shape (no separate mutation step needed).
  - `.get_seg_array()` returns TPTBox's own dtype choice (it coerces to the
    smallest unsigned integer type that fits the label values, e.g.
    `uint8`), not `int64`. `load_volume` still casts the result to `int64`
    itself (same as the pre-migration `_spacing_from_affine`-era code did
    from nibabel's native dtype) so `Volume.data.dtype` for
    `integer_labels=True` is unchanged from before this item (confirmed by
    AC3's snapshot, which records `int64`).
  - `.get_array()` (the intensity path) preserves the file's original
    on-disk float dtype (e.g. `float32`) rather than always producing
    `float64` the way nibabel's `get_fdata(dtype=np.float64)` did.
    `load_volume` explicitly casts to `float64` after the TPTBox read to
    preserve this module's documented `Volume.data` contract for scans.
  - Malformed/corrupt files raise `nibabel.filebasedimages.ImageFileError`
    from inside `NII.load` (TPTBox delegates to nibabel under the hood for
    file parsing) — already caught by the existing broad `except Exception`
    wrap into `FacetInputError`, so no TPTBox-specific exception type needed
    adding to the catch clause.
- **`_spacing_from_affine` was removed** (not kept as a fallback) — TPTBox's
  `.zoom` property covers every case the old `nib.affines.voxel_sizes`-based
  helper did, and no edge case requiring the old path was found.
- **`nibabel` is no longer imported in `io.py`** (the module's only nibabel
  usage was `nib.load` and `nib.affines.voxel_sizes`, both replaced). The
  package remains a core dependency (`tests/test_094_*` asserts it stays in
  `pyproject.toml`'s `dependencies`) since ~21 other modules still import it
  directly (explicitly out of scope for this item; see Description).
- **`constraints.txt` regeneration surfaced one categorisation nuance**:
  `matplotlib`, previously included only via the `dev` extra, is now also a
  direct transitive of TPTBox's own core dependencies — it is documented in
  the regenerated file's header comment rather than silently reclassified.
- **AC8's wheel**: TPTBox 0.7.5 ships as a pure-Python wheel
  (`tptbox-0.7.5-py3-none-any.whl`, no compiled extensions), so there is no
  numpy ABI baked into the artifact — `pip download tptbox==0.7.5 --no-deps`
  (equivalent to a from-source wheel build for this pinned release) plus
  `pip install --no-deps <wheel>` is sufficient and was used as the
  documented procedure in `docs/tptbox-install-numpy1.md`, rather than
  requiring an actual `git clone` + `python -m build` round-trip.

One forward-looking note captured as an `insights.md` `gap` entry (not this
item's own scope): `geometry.py`'s face-mapping table's anatomical
mislabelling for real, arbitrarily-oriented data (documented in its own
docstring as a "pragmatic convention... downstream callers that have
orientation information can remap as needed") is now genuinely *remappable*,
since this item guarantees a consistent RAS array layout — but the remap
itself (making `touches_superior` etc. anatomically correct, and auditing
every rule that consumes them) is deliberately not attempted here.
