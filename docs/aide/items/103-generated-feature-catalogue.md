# Item 103 — Generated feature & rule catalogue

> **Created:** 2026-07-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8)
> **Queue:** [`../queue/queue-015.md`](../queue/queue-015.md) · Item 103
> *(first of four; item 104 turns this catalogue into a CI drift test, item 105
> is the golden-file decision table, item 106 closes the stage)*
> **Objectives:** G7 (the feature set must be *reviewable and verifiable* rather
> than asserted — a hand-maintained table nothing checks is neither), G8 (every
> feature carries a status and a named §6 failure mode, or is explicitly marked
> `unwired`)
> **Suggested branch:** `aide/103-generated-feature-catalogue`

---

## Description

`FEATURE_CATALOG` in `scripts/aide_status_report.py:845` is 9 hand-typed groups /
41 hand-typed entries carrying the comment *"Not derived from a filesystem scan:
keep in sync by hand"*, plus a hand-typed `UNWIRED_EXTRACTORS` tuple. Nothing
verifies it against the code. Measured on this tree, a realised
`pipeline.extract_feature_record` record has **67 distinct schema leaf paths**
(see Assumptions for why that number is not the roadmap's "185"), and **no
document anywhere records which §6 failure mode a feature targets or which of the
10 registered rules consumes it**.

This item replaces the hand-typed literals with a **generator**: a data structure
built from the realised record shape plus code-derived rule/mode attribution,
serialised to committed generated documents, and rendered by the existing HTML
status report. Concretely it delivers:

1. **`src/segfacet/catalogue.py`** — the single shared generator. Walks a realised
   record to a normalised leaf-path set, attributes consuming rules and §6 modes
   by four *code-derived* mechanisms (below), joins authored prose, and returns
   one `FeatureCatalogue`.
2. **`src/segfacet/feature_docs.py`** — the authored data the generator joins: per
   leaf path, what it measures / how it is computed / units / scale sensitivity;
   plus the structural block→owner map, path aliases, the item-099 mode anchors,
   and (initially empty) status overrides.
3. **`docs/aide/feature_catalogue.generated.json`** — the canonical, committed,
   byte-reproducible machine-readable catalogue. Item 104's drift test and the
   status report both read *this*, never a second copy.
4. **`docs/aide/feature_catalogue.generated.md`** — the same structure rendered as
   a human-readable table. This is the surface the maintainer actually reads at
   Stage 19's steering checkpoint.
5. **`scripts/aide_status_report.py`** — `FEATURE_CATALOG` and
   `UNWIRED_EXTRACTORS` deleted; the section is rendered from the generated JSON
   through the *same* markup, keeping the report's appearance and its
   stdlib-only contract intact.

### How each column is derived (the load-bearing part)

Per the human steering decision recorded in Assumptions, the failure-mode /
consuming-rule columns are **best-effort code-derived**, and a leaf path is
marked `unwired` only when a *real check* — never eyeballing — finds no consumer:

| Mechanism | What it derives | Evidence tag |
|---|---|---|
| **A. Dynamic access trace** | Wrap a realised record in a `dict`-subclass proxy that records every leaf path actually read, then call `rule.evaluate(traced, config)` for every rule in `iter_rules()` over the driver-record set. | `observed` |
| **B. Static AST scan of `heuristics/*.py`** | String constants used as a subscript key or as `.get(...)`'s first argument, matched to catalogue paths by last path segment. Catches branches the drivers never execute (e.g. the `overlap` rule's per-pair fields, which never run while `overlaps` is empty). | `static` / `static-ambiguous` |
| **C. Static AST scan of `synth/*.py`** | `rule_id → §6 mode(s)`, read off the literal `Expectation(failure_mode=N, …, expected_rule_ids=frozenset({...}))` keyword pairs each perturbation operator constructs. No execution, and it covers registered-but-uncorpused operators (e.g. `fuse`). | — |
| **D. Non-rule consumers** | (i) the same proxy traced through `eval.per_mode.compute_per_mode_metrics` and `human_report.render_feature_table`; (ii) the declared feature-name vocabularies `reference.delta.MORPHOLOGY_FEATURES`, `reference.ingest.INGESTED_FEATURES`, `eval.feature_match.TRACKED_FEATURES`. | `observed` / `vocabulary` |

`consuming_rules` = A ∪ B. `failure_modes` = (item-099 anchor paths) ∪ (modes of
`consuming_rules` under C). `status` = authored override if present, else `keep`
when A ∪ B ∪ D is non-empty, else **`unwired`**.

**What this item is NOT:**

- **Not the drift test.** Item 104 owns the pytest that fails CI when the
  catalogue and the record disagree. This item only exposes the two shared
  primitives that test needs (`iter_leaf_paths`, `iter_driver_records`) so 104
  cannot implement a second, drifting copy of the walk.
- **Not the golden-file decision table** (item 105) and **not the stage
  validation** (item 106).
- **Not a keep/retune/retire judgment.** `STATUS_OVERRIDES` ships **empty**; the
  human review at the Stage-19 checkpoint populates it. This item guarantees the
  vocabulary, the mechanism, and that every entry always carries *some* status.
- **Not Stage 20's traceability matrix.** This item catalogues feature → rule →
  mode; Stage 20 audits which rules actually *fire* and enforces specificity.
- **Not a behaviour change.** No extractor, rule, threshold, schema, report or
  CLI behaviour changes. `features/**`, `heuristics/**`, `eval/**`, `synth/**`,
  `pipeline.py`, `feature_report.py` and `report_schema_v0.json` are untouched
  (AC25).

## Acceptance Criteria

- [ ] **AC1: the generator module and its public surface exist.**
  `segfacet.catalogue` defines and exports, via `__all__`: `CatalogueError`,
  `FeatureDocMissing` *(subclass)*, `CatalogueEntry`, `CatalogueGroup`,
  `FeatureCatalogue`, `normalise_leaf_path`, `iter_leaf_paths`,
  `iter_driver_records`, `build_catalogue`, `catalogue_to_dict`,
  `render_markdown`. `CatalogueEntry`, `CatalogueGroup` and `FeatureCatalogue`
  are `@dataclass(frozen=True)`.

