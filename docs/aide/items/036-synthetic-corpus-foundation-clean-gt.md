# Item 036 — Synthetic-corpus foundation: clean-GT spine builder & perturbation framework

> **Created:** 2026-07-08 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (G7)
> **Queue:** [`../queue/queue-004.md`](../queue/queue-004.md) · Item 036 *(critical-path foundation for the whole queue)*
> **Objectives:** G7 (evaluable & regression-testable — the reproducible,
> seeded generator every corpus case is built from), and the synthetic-corpus
> half of G2 (the positive-control clean GT + the failure-injection framework)
> **Suggested branch:** `aide/036-synthetic-corpus-foundation-clean-gt`

---

## Description

Establish the **deterministic foundation** that every Stage 5 operator (037–039),
the committed fixture corpus (040), the regression suite (041), and the golden
snapshots (042) build on. Two deliverables, one new package `src/segqc/synth/`:

1. **A parametric clean-GT spine builder** (`build_clean_spine`) that constructs
   a multi-vertebra **instance label map** — ordered, plausibly-spaced,
   single-component vertebra bodies stacked along a smooth spinal curve, with
   configurable level span, voxel spacing, and affine — such that the **real
   Stage 4 pipeline** (`segqc.pipeline.run_qc` under the bundled default config)
   judges it **`pass` with zero findings**. This is the positive-control base
   every perturbation starts from: if the clean GT does not pass cleanly, no
   injected-failure expectation downstream is trustworthy.

2. **A perturbation framework** — a `Perturbation` abstraction + registry with a
   precise, seeded `apply(labelmap, seed) -> PerturbationResult` contract, where
   the result carries the perturbed label map and an **`Expectation`** recording
   the intended §6 failure mode, the Stage 4 rule(s) expected to fire, the
   expected offending labels, and the expected verdict. Ships the reference
   **identity / no-op** perturbation. Perturbations are seeded and reproducible:
   the same operator with the same seed and input produces a **byte-identical**
   output array.

This item must **nail the exact interface/contract** — function signatures, the
`Perturbation` base class, the registry API, the `Expectation` and
`PerturbationResult` data shapes — precisely enough that the three independent
operator-family items (037, 038, 039) implement against it with **no further
clarification**.

### Why the clean-GT builder is the hard part (not the item-002 cubes)

The existing `tests/synthetic.py` helpers (item 002) build tiny geometric cubes
that deliberately do **not** satisfy the anatomical Stage 4 thresholds — item
035's own Decisions section records that the 4×4×4 mm `labelled_blocks` fixture
now scores `flagged-for-review` once the rule engine is wired, because a 64 mm³
cube is far below the lumbar `min_volume_mm3` of 8000. The clean-GT builder is a
**new** artefact whose whole job is to pass *every* default rule at once. Reading
the shipped `src/segqc/default_config.yaml` and the rule modules, that means the
default output must simultaneously satisfy:

| Rule (item) | What the clean GT must guarantee |
|-------------|----------------------------------|
| `bounds` (027) | each body's `physical_volume_mm3` + `extent_{x,y,z}_mm` inside its **level group's** default range (e.g. lumbar: 8000–120000 mm³; extents 20–120 mm x/y, 15–100 mm z) |
| `fragmentation` (028) | one connected component per label → `fragmentation_index == 1.0`, no island < 50 voxels |
| `coverage` (029) | no missing **interior** level within the present span → `relationships.missing_levels == []` |
| `sequence` (030) | ascending labels in ascending anatomical order → `is_continuous`, `out_of_order_labels == []` |
| `border` (031) | no **in-plane** face contact and no unexpected end contact → all six `touches_*` flags `False` |
| `overlap` (032) | disjoint bodies → `detect_overlaps(...) == []` |
| `mislabel` (033) | centroids on a smooth curve → every fitted-spline `offset_mm < 15.0`; centroids monotonic → `non_monotonic_pairs == []` |

### The transitional-vertebra trap (a hard constraint on the default span)

