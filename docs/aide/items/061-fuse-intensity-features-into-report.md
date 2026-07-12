# Item 061 — Fuse intensity features into the JSON report & per-case feature table

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 061 *(the fusion half of Stage-8 deliverable 2; consumes 059's `LabelIntensity` (and, via a seam, 060's radiomics `extended`); feeds 065's `segqc run` wiring)*
> **Objectives:** G2 (fuses the image-based feature family into the report machinery so intensity/radiomics features are *visible* alongside geometry — the report half of Stage-8 deliverable 2), G7 (deterministic, schema-validated, byte-reproducible, regression-testable). Realises the vision's §5.2 "Image-based" feature family surfacing in the QC output.
> **Suggested branch:** `aide/061-fuse-intensity-features-into-the`

---

## Description

Wire the Stage-8 **image-based feature family** (item 059's per-label first-order
intensity statistics, and item 060's optional PyRadiomics `extended` features when
available) into the existing **report machinery** as a new, optional, top-level
JSON block and its human-report rendering — **deliverable 2, the fusion half**.

Concretely, this item adds:

1. A **pure assembly utility** `build_image_features_block(...)` in
   `src/segqc/feature_report.py` (alongside `build_features_block`) that takes
   **already-computed** per-label intensity results (a `Mapping[int,
   LabelIntensity]` from item 059) plus, via an **optional seam**, per-label
   `extended` radiomics maps + a backend/availability provenance marker (from item
   060), and folds them into a JSON-ready **`image_features` block**.
2. An optional `image_features` parameter on `serialize_report` /
   `serialize_report_json` (`src/segqc/report.py`), added **exactly** as item 046
   added `reference_delta` — default `None` ⇒ the key is omitted and every prior
   report shape (including the item-042 golden snapshots) is byte-identical.
3. A new top-level optional `image_features` property + definitions in
   `src/segqc/report_schema_v0.json`, so the block validates in-report (the
   top-level object is `additionalProperties: false`, so the property must be
   declared).
4. An optional `image_features` argument on `human_report.render_feature_table`
   that appends a deterministic **per-case intensity section** when a block is
   supplied — default `None` ⇒ the rendered table is byte-identical to today.

The `image_features` block is a **sibling** of `features` / `findings` /
`reference_delta` (not nested inside `features`), keyed per label under its own
`per_label`; it carries block-level provenance (`backend`, `radiomics_available`)
and an `available` flag so a run with **no scan / no intensity backend** can emit
an explicit `available: false` sentinel block rather than an ambiguous omission.

### Scope boundary — what this item is **not**

- **Not the `segqc run` / CLI wiring.** Loading the scan alongside the
  segmentation, adding a CLI flag / config knob to enable the intensity path, and
  calling the extractor inside a real pipeline run are **item 065's** job (the
  Stage-8 integration + acceptance closure), mirroring how item 046 supplied the
  computation + `serialize_report` seam and item 049 did the `segqc run` wiring.
  This item adds **no** CLI flag, **no** `config.py` change, **no** new pipeline
  entry point (`pipeline.py` is untouched), and does **not** load any scan.
- **Not new feature extraction.** It reads the already-computed dataclasses from
  items 059/060 and serialises them; it computes no intensity statistics itself
  and imports neither NumPy nor NiBabel into the assembly/render path.
- **Not a heuristic / rule.** The implausible-intensity heuristic (deliverable 2's
  rule half) is **item 062**; this item adds no `@register_rule`, no finding, and
  does not touch `segqc.heuristics.*` / verdict aggregation.
- **Not a reference/delta change.** Extending reference distributions with
  intensity (063) and the intensity delta rule (064) are separate items.
- **Not a change to the geometric `features` block.** `build_features_block`,
  `FEATURES_VERSION`, and the `features` schema stay byte-identical; intensity is
  a *new* sibling block, not a mutation of the existing one.

---

## Public interface (the contract 065 builds on)

New/extended surface (all under `source_dir = src/segqc/`). Private helpers are
the builder's choice; the **exported surface** below is the contract 065 wires.