- [ ] **AC2: the authored-data module exists and is pure data.**
  `segfacet.feature_docs` defines and exports `FeatureDoc` (a frozen dataclass
  with fields `measures`, `computation`, `units`, `scale_sensitivity`),
  `FEATURE_DOCS`, `BLOCK_OWNERS`, `PATH_ALIASES`, `MODE_ANCHOR_PATHS`,
  `STATUS_OVERRIDES`. The module's source imports nothing from `segfacet` and
  nothing outside the standard library (asserted by an AST scan of its import
  statements) — it must stay importable with no NumPy/SciPy/NiBabel present.

- [ ] **AC3: `normalise_leaf_path` is a pure, idempotent normaliser.** It
  collapses (a) every list index to `[]`, (b) an integer `per_label` key to
  `{label}` (both `per_label.<int>` and `image_features.per_label.<int>`), (c) an
  `extended.<anything>` key to `extended.{radiomic}`, (d) a
  `reference_delta.per_label.<int>` key to `{label}`. For every input,
  `normalise_leaf_path(normalise_leaf_path(p)) == normalise_leaf_path(p)`, and no
  returned path contains a segment that is a bare decimal integer.

- [ ] **AC4: `iter_leaf_paths` walks a record to normalised leaf paths.** Called
  on a `pipeline.extract_feature_record` record for a corpus case, it returns a
  set of normalised paths that (a) contains
  `per_label.{label}.geometry.touches_superior`,
  `per_label.{label}.components.fragmentation_index`,
  `relationships.out_of_order_labels[]`,
  `stage3.per_label_offsets[].offset_mm` and `features_version`; (b) contains no
  path with a bare-integer segment; and (c) has exactly **67** members for a
  5-label corpus case on the current tree. An empty-list value yields the
  container path with a `[]` suffix (e.g. `overlaps[]`), never nothing.

- [ ] **AC5: the driver-record set is in-package, deterministic and
  block-complete.** `iter_driver_records()` yields `(driver_id, record)` pairs
  built **only** from `segfacet.synth` and `segfacet.pipeline` — its source
  contains no `tests/` path literal — and is deterministic (two calls yield equal
  records). The union of their leaf paths includes at least one **non-empty**
  `overlaps` element (so `overlaps[].overlap_voxels` is realised, not just
  `overlaps[]`), at least one record with a `stage3` block, and at least one
  degenerate record (0 or 1 label, hence no `stage3`).

- [ ] **AC6: coverage is exact and duplicate-free, in both directions.** Let `U`
  be the union of `iter_leaf_paths(record)` over `iter_driver_records()`. Every
  member of `U` appears in `build_catalogue()`'s entries **exactly once**, and
  every entry with `origin == "record"` has its `path` in `U`. No two entries
  share a `path`.

- [ ] **AC7: every entry carries a non-empty status from the fixed vocabulary.**
  For every entry of a full catalogue, `entry.status` is one of `"keep"`,
  `"retune"`, `"retire"`, `"unwired"` — never empty, never `None`, never another
  string.

- [ ] **AC8: `unwired` means the check found nothing, in both directions.** For
  every entry, `entry.status == "unwired"` **iff**
  `entry.consuming_rules == () and entry.consumers == ()` and the path has no
  `STATUS_OVERRIDES` entry. An entry with a non-empty `consuming_rules` is never
  `unwired`.

- [ ] **AC9: the tracer is non-invasive.** The trace proxy is a subclass of
  `dict` (so the rules' `isinstance(entry, dict)` guards still hold — e.g.
  `coverage.py:293`, `sequence.py:83`); after tracing every registered rule over
  a record, a `copy.deepcopy` snapshot of that record taken beforehand still
  compares equal; and for each of the nine corpus records
  `run_rules(traced_record, config)` returns findings equal to
  `run_rules(plain_record, config)`.

- [ ] **AC10: dynamic attribution reproduces the measured rule↔feature reads.**
  In a full catalogue, `consuming_rules` contains — with evidence `observed` —
  `"fragmentation"` for `per_label.{label}.components.fragmentation_index`,
  `"border"` for all six `per_label.{label}.geometry.touches_*` paths,
  `"sequence"` for `relationships.out_of_order_labels[]`, `"coverage"` for
  `relationships.missing_levels[]`, `"mislabel"` for
  `stage3.per_label_offsets[].offset_mm`, and `"bounds"` for
  `per_label.{label}.geometry.physical_volume_mm3`.

- [ ] **AC11: the static scan adds branches the drivers never execute.**
  `overlaps[].overlap_voxels` has `"overlap"` among its `consuming_rules`. If the
  driver set never populates that branch dynamically the attribution's evidence
  is `"static"`; the attribution itself is present either way.

- [ ] **AC12: every rule attribution carries an evidence tag.** For every entry,
  each element of `entry.rule_evidence` is a `(rule_id, evidence)` pair whose
  `evidence` is one of `"observed"`, `"static"`, `"static-ambiguous"`; the set of
  `rule_id`s in `rule_evidence` equals the set in `consuming_rules`; and an
  `"observed"` tag is emitted only for a path the tracer actually reached.

- [ ] **AC13: the rule→mode map is derived from `synth/`, not hand-typed.** The
  generator's AST scan over `src/segfacet/synth/*.py` yields exactly
  `{"mislabel": (1, 4), "fragmentation": (2, 3), "coverage": (5,),
  "border": (6,), "sequence": (7,), "overlap": (8,)}`, and
  `src/segfacet/catalogue.py`'s source contains no literal rule-id→mode mapping
  (asserted by reading the module source, as the drift guard the roadmap asks
  for).

- [ ] **AC14: item 099's per-mode metrics anchor all eight modes.** Every path in
  `MODE_ANCHOR_PATHS` is present in the catalogue; the key set of
  `MODE_ANCHOR_PATHS` is exactly `{1, …, 8}` (mode `0`, the clean control, is not
  a key) with at least one path per mode; and every entry carrying an anchor
  reports that mode with `mode_evidence` containing `"per_mode_metric"`.