`relationships.missing_levels` is derived from a `CANONICAL_ORDER` slice
(`segqc/features/relationships.py`), and `CANONICAL_ORDER` interleaves the
**transitional** vertebrae T13 (between T12 and L1) and L6 (between L5 and S).
A span that crosses the T12→L1 junction therefore reports **T13 as a missing
interior level**, and `coverage` fires — the control would not be clean. The
builder's default span must be a **canonically-contiguous run with no interior
transitional vertebra**: a pure-lumbar, pure-thoracic, or pure-cervical run is
safe. The default is **lumbar L1–L5** (labels 20–24); the span is configurable
but must stay within this contiguity constraint (see Assumptions).

### Scope boundary — what this item is **not**

- **Not the failure operators.** Only the framework + the reference identity
  operator ship here. Fragment/fuse/islands (037), remove-level/crop/overlap
  (038), and displace/relabel/sequence-break (039) are separate items that
  register their operators against this framework.
- **Not the committed corpus, manifest, regression suite, or golden files**
  (040/041/042). No NIfTI fixtures are committed here; the builder produces
  in-memory `Nifti1Image`s.
- **Not new rules, extractors, or config.** It consumes the already-merged
  `run_qc` / `run_rules` / `build_features_block` / extractors / bundled config
  unchanged; it adds no `Rule` and edits no `heuristics`/`features`/`config` code.
- **Not a change to `segqc run` behaviour.** The CLI is invoked as-is (item 035)
  in the positive-control test; no CLI code changes.

---

## Public interface (the contract 037–039 implement against)

New package `src/segqc/synth/`. `synth/__init__.py` re-exports the whole surface.

### Clean-GT builder (`synth/clean_gt.py`)

```python
DEFAULT_LEVELS: tuple[str, ...] = ("L1", "L2", "L3", "L4", "L5")

@dataclass(frozen=True)
class CleanSpine:
    scan_img: nib.Nifti1Image          # matching intensity scan (same shape/affine)
    seg_img: nib.Nifti1Image           # the instance label map (integer dtype)
    labels: tuple[int, ...]            # present integer labels, ascending
    level_names: tuple[str, ...]       # anatomical names, parallel to `labels`
    spacing: tuple[float, float, float]
    shape: tuple[int, int, int]
    voxel_counts: dict[int, int]       # {label: n_voxels}

def build_clean_spine(
    *,
    levels: Sequence[str] = DEFAULT_LEVELS,
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
    convention: LabelConvention | None = None,   # default: LabelConvention.default()
    curve_amplitude_mm: float = <small default>, # gentle lateral arc; 0.0 ⇒ straight
) -> CleanSpine: ...
```

- **Axis convention** (from `segqc/features/geometry.py`): image axis 0 is
  superior–inferior (the stacking axis), axis 1 is left–right, axis 2 is
  anterior–posterior. Bodies are stacked along axis 0.
- Each body is a solid rectangular block sized in **physical mm** (converted to
  voxel counts via `spacing`) so its volume/extents land inside its level
  group's default `bounds` **regardless of spacing** (anisotropy-correct).
- Bodies are separated by a gap along axis 0 (disjoint ⇒ no overlap, single
  component each) and inset from **all six faces** by a margin (no border
  contact). The volume `shape` is computed to fit the whole stack + curve
  amplitude + margins.
- Centroids follow a **smooth, gently-curved path** (default a shallow arc in
  the left–right / anterior–posterior plane as a function of axis-0 position;
  `curve_amplitude_mm=0.0` gives a straight line). The path is chosen so the
  fitted-spline offset of every body stays well below the default
  `mislabel.max_offset_mm` (15 mm) and the centroid order is monotonic.
- **Deterministic**: content is computed, never random — building twice with the
  same arguments yields byte-identical arrays.

### Perturbation framework (`synth/perturbation.py`)