```python
# --- src/segqc/feature_report.py (new) ---
IMAGE_FEATURES_VERSION: str = "1.0"        # version discriminator for the image_features block

def label_intensity_to_dict(li: LabelIntensity) -> dict:
    """Pure: one LabelIntensity -> its JSON-ready first_order dict.
    All 15 fields emitted; None statistic fields serialise to JSON null (never NaN)."""

def build_image_features_block(
    intensity: Mapping[int, "LabelIntensity"],   # item 059's per-label first-order results
    *,
    extended: "Optional[Mapping[int, Mapping[str, float]]]" = None,  # item 060 radiomics extended, per label
    backend: str = "builtin",                    # block-level provenance: "builtin" | "pyradiomics"
    radiomics_available: bool = False,           # whether PyRadiomics produced any extended features
    available: bool = True,                      # False -> unavailable sentinel (no scan/backend)
    image_features_version: str = IMAGE_FEATURES_VERSION,
) -> dict:
    """Pure: fold already-computed per-label intensity (and optional radiomics
    `extended`) results into a JSON-ready `image_features` block. per_label is
    assembled in ascending integer-label order. Inputs are never mutated. When
    `available=False`, per_label is `{}` (the explicit 'intensity unavailable'
    sentinel). No file I/O, no wall clock, no NumPy/NiBabel import."""

# --- src/segqc/report.py (extended) ---
def serialize_report(verdict, case_id, config, features=None, findings=None,
                     reference_delta=None, image_features=None) -> dict: ...
def serialize_report_json(verdict, case_id, config, indent=2, features=None,
                          findings=None, reference_delta=None, image_features=None) -> str: ...

# --- src/segqc/human_report.py (extended) ---
def render_feature_table(features_block: dict, image_features: "dict | None" = None) -> str: ...
```

**Canonical JSON shape** produced by `build_image_features_block` (the top-level
`image_features` block item 065 embeds in the report):

```json
{
  "image_features_version": "1.0",
  "available": true,
  "radiomics_available": false,
  "backend": "builtin",
  "per_label": {
    "20": {
      "label": 20,
      "first_order": {
        "voxel_count": 512,
        "n_nonfinite_excluded": 0,
        "mean": 210.5, "median": 208.0, "std": 33.1,
        "min": 120.0, "max": 305.0,
        "p05": 150.0, "p25": 188.0, "p50": 208.0, "p75": 233.0, "p95": 280.0,
        "range": 185.0, "iqr": 45.0, "entropy": 3.42
      },
      "extended": {}
    }
  }
}
```

`first_order` mirrors `LabelIntensity` exactly: `voxel_count` /
`n_nonfinite_excluded` are integers; the other 13 statistic fields are
number-or-`null` (JSON `null` for the sentinel record). `extended` is a flat
`{name: number}` map — `{}` on the builtin (first-order-only) path, and the item
060 radiomics feature map (e.g. `{"original_glcm_Contrast": 1.5}`) when supplied.
An `available: false` block has `per_label: {}`.

---

## Acceptance Criteria

_One focused test per criterion, atomic and directly observable. Tests hand-build
`LabelIntensity` dataclasses (frozen; import from `segqc.features.intensity`) with
known field values so every serialised number is hand-checkable — no scan fixture
is required for the unit tests._

- [ ] **AC1: `build_image_features_block` produces a well-formed block.** Given a
      `Mapping[int, LabelIntensity]` with two populated labels, the returned dict
      has `image_features_version == IMAGE_FEATURES_VERSION` (`"1.0"`),
      `available is True`, `radiomics_available is False`, `backend == "builtin"`,
      and `per_label` keyed by `str(label)` with exactly one entry per input label.

- [ ] **AC2: per-label `first_order` mirrors `LabelIntensity` field-for-field.**
      For a label whose `LabelIntensity` carries populated statistics, the entry's
      `first_order` dict contains all 15 fields (`voxel_count`,
      `n_nonfinite_excluded`, `mean`, `median`, `std`, `min`, `max`, `p05`, `p25`,
      `p50`, `p75`, `p95`, `range`, `iqr`, `entropy`) with values equal to the
      dataclass fields, and the entry carries `label` equal to the integer label.