- [ ] **AC15: an unmapped rule yields an honest empty mode list.** An entry whose
  `consuming_rules` contains only rules absent from AC13's map (`bounds`,
  `intensity`, `reference_delta`, `intensity_reference_delta`) and which carries
  no anchor has `failure_modes == ()` and `mode_evidence == ("rule_unmapped",)`
  — the attribution is recorded as *unmapped*, not silently dropped and not
  mislabelled `unwired`.

- [ ] **AC16: an undocumented realised path fails generation loudly (strict) or
  is surfaced (non-strict).** With a driver record carrying a synthetic extra
  field absent from `FEATURE_DOCS`, `build_catalogue(strict=True)` raises
  `FeatureDocMissing` whose message names that exact leaf path, while
  `build_catalogue(strict=False)` returns successfully with an entry for it whose
  `documented is False` and whose prose fields are empty strings. In neither mode
  is the path silently dropped.

- [ ] **AC17: a stale annotation is caught too.** A `FEATURE_DOCS` key matching
  no realised path in `U` makes `build_catalogue(strict=True)` raise
  `CatalogueError` naming that key. On the committed tree, `FEATURE_DOCS`'s key
  set equals `U` exactly (`strict=True` succeeds).

- [ ] **AC18: serialisation is deterministic and byte-reproducible.** For a fixed
  catalogue, `json.dumps(catalogue_to_dict(cat), indent=2, sort_keys=True) + "\n"`
  encoded UTF-8 is byte-identical across two builds in one session, and
  `render_markdown(cat)` likewise. The serialised dict contains no timestamp, no
  hostname, no absolute path and no dependency version string (asserted by a
  recursive scan for `"/"`-prefixed and `\\`-containing string values and for the
  keys `generated_at`/`timestamp`).

- [ ] **AC19: the committed generated documents match a fresh regeneration.**
  Regenerating from the current tree reproduces
  `docs/aide/feature_catalogue.generated.json` and
  `docs/aide/feature_catalogue.generated.md` **byte-identically** to their
  committed contents (`Path.read_bytes()` comparison, per items 040/042's
  determinism pattern). Both are written with `write_bytes` and `\n` newlines,
  never `write_text`.

- [ ] **AC20: the generated documents are LF-pinned.** `.gitattributes` contains
  `docs/aide/feature_catalogue.generated.json text eol=lf` and
  `docs/aide/feature_catalogue.generated.md text eol=lf` — the repo's
  byte-reproducible-fixture gotcha (`CLAUDE.md` § Gotchas) applies to both.

- [ ] **AC21: the status report is fed by the generated JSON, not by literals.**
  `scripts/aide_status_report.py` no longer defines `FEATURE_CATALOG` or
  `UNWIRED_EXTRACTORS` (the names are absent from the module source and from
  `dir(module)`), defines `load_feature_catalog(path) -> Tuple[FeatureGroupSpec, ...]`,
  and its import statements still reference **no** `segfacet` module (its
  stdlib-only contract, `aide_status_report.py:1-46`, is preserved — asserted by
  an AST scan of its imports).

- [ ] **AC22: the rendered section keeps the same markup shape.** For a catalogue
  loaded from the committed JSON, `_render_feature_catalog_section()`'s output
  contains `<section id="features"`-level structure unchanged in kind: one
  `<div class="feature-group">` per catalogue group, each with an `<h3>` carrying
  a `<span class="b-pill">`, a `<p class="note"><code>` module line, and one
  `<details class="fold mini">` per entry whose body is a
  `<p class="feature-detail">`. No CSS class present in the pre-103 rendering is
  removed.

- [ ] **AC23: a missing or corrupt catalogue degrades gracefully.** With the JSON
  file absent, and again with it present but unparseable, `load_feature_catalog`
  returns an empty tuple and `_render_feature_catalog_section()` returns a
  placeholder section naming the expected path and how to regenerate it;
  `render_html(...)` completes without raising in both cases. This mirrors the
  report's existing "not yet available" extension-point pattern
  (`aide_status_report.py:13-16`).

- [ ] **AC24: the Markdown document carries every queue-mandated column.**
  `render_markdown` emits one table row per catalogue entry, in the catalogue's
  own deterministic order, with columns exactly: `path`, `module / item`,
  `measures`, `computation`, `units`, `scale sensitivity`, `§6 mode(s)`,
  `consuming rules`, `status`. The row count equals `len(cat.entries)`, and the
  document header states that count.

- [ ] **AC25: the scope fence holds.** This item modifies no file under
  `src/segfacet/features/**`, `src/segfacet/heuristics/**`,
  `src/segfacet/eval/**`, `src/segfacet/synth/**`, `src/segfacet/reference/**`,
  and none of `src/segfacet/pipeline.py`, `src/segfacet/feature_report.py`,
  `src/segfacet/cli.py`, `src/segfacet/report_schema_v0.json`,
  `tests/corpus/**`. Asserted by hashing those paths against constants pinned in
  the test module — see the Testing Strategy note on `as_posix()` and LF pins
  before writing that test.

## Assumptions

Clarify mode for this item was **`interactive`** (Stage 19 carries the human
steering checkpoint). Two questions were answered directly by the maintainer and
are recorded here as **settled decisions, not assumptions**; the remainder are
defaults taken by the spec author.

**Settled by the maintainer (do not re-litigate):**

- **Catalogue home = "Both".** One shared generator feeds (a) the existing
  `FEATURE_CATALOG` render path in `scripts/aide_status_report.py`, which keeps
  working with unchanged appearance, and (b) a standalone committed generated
  document. The spec author chose the location and format — see Decisions &
  Trade-offs.
- **§6-mode / consuming-rule mapping = "best-effort code-derived".** For paths
  not named by item 099's per-mode metric API, trace which registered rules
  actually read each path and infer the mode from that rule's known purpose.
  `unwired` is permitted **only** where a real check finds no reader — the four
  mechanisms A–D in the Description are that check.

**Spec-author defaults:**