```python
CLEAN_CONTROL_MODE: int = 0    # sentinel §6 "mode" for the clean control (no failure)

# Canonical §6 failure-mode names, keyed 0..8 (0 == clean control). Shared so
# every operator names its mode identically.
FAILURE_MODE_NAMES: dict[int, str] = {
    0: "clean control (no failure)",
    1: "label not aligned with the vertebra it names",
    2: "over-/under-segmentation (fused / fragmented)",
    3: "disconnected components / rogue islands",
    4: "semantic mislabelling (wrong identification)",
    5: "not all vertebrae segmented (missing levels)",
    6: "partial vertebra at the image border",
    7: "non-continuous label sequence",
    8: "overlapping segments",
}

@dataclass(frozen=True)
class Expectation:
    failure_mode: int                    # 0..8 (0 == clean control)
    failure_mode_name: str               # human name (usually FAILURE_MODE_NAMES[failure_mode])
    expected_rule_ids: frozenset[str]    # Stage 4 rule_id(s) expected among the fired findings
    expected_labels: frozenset[int]      # expected offending labels (empty for case-level / clean)
    expected_verdict: str                # one of "pass" / "flagged-for-review" / "fail"
    detail: str = ""                     # optional free-text note
    def to_dict(self) -> dict: ...       # JSON-ready: rule_ids & labels as sorted lists

class PerturbationResult(NamedTuple):
    labelmap: nib.Nifti1Image            # perturbed label map (affine/spacing preserved)
    expectation: Expectation

class Perturbation(abc.ABC):
    name: str                            # unique registry key (class attribute)
    @abc.abstractmethod
    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult: ...

# Registry (mirrors segqc.heuristics.rule): _PERTURBATIONS keyed by name, exposed
# for test snapshot/restore. register_perturbation registers the CLASS (operators
# are parameterised via their constructor; apply takes only labelmap + seed).
def register_perturbation(cls: type[Perturbation]) -> type[Perturbation]: ...
def get_perturbation(name: str) -> type[Perturbation]: ...      # KeyError if unknown
def iter_perturbations() -> Iterator[type[Perturbation]]: ...   # sorted by name
def perturbation_names() -> list[str]: ...                      # sorted

@register_perturbation
class IdentityPerturbation(Perturbation):
    name = "identity"
    # returns a copy whose array equals the input, with a clean-control Expectation
```