- [ ] **AC3: `None` statistics serialise to JSON `null`, never `NaN`.** For a
      sentinel `LabelIntensity` (`voxel_count == 0`, every statistic field
      `None`), the entry's `first_order` has each of the 13 statistic fields
      `None` while `voxel_count`/`n_nonfinite_excluded` stay integers, and
      `json.dumps(block, allow_nan=False)` succeeds (no `NaN`/`Infinity` token).

- [ ] **AC4: the optional `extended` seam folds radiomics features in.** Passing
      `extended={20: {"original_glcm_Contrast": 1.5}}` places that mapping under
      label 20's `extended`; a label present in `intensity` but absent from
      `extended` gets `extended == {}`; and when `extended=None` (default) every
      entry's `extended == {}`.

- [ ] **AC5: block-level provenance echoes the arguments.** With
      `backend="pyradiomics", radiomics_available=True` the block carries
      `backend == "pyradiomics"` and `radiomics_available is True`; the defaults
      yield `backend == "builtin"` and `radiomics_available is False`.

- [ ] **AC6: `available=False` yields the unavailable sentinel block.**
      `build_image_features_block(intensity, available=False)` returns a block with
      `available is False` and `per_label == {}` (intensity marked unavailable, not
      omitted-ambiguously), and that block still validates against the schema
      (AC10 machinery).

- [ ] **AC7: assembly is deterministic, ordered, and non-mutating.** Two calls on
      the same inputs return **equal** dicts and byte-identical
      `json.dumps(block, sort_keys=True)`; `list(block["per_label"].keys())` is in
      ascending integer-label order regardless of input mapping order; and neither
      the `intensity` mapping/dataclasses nor the `extended` mapping is mutated.

- [ ] **AC8: `serialize_report` gains an optional `image_features` parameter.**
      `serialize_report(verdict, case_id, config,
      image_features=build_image_features_block(...))` returns without raising and
      the returned report carries the block verbatim under the top-level
      `image_features` key (validated together with the rest of the report).

- [ ] **AC9: omitting `image_features` preserves the prior report shape.**
      `serialize_report(verdict, case_id, config)` — and calls passing only
      `features` / `findings` / `reference_delta` — emit **no** `image_features`
      key, byte-identical to the pre-item output (so item-042 goldens and the
      reference-less path are unaffected). The report `schema_version` stays
      `"0.1"`.

- [ ] **AC10: the schema validates a well-formed block and rejects a malformed
      one.** A well-formed `image_features` block validates in-report (AC8); a
      block carrying an unknown extra top-level key (e.g. `"bogus": 1`), or a
      per-label entry missing a required `first_order` field, raises
      `jsonschema.ValidationError` (the `additionalProperties: false` /
      required-field constraints are honoured).

- [ ] **AC11: `serialize_report_json` forwards `image_features` and round-trips.**
      `json.loads(serialize_report_json(verdict, case_id, config,
      image_features=block))` equals `serialize_report(verdict, case_id, config,
      image_features=block)`, and the string is parseable (no `NaN`/`Infinity`).

- [ ] **AC12: `render_feature_table` renders an intensity section when given a
      block, and is unchanged when not.** `render_feature_table(features_block,
      image_features=block)` returns a string containing a per-case intensity
      section that lists each present label (ascending) with its
      mean/median/std/min/max/entropy formatted; `render_feature_table(features_block)`
      (default `image_features=None`) returns a string **byte-identical** to the
      pre-item render for the same `features_block`.

- [ ] **AC13: the rendered intensity section is null-safe and deterministic.** A
      sentinel (unavailable) label renders an explicit placeholder (e.g. `(n/a)`)
      rather than the text `None`/`nan`; an `available: false` block renders an
      explicit "(unavailable)"/"(none)" line; and the section contains no raw
      Python `None`, `nan`, tuple, `frozenset`, or class-name text, with labels in
      ascending integer order regardless of `per_label` insertion order.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete contract is recorded here for audit; several