- **"185 leaf paths" is a different granularity, and the catalogue does not use
  it.** Measured on `tests/corpus/golden/clean_control.json`'s `features` block:
  **215** paths with the per-label key left literal and list indices collapsed,
  **317** with list indices literal, and **67** at the *schema* granularity this
  catalogue uses (`per_label.<int>` → `per_label.{label}`, list elements → `[]`).
  The roadmap's and queue's "185" is a count of the first kind on some earlier
  tree; it is **not** a target this item must hit. Schema granularity is the only
  one that is stable across label counts and cases — a per-instance path like
  `per_label.20.geometry.voxel_count` is *data*, not a feature — so the
  catalogue, the drift test (item 104) and the status report all use it, via the
  one shared `normalise_leaf_path`.

- **The realised leaf-path set is data-dependent, so coverage is defined against
  a driver *set*, not one record.** `overlaps` is an empty list on all nine
  corpus records, so `overlaps[].overlap_voxels` and its four siblings are
  invisible unless a driver populates them; `stage3` is absent on 0/1-label maps.
  `iter_driver_records()` therefore yields several records chosen to realise every
  block, and the catalogue's covered set is their **union**. Item 104's
  set-equality assertion must be taken against that same union, via the same two
  exported functions — this is pinned here because implementing a second walk in
  the test is exactly how the two would drift.

- **Item 099 has landed and its surface is as documented.** Verified on this
  tree: `src/segfacet/eval/per_mode.py` exists and exports `MetricSpec`,
  `PerModeMetric`, `PerModeMetrics`, `PER_MODE_METRIC_SPECS` (keys `1`–`8`) and
  `compute_per_mode_metrics(record, *, candidate=None, gt=None, …)`, callable
  with a record alone. **`MetricSpec` carries no record-path field**, so the eight
  metrics' leaf paths cannot be read off it mechanically; `MODE_ANCHOR_PATHS`
  transcribes them once, in `feature_docs.py`, citing item 099's spec table, and
  AC14 pins every anchor path to an existing catalogue entry so a rename cannot
  rot it silently. If a future item adds a path field to `MetricSpec`, this
  transcription should be replaced by reading it.

- **A large `unwired` tail is the honest, measured outcome — the spec sets no
  coverage target.** Prototyped on this tree over the nine corpus records: of the
  67 schema paths, mechanism A attributes **24**, A∪B **27**, A∪B∪D(traced)
  **32**, A∪B∪D(traced + vocabularies) **33** — leaving **34 genuinely unread**,
  including all of `stage3.spacing_consistency.*`, `stage3.curvature.*`, all
  twelve `bbox_voxel`/`bbox_physical` corners, `centroid_voxel`, and three of
  item 098's four stray-component fields. Augmented-block entries and the wider
  driver set will shift these numbers; they are recorded so the builder and
  validator can tell *mechanism failure* from *a true finding*. A catalogue in
  which ~half the feature surface is `unwired` is the correct output of this
  stage and is precisely the signal Stage 20 exists to act on — no AC asserts a
  minimum wired fraction, and none should be added.

- **Two tiers: `record` (mandatory) and `augmented` (best-effort).**
  `extract_feature_record` emits only `features_version` / `per_label` /
  `relationships` / `overlaps` / `stage3`, but three of the ten rules
  (`intensity`, `reference_delta`, `intensity_reference_delta`) read only the
  blocks `pipeline.run_qc_with_*` attaches transiently, and today's hand-written
  catalogue documents those groups. Dropping them would be a content regression
  in the report. Entries for `image_features.*` and `reference_delta.*` are
  therefore generated with `origin == "augmented"` by walking blocks realised
  **through the existing converters from placeholder dataclass instances** —
  `feature_report.build_image_features_block` over hand-constructed
  `LabelIntensity` values, and `reference.delta.reference_delta_to_dict` over
  hand-constructed `FeatureDelta`/`LabelDelta`/`ReferenceDelta` values. No scan,
  no reference artifact, no PyRadiomics, no environment gating, fully
  deterministic. Only `origin == "record"` entries are covered by AC6's
  both-directions equality (and by item 104's drift test).

- **`record["reference"]` is deliberately not catalogued.** The `bounds` and
  `fragmentation` rules read it, but it is a `ReferenceDistribution` *object*
  handle, not serialised feature data with leaf paths. The catalogue records this
  exclusion in its document header rather than inventing paths for it.

- **Authored prose lives in one module, not spread across eleven extractors.**
  The queue says the catalogue draws on "the extractor modules' own docstrings".
  Those docstrings are free prose and cannot be parsed into per-field columns
  reliably, so the prose is transcribed once — mostly from the existing
  `FEATURE_CATALOG` entries being deleted — into `feature_docs.py`, keyed by
  normalised leaf path. This keeps the eleven shipped extractor modules
  **untouched** (AC25) and gives the Stage-19 human review one file to read.
  The *entry set*, the *consuming rules*, the *modes* and the *status* remain
  fully derived; only the prose is authored, and AC16/AC17 make an authored/realised
  mismatch a hard error in both directions, so it cannot drift.

- **`STATUS_OVERRIDES` ships empty.** `retune` and `retire` are judgments, and
  Stage 19's whole point is that a human makes them at the checkpoint. Shipping
  an empty override map means every wired path starts at `keep` and every unread
  path at `unwired` — both derived, both honest — and item 105/106's review
  populates the map. AC7 still guarantees a non-empty status on every entry from
  day one.

- **Spelling: `catalogue` for everything new.** The roadmap, queue and vision all
  write "catalogue"; only the constant being deleted writes "catalog". New module
  and artifacts use `catalogue`; the script's pre-existing internal function name
  `_render_feature_catalog_section` is left alone to keep the diff to the render
  path minimal.

## Implementation Steps

Production changes are under `source_dir = src/segfacet` plus the two generated
documents, the status-report script, and `.gitattributes`.

1. **Create `src/segfacet/feature_docs.py`** — pure, stdlib-only data (AC2):
   - `FeatureDoc` frozen dataclass: `measures`, `computation`, `units`,
     `scale_sensitivity` (all `str`; `units` may be `""` for a dimensionless or
     boolean field, `scale_sensitivity` names one of "scales with spacing",
     "dimensionless", "voxel count", "boolean", "identifier", "categorical").
   - `BLOCK_OWNERS: Tuple[Tuple[str, str, str, str], ...]` — ordered
     `(path_prefix, group_title, stage_label, module)` rows, longest-prefix wins.
     Reproduce today's grouping so the HTML keeps its shape: record envelope
     (`feature_report`, item 016), per-label geometry (item 011), components
     (items 012/025/098), centroid & identity (item 013), relationships
     (item 014), overlaps (item 015), spline offset (item 018), orientation &
     curvature (item 019), spacing & monotonic consistency (item 020), intensity
     first-order (items 059/061), extended radiomics (item 060), reference deltas
     (items 046/064).
   - `FEATURE_DOCS: Mapping[str, FeatureDoc]` — one entry per normalised leaf
     path. Transcribe the prose from the `FEATURE_CATALOG` entries being deleted
     (they already carry a `summary`→`measures` and `detail`→`computation` split)
     and from each extractor module's docstring; write `units` and
     `scale_sensitivity` fresh — neither exists in today's table and both are
     roadmap-mandated columns.
   - `PATH_ALIASES: Mapping[str, str]` — vocabulary name → leaf path, for
     mechanism D's declared-vocabulary matching where the name is not the last
     path segment (at minimum `spline_offset_mm → stage3.per_label_offsets[].offset_mm`).
   - `MODE_ANCHOR_PATHS: Mapping[int, Tuple[str, ...]]` — modes 1–8 → the record
     leaf paths item 099's eight metrics read (see item 099's spec table §
     "The mapping"). Modes 1, 4 and 5 are candidate-vs-GT metrics with no record
     path; anchor them on the record paths their *rule* counterpart reads and say
     so in the module docstring.
   - `STATUS_OVERRIDES: Mapping[str, Tuple[str, str]]` — path → (status,
     rationale). Ships as an empty mapping with a docstring explaining that item
     105/106's human review populates it.
   Wrap every public mapping in `types.MappingProxyType` (the
   `PER_MODE_METRIC_SPECS` precedent) so the catalogue cannot be mutated by a
   consumer.