- **`labelmap` carries spacing/affine.** The queue's "`apply(labelmap,
  spacing/affine, seed)`" is satisfied by passing a `Nifti1Image` — operators
  read spacing via `labelmap.header.get_zooms()[:3]` and the affine via
  `labelmap.affine`, exactly as the Stage 2/3 extractors do.
- **Seeded & reproducible.** Every stochastic operator MUST derive all randomness
  solely from `numpy.random.default_rng(seed)` (never the global RNG). Same seed
  + same input ⇒ byte-identical output array. Identity ignores the seed (it is
  trivially deterministic) but still accepts it to honour the signature.
- **Non-mutating.** `apply` never modifies the caller's input array/image; it
  returns a fresh `Nifti1Image`.

---

## Acceptance Criteria

_One test per criterion. Group A = clean-GT builder, Group B = perturbation
framework, Group C = determinism & immutability._

### A. Clean-GT spine builder

- [ ] **AC1: The builder returns a well-formed `CleanSpine`.**
      `build_clean_spine()` returns a `CleanSpine` whose `scan_img` and `seg_img`
      are `nibabel.Nifti1Image`s of **equal shape** sharing one affine; whose
      `labels == (20, 21, 22, 23, 24)` with parallel `level_names ==
      ("L1","L2","L3","L4","L5")` (default convention); and whose `voxel_counts`
      keys are exactly those five labels.

- [ ] **AC2: The clean GT passes the real pipeline with zero findings (positive
      control).** `run_qc(clean.seg_img, bundled_default_config())` returns a
      `CaseResult` with `findings == ()` **and** `verdict.overall ==
      Severity.PASS`.

- [ ] **AC3: The clean GT passes end-to-end through `segqc run`.** Writing
      `clean.scan_img` / `clean.seg_img` to disk (via `synthetic.write_nifti`)
      and calling `segqc.cli.main(["run","--scan",<scan>,"--seg",<seg>,"--out",
      <dir>])` returns **0**; the emitted `<dir>/segqc_report.json` parses to a
      dict with `"verdict" == "pass"` and an empty `"findings"` array.

- [ ] **AC4: The builder honours anisotropic spacing (physical volumes correct).**
      `build_clean_spine(spacing=(1.0, 1.0, 3.0))` still yields `findings == ()`
      and `Severity.PASS` through `run_qc`; and for every label,
      `compute_label_geometry(seg_img, label).physical_volume_mm3 ==
      voxel_counts[label] * (1.0 * 1.0 * 3.0)`.

- [ ] **AC5: The level span is parametric and stays clean.**
      `build_clean_spine(levels=["T5","T6","T7","T8","T9","T10"])` returns
      `labels == (12,13,14,15,16,17)` and, through `run_qc` under the bundled
      default config, yields `findings == ()` and `Severity.PASS`.

- [ ] **AC6: `bounds` cannot fire — every body is within its level group's
      bounds.** For each label in the default clean GT, `compute_label_geometry`
      reports `physical_volume_mm3` and `extent_{x,y,z}_mm` all inside the
      `DEFAULT_BOUNDS["lumbar"]` `[min, max]` ranges.

- [ ] **AC7: `fragmentation` cannot fire — one component per label.** For each
      label in the default clean GT, `compute_components(seg_img, label, cfg)`
      reports a single connected component with `fragmentation_index == 1.0` and
      no island below `island_min_voxels`.

- [ ] **AC8: `border` cannot fire — no face contact.** For each label in the
      default clean GT, all six `compute_label_geometry` `touches_*` flags are
      `False` (every body is inset from the FOV by a margin).

- [ ] **AC9: `overlap` cannot fire — bodies are disjoint.** `detect_overlaps`
      over the default clean GT's per-label masks returns `[]` (no two labels
      share a voxel).

- [ ] **AC10: `coverage` and `sequence` cannot fire — contiguous, in-order
      span.** For the default clean GT, `compute_spine_relationships` over the
      ordered centroids reports `missing_levels == []`, `is_continuous is True`,
      and `out_of_order_labels == []`.

- [ ] **AC11: `mislabel` cannot fire — smooth curve, monotonic order.** For the
      default clean GT, every per-vertebra fitted-spline `offset_mm` is `< 15.0`
      and `compute_monotonic_consistency(...).non_monotonic_pairs == []`.

### B. Perturbation framework

- [ ] **AC12: `Perturbation` is an abstract base.** Instantiating a `Perturbation`
      subclass that does not implement `apply` raises `TypeError`; a concrete
      subclass declares a class-attribute `name` and an `apply(self, labelmap,
      seed)` method.

- [ ] **AC13: `Expectation` has the pinned shape.** `Expectation` is a frozen
      dataclass carrying `failure_mode: int`, `failure_mode_name: str`,
      `expected_rule_ids: frozenset[str]`, `expected_labels: frozenset[int]`, and
      `expected_verdict: str`; an instance can be constructed with those fields
      and compares equal to an identically-constructed one.

- [ ] **AC14: `Expectation.to_dict()` is JSON-ready.** For an `Expectation` with
      `expected_rule_ids == {"overlap"}` and `expected_labels == {21, 20}`,
      `to_dict()` returns a dict whose `expected_rule_ids == ["overlap"]` and
      `expected_labels == [20, 21]` (both **sorted lists**) and whose scalar
      fields (`failure_mode`, `failure_mode_name`, `expected_verdict`) match
      verbatim; the dict is accepted by `json.dumps`.

- [ ] **AC15: `PerturbationResult` is an unpackable named pair.** A
      `PerturbationResult(labelmap=img, expectation=exp)` unpacks as
      `lm, ex = result` to `(img, exp)` **and** exposes `result.labelmap is img`
      and `result.expectation is exp`.

- [ ] **AC16: The registry registers and looks up by name.**
      `register_perturbation` registers a `Perturbation` subclass under its `name`;
      `get_perturbation("identity")` returns the `IdentityPerturbation` **class**;
      `"identity"` appears in `perturbation_names()` and the class appears in
      `iter_perturbations()`, which is sorted by `name`.

- [ ] **AC17: Duplicate and unknown names are rejected.** Registering a second
      class whose `name` is already registered raises `ValueError`;
      `get_perturbation("does-not-exist")` raises `KeyError`.

- [ ] **AC18: `IdentityPerturbation` is registered under `"identity"`.** Importing
      `segqc.synth` makes `get_perturbation("identity")` return
      `IdentityPerturbation`.

- [ ] **AC19: Identity returns an array equal to its input.** For the default
      clean GT, `IdentityPerturbation().apply(clean.seg_img, seed=0).labelmap` has
      a data array `np.array_equal(...) is True` against `clean.seg_img`'s array,
      and its affine equals the input affine (`np.array_equal`), and its
      `get_zooms()[:3]` equals the input spacing.

- [ ] **AC20: Identity's expectation is the well-formed clean control.** That same
      call's `expectation` has `failure_mode == CLEAN_CONTROL_MODE` (`== 0`),
      `failure_mode_name == FAILURE_MODE_NAMES[0]`, `expected_rule_ids ==
      frozenset()`, `expected_labels == frozenset()`, and `expected_verdict ==
      "pass"`.

- [ ] **AC21: Identity's expectation is consistent with the pipeline.** Running
      the identity-perturbed clean GT through `run_qc(result.labelmap,
      bundled_default_config())` yields `findings == ()` and
      `verdict.overall.label == result.expectation.expected_verdict` (`"pass"`) —
      the expectation truthfully predicts the pipeline outcome.

### C. Determinism & immutability (the reproducibility contract 037–039 inherit)

- [ ] **AC22: Perturbation output is reproducible (same seed + input ⇒ identical
      array).** Two `IdentityPerturbation().apply(clean.seg_img, seed=7)` calls
      return output arrays that are `np.array_equal`.

- [ ] **AC23: `apply` does not mutate the caller's input.** The data array of the
      `seg_img` passed to `apply` is unchanged after the call (equal to a copy
      taken before it).

- [ ] **AC24: The builder is deterministic.** Two `build_clean_spine()` calls
      (same arguments) produce `seg_img` arrays that are `np.array_equal` and
      affines that are `np.array_equal`.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **The module lives in `src/segqc/synth/` (production `source_dir`), not under
  `tests/`.** The queue offers either; `src/segqc/synth/` is chosen because
  (a) under the AIDE role split the **builder** owns `source_dir` and the
  **test-writer** owns `tests/`, so a reusable framework that items 037–042 all
  *import* belongs where the builder can author it and every later item can
  import it uniformly; (b) item 040's "one-command regeneration path" is cleanest
  as an importable, packaged module; (c) the generator is part of G7 (evaluable &
  regression-testable), a stated tool objective. The validator surfaces this
  placement at the queue boundary. If a reviewer prefers a `tests/`-level package
  the move is mechanical, but the build/validate split favours `src/segqc/synth/`.

- **The default clean-GT span is lumbar L1–L5 (labels 20–24).** This is a
  canonically-contiguous run with **no interior transitional vertebra**, so
  `relationships.missing_levels` is empty and `coverage` stays silent. Any
  configured `levels` must likewise be a contiguous run within a single group
  (pure cervical / thoracic / lumbar) — crossing the T12→L1 or L5→S junction
  interleaves T13 / L6 in `CANONICAL_ORDER` and would (correctly) trip the
  missing-interior-level check. This constraint is documented on
  `build_clean_spine`; the builder does not attempt to "fix" a span that violates
  it. This is the most material design default under clarify=`assume`.

- **The positive control is asserted primarily through `run_qc`, and additionally
  end-to-end through `segqc run`.** `run_qc` (item 035) is the honest "full Stage 4
  pipeline" (extract features → run every rule → aggregate), so AC2 asserts
  `findings == ()` + `PASS` directly on it. AC3 additionally drives the real CLI on
  written NIfTI files (needing a matching scan, which the builder supplies) so the
  extract→rules→report→exit-code path is genuinely exercised. Pinned interface:
  `run_qc(seg_img, config) -> (CaseResult, dict)` with `CaseResult.findings:
  tuple[Finding, ...]` and `CaseResult.verdict.overall: Severity`. If these
  diverged the builder/validator hands back.

- **Vertebra bodies are sized in physical mm and stacked along image axis 0.**
  Geometry (item 011) maps axis 0 → superior/inferior, axis 1 → left/right,
  axis 2 → anterior/posterior. Sizing bodies in mm (converted to voxels via
  `spacing`) is what makes the control pass `bounds` under **any** spacing and is
  what makes AC4's anisotropy assertion hold. Bodies are inset from all faces by a
  margin (AC8) and separated by a gap (AC7/AC9).

- **A smooth curve keeps `mislabel` silent because the fitted spline reproduces
  it.** A low-order smooth centroid path (default a shallow arc; `0.0` gives a
  straight line) is reproduced by `fit_centroid_spline` (item 017) with near-zero
  perpendicular offsets, so every `offset_mm` sits well under the 15 mm default
  and the centroid order is monotonic (AC11). Amplitude is chosen small enough
  that no body's inset/margin is violated.

- **Perturbations are parameterised classes; the registry stores the class.**
  Unlike stateless zero-arg `Rule`s (which the item-026 registry instantiates at
  registration), operators need per-instance parameters (target level, island
  size, shift distance), so `apply` takes only `(labelmap, seed)` and any
  operator config is a constructor argument. `register_perturbation` therefore
  stores the **class** and `get_perturbation` returns it for the caller to
  instantiate. This is a deliberate divergence from the rule registry, chosen so
  037–039 can express `FragmentPerturbation(target_level="L3").apply(seg, seed)`.

- **`labelmap` is a `Nifti1Image`, carrying spacing/affine.** The queue's
  "`apply(labelmap, spacing/affine, seed)`" is satisfied by the image object
  (spacing = `header.get_zooms()`, affine = `.affine`), matching how every Stage
  2/3 extractor already takes `seg_img`. `PerturbationResult` is a `NamedTuple`
  so it both unpacks as the literal `(perturbed_labelmap, expectation)` tuple the
  queue specifies and offers named `.labelmap` / `.expectation` access.

- **`Expectation` records rule ids in addition to the §6 mode.** The queue lists
  "intended §6 failure mode, expected offending labels, expected verdict"; the
  downstream regression suite (041) must also assert **which heuristic fired**, so
  `expected_rule_ids: frozenset[str]` is included now (empty for the clean
  control). `failure_mode == 0` (`CLEAN_CONTROL_MODE`) is the sentinel for "no
  failure", named via `FAILURE_MODE_NAMES`.

- **Only the identity operator ships here; no stochastic reference operator.**
  The reproducibility contract (same seed ⇒ byte-identical) is documented on the
  abstraction and exercised mechanically via identity (AC22). A genuinely
  stochastic operator would necessarily be one of 037–039's failure operators;
  adding one here would step on their scope. Each of 037–039 asserts the seeded
  contract for its own operators against this framework.

- **The builder emits a matching scan.** `run_qc` needs only `seg_img`, but the
  CLI (`segqc run`, AC3) needs a scan with the same shape/compatible affine
  (`load_case` validates this), so `CleanSpine` carries a `scan_img` (a
  deterministic intensity volume, mirroring `synthetic.make_scan`).

## Implementation Steps

Intended code path in `src/segqc/synth/` (new package). No edits to existing
production modules.

1. **Create `src/segqc/synth/__init__.py`** re-exporting the public surface (the
   builder symbols and the framework symbols listed above) and importing
   `synth.perturbation` so `IdentityPerturbation` self-registers on
   `import segqc.synth` (mirroring how `segqc.heuristics.__init__` imports its
   rule modules).

2. **Create `src/segqc/synth/clean_gt.py`:**
   - Define `DEFAULT_LEVELS = ("L1","L2","L3","L4","L5")` and the frozen
     `CleanSpine` dataclass.
   - `build_clean_spine(*, levels=DEFAULT_LEVELS, spacing=(1,1,3? no →1,1,1),
     convention=None, curve_amplitude_mm=<small>)`:
     - Resolve `convention = convention or LabelConvention.default()`; map each
       level name → integer label via `convention.value_of`; raise
       `SegQCInputError` on an unknown level name or a span that is not a
       contiguous single-group run (guard the transitional-vertebra trap).
     - Choose a per-body physical size (mm) comfortably inside the level group's
       `DEFAULT_BOUNDS` (e.g. lumbar ≈ 24 × 30 × 25 mm → volume ≈ 18000 mm³);
       convert to voxel counts per axis via `spacing` (round up, ensure ≥ the
       group's `min_extent`).
     - Lay out bodies along axis 0 with a fixed inter-body gap and an all-faces
       margin; compute centroids on a shallow arc (`curve_amplitude_mm`) in the
       (axis-1, axis-2) plane; compute the volume `shape` to fit stack + margins +
       amplitude.
     - Paint solid blocks into a zero `uint16`/`int` array (reuse the
       `make_labelmap`-style block-fill idiom); build `seg_img` and a matching
       gradient `scan_img` via `affine_from_spacing(spacing)`.
     - Populate and return `CleanSpine` (labels ascending, parallel level_names,
       voxel_counts, spacing, shape).
   - Keep it purely computed (no RNG) so it is deterministic (AC24).

3. **Create `src/segqc/synth/perturbation.py`:**
   - Define `CLEAN_CONTROL_MODE = 0` and `FAILURE_MODE_NAMES` (0..8).
   - Define the frozen `Expectation` dataclass with `to_dict()` (sorted lists for
     `expected_rule_ids` / `expected_labels`; scalars verbatim).
   - Define `PerturbationResult(NamedTuple)` with `labelmap`, `expectation`.
   - Define `Perturbation(abc.ABC)` with class attr `name` and abstract `apply`.
   - Define the registry: module-level `_PERTURBATIONS: dict[str, type]` (exposed
     for test snapshot/restore, mirroring `heuristics.rule._RULES`),
     `register_perturbation` (rejects missing/duplicate `name` with `ValueError`),
     `get_perturbation` (`KeyError` on unknown), `iter_perturbations` (sorted by
     name), `perturbation_names`.
   - Define and `@register_perturbation` the `IdentityPerturbation` (`name =
     "identity"`): `apply` returns `PerturbationResult(labelmap=<copy of input,
     same affine>, expectation=Expectation(failure_mode=CLEAN_CONTROL_MODE,
     failure_mode_name=FAILURE_MODE_NAMES[0], expected_rule_ids=frozenset(),
     expected_labels=frozenset(), expected_verdict="pass"))`. Copy the array
     (`np.array(...)`) so the input is never mutated and the output is a distinct
     but equal array.
   - Provide a documented `seeded_rng(seed) -> numpy.random.Generator` helper
     (`= np.random.default_rng(seed)`) so every future operator has one obvious,
     enforced way to obtain reproducible randomness.

4. **Do not** edit any existing module under `src/segqc/` (no rule, extractor,
   config, CLI, or report changes). The package `src/segqc/synth/` ships as
   package data automatically (Hatch already packages `src/segqc`).

## Testing Strategy

- **Framework:** `pytest`. New modules: `tests/test_036_clean_gt.py` and
  `tests/test_036_perturbation_framework.py`.
- **Registry isolation:** snapshot/restore `segqc.synth.perturbation._PERTURBATIONS`
  around any test that registers a throwaway `Perturbation` subclass (mirroring
  the item-026/032 `_RULES` snapshot idiom), so duplicate-name and iteration
  tests do not leak across tests.
- **Clean-GT builder (AC1–AC11):** build the default spine; assert the
  `CleanSpine` shape/labels/level_names (AC1); drive `run_qc(clean.seg_img,
  bundled_default_config())` for `findings == ()` + `PASS` (AC2); write NIfTI via
  `synthetic.write_nifti` and call `segqc.cli.main([...])` in a `tmp_path` out
  dir, parse the JSON for `verdict == "pass"` / empty `findings` / exit 0 (AC3);
  rebuild with `spacing=(1,1,3)` for the anisotropy + physical-volume checks
  (AC4); rebuild with a thoracic span (AC5); assert the per-rule structural
  guarantees directly against the extractors — `compute_label_geometry` for
  bounds + border (AC6, AC8), `compute_components` for single-component (AC7),
  `detect_overlaps` for disjointness (AC9), `compute_spine_relationships` for
  coverage/sequence (AC10), and `fit_centroid_spline` + `compute_spline_offsets` +
  `compute_monotonic_consistency` for mislabel (AC11).
- **Perturbation framework (AC12–AC21):** abstract-base enforcement via a
  deliberately-incomplete subclass (AC12); `Expectation` construction/equality and
  `to_dict()` sorted-list shape + `json.dumps` round-trip (AC13, AC14);
  `PerturbationResult` unpack + attribute access (AC15); register a dummy operator
  and assert `get_perturbation` / `perturbation_names` / `iter_perturbations`
  ordering (AC16), duplicate `ValueError` + unknown `KeyError` (AC17); identity
  registered under `"identity"` (AC18); identity array-equality + affine/spacing
  preservation (AC19); identity expectation fields (AC20); and identity→`run_qc`
  consistency (AC21).
- **Determinism & immutability (AC22–AC24):** two identity `apply` calls at the
  same seed → `np.array_equal` (AC22); deep-copy the input array before `apply`,
  assert equality afterwards (AC23); two `build_clean_spine()` calls →
  `np.array_equal` seg arrays + affines (AC24).
- **Adversarial / edge cases:** an unknown level name and a
  transitional-crossing span (e.g. `["T12","L1"]`) to `build_clean_spine` raise a
  clear error (do **not** silently emit a coverage-flagging map); a single-level
  span (`["L3"]`) still builds (Stage 3 is skipped for < 2 labels) though it is
  not the intended positive control; identity `apply` with two **different** seeds
  still yields equal arrays (identity is seed-independent); `Expectation` with an
  invalid `expected_verdict` string is still constructible (the framework does not
  validate verdict strings — the manifest/regression items do), documented so
  037–039 pass real Severity labels.

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 035** — `segqc.pipeline.run_qc` / `extract_feature_record`, the
    bundled `default_config.yaml`, and `segqc.config.bundled_default_config`: the
    full-pipeline entry point and default config the positive control runs
    against.
  - **Item 034** — `segqc.aggregate` (`CaseResult`, `build_case_result`): the
    `findings` / `verdict` shape AC2/AC21 read.
  - **Items 026–033** — the rule engine + seven rule families and the bundled
    thresholds the clean GT must satisfy simultaneously (the per-rule structural
    guarantees AC6–AC11 mirror these rules' inputs).
  - **Items 011–020 / 016 / 022** — the Stage 2/3 extractors and
    `build_features_block` the structural-guarantee tests call directly
    (`compute_label_geometry`, `compute_components`, `compute_centroid`,
    `compute_spine_relationships`, `detect_overlaps`, `fit_centroid_spline`,
    `compute_spline_offsets`, `compute_monotonic_consistency`).
  - **Item 010 / 035** — `segqc.cli.main` (`segqc run`) the AC3 end-to-end
    positive control invokes unchanged.
  - **Item 004** — `segqc.labels` (`LabelConvention`, `CANONICAL_ORDER`,
    `DEFAULT_LABEL_MAP`): level-name↔label resolution and the canonical order
    whose transitional-vertebra interleaving pins the span constraint.
  - **Item 002** — `tests/synthetic.py` (`write_nifti`, `affine_from_spacing`,
    `make_scan` idioms) reused by the tests and mirrored by the builder.
  - **Item 003** — `segqc.io` (`SegQCInputError`) for the builder's span-guard
    error type.
- **Downstream (depend on this item):**
  - **Items 037 / 038 / 039** — the three operator families register their
    `Perturbation` subclasses against this framework and start every perturbation
    from `build_clean_spine`'s output; they implement directly against the
    `Perturbation` / `Expectation` / `PerturbationResult` contract pinned here.
  - **Item 040** — the committed fixture corpus + manifest materialises operators
    over the clean GT and serialises `Expectation.to_dict()`.
  - **Items 041 / 042** — the regression suite and golden snapshots consume the
    clean-GT positive control and the per-case expectations.

This item integrates only already-merged interfaces and adds one new package; it
is the critical-path foundation gating the rest of queue-004.

## Decisions & Trade-offs

To be updated during implementation.