**pin an interface** item 065 must honour (hand back if reality diverged).

- **Fusion = a new top-level `image_features` block (sibling of `features`), not a
  mutation of the geometric `features` block — deliberately diverging from the
  literal queue wording.** The queue-007 item-061 text says "add them to the
  versioned JSON `features` block … bumping the schema/`features` version." This
  spec instead adds intensity as a **separate optional top-level block**, exactly
  as item 046 chose a top-level `reference_delta` sibling over nesting inside
  `features`. Reasoning: (a) it decouples this item from the frozen
  `labelFeatures` schema (`additionalProperties: false`, fixed `required` set) and
  from `build_features_block`, so the geometric path and its `FEATURES_VERSION`
  stay byte-identical; (b) a `None`-default `serialize_report(image_features=…)`
  parameter guarantees the item-042 golden snapshots stay byte-identical, matching
  CLAUDE.md's byte-reproducible-fixture contract, whereas threading intensity
  through the shared `features` assembler risks the goldens; (c) it mirrors the
  established Stage-2/4/6 pattern for optional blocks (`features`/`findings`/
  `reference_delta` — each a top-level property + a `serialize_report` parameter).
  **The validator should surface this divergence** so a reviewer who truly wants
  intensity *inside* `features` can redirect. Either way the observable milestone —
  "intensity features fused into the JSON report and the per-case feature table" —
  holds.

- **This item owns the report seam only; `segqc run` wiring is deferred to 065.**
  The queue text says "extend the feature aggregation (`segqc/features/__init__.py`)
  so `segqc run` computes intensity features when a scan is present." This spec
  reads that as **065's** responsibility (the Stage-8 integration item that "wires
  extractor → fusion → heuristics → reference-delta into `segqc run`"), because (a)
  the queue's own sequencing note makes 061 depend only on 059 and be **mutually
  independent** of 060/062/063 — impossible if 061 also owned the `segqc run` scan
  loading that 065 explicitly owns; and (b) it mirrors item 046 (computation +
  seam) vs item 049 (run wiring). This item therefore delivers the pure
  fusion utility + serialiser seam + schema + renderer, and leaves `pipeline.py`,
  `cli.py`, `config.py`, `default_config.yaml`, and `features/__init__.py`
  **untouched**. **Pinned for 065:** the run wiring computes
  `compute_intensity_features(scan_img, seg_img)` (059) — optionally
  `compute_radiomics_features(...)` (060) — then calls
  `build_image_features_block(intensity, extended=…, backend=…,
  radiomics_available=…)` and passes the result to
  `serialize_report(image_features=…)` and `render_feature_table(…,
  image_features=…)`. Hand back if that wiring cannot be expressed against this
  surface.