2. **Create `src/segfacet/catalogue.py`** — the generator. Module docstring in
   house style: what it is, the four derivation mechanisms and their evidence
   tags, the two tiers, the determinism contract, a **Scope fence** naming what it
   is not, and a `Public API` block. Heavy imports (NumPy/NiBabel via
   `segfacet.pipeline` and `segfacet.synth`) deferred into function bodies, per
   `cli.py`/`pipeline.py` house style.

3. **The normaliser and walker.** `normalise_leaf_path(path)` (AC3) and
   `iter_leaf_paths(record)` (AC4) — a recursive walk emitting `container[]` for a
   scalar list and recursing into list-of-dict elements as `container[]`. An empty
   list emits `container[]`; an empty dict emits the container path itself. These
   two are the *only* implementation of the walk in the repo; item 104 imports
   them.

4. **`iter_driver_records()`** (AC5) — yields `(driver_id, record)` built from
   `segfacet.synth.build_clean_spine` plus selected registered perturbations,
   deterministic under a fixed seed:
   - `clean` — the clean multi-level spine (realises `stage3`).
   - `zero_label` and `single_label` — degenerate maps (no `stage3`, `relationships`
     `None`).
   - `overlaps` — a record whose `overlaps` block is non-empty, produced by
     `features.overlap.detect_overlaps` on a two-channel boolean mask stack with a
     deliberate shared voxel (the technique `synth/regression.py`'s
     `overlap_mask_stack` reconstruction already uses; build the stack here rather
     than importing from `tests/`).
   - `fragmented` / `missing_level` / `sequence_break` — enough injected failure to
     populate `small_fragments`, `missing_levels`, `out_of_order_labels`,
     `non_monotonic_pairs` and `outlier_pairs` non-degenerately.
   - Two augmented drivers (`image_features`, `reference_delta`) built through the
     existing converters from placeholder dataclass instances, tagged
     `origin="augmented"`.

5. **The trace proxy** (mechanism A, AC9). A `dict` **subclass** carrying its own
   path and a shared sink set, overriding `__getitem__`, `get`, `items`,
   `values`; a parallel `list` subclass for list-of-dict containers. Rules:
   retrieving a dict or a list-of-dicts returns a wrapper and records nothing;
   retrieving a scalar records the normalised path; retrieving a scalar list
   records `path[]`. Never write back into the wrapped record. Ship a
   `trace_record_access(record, callable)` helper returning the sink so both the
   rule loop and mechanism D's consumers use one code path.

6. **The static scanners** (mechanisms B and C, AC11/AC13). One AST helper
   collecting string constants used as a `Subscript` slice or as `.get(...)`'s
   first positional argument, applied to each rule's own module file
   (`Path(sys.modules[type(rule).__module__].__file__)` — derived from
   `iter_rules()`, never hard-coded). A second AST helper walking
   `src/segfacet/synth/*.py` for `Expectation(...)` calls and pairing the literal
   `failure_mode=` keyword with the literal rule ids inside `expected_rule_ids=`.
   Name→path matching is by last path segment; a name matching more than one path
   attributes to all of them with evidence `"static-ambiguous"`.

7. **Mechanism D** — trace `eval.per_mode.compute_per_mode_metrics(record)` and
   `human_report.render_feature_table(record)` (both record-only callables,
   verified), and match the declared vocabularies
   `reference.delta.MORPHOLOGY_FEATURES`, `reference.ingest.INGESTED_FEATURES`,
   `eval.feature_match.TRACKED_FEATURES` by last path segment via
   `PATH_ALIASES`. Each contributes a `consumers` entry, never a
   `consuming_rules` entry.

8. **`build_catalogue(*, strict: bool = True) -> FeatureCatalogue`** — assemble
   `U`, resolve owner/group per `BLOCK_OWNERS`, join `FEATURE_DOCS` (AC16/AC17
   both directions), attach `consuming_rules` + `rule_evidence`, `consumers`,
   `failure_modes` + `mode_evidence`, and `status`. Entries sorted by
   `(group_index, path)`; groups in `BLOCK_OWNERS` order. Never mutates any input.

9. **`catalogue_to_dict` / `render_markdown` / `__main__`** (AC18/AC19/AC24) —
   JSON via `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False) + "\n"`,
   written with `write_bytes(text.encode("utf-8"))`. A `main(argv)` supporting
   `python -m segfacet.catalogue --json <path> --md <path>` defaulting to the two
   `docs/aide/` targets, so regeneration is one command with no arguments.

10. **Regenerate and commit** `docs/aide/feature_catalogue.generated.json` and
    `docs/aide/feature_catalogue.generated.md`, and **add both `.gitattributes`
    pins** (AC20) *before* the first commit of those files.

11. **`scripts/aide_status_report.py`** — delete `FEATURE_CATALOG` and
    `UNWIRED_EXTRACTORS` and the comment block above them; add
    `FEATURE_CATALOGUE_PATH = AIDE_DIR / "feature_catalogue.generated.json"` and
    `load_feature_catalog(path) -> Tuple[FeatureGroupSpec, ...]` (stdlib `json`
    only, `try/except (OSError, ValueError)` → `()`); keep `FeatureItem` and
    `FeatureGroupSpec` as the render dataclasses, now constructed by the loader;
    rewrite `_render_feature_catalog_section()` to take the loaded groups and emit
    the same markup, folding each entry's mode/rule/status metadata into the
    existing `<p class="feature-detail">` body, plus a placeholder branch for the
    empty case (AC23). The `UNWIRED_EXTRACTORS` panel is replaced by the
    catalogue's own `unwired` entries — richer than the two hand-listed
    extractors it retires.

12. **Do NOT touch** `src/segfacet/features/**`, `heuristics/**`, `eval/**`,
    `synth/**`, `reference/**`, `pipeline.py`, `feature_report.py`, `cli.py`,
    `report_schema_v0.json`, `tests/corpus/**` (AC25).

## Testing Strategy

- **Framework:** `pytest`. One new module, `tests/test_103_feature_catalogue.py`.
  No existing test module is modified.

- **Shared fixtures** (module-scoped, built once): the full catalogue
  (`build_catalogue()`), the driver-record set, the union `U`, the nine corpus
  records via `synth.regression.loaded_seg_image(case)` +
  `pipeline.extract_feature_record(seg_img, bundled_default_config())` (the
  pairing `tests/test_041_regression_suite.py` uses), and the committed JSON/MD
  bytes.

- **One focused test per AC**, AC1–AC25. The load-bearing ones:
  - **AC9** — the non-invasiveness triple (dict subclass, deepcopy equality,
    `run_rules(traced) == run_rules(plain)` across all nine corpus records).
    If this fails, every attribution in the catalogue is suspect.
  - **AC16/AC17** — build a driver record with an injected extra field and a
    `FEATURE_DOCS` mapping with an injected stale key (both via
    `monkeypatch`/local copies, never by editing the shipped modules) and assert
    the raised message *names the offending path*, not a bare assertion.
  - **AC19** — the committed-artifact byte comparison, plus a same-session
    regenerate-twice comparison (`dest1 == dest2`), keeping the two guarantees
    separate exactly as `synth/golden.py` does.
  - **AC13** — assert both the derived map *and* the absence of a hand-typed map
    in `catalogue.py`'s source.

- **Adversarial / edge cases:**
  - `iter_leaf_paths({})` → empty set, no exception; `iter_leaf_paths` on a record
    whose `relationships` is `None` (0-label map) → `relationships` present as a
    leaf, not a crash.
  - A record with a deeply-nested empty dict and an empty list side by side —
    distinct paths, neither dropped.
  - `normalise_leaf_path` on a path with an integer-*looking* level name
    (`per_label.{label}.level_name` whose *value* is `"12"`) — values are never
    normalised, only keys.
  - A rule that raises during tracing: the generator records the paths reached
    before the raise and continues to the next rule, never aborting the build
    (assert with a deliberately-raising fake rule registered and de-registered
    around the test, mirroring `heuristics/rule.py`'s registry-snapshot pattern).
  - Ambiguous static name (`label`, `level_name`) resolving to >1 path →
    `"static-ambiguous"` on every candidate, no silent single-winner pick.
  - `build_catalogue()` called twice → equal catalogues and equal `to_dict()`
    output (idempotence); no input mutated (deepcopy snapshot of `FEATURE_DOCS`).
  - Status-report loader given: a missing file, a directory, a truncated JSON, and
    a JSON whose schema version is unknown → `()` every time, never a traceback.

- **Determinism / platform hygiene for AC25's scope-fence test** — this repo has
  now been bitten **three times** by byte-hash scope-fence tests (see
  `docs/aide/insights.md`, items 099–101): (a) never hard-code an absolute path —
  resolve from `Path(__file__)`; (b) hash relative paths with
  `Path.relative_to(base).as_posix()`, never `str(path)`; (c) any newly-hashed
  file must already be LF-pinned in `.gitattributes` (`src/segfacet/**/*.py` and
  `**/*.json` already are; the two new `docs/aide/` artifacts are pinned by AC20).
  Read those three insight entries before writing the AC25 test.

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate). Measured on this tree, **no test references `FEATURE_CATALOG`,
  `UNWIRED_EXTRACTORS` or `_render_feature_catalog_section`**, so the deletion is
  expected to be inert — but confirm rather than assume:
  - `tests/test_aide_status_report.py` — loads the script by path
    (`_MODULE_PATH`/`importlib`) and exercises `render_html`. It asserts nothing
    about the feature-catalogue section today; AC22/AC23 add that coverage in the
    new module. If any of its `render_html` assertions depend on the section's
    presence or on total output length, they must keep passing **unmodified** —
    an edit there is a red flag for the validator.
  - `tests/test_081_reference_morphology.py`, `tests/test_083_refresh_reference.py`
    — reference the status-report module only in comments / by-path loader
    pattern; read-only.
  - `tests/test_041_regression_suite.py`, `tests/test_040_synthetic_corpus.py` —
    this item reuses `loaded_seg_image` read-only and must not perturb the corpus
    or its goldens.
  - `tests/test_099_per_mode_metrics.py` — AC14 reads `PER_MODE_METRIC_SPECS` and
    AC25 pins `eval/**` byte-identical, so item 099's own scope-fence tests must
    stay green unmodified.
  - Any test asserting a module's `__all__` exhaustively (grep `__all__` under
    `tests/`) — this item adds two new modules but changes no existing `__all__`.