- **Assembly consumes item 059's `LabelIntensity`; item 060's radiomics enter via
  an optional seam (so 061 stays independent of 060).** `build_image_features_block`
  imports only `LabelIntensity` (from `segqc.features.intensity`) for typing and
  reads the frozen dataclass's 15 fields; the higher-order radiomics features enter
  as plain `extended` dicts (item 060's `LabelRadiomics.extended`) plus a
  `backend`/`radiomics_available` provenance pair, rather than importing
  `segqc.features.radiomics`. This honours the queue's "060 ‖ 061 … mutually
  independent" sequencing and keeps the assembler free of the optional-PyRadiomics
  import path, while still letting 065 fold 060's normalised output in unchanged.

- **`first_order` mirrors `LabelIntensity` verbatim (15 fields; `None` → JSON
  `null`).** All fields are emitted so the block is self-describing; `None`
  statistics (059's sentinel policy for absent/empty/all-non-finite labels)
  serialise to JSON `null` — never `float('nan')` — preserving 059's determinism
  discipline (`NaN != NaN` would break byte-stability) and keeping the artifact
  JSON-valid under `allow_nan=False`.

- **Block-level `available` flag realises the queue's "marked unavailable rather
  than omitted-ambiguously."** Two distinct absences are represented: (i) intensity
  **not attempted** (geometric-only run) ⇒ `serialize_report(image_features=None)`
  omits the key entirely (default, back-compatible); (ii) intensity attempted but
  **no scan / no data** ⇒ 065 calls `build_image_features_block(..., available=False)`
  to emit an explicit `available: false, per_label: {}` sentinel. This item
  provides both mechanisms; 065 chooses which applies at run time.

- **Block name `image_features` / version `IMAGE_FEATURES_VERSION = "1.0"`.** The
  name distinguishes the image-based family from the geometric `features` block and
  encompasses both first-order intensity and optional radiomics `extended`. The
  block carries its own version discriminator (like `features_version` /
  `reference_delta_version`), independent of the report `schema_version` (stays
  `"0.1"`); a future radiomics-shape change bumps only `IMAGE_FEATURES_VERSION`.

- **Render extends `render_feature_table` via an optional `image_features` param
  (default `None`).** Rendering the block into the human-readable "per-case feature
  table" is a **pure** extension of `human_report.render_feature_table` (which
  already consumes the plain features-block dict and stays stdlib-only). Default
  `None` ⇒ byte-identical output, mirroring how `render_human_report(findings=…)`
  was added (item 035). The section formats numbers with the existing `_fmt_num`
  helper and renders `None`/unavailable entries as an explicit placeholder — no
  raw Python internals leak (item-010 discipline). Wiring this renderer into
  `cli._handle_run`'s written `segqc_report.txt` is 065's job.

- **Dependencies 059 and 060 are present in the tree (merged on the Stage-8 line).**
  `segqc.features.intensity.LabelIntensity` / `compute_intensity_features` (059)
  and `segqc.features.radiomics.LabelRadiomics` / `compute_radiomics_features`
  (060, whose `.extended` feeds the seam) are confirmed present in
  `src/segqc/features/`. This item imports only `LabelIntensity`; if that surface
  changed, hand back. (Item 058's intensity-bearing fixtures are **not** required
  for this item's unit tests, which hand-build `LabelIntensity` dataclasses
  directly; 065's acceptance suite uses them end-to-end.)

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): new functions in
`src/segqc/feature_report.py`; an optional parameter added to `serialize_report` /
`serialize_report_json` in `src/segqc/report.py`; a top-level property + three
definitions in `src/segqc/report_schema_v0.json`; an optional parameter added to
`render_feature_table` in `src/segqc/human_report.py`. **No** edits to
`pipeline.py`, `cli.py`, `config.py`, `default_config.yaml`, `features/__init__.py`,
`build_features_block`, or items 059/060's modules.

1. **`src/segqc/feature_report.py` — assembly utility.**
   - Add `IMAGE_FEATURES_VERSION = "1.0"` and extend `__all__` with
     `IMAGE_FEATURES_VERSION`, `label_intensity_to_dict`,
     `build_image_features_block`.
   - Add a `TYPE_CHECKING` import of `LabelIntensity` from
     `segqc.features.intensity` (annotation only — keep the module heavy-import-free,
     consistent with the existing dataclass-typing convention).
   - `label_intensity_to_dict(li)` → a fresh dict with all 15 `LabelIntensity`
     fields in a fixed order (`voxel_count`, `n_nonfinite_excluded`, then `mean`,
     `median`, `std`, `min`, `max`, `p05`, `p25`, `p50`, `p75`, `p95`, `range`,
     `iqr`, `entropy`). Copy values verbatim (`None` stays `None`; floats stay
     floats).
   - `build_image_features_block(intensity, *, extended=None, backend="builtin",
     radiomics_available=False, available=True, image_features_version=
     IMAGE_FEATURES_VERSION)`:
     - When `available is False`: return `{"image_features_version": …,
       "available": False, "radiomics_available": bool(radiomics_available),
       "backend": backend, "per_label": {}}`.
     - Else build `per_label` in ascending integer-label order: for each
       `label` in `sorted(intensity)`, entry `{"label": int(label),
       "first_order": label_intensity_to_dict(intensity[label]), "extended":
       dict(extended.get(label, {})) if extended else {}}`. Shallow-copy the
       per-label `extended` map so the block never aliases the caller's dict.
     - Return the fresh block; never mutate `intensity`/`extended`.

2. **`src/segqc/report.py` — serialiser seam.** Add an optional
   `image_features: "dict | None" = None` parameter to `serialize_report`
   (embed under `report["image_features"]` before `jsonschema.validate` when
   non-`None`) and forward it from `serialize_report_json`, mirroring the existing
   `reference_delta` handling exactly (docstrings updated to mention the block).

3. **`src/segqc/report_schema_v0.json` — schema extension.** Add a top-level
   optional `image_features` property → `#/definitions/imageFeatures`. Define:
   - `imageFeatures`: object, `additionalProperties: false`, required
     `image_features_version` (string, minLength 1), `available` (boolean),
     `radiomics_available` (boolean), `backend` (string), `per_label` (object,
     `additionalProperties` → `imageLabelFeatures`).
   - `imageLabelFeatures`: object, `additionalProperties: false`, required
     `label` (integer), `first_order` (`firstOrderIntensity`), `extended`
     (object, `additionalProperties: {"type": "number"}`).
   - `firstOrderIntensity`: object, `additionalProperties: false`, required all 15
     fields; `voxel_count`/`n_nonfinite_excluded` → `{"type": "integer"}`; the
     other 13 → `{"type": ["number", "null"]}`.
   - Do **not** change the top-level `required` array (old reports still validate).

4. **`src/segqc/human_report.py` — render extension.** Add an optional
   `image_features: "dict | None" = None` parameter to `render_feature_table`.
   When non-`None`, append an "Intensity features:" section after the existing
   sections: a header row + one row per `per_label` entry (ascending integer-label
   order) showing label, and mean/median/std/min/max/entropy via `_fmt_num`
   (rendering `None` as an explicit placeholder such as `(n/a)`); when the block's
   `available` is `False` or `per_label` is empty, render a single
   "(unavailable)"/"(none)" line. When `None` (default) append nothing — output is
   byte-identical to today. Update `__all__`/docstring as needed (the function is
   already exported).

5. **Do not** add a rule, a CLI flag, a config key, a pipeline entry point, or a
   `features/__init__.py` aggregation function, and do **not** write `tests/`
   fixtures — those are items 062/065 and the test-writer's remit.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_061_image_features_fusion.py`
  (naming matches the `test_0NN_*` siblings). Inputs are **hand-built**: construct
  `segqc.features.intensity.LabelIntensity` instances directly with known field
  values (populated and all-`None` sentinel), so every serialised number is
  hand-checkable and no scan/NiBabel fixture is needed. A minimal `verdict` +
  `config` for the `serialize_report` ACs is built the same way the
  `test_046`/`test_035` siblings build them (a `Verdict` with an empty/simple
  reasons set and a `bundled_default_config()` / `default_config()`), and a small
  `features_block` for the render ACs comes from `build_features_block` on
  hand-built dataclasses or a reused helper.
- **One focused test per AC** (AC1–AC13), each asserting a single observable fact
  against hand-computed expectations.
- **Adversarial / edge cases (beyond the ACs):**
  - **Empty intensity mapping** — `build_image_features_block({})` yields
    `available: true, per_label: {}` and serialises to a schema-valid block.
  - **Mixed populated + sentinel labels** — a block with one populated and one
    all-`None` label serialises with `allow_nan=False` succeeding and both entries
    present, ordered ascending.
  - **`extended` for a label absent from `intensity`** — is ignored (only labels
    present in `intensity` produce entries); a label in `intensity` but not in
    `extended` gets `extended: {}`.
  - **Non-mutation** — deep-copy `intensity` and `extended` before the call and
    assert equality afterward; assert byte-identical `json.dumps(sort_keys=True)`
    across two calls (AC7).
  - **Back-compat omission** — `serialize_report(verdict, case_id, config)` output
    is deep-equal to the same call before this item (no `image_features` key), and
    a report passing `features`/`findings`/`reference_delta` but no
    `image_features` also omits the key (AC9).
  - **Schema round-trip** — the block survives `json.dumps`/`json.loads` unchanged
    and re-validates; a block with a `null` statistic still validates (the
    `["number","null"]` union); an unknown extra key fails (AC10).
  - **Render back-compat** — `render_feature_table(features_block)` equals the
    pre-item render byte-for-byte (AC12); the intensity section formats a sentinel
    label without emitting `None`/`nan`/class-name text (AC13).

## Dependencies

- **Item 059 (present in tree) — REQUIRED.** Provides `LabelIntensity` and its 15
  fields (imported for typing) and `compute_intensity_features` (the source of the
  `intensity` mapping 065 will pass). Imported from `segqc.features.intensity`.
- **Item 060 (present in tree) — used via the optional seam, not imported.**
  Provides `LabelRadiomics.extended` / `compute_radiomics_features`; its per-label
  `extended` maps and `backend`/`radiomics_available` provenance flow into
  `build_image_features_block(extended=…, backend=…, radiomics_available=…)` when
  065 wires them. This item does **not** import `segqc.features.radiomics`.
- **Report serialiser + schema (items 009/016/035/046, ✅) — extended, not
  rewritten.** `serialize_report`/`serialize_report_json` gain an optional
  `image_features` parameter and `report_schema_v0.json` gains one optional
  top-level property + three definitions, exactly as `reference_delta` was added.
- **Human report (item 010/035, ✅) — extended, not rewritten.**
  `render_feature_table` gains an optional `image_features` parameter.
- **Downstream (this item feeds them):** **065** (wires 059/060 → this fusion into
  `segqc run`, populating `image_features` in the JSON + text reports and asserting
  Stage-8 acceptance) and, indirectly, **062** (the intensity heuristic renders its
  findings via the existing findings machinery; this block gives the numeric
  context in the report).

## Decisions & Trade-offs

- **Implemented exactly as specified** — no interface divergence found. All
  four surfaces (`feature_report.build_image_features_block`/
  `label_intensity_to_dict`, `report.serialize_report`/
  `serialize_report_json`, `report_schema_v0.json`, and
  `human_report.render_feature_table`) match the "Public interface" section
  and Implementation Steps verbatim.
- **`label_intensity_to_dict`** uses a fixed `_INTENSITY_FIELD_ORDER` tuple
  and a dict comprehension over `getattr(li, name)` rather than a literal
  dict, avoiding field-order duplication with the docstring while still
  guaranteeing a fixed key order (Python dict insertion order is guaranteed
  since 3.7, so `json.dumps(..., sort_keys=False)` output is deterministic
  either way; `sort_keys=True` is used in the AC7 test so the exact
  insertion order doesn't matter for that assertion).
- **Render layout**: the "Intensity features:" section reuses the existing
  `_fmt_num` helper via a new small `_fmt_or_na` wrapper (renders `None` as
  `(n/a)`) and a new `_render_image_features_section` helper, mirroring the
  existing `_render_findings_section` pattern. The unavailable/empty case
  (`available` falsy or `per_label` empty) renders a single `(unavailable)`
  line, satisfying both the "available=False" and the (unreachable in
  practice, but defensively handled) "available=True with empty per_label"
  cases with one code path.
- **Schema**: `imageFeatures`/`imageLabelFeatures`/`firstOrderIntensity`
  definitions were inserted immediately before the pre-existing
  `referenceFeatureDelta` definition (definitions order is irrelevant to
  `jsonschema` resolution; this placement groups the new Stage-8
  definitions together, adjacent to the Stage-6 `reference*` definitions).
- No `pipeline.py`, `cli.py`, `config.py`, `default_config.yaml`, or
  `features/__init__.py` changes were made, per the Assumptions' scope
  boundary (065's job).