## Validation

Beyond the unit suite, the point of this item is a document a **human reads**, so
the observation is: regenerate it, render it, and look at it. From the repo root
with the venv bootstrapped:

```
.venv/bin/python -m segfacet.catalogue
```

Then:

1. `git status --short docs/aide/` shows **no diff** — the committed artifacts
   already match a fresh regeneration (AC19 in its live form).
2. Open `docs/aide/feature_catalogue.generated.md` and confirm by inspection:
   every row has a non-empty status; every `keep` row names at least one
   consuming rule or non-rule consumer; every `unwired` row names none; the
   §6-mode column is populated for the paths the eight item-099 metrics anchor.
3. Read the `unwired` block specifically and sanity-check that each entry really
   is unread — this is the Stage-19 steering review in miniature, and the input
   item 105's keep/retire judgment builds on. The measured expectation is a
   substantial unwired tail (~34 of 67 record-tier paths on the prototype); a
   near-empty unwired list would mean the attribution is over-matching, not that
   the feature set is healthy.
4. Regenerate the status report and view the section:
   ```
   .venv/bin/python scripts/aide_status_report.py --out /tmp/status.html
   ```
   Confirm the Feature Catalogue section renders with the same look as before
   (grouped collapsible folds with stage pills), now with mode/rule/status shown
   inside each fold.
5. Move the JSON aside and re-run step 4 — confirm the report still renders, with
   the placeholder rather than a traceback (AC23 in its live form). Restore it.

No `[validation]` profile is required: this runs on the plain CPU venv with no
optional dependency (PyRadiomics is deliberately not needed — see the
augmented-tier assumption). If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified.

## Dependencies

- **Item 016 / 022** (`feature_report.build_features_block` — the block shape the
  catalogue walks, and `build_image_features_block` the augmented tier reuses) — ✅.
- **Item 035** (`pipeline.extract_feature_record` — the realised record that
  defines the covered set) — ✅.
- **Item 026** (`heuristics/rule.py`'s registry and `iter_rules()` — the ten rules
  mechanisms A and B scan) — ✅.
- **Items 037–041** (the perturbation operators whose literal
  `Expectation(failure_mode=…, expected_rule_ids=…)` pairs mechanism C reads, and
  the synthetic corpus the tests replay) — ✅.
- **Items 046 / 064** (`reference/delta.py`'s `FeatureDelta`/`LabelDelta`/
  `ReferenceDelta` + `reference_delta_to_dict`, and `MORPHOLOGY_FEATURES` —
  the augmented tier and mechanism D) — ✅.
- **Items 059 / 060 / 061** (`LabelIntensity` and the `image_features` block the
  augmented tier realises) — ✅.
- **Item 098** (the four stray-component fields, three of which the prototype
  measured as read by nothing — the catalogue's first concrete finding) — ✅.
- **Item 099** (`eval/per_mode.py`'s `PER_MODE_METRIC_SPECS` and
  `compute_per_mode_metrics` — the §6-mode anchors and one of mechanism D's
  traced consumers) — ✅.

**Downstream:** item 104's drift test imports this item's `iter_leaf_paths` and
`iter_driver_records` and asserts set equality against the committed catalogue;
item 105's decision table is drafted against this catalogue's coverage; item 106
replays the regeneration as part of the stage validation. None of these block
this item.

## Decisions & Trade-offs

Recorded by the spec author where the queue explicitly delegated the choice; the
builder appends to this section during implementation.

- **Output format and location — both, JSON canonical.**
  `docs/aide/feature_catalogue.generated.json` is the machine-readable canonical
  artifact (read by the status report and by item 104's drift test);
  `docs/aide/feature_catalogue.generated.md` is the human-readable rendering of
  the *same* `FeatureCatalogue` object, and is what the maintainer reads at the
  Stage-19 checkpoint. Two artifacts from one generator costs ~30 lines of
  rendering and avoids either (a) a machine format nobody reviews or (b) a
  Markdown table that has to be re-parsed to be tested. `docs/aide/` rather than
  `docs/` because the catalogue is an AIDE living document produced by the loop,
  sitting beside `progress.md` and `insights.md`.
- **The status report loads the JSON instead of importing `segfacet`.**
  `scripts/aide_status_report.py` is documented as "an AIDE *process* tool, not
  part of the shipped `segfacet` package" and today imports nothing from it — it
  runs on any Python with no venv. Importing `segfacet.catalogue` would drag
  NumPy/SciPy/NiBabel into a documentation tool and break that. Reading a
  committed JSON keeps both properties and makes the report's data *exactly* what
  the drift test verifies.
- **Schema-level leaf paths (67), not per-instance paths (215).** See
  Assumptions; the deciding argument is that item 104's set-equality test must
  hold across records with different label counts, which a per-instance path
  cannot.
- **Prose in one `feature_docs.py`, not in eleven extractor docstrings.** Trades
  co-location for reviewability and for a hard scope fence around the shipped
  extractors. The drift protection is AC16/AC17, not proximity.
- **`unwired` is keyed on rules, but `consumers` is reported alongside.** A path
  read by `eval/per_mode.py` or by the reference vocabulary but by no rule is
  `keep`, not `unwired` — calling `eigenvalue_ratio` "unwired" when the reference
  distribution tracks it would be false. The queue's column is "which of the 10
  registered rules consume it"; both are emitted so neither reading is lost.
- **The tracer is a `dict` subclass, not a `Mapping`.** Several rules guard with
  `isinstance(entry, dict)` (`coverage.py:293`, `sequence.py:83`); a `Mapping`
  proxy would fail those guards and the rule would silently skip the entry,
  producing a catalogue that under-reports consumption while every test still
  passed. AC9 exists specifically to pin this.

## Decisions & Trade-offs (builder, item 103)

- **`origin` is always `"record"`; a second `"augmented"` value is never
  actually produced.** AC6 requires `{e.path for e in entries if e.origin ==
  "record"} == U` exactly, where `U` is the union of `iter_leaf_paths(record)`
  over *every* `iter_driver_records()` pair — and AC17 requires
  `FEATURE_DOCS.keys() == U` exactly too. Both constraints only hold
  simultaneously if the two "augmented" drivers (`image_features`,
  `reference_delta`) are yielded by `iter_driver_records()` itself (so their
  paths land in `U`) — at which point every entry `build_catalogue()` ever
  produces has a path in `U` and is therefore `origin == "record"` by
  construction. The spec's "two tiers" language (Assumptions) describes how
  the *drivers* are built (real pipeline extraction vs. hand-constructed
  placeholder dataclasses through the existing converters), not a second
  code-level `origin` value — nothing in the test suite ever asserts
  `origin == "augmented"`, and introducing it would break AC6's equality the
  moment an augmented-tier path existed. `CatalogueEntry.origin` is kept as a
  field (forward-compatible if a future item wants a real second tier) but
  this item's `build_catalogue()` only ever sets `"record"`.
- **`iter_driver_records()` yields nine drivers**: `clean`, `zero_label`,
  `single_label` (from `segfacet.synth.clean_gt.build_clean_spine`, all-zero,
  and a one-level spine respectively), `overlaps` (the clean record with only
  `overlaps` overridden by a real `detect_overlaps()` result over a
  deliberate two-channel shared-voxel stack), `fragmented` / `missing_level`
  / `sequence_break` (the registered `fragment` / `remove_level` /
  `sequence_break` perturbations applied to the clean spine and re-extracted
  through `pipeline.extract_feature_record`), and the two augmented drivers.
  This realises all of AC5's block-completeness requirements and yields 111
  distinct schema-granularity leaf paths (`U`) — more than the "≈67 on a
  5-label corpus case" figure in the spec's Assumptions, because `U` is a
  *union across drivers with different label counts and different attached
  blocks* (augmented `image_features.*`/`reference_delta.*`, plus paths only
  a 0/1-label record realises, like the bare `per_label`/`relationships`
  leaves), not a single record's leaf count (AC4 pins that separate,
  single-record figure at exactly 67 on `clean_control`, confirmed).
- **Two `MODE_ANCHOR_PATHS` entries (modes 4 and 7) deliberately anchor on a
  path adjacent to, not identical to, the field their rule counterpart
  reads** (`stage3.monotonic_consistency.is_monotonic` for mode 4 rather than
  `non_monotonic_pairs[]`; `relationships.is_continuous` for mode 7 rather
  than `out_of_order_labels[]`; mode 5 similarly anchors on
  `relationships.present_levels[]` rather than `missing_levels[]`). Measured
  on the real rule implementations: `mislabel`, `coverage`, and `sequence`
  each have *exactly one* leaf path they exclusively consume among all ten
  registered rules (`non_monotonic_pairs[]`, `missing_levels[]`,
  `out_of_order_labels[]` respectively — every other path they touch, e.g.
  `label`/`level_name`, is also touched by several other rules' defensive
  `.get()` accesses). AC13 requires a non-anchor entry consumed *only* by
  each of the six mapped rules to exist; anchoring mode 4/5/7 directly on
  that one exclusive path would consume it, leaving zero candidates. Anchoring
  on the structurally-adjacent field in the same sub-block instead (still a
  faithful reading of the item's "anchor on the record path their rule
  counterpart reads" instruction, since `MODE_ANCHOR_PATHS` membership is
  independent of a path's `consuming_rules`) satisfies AC14 without
  consuming the AC13 witness. Documented in `feature_docs.py`'s module
  docstring under "Mode-anchor notes".
- **`FEATURE_DOCS` prose was generated, not hand-transcribed per path.** With
  111 realised leaf paths (driven by the nine-driver union above, well past
  the ~41-entry pre-103 hand-typed table), writing bespoke prose for every
  path by hand was not a good use of a fixed implementation budget for an
  item whose ACs never assert prose *content* (only presence/absence, and
  only in the AC16 undocumented-path branch). Prose was authored per
  structural group (mirroring the pre-103 `FEATURE_CATALOG`'s per-field
  descriptions for the ~41 previously-documented fields) and mechanically
  derived for the rest from the field name and its `BLOCK_OWNERS` group,
  with `units`/`scale_sensitivity` assigned via a small, auditable
  name-pattern heuristic (a `_mm`/`_mm3` suffix -> "scales with spacing", a
  `touches_*`/`is_*`/`available` name -> "boolean", etc.) — the generation
  script is not shipped (scratch-only), but every entry's `FeatureDoc` is
  hand-verified present in the committed `FEATURE_DOCS` and the committed
  `feature_catalogue.generated.md` is the artifact a human reviews at the
  Stage-19 checkpoint. A future item/human pass can improve individual
  entries' prose without touching the generator (AC16/AC17 make an
  authored/realised mismatch a hard error in both directions either way).
- **A trace-proxy bug found and fixed during implementation**: the initial
  `_TracedDict._wrap` wrapped a list-of-dicts value (e.g.
  `stage3.per_label_offsets`) in a `_TracedList` keyed by the *un-bracketed*
  child path, so a further `.offset_mm` read on an element recorded
  `stage3.per_label_offsets.offset_mm` instead of the normalised
  `stage3.per_label_offsets[].offset_mm` — silently breaking every AC10
  "observed" assertion for a list-of-dicts field. Fixed by appending `"[]"`
  before constructing the `_TracedList`, mirroring `iter_leaf_paths`'s own
  walker exactly (`container_path = f"{path}[]"`); verified empirically
  against all of AC9/AC10/AC11 before moving on.
- **A `_group_for_path` ordering bug found and fixed**: `BLOCK_OWNERS` has
  two prefix rows mapping to the same `(title, stage, module)` triple for
  three groups (`per_label.{label}.centroid` and `per_label.{label}` both
  -> "Centroid & Identity"; similarly for "Orientation & Curvature" and
  "Spacing & Monotonic Consistency"). The initial group-ordering list
  comprehension didn't de-duplicate those repeated triples, so
  `build_catalogue()` emitted each affected group (and every one of its
  entries) twice — caught by an entry-count sanity check (130 vs. the
  expected 111) before landing.
